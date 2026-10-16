# OpenAI 연결과 실제 조사 실행

**현재 기본값은 live + OpenAI + 웹 조사다.** 일반 실행과 evaluate는 합성 시세를 사용하지 않는다. 키는 실행 프로세스가 읽을 수 있어야 한다.

## 설치와 키 입력

저장소 루트에서 Python 3.10 이상을 사용한다. 현재 검증 환경은 Python 3.13이다.

```zsh
python3 -m venv .venv
.venv/bin/python -m pip install .
read -rs "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
PYTHONPATH=src .venv/bin/python -m market_agent serve
```

`read -s`가 입력을 숨긴다. 키를 채팅·명령문·커밋에 직접 적지 않는다. 이미 서버가 켜져 있으면 종료한 뒤 키를 설정한 같은 터미널에서 다시 시작한다. 환경변수는 다른 터미널이나 기존 프로세스에 자동 전달되지 않는다. [OpenAI 공식 quickstart](https://developers.openai.com/api/docs/quickstart)

`.env` 자동 로드는 하지 않는다. 종료 후 현재 터미널의 키를 해제하려면 `unset OPENAI_API_KEY`를 실행한다. `/api/status`는 키 설정 여부만 반환한다.

## 실제 뉴스·거시 조사

```sh
PYTHONPATH=src .venv/bin/python -m market_agent research 'Find recent bitcoin news and official US macro releases.'
PYTHONPATH=src .venv/bin/python -m market_agent evaluate --limit 2 --output .market-agent/pilot.json
```

evaluate의 2개 질문은 첫 한·영 쌍만 실행한다. 전체 12개는 `--limit 12`다. 모델·검색 비용이 발생하며 키가 없으면 시작 전에 종료한다. [평가셋 선정과 채점 기준](live-research-evaluation.md)을 먼저 읽는다.

웹 조사가 필요 없는 가격 계획만 확인하려면 `--no-web`을 붙인다. 예: `research 'BTC ETH BNB 7d' --no-web --planner ollama`. Qwen의 계획 추출과 Astra의 웹 조사 보고서는 다른 과제이므로 점수를 직접 비교하지 않는다.

현재 실제 Astra 접근·검색·답변 품질은 미검증이다. 연결 코드의 모의 응답 테스트와 실제 모델 점수를 혼동하지 않는다. [서버 버전 불일치 오류](integration-status.md), [웹 조사와 예산](web-research.md).
