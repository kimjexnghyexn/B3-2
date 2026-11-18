import argparse
import sys

import ai_client
import git_utils

import prompts

import validator

import safety

DEFAULT_MODEL = "gemini-3.5-flash-lite"
DEFAULT_MAX_TOKENS = 4096

LINE = "=" * 60
THIN_LINE = "-" * 60

def build_parser():
    parser = argparse.ArgumentParser(description="AI 커밋/PR 초안 생성기")
    parser.add_argument("command", choices=["commit", "pr"])
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Gemini 모델 (기본값: " + DEFAULT_MODEL + ") / "
                             + "선택 가능: gemini-3.8-flash, gemini-3.5-flash-lite")
    parser.add_argument("--temperature", type=float, default=None,
                        help="0.0~2.0, 지정하지 않을 시 모델 기본값 사용")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="AI 답변 최대 토큰 수")
    parser.add_argument("--lang", choices=["ko", "en"], default="ko",
                        help="결과 언어 (기본값: ko)")
    parser.add_argument("--safe-mode", action="store_true",
                        help="API 키, 이메일, 비밀번호 등을 ***MASKED*** 로 가린 뒤 전송")
    return parser


def check_options(args):
    if args.temperature is not None:
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
    parser = build_parser()
    args = parser.parse_args()
    check_options(args)

    if not git_utils.is_git_repo():
        print("[오류] Git 저장소가 아닙니다.")
        sys.exit(1)
    if not git_utils.is_project_root():
        print("[오류] 프로젝트 루트(최상위) 폴더에서 실행하세요.")
        sys.exit(1)

    status_text = git_utils.get_status()
    if status_text.strip() == "":
        print("변경 사항이 없습니다.")
        sys.exit(0)

    diff_text = git_utils.get_diff()
    changed_files = git_utils.get_changed_files(status_text)

    if args.safe_mode:
        diff_text, diff_count = safety.mask_secrets(diff_text)
        status_text, status_count = safety.mask_secrets(status_text)
        print("[SAFE] 민감정보 마스킹 " + str(diff_count + status_count) + "건")
    
    if args.command == "commit":
        prompt = prompts.build_commit_prompt(status_text, diff_text, args.lang, "")
    else:
        prompt = prompts.build_pr_prompt(status_text, diff_text, args.lang, "")
        
    # AI API 호출 (1차)
    api_call_count = 0
    ai_text = ai_client.call_gemini(prompt, args.model, args.temperature, args.max_tokens)
    api_call_count = api_call_count + 1

    # 형식 검증 -> 위반이 있으면 재생성 요청 (최대 1회)
    blocks = validator.parse_blocks(ai_text)
    if args.command == "commit":
        problems = validator.find_commit_problems(blocks, changed_files)
    else:
        problems = validator.find_pr_problems(blocks)

    regenerated = False
    if len(problems) > 0:
        print("[LOG] 형식 위반 " + str(len(problems)) + "건 발견 -> AI에 재생성 요청 (최대 1회)")
        for problem in problems:
            print("      - " + problem)

        fix_prompt = prompts.build_fix_prompt(ai_text, problems)
        ai_text = ai_client.call_gemini(fix_prompt, args.model, args.temperature, args.max_tokens)
        api_call_count = api_call_count + 1
        regenerated = True

        # 재생성 결과를 다시 검사 (더 이상 재요청하지 않음)
        blocks = validator.parse_blocks(ai_text)
        if args.command == "commit":
            problems = validator.find_commit_problems(blocks, changed_files)
        else:
            problems = validator.find_pr_problems(blocks)

    print("[LOG] AI API 호출 횟수: " + str(api_call_count) + "회")

    summary = validator.get_summary(blocks)
    if args.command == "commit":
        title, body = validator.get_commit(blocks)
    else:
        title, body = validator.get_pr(blocks)
    check_messages = validator.make_report(args.command, blocks, problems, regenerated)

    # 출력
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
    
if __name__ == "__main__":
    main()