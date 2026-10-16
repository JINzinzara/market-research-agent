"""Synthetic offline data, deliberately unrelated to historical Binance prices."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from .tools import DAY_MS

DEMO_AS_OF = datetime(2026, 10, 16, tzinfo=timezone.utc)
# Explicit seven-day openings and closings. Evaluation expectations are separate.
PRICES = {
    "BTCUSDT": [("100", "101"), ("101", "102"), ("102", "103"), ("103", "104"),
                ("104", "105"), ("105", "106"), ("106", "110")],
    "ETHUSDT": [("200", "198"), ("198", "196"), ("196", "194"), ("194", "192"),
                ("192", "191"), ("191", "190"), ("190", "180")],
    "BNBUSDT": [("50", "51"), ("51", "52"), ("52", "51"), ("51", "50"),
                ("50", "50"), ("50", "50"), ("50", "50")],
}


def demo_transport(scenario: str = "none") -> httpx.MockTransport:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.method != "GET" or request.url.path != "/api/v3/klines":
            raise ValueError("unexpected demo request")
        params = request.url.params
        symbol = params["symbol"]
        if scenario == "all_timeout" or (scenario == "eth_timeout" and symbol == "ETHUSDT"):
            raise httpx.ReadTimeout("Synthetic timeout (failure injection)", request=request)
        if scenario == "eth_rate_limit" and symbol == "ETHUSDT":
            return httpx.Response(429, json={"code": -1003, "msg": "Synthetic rate limit"})
        rows = []
        first_day = DEMO_AS_OF - timedelta(days=7)
        for day, (opening, close) in enumerate(PRICES[symbol]):
            timestamp = int((first_day + timedelta(days=day)).timestamp() * 1000)
            if int(params["startTime"]) <= timestamp <= int(params["endTime"]):
                high, low = max(Decimal(opening), Decimal(close)), min(Decimal(opening), Decimal(close))
                rows.append([timestamp, opening, str(high), str(low), close, "1",
                             timestamp + DAY_MS - 1, "1", 1, "1", "1", "0"])
        if symbol == "ETHUSDT" and scenario == "eth_missing" and rows:
            rows.pop()
        if symbol == "ETHUSDT" and scenario == "eth_invalid" and rows:
            rows[0][1] = "NaN"
        return httpx.Response(200, json=rows)
    return httpx.MockTransport(respond)
