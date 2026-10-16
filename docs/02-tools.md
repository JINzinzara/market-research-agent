# 재사용 검색 라이브러리와 오케스트레이션

**직접 만든 BM25 점수식과 정규식 토큰화를 제거했다.** 보존된 로컬 문서 검색은 NLTK `wordpunct_tokenize`와 `rank_bm25.BM25Okapi`를 사용한다. live 뉴스 검색은 별도 OpenAI hosted web search이며, 이 로컬 BM25를 거치지 않는다.

## LangChain을 통째로 넣지 않은 이유

공식 [BM25Retriever 코드](https://github.com/langchain-ai/langchain-community/blob/main/libs/community/langchain_community/retrievers/bm25.py)는 `rank_bm25`를 감싼다. 기본 전처리도 `text.split()`이다. 따라서 LangChain을 가져오는 것만으로 한국어 형태소 처리나 검색 정확도가 자동으로 개선되지 않는다. 2026-10-16 확인 당시 이 공식 community 저장소는 2026-06-19 보관 상태였다.

이번 목적은 알고리즘 재구현을 없애는 것이므로 원 라이브러리를 직접 사용했다. 범용 LangChain 인터페이스·다중 검색기 합성·모델 교체 같은 요구가 생기면 그 인터페이스의 이득을 따로 평가한다. NLTK 단어/구두점 분리는 한국어 형태소 분석이 아니며 품질 개선을 측정한 결과도 없다.

검색 횟수 증가와 프레임워크 효율 향상은 같은 말이 아니다. 현재 검색·페이지 열기 결정은 OpenAI 제공자 내부에서 이루어진다. 바깥에 LangGraph를 추가해도 이 내부 네트워크 지연이 줄거나 검색 횟수가 자동 늘어나지 않는다. 앱 자체의 조건부 재검색, 충분한 근거 판단, 중간 재개, 긴 실행 상태 관리가 필요해질 때 LangGraph를 쓰는 편이 설계·유지보수 측면에서 유리할 수 있다. 속도·비용 우위는 별도 실험이 필요하다. 상태 지속과 재개 기능은 [LangGraph 공식 문서](https://docs.langchain.com/oss/python/langgraph/interrupts)를 참고했다.

## 로컬 문서 경계

`build_bm25()`는 검증한 Source 목록으로 라이브러리 인덱스를 만든다. `search_documents()`는 점수 순서로 반환하되 질의와 토큰이 전혀 겹치지 않는 문서를 제외한다. 라이브러리는 비매칭 문서도 top-k로 반환할 수 있기 때문이다. 작은 코퍼스에서는 유효한 일치 점수도 0 또는 음수일 수 있어 점수 > 0을 정답 조건으로 쓰지 않는다.

소문자 정규화와 구두점 제외만 앱에서 수행한다. `k1=1.5`, `b=.75`는 기존 초기 가정을 유지했으며 최적값을 검증한 것은 아니다. 라이브러리의 IDF 정의가 이전 직접 구현과 다르므로 점수 숫자를 이전 값과 직접 비교하지 않는다. 새 벤치마크의 답변 정확도를 BM25 점수로 표현하지 않는다.

## 가격 도구

[tools.py](../src/market_agent/tools.py)는 계속 Binance 일봉의 수·순서·중복·누락·완료 시각·원 가격 문자열·OHLC 범위를 검사한다. `calculate_return()`은 40자리 Decimal로 계산하고 표시 반올림은 분리한다. 잘못된 자료를 기본 시세로 대체하지 않는다. 해당 경계와 실패 시 다른 종목 보존은 테스트로 유지했다.

현재 검증 환경: NLTK 3.10.3, rank-bm25 0.2.2, Python 3.13. 실제 연구 품질 평가와 검증 한계는 [live 평가 기준](live-research-evaluation.md)에 있다.
