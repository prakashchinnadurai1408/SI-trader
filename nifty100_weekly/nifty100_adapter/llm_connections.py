"""Saved model connections and encrypted API keys for the local dashboard."""
import ctypes
from contextlib import contextmanager
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import re
import http.client
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from .research_jobs import progress
from uuid import uuid4

PROVIDERS = {
    "claude": ("Claude", "https://api.anthropic.com/v1", "anthropic"),
    "openai": ("OpenAI", "https://api.openai.com/v1", "openai"),
    "gemini": ("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "openai"),
    "grok": ("Grok", "https://api.x.ai/v1", "openai"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com", "openai"),
    "nvidia": ("NVIDIA", "https://integrate.api.nvidia.com/v1", "openai"),
    "openrouter": ("OpenRouter", "https://openrouter.ai/api/v1", "openai"),
    "qwen": ("Qwen", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "openai"),
    "kimi": ("Kimi", "https://api.moonshot.ai/v1", "openai"),
    "custom": ("Custom OpenAI-compatible", "", "openai"),
}


class ProviderUnavailable(ValueError):
    """A configured upstream service failed, rather than invalid user input."""
    status = 502
    code = "provider_unavailable"


class ProviderTimeout(ProviderUnavailable):
    status = 504
    code = "provider_timeout"


def provider_timeout():
    try:
        seconds = int(os.environ.get("SI_TRADER_LLM_TIMEOUT_SECONDS", "600"))
    except ValueError:
        raise ValueError("SI_TRADER_LLM_TIMEOUT_SECONDS must be an integer from 30 to 1800.") from None
    if not 30 <= seconds <= 1800:
        raise ValueError("SI_TRADER_LLM_TIMEOUT_SECONDS must be an integer from 30 to 1800.")
    return seconds

class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


def protect(value, decrypt=False):
    prefix = b"fernet:v1:"
    key = os.environ.get("SI_TRADER_ENCRYPTION_KEY")
    if (decrypt and value.startswith(prefix)) or (not decrypt and key):
        from cryptography.fernet import Fernet, InvalidToken
        try:
            cipher = Fernet((key or "").encode())
            return cipher.decrypt(value[len(prefix):]) if decrypt else prefix + cipher.encrypt(value)
        except (ValueError, InvalidToken):
            raise ValueError("The saved key cannot be opened. Check SI_TRADER_ENCRYPTION_KEY or save the connection again.") from None
    if os.name != "nt":
        raise ValueError("Set SI_TRADER_ENCRYPTION_KEY for encrypted API key storage on this host.")
    buffer = ctypes.create_string_buffer(value)
    source = Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    result = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(result)):
        raise ValueError("Windows could not access this API key. Save it again under the current user.")
    try:
        return ctypes.string_at(result.data, result.size)
    finally:
        release = ctypes.windll.kernel32.LocalFree
        release.argtypes = [ctypes.c_void_p]
        release.restype = ctypes.c_void_p
        release(result.data)


@contextmanager
def connection():
    folder = Path(os.environ.get("SI_TRADER_LLM_HOME", str(Path.home() / ".si-trader")))
    folder.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(folder / "llm.sqlite", timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA secure_delete=ON")
    conn.execute("""CREATE TABLE IF NOT EXISTS profiles
        (id TEXT PRIMARY KEY, provider TEXT, label TEXT, model TEXT, endpoint TEXT, secret BLOB)""")
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def profiles():
    with connection() as conn:
        return [dict(id=row["id"], provider=row["provider"], label=row["label"], model=row["model"],
                     endpoint=row["endpoint"], hasKey=bool(row["secret"])) for row in conn.execute("SELECT * FROM profiles ORDER BY label, id")]


def validate_endpoint(value):
    if not isinstance(value, str) or len(value) > 2048 or any(ord(char) <= 32 for char in value):
        raise ValueError("Enter a valid HTTPS API base URL.")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Use an HTTPS API base URL without credentials, query or fragment.")
    return value.rstrip("/")


def save_profile(payload):
    provider = payload.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError("Choose a supported provider.")
    label, model = payload.get("label"), payload.get("model")
    if any(not isinstance(v, str) or not 1 <= len(v.strip()) <= cap for v, cap in ((label, 80), (model, 160))):
        raise ValueError("Enter a connection name and exact model ID.")
    if "@" in model or any(char.isspace() for char in model.strip()):
        raise ValueError("Model ID must be the provider's model identifier, such as z-ai/glm-5.3-flash. Enter a descriptive name in Connection name.")
    endpoint = payload.get("endpoint") or PROVIDERS[provider][1]
    if not isinstance(endpoint, str):
        raise ValueError("Enter an API base URL.")
    endpoint = validate_endpoint(endpoint)
    secret = payload.get("apiKey", "")
    if not isinstance(secret, str) or len(secret) > 8192 or any(ord(c) < 32 for c in secret):
        raise ValueError("Enter a valid API key.")
    identifier = payload.get("id") or uuid4().hex
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Choose a valid saved connection.")
    if secret and not secret.strip():
        raise ValueError("Enter a valid API key.")
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        old = conn.execute("SELECT * FROM profiles WHERE id=?", (identifier,)).fetchone()
        if payload.get("id") and old is None:
            raise ValueError("The connection no longer exists.")
        if not secret and (old is None or not old["secret"] or old["endpoint"] != endpoint or old["provider"] != provider):
            raise ValueError("Enter an API key for this provider and endpoint.")
        encrypted = protect(secret.encode()) if secret else old["secret"]
        conn.execute("INSERT OR REPLACE INTO profiles VALUES (?,?,?,?,?,?)",
                     (identifier, provider, label.strip(), model.strip(), endpoint, encrypted))
    return {"id": identifier}


def delete_profile(identifier, key_only=False):
    if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
        raise ValueError("Choose a saved connection.")
    with connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if key_only:
            conn.execute("UPDATE profiles SET secret=NULL WHERE id=?", (identifier,))
        else:
            conn.execute("DELETE FROM profiles WHERE id=?", (identifier,))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("The API redirected. Set its final API base URL before retrying.")


def chat(identifier, payload):
    with connection() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE id=?", (identifier,)).fetchone()
    if row is None or not row["secret"]:
        raise ValueError("The model connection or its API key was deleted. Configure it again.")
    key = protect(row["secret"], decrypt=True).decode()
    if "@" in row["model"]:
        raise ValueError("This connection has an email address in Model ID. Edit it and choose a provider model.")
    messages = list(payload["messages"])
    if any(message.get("images") for message in messages):
        raise ValueError("Cloud connections currently support text research. Choose a local vision model for screenshot review.")
    format_spec = payload.get("format")
    if format_spec:
        instruction = "Return only a valid JSON value."
        if isinstance(format_spec, dict):
            instruction += " Match this JSON Schema: " + json.dumps(format_spec)
        messages = [{"role": "system", "content": instruction}, *messages]
    options = payload.get("options", {})
    headers = {"Content-Type": "application/json"}
    if PROVIDERS[row["provider"]][2] == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
        body = {"model": row["model"], "max_tokens": max(128, options.get("num_predict", 900)),
                "system": "\n".join(m["content"] for m in messages if m["role"] == "system"),
                "messages": [m for m in messages if m["role"] != "system"]}
        suffix = "/messages"
    else:
        headers["Authorization"] = "Bearer " + key
        body = {"model": row["model"], "messages": messages, "stream": False,
                "max_tokens": max(128, options.get("num_predict", 900))}
        if row["provider"] == "openai":
            body["max_completion_tokens"] = body.pop("max_tokens")
        if row["provider"] == "nvidia" and row["model"].startswith("z-ai/glm-5.3"):
            body["reasoning_effort"] = "low"
            body["chat_template_kwargs"] = {"clear_thinking": True}
            # This model counts reasoning and final text against the same budget.
            body["max_tokens"] = max(4096, body["max_tokens"])
            if isinstance(format_spec, dict):
                body["response_format"] = {"type": "json_schema", "json_schema": {
                    "name": "research_result", "strict": True, "schema": format_spec,
                }}
        suffix = "/chat/completions"
    request = Request(validate_endpoint(row["endpoint"]) + suffix, json.dumps(body).encode(), headers)
    timeout = provider_timeout()
    progress("Waiting for AI provider", model=row["model"], providerTimeoutSeconds=timeout)
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Provider response exceeded the supported size.")
        data = json.loads(raw)
        if suffix == "/messages":
            content = "".join(item["text"] for item in data["content"] if item["type"] == "text")
        else:
            content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            if suffix != "/messages" and data["choices"][0].get("finish_reason") == "length":
                raise ValueError("The model exhausted its output budget before returning an answer. Choose a model with a smaller reasoning budget or retry in LLM Configuration.")
            raise ValueError("The selected model returned no text.")
        return {"message": {"content": content}}
    except HTTPError as error:
        if error.code in (408, 504):
            raise ProviderTimeout("The AI provider timed out. No new basket or paper fills were created. Retry once, or test/select another model in LLM Configuration.") from None
        if error.code in (429, 500, 502, 503):
            raise ProviderUnavailable(f"The AI provider is busy or unavailable (HTTP {error.code}). Retry later or select another model in LLM Configuration.") from None
        if error.code == 404:
            raise ValueError("Provider could not find this model or API route (HTTP 404). Edit the connection, load available models, and check the API base URL.") from None
        raise ValueError(f"Provider returned HTTP {error.code}. Check the key, model access, quota and API endpoint.") from None
    except (TimeoutError, URLError) as error:
        if isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError):
            raise ProviderTimeout(f"The AI provider did not answer within {timeout} seconds. No new basket or paper fills were created. Retry once, or test/select another model in LLM Configuration.") from None
        raise ProviderUnavailable("Could not connect to the AI provider. Check the network and API endpoint, or select another model in LLM Configuration.") from None
    except (OSError, http.client.HTTPException):
        raise ProviderUnavailable("The AI provider connection was interrupted. Retry once, or test/select another model in LLM Configuration.") from None
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("Provider returned an unsupported response format.") from None


def provider_models(payload):
    provider = payload.get("provider")
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError("Choose a provider.")
    endpoint = validate_endpoint(payload.get("endpoint") or PROVIDERS[provider][1])
    key = payload.get("apiKey") or ""
    if not isinstance(key, str) or any(ord(char) < 32 for char in key):
        raise ValueError("Enter a valid API key.")
    identifier = payload.get("id")
    if identifier is not None and (not isinstance(identifier, str) or not re.fullmatch(r"[a-f0-9]{32}", identifier)):
        raise ValueError("Choose a saved connection.")
    if not key and identifier:
        with connection() as conn:
            row = conn.execute("SELECT * FROM profiles WHERE id=?", (payload["id"],)).fetchone()
        if row and row["provider"] == provider and row["endpoint"] == endpoint and row["secret"]:
            key = protect(row["secret"], True).decode()
    if not key:
        raise ValueError("Enter an API key or edit a saved connection that has a key.")
    headers = {"Accept": "application/json"}
    if PROVIDERS[provider][2] == "anthropic":
        headers.update({"x-api-key": key, "anthropic-version": "2023-06-01"})
    else:
        headers["Authorization"] = "Bearer " + key
    try:
        with build_opener(NoRedirect()).open(Request(endpoint + "/models", headers=headers), timeout=20) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("Provider model list exceeds the supported size.")
        data = json.loads(raw)
        models = sorted({item["id"] for item in data["data"] if isinstance(item, dict) and isinstance(item.get("id"), str)})
        if not models:
            raise ValueError("The provider returned no available model IDs.")
        return {"models": models}
    except HTTPError as error:
        raise ValueError(f"Model listing returned HTTP {error.code}. Check the endpoint and key, or enter the model ID from your provider console.") from None
    except (OSError, http.client.HTTPException):
        raise ValueError("Could not retrieve the provider model list. Retry or enter its exact model ID.") from None
    except (KeyError, TypeError, json.JSONDecodeError):
        raise ValueError("Provider model listing has an unsupported format. Enter the exact model ID from its console.") from None
