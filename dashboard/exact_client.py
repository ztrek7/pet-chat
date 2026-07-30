"""The one permitted private/dev generation path (spec v6 §8).

This module is deliberately the *only* place Pet Chat touches Hermes' provider
routing, so that the compatibility guard, the no-fallback proof, and the
retry proof all live at a single chokepoint that a future supported plugin API
can replace wholesale.

Banned here and in :mod:`quip`, permanently:

* ``call_llm`` — on Hermes v0.19.0 it can reach a main-model fallback even with
  an empty ``fallback_chain``;
* ``ctx.llm`` — same reachability, plus renderer-selected routing;
* the configured-fallback-chain resolver and any main-agent model client.

``resolve_provider_client`` is an *internal* Hermes function. Using it is what
makes this a private/dev compatibility build rather than a supported public
plugin: the adapter therefore accepts only the verified target version and
rejects every other build before any provider call.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Tuple

#: The single Hermes (major, minor) this adapter has been proven against.
#: Widening this is a preflight exercise (Gate E), not an edit.
SUPPORTED_HERMES: Tuple[int, int] = (0, 19)

#: Routing values that name a router rather than a concrete provider. Rejected
#: *before* resolution so a virtual name can never reach Hermes' auto chain.
VIRTUAL_ROUTING = frozenset({"", "auto", "main", "moa", "default", "none"})

#: Provider families excluded from the catalog because they failed the Gate E
#: failure matrix on the target build. Populated by live preflight (Slice 6);
#: empty means "nothing has been disproven yet", never "everything passed".
EXCLUDED_PROVIDERS: frozenset = frozenset()

#: One bounded completion. Not configurable by the renderer or by config.
MAX_COMPLETION_TOKENS = 64


class AdapterUnavailable(RuntimeError):
    """Generation cannot run at all: wrong build, no adapter, or no client.

    Maps to the ``generation_unavailable`` reason. Never a fallback quip.
    """


class AdapterFailed(RuntimeError):
    """The selected provider/model was reached and failed.

    The bounded ``reason`` is safe to display. The caller must not try a second
    client, a second model, or Hermes' main model.
    """

    def __init__(self, message: str, reason: str = "generation_failed") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ExactResult:
    """Proof-carrying result of one bounded call."""

    text: str
    provider: str
    model: str


def _hermes_version() -> Optional[Tuple[int, int]]:
    try:
        from hermes_cli.version import __version__ as raw  # type: ignore
    except Exception:
        try:
            from hermes_cli import __version__ as raw  # type: ignore
        except Exception:
            return None
    parts = str(raw).split(".")
    try:
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None


def is_supported() -> bool:
    """True only on the verified build with every required adapter helper."""
    if _hermes_version() != SUPPORTED_HERMES:
        return False
    try:
        from agent.auxiliary_client import (  # noqa: F401
            _build_call_kwargs,
            resolve_provider_client,
        )
        from agent.models_dev import PROVIDER_TO_MODELS_DEV, fetch_models_dev  # noqa: F401
    except Exception:
        return False
    return True


def is_concrete(provider: str, model: str) -> bool:
    return bool(
        provider
        and model
        and provider.lower() not in VIRTUAL_ROUTING
        and model.lower() not in VIRTUAL_ROUTING
    )


def _retries_are_disabled(client: Any) -> bool:
    """Prove the selected client will not silently re-issue our one call.

    Hermes' ``_create_openai_client`` already defaults auxiliary clients to
    zero retries, but Gate E requires proof rather than trust. A client that
    cannot expose the value is *not* treated as verified — it fails closed,
    which is the same outcome as excluding its provider family.
    """
    for candidate in (client, getattr(client, "_real_client", None)):
        if candidate is None:
            continue
        retries = getattr(candidate, "max_retries", None)
        if isinstance(retries, int):
            return retries == 0
    return False


def _normalize_model_id(model: str) -> str:
    """Strip + casefold; allow a single ``vendor/`` prefix, nothing else.

    Bidirectional substring matching is intentionally not used: ``gpt-4`` must
    not accept ``gpt-4o`` or ``gpt-4-turbo``.
    """
    value = model.strip().lower()
    if "/" in value:
        vendor, rest = value.split("/", 1)
        if vendor and rest and "/" not in rest:
            return rest
    return value


def _models_match(requested: str, resolved: Any) -> bool:
    """Confirm the resolver handed back the model we asked for."""
    if not isinstance(resolved, str) or not resolved.strip():
        return False
    return _normalize_model_id(requested) == _normalize_model_id(resolved)


def _failure_reason(exc: Any) -> str:
    """Map private provider failures to fixed, non-sensitive reason codes."""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 401:
        return "provider_auth_failed"
    if status == 404:
        return "model_unavailable"
    if (
        status == 408
        or isinstance(exc, TimeoutError)
        or "timeout" in type(exc).__name__.lower()
    ):
        return "generation_timeout"
    return "generation_failed"


def _lowest_reasoning_effort(provider: str, model: str) -> Optional[str]:
    """Return the model's lightest advertised effort, or no override."""
    try:
        from agent.models_dev import PROVIDER_TO_MODELS_DEV, fetch_models_dev

        provider_id = PROVIDER_TO_MODELS_DEV.get(provider.strip().lower(), provider)
        if provider_id == "anthropic" or "claude" in model.lower():
            return None
        models = fetch_models_dev().get(provider_id, {}).get("models", {})
        entry = next(
            (value for key, value in models.items() if key.lower() == model.lower()),
            None,
        )
        options = entry.get("reasoning_options", []) if isinstance(entry, dict) else []
        values = next(
            (item.get("values", []) for item in options if item.get("type") == "effort"),
            [],
        )
    except Exception:
        return None
    allowed = {str(value).lower() for value in values}
    order = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
    return next((value for value in order if value in allowed), None)


def resolve_exact(provider: str, model: str) -> Tuple[Any, str]:
    """Resolve exactly one concrete client for exactly this pair.

    Raises :class:`AdapterUnavailable` on every rejection. It never widens the
    request, never consults a fallback chain, and never returns a client for a
    provider/model other than the one asked for.
    """
    provider = (provider or "").strip()
    model = (model or "").strip()

    # Gate order matters: virtual routing is rejected *before* resolution, so
    # "auto" can never enter Hermes' auto-detection chain via this path.
    if not is_concrete(provider, model):
        raise AdapterUnavailable("routing is not a concrete provider/model pair")
    if provider.lower() in EXCLUDED_PROVIDERS:
        raise AdapterUnavailable("provider family excluded by preflight")
    if not is_supported():
        raise AdapterUnavailable("unsupported Hermes build")

    from agent.auxiliary_client import resolve_provider_client

    try:
        client, resolved_model = resolve_provider_client(provider=provider, model=model)
    except Exception as exc:  # resolution failure is never a fallback trigger
        raise AdapterUnavailable("provider client could not be resolved") from exc

    if client is None or resolved_model is None:
        raise AdapterUnavailable("no authenticated client for the selected pair")
    if not _models_match(model, resolved_model):
        raise AdapterUnavailable("resolver returned a different model than requested")
    if not _retries_are_disabled(client):
        raise AdapterUnavailable("selected client cannot prove retries are disabled")
    return client, resolved_model


def _completion_kwargs(
    *,
    provider: str,
    model: str,
    messages: list,
    timeout: float,
    base_url: str,
) -> dict:
    """Build one small request using Hermes' provider-specific wire rules."""
    from agent.auxiliary_client import _build_call_kwargs

    effort = _lowest_reasoning_effort(provider, model)
    if effort is None:
        reasoning_config = None
    elif effort == "none":
        reasoning_config = {"enabled": False}
    else:
        reasoning_config = {"enabled": True, "effort": effort}

    kwargs = _build_call_kwargs(
        provider,
        model,
        messages,
        temperature=0.8,
        max_tokens=MAX_COMPLETION_TOKENS,
        timeout=timeout,
        reasoning_config=reasoning_config,
        base_url=base_url,
        task="pet_chat",
    )
    return kwargs


def generate(
    *,
    provider: str,
    model: str,
    system_instruction: str,
    user_text: str,
    timeout: float,
) -> ExactResult:
    """Make exactly one bounded completion call against the selected pair.

    The system instruction is static and carries the attitude contract; user
    text travels only in the separate user message and is never interpolated
    into it. No tools, no streaming, no history, no second attempt.
    """
    client, resolved_model = resolve_exact(provider, model)
    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_text},
    ]
    try:
        kwargs = _completion_kwargs(
            provider=provider,
            model=resolved_model,
            messages=messages,
            timeout=timeout,
            base_url=str(getattr(client, "base_url", "") or ""),
        )
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        # Every provider-family failure lands here — missing credentials, auth,
        # payment/capacity, model-not-found, rate limit, timeout, connection
        # error, cancellation. All of them stop. None of them escalate.
        raise AdapterFailed(
            "selected provider/model call failed",
            reason=_failure_reason(exc),
        ) from exc

    return ExactResult(
        text=_extract_text(response),
        provider=provider,
        model=resolved_model,
    )


def _extract_text(response: Any) -> str:
    """Pull the single completion's text out, tolerating dict or object shapes."""
    try:
        choices = response["choices"] if isinstance(response, dict) else response.choices
        first = choices[0]
        message = first["message"] if isinstance(first, dict) else first.message
        content = message["content"] if isinstance(message, dict) else message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise AdapterFailed("malformed provider response") from exc
    if content is None:
        return ""
    if not isinstance(content, str):
        raise AdapterFailed("provider returned non-text content")
    return content
