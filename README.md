# market-research-agent

## 개발 환경

Python 3.13과 프로젝트 전용 `.venv`를 사용합니다. 의존성과 `src/market_agent` 패키지 설정은 `pyproject.toml`에서 관리합니다.

프로젝트 루트에서 최초 한 번 실행합니다.

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

이후 새 터미널에서는 가상환경을 활성화하고 테스트합니다.

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

편집기의 Python 인터프리터도 이 프로젝트의 `.venv/bin/python`으로 선택합니다. 가상환경 폴더는 Git에 올리지 않고, 다른 컴퓨터에서는 위 절차로 다시 만듭니다.
