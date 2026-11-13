import argparse
import sys

import git_utils


def main():
    parser = argparse.ArgumentParser(description="AI 커밋/PR 초안 생성기")
    parser.add_argument("command", choices=["commit", "pr"])
    args = parser.parse_args()

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

    print("명령:", args.command)
    print("변경된 파일:", changed_files)
    print("=" * 60)
    print(diff_text)


if __name__ == "__main__":
    main()