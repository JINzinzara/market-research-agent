# 실행 기록·재현·평가

**HTTP 응답과 오류를 고정해 현재 조사 코드를 다시 실행한다.** 기록 조회와 재현은 별도 기능이다. 20개 개발 사례는 구현돼 있으며 실제 모델 품질 평가가 아니다.

## 기록

실행별 JSON의 `format_version=1`이다. 입력·실행 모드·기준 시각·결과·도구 이벤트·HTTP 요청/응답·오류·문서 스냅샷·사용량·소요 시간을 저장한다. 기본 경로는 `.market-agent/runs/`이며 임시 파일에 완전히 기록하고 `os.replace()`로 교체한다.

코드와 패키지 자료의 SHA-256을 저장한다. Git 커밋을 확인하지 않았으므로 `source_revision=null`이고 가짜 커밋을 채우지 않는다. 모델 이름·프롬프트 버전·실행 설정을 남기지만 모델 가중치 digest는 수집하지 않는다.

사용량은 모델 HTTP 시도별로 기록한다. Ollama의 `prompt_eval_count`, `eval_count`, `total_duration`과 정규화한 `input_tokens`, `output_tokens`를 보존한다. OpenAI는 Responses usage의 입력·출력·캐시·추론 토큰을 기록한다. 응답이 없거나 빠진 값은 `null`이며 실패 호출도 분모에 포함한다. Ollama의 `total_duration`은 ns, 도구·HTTP·전체 실행의 `duration_ms`는 ms다. `http_calls`·`llm_calls`는 재현 transport 호출까지 포함한 논리적 요청 수다. `network_attempts`는 실제 네트워크 시도, `live_llm_calls`는 실제 모델 요청, `replayed_http_calls`는 기록 소비 수다. 따라서 모델 응답을 재현해도 실제 모델 호출 수는 0이다. 도구 실행·모델 호출·HTTP 요청·수집 라운드를 구분한다.

`think=False`를 유지하고 저장 전에 Ollama `message.thinking`을 제외한다. 인증 헤더·비밀키는 저장하지 않는다. 로컬 실행 기록에는 질문과 관측 가능한 응답이 포함되므로 공개할 사례를 직접 골라야 한다.

## 재현

- **Inspect:** 저장된 과거 결과를 표시한다. 코드 실행이 아니다.
- **Replay:** 원 질문·고정 시각·문서 스냅샷·HTTP 응답/오류로 현재 `run_research()`를 실행한다.
- 메서드·전체 URL·본문·순서가 다르거나 기록이 부족/남으면 `ReplayMismatch`로 실패한다. API는 409를 반환한다. 라이브 fallback은 없다.
- 재현에서는 모델 응답도 고정된다. 별도 `evaluate --planner ollama|openai`는 같은 합성 시장 자료에 실제 모델을 호출한다. 두 실험을 혼동하지 않는다.
- `same_result`는 시장 자료의 새 `retrieved_at`만 제외한 결과 객체를 비교한다. 참조 본문·수치·답변·상태·인용을 포함한다. 실행 지연·trace의 동일성을 뜻하지 않는다.

합성 장애를 재현하는 것은 오류 처리 검사다. 실제 운영 사고를 발견해 수정했다는 증거는 아니다.

## 개발용 20개

입력과 기대값은 [smoke_cases.json](../src/market_agent/data/smoke_cases.json)에 있다. 원 자료는 `fixtures.py`의 명시적 합성 시가·종가다. 평가기는 생산 계산 함수를 호출해 정답을 만들지 않고 별도 작성한 유리수 기대값과 비교한다. Decimal의 유한 정밀도 때문에 허용 절대 오차 `10^-35`를 사용한다. 이 허용치는 이번 산술 계약의 검사 가정이지 실측한 금융 오차 기준이 아니다.

검사 항목은 상태·확인된 종목 집합·수익률·HTTP 수·수집 한도·인용 존재·구간 일치·기대 오류 보존이다. 정상 조회, 일봉 1개, 부분 타임아웃·누락·잘못된 가격·429, 전체 실패, 모호한 입력, 지원 불가, 근거 부족을 포함한다. 문서만 제시한 결과를 성공으로 세지 않는다.

평가 JSON은 사례별 입력·기대값·오류 목록·전체 실행 기록과 상태별 분모를 포함한다. 평가셋을 보며 구현했으므로 개발셋이다. 링크 존재 검사는 의미적 근거 적합성 점수가 아니며, 실모델·실시장 품질은 이 평가에 들어 있지 않다.

```sh
PYTHONPATH=src python3 -m market_agent evaluate --output .market-agent/evaluation.json
```

## 남은 비교

[τ-bench](https://arxiv.org/abs/2406.12045)의 업무 결과·정책 준수·반복 신뢰성 관점을 참고하되 논문의 점수·도메인·실행 수를 이 제품의 근거로 옮기지 않는다.

실제 실패 수정 전후, 새로 동결한 평가셋, 고정 흐름 대비 모델/도구 선택의 효과가 남았다. 40개 동결 사례·3회 반복은 아직 채택·실행하지 않은 계획이다. 현재 20/20을 일반적인 에이전트 신뢰성이나 채용 가능성으로 해석하지 않는다.

## 항목별 점수와 Markdown 출력

평가 JSON에는 `dimensions`, `summary`, `pass_rate`, `wall_duration_ms`를 추가했다. JSON과 같은 이름의 `.md`를 함께 저장한다. 수치 검사는 기대 종목별로 세며 누락도 실패다. 지연은 실패·거절까지 포함한다. 누락 사용량과 청구 비용을 0으로 만들지 않는다. 최신 범위와 실측은 [모델 비교 기록](metrics-and-model-comparison.md)에 있다.
