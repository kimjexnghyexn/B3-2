import argparse
import sys

import ai_client
import git_utils

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 1024

LINE = "=" * 60


def build_parser():
    parser = argparse.ArgumentParser(description="AI 커밋/PR 초안 생성기")
    parser.add_argument("command", choices=["commit", "pr"])
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Gemini 모델 (기본값: " + DEFAULT_MODEL + ")")
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE,
                        help="0.0~2.0, 낮을수록 일관된 결과")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="AI 답변 최대 토큰 수")
    return parser


def check_options(args):
    if args.temperature < 0.0 or args.temperature > 2.0:
        print("[오류] --temperature 는 0.0 ~ 2.0 사이여야 합니다.")
        sys.exit(1)
    if args.max_tokens <= 0:
        print("[오류] --max-tokens 는 1 이상이어야 합니다.")
        sys.exit(1)


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

    # 임시 프롬프트 (3단계에서 prompts.py로 교체 예정)
    if args.command == "commit":
        request = "다음 git 변경 사항을 보고 커밋 메시지를 작성해줘. 제목 1줄과 불릿 본문으로."
    else:
        request = "다음 git 변경 사항을 보고 PR 제목과 본문을 작성해줘."
    prompt = request + "\n\n[git status]\n" + status_text + "\n[git diff]\n" + diff_text

    api_call_count = 0
    result = ai_client.call_gemini(prompt, args.model, args.temperature, args.max_tokens)
    api_call_count = api_call_count + 1
    print("[LOG] AI API 호출 횟수: " + str(api_call_count) + "회")

    print(LINE)
    print("  AI 결과")
    print(LINE)
    print(result)


if __name__ == "__main__":
    main()