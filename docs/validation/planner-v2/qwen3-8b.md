# 개발용 평가 결과

실행 시각: 2026-10-16T02:14:36.192146+00:00

**시나리오 통과: 20/20 (100.0%)**

실행 모드: synthetic demo / ollama planner. 고정 합성 자료의 애플리케이션 계약 검사이며 일반적인 LLM 정확도가 아니다.

## 검사 항목별 결과

- `status`: 20/20
- `market_evidence_set`: 20/20
- `numerical_return`: 15/15
- `http_call_count`: 20/20
- `execution_budget`: 20/20
- `planner_output_valid`: 15/15
- `planner_matches_request`: 15/15
- `citation_reference_integrity`: 20/20
- `consistent_market_window`: 12/12
- `expected_failure_preserved`: 5/5
- `required_document_present`: 1/1

숫자 검사는 기대 종목별 변화율을 센다. 인용 ID 검사는 문장의 의미적 근거 적합성을 판정하지 않는다.

## 시간·사용량

- 평가 루프 전체 경과: 9239.55 ms
- 실패 포함 실행 지연 합계: 9233.143 ms · 평균: 461.657 ms · 중앙값: 585.387 ms
- 실행 지연 범위: 6.597–759.537 ms
- 논리적 HTTP 요청: 37 · 실제 네트워크 시도: 15
- 실제 모델 요청: 15
- 입력 토큰: 3542 · 출력 토큰: 451
- 외부 LLM API 비용 추정: 0 USD. 청구 금액이 아니며 장비·전력·운영 비용은 미측정.

## 상태별 시나리오

- 기대 상태 `completed`: 7/7
- 기대 상태 `partial`: 4/4
- 기대 상태 `error`: 1/1
- 기대 상태 `needs_clarification`: 3/3
- 기대 상태 `unsupported`: 2/2
- 기대 상태 `insufficient_evidence`: 3/3

## 보고서에 쓸 수 있는 범위

고정 합성 데이터의 정상·부분 장애·거절·근거 부족 시나리오 20개를 개발용으로 검증해 20개가 기대 결과를 충족했다. 수치 계산과 오류 보존을 독립 기대값으로 확인했다.

구현 중 사용한 개발셋이며 동결 평가·근거의 의미적 적합성은 미측정이다. 모델 호출 수가 0이면 모델 품질 검사도 아니다. 호출이 있더라도 정규식 사전 검사를 통과한 연구 요청의 제한된 계획 추출만 측정한다. 지연은 도구 실행을 포함한 애플리케이션 경과 시간이며 개별 API/LLM 응답 시간과 구분한다.

코드/자료 SHA-256: `c944516698839cbac69c71f2586f5b75e07e32821d6b1931390006eb0fa0489a`
