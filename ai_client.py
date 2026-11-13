"""
ai_client.py
- Google Gemini API를 REST 방식(HTTP POST 요청)으로 호출하는 파일
- 요청 구성 -> 전송 -> 응답 처리 -> 예외 처리
"""

import os
import sys

import requests

API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/"
API_KEY_ENV_NAME = "GEMINI_API_KEY"


def get_api_key():
    """환경변수에서 API 키를 꺼낸다. 없으면 안내 메시지를 출력하고 종료한다."""
    api_key = os.environ.get(API_KEY_ENV_NAME)
    if api_key is None or api_key.strip() == "":
        print("[오류] " + API_KEY_ENV_NAME + " 환경변수가 설정되지 않았습니다.")
        print("       예) export " + API_KEY_ENV_NAME + '="발급받은키"')
        sys.exit(1)
    return api_key.strip()


def build_request_body(prompt, temperature, max_tokens):
    """API에 보낼 JSON 본문(body)을 만든다."""
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,      # 답변의 무작위성(창의성)
            "maxOutputTokens": max_tokens,   # 답변 최대 길이
        },
    }
    return body


def explain_http_error(status_code):
    """HTTP 상태 코드를 사람이 이해하기 쉬운 원인 설명으로 바꾼다."""
    if status_code == 400:
        return "요청 형식이 잘못되었습니다. (API 키, 모델 이름, 파라미터 값을 확인하세요)"
    if status_code == 401 or status_code == 403:
        return "인증 실패입니다. API 키가 올바른지 확인하세요."
    if status_code == 404:
        return "모델을 찾을 수 없습니다. --model 이름을 확인하세요."
    if status_code == 429:
        return "요청 한도를 초과했습니다. 잠시 후 다시 시도하세요."
    if status_code >= 500:
        return "Gemini 서버 쪽 문제입니다. 잠시 후 다시 시도하세요."
    return "알 수 없는 오류입니다."


def extract_text(data):
    """응답 JSON에서 AI가 쓴 글자만 꺼낸다."""
    candidates = data.get("candidates")
    if candidates is None or len(candidates) == 0:
        # 안전 필터 등으로 답변이 차단된 경우
        feedback = data.get("promptFeedback", {})
        reason = feedback.get("blockReason", "알 수 없음")
        print("[오류] AI가 답변을 만들지 않았습니다. (차단 사유: " + str(reason) + ")")
        sys.exit(1)

    first = candidates[0]
    finish_reason = first.get("finishReason", "")
    parts = first.get("content", {}).get("parts", [])

    text = ""
    for part in parts:
        if "text" in part:
            text = text + part["text"]

    if text.strip() == "":
        if finish_reason == "MAX_TOKENS":
            print("[오류] max_tokens 한도에 걸려 답변이 비어 있습니다. --max-tokens 값을 늘려 보세요.")
        else:
            print("[오류] AI 응답이 비어 있습니다. (종료 사유: " + str(finish_reason) + ")")
        sys.exit(1)

    if finish_reason == "MAX_TOKENS":
        print("[경고] 답변이 max_tokens 한도에서 잘렸을 수 있습니다. --max-tokens 값을 늘려 보세요.")

    return text


def call_gemini(prompt, model, temperature, max_tokens):
    """Gemini API를 1번 호출하고, AI가 쓴 텍스트를 돌려준다."""
    # 1) API 키 준비
    api_key = get_api_key()

    # 2) 요청 구성: 주소 + 헤더 + 본문
    url = API_BASE_URL + model + ":generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    body = build_request_body(prompt, temperature, max_tokens)

    # 3) 요청 전송 + 네트워크 예외 처리 (서버에 도착도 못 한 경우)
    print("[LOG] AI API 호출 중... (model=" + model + ")")
    try:
        response = requests.post(url, headers=headers, json=body, timeout=60)
    except requests.exceptions.Timeout:
        print("[오류] 요청 시간(60초)이 초과되었습니다. 네트워크 상태를 확인하세요.")
        sys.exit(1)
    except requests.exceptions.ConnectionError:
        print("[오류] Gemini 서버에 연결할 수 없습니다. 인터넷 연결을 확인하세요.")
        sys.exit(1)
    except requests.exceptions.RequestException as error:
        print("[오류] 요청 중 문제가 발생했습니다: " + str(error))
        sys.exit(1)

    # 4) 서버가 거절한 경우 (도착은 했지만 200 OK가 아님)
    if response.status_code != 200:
        print("[오류] API 호출 실패 (HTTP " + str(response.status_code) + ")")
        print("       원인: " + explain_http_error(response.status_code))
        try:
            detail = response.json()["error"]["message"]
            print("       상세: " + detail)
        except Exception:
            print("       상세: " + response.text[:300])
        sys.exit(1)

    # 5) 정상 응답 -> JSON 해석 -> 텍스트 꺼내기
    try:
        data = response.json()
    except ValueError:
        print("[오류] 응답을 JSON으로 해석할 수 없습니다.")
        sys.exit(1)

    return extract_text(data)