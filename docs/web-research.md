# 뉴스·기사·거시경제 웹 조사

**현재 기본값은 live + OpenAI + 웹 조사다. 기존 가격·고정 문서 경로는 `--no-web`으로 명시한다.** 실제 OpenAI 검색 호출은 키가 없어 아직 확인하지 않았다. 연결·오류 처리·인용·재현은 합성 제공자 응답으로 검사했다.

## 실행

의존성을 설치한 저장소 루트의 macOS zsh 터미널에서:

```zsh
read -rs "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY

PYTHONPATH=src .venv/bin/python -m market_agent research '비트코인 최근 7일 관련 뉴스와 미국 금리·물가 발표를 조사해줘' --mode live --planner openai --web
```

가격이 필요 없는 질문도 가능하다:

```sh
PYTHONPATH=src .venv/bin/python -m market_agent research '최근 Fed 금리 결정과 BLS 물가 발표를 공식 자료로 조사해줘' --mode live --planner openai --web
```

웹 콘솔은 키를 설정한 같은 터미널에서 다시 시작한다. `News & macro` 또는 `Official macro releases`를 선택하면 웹 조사, live, OpenAI가 함께 선택된다. `--no-web`이면 기존 가격·고정 문서 흐름이다. Qwen에 자체 웹 검색 도구를 연결한 것은 아니다.

## 실제로 수행하는 일

- OpenAI Responses의 `web_search`를 필수로 호출하고 실시간 웹 접근을 허용한다. 별도 검색 서비스 키나 SDK는 추가하지 않았다.
- 프롬프트는 질문의 언어 또는 명시한 출력 언어에 맞춰 답하고, 질문 관련 기사와 Fed·BLS·BEA 등의 공식 발표를 우선하고, 보도된 사실·거시 배경·해석·반대 근거·미확인 사항을 나눠 쓰도록 요청한다. 발행일·사건일·통계 기준 기간도 가능한 경우 구분한다. 이는 요청 지침이며 충족을 자동 검증한 결과가 아니다.
- 지원 종목과 완료된 UTC 1일/7일 조건을 기존 파서가 인식하면 Binance 수치를 함께 조회한다. 뉴스만 묻거나 가격 기간을 인식하지 못하면 웹 조사만 수행한다. 가격 수치는 Python이 계산한다.
- 완료된 검색 실행과 제공자의 `url_citation` 주석을 검사한다. 인용 URL·제목·본문 위치를 검증하고 URL 중복을 제거한다. 생성된 글 안에 URL을 적었다는 이유만으로 출처로 인정하지 않는다.
- 보고서 안의 `[web-N]`과 출처 목록을 클릭할 수 있다. 제공자가 반환한 전체 조회 URL 목록과 검색·페이지 열기 이력은 원시 응답에도 남긴다.
- 키가 없으면 네트워크 호출 전에 실패한다. 검색 실패·미완료 응답·인용 누락은 웹 조사 성공으로 처리하지 않는다. 가격만 성공했다면 그 근거를 보존한 `partial` 결과를 만든다.

`completed`는 검색 실행과 인용 형식 검사를 통과했다는 뜻이다. 질문 전체의 정답·기사의 진위·모든 문장의 인용 적합성을 보증하지 않는다. 원인을 묻는 질문은 인용 기사가 있어도 `insufficient_evidence`로 두고 인과관계의 한계를 표시한다.

## 호출 예산과 관측 값

한 번의 앱 웹 조사에서 Responses 요청은 1회다. 그 내부의 검색·페이지 열기·본문 찾기는 제공자 실행이므로 앱의 HTTP 요청 수와 다르다. 기본 제공 도구의 합산 한도 `max_tool_calls=3`, 최대 출력 4,096토큰, reasoning low를 초기 운영 가정으로 사용한다. 이 수치가 최적이라는 실험 근거는 없다. 기존 모델 HTTP 타임아웃 300초도 그대로 사용하며 전체 작업 시간 한도를 뜻하지 않는다.

`web_tool_calls`는 응답에 관측된 hosted tool 항목 수, `web_search_calls`는 그중 search 행동 수, `citation_count`는 검증 후 고유 인용 URL 수다. URL 수는 주장을 맞힌 수가 아니다. 지연과 입력·출력 토큰도 기존 실행 기록에 남는다. 총 비용은 웹 검색 도구 이용료를 아직 추정하지 않아 `null`이다. 텍스트 토큰 비용 추정은 `estimated_text_api_cost_usd`에 따로 둔다.

재현에서는 이 호출 기록도 고정한다. 웹 도구 수치는 원래 응답에 관측된 횟수이며 새 검색을 했다는 뜻이 아니다. 재현의 `live_llm_calls=0`, `network_attempts=0`을 함께 확인한다. 저장된 검색 보고서가 재현됐다는 사실은 지금도 기사가 존재하거나 최신이라는 증거가 아니다.

공식 근거는 [OpenAI 웹 검색 문서](https://developers.openai.com/api/docs/guides/tools-web-search)의 필수 도구 선택·인용·전체 sources와 [Responses API](https://developers.openai.com/api/reference/python/resources/responses/methods/create)의 `max_tool_calls`·`max_output_tokens` 정의다. 2026-10-16 확인. 한도는 모든 기본 제공 도구 호출의 합계이며 검색어 수·문서 수를 뜻하지 않는다.

## 검증과 아직 없는 것

현재 전체 단위·통합 테스트 90개가 통과했다. 합성 응답으로 뉴스만 조사, 가격+웹 조사, 인용 검증·중복 제거, 위험 URL 거부, 실패 시 가격 보존, 미완료 토큰 보존, 키 비기록, API 저장과 연속 재현을 검사했다. 기존 baseline 개발 사례도 20/20 통과했다.

**이 테스트 수를 뉴스 검색 정확도나 사실 정확도로 쓰면 안 된다.** 실제 검색 성공률·질의별 관련 문서 Recall@k·인용 주장의 지지율·최신성·뉴스/공식 자료 충족률은 아직 측정하지 않았다.

앱은 기사 전문을 직접 크롤링하지 않는다. `Source.content`는 제공자 인용 메타데이터임을 표시하고 원문 발췌인 것처럼 저장하지 않는다. 전문 확보·교차 출처 검증·정확한 발행일 필터·FRED 등 거시 시계열 전용 API·Qwen과 Astra가 공유하는 독립 검색 계층·자체 동적 조사 루프는 아직 없다. Perplexity와 동등한 조사 품질을 입증한 구현은 아니다.

## 출력 4,096토큰의 의미

Astra의 최대 출력량은 4,096 또는 4,069가 아니라 **128,000토큰**이다. [공식 모델 규격](https://developers.openai.com/api/docs/models/gpt-6-astra), [Responses 출력 한도 정의](https://developers.openai.com/api/reference/python/resources/responses/methods/create)를 2026-10-16 확인했다. `max_output_tokens`는 보이는 답변만이 아니라 추론 등 비가시 생성 토큰까지 포함한다.

4,096은 제가 초기 응답 길이와 비용을 제한하려고 선택한 앱 예산이다. 현재 과제의 충분성·최적값은 측정하지 않았다. 기사 문서 길이나 검색 입력 문맥의 최대 크기를 뜻하지도 않는다. 미완료 응답은 성공 처리하지 않고 usage와 원 응답의 incomplete_details를 남긴다. 값을 바꾸기 전 같은 질문·출처 기준에서 잘림 비율, 의미 평가, 지연·토큰 비용을 함께 비교해야 한다.

이제 실제 평가 실행기는 [live 평가 기준](live-research-evaluation.md)을 사용한다. 위의 합성 응답 검사는 연결 검증이며 실제 웹 검색 품질 점수가 아니다.
