# 02 — 구현된 도구 읽기와 수정

**[tools.py](../src/market_agent/tools.py)는 본문까지 구현됐다.** 이전의 빈 함수 작성 과제 대신, 아래 경계를 이해하고 직접 요구 변경을 수행한다.

## 계산과 시간

`calculate_return()`은 양수·유한한 Decimal만 받고 40자리 정밀도로 변화율을 반환한다. 전역 Decimal context를 바꾸지 않는다. 별도 `display_return_pct`는 소수 둘째 자리 HALF_UP이다.

`market_window()`는 timezone-aware `as_of`를 UTC로 바꾼 뒤 자정 경계를 만든다. 한국 시각 08:59는 UTC 전날 23:59이므로 먼저 한국 날짜를 자정으로 만들면 잘못된다. 이 경계는 테스트로 고정했다.

## Binance 일봉 검증

`fetch_market_data()`는 종목 하나와 기간을 받는다. 정확한 완료 일봉 수, 각 행의 12개 필드, 시작·종료 시각, 순서·중복·누락, 원 가격 문자열, 유한·양수 OHLC와 고저 범위를 검사한다. HTTP 오류는 숨기지 않는다.

한 종목의 오류와 다른 종목 결과를 합치는 곳은 `runtime.py`다. 도구 안에서 기본 시세를 만들거나 재시도하지 않는다. `Source.content`에는 원 일봉·구간·계산값·표시값이 들어간다.

## 고정 문서 검색

`load_documents()`는 JSON의 중복 ID와 잘못된 출처 종류를 거부한다. 코퍼스는 [documents.json](../src/market_agent/data/documents.json)의 검토된 API 요약 3개다.

BM25는 제목과 본문에 동일한 `[0-9a-z가-힣]+` 토큰화를 적용한다. 인덱스의 `documents`는 원 `Source` 목록이고, 빈 자료·무일치 결과는 빈 목록이다. 양수 점수만 반환하며 동점은 원 순서다. 형태소 분석·동의어 이해·의미 검색은 하지 않는다.

`k1=1.5`, `b=.75`는 학습 참고 코드의 기본값이며 이 제품의 최적값이 아니다. 호출부는 `top_k=2`를 초기 가정으로 사용한다.

외부 기사·뉴스·거시 자료는 이 BM25 함수가 찾지 않는다. 별도 [web_research.py](../src/market_agent/web_research.py)의 OpenAI hosted web search 경계를 사용하며, 원문 직접 수집과 인용 메타데이터를 구분한다. [실행과 한계](web-research.md)를 함께 읽는다.

## 확인 명령과 연습

```sh
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_tools.py' -v
PYTHONPATH=src python3 -m market_agent research 'BTC ETH 7d' --scenario eth_missing
```

다음에는 잘못된 일봉 순서·시가 0·누락 일봉을 직접 만들어 거부되는 위치를 설명한다. 지원 종목 추가를 연습한다면 스키마·도구·계획 파서·합성 자료·평가·문서를 함께 바꿔야 한다.
