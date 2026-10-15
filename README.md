# market-research-agent

## 개발 환경

Python 3.13과 프로젝트 전용 `.venv`를 사용합니다. 의존성과 패키지 설정은 `pyproject.toml`에서 관리합니다.

프로젝트 루트에서 최초 한 번 실행합니다.

```bash
python3.13 -m venv .venv
.venv/bin/python -m pip install .
```

이미 `pip install -e .`로 설치했다면 일반 설치로 바꿉니다.

```bash
.venv/bin/python -m pip install --force-reinstall --no-deps .
```

일반 설치는 `.venv` 안에 패키지를 설치하므로 editable 설치의 `.pth` 경로 등록에 의존하지 않습니다. Python 3.13은 macOS 숨김 속성이 붙은 `.pth` 파일을 무시합니다. 이 경우 설치 기록이 있어도 `src/market_agent`를 찾지 못할 수 있습니다.

## 테스트

다음 명령은 가상환경 활성화나 `PYTHONPATH` 설정 없이 실행합니다.

```bash
.venv/bin/python tests/test_llm.py
```

unittest discovery도 지원합니다.

```bash
.venv/bin/python -m unittest discover -s tests -v
```

테스트는 자신의 파일 위치를 기준으로 현재 저장소의 `src`를 등록합니다. 따라서 실행한 디렉터리나 editable 설치의 `.pth` 상태와 관계없이 **지금 수정 중인 코드**를 검사합니다. 설치된 과거 복사본을 검사하지 않는지도 회귀 테스트로 확인합니다.

편집기의 Python 인터프리터는 이 프로젝트의 `.venv/bin/python`으로 선택합니다. 시스템 `python` 또는 `python3`은 별도의 환경일 수 있습니다.

## 코드 수정 후

테스트는 현재 소스를 직접 읽으므로 재설치 없이 실행할 수 있습니다. 테스트 이외의 프로그램에서 일반 설치된 패키지를 사용할 때는 소스 변경 후 다시 설치합니다.

```bash
.venv/bin/python -m pip install --force-reinstall --no-deps .
```

의존성을 추가하거나 변경했다면 `--no-deps`를 생략합니다. `.venv`는 Git에 올리지 않고 다른 컴퓨터에서는 위 개발 환경 절차로 다시 만듭니다.
