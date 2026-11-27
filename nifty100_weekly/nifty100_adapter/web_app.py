"""Serve the SI-Trader paper dashboard on the local machine."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from .deployment import Runtime, Sessions

from .ai_parameters import PARAMETERS, catalogue_view, propose_profile
from .llm_connections import PROVIDERS, profiles, save_profile, delete_profile, provider_models
from .ai_strategy import generate_plan, installed_models, test_model
from .data.catalogue_evidence import collect_evidence
from .data.nse_market import load_nifty100
from .full_catalogue import full_catalogue, readiness, run_report, score_individual_stock
from .investright import broker_get, holdings_count
from .research_committee import build_committee, held_symbols
from .research_watchlist import build_watchlist
from .strategy_lab import pulse, run_comparison, run_diagnostics, run_replay
from .strategy_builder import build_research_strategy
from .weekly_research import weekly_candidates, weekly_context
from .trading_workspace import ENDPOINTS, affordable_candidates, broker_snapshot, cash_amount, number, paper_sizing
from .broker import (
    BrokerConfig, BrokerPlatform, PaperBrokerAdapter,
    KiteConnectAdapter, OpenAlgoAdapter, FenixAdapter,
    OrderRequest, OrderSide, OrderType, ProductType,
)
from .options import black_scholes, build_option_chain, payoff, implied_volatility
from .realtime import PriceRegistry, intraday_scan
from .tax import capital_gains_for_trades, Trade
from .webhooks import WebhookStore, fire_webhooks, deliver_webhook

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

    def _get_broker(self):
        adapter = self.server.broker_adapter
        if adapter is None or not adapter.is_connected():
            raise ValueError("Broker not connected. POST /api/broker/connect first.")
        return adapter

    def _handle_broker_subpath(self, payload):
        subpath = self.path[len("/api/broker/"):]
        adapter = self.server.broker_adapter

        if subpath == "connect":
            platform = payload.get("platform", "paper")
            if platform == "paper":
                adapter = PaperBrokerAdapter(BrokerConfig(
                    platform=BrokerPlatform.ZERODHA_KITE,
                    client_id=payload.get("client_id", "PAPER"),
                ), webhook_store=self.server.webhook_store)
            else:
                try:
                    plat = BrokerPlatform(platform)
                except ValueError:
                    raise ValueError(f"Unknown broker platform: {platform}")
                if plat == BrokerPlatform.ZERODHA_KITE:
                    adapter = KiteConnectAdapter(BrokerConfig(
                        platform=plat,
                        client_id=payload.get("client_id", ""),
                        api_key=payload.get("api_key", ""),
                        secret_key=payload.get("secret_key", ""),
                        access_token=payload.get("access_token", ""),
                    ))
                elif plat == BrokerPlatform.OPEN_ALGO:
                    adapter = OpenAlgoAdapter(BrokerConfig(
                        platform=plat,
                        api_key=payload.get("api_key", ""),
                        base_url=payload.get("base_url", "http://localhost:5000"),
                    ))
                elif plat == BrokerPlatform.FENIX:
                    adapter = FenixAdapter(BrokerConfig(
                        platform=plat,
                        api_key=payload.get("api_key", ""),
                        base_url=payload.get("base_url", "http://localhost:8000"),
                    ))
                else:
                    adapter = PaperBrokerAdapter(BrokerConfig(
                        platform=BrokerPlatform.ZERODHA_KITE,
                        client_id=payload.get("client_id", "PAPER"),
                    ))
            if not adapter.connect():
                raise ValueError(f"Broker connect failed: {platform}")
            self.server.broker_adapter = adapter
            self.send_json(200, {
                "connected": True,
                "platform": platform,
                "account_id": adapter.account_id,
            })
            return

        if subpath == "disconnect":
            if adapter:
                adapter.disconnect()
            self.server.broker_adapter = None
            self.send_json(200, {"connected": False})
            return

        broker = self._get_broker()

        if subpath == "margins":
            m = broker.get_margins()
            self.send_json(200, {
                "available_cash": m.available_cash if m else 0.0,
                "used_margin": m.used_margin if m else 0.0,
                "total_margin": m.total_margin if m else 0.0,
                "timestamp": m.timestamp if m else None,
            })
            return

        if subpath == "positions":
            positions = broker.get_positions()
            self.send_json(200, {
                "positions": [
                    {
                        "symbol": p.symbol,
                        "quantity": p.quantity,
                        "average_price": p.average_price,
                        "current_price": p.current_price,
                        "pnl": p.pnl,
                        "pnl_percent": p.pnl_percent,
                        "product": p.product.value,
                    }
                    for p in positions
                ]
            })
            return

        if subpath == "orders":
            orders = broker.get_orders()
            self.send_json(200, {
                "orders": [
                    {
                        "order_id": o.order_id,
                        "algo_id": o.algo_id,
                        "symbol": o.symbol,
                        "action": o.action.value,
                        "quantity": o.quantity,
                        "price": o.price,
                        "order_type": o.order_type.value,
                        "product": o.product.value,
                        "status": o.status.value,
                        "filled_quantity": o.filled_quantity,
                        "average_price": o.average_price,
                        "timestamp": o.timestamp,
                        "error_message": o.error_message,
                    }
                    for o in orders
                ]
            })
            return

        if subpath == "trades":
            trades = broker.get_trades()
            self.send_json(200, {
                "trades": [
                    {
                        "trade_id": t.trade_id,
                        "order_id": t.order_id,
                        "symbol": t.symbol,
                        "action": t.action.value,
                        "quantity": t.quantity,
                        "price": t.price,
                        "timestamp": t.timestamp,
                        "brokerage": t.brokerage,
                    }
                    for t in trades
                ]
            })
            return

        if subpath == "place-order":
            symbol = payload.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Provide a valid symbol.")
            action = OrderSide(payload.get("action", "BUY").upper())
            quantity = int(payload.get("quantity", 1))
            price = payload.get("price")
            order_type = OrderType(payload.get("order_type", "MARKET").upper())
            product = ProductType(payload.get("product", "CNC").upper())
            validity = payload.get("validity", "DAY")
            stop_loss = payload.get("stop_loss")
            target = payload.get("target")
            tag = payload.get("tag")
            strategy_id = payload.get("strategy_id")

            order = OrderRequest(
                symbol=symbol, action=action, quantity=quantity,
                price=float(price) if price is not None else None,
                order_type=order_type, product=product,
                validity=validity, stop_loss=float(stop_loss) if stop_loss is not None else None,
                target=float(target) if target is not None else None,
                tag=tag, strategy_id=strategy_id,
            )
            resp = broker.place_order(order)
            self.send_json(200, {
                "order_id": resp.order_id,
                "algo_id": resp.algo_id,
                "status": resp.status.value,
                "filled_quantity": resp.filled_quantity,
                "average_price": resp.average_price,
                "brokerage": resp.brokerage,
                "exchange": resp.exchange,
                "timestamp": resp.timestamp,
                "error_message": resp.error_message,
            })
            return

        self.send_error(404)


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
            elif self.path.startswith("/api/broker/"):
                self._handle_broker_subpath(payload)
                return
            elif self.path.startswith("/api/options/"):
                self._handle_options_subpath(payload)
                return
            elif self.path.startswith("/api/realtime/"):
                self._handle_realtime_subpath(payload)
                return
            elif self.path.startswith("/api/tax/"):
                self._handle_tax_subpath(payload)
                return
            elif self.path.startswith("/api/webhooks/"):
                self._handle_webhooks_subpath(payload)
                return
                return
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
                if self.path == "/api/individual-stock-score":
                    symbol = payload.get("symbol")
                    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9._&-]{0,29}", symbol):
                        raise ValueError("Choose a valid NSE symbol.")
                    frame, market = load_nifty100()
                    evidence, records = readiness(frame, market)
                    self.send_json(200, score_individual_stock(symbol, records, evidence))
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
        except Exception as error:  # defensive: never leave the connection empty
            self.send_json(500, {"error": "Internal server error."})

    def _handle_options_subpath(self, payload):
        subpath = self.path[len("/api/options/"):]

        if subpath == "greeks":
            symbol = payload.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Provide a valid symbol.")
            strike = float(payload.get("strike", 0))
            rate = float(payload.get("rate", 0.06))
            vol = float(payload.get("vol", 0.20))
            tte_days = float(payload.get("tte_days", 30))
            option_type = payload.get("option_type", "call").lower()
            if option_type not in ("call", "put"):
                raise ValueError("option_type must be 'call' or 'put'")
            spot = float(payload.get("spot", 100))
            tte = tte_days / 365.0
            g = black_scholes(option_type, spot, strike, rate, vol, tte)
            self.send_json(200, {
                "symbol": symbol, "option_type": option_type, "spot": spot,
                "strike": strike, "rate": rate, "vol": vol,
                "tte_days": tte_days, "tte_years": tte,
                "price": g.price, "delta": g.delta, "gamma": g.gamma,
                "theta": g.theta, "vega": g.vega, "rho": g.rho,
                "d1": g.d1, "d2": g.d2,
            })
            return

        if subpath == "iv":
            symbol = payload.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Provide a valid symbol.")
            strike = float(payload.get("strike", 0))
            rate = float(payload.get("rate", 0.06))
            tte_days = float(payload.get("tte_days", 30))
            option_type = payload.get("option_type", "call").lower()
            market_price = float(payload.get("market_price", 0))
            spot = float(payload.get("spot", 100))
            tte = tte_days / 365.0
            iv = implied_volatility(option_type, spot, strike, rate, market_price, tte)
            bs = black_scholes(option_type, spot, strike, rate, 0.20, tte) if iv is None else None
            self.send_json(200, {
                "symbol": symbol, "option_type": option_type, "spot": spot,
                "strike": strike, "rate": rate,
                "market_price": market_price, "tte_days": tte_days,
                "implied_volatility": iv,
                "theoretical_price_at_20pct_vol": bs.price if bs else None,
            })
            return

        if subpath == "chain":
            symbol = payload.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Provide a valid symbol.")
            spot = float(payload.get("spot", 100))
            strikes_raw = payload.get("strikes", [])
            if not isinstance(strikes_raw, list) or not strikes_raw:
                # Generate strikes around spot
                strikes = [round(spot * (1 + (i - 5) * 0.05), 2) for i in range(11)]
            else:
                strikes = [float(s) for s in strikes_raw]
            expiry = payload.get("expiry", "2026-12-31")
            rate = float(payload.get("rate", 0.06))
            vol = float(payload.get("vol", 0.20))
            tte_days = float(payload.get("tte_days", 30))
            tte = tte_days / 365.0
            market_prices = payload.get("market_prices", {})
            chain = build_option_chain(
                symbol, spot, strikes, expiry, rate, vol, tte,
                market_prices=market_prices,
            )
            self.send_json(200, chain)
            return

        if subpath == "payoff":
            symbol = payload.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Provide a valid symbol.")
            strike = float(payload.get("strike", 100))
            premium = float(payload.get("premium", 5))
            option_type = payload.get("option_type", "call").lower()
            if option_type not in ("call", "put"):
                raise ValueError("option_type must be 'call' or 'put'")
            spot_low = float(payload.get("spot_low", 50))
            spot_high = float(payload.get("spot_high", 150))
            steps = int(payload.get("steps", 21))
            spot_range = [spot_low + (spot_high - spot_low) * i / (steps - 1) for i in range(steps)]
            result = payoff(option_type, strike, premium, spot_range)
            self.send_json(200, {
                "symbol": symbol, "option_type": option_type,
                "strike": strike, "premium": premium,
                "spot_low": spot_low, "spot_high": spot_high, "steps": steps,
                "payoff": result,
            })
            return

        self.send_error(404)

    def _handle_realtime_subpath(self, payload):
        subpath = self.path[len("/api/realtime/"):]
        registry = self.server.price_registry

        if subpath == "quote":
            symbol = payload.get("symbol")
            if not isinstance(symbol, str) or not symbol:
                raise ValueError("Provide a valid symbol.")
            price = payload.get("price")
            previous_close = payload.get("previous_close")
            volume = payload.get("volume")
            if price is not None:
                q = registry.set_quote(
                    symbol, float(price),
                    float(previous_close) if previous_close is not None else None,
                    int(volume) if volume is not None else None,
                )
            else:
                q = registry.get_quote(symbol)
                if q is None:
                    raise ValueError(f"No quote for {symbol}")
            self.send_json(200, q.to_dict())
            return

        if subpath == "quotes":
            quotes = [q.to_dict() for q in registry.get_all_quotes()]
            self.send_json(200, {
                "quotes": quotes,
                "count": len(quotes),
                "symbols": registry.symbols(),
            })
            return

        if subpath == "scan":
            watchlist = payload.get("watchlist", [])
            if not isinstance(watchlist, list) or not watchlist:
                raise ValueError("Provide a watchlist of symbols.")
            breakout_pct = float(payload.get("breakout_pct", 1.0))
            result = intraday_scan(registry, [str(s) for s in watchlist], breakout_pct)
            self.send_json(200, result)
            return

        self.send_error(404)

    def _handle_tax_subpath(self, payload):
        subpath = self.path[len("/api/tax/"):]

        if subpath in ("capital-gains", "statement"):
            fy = payload.get("fy", "FY2025-26")
            trades_raw = payload.get("trades", [])
            if not isinstance(trades_raw, list):
                raise ValueError("trades must be a list.")
            trades = []
            for t in trades_raw:
                td = t.get("trade_date")
                if isinstance(td, str):
                    td = datetime.fromisoformat(td).date()
                elif isinstance(td, date):
                    pass
                else:
                    raise ValueError("trade_date required (YYYY-MM-DD).")
                symbol = t.get("symbol")
                if not isinstance(symbol, str) or not symbol:
                    raise ValueError("symbol required.")
                side = t.get("side", "BUY").upper()
                if side not in ("BUY", "SELL"):
                    raise ValueError("side must be BUY or SELL.")
                quantity = int(t.get("quantity", 0))
                price = float(t.get("price", 0))
                brokerage = float(t.get("brokerage", 0))
                trades.append(Trade(
                    trade_date=td, symbol=symbol, side=side,
                    quantity=quantity, price=price, brokerage=brokerage,
                ))
            stmt = capital_gains_for_trades(trades, fy)
            self.send_json(200, stmt.to_dict())
            return

        self.send_error(404)

    def _handle_webhooks_subpath(self, payload):
        subpath = self.path[len("/api/webhooks/"):]
        store = self.server.webhook_store

        if subpath == "register":
            url = payload.get("url")
            if not isinstance(url, str) or not url:
                raise ValueError("Provide a webhook url.")
            secret = payload.get("secret", "")
            events = payload.get("events", ["*"])
            if not isinstance(events, list):
                raise ValueError("events must be a list.")
            wh = store.register(url, secret, events)
            self.send_json(200, wh.to_dict())
            return

        if subpath == "list":
            self.send_json(200, {
                "webhooks": [w.to_dict() for w in store.list_all()],
                "count": len(store.list_all()),
            })
            return

        if subpath == "unregister":
            webhook_id = payload.get("id")
            if not isinstance(webhook_id, str) or not webhook_id:
                raise ValueError("Provide the webhook id returned by register or list.")
            ok = store.unregister(webhook_id)
            self.send_json(200, {"unregistered": ok})
            return

        if subpath == "test":
            webhook_id = payload.get("id")
            if not isinstance(webhook_id, str) or not webhook_id:
                raise ValueError("Provide the webhook id returned by register or list.")
            event = payload.get("event", "test.ping")
            test_payload = payload.get("payload", {"test": True})
            if not isinstance(event, str) or not event.strip() or any(ord(char) < 32 for char in event):
                raise ValueError("Provide a nonempty webhook event without control characters.")
            if not isinstance(test_payload, dict):
                raise ValueError("Webhook payload must be a JSON object.")
            wh = store.get(webhook_id) if webhook_id else None
            if wh is None:
                raise ValueError("Webhook not found. Use a current id from register or list; registrations reset when the server restarts.")
            ok = deliver_webhook(wh.url, wh.secret, event, test_payload)
            self.send_json(200, {"delivered": ok, "event": event, "url": wh.url})
            return

        self.send_error(404)


class DashboardServer(ThreadingHTTPServer):
    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(90)
        return connection, address


def create_server(host="127.0.0.1", port=8765, runtime=None):
    runtime = runtime or Runtime.environment()
    if not runtime.hosted and host != "127.0.0.1":
        raise ValueError("Non-loopback binding requires SI_TRADER_MODE=hosted.")
    server = DashboardServer((host, port), DashboardHandler)
    server.runtime = runtime
    server.sessions = Sessions()
    server.broker_adapter = None
    server.price_registry = PriceRegistry()
    server.webhook_store = WebhookStore()
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
