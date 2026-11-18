"""
safety.py
- --safe-mode 일 때, AI에게 보내기 '전에' diff 속 민감정보를 가리는 파일
- 과제 제약 사항 (A): diff에서 특정 패턴(API Key 형태, 이메일 등)을 마스킹 후 전송

이 도구는 어떤 프로젝트에서든 실행할 수 있으므로,
내가 쓰는 Gemini 키뿐 아니라 diff에 들어올 수 있는 여러 종류의 비밀을 가린다.
"""

import re

MASK = "***MASKED***"

# 민감한 값의 '모양'을 정규표현식(regex)으로 정의
# 예) [A-Za-z0-9]{20,} = 영문/숫자가 20글자 이상 연속
SECRET_PATTERNS = [
    # Google(Gemini) API 키: AIza로 시작 + 35글자
    r"AIza[0-9A-Za-z_\-]{35}",
    # OpenAI / Anthropic 키: sk- 로 시작
    r"sk-[A-Za-z0-9_\-]{16,}",
    # GitHub 토큰: ghp_, gho_ 등으로 시작
    r"gh[pousr]_[A-Za-z0-9]{30,}",
    # AWS Access Key: AKIA로 시작 + 16글자
    r"AKIA[0-9A-Z]{16}",
    # 이메일 주소: 아이디@도메인.확장자
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
]

# password = "1234" 처럼 '이름 = 값' 형태의 비밀 값
# 괄호 ( ) 로 묶은 첫 부분(이름과 =)은 남기고, 값만 가린다.
ASSIGNMENT_PATTERN = r"((?:api[_\-]?key|secret|password|passwd|token|access[_\-]?key)\s*[=:]\s*)[\"']?[^\"'\s,]+[\"']?"


def mask_secrets(text):
    """민감한 값을 가린 텍스트와, 가린 개수를 돌려준다.

    예) 'API_KEY = "AIzaSy..."'  ->  'API_KEY = ***MASKED***'
    """
    total_count = 0

    # 1) '이름 = 값' 형태를 먼저 가린다
    # flags=re.IGNORECASE : 대소문자 구분 없이 (PASSWORD, Password 모두)
    result = re.subn(ASSIGNMENT_PATTERN, r"\1" + MASK, text, flags=re.IGNORECASE)
    text = result[0]
    total_count = total_count + result[1]

    # 2) 남은 부분에서 키/이메일 모양을 찾아 가린다
    for pattern in SECRET_PATTERNS:
        # re.subn: 패턴에 맞는 부분을 모두 바꾸고 (바뀐 문자열, 바꾼 개수)를 돌려줌
        result = re.subn(pattern, MASK, text)
        text = result[0]
        total_count = total_count + result[1]

    return text, total_count