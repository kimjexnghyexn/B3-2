"""
main.py  (실행 시작점)
- argparse로 CLI 옵션을 읽고, 다른 파일들의 함수를 순서대로 불러 전체 흐름을 지휘한다.

전체 흐름
 1. 옵션 읽기 (argparse)
 2. 실행 위치 확인 (git 저장소 루트인지)
 3. git status / git diff 수집 -> 변경 없으면 종료
 4. (safe-mode) 민감정보 마스킹 + diff 일부만 전송
 5. 프롬프트 만들기 (commit용 / pr용)
 6. AI API 1회 호출
 7. 결과 검증 + 후처리
 8. 구분선으로 나눠서 출력

사용 예)
  python3 main.py commit
  python3 main.py pr --safe-mode
  python3 main.py commit --model gemini-2.5-flash --temperature 0.2 --max-tokens 800
"""

import argparse
import sys

import ai_client
import git_utils
import prompts
import safety
import validator

# 기본값 (CLI 옵션으로 바꿀 수 있음)
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.3      # 낮을수록 일관되고 정확한 문장 (커밋 메시지에 적합)
DEFAULT_MAX_TOKENS = 1024      # 답변 최대 길이

# safe-mode 제한값
SAFE_MAX_FILES = 10
SAFE_MAX_LINES = 200

# safe-mode가 아니어도 항상 적용하는 상한 (비용 보호)
ALWAYS_MAX_DIFF_CHARS = 30000

LINE = "=" * 60
THIN_LINE = "-" * 60


def build_parser():
    """CLI 명령어와 옵션을 정의한다."""
    parser = argparse.ArgumentParser(
        description="git diff를 분석해 AI로 커밋 메시지 / PR 초안을 생성하는 CLI",
    )
    parser.add_argument(
        "command",
        choices=["commit", "pr"],
        help="commit: 커밋 메시지 생성 / pr: PR 제목과 본문 생성",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="사용할 Gemini 모델 (기본값: " + DEFAULT_MODEL + ")",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help="0.0~2.0, 낮을수록 일관된 결과 (기본값: " + str(DEFAULT_TEMPERATURE) + ")",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="AI 답변 최대 토큰 수 (기본값: " + str(DEFAULT_MAX_TOKENS) + ")",
    )
    parser.add_argument(
        "--safe-mode",
        action="store_true",
        help="민감정보 마스킹 + diff 일부만 전송 (최대 10개 파일, 200줄)",
    )
    parser.add_argument(
        "--lang",
        choices=["ko", "en"],
        default="ko",
        help="결과 언어 (기본값: ko)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="AI를 호출하지 않고, 보낼 프롬프트만 출력 (비용 0, 마스킹 확인용)",
    )
    return parser


def check_options(args):
    """옵션 값이 올바른 범위인지 확인한다."""
    if args.temperature < 0.0 or args.temperature > 2.0:
        print("[오류] --temperature 는 0.0 ~ 2.0 사이여야 합니다.")
        sys.exit(1)
    if args.max_tokens <= 0:
        print("[오류] --max-tokens 는 1 이상이어야 합니다.")
        sys.exit(1)


def print_section(title, content):
    """구분선과 헤더를 붙여서 한 구역을 출력한다."""
    print("")
    print(LINE)
    print("  " + title)
    print(LINE)
    print(content)


def main():
    # 1. 옵션 읽기 -------------------------------------------------
    parser = build_parser()
    args = parser.parse_args()
    check_options(args)

    # 2. 실행 위치 확인 ---------------------------------------------
    if not git_utils.is_git_repo():
        print("[오류] Git 저장소가 아닙니다. 'git init' 된 프로젝트 폴더에서 실행하세요.")
        sys.exit(1)
    if not git_utils.is_project_root():
        print("[오류] 프로젝트 루트(최상위) 폴더에서 실행하세요.")
        sys.exit(1)

    # 3. git 변경 사항 수집 -----------------------------------------
    status_text = git_utils.get_status()
    if status_text.strip() == "":
        print("변경 사항이 없습니다.")
        sys.exit(0)

    diff_text = git_utils.get_diff()
    changed_files = git_utils.get_changed_files(status_text)

    print("[LOG] 변경된 파일 " + str(len(changed_files)) + "개 감지")

    # 새 파일(??)만 있고 diff가 비어 있는 경우 안내
    extra_notes = []
    if diff_text.strip() == "":
        diff_text = "(diff 없음: 새로 만든 파일(untracked)만 있습니다. git add 하면 내용까지 분석합니다.)"
        extra_notes.append("diff 내용은 없고 파일 목록만 있음. 파일 이름으로 추론해서 작성할 것.")

    # 4. 안전 처리 --------------------------------------------------
    if args.safe_mode:
        diff_text, limit_notes = safety.limit_diff(diff_text, SAFE_MAX_FILES, SAFE_MAX_LINES)
        diff_text, mask_count = safety.mask_secrets(diff_text)
        status_text, status_mask_count = safety.mask_secrets(status_text)
        print("[SAFE] 민감정보 마스킹 " + str(mask_count + status_mask_count) + "건")
        for note in limit_notes:
            print("[SAFE] " + note)
            extra_notes.append(note)

    diff_text, was_cut = safety.truncate_text(diff_text, ALWAYS_MAX_DIFF_CHARS)
    if was_cut:
        print("[LOG] diff가 너무 길어 앞 " + str(ALWAYS_MAX_DIFF_CHARS) + "자만 전송합니다. (--safe-mode 사용 권장)")
        extra_notes.append("diff가 길어 뒷부분이 생략됨")

    # 5. 프롬프트 만들기 ---------------------------------------------
    note_text = "\n".join(extra_notes)
    if args.command == "commit":
        prompt = prompts.build_commit_prompt(status_text, diff_text, args.lang, note_text)
    else:
        prompt = prompts.build_pr_prompt(status_text, diff_text, args.lang, note_text)

    if args.dry_run:
        print_section("[DRY RUN] AI에 보낼 프롬프트 (API 호출 안 함)", prompt)
        print("")
        print("[LOG] AI API 호출 횟수: 0회 (dry-run)")
        sys.exit(0)

    # 6. AI API 호출 (1회) -------------------------------------------
    api_call_count = 0
    ai_text = ai_client.call_gemini(prompt, args.model, args.temperature, args.max_tokens)
    api_call_count = api_call_count + 1
    print("[LOG] AI API 호출 횟수: " + str(api_call_count) + "회")

    # 7. 검증 + 후처리 ------------------------------------------------
    blocks = validator.parse_blocks(ai_text)
    summary = validator.get_summary(blocks)

    if args.command == "commit":
        title, body, check_messages = validator.validate_commit(blocks, changed_files)
    else:
        title, body, check_messages = validator.validate_pr(blocks)

    # 8. 출력 ---------------------------------------------------------
    print_section("[1] 변경 요약", summary)

    if args.command == "commit":
        commit_message = title
        if body != "":
            commit_message = title + "\n\n" + body
        print_section("[2] 커밋 메시지 (복사해서 사용하세요)", commit_message)
    else:
        print_section("[2] PR 제목", title)
        print_section("[3] PR 본문", body)

    print("")
    print(THIN_LINE)
    print("  형식 검증 결과")
    print(THIN_LINE)
    for message in check_messages:
        print(message)

    print("")
    print("※ AI가 만든 초안입니다. 내용을 검토한 뒤 적용하세요.")
    if args.command == "commit":
        print('  적용 예) git commit -m "' + title.replace('"', '\\"') + '"')


if __name__ == "__main__":
    main()