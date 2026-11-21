"""Multi-provider LLM client for SI-Trader.

Real completions across the 10 providers the BRD supports. Uses only the
standard library (urllib) so it works on the core requirements.txt with no
extra dependency.

Providers
    openai, anthropic, nvidia, gemini, deepseek, grok, z.ai, kimi, qwen,
    ollama

Design rules
    - never raises: callers fall back to their own logic
    - API keys come from the environment only, never from argv or logs
    - responses are parsed defensively (models often wrap JSON in prose)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)


class ProviderSpec:
    """Endpoint and model metadata for one provider."""

    def __init__(self, name, base_url, default_model, env_var,
                 style="openai"):
        self.name = name
        self.base_url = base_url
        self.default_model = default_model
        self.env_var = env_var
        self.style = style  # "openai" or "anthropic"


PROVIDERS: Dict[str, ProviderSpec] = {
    "openai": ProviderSpec(
        "openai", "https://api.openai.com/v1", "gpt-4o-mini", "OPENAI_API_KEY"),
    "anthropic": ProviderSpec(
        "anthropic", "https://api.anthropic.com/v1", "claude-3-5-haiku-latest",
        "ANTHROPIC_API_KEY", style="anthropic"),
    "nvidia": ProviderSpec(
        "nvidia", "https://integrate.api.nvidia.com/v1",
        "nvidia/llama-3.1-nemotron-ultra-253b-v1", "NVIDIA_API_KEY"),
    "gemini": ProviderSpec(
        "gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-1.5-flash", "GEMINI_API_KEY"),
    "deepseek": ProviderSpec(
        "deepseek", "https://api.deepseek.com/v1", "deepseek-chat",
        "DEEPSEEK_API_KEY"),
    "grok": ProviderSpec(
        "grok", "https://api.x.ai/v1", "grok-2-latest", "XAI_API_KEY"),
    "z.ai": ProviderSpec(
        "z.ai", "https://api.z.ai/v1", "glm-4-plus", "ZAI_API_KEY"),
    "kimi": ProviderSpec(
        "kimi", "https://api.moonshot.cn/v1", "moonshot-v1-8k",
        "MOONSHOT_API_KEY"),
    "qwen": ProviderSpec(
        "qwen", "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus", "DASHSCOPE_API_KEY"),
    "ollama": ProviderSpec(
        "ollama", "http://localhost:11434/v1", "llama3.1", "", style="openai"),
}

SUPPORTED_PROVIDERS = list(PROVIDERS.keys())


def _extract_json(text: str) -> Optional[Any]:
    """Pull the first JSON object/array out of a model response."""
    if not text:
        return None
    if isinstance(text, (dict, list)):  # already parsed
        return text
    # strip code fences
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fenced:
        text = fenced.group(1)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find the outermost JSON span
    start = None
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        i = text.find(open_ch)
        if i != -1 and (start is None or i < start):
            start = i
            closer = close_ch
    if start is None:
        return None
    depth = 0
    for j in range(start, len(text)):
        if text[j] in "{[":
            depth += 1
        elif text[j] in "}]":
            depth -= 1
            if depth == 0:
                snippet = text[start:j + 1]
                try:
                    return json.loads(snippet)
                except json.JSONDecodeError:
                    return None
    return None


class LLMClient:
    """Chat-completion client for the 10 supported providers."""

    def __init__(self, provider: str = "openai", model: Optional[str] = None,
                 api_key: Optional[str] = None, base_url: Optional[str] = None,
                 timeout: int = 60):
        provider = (provider or "openai").lower()
        if provider not in PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{provider}'. "
                f"Supported: {', '.join(SUPPORTED_PROVIDERS)}")
        spec = PROVIDERS[provider]
        self.provider = provider
        self.spec = spec
        self.model = model or spec.default_model
        self.base_url = (base_url or spec.base_url).rstrip("/")
        self.timeout = timeout
        # Key resolution order: explicit arg -> env var. Never logged.
        self.api_key = api_key or os.environ.get(spec.env_var, "")

    # -- availability ----------------------------------------------------

    def has_credentials(self) -> bool:
        if self.provider == "ollama":
            return True  # local, keyless
        return bool(self.api_key)

    # -- raw completion --------------------------------------------------

    def complete(self, system: str, prompt: str,
                 temperature: float = 0.2,
                 max_tokens: int = 2048) -> str:
        """Return the assistant text for a system/user prompt pair."""
        if not self.has_credentials():
            logger.info("LLMClient(%s): no API key configured", self.provider)
            return ""

        if self.spec.style == "anthropic":
            payload = {
                "model": self.model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
            headers = {
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
            url = f"{self.base_url}/messages"
        else:
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            headers = {
                "content-type": "application/json",
                "authorization": f"Bearer {self.api_key}",
            }
            url = f"{self.base_url}/chat/completions"

        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("LLMClient(%s) HTTP %s", self.provider, exc.code)
            return ""
        except Exception as exc:  # network/timeout/JSON
            logger.warning("LLMClient(%s) request failed: %s",
                           self.provider, type(exc).__name__)
            return ""

        if self.spec.style == "anthropic":
            for block in body.get("content", []) or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
            return ""
        choices = body.get("choices") or []
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return ""

    # -- strategy ideas --------------------------------------------------

    def generate_strategy_ideas(self, system: str, prompt: str,
                                max_ideas: int = 5) -> List[Dict[str, Any]]:
        """Ask the model for strategy ideas and return normalised dicts."""
        text = self.complete(system, prompt)
        data = _extract_json(text)
        if data is None:
            logger.info("LLMClient(%s): no parseable strategy JSON",
                        self.provider)
            return []

        if isinstance(data, dict):
            for key in ("strategies", "ideas", "results"):
                if isinstance(data.get(key), list):
                    data = data[key]
                    break
            else:
                data = [data]
        if not isinstance(data, list):
            return []

        ideas: List[Dict[str, Any]] = []
        for item in data[:max_ideas]:
            if not isinstance(item, dict):
                continue
            idea = self._normalise_idea(item)
            if idea:
                ideas.append(idea)
        return ideas

    @staticmethod
    def _normalise_idea(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Coerce a model idea into the StrategyIdea field shape."""
        name = str(item.get("name") or item.get("strategy_name") or "").strip()
        if not name:
            return None
        stype = str(item.get("strategy_type") or "momentum").strip().lower()
        if stype not in ("momentum", "mean_reversion", "breakout",
                         "fundamental"):
            stype = "momentum"

        def rules(value):
            return value if isinstance(value, dict) else {}

        try:
            confidence = float(item.get("confidence", item.get(
                "confidence_score", 60)))
        except (TypeError, ValueError):
            confidence = 60.0

        try:
            hold = int(item.get("expected_hold_days", 5))
        except (TypeError, ValueError):
            hold = 5

        return {
            "name": name,
            "strategy_type": stype,
            "description": str(item.get("description", "") or ""),
            "entry_rules": rules(item.get("entry_rules")),
            "exit_rules": rules(item.get("exit_rules")),
            "risk_rules": rules(item.get("risk_rules")),
            "confidence": max(0.0, min(100.0, confidence)),
            "expected_hold_days": max(1, hold),
        }


__all__ = [
    "LLMClient", "PROVIDERS", "SUPPORTED_PROVIDERS", "ProviderSpec",
]