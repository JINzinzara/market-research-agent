# Live 단계 전환 검증

검증 시각: 2026-10-16T07:16:30.422603+00:00

**이 문서는 구현 검증 기록이다. 실제 LLM 품질 점수가 아니다.**

- 단위·통합 테스트: 90개 통과. 제공자 연결·인용·벤치마크 실행기 검사는 모의 응답을 사용했다.
- 보존한 합성 baseline 회귀 사례: 20/20 통과. 일반 실행과 UI 평가의 기본값은 live다.
- 실제 8000번 서버: 이전 스키마에는 web 필드가 없었다. 최신 가상환경 서버로 교체했다.
- 같은 live/OpenAI/web=false 본문을 다시 보냈을 때 HTTP 200으로 수락됐다. 결과는 키 부재에 따른 error, 외부 요청은 0회였다. 실제 Astra 성공 기록이 아니다.
- /api/status: research-live-v1, /openapi.json: web 필드 및 live 기본값 확인. 브라우저에서도 키 설정 안내를 확인했다.
- 기존 web 필드 없는 실행 기록은 web=false로 해석해 재현하는 호환 경계를 검사했다.
- GitHub 원격과 이 대화의 인증 GitHub 커넥터 읽기 동작을 확인했다. 앱 자체 MCP 서버는 구현하지 않았다.
- JavaScript 구문과 Git 공백 검사를 통과했다.

환경: Python 3.13.9; httpx 0.28.1, pydantic 2.14.1, fastapi 0.143.2, uvicorn 0.54.0, nltk 3.10.3, rank-bm25 0.2.2. 프로젝트 .venv 사용.

패키지 코드/자료 SHA-256: `6e7ad70dba6a73ae69879a0849a8eac4190bff6d67f829991fb7e71e148261d4`

파일럿 데이터 SHA-256: `b041d59033d57237be2d11913f9650355366af7119abc9b9656ffbad94daf6ce`

실제 Astra 호출·검색 품질·의미 정답률·청구 비용은 미측정이다. 독립 gold 검토도 받지 않았다. [평가 기준](../live-research-evaluation.md)을 따른다.
