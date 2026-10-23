import json
import os
import threading
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener


class ProviderError(Exception):
    """Sanitized failure safe to display without credentials or response bodies."""


@dataclass(frozen=True)
class ProviderCapabilities:
    name: str
    max_batch: int = 50
    max_bytes: int = 120_000
    timeout: int = 30


@dataclass(frozen=True)
class BatchResult:
    texts: list[str]
    billed_characters: int


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Provider redirect refused")


class DeepLProvider:
    capabilities = ProviderCapabilities("DeepL")

    def __init__(self, api_key=None, opener=None):
        self._key = api_key if api_key is not None else os.environ.get("DEEPL_API_KEY", "")
        self._opener = opener or build_opener(NoRedirect())

    def validate_configuration(self):
        if not self._key or self._key.strip() != self._key or any(c in self._key for c in "\r\n"):
            raise ProviderError("Set a valid DEEPL_API_KEY environment variable")

    def estimate_cost(self, texts):
        return {"source_characters": sum(map(len, texts)), "currency_cost": None,
                "note": "Account pricing and billable token placeholders may differ"}

    def translate_batch(self, texts, source, target, cancel=None):
        self.validate_configuration()
        cancel = cancel or threading.Event()
        if not 1 <= len(texts) <= self.capabilities.max_batch:
            raise ProviderError("Batch must contain 1–50 texts")
        payload = json.dumps({"text": texts, "source_lang": source, "target_lang": target,
                              "preserve_formatting": True}, ensure_ascii=False).encode("utf-8")
        if len(payload) > self.capabilities.max_bytes:
            raise ProviderError("Batch exceeds request size limit")
        host = "api-free.deepl.com" if self._key.endswith(":fx") else "api.deepl.com"
        request = Request(f"https://{host}/v2/translate", data=payload,
                          headers={"Authorization": f"DeepL-Auth-Key {self._key}", "Content-Type": "application/json"})
        for attempt in range(3):
            if cancel.is_set():
                raise ProviderError("Cancelled before request")
            try:
                with self._opener.open(request, timeout=self.capabilities.timeout) as response:
                    raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ProviderError("Provider response exceeds limit")
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise ProviderError("Malformed provider response")
                rows = result.get("translations")
                if not isinstance(rows, list) or len(rows) != len(texts):
                    raise ProviderError("Invalid provider translation count")
                if not all(isinstance(r, dict) and isinstance(r.get("text"), str) and r["text"].strip() for r in rows):
                    raise ProviderError("Empty or malformed provider translation")
                if not all(type(r.get("billed_characters", 0)) is int and r.get("billed_characters", 0) >= 0 for r in rows):
                    raise ProviderError("Invalid provider usage report")
                billed = sum(r.get("billed_characters", 0) for r in rows)
                return BatchResult([r["text"] for r in rows], billed)
            except HTTPError as exc:
                if (exc.code == 429 or 500 <= exc.code < 600) and attempt < 2:
                    if cancel.wait(2 ** attempt):
                        raise ProviderError("Cancelled during backoff") from None
                    continue
                raise ProviderError(f"DeepL HTTP {exc.code}; request failed") from None
            except (URLError, TimeoutError, OSError):
                raise ProviderError("Provider network failure; billing may be uncertain, no automatic network retry") from None
            except (ValueError, KeyError, TypeError, UnicodeError):
                raise ProviderError("Malformed provider response") from None
        raise ProviderError("Provider retry limit reached")
