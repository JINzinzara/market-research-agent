# 첫 버전 검증 기록

이 문서는 초기 버전의 보존 기록이다. 이후 79개 테스트와 실제 Qwen 개발 평가, 계획 계약 수정은 [최신 지표·모델 비교 기록](metrics-and-model-comparison.md)을 따른다.

검증일: 2026-10-16 KST. **단위·통합 테스트 52개와 개발용 20개 사례가 통과했다.** 실제 Binance 조회와 로컬 Ollama 계획 생성도 아래 기록에서 완료됐고, 같은 기록의 오프라인 재현은 외부 네트워크 없이 같은 결과를 만들었다.

## 코드와 환경

- 패키지: `market-agent 0.1.0`
- Python: `3.13.9` · OS: `Darwin`
- 코드/패키지 자료 SHA-256: `fba2ed8424adf5177a46f11ad28bab2f253a1b764e2ae6f9a302fe33b46acaf3`
- 테스트: `PYTHONPATH=src python3 -m unittest discover -s tests -q` → `Ran 52 tests`, `OK`
- Git 커밋은 없는 로컬 작업이다. hash는 검증한 파일 내용을 식별하며 커밋을 뜻하지 않는다.

- `httpx`: `0.28.1`
- `pydantic`: `2.13.2`
- `fastapi`: `0.142.1`
- `uvicorn`: `0.54.0`
- `setuptools`: `82.0.1`

## 평가 원시 자료

[개발용 20개 전체 결과](validation/development-smoke.json)에는 입력·독립 기대값·상태별 분모·오류 목록·전체 실행을 보존했다. 정상 완료 7, 부분 완료 4, 실행 실패 1, 확인 질문 3, 지원 불가 2, 근거 부족 3개이며 각각 기대 상태로 판정됐다. 실패 상태가 기대값과 일치해도 업무를 완료한 성공으로 세는 것은 아니다.

이 자료는 구현 중 사용한 개발셋이다. 실제 모델 품질·일반적인 업무 완료율·인용의 의미적 적합성·합격 가능성을 측정하지 않았다. 수치 기대값을 잘못된 값으로 바꾸면 평가기가 실패하는지도 테스트했다.

## 실제 연결과 재현

- [Binance live baseline](validation/live-baseline.json) / [재현](validation/live-baseline-replay.json): 실제 공개 API의 BTC 완료 일봉 7개. 상태 `completed`, 재현 동일 `True`.
- [실제 Ollama 계획 + 합성 시세](validation/ollama-demo.json) / [재현](validation/ollama-demo-replay.json): 실제 `qwen3:8b` 계획 요청. 상태 `completed`, 재현 동일 `True`. 시장 자료는 합성이며 모델이 수익률을 계산한 것이 아니다.
- [429 합성 장애](validation/rate-limit-demo.json) / [재현](validation/rate-limit-demo-replay.json): BTC 성공, ETH 429, BNB 조회 중단. 상태 `partial`, 실제 네트워크 시도 0. 재현 동일 `True`.

모든 재현 기록의 `network_attempts`는 0이다. `http_calls`와 `llm_calls`는 기록 소비를 포함한 논리적 요청 수이고, 실제 모델 요청은 `live_llm_calls`로 구분한다. 재현에서 원 모델의 토큰·시간 값이 남는 것은 원 응답을 고정했기 때문이며 새 추론 비용이 아니다.

연결 확인은 소수 사례의 동작 확인이다. 지연 우수성·모델 신뢰성·모든 지역의 API 접근을 입증하지 않는다. 재현 동일 판정은 시장 자료의 새 수집 시각만 제외한다.

## 실행·화면·설치

CLI에서 정상/부분 실행, 기록 재현, 전체 실패의 종료 코드 1, 잘못된 입력의 종료 코드 2를 확인했다. FastAPI의 실제 라우트를 ASGI transport로 검사했다.

브라우저에서는 정상 3종목 비교, ETH 타임아웃 부분 결과, 동일 장애 재현, 실행 내역, 20개 평가, 429 이후 남은 조회 중단을 확인했다. [평가 화면](screenshots/evaluation.jpg)과 [부분 결과](screenshots/partial-result.jpg)를 보존했다. 화면 크기별 전체 호환성 검사는 수행하지 않았다.

wheel을 빌드하고 별도 임시 설치 경로에서 CLI 조사·평가를 실행했다. 코퍼스와 HTML/CSS/JS 파일의 패키지 포함을 확인했다. 이미 설치된 의존성을 사용한 검사이며, 빈 컴퓨터에서 모든 의존성을 새로 내려받는 설치 검사는 아니다.

공개 배포, 다중 사용자 인증, 부하·동시성, 동결 평가, 모델과 고정 흐름의 효과 비교, 실제 사용자 수요, 과거 장애의 수정 전후 비교는 미검증이다. 현재는 실행 가능한 로컬 첫 버전이다.

웹 조사 연결의 합성 응답 검증과 실제 호출 미검증 범위는 [웹 조사 기록](web-research.md)에 있다.
