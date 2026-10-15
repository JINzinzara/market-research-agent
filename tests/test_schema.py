"""Check research schema contracts without a model server or network access."""

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

from pydantic import ValidationError

# Test this checkout directly, without relying on editable-install .pth files.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_agent.schema import (
    DraftAnswer,
    Reflection,
    ResearchPlan,
    ResearchResult,
    Source,
)


class SchemaTests(unittest.TestCase):
    def setUp(self):
        """Prepare valid inputs that each test can change independently."""
        self.market_plan = {
            "action": "research",
            "symbols": ["BTCUSDT"],
            "period": "24h",
        }
        self.source_data = {
            "source_id": "doc-1",
            "kind": "document",
            "title": "Market reference",
            "url": "https://example.com/reference",
            "content": "Collected evidence.",
            "retrieved_at": datetime(2026, 10, 15, tzinfo=timezone.utc),
        }
        self.source = Source.model_validate(self.source_data)
        self.other_source = Source.model_validate(
            {**self.source_data, "source_id": "doc-2"}
        )
        self.completed = {
            "status": "completed",
            "answer": "An answer based on evidence.",
            "sources": [self.source],
            "source_ids": ["doc-1"],
        }
        self.valid_inputs = [
            (ResearchPlan, self.market_plan),
            (Source, self.source_data),
            (DraftAnswer, {"answer": "An answer.", "source_ids": ["doc-1"]}),
            (Reflection, {"needs_more_research": False, "reason": "Evidence is sufficient."}),
            (ResearchResult, self.completed),
        ]

    def test_research_plans_accept_market_documents_and_combined_requests(self):
        cases = [
            self.market_plan,
            {**self.market_plan, "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"], "period": "7d"},
            {"action": "research", "document_query": "rolling window definition"},
            {**self.market_plan, "document_query": "rolling window definition"},
        ]
        for data in cases:
            with self.subTest(data=data):
                plan = ResearchPlan.model_validate(data)
                self.assertIsInstance(plan, ResearchPlan)
                self.assertEqual(plan.symbols, data.get("symbols", []))
                self.assertEqual(plan.period, data.get("period"))
                self.assertEqual(plan.document_query, data.get("document_query"))

    def test_research_plans_reject_inconsistent_targets(self):
        cases = [
            {"action": "research"},
            {"action": "research", "symbols": ["BTCUSDT"]},
            {"action": "research", "period": "24h"},
            {**self.market_plan, "message": "Which trading pair?"},
            {**self.market_plan, "symbols": ["BTCUSDT", "BTCUSDT"]},
        ]
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    ResearchPlan.model_validate(data)

    def test_non_research_plans_require_a_message_and_no_research_fields(self):
        for action in ("clarify", "unsupported"):
            data = {"action": action, "message": "Please clarify the request."}
            with self.subTest(action=action):
                plan = ResearchPlan.model_validate(data)
                self.assertEqual(plan.message, data["message"])
                self.assertEqual(plan.symbols, [])
                self.assertIsNone(plan.period)
                self.assertIsNone(plan.document_query)

            invalid = [
                {"action": action},
                {"action": action, "message": " "},
                {**data, "symbols": ["BTCUSDT"]},
                {**data, "period": "24h"},
                {**data, "document_query": "rolling window"},
            ]
            for invalid_data in invalid:
                with self.subTest(data=invalid_data):
                    with self.assertRaises(ValidationError):
                        ResearchPlan.model_validate(invalid_data)

    def test_plans_reject_unsupported_actions_symbols_and_periods(self):
        cases = [
            {**self.market_plan, "action": "buy"},
            {**self.market_plan, "symbols": ["SOLUSDT"]},
            {**self.market_plan, "period": "1m"},
            {**self.market_plan, "period": "1y"},
        ]
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    ResearchPlan.model_validate(data)

    def test_reflection_accepts_continuing_and_stopping_with_reasons(self):
        cases = [
            {"needs_more_research": True, "reason": "A definition is missing.", "follow_up_query": "rolling window definition"},
            {"needs_more_research": False, "reason": "Evidence is sufficient."},
        ]
        for data in cases:
            with self.subTest(data=data):
                reflection = Reflection.model_validate(data)
                self.assertEqual(reflection.reason, data["reason"])
                self.assertEqual(reflection.follow_up_query, data.get("follow_up_query"))

    def test_reflection_rejects_inconsistent_follow_up_queries(self):
        cases = [
            {"needs_more_research": True, "reason": "A definition is missing."},
            {"needs_more_research": True, "reason": "A definition is missing.", "follow_up_query": " "},
            {"needs_more_research": False, "reason": "Evidence is sufficient.", "follow_up_query": "rolling window"},
        ]
        for data in cases:
            with self.subTest(data=data):
                with self.assertRaises(ValidationError):
                    Reflection.model_validate(data)

    def test_reflection_requires_a_reason_even_when_research_stops(self):
        for needs_more_research in (True, False):
            data = {"needs_more_research": needs_more_research}
            if needs_more_research:
                data["follow_up_query"] = "rolling window definition"
            for invalid_data in (data, {**data, "reason": " "}):
                with self.subTest(data=invalid_data):
                    with self.assertRaises(ValidationError):
                        Reflection.model_validate(invalid_data)

    def test_source_rejects_invalid_urls_naive_timestamps_and_unknown_kinds(self):
        changes = [
            {"url": "not a URL"},
            {"url": "ftp://example.com/reference"},
            {"retrieved_at": datetime(2026, 10, 15)},
            {"kind": "unknown"},
        ]
        for change in changes:
            with self.subTest(change=change):
                with self.assertRaises(ValidationError):
                    Source.model_validate({**self.source_data, **change})

    def test_completed_results_can_cite_a_subset_of_collected_sources(self):
        result = ResearchResult.model_validate(
            {**self.completed, "sources": [self.source, self.other_source]}
        )
        self.assertEqual(result.source_ids, ["doc-1"])
        self.assertEqual([source.source_id for source in result.sources], ["doc-1", "doc-2"])

    def test_non_completed_results_can_explain_missing_evidence(self):
        for status in ("insufficient_evidence", "needs_clarification", "unsupported", "error"):
            for sources in ([], [self.source]):
                with self.subTest(status=status, sources=sources):
                    result = ResearchResult.model_validate(
                        {"status": status, "answer": "An explanation.", "sources": sources}
                    )
                    self.assertEqual(result.source_ids, [])
                    self.assertEqual(result.status, status)

    def test_results_reject_duplicate_collected_source_ids(self):
        duplicate = Source.model_validate(
            {**self.source_data, "content": "A different excerpt with the same ID."}
        )
        with self.assertRaises(ValidationError):
            ResearchResult.model_validate(
                {"status": "insufficient_evidence", "answer": "An explanation.", "sources": [self.source, duplicate]}
            )

    def test_results_reject_duplicate_citation_ids(self):
        with self.assertRaises(ValidationError):
            ResearchResult.model_validate(
                {**self.completed, "source_ids": ["doc-1", "doc-1"]}
            )

    def test_results_reject_unknown_citations_for_all_outcomes(self):
        for status in ("completed", "insufficient_evidence", "needs_clarification", "unsupported", "error"):
            with self.subTest(status=status):
                with self.assertRaises(ValidationError):
                    ResearchResult.model_validate(
                        {**self.completed, "status": status, "source_ids": ["missing"]}
                    )

    def test_completed_results_require_at_least_one_citation(self):
        for sources in ([], [self.source]):
            with self.subTest(sources=sources):
                with self.assertRaises(ValidationError):
                    ResearchResult.model_validate(
                        {**self.completed, "sources": sources, "source_ids": []}
                    )

    def test_common_configuration_rejects_extra_fields(self):
        for model, data in self.valid_inputs:
            with self.subTest(model=model.__name__):
                with self.assertRaises(ValidationError):
                    model.model_validate({**data, "unexpected": "value"})

    def test_common_configuration_rejects_wrong_types(self):
        cases = [
            (ResearchPlan, {**self.market_plan, "symbols": ("BTCUSDT",)}),
            (Source, {**self.source_data, "content": 123}),
            (DraftAnswer, {"answer": 123}),
            (Reflection, {"needs_more_research": "false", "reason": "Sufficient."}),
            (Reflection, {"needs_more_research": 1, "reason": "Missing.", "follow_up_query": "definition"}),
            (ResearchResult, {**self.completed, "source_ids": ("doc-1",)}),
        ]
        for model, data in cases:
            with self.subTest(model=model.__name__, data=data):
                with self.assertRaises(ValidationError):
                    model.model_validate(data)

    def test_common_configuration_rejects_blank_text(self):
        cases = [
            (ResearchPlan, {**self.market_plan, "document_query": " "}),
            (Source, {**self.source_data, "source_id": " "}),
            (Source, {**self.source_data, "title": " "}),
            (Source, {**self.source_data, "content": " "}),
            (DraftAnswer, {"answer": " "}),
            (DraftAnswer, {"answer": "An answer.", "source_ids": [" "]}),
            (Reflection, {"needs_more_research": False, "reason": " "}),
            (ResearchResult, {**self.completed, "answer": " "}),
        ]
        for model, data in cases:
            with self.subTest(model=model.__name__, data=data):
                with self.assertRaises(ValidationError):
                    model.model_validate(data)

    def test_common_configuration_strips_surrounding_whitespace(self):
        cases = [
            (ResearchPlan, {"action": "research", "document_query": "  definition  "}, "document_query", "definition"),
            (Source, {**self.source_data, "content": "  Evidence.  "}, "content", "Evidence."),
            (DraftAnswer, {"answer": "  An answer.  "}, "answer", "An answer."),
            (Reflection, {"needs_more_research": False, "reason": "  Sufficient.  "}, "reason", "Sufficient."),
            (ResearchResult, {**self.completed, "answer": "  An answer.  "}, "answer", "An answer."),
        ]
        for model, data, field, expected in cases:
            with self.subTest(model=model.__name__):
                self.assertEqual(getattr(model.model_validate(data), field), expected)

    def test_llm_output_schemas_can_be_sent_as_json(self):
        for model in (ResearchPlan, DraftAnswer, Reflection):
            with self.subTest(model=model.__name__):
                schema = json.loads(json.dumps(model.model_json_schema()))
                self.assertEqual(schema["type"], "object")
                self.assertIs(schema["additionalProperties"], False)
                self.assertTrue(schema["properties"])

    def test_llm_json_responses_are_validated_into_model_instances(self):
        cases = [
            (ResearchPlan, {"action": "research", "symbols": ["BTCUSDT"], "period": "24h"}),
            (DraftAnswer, {"answer": "An answer.", "source_ids": ["doc-1"]}),
            (Reflection, {"needs_more_research": False, "reason": "Evidence is sufficient."}),
        ]
        for model, data in cases:
            with self.subTest(model=model.__name__):
                result = model.model_validate_json(json.dumps(data))
                self.assertIsInstance(result, model)
                self.assertEqual(result, model.model_validate(data))

    def test_llm_json_validation_rejects_malformed_or_inconsistent_data(self):
        for model in (ResearchPlan, DraftAnswer, Reflection):
            for payload in ("{", "[]", "{}"):
                with self.subTest(model=model.__name__, payload=payload):
                    with self.assertRaises(ValidationError):
                        model.model_validate_json(payload)

        inconsistent = [
            (ResearchPlan, {"action": "research", "symbols": ["BTCUSDT"]}),
            (Reflection, {"needs_more_research": True, "reason": "Missing evidence."}),
        ]
        for model, data in inconsistent:
            with self.subTest(model=model.__name__, data=data):
                with self.assertRaises(ValidationError):
                    model.model_validate_json(json.dumps(data))

    def test_source_and_result_json_round_trips_preserve_evidence(self):
        cases = [
            self.source,
            ResearchResult.model_validate(self.completed),
        ]
        for value in cases:
            with self.subTest(model=type(value).__name__):
                restored = type(value).model_validate_json(value.model_dump_json())
                self.assertEqual(restored, value)


if __name__ == "__main__":
    unittest.main()
