"""Serve the SI-Trader paper dashboard on the local machine."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from pathlib import Path
from .deployment import Runtime, Sessions

from .ai_parameters import PARAMETERS, catalogue_view, propose_profile
from .llm_connections import PROVIDERS, profiles, save_profile, delete_profile, provider_models
from .ai_strategy import generate_plan, installed_models, test_model
from .data.catalogue_evidence import collect_evidence
from .data.nse_market import load_nifty100
from .full_catalogue import full_catalogue, readiness, run_report
from .investright import broker_get, holdings_count
from .research_committee import build_committee, held_symbols
from .research_watchlist import build_watchlist
from .strategy_lab import pulse, run_comparison, run_diagnostics, run_replay
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
    def send_payload(self, status, content_type, payload, headers=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status, result, headers=None):
        self.send_payload(status, "application/json", json.dumps(result).encode(), headers)

    def local_request(self):
        return self.server.runtime.allowed_host(self.headers.get("Host"), self.server.server_port)

    def authenticated(self):
        return not self.server.runtime.hosted or self.server.sessions.authorized(self.headers.get("Cookie"))

    def read_json(self):
        size = int(self.headers.get("Content-Length", 0))
        if not 0 < size <= 32_768:
            raise ValueError("Provide a valid request body.")
        payload = json.loads(self.rfile.read(size))
        if not isinstance(payload, dict):
            raise ValueError("Provide a JSON object.")
        return payload

    def do_GET(self):
        if self.path == "/healthz" and (self.local_request() or self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"):
            self.send_json(200, {"status": "ok", "paper": True})
            return
        if not self.local_request():
            self.send_error(403)
            return
        if self.path == "/api/auth/session":
            self.send_json(200, {"hosted": self.server.runtime.hosted, "authenticated": self.authenticated()})
            return
        if self.path not in FILES:
            self.send_error(404)
            return
        name, content_type = FILES[self.path]
        self.send_payload(200, content_type, (ASSETS / name).read_bytes())

    def do_POST(self):
        if not self.local_request() or not self.server.runtime.allowed_origin(self.headers.get("Origin"), self.server.server_port):
            self.send_error(403)
            return
        try:
            # Consume bounded bodies before responding, including authentication failures.
            payload = self.read_json() if self.headers.get("Content-Length", "0") != "0" else {}
            if self.path == "/api/auth/login" and self.server.runtime.hosted:
                token, status = self.server.sessions.login(payload.get("email"), payload.get("password"), self.server.runtime)
                if token:
                    self.send_json(200, {"authenticated": True}, {"Set-Cookie": self.server.sessions.cookie(token)})
                else:
                    self.send_json(status, {"error": "Too many attempts. Try again in 15 minutes." if status == 429 else "Invalid sign-in details."})
                return
            if not self.authenticated():
                self.send_json(401, {"error": "Sign in to continue."})
                return
            if self.path == "/api/auth/logout":
                self.server.sessions.logout(self.headers.get("Cookie"))
                self.send_json(200, {"authenticated": False}, {"Set-Cookie": self.server.sessions.cookie("", clear=True)})
                return
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
                try:
                    models, error = installed_models(), ""
                except ValueError as exc:
                    models, error = [], str(exc)
                self.send_json(200, {"models": models, "profiles": profiles(), "error": error,
                                     "providers": [{"id": key, "label": value[0], "endpoint": value[1]} for key, value in PROVIDERS.items()]})
            elif self.path in ("/api/parameters", "/api/strategy", "/api/strategy-builder", "/api/watchlist", "/api/full-catalogue", "/api/research-committee", "/api/quant-diagnostics", "/api/monthly-comparison", "/api/research-replay", "/api/model-test", "/api/llm-save", "/api/llm-delete", "/api/llm-delete-key", "/api/provider-models"):
                if self.path == "/api/provider-models":
                    self.send_json(200, provider_models(payload))
                    return
                if self.path == "/api/llm-save":
                    self.send_json(200, save_profile(payload))
                    return
                if self.path in ("/api/llm-delete", "/api/llm-delete-key", "/api/provider-models"):
                    delete_profile(payload.get("id"), key_only=self.path == "/api/llm-delete-key")
                    self.send_json(200, {"deleted": True})
                    return
                if self.path == "/api/research-replay":
                    self.send_json(200, run_replay(payload))
                    return
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
                if self.path == "/api/model-test":
                    if not isinstance(model, str) or model not in installed_models():
                        raise ValueError("Choose an available model in LLM Configuration.")
                    self.send_json(200, test_model(model))
                    return
                objective = payload.get("objective")
                max_positions = payload.get("maxPositions")
                if not isinstance(objective, str) or not 1 <= len(objective.strip()) <= 500:
                    raise ValueError("Enter a strategy objective of up to 500 characters.")
                if not isinstance(model, str) or model not in installed_models():
                    raise ValueError("Choose an available model in LLM Configuration.")
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


class DashboardServer(ThreadingHTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(30)
        return connection, address


def create_server(host="127.0.0.1", port=8765, runtime=None):
    runtime = runtime or Runtime.environment()
    if not runtime.hosted and host != "127.0.0.1":
        raise ValueError("Non-loopback binding requires SI_TRADER_MODE=hosted.")
    server = DashboardServer((host, port), DashboardHandler)
    server.runtime = runtime
    server.sessions = Sessions()
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--host", default="0.0.0.0" if os.environ.get("SI_TRADER_MODE") == "hosted" else "127.0.0.1")
    args = parser.parse_args()
    with create_server(args.host, args.port) as server:
        print(f"SI-Trader running on {args.host}:{server.server_port} ({'hosted' if server.runtime.hosted else 'local'})", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
