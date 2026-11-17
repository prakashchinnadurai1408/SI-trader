"""Serve the SI-Trader paper dashboard on the local machine."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
from pathlib import Path

from .ai_parameters import PARAMETERS, catalogue_view, propose_profile
from .ai_strategy import generate_plan, installed_models
from .data.catalogue_evidence import collect_evidence
from .data.nse_market import load_nifty100
from .full_catalogue import full_catalogue, readiness, run_report
from .investright import broker_get, holdings_count
from .research_committee import build_committee, held_symbols
from .research_watchlist import build_watchlist
from .strategy_lab import pulse, run_comparison, run_diagnostics
from .strategy_builder import build_research_strategy
from .weekly_research import weekly_candidates, weekly_context
from .trading_workspace import ENDPOINTS, affordable_candidates, broker_snapshot, cash_amount, number, paper_sizing

ASSETS = Path(__file__).with_name("web")
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
}


class DashboardHandler(BaseHTTPRequestHandler):
    def send_payload(self, status, content_type, payload):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, result):
        self.send_payload(status, "application/json", json.dumps(result).encode())

    def local_request(self):
        port = self.server.server_port
        return self.headers.get("Host") == f"127.0.0.1:{port}"

    def do_GET(self):
        if not self.local_request():
            self.send_error(403)
            return
        if self.path not in FILES:
            self.send_error(404)
            return
        name, content_type = FILES[self.path]
        self.send_payload(200, content_type, (ASSETS / name).read_bytes())

    def do_POST(self):
        origin = f"http://127.0.0.1:{self.server.server_port}"
        if not self.local_request() or self.headers.get("Origin") != origin:
            self.send_error(403)
            return
        try:
            if self.path == "/api/holdings":
                self.send_json(200, {"count": holdings_count()})
            elif self.path == "/api/broker":
                self.send_json(200, broker_snapshot())
            elif self.path == "/api/catalogue-evidence":
                frame, market = load_nifty100()
                self.send_json(200, collect_evidence(frame, market))
            elif self.path == "/api/catalogue-readiness":
                self.send_json(200, full_catalogue())
            elif self.path == "/api/parameter-run-report":
                frame, market = load_nifty100()
                coverage, records = readiness(frame, market)
                self.send_json(200, run_report(coverage, records, "preview"))
            elif self.path == "/api/strategy-lab":
                self.send_json(200, pulse())
            elif self.path == "/api/models":
                self.send_json(200, {"models": installed_models()})
            elif self.path in ("/api/parameters", "/api/strategy", "/api/strategy-builder", "/api/watchlist", "/api/full-catalogue", "/api/research-committee", "/api/quant-diagnostics", "/api/monthly-comparison"):
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 32_768:
                    raise ValueError("Provide a valid strategy configuration.")
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError("Provide a strategy configuration.")
                if self.path == "/api/monthly-comparison":
                    self.send_json(200, run_comparison(payload))
                    return
                if self.path == "/api/quant-diagnostics":
                    symbol = payload.get("symbol")
                    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9._&-]{0,29}", symbol):
                        raise ValueError("Choose a valid NSE symbol.")
                    self.send_json(200, run_diagnostics(symbol, payload.get("horizon")))
                    return
                model = payload.get("model")
                objective = payload.get("objective")
                max_positions = payload.get("maxPositions")
                if not isinstance(objective, str) or not 1 <= len(objective.strip()) <= 500:
                    raise ValueError("Enter a strategy objective of up to 500 characters.")
                if not isinstance(model, str) or model not in installed_models():
                    raise ValueError("Choose an installed Ollama model in LLM configuration.")
                if self.path == "/api/research-committee":
                    holdings = held_symbols(payload.get("holdings", []))
                    self.send_json(200, build_committee(model, objective.strip(), holdings))
                    return
                if self.path == "/api/full-catalogue":
                    self.send_json(200, full_catalogue(model, objective.strip()))
                    return
                if self.path == "/api/watchlist":
                    self.send_json(200, build_watchlist(model, objective.strip()))
                    return
                if self.path == "/api/strategy-builder":
                    self.send_json(200, build_research_strategy(model, objective.strip()))
                    return
                if self.path == "/api/parameters":
                    self.send_json(200, {"parameters": catalogue_view(propose_profile(model, objective.strip()))})
                    return
                if type(max_positions) is not int or not 1 <= max_positions <= 10:
                    raise ValueError("Choose 1 to 10 positions.")
                trading = payload.get("execution")
                if not isinstance(trading, dict):
                    raise ValueError("Save execution settings before running.")
                funding = trading.get("funding")
                cash_buffer = number(trading.get("cashBuffer"))
                scenario_move = number(trading.get("scenarioMove"))
                execute = trading.get("paperAuto")
                if funding not in ("paper", "broker") or type(execute) is not bool:
                    raise ValueError("Choose a cash source and paper execution mode.")
                if cash_buffer is None or not 10 <= cash_buffer <= 90:
                    raise ValueError("Cash buffer must be 10–90%.")
                if scenario_move is None or not 0.1 <= scenario_move <= 25:
                    raise ValueError("Scenario move must be 0.1–25%.")
                budget = cash_amount(broker_get(ENDPOINTS["funds"])) if funding == "broker" else number(trading.get("paperCapital"))
                if budget is None or not 0 <= budget <= 10_000_000_000:
                    raise ValueError("Choose a valid capital amount.")
                frame, market = load_nifty100()
                coverage, records = readiness(frame, market)
                context, market_dials = weekly_context(coverage, records)
                candidates, weights, rejected = weekly_candidates(frame, coverage, records)
                # The least favorable observed dial can only reduce the user-set paper exposure.
                exposure = (100 - cash_buffer) * min(market_dials.values(), default=100) / 100
                effective_buffer = 100 - exposure
                affordable = affordable_candidates(candidates, budget, effective_buffer)[:12]
                active_scores = [
                    {"name": PARAMETERS[key].display_name, "weight": round(weight, 2)}
                    for key, weight in weights.items()
                ]
                plan = generate_plan(
                    model, objective.strip(), affordable, max_positions, active_scores,
                    {"available_cash_inr": budget, "cash_buffer_pct": round(effective_buffer, 2), "paper": True},
                    research_context=context,
                ) if affordable else {"basket": [], "title": "", "thesis": ""}
                execution = paper_sizing(plan["basket"], budget, effective_buffer, scenario_move, execute)
                if candidates and not affordable:
                    message = "No shortlisted stock can be sized within the current paper cash or exposure limit."
                elif not candidates:
                    message = "No research candidates passed the observed checks with sufficient comparable score data."
                else:
                    message = ""
                market["unverifiedChecks"] = [row["label"] for row in coverage["parameters"]
                                               if row["key"] in rejected and not row["ready"]]
                self.send_json(200, {
                    **plan,
                    "basket": execution["basket"],
                    "execution": {key: value for key, value in execution.items() if key != "basket"},
                    "funding": funding,
                    "model": model,
                    "market": market,
                    "considered": len(frame),
                    "parameterRunReport": run_report(
                        coverage, records, "weekly", weights, rejected,
                        tuple(item["symbol"] for item in execution["basket"]),
                        market_dials=market_dials, planner_used=bool(affordable),
                    ),
                    "maximumPaperExposurePct": round(exposure, 2),
                    "message": message,
                })
            else:
                self.send_error(404)
        except (ValueError, OSError) as error:
            self.send_json(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), DashboardHandler) as server:
        print(f"SI-Trader running at http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
