# 연결 상태와 로컬 서버 오류

**GitHub 원격과 이 Codex 대화의 GitHub 커넥터는 연결돼 있다.** `JINzinzara/market-research-agent`의 원격 이력과 인증 계정을 실제로 확인했다. 이는 앱이 MCP 서버로 구현됐다는 뜻은 아니다. 앱 자체의 MCP 서버/클라이언트는 만들지 않았다. 이번 사용 오류를 해결하는 데 MCP 추가는 필요하지 않았다.

## `extra_forbidden`, `loc=[body, web]`

화면은 새 `web` 필드를 보내는데 실행 중인 이전 백엔드의 ResearchRequest 스키마에는 그 필드가 없었다. 실제 8000번 서버의 `/openapi.json`에서 이를 확인했다. 소스 파일만 바뀌고 Python 프로세스는 이전 코드를 들고 있었던 것이 원인이다.

이전 프로세스를 종료하고 프로젝트 가상환경의 최신 코드로 교체했다. 같은 `web=false` 요청이 HTTP 200으로 수락되는 것과 외부 요청 0회를 확인했다. 당시 실행 결과는 API 키 부재에 따른 error였고, 실제 Astra 응답 성공은 아니다.

현재 UI는 `/api/status`의 `research-live-v1` 계약을 확인한다. 계약이 다르거나 상태 경로가 없으면 재시작 안내를 보여준다. 정적 파일은 캐시를 재검증하고 자산 URL도 갱신했다. `extra=forbid` 검증 자체는 유지한다.

## 실행 환경을 맞추는 방법

```zsh
read -rs "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
PYTHONPATH=src .venv/bin/python -m market_agent serve
```

8000번에 이미 서버가 있으면 먼저 그 서버를 종료한다. 키를 설정한 같은 터미널에서 다시 시작한다. 다른 터미널에 export하거나 나중에 export해도 이미 실행 중인 서버에는 전달되지 않는다. `/api/status`의 `openai_key_configured`는 설정 여부만 보여주고 키는 반환하지 않는다. `.env` 자동 로드는 하지 않는다.

개발 중 Python 변경을 자동 반영하려면:

```sh
PYTHONPATH=src .venv/bin/python -m uvicorn market_agent.api:create_app --factory --host 127.0.0.1 --port 8000 --reload --reload-dir src
```

서버가 재시작돼도 실행 기록은 `.market-agent/runs/`에 남는다. API 키와 개인 지원 문서는 Git에 올리지 않는다. 현재 확인일: 2026-10-16.
