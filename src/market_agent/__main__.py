"""Run research, replay, evaluate, or start the local web console."""

import argparse
import asyncio
import json
from pathlib import Path

from .evaluate import evaluate, save_report
from .records import ReplayMismatch, RunStore
from .runtime import ResearchRequest, replay_run, run_research


def main() -> None:
    parser = argparse.ArgumentParser(prog="market-agent")
    parser.add_argument("--data-dir", type=Path, default=Path(".market-agent"))
    sub = parser.add_subparsers(dest="command", required=True)
    research = sub.add_parser("research")
    research.add_argument("question")
    research.add_argument("--mode", choices=["demo", "live"], default="demo")
    research.add_argument("--planner", choices=["baseline", "ollama", "openai"], default="baseline")
    research.add_argument("--web", action="store_true", help="Paid OpenAI web news/macro research; requires --mode live --planner openai")
    research.add_argument("--scenario", default="none", choices=["none", "eth_timeout", "all_timeout",
                                                               "eth_missing", "eth_invalid", "eth_rate_limit"])
    research.add_argument("--as-of", default=None, help="Timezone-aware ISO timestamp")
    replay = sub.add_parser("replay")
    replay.add_argument("run_id")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--planner", choices=["baseline", "ollama", "openai"], default="baseline")
    evaluation.add_argument("--output", type=Path, default=Path(".market-agent/evaluation.json"))
    serve = sub.add_parser("serve")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    store = RunStore(args.data_dir / "runs")
    try:
        if args.command == "serve":
            import uvicorn
            from .api import create_app
            print(f"Local console: http://127.0.0.1:{args.port}", flush=True)
            uvicorn.run(create_app(args.data_dir), host="127.0.0.1", port=args.port)
            return
        if args.command == "research":
            request = ResearchRequest(question=args.question, mode=args.mode, planner=args.planner,
                                      scenario=args.scenario, as_of=args.as_of, web=args.web)
            result = asyncio.run(run_research(request, store=store))
            print(result["result"]["answer"])
            print(f"\nstatus={result['result']['status']} · run_id={result['run_id']}")
            print(f"record={store.path(result['run_id']).resolve()}")
            if result["result"]["status"] == "error":
                raise SystemExit(1)
        elif args.command == "replay":
            result = asyncio.run(replay_run(store.get(args.run_id), store=store))
            print(json.dumps({"run_id": result["run_id"], **result["comparison"]}, ensure_ascii=False, indent=2))
            if not result["comparison"]["same_result"]:
                raise SystemExit(1)
        else:
            result = asyncio.run(evaluate(args.planner))
            save_report(result, args.output)
            print(f"{result['passed']}/{result['total']} development smoke cases passed")
            print(f"report={args.output.resolve()}")
            print(f"summary={args.output.with_suffix('.md').resolve()}")
            if result["passed"] != result["total"]:
                raise SystemExit(1)
    except (ValueError, FileNotFoundError, ReplayMismatch) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    main()
