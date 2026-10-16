"""Check the Ollama request and response boundary without a model server."""

import copy
import json
from pathlib import Path
import sys
import unittest

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from market_agent.llm import call_llm


MESSAGES = [{"role": "user", "content": "Say hello."}]
RESULT = {
    "message": {"role": "assistant", "content": "Hello."},
    "done": True,
    "prompt_eval_count": 7,
    "eval_count": 3,
    "total_duration": 123,
}


class CallLLMTests(unittest.IsolatedAsyncioTestCase):
    def test_import_uses_checkout(self):
        self.assertEqual(
            Path(call_llm.__code__.co_filename).resolve(),
            PROJECT_ROOT / "src" / "market_agent" / "llm.py",
        )

    async def test_payload_full_response_and_input_preservation(self):
        for schema in (None, {}, {"type": "object"}):
            with self.subTest(schema=schema):
                messages = copy.deepcopy(MESSAGES)
                original_schema = copy.deepcopy(schema)

                def handle(request):
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(str(request.url), "http://localhost:11434/api/chat")
                    expected = {
                        "model": "qwen3:8b",
                        "messages": MESSAGES,
                        "stream": False,
                        "think": False,
                        "options": {"temperature": 0},
                        "keep_alive": "10m",
                    }
                    if schema is not None:
                        expected["format"] = schema
                    self.assertEqual(json.loads(request.content), expected)
                    return httpx.Response(200, json=RESULT)

                async with httpx.AsyncClient(
                    base_url="http://localhost:11434",
                    transport=httpx.MockTransport(handle),
                ) as client:
                    result = await call_llm(client, "qwen3:8b", messages, schema)
                    self.assertEqual(result, RESULT)
                    self.assertEqual(messages, MESSAGES)
                    self.assertEqual(schema, original_schema)
                    self.assertFalse(client.is_closed)

    async def test_invalid_inputs_are_rejected_before_request(self):
        def reject_request(request):
            self.fail("Invalid inputs must not send an HTTP request")

        cases = [("", MESSAGES), ("   ", MESSAGES), (None, MESSAGES)]
        cases += [("qwen3:8b", value) for value in ([], {}, None)]
        async with httpx.AsyncClient(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(reject_request),
        ) as client:
            for model, messages in cases:
                with self.subTest(model=model, messages=messages):
                    with self.assertRaises(ValueError):
                        await call_llm(client, model, messages)

    async def test_invalid_response_structure(self):
        cases = [[], "text", {}, {"message": None}, {"message": "text"}]
        for body in cases:
            with self.subTest(body=body):
                async with httpx.AsyncClient(
                    base_url="http://localhost:11434",
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
                ) as client:
                    with self.assertRaises(ValueError):
                        await call_llm(client, "qwen3:8b", MESSAGES)

    async def test_incomplete_response_or_unusable_content(self):
        cases = [{**RESULT, "done": value} for value in (False, 1, "true", None)]
        cases.append({"message": RESULT["message"]})
        cases += [{**RESULT, "message": {"content": value}} for value in (None, 1, "", " \n")]
        cases.append({**RESULT, "message": {}})
        for body in cases:
            with self.subTest(body=body):
                async with httpx.AsyncClient(
                    base_url="http://localhost:11434",
                    transport=httpx.MockTransport(lambda request: httpx.Response(200, json=body)),
                ) as client:
                    with self.assertRaises(RuntimeError):
                        await call_llm(client, "qwen3:8b", MESSAGES)

    async def test_invalid_json_is_propagated(self):
        async with httpx.AsyncClient(
            base_url="http://localhost:11434",
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"not json")),
        ) as client:
            with self.assertRaises(json.JSONDecodeError):
                await call_llm(client, "qwen3:8b", MESSAGES)

    async def test_http_errors_are_propagated(self):
        for status in (400, 500):
            with self.subTest(status=status):
                async with httpx.AsyncClient(
                    base_url="http://localhost:11434",
                    transport=httpx.MockTransport(lambda request: httpx.Response(status, json=RESULT)),
                ) as client:
                    with self.assertRaises(httpx.HTTPStatusError) as caught:
                        await call_llm(client, "qwen3:8b", MESSAGES)
                    self.assertEqual(caught.exception.response.status_code, status)
                    self.assertFalse(client.is_closed)

    async def test_transport_errors_are_propagated(self):
        for error in (httpx.ReadTimeout("timeout"), httpx.ConnectError("connection failed")):
            with self.subTest(error=type(error).__name__):
                def handle(request):
                    raise error

                async with httpx.AsyncClient(
                    base_url="http://localhost:11434",
                    transport=httpx.MockTransport(handle),
                ) as client:
                    with self.assertRaises(type(error)) as caught:
                        await call_llm(client, "qwen3:8b", MESSAGES)
                    self.assertIs(caught.exception, error)
                    self.assertFalse(client.is_closed)


if __name__ == "__main__":
    unittest.main()
