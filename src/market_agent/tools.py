"""Deterministic evidence tools. Market figures never come from an LLM."""

from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import json
from math import log
from pathlib import Path
import re
from typing import Any

import httpx

from .schema import Period, Source, Symbol

SYMBOLS = ("BTCUSDT", "ETHUSDT", "BNBUSDT")
DAY_MS = 86_400_000


def calculate_return(open_price: Decimal, close_price: Decimal) -> Decimal:
    """Return percentage change with 40 significant digits, before display rounding."""
    for price in (open_price, close_price):
        if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
            raise ValueError("prices must be positive finite Decimals")
    with localcontext() as context:
        context.prec = 40
        return (close_price / open_price - 1) * 100


def market_window(as_of: datetime, period: Period) -> tuple[datetime, datetime]:
    """Resolve the exclusive interval of completed UTC daily candles."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    if period not in ("24h", "7d"):
        raise ValueError("period must be 24h or 7d")
    end = as_of.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return end - timedelta(days=1 if period == "24h" else 7), end


async def fetch_market_data(
    client: httpx.AsyncClient, symbol: Symbol, period: Period, *, as_of: datetime,
) -> Source:
    """Fetch and validate exactly one requested window, without retries or fallback."""
    if symbol not in SYMBOLS:
        raise ValueError("unsupported symbol")
    start, end = market_window(as_of, period)
    start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    count = (end_ms - start_ms) // DAY_MS
    response = await client.get("/api/v3/klines", params={
        "symbol": symbol, "interval": "1d", "startTime": start_ms,
        "endTime": end_ms - 1, "timeZone": "0", "limit": count,
    })
    response.raise_for_status()
    candles = response.json()
    if not isinstance(candles, list) or len(candles) != count:
        raise ValueError(f"expected {count} completed candles")
    for offset, row in enumerate(candles):
        if not isinstance(row, list) or len(row) != 12:
            raise ValueError("invalid Binance kline shape")
        expected_open = start_ms + offset * DAY_MS
        if (type(row[0]) is not int or type(row[6]) is not int
                or row[0] != expected_open or row[6] != expected_open + DAY_MS - 1):
            raise ValueError("missing, duplicate, unordered, or incomplete daily candle")
        try:
            if any(not isinstance(row[i], str) for i in (1, 2, 3, 4)):
                raise ValueError("price fields must be original decimal strings")
            opening, high, low, close = (Decimal(row[i]) for i in (1, 2, 3, 4))
            if any(not p.is_finite() or p <= 0 for p in (opening, high, low, close)):
                raise ValueError("non-positive or non-finite OHLC")
            if not low <= min(opening, close) <= max(opening, close) <= high:
                raise ValueError("inconsistent OHLC bounds")
        except InvalidOperation as exc:
            raise ValueError("invalid decimal price") from exc
    change = calculate_return(Decimal(candles[0][1]), Decimal(candles[-1][4]))
    content = {
        "symbol": symbol, "period": period, "start_utc": start.isoformat(),
        "end_utc_exclusive": end.isoformat(), "open": candles[0][1],
        "close": candles[-1][4], "return_pct": str(change),
        "display_return_pct": format(change.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), ".2f"),
        "calculation": "(last_close / first_open - 1) * 100",
        "decimal_precision": 40, "candles": candles,
    }
    return Source.model_validate_json(json.dumps({
        "source_id": f"market-{symbol}", "kind": "market",
        "title": f"{symbol} · {count} completed UTC daily candle(s)",
        "url": str(response.request.url), "content": json.dumps(content),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }))


def load_documents(path: Path) -> list[Source]:
    """Load a reviewed corpus; reject duplicate IDs and non-document sources."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("document corpus must be a JSON array")
    documents = [Source.model_validate_json(json.dumps(row)) for row in data]
    ids = [doc.source_id for doc in documents]
    if len(ids) != len(set(ids)) or any(doc.kind != "document" for doc in documents):
        raise ValueError("corpus requires unique document sources")
    return documents


def tokenize(text: str) -> list[str]:
    return re.findall(r"[0-9a-z가-힣]+", text.lower())


def build_bm25(documents: list[Source]) -> dict[str, Any]:
    terms = [tokenize(doc.title + " " + doc.content) for doc in documents]
    lengths = [len(row) for row in terms]
    return {
        "documents": documents, "frequencies": [Counter(row) for row in terms],
        "lengths": lengths, "average_length": sum(lengths) / len(lengths) if lengths else 0,
        "document_frequencies": Counter(term for row in terms for term in set(row)),
    }


def search_documents(query: str, index: dict[str, Any], *, top_k: int) -> list[Source]:
    """Small-corpus BM25, using exercise defaults k1=1.5 and b=0.75."""
    if not query.strip() or type(top_k) is not int or top_k <= 0:
        raise ValueError("query must be non-blank and top_k a positive integer")
    count = len(index["documents"])
    if not count or not index["average_length"]:
        return []
    scores = []
    for i, frequencies in enumerate(index["frequencies"]):
        score = 0.0
        for term in set(tokenize(query)):
            frequency = frequencies[term]
            if not frequency:
                continue
            df = index["document_frequencies"][term]
            idf = log(1 + (count - df + 0.5) / (df + 0.5))
            norm = 0.25 + 0.75 * index["lengths"][i] / index["average_length"]
            score += idf * frequency * 2.5 / (frequency + 1.5 * norm)
        if score > 0:
            scores.append((i, score))
    scores.sort(key=lambda item: (-item[1], item[0]))
    return [index["documents"][i] for i, _ in scores[:top_k]]
