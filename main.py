import argparse
import sys

import ai_client
import git_utils

import prompts

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_MAX_TOKENS = 4096

LINE = "=" * 60


def build_parser():
    parser = argparse.ArgumentParser(description="AI 커밋/PR 초안 생성기")
    parser.add_argument("command", choices=["commit", "pr"])
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="Gemini 모델 (기본값: " + DEFAULT_MODEL + ")")
    parser.add_argument("--temperature", type=float, default=None,
                        help="0.0~2.0, 지정하지 않을 시 모델 기본값 사용")
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
                        help="AI 답변 최대 토큰 수")
    parser.add_argument("--lang", choices=["ko", "en"], default="ko",
                        help="결과 언어 (기본값: ko)")
    return parser


def check_options(args):
    if args.temperature is not None:
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

    if args.command == "commit":
        prompt = prompts.build_commit_prompt(status_text, diff_text, args.lang, "")
    else:
        prompt = prompts.build_pr_prompt(status_text, diff_text, args.lang, "")

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