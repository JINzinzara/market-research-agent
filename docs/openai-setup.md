# OpenAI API 연결과 실행

현재 구현은 **선택형 LLM 계획 생성이 붙은 고정 연구 워크플로우**다. 모델이 도구를 자율 선택하며 반복 실행하는 에이전트는 아니다. API 통신 코드는 이미 [llm.py](../src/market_agent/llm.py)에 있고, 키를 읽어 인증 헤더를 만드는 곳은 [runtime.py](../src/market_agent/runtime.py)다.

## 최초 설치

저장소 루트에서 Python 3.10 이상으로 실행한다. Python이 여러 개 설치돼 있으면 의존성을 설치한 가상환경의 Python을 일관되게 사용한다.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
```

## 키 입력 — macOS zsh

다음 명령을 본인 터미널에서 실행하고 프롬프트에 키를 붙여 넣는다. `read -s`가 입력을 숨기므로 실제 키를 명령문이나 셸 히스토리에 직접 적을 필요가 없다.

```sh
read -rs "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
```

OpenAI 공식 문서도 `OPENAI_API_KEY` 환경변수로 키를 전달한다. 위 `read`는 값을 숨겨 입력하기 위한 zsh 명령이다. [공식 API quickstart](https://developers.openai.com/api/docs/quickstart)

## 같은 터미널에서 실행

실제 Binance 조회와 GPT-6 Astra 계획 생성:

```sh
PYTHONPATH=src .venv/bin/python -m market_agent research 'BTC ETH BNB 7d' --mode live --planner openai
```

웹 콘솔:

```sh
PYTHONPATH=src .venv/bin/python -m market_agent serve
```

`http://127.0.0.1:8000`에서 Planner를 `GPT-6 Astra · paid API`로 선택한다. 이미 실행 중인 서버에는 나중에 설정한 환경변수가 전달되지 않으므로 기존 서버를 종료한 뒤 키를 설정한 터미널에서 다시 시작한다.

같은 합성 시장 자료로 모델을 비교하려면:

```sh
PYTHONPATH=src .venv/bin/python -m market_agent evaluate --planner ollama --output .market-agent/qwen.json
PYTHONPATH=src .venv/bin/python -m market_agent evaluate --planner openai --output .market-agent/astra.json
```

각 명령은 원시 JSON과 같은 이름의 Markdown 요약을 만든다. 이 비교에서 시장 자료는 합성이지만 모델 요청은 실제 호출이다. OpenAI API 이용료가 발생한다.

작업 후 현재 터미널의 키를 해제하려면:

```sh
unset OPENAI_API_KEY
```

키 값은 채팅·README·커밋에 넣지 않는다. 현재 프로그램은 `.env`를 자동으로 읽지 않는다. API 키가 없으면 호출 전에 종료한다. Astra의 실제 계정 접근과 성능은 아직 검증하지 않았으며, 현재 연결 코드는 모의 응답으로 검사했다.
