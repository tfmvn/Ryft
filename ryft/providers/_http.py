"""Minimal HTTP helpers shared by provider backends.

Uses urllib (stdlib) so Ryft has no heavy HTTP dependency. Synchronous
functions here are always called from `asyncio.to_thread` by the providers, so
they never block the event loop. Retries transient failures with backoff.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from .base import ProviderError

_RETRYABLE = {429, 500, 502, 503, 504}


def post_json(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 60,
    retries: int = 2,
) -> dict:
    body = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    last: Exception | None = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            status = exc.code
            detail = _read_error(exc)
            if status in (401, 403):
                raise ProviderError(detail, kind="auth", status=status) from exc
            if status == 429:
                last = ProviderError(detail, kind="rate_limit", status=status)
            elif status in _RETRYABLE:
                last = ProviderError(detail, kind="unavailable", status=status)
            else:
                raise ProviderError(detail, kind="unknown", status=status) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last = ProviderError(str(exc), kind="timeout")
        except json.JSONDecodeError as exc:
            raise ProviderError(f"invalid JSON response: {exc}", kind="unknown") from exc

        if attempt < retries:
            time.sleep(0.4 * (2 ** attempt))
    raise last or ProviderError("request failed", kind="unknown")


def post_stream(
    url: str,
    payload: dict,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 120,
):
    """Yield raw decoded lines from a streaming endpoint (SSE or JSONL)."""
    body = json.dumps(payload).encode()
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=hdrs, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        status = exc.code
        kind = "auth" if status in (401, 403) else "unavailable" if status in _RETRYABLE else "unknown"
        raise ProviderError(_read_error(exc), kind=kind, status=status) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(str(exc), kind="timeout") from exc
    with resp:
        for raw in resp:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line:
                yield line


def get_json(url: str, *, headers: dict[str, str] | None = None, timeout: int = 5) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raise ProviderError(_read_error(exc), kind="unavailable", status=exc.code) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ProviderError(str(exc), kind="timeout") from exc
    except json.JSONDecodeError as exc:
        raise ProviderError(f"invalid JSON: {exc}", kind="unknown") from exc


def _read_error(exc: urllib.error.HTTPError) -> str:
    try:
        return exc.read().decode("utf-8", "replace")[:300] or f"HTTP {exc.code}"
    except Exception:
        return f"HTTP {exc.code}"
