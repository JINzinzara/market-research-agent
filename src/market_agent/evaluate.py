"""Development smoke evaluation with separately authored rational expectations."""

from collections import Counter
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
import json
import os
from pathlib import Path
from statistics import median
from time import perf_counter

from .runtime import PACKAGE, ResearchRequest, code_fingerprint, run_research


def case_checks(case: dict, record: dict) -> list[dict]:
    checks = []

    def add(metric, passed, reason):
        checks.append({"metric": metric, "passed": bool(passed), "failure_reason": reason})

    result, metrics = record["result"], record["metrics"]
    add("status", result["status"] == case["status"],
        f"status: expected {case['status']}, got {result['status']}")
    actual = {json.loads(source["content"])["symbol"]: json.loads(source["content"])
              for source in result["sources"] if source["kind"] == "market"}
    add("market_evidence_set", set(actual) == set(case["returns"]),
        "market evidence set differs from expected symbols")
    for symbol, expected in case["returns"].items():
        # Rational oracle: no call to the production calculator.
        correct = symbol in actual and abs(Fraction(actual[symbol]["return_pct"]) - Fraction(expected)) <= Fraction(1, 10**35)
        add("numerical_return", correct, f"incorrect percentage for {symbol}")
    model_calls = int(record["request"]["planner"] != "baseline" and case["status"] not in {"needs_clarification", "unsupported"})
    add("http_call_count", metrics["http_calls"] == case["http_calls"] + model_calls, "unexpected HTTP request count")
    add("execution_budget", metrics["llm_calls"] == model_calls and metrics["network_attempts"] == model_calls
        and metrics["collection_rounds"] <= 2, "baseline exceeded its execution contract")
    if model_calls:
        validation = record["planner_validation"]
        add("planner_output_valid", validation["output_valid"] is True, "model output failed plan validation")
        add("planner_matches_request", validation["matches_request"] is True, "model plan disagrees with request")
    available = {source["source_id"] for source in result["sources"]}
    add("citation_reference_integrity", set(result["source_ids"]).issubset(available), "unknown citation")
    if case.get("documents_required"):
        add("required_document_present", any(source["kind"] == "document" for source in result["sources"]),
            "expected document reference is missing")
    if case.get("failure_type"):
        add("expected_failure_preserved", case["failure_type"] in {row["type"] for row in record["failures"]},
            "expected failure was not preserved")
    if actual:
        windows = {(row["start_utc"], row["end_utc_exclusive"]) for row in actual.values()}
        add("consistent_market_window", len(windows) == 1, "market windows are inconsistent")
    return checks


def check_case(case: dict, record: dict) -> list[str]:
    return [check["failure_reason"] for check in case_checks(case, record) if not check["passed"]]


def summarize_runs(records: list[dict]) -> dict:
    """Include failed runs; distinguish missing usage and frozen model responses."""
    durations = [record["metrics"]["duration_ms"] for record in records]
    attempts = sum(record["metrics"].get("live_llm_calls", 0) for record in records)
    usage = [row for record in records if record["metrics"].get("live_llm_calls", 0)
             for row in record["metrics"]["usage"]]
    tokens = {}
    for name, field in (("input", "prompt_eval_count"), ("output", "eval_count")):
        generic = "input_tokens" if name == "input" else "output_tokens"
        values = [row.get(generic, row.get(field)) for row in usage
                  if type(row.get(generic, row.get(field))) is int]
        tokens[name] = {
            "total": sum(values) if len(values) == attempts else None,
            "observed_total": sum(values) if values or attempts == 0 else None,
            "observed_calls": len(values), "missing_calls": attempts - len(values),
        }
    costs = [row["estimated_api_cost_usd"] for row in usage
             if row.get("estimated_api_cost_usd") is not None]
    return {
        "runs": len(records),
        "latency_ms": {"sum": round(sum(durations), 3),
                       "mean": round(sum(durations) / len(durations), 3) if durations else None,
                       "median": round(median(durations), 3) if durations else None,
                       "min": min(durations) if durations else None, "max": max(durations) if durations else None},
        "http_calls": sum(record["metrics"]["http_calls"] for record in records),
        "network_attempts": sum(record["metrics"]["network_attempts"] for record in records),
        "live_llm_calls": attempts, "tokens": tokens,
        "estimated_external_llm_api_cost_usd": round(sum(costs), 8) if len(costs) == attempts else None,
        "operating_cost_usd": None,
        "cost_scope": "Local Ollama API fee is zero. GPT-6 Astra uses a dated Standard text estimate; cache-write premiums, other fees, tax and operating cost are unmeasured. Not an invoice.",
    }


async def evaluate(planner: str = "baseline") -> dict:
    if planner not in {"baseline", "ollama", "openai"}:
        raise ValueError("unsupported evaluation planner")
    if planner == "openai" and not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("Set OPENAI_API_KEY in the evaluation process environment first")
    path = PACKAGE / "data/smoke_cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    results = []
    started = perf_counter()
    for case in cases:
        request = ResearchRequest(question=case["question"], scenario=case.get("scenario", "none"),
                                  mode="demo", web=False, planner=planner)
        record = await run_research(request)
        checks = case_checks(case, record)
        errors = [check["failure_reason"] for check in checks if not check["passed"]]
        results.append({"case_id": case["id"], "passed": not errors, "errors": errors,
                        "checks": checks, "expected": case, "run": record})
    wall_duration = round((perf_counter() - started) * 1000, 3)
    groups = {}
    for status, count in Counter(case["status"] for case in cases).items():
        groups[status] = {"total": count, "passed": sum(row["passed"] for row in results
                                                      if row["expected"]["status"] == status)}
    dimensions = {}
    for row in results:
        for check in row["checks"]:
            score = dimensions.setdefault(check["metric"], {"total": 0, "passed": 0})
            score["total"] += 1
            score["passed"] += check["passed"]
    passed = sum(row["passed"] for row in results)
    return {"format_version": 1, "evaluated_at": datetime.now(timezone.utc).isoformat(),
            "suite": "development-smoke-v1", "mode": f"synthetic demo / {planner} planner",
            "code_sha256": code_fingerprint(), "dataset_sha256": sha256(path.read_bytes()).hexdigest(),
            "total": len(results), "passed": passed, "pass_rate": passed / len(results) if results else None,
            "wall_duration_ms": wall_duration, "dimensions": dimensions,
            "summary": summarize_runs([row["run"] for row in results]),
            "by_expected_status": groups, "cases": results,
            "limitations": ["Development cases used during implementation; not a held-out benchmark.",
                            "Only research requests passing the regex scope gate reach the model; other cases do not measure the model.",
                            "No live market accuracy, general model quality, or human grounding score measured."]}


def report_markdown(report: dict) -> str:
    summary = report["summary"]
    latency = summary["latency_ms"]
    lines = ["# 개발용 평가 결과", "", f"실행 시각: {report['evaluated_at']}", "",
             f"**시나리오 통과: {report['passed']}/{report['total']} ({report['pass_rate']:.1%})**",
             "", f"실행 모드: {report['mode']}. 고정 합성 자료의 애플리케이션 계약 검사이며 일반적인 LLM 정확도가 아니다.",
             "", "## 검사 항목별 결과", ""]
    for name, score in report["dimensions"].items():
        lines.append(f"- `{name}`: {score['passed']}/{score['total']}")
    lines.extend(["", "숫자 검사는 기대 종목별 변화율을 센다. 인용 ID 검사는 문장의 의미적 근거 적합성을 판정하지 않는다.",
                  "", "## 시간·사용량", "",
                  f"- 평가 루프 전체 경과: {report['wall_duration_ms']} ms",
                  f"- 실패 포함 실행 지연 합계: {latency['sum']} ms · 평균: {latency['mean']} ms · 중앙값: {latency['median']} ms",
                  f"- 실행 지연 범위: {latency['min']}–{latency['max']} ms",
                  f"- 논리적 HTTP 요청: {summary['http_calls']} · 실제 네트워크 시도: {summary['network_attempts']}",
                  f"- 실제 모델 요청: {summary['live_llm_calls']}",
                  f"- 입력 토큰: {summary['tokens']['input']['total']} · 출력 토큰: {summary['tokens']['output']['total']}",
                  f"- 외부 LLM API 비용 추정: {summary['estimated_external_llm_api_cost_usd']} USD. 청구 금액이 아니며 장비·전력·운영 비용은 미측정.",
                  "", "## 상태별 시나리오", ""])
    for status, score in report["by_expected_status"].items():
        lines.append(f"- 기대 상태 `{status}`: {score['passed']}/{score['total']}")
    lines.extend(["", "## 보고서에 쓸 수 있는 범위", "",
                  f"고정 합성 데이터의 정상·부분 장애·거절·근거 부족 시나리오 {report['total']}개를 개발용으로 검증해 {report['passed']}개가 기대 결과를 충족했다. 수치 계산과 오류 보존을 독립 기대값으로 확인했다.",
                  "", "구현 중 사용한 개발셋이며 동결 평가·근거의 의미적 적합성은 미측정이다. 모델 호출 수가 0이면 모델 품질 검사도 아니다. 호출이 있더라도 정규식 사전 검사를 통과한 연구 요청의 제한된 계획 추출만 측정한다. 지연은 도구 실행을 포함한 애플리케이션 경과 시간이며 개별 API/LLM 응답 시간과 구분한다.",
                  "", f"코드/자료 SHA-256: `{report['code_sha256']}`", ""])
    return "\n".join(lines)


def save_report(report: dict, path: Path) -> None:
    if path.suffix.lower() != ".json":
        raise ValueError("output must end in .json; the Markdown companion is saved automatically")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    path.with_suffix(".md").write_text(report_markdown(report), encoding="utf-8")
