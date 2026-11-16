"""
validator.py
- AI가 돌려준 결과를 '검사'하는 파일 (고치지는 않는다)
- 규칙을 어긴 부분을 찾아 '문제 목록'으로 돌려주면,
  main.py가 그 목록을 AI에게 보내 재생성을 요청한다. (최대 1회)

검증 규칙 (과제 요구사항)
- 커밋 제목: 50자 이내 권장, 최대 72자
- 커밋 본문: (있다면) 불릿 요약 또는 변경 파일 언급
- PR 제목 : 최대 80자
- PR 본문 : Why / What / How to Test 섹션 헤더 필수 + 각 섹션 최소 1개 불릿
"""

COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
PR_TITLE_MAX = 80
REQUIRED_SECTIONS = ["Why", "What", "How to Test"]


# ---------------------------------------------------------------
# 1. AI 답변을 구역별로 나누기 (파싱)
# ---------------------------------------------------------------
def remove_code_fence(text):
    """AI가 ``` 로 감싸서 답한 경우, ``` 줄을 지운다."""
    result_lines = []
    for line in text.split("\n"):
        if line.strip().startswith("```"):
            continue
        result_lines.append(line)
    return "\n".join(result_lines)


def parse_blocks(text):
    """'===이름===' 표시를 기준으로 결과를 나눠 딕셔너리로 돌려준다.

    예) "===SUMMARY===\n- a\n===COMMIT===\nfix: b"
        -> {"RAW": 원문, "SUMMARY": "- a", "COMMIT": "fix: b"}
    """
    text = remove_code_fence(text)
    blocks = {"RAW": text.strip()}   # 형식 표시가 없을 때를 대비해 원문도 보관
    current_name = ""
    current_lines = []

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("===") and stripped.endswith("===") and len(stripped) > 6:
            # 이전 구역 저장
            if current_name != "":
                blocks[current_name] = "\n".join(current_lines).strip()
            current_name = stripped.strip("=").strip().upper()
            current_lines = []
        else:
            current_lines.append(line)

    if current_name != "":
        blocks[current_name] = "\n".join(current_lines).strip()

    return blocks


def clean_title(title):
    """제목 앞뒤의 따옴표, # 기호, 공백을 정리한다."""
    title = title.strip()
    title = title.strip("\"'`")
    while title.startswith("#"):
        title = title[1:].strip()
    return title.strip()


def first_non_empty_line(text):
    """텍스트에서 비어 있지 않은 첫 줄과, 그 다음 줄 번호를 돌려준다."""
    lines = text.split("\n")
    for i in range(len(lines)):
        if lines[i].strip() != "":
            return lines[i], i + 1
    return "", len(lines)


def is_bullet(line):
    """'- ' 로 시작하는 불릿 줄인지 확인한다."""
    return line.strip().startswith("- ")


# ---------------------------------------------------------------
# 2. 결과 꺼내기 (출력용)
# ---------------------------------------------------------------
def get_summary(blocks):
    summary = blocks.get("SUMMARY", "")
    if summary == "":
        return "(요약 없음)"
    return summary


def get_commit(blocks):
    """커밋 제목과 본문을 돌려준다."""
    commit_text = blocks.get("COMMIT", "")
    if commit_text == "":
        commit_text = blocks.get("RAW", "")

    first_line, body_start = first_non_empty_line(commit_text)
    title = clean_title(first_line)
    body = "\n".join(commit_text.split("\n")[body_start:]).strip()
    return title, body


def get_pr(blocks):
    """PR 제목과 본문을 돌려준다."""
    first_line, body_start = first_non_empty_line(blocks.get("PR_TITLE", ""))
    title = clean_title(first_line)

    body = blocks.get("PR_BODY", "")
    if body == "":
        body = blocks.get("RAW", "")
    return title, body.strip()


# ---------------------------------------------------------------
# 3. 규칙 검사 (문제 목록 만들기)
# ---------------------------------------------------------------
def find_commit_problems(blocks, changed_files):
    """커밋 결과에서 규칙 위반을 찾아 리스트로 돌려준다. 문제가 없으면 빈 리스트."""
    problems = []

    if blocks.get("COMMIT", "") == "":
        problems.append("===COMMIT=== 구분 표시와 커밋 메시지가 없습니다.")
        return problems

    title, body = get_commit(blocks)

    # 제목 검사
    if title == "":
        problems.append("커밋 제목(첫 줄)이 비어 있습니다.")
    elif len(title) > COMMIT_TITLE_MAX:
        problems.append("커밋 제목이 " + str(len(title)) + "자입니다. "
                        + str(COMMIT_TITLE_MAX) + "자 이내(권장 50자)로 줄이세요.")

    # 본문 검사 (본문은 선택 사항이지만, 있다면 최소 품질을 지켜야 함)
    if body != "":
        has_bullet = False
        for line in body.split("\n"):
            if is_bullet(line):
                has_bullet = True
                break

        mentions_file = False
        for file_name in changed_files:
            short_name = file_name.split("/")[-1]
            if short_name != "" and short_name in body:
                mentions_file = True
                break

        if not has_bullet and not mentions_file:
            problems.append("커밋 본문에 '- ' 불릿 요약이나 변경 파일 이름이 없습니다.")

    return problems


def find_section_name(line):
    """'## Why' 같은 헤더 줄이면 섹션 이름(Why)을, 아니면 빈 문자열을 돌려준다."""
    stripped = line.strip()
    if not stripped.startswith("#"):
        return ""
    name = stripped.lstrip("#").strip().rstrip(":").strip().lower()
    if name.startswith("how to test"):
        return "How to Test"
    if name.startswith("why"):
        return "Why"
    if name.startswith("what"):
        return "What"
    return ""


def split_pr_sections(body_text):
    """PR 본문을 섹션별 줄 리스트로 나눈다. {"Why": [...], "What": [...], ...}"""
    sections = {}
    current = ""
    for line in body_text.split("\n"):
        name = find_section_name(line)
        if name != "":
            current = name
            sections[current] = []
            continue
        if current != "" and line.strip() != "":
            sections[current].append(line)
    return sections


def find_pr_problems(blocks):
    """PR 결과에서 규칙 위반을 찾아 리스트로 돌려준다. 문제가 없으면 빈 리스트."""
    problems = []
    title, body = get_pr(blocks)

    # 제목 검사
    if title == "":
        problems.append("===PR_TITLE=== 구분 표시와 PR 제목이 없습니다.")
    elif len(title) > PR_TITLE_MAX:
        problems.append("PR 제목이 " + str(len(title)) + "자입니다. "
                        + str(PR_TITLE_MAX) + "자 이내로 줄이세요.")

    # 본문 섹션 검사
    if blocks.get("PR_BODY", "") == "":
        problems.append("===PR_BODY=== 구분 표시와 PR 본문이 없습니다.")
        return problems

    sections = split_pr_sections(body)
    for name in REQUIRED_SECTIONS:
        if name not in sections:
            problems.append("'## " + name + "' 섹션 헤더가 없습니다.")
            continue

        bullet_count = 0
        for line in sections[name]:
            if is_bullet(line):
                bullet_count = bullet_count + 1
        if bullet_count == 0:
            problems.append("'## " + name + "' 섹션에 '- ' 불릿이 하나도 없습니다.")

    return problems


# ---------------------------------------------------------------
# 4. 검증 결과 보고서 (출력용 메시지)
# ---------------------------------------------------------------
def make_report(command, blocks, problems, regenerated):
    """최종 검증 결과를 사람이 읽기 좋은 메시지 리스트로 만든다."""
    messages = []

    if regenerated:
        messages.append("[재생성] 1차 결과의 형식 위반으로 AI에 1회 재생성을 요청함")

    if command == "commit":
        title, body = get_commit(blocks)
        if len(title) <= COMMIT_TITLE_RECOMMENDED:
            messages.append("[통과] 커밋 제목 " + str(len(title)) + "자 (권장 50자 이내)")
        elif len(title) <= COMMIT_TITLE_MAX:
            messages.append("[경고] 커밋 제목 " + str(len(title)) + "자 (권장 50자 초과, 최대 72자 이내)")
    else:
        title, body = get_pr(blocks)
        if len(title) <= PR_TITLE_MAX:
            messages.append("[통과] PR 제목 " + str(len(title)) + "자 (80자 이내)")

    if len(problems) == 0:
        messages.append("[통과] 모든 형식 규칙을 만족함")
    else:
        for problem in problems:
            messages.append("[위반] " + problem)
        messages.append("※ 재생성 후에도 남은 위반입니다. 적용 전에 직접 수정하세요.")

    return messages