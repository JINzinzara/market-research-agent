# 01 — llm.py 작성 가이드

**현재 상태: 작성하신 코드의 HTTPX 호출과 응답 검증을 수정하고 확인했습니다.** 수정한 본문과 영문 docstring은 [llm.py](../src/market_agent/llm.py)에 있습니다. 아래 순서와 비교하며 각 줄의 역할을 확인합니다.

작성 경로: `src/market_agent/llm.py`.

## 역할과 입출력

이 파일은 Ollama와의 통신을 담당합니다. 조사 계획의 의미, 지원 거래쌍, 출처의 정확성은 후속 파일이 검증합니다.

- `client`: 호출자가 생성한 `httpx.AsyncClient`. Ollama 루트 URL과 타임아웃이 설정되어 있어야 합니다.
- `model`: 모델 이름. 첫 실행에서는 합의한 `qwen3:8b`를 사용합니다.
- `messages`: `role`과 `content`를 포함한 순서 있는 메시지 목록.
- `schema`: 선택적인 JSON Schema. `None`이면 일반 텍스트를 요청하고, 전달되면 `format`에 넣습니다.
- 반환값: `message.content`만 추출하지 않은 **전체 Ollama 응답 딕셔너리**.

응답에 있는 `prompt_eval_count`, `eval_count`, 처리 시간 필드를 그대로 유지합니다. 보고되지 않은 사용량을 0으로 채우지 않습니다. Ollama의 duration 필드는 나노초이며, 단위 변환은 평가·표시 단계에서 처리합니다. [공식 Chat API 응답](https://docs.ollama.com/api/chat)

`schema`는 생성 형식을 요청하는 데 사용합니다. 이 함수가 `message.content`를 업무 모델로 파싱하거나 필드의 의미를 검증하지는 않습니다. 이후 호출부에서 Pydantic 모델로 검증합니다. [구조화된 출력과 검증](https://docs.ollama.com/capabilities/structured-outputs)

## 참고할 코드

1. 기존 로컬 학습 예제의 `ask_json()`: 요청 필드, 완료 여부 확인, HTTP 오류 처리를 읽습니다. 마지막의 `json.loads(content)`는 이 함수에 옮기지 않습니다. 전체 응답을 반환한다는 계약이 다릅니다.
2. [원본 get_llm()](https://github.com/langchain-ai/local-deep-researcher/blob/03537326ffa0dd90c9702bece2f3aeba5d84162a/src/ollama_deep_researcher/graph.py#L97): 모델 이름·주소·temperature와 출력 모드의 관계를 참고합니다. 이번에는 HTTPX로 직접 호출하므로 ChatOllama·LMStudio 분기를 가져올 필요가 없습니다.
3. [HTTPX 비동기 가이드](https://www.python-httpx.org/async/): 클라이언트 수명과 비동기 요청을 확인합니다.
4. [HTTPX MockTransport](https://www.python-httpx.org/advanced/transports/#mock-transports): 모델을 실제로 실행하지 않고 요청·응답·오류를 검증하는 데 사용합니다.

## 작성 순서

1. 모델 이름이 공백뿐인 문자열이거나 메시지 목록이 비어 있으면 요청 전에 `ValueError`를 발생시킵니다.
2. 요청 본문에 `model`, `messages`, `stream=False`, `think=False`, `options`의 `temperature=0`을 넣습니다.
3. `schema is not None`인 경우에만 `format`을 넣습니다. 원래 메시지나 schema 객체를 수정하지 않습니다.
4. 전달받은 클라이언트로 `POST /api/chat`을 요청합니다. 클라이언트는 이 함수 안에서 생성하거나 종료하지 않습니다.
5. `raise_for_status()`로 HTTP 상태를 확인한 뒤 응답의 JSON을 읽습니다. 비동기 요청에는 `await`가 필요하고 `response.json()`에는 필요하지 않습니다.
6. 응답이 딕셔너리이고 `message`가 딕셔너리인지 확인합니다. 구조가 잘못되면 `ValueError`를 발생시킵니다.
7. `done`이 실제 불리언 `True`이고 `message.content`가 공백뿐이지 않은 문자열인지 확인합니다. 완료되지 않았거나 사용할 본문이 없으면 `RuntimeError`를 발생시킵니다.
8. 원래 응답 딕셔너리를 반환합니다.

`done=True`만으로 답변의 품질이나 업무 스키마 일치를 판단하지 않습니다. 이 파일은 응답 수신 경계까지만 확인합니다.

## 오류와 초기 설정

- HTTP 오류·접속 실패·타임아웃은 HTTPX 예외를 호출자에게 전달합니다. 광범위한 `except Exception`으로 성공처럼 처리하지 않습니다.
- 응답 자체가 잘못된 JSON이면 파싱 오류를 전달합니다. 응답의 `message.content` 내부 JSON 검증은 후속 호출부의 책임입니다.
- 자동 재시도, 임의의 대체 답변, 원문 응답 출력은 추가하지 않습니다.
- 클라이언트의 기본 URL은 `http://localhost:11434`입니다. `/api/chat` 요청 경로와 중복되지 않도록 루트 주소를 사용합니다.
- 타임아웃 초기값 300초는 이전 `ask_json()`에서 사용한 값입니다. 검증된 최적값이나 전체 워크플로우 시간 제한이 아니며, 실제 측정 후 조정합니다. 이번 함수의 기본 인자에 추가하지 않고 호출자가 클라이언트에 설정합니다.
- `temperature=0`과 `think=False`는 이전 실습과 같은 초기 조건입니다. 낮은 temperature가 항상 동일한 출력이나 높은 정확도를 보장하지는 않습니다.
- `keep_alive="10m"`은 작성하신 코드와 이전 `ask_json()`의 설정을 유지한 값입니다. 모델을 메모리에 유지하는 시간이므로 HTTP 요청 타임아웃과 구분합니다.

## 작성하신 코드에서 수정한 부분

- `async with client.post() as client`를 `await client.post("/api/chat", json=payload)`로 변경했습니다. post는 응답을 반환하는 코루틴이며, 전달받은 클라이언트를 새 변수로 덮어쓰거나 종료하지 않습니다.
- `client.raise_for_status(payload)`를 `response.raise_for_status()`로 변경했습니다. 이 메서드는 HTTP 응답의 상태를 확인하며, payload를 보내거나 응답 내용을 반환하지 않습니다. await도 필요하지 않습니다.
- HTTP 응답 객체는 `response`, 파싱한 딕셔너리는 `result`로 구분했습니다. 딕셔너리 검사는 `response.json()` 이후에 수행합니다.
- 입력 `messages`는 목록이고 응답의 `message`는 딕셔너리입니다. `message.get("content")`로 답변 본문을 읽습니다.
- 정의되지 않은 `done` 대신 `result.get("done")`을 사용합니다. 정상 응답에 오류를 내던 조건을 바꿔, 미완료이거나 본문이 없을 때만 거부합니다.
- schema가 None이면 `format`을 생략합니다. 빈 딕셔너리 schema도 전달할 수 있도록 `is not None`으로 확인합니다.
- 빈 모델 이름·빈 메시지 목록 검사를 추가하고, 반환값은 전체 응답으로 유지합니다.

## 완료 기준

[tests/test_llm.py](../tests/test_llm.py)를 함께 작성했습니다. HTTPX MockTransport와 표준 라이브러리 unittest의 `IsolatedAsyncioTestCase`를 사용하므로 비동기 테스트용 추가 플러그인은 필요하지 않습니다.

- 정상 응답: 전체 응답과 보고된 사용량·시간 정보가 유지됩니다.
- 형식 선택: schema가 없으면 `format`을 생략하고, 있으면 전달한 schema를 사용합니다.
- 입력 보존: 호출 후 원래 messages와 schema가 바뀌지 않습니다.
- 빈 입력: 공백뿐인 모델 이름과 빈 메시지 목록은 HTTP 호출 전에 거부합니다.
- HTTP 오류·타임아웃·접속 실패: 예외가 호출자에게 전달됩니다.
- 응답 파싱: 잘못된 JSON과 잘못된 응답 구조를 거부합니다.
- 완료 확인: `done=False`, `done` 누락, 불리언이 아닌 값, 빈 본문·공백 본문을 거부합니다.
- 클라이언트 수명: 호출 후 전달한 클라이언트가 닫히지 않습니다.

2026-10-15 모의 테스트 7개를 통과했습니다. 실제 Qwen3:8B 호출에서는 일반 텍스트 `OK.`와 JSON `{"status": "ok"}`를 각각 확인했습니다. 이 두 호출은 연결·생성 형식 확인이며, 일반적인 답변 정확도나 업무 스키마의 신뢰성을 검증한 결과는 아닙니다.

**2026-10-16 갱신:** 기존 GitHub의 `schema.py`와 스키마 테스트를 로컬에 반영했습니다. 원격의 단수형 파일명을 유지하므로 `schemas.py`를 새로 만들지 않습니다. 다음 파일은 [tools.py](../src/market_agent/tools.py)이며 [작성 가이드](02-tools.md)를 따릅니다. 이 문서의 중심은 기존 Ollama 통신 함수입니다. 현재는 별도 연구 워크플로우·평가·OpenAI 통신 경계도 구현했으며 Ollama 네이티브 `tools` 프로토콜은 구현하지 않았습니다. 재구성한 전체 흐름은 [구조와 구현 순서](implementation-plan.md)에 있습니다.
