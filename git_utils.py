"""
git_utils.py
- git status / git diff 명령을 실행해서 결과를 "문자열"로 돌려주는 파일
- 파일로 저장하지 않고 subprocess로 결과를 바로 변수에 담는다.
"""

import os
import subprocess
import sys


def run_git(args):
    """git 명령을 실행하고 결과(문자열)를 돌려준다. 실패하면 None을 돌려준다.
    """
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,   # 터미널에 찍힐 결과를 붙잡는다
            text=True,             # bytes가 아니라 문자열(str)로 받는다
            encoding="utf-8",      # 한글이 깨지지 않도록 UTF-8로 해석
            errors="replace",      # 해석이 안 되는 글자는 ?로 바꿔서 프로그램이 죽지 않게
        )
    except FileNotFoundError:
        print("[오류] git이 설치되어 있지 않습니다. git을 먼저 설치하세요.")
        sys.exit(1)

    # returncode가 0이면 성공, 0이 아니면 실패
    if result.returncode != 0:
        return None
    return result.stdout


def is_git_repo():
    """현재 폴더가 git 저장소 안인지 확인한다."""
    output = run_git(["rev-parse", "--is-inside-work-tree"])
    if output is None:
        return False
    # /n의 출력 제거
    return output.strip() == "true"


def is_project_root():
    """현재 폴더가 git 저장소의 '루트(최상위) 폴더'인지 확인한다."""
    output = run_git(["rev-parse", "--show-toplevel"])
    if output is None:
        return False
    root_path = os.path.realpath(output.strip())
    current_path = os.path.realpath(os.getcwd())
    return root_path == current_path


def get_status():
    """git status 결과를 짧은 형식으로 돌려준다.
    """
    output = run_git(["status", "--short"])
    if output is None:
        return ""
    return output


def get_changed_files(status_text):
    """git status 결과에서 파일 이름만 뽑아 리스트로 돌려준다."""
    files = []
    lines = status_text.split("\n")
    for line in lines:
        if line.strip() == "":
            continue
        # 앞의 2글자는 상태 표시(M, A, ?? 등), 그 뒤가 파일 이름
        name = line[3:].strip()
        # 이름이 바뀐 파일은 "old -> new" 형식이므로 새 이름만 사용
        if " -> " in name:
            name = name.split(" -> ")[1]
        files.append(name)
    return files


def get_diff():
    """변경 내용(diff)을 문자열로 돌려준다.

    - staged  : git add 해서 커밋 준비가 된 변경   (git diff --cached)
    - unstaged: 아직 git add 안 한 변경            (git diff)
    """
    staged = run_git(["diff", "--cached"])
    unstaged = run_git(["diff"])

    if staged is None:
        staged = ""
    if unstaged is None:
        unstaged = ""

    diff_text = ""
    if staged.strip() != "":
        diff_text = diff_text + "### Staged changes (git add 된 변경)\n" + staged + "\n"
    if unstaged.strip() != "":
        diff_text = diff_text + "### Unstaged changes (git add 안 된 변경)\n" + unstaged + "\n"
    return diff_text


# 이 파일만 단독으로 실행했을 때 테스트용: python3 git_utils.py
if __name__ == "__main__":
    if not is_git_repo():
        print("Git 저장소가 아닙니다.")
        sys.exit(1)

    status = get_status()
    if status.strip() == "":
        print("변경 사항이 없습니다.")
        sys.exit(0)

    print("=== git status ===")
    print(status)
    print("=== 변경된 파일 목록 ===")
    print(get_changed_files(status))
    print("=== git diff ===")
    print(get_diff())