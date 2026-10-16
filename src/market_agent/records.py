"""Local atomic run storage and a network-free, strict HTTP replay boundary."""

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter
from uuid import UUID

import httpx

from .llm import without_reasoning


class ReplayMismatch(Exception):
    """Recorded execution and current requests no longer agree."""


def request_key(request: httpx.Request) -> dict:
    return {"method": request.method, "url": str(request.url),
            "body": request.content.decode("utf-8")}


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport, tape: list[dict]):
        self.inner, self.tape = inner, tape

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        event = {**request_key(request), "sequence": len(self.tape) + 1}
        self.tape.append(event)
        started = perf_counter()
        try:
            response = await self.inner.handle_async_request(request)
            await response.aread()
            body = response.text
            if request.url.path in {"/api/chat", "/v1/responses"}:
                try:
                    payload = response.json()
                    if isinstance(payload, dict):
                        body = json.dumps(without_reasoning(payload), ensure_ascii=False)
                except ValueError:
                    # Do not persist an unparseable model response that may contain reasoning.
                    body = "[unparseable model response omitted]"
            event.update(status_code=response.status_code, response_text=body,
                         retry_after=response.headers.get("retry-after"), error=None)
            return response
        except httpx.RequestError as exc:
            event.update(error={"type": type(exc).__name__, "message": str(exc)})
            raise
        finally:
            event["duration_ms"] = round((perf_counter() - started) * 1000, 3)

    async def aclose(self) -> None:
        await self.inner.aclose()


class ReplayTransport(httpx.AsyncBaseTransport):
    def __init__(self, tape: list[dict]):
        self.tape, self.position = deepcopy(tape), 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self.position >= len(self.tape):
            raise ReplayMismatch("current code requested an unrecorded HTTP call")
        event = self.tape[self.position]
        if request_key(request) != {key: event[key] for key in ("method", "url", "body")}:
            raise ReplayMismatch(f"HTTP request mismatch at position {self.position + 1}")
        self.position += 1
        if event.get("error"):
            error = event["error"]
            error_class = getattr(httpx, error["type"], None)
            if not isinstance(error_class, type) or not issubclass(error_class, httpx.RequestError):
                raise ReplayMismatch("unsupported recorded transport error")
            raise error_class(error["message"], request=request)
        headers = {"retry-after": event["retry_after"]} if event.get("retry_after") else {}
        return httpx.Response(event["status_code"], text=event["response_text"], headers=headers)

    def assert_consumed(self) -> None:
        if self.position != len(self.tape):
            raise ReplayMismatch(f"{len(self.tape) - self.position} recorded HTTP calls were unused")


class RunStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def path(self, run_id: str) -> Path:
        if str(UUID(run_id)) != run_id:
            raise ValueError("invalid run ID")
        return self.directory / f"{run_id}.json"

    def save(self, record: dict) -> None:
        destination = self.path(record["run_id"])
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory,
                                             suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def get(self, run_id: str) -> dict:
        record = json.loads(self.path(run_id).read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("format_version") != 1:
            raise ValueError("unsupported run format version")
        return record

    def list(self) -> list[dict]:
        # shortcut: scan local JSON files; add pagination if run history becomes large.
        records = []
        for path in self.directory.glob("*.json"):
            try:
                record = self.get(path.stem)
                records.append({key: record[key] for key in
                                ("run_id", "started_at", "request", "metrics", "replay_of")}
                               | {"status": record["result"]["status"]})
            except (ValueError, KeyError, OSError):
                continue
        return sorted(records, key=lambda row: row["started_at"], reverse=True)
