"""Real-document research pilot; retrieval telemetry is not answer accuracy."""

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from time import perf_counter
from urllib.parse import parse_qsl, urlencode, urlsplit

from pydantic import Field, HttpUrl, model_validator

from .evaluate import summarize_runs
from .records import RunStore, write_json_atomic
from .runtime import PACKAGE, ResearchRequest, code_fingerprint, run_research
from .schema import Model

DATASET = PACKAGE / "data/research_benchmark.json"
QUALITY_FIELDS = ("answer_correct", "citations_support_answer", "temporal_correct", "language_match")


class BenchmarkCase(Model):
    case_id: str
    event_id: str
    category: str
    question: str = Field(max_length=2000)
    language: str
    reference_answer: str
    reference_urls: list[HttpUrl] = Field(min_length=1)
    requirements: list[str] = Field(min_length=1)
    reference_checked_at: str
    expected_status: str


class Review(Model):
    evaluation_id: str
    run_id: str
    reviewer: str | None = None
    notes: str | None = None
    answer_correct: bool | None = None
    citations_support_answer: bool | None = None
    temporal_correct: bool | None = None
    language_match: bool | None = None

    @model_validator(mode="after")
    def require_review_attribution(self):
        if any(getattr(self, field) is not None for field in QUALITY_FIELDS) and not (self.reviewer and self.notes):
            raise ValueError("scored reviews require reviewer and evidence-based notes")
        return self


def load_benchmark(path: Path = DATASET) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or set(data) != {"suite", "provenance", "selection", "cases"}:
        raise ValueError("benchmark requires suite, provenance, selection and cases")
    if any(not isinstance(data[key], str) or not data[key].strip() for key in ("suite", "provenance", "selection")):
        raise ValueError("benchmark metadata must be non-empty strings")
    if not isinstance(data["cases"], list) or not data["cases"]:
        raise ValueError("benchmark must contain cases")
    cases = [BenchmarkCase.model_validate_json(json.dumps(row)) for row in data["cases"]]
    if len({row.case_id for row in cases}) != len(cases):
        raise ValueError("benchmark case IDs must be unique")
    return {**data, "cases": [row.model_dump(mode="json") for row in cases]}


def url_key(url: str) -> str:
    """Exact host/path matching; discard fragments and tracking parameters only."""
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            return ""
        query = [(key, value) for key, value in parse_qsl(parsed.query)
                 if not key.lower().startswith("utm_")]
        return parsed.hostname.lower().removeprefix("www.") + parsed.path.rstrip("/") + (
            "?" + urlencode(sorted(query)) if query else "")
    except ValueError:
        return ""


def source_coverage(case: dict, record: dict) -> dict:
    cited = {url_key(row["url"]) for row in record["result"]["sources"]
             if row["source_id"] in record["result"]["source_ids"]}
    consulted = set(cited)
    for response in record["llm_responses"]:
        for item in response.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "web_search_call":
                continue
            action = item.get("action")
            if not isinstance(action, dict):
                continue
            rows = action.get("sources")
            if isinstance(rows, list):
                consulted.update(url_key(row["url"]) for row in rows
                                 if isinstance(row, dict) and isinstance(row.get("url"), str))
    gold = {url_key(url) for url in case["reference_urls"]}
    return {"gold_urls": len(gold), "consulted_hits": len(gold & consulted),
            "cited_hits": len(gold & cited),
            "missing_cited_urls": [url for url in case["reference_urls"] if url_key(url) not in cited]}


def review_has_work(row: dict) -> bool:
    return any(row.get(field) is not None for field in (*QUALITY_FIELDS, "reviewer", "notes"))


def quality_scores(rows: list[dict], reviews: list[dict] = (), *, planned_total: int | None = None) -> dict:
    total = planned_total if planned_total is not None else len(rows)
    scores = {}
    for field in QUALITY_FIELDS:
        labels = [row[field] for row in reviews if row[field] is not None]
        scores[field] = {"passed": sum(labels) if labels else None, "reviewed": len(labels),
                         "total": total, "rate_reviewed": sum(labels) / len(labels) if labels else None,
                         "rate_all_cases": sum(labels) / total if total and len(labels) == total else None}
    return scores


def update_summary(report: dict) -> None:
    rows = report["cases"]
    metrics = [row["coverage"] for row in rows]
    gold = sum(row["gold_urls"] for row in metrics)
    report.update(total=len(rows), complete=len(rows) == report["planned_total"],
                  event_groups=len({row["expected"]["event_id"] for row in rows}),
                  operational_completed=sum(row["run"]["result"]["status"] not in {"error", "unsupported", "needs_clarification"}
                                            for row in rows),
                  reference_urls={"total": gold, "consulted_hits": sum(row["consulted_hits"] for row in metrics),
                                  "cited_hits": sum(row["cited_hits"] for row in metrics)},
                  quality=quality_scores(rows, planned_total=report["planned_total"]), summary=summarize_runs([row["run"] for row in rows]))


async def run_benchmark(*, limit: int | None = None, repeats: int = 1, dataset: Path = DATASET,
                        store: RunStore | None = None, checkpoint: Path | None = None) -> dict:
    data = load_benchmark(dataset)
    if type(repeats) is not int or not 1 <= repeats <= 5:
        raise ValueError("repeats must be between 1 and 5 (application budget, not statistical sufficiency)")
    if limit is not None and (type(limit) is not int or not 1 <= limit <= len(data["cases"])):
        raise ValueError("limit must be between 1 and the dataset case count")
    if checkpoint is not None and checkpoint.suffix != ".json":
        raise ValueError("benchmark output must end in .json")
    if checkpoint is not None and checkpoint.with_suffix(".reviews.json").exists():
        prior = json.loads(checkpoint.with_suffix(".reviews.json").read_text())
        if any(review_has_work(row) for row in prior.get("reviews", [])):
            raise ValueError("output has human reviews; choose a new output path to preserve their source report")
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY is missing in this server process; export it and restart the server")
    cases = data["cases"][:limit] if limit else data["cases"]
    started = perf_counter()
    report = {"format_version": 1, "suite": data["suite"], "mode": "live web research / OpenAI",
              "evaluated_at": datetime.now(timezone.utc).isoformat(),
              "code_sha256": code_fingerprint(), "dataset_sha256": sha256(dataset.read_bytes()).hexdigest(),
              "provenance": data["provenance"], "planned_total": len(cases) * repeats,
              "dataset_total": len(data["cases"]), "repeats": repeats, "cases": [],
              "limitations": ["Authored pilot, not held out; paired languages are correlated within event groups.",
                              "URL coverage is not claim support, semantic accuracy, or Recall@k of a complete relevance set.",
                              "Semantic quality is pending attributed human review; no regex or self-judge accuracy.",
                              "Historical fixed-answer questions do not measure breaking-news freshness or causality."]}
    for repeat in range(1, repeats + 1):
        for case in cases:
            # Only the question reaches the model; never supply reference answers, URLs or rubrics.
            record = await run_research(ResearchRequest(question=case["question"], mode="live", planner="openai", web=True), store=store)
            report["cases"].append({"evaluation_id": f"{case['case_id']}:r{repeat}", "expected": case,
                                    "run": record, "coverage": source_coverage(case, record)})
            update_summary(report)
            report["wall_duration_ms"] = round((perf_counter() - started) * 1000, 3)
            if checkpoint:
                save_benchmark(report, checkpoint)
            if any(event.get("status_code") in {401, 403, 404, 429}
                   and event["url"].startswith("https://api.openai.com/") for event in record["http"]):
                report["stop_reason"] = "Provider access or rate limit failure; remaining cases were not executed."
                if checkpoint:
                    save_benchmark(report, checkpoint)
                return report
    return report


def benchmark_markdown(report: dict) -> str:
    refs, summary = report["reference_urls"], report["summary"]
    lines = ["# Live research benchmark", "", f"Suite: {report['suite']}",
             f"Executed: {report['total']}/{report['planned_total']} · event groups: {report['event_groups']}",
             f"Operational results: {report['operational_completed']}/{report['total']} (not answer accuracy)",
             f"Gold URL coverage — consulted: {refs['consulted_hits']}/{refs['total']}; cited: {refs['cited_hits']}/{refs['total']}",
             "", "## Semantic review", ""]
    for field, score in report["quality"].items():
        lines.append(f"- {field}: {score['passed']}/{score['reviewed']} reviewed; {score['reviewed']}/{score['total']} coverage; full-set rate: {score['rate_all_cases']}")
    lines += ["", "Unreviewed labels are null, never counted as correct.", "", "## Time and usage", "",
              f"- Wall time: {report['wall_duration_ms']} ms; run latency: {summary['latency_ms']}",
              f"- Actual model calls: {summary['live_llm_calls']}; tokens: {summary['tokens']}",
              f"- Total API cost: {summary['estimated_external_llm_api_cost_usd']} USD; hosted search fees unmeasured.",
              "", "## Limits", "", *[f"- {line}" for line in report["limitations"]], "",
              f"Dataset SHA-256: {report['dataset_sha256']}", f"Code SHA-256: {report['code_sha256']}", ""]
    for row in report["cases"]:
        expected, result = row["expected"], row["run"]["result"]
        # Keep untrusted model text literal in the review document.
        fence = "`" * max(3, max(map(len, re.findall(r"`+", result["answer"])), default=0) + 1)
        lines += [f"## {row['evaluation_id']}", "", expected["question"], "",
                  f"Reference answer: {expected['reference_answer']}", "",
                  *[f"- Requirement: {item}" for item in expected["requirements"]],
                  *[f"- [Reference source]({url})" for url in expected["reference_urls"]], "",
                  f"Actual status: {result['status']}; semantic review pending unless graded above.", "",
                  fence + "text", result["answer"], fence, "",
                  *[f"- [{source['source_id']}]({source['url']})" for source in result["sources"]], ""]
    return "\n".join(lines)


def save_benchmark(report: dict, path: Path) -> None:
    if path.suffix != ".json":
        raise ValueError("benchmark output must end in .json")
    write_json_atomic(path, report)
    path.with_suffix(".md").write_text(benchmark_markdown(report))
    if "reviews" in report:
        return
    review_path = path.with_suffix(".reviews.json")
    # Preserve existing human labels; reject stale hashes at scoring time.
    if not review_path.exists():
        write_json_atomic(review_path, {"report_sha256": sha256(path.read_bytes()).hexdigest(), "reviews": [
            Review(evaluation_id=row["evaluation_id"], run_id=row["run"]["run_id"]).model_dump()
            for row in report["cases"]]})
    else:
        current = json.loads(review_path.read_text())
        if not any(review_has_work(row) for row in current.get("reviews", [])):
            write_json_atomic(review_path, {"report_sha256": sha256(path.read_bytes()).hexdigest(), "reviews": [
                Review(evaluation_id=row["evaluation_id"], run_id=row["run"]["run_id"]).model_dump()
                for row in report["cases"]]})


def score_reviews(report_path: Path, review_path: Path, output: Path) -> dict:
    report = json.loads(report_path.read_text())
    review_data = json.loads(review_path.read_text())
    if not isinstance(review_data, dict) or set(review_data) != {"report_sha256", "reviews"} or not isinstance(review_data["reviews"], list):
        raise ValueError("review file requires report_sha256 and a reviews array")
    if review_data.get("report_sha256") != sha256(report_path.read_bytes()).hexdigest():
        raise ValueError("review file belongs to a different report revision")
    reviews = [Review.model_validate_json(json.dumps(row)) for row in review_data["reviews"]]
    runs = {row["evaluation_id"]: row["run"]["run_id"] for row in report["cases"]}
    if len({row.evaluation_id for row in reviews}) != len(reviews):
        raise ValueError("duplicate review IDs")
    if any(runs.get(row.evaluation_id) != row.run_id for row in reviews):
        raise ValueError("review does not match its evaluation and run")
    if output.resolve() in {report_path.resolve(), review_path.resolve()}:
        raise ValueError("scored output must not overwrite the source report or review file")
    report["reviews"] = [row.model_dump() for row in reviews]
    report["quality"] = quality_scores(report["cases"], report["reviews"], planned_total=report["planned_total"])
    save_benchmark(report, output)
    return report
