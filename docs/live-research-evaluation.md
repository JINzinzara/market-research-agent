# 실제 조사 답변 평가 기준

**일반 실행과 `evaluate`는 live 연구를 사용한다. 합성 시세는 회귀 검사 `regression`에만 남긴다.** 현재 실제 Astra 점수는 없다. API 키가 없으며, 테스트 90개 통과를 모델 정확도로 바꾸어 쓰지 않는다.

## 왜 이 평가셋인가

공개 후보를 먼저 확인했다. [FinanceBench](https://github.com/patronus-ai/financebench)는 재무 공시 기반 금융 문답, [FRAMES](https://huggingface.co/datasets/google/frames-benchmark)는 오픈 도메인 검색·추론, [FreshQA](https://github.com/freshllms/freshqa)는 변하는 사실과 잘못된 전제를 다룬다. 이들은 유용하지만 이번 앱의 금리 단위·통계 기준월·최초 발표치·사건 시점·시장 인과 유보와 한·영 질문 대응을 그대로 평가하는 세트는 아니다.

따라서 [pilot 데이터](../src/market_agent/data/research_benchmark.json)를 별도로 만들었다. 정답이 고정된 과거 사건을 먼저 써서 검색일마다 바뀌는 정답 문제를 피하고, 실제 외부 문서를 찾는 실행과 의미 평가를 분리한다. AI 보조로 작성하고 아래 원문을 확인했다. 독립된 사람의 gold 검토는 아직 받지 않았다. **공인 외부 벤치마크나 비공개 테스트셋이 아니라 개발용 파일럿**이다.

## 선정과 단위

6개 사건에 각각 한국어·영어 질문을 만들어 12개다. 한·영 쌍은 같은 사건을 공유하므로 독립된 12개 사건으로 주장하지 않는다.

- 2024-09-18 FOMC: 목표 범위 4.75–5.00%, 인하 0.50%p = 50bp. [원문](https://www.federalreserve.gov/newsevents/pressreleases/monetary20240918a.htm)
- 2024년 6월 CPI, 7월 11일 발표: 전월 대비 -0.1% 계절조정, 전년 대비 +3.0% 비계절조정. [원문](https://www.bls.gov/news.release/archives/cpi_07112024.htm)
- 2024년 6월 고용, 7월 5일 최초 발표: 비농업 고용 +206,000명, 실업률 4.1%. 이후 수정치로 대체하지 않는다. [원문](https://www.bls.gov/news.release/archives/empsit_07052024.htm)
- 2024년 2분기 GDP 속보치: 실질 연율 2.8%. 분기 단순 변화율이나 후속 수정치와 구분한다. [원문](https://www.bea.gov/news/2024/gross-domestic-product-second-quarter-2024-advance-estimate)
- 2024년 1월 SEC 비트코인 ETP: 1월 9일 무단 게시와 1월 10일 실제 상장·거래 승인을 구분하고, 비트코인 자체의 보증으로 오해하지 않는다. [계정 사건](https://www.sec.gov/newsroom/speeches-statements/gensler-x-account), [승인 성명](https://www.sec.gov/newsroom/speeches-statements/gensler-statement-spot-bitcoin-011023)
- 2024-05-01 FOMC: 5.25–5.50% 동결. 이 발표 하나로 비트코인 가격 방향·크기·원인을 입증할 수 있는지 유보한다. [원문](https://www.federalreserve.gov/newsevents/pressreleases/monetary20240501a.htm)

원문 확인일은 2026-10-16이다. 과거 발표의 당시 수치를 묻는 것이며 현재 수치라고 제시하지 않는다. 발표문은 현재 다시 검색한다. 역사적 `as_of` 상황의 정보 접근을 재현한 실험은 아니다. gold 정답·URL·채점 기준은 모델 입력에 넣지 않고 질문만 보낸다.

## 자동으로 측정하는 것

- 실행 완료 수/시도 수. 오류와 미시도도 구분한다. 실행 완료는 정답이 아니다.
- 질문별 기준 URL 중 검색 제공자가 조회했다고 보고한 수와 실제 인용한 수. fragment와 `utm_*`만 제거해 호스트·경로·나머지 질의를 비교한다. 다른 유효한 출처를 놓칠 수 있다.
- 기준 URL은 가능한 모든 관련 문서의 완전한 목록이 아니다. 따라서 이 수치를 일반적인 검색 Recall@k나 의미적 인용 적합성으로 부르지 않는다. 전체 분모는 질문별 기준 URL 발생 수이며 언어 쌍에서 같은 URL이 다시 센다.
- 전체 경과 시간, 실패 포함 실행 지연, 실제 모델 요청, 입력·출력 토큰과 누락 수. HTTP 1회와 내부 hosted search/read 횟수를 구분한다.
- 웹 도구 이용료를 포함한 총 API 비용은 아직 미측정이다. 텍스트 토큰 추정과 총 비용 `null`을 구분한다.

각 실제 실행은 저장하고 질문마다 JSON/Markdown을 갱신한다. 401·403·404·429가 나오면 남은 배치를 중단한다. 완료하지 않은 사례를 성공으로 세지 않는다. 기본 반복은 1회다. `--repeats 3`은 변동성을 보기 위한 초기 운영 선택이며 통계적 충분성을 보장하지 않는다. 반복 한도 5는 비용 관리를 위한 앱 제한이다.

## 의미 평가 — 왜 자동 정답률을 붙이지 않았나

현재 앱이 가진 문서 본문은 웹 검색 제공자의 인용 메타데이터다. URL이 있다는 사실만으로 기사 내용을 검증할 수 없고, 정답 숫자의 문자열 출현도 부정·잘못된 단위·다른 발표치를 구분하지 못한다. 답변을 만든 같은 모델의 자기 채점을 독립 검증으로 취급하지도 않는다.

그래서 1차 의미 평가는 사람이 원문과 답변을 대조해 기록하도록 만들었다. 이 단계는 수동이며 자동 LLM judge는 구현하지 않았다. 회귀 검사에서 regex/JSON Schema/unittest를 사용하는 것과 실제 답변 의미를 채점하는 것은 다른 일이다.

`.reviews.json`의 각 실행에 다음 네 가지를 `true` 또는 `false`로 채운다. 아직 판단하지 않은 것은 `null`을 유지한다.

- `answer_correct`: 해당 질문의 필수 요구를 모두 맞췄는가. 숫자·방향·단위·범위·원인 유보를 포함하며 중대한 모순이 있으면 false다.
- `citations_support_answer`: 중요한 사실 주장을 실제 인용 문서가 지지하는가. 제목/URL만 확인해서 true로 두지 않는다. 인용이 빠졌거나 무관한 자료에 기댄 주장이 있으면 false다. 문장별 claim precision은 별도 미구현이다.
- `temporal_correct`: 발표일·사건일·통계 기준 기간·발표 차수/수정치를 혼동하지 않았는가.
- `language_match`: 질문의 언어 또는 명시한 출력 언어를 따랐는가. 고유명사·수치·인용문은 허용한다.

`reviewer`와 원문 위치·오류 이유 등을 적은 `notes`가 없으면 점수를 반영하지 못한다. 보고서 SHA-256과 실행 ID를 확인해 다른 실행의 라벨이 섞이는 것을 막는다. 네 지표마다 검토 분모와 전체 분모를 표시하고, 선택한 전체 질문이 실행·검토되기 전에는 전체 정답률을 `null`로 둔다. 일부만 골라 검토한 정확도를 전체 성능으로 주장하면 안 된다.

```sh
PYTHONPATH=src .venv/bin/python -m market_agent evaluate --limit 12 --output .market-agent/pilot.json
# companion Markdown에서 답변·정답·필수 요구·실제 인용을 읽고 .reviews.json을 검토한다.
PYTHONPATH=src .venv/bin/python -m market_agent score .market-agent/pilot.json .market-agent/pilot.reviews.json --output .market-agent/pilot-scored.json
```

검토를 시작한 파일에 같은 출력 이름으로 새 평가를 덮어쓰지 못하게 했다. 다른 이름을 사용한다. 원문 일부가 사라지거나 접근되지 않으면 지지 여부를 추측하지 말고 미검토로 남긴다.

## 보고서에 쓸 수 있는 범위

실제 실행·검토 후에만 실행 N/M, 기준 URL 확보 A/B, 답변 정답 C/D(검토 D/전체 M), 인용 지지·시점·언어 통과 수와 지연·토큰을 보고한다. 지금은 평가 도구와 기준을 구현했다는 사실만 쓸 수 있다.

최신 속보, 기사 전문 수집, 동결하지 않은 시장 질문의 최신성, 검색엔진/모델 간 공정 비교, 독립적인 gold 검토와 평가자 간 일치도는 남았다. 다음 독립 비교에는 외부 세트를 수정 없이 고정된 버전으로 적용하고 출처·선정 방법·평가 방식을 별도로 기록해야 한다. 이 파일럿을 보며 프롬프트를 조정한 뒤 비공개 검증이라고 이름 붙이지 않는다.
