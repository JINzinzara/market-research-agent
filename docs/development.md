# 개발 방식과 출처

**이번에는 사용자의 명시적 요청에 따라 실행 가능한 첫 버전까지 AI가 구현했다.** 기존의 ‘코드 본문은 사용자가 직접 작성’ 방식은 이번 구현에 적용하지 않는다. 이후 학습 단계에서는 파일별로 설명·수정하며 이해를 검증한다.

## 보존과 변경

기존 로컬 `llm.py`와 그 테스트를 유지했다. 스키마·스키마 테스트는 기존 저장소 [기준 커밋](https://github.com/JINzinzara/market-research-agent/tree/1d3be3d1d6204ae2c669c146347094fa5a840901)에서 반영했고 `partial` 상태와 인용 검증을 확장했다.

새 도구·런타임·저장/재현·평가·API·웹 콘솔·관련 테스트는 이번 AI 보조 구현이다. 기존 원격 main 이력을 연결해 보존하고, 새 변경은 파일별 커밋으로 기록한다. 실행 기록의 버전은 현재 파일 내용 hash이며 Git revision 조회는 아직 구현하지 않아 source_revision은 null로 남는다.

BM25는 기존 `minimal_rag.py` 학습 코드의 토큰화·통계·점수식을 참고해 이 패키지에 맞게 작성했다. 빈 자료·0점 문서·출처 매핑·동점 순서를 처리한다. 개인 학습 파일을 런타임에서 import하지 않는다. LangGraph나 외부 연구 프레임워크의 구현을 복사하지 않았다.

## 공식 API와 라이브러리 참고

2026-10-16 KST 확인:

- [Binance 공식 REST 명세](https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md#klinecandlestick-data): 일봉·UTC·timestamp·필드 구조. 코퍼스의 세 요약은 이 문서의 해당 절을 검토한 의역이다. `retrieved_at`은 이번 검토 기록 시각이며 발행 시각이 아니다.
- [HTTPX MockTransport](https://www.python-httpx.org/advanced/transports/#mock-transports): 고정 응답과 재현 transport의 기반.
- [Pydantic JSON 검증](https://docs.pydantic.dev/latest/concepts/json/), [strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/): 모델 응답은 `model_validate_json()`, 내부 객체는 `model_validate()`로 검증한다.
- [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/), [FileResponse](https://fastapi.tiangolo.com/advanced/custom-response/): API 통합 검사와 로컬 정적 콘솔. 최신 사용법은 Context7의 공식 문서로 확인했다.

설정의 출처와 가정은 [구현 구조](implementation-plan.md)에 기록했다. 특정 논문이 이 제품의 한도·정밀도·timeout을 최적값으로 검증했다고 주장하지 않는다.

## 본인이 직접 확인할 순서

1. 기본 조사와 ETH 타임아웃을 실행하고, 왜 각각 `completed`·`partial`인지 설명한다.
2. `market_window()`에서 한국 시각을 UTC로 바꾸는 순서와 `endTime - 1ms`를 설명한다.
3. 원 실행과 재현의 수치·오류가 같고 수집 시각은 다른 이유를 설명한다.
4. 합성 입력의 종가를 바꾸고 독립 평가 기대값이 왜 실패하는지 확인한다.
5. 모델 계획을 끄거나 실패시켜도 어떤 기능이 동작하는지 설명한다. 모델을 사용했다는 사실과 유용성을 구분한다.

AI 도움을 받은 범위와 직접 수정·검증한 범위를 README·면접에서 사실대로 말한다. 현재 코드가 있다는 이유로 본인이 전부 설계·작성했다고 쓰지 않는다.
