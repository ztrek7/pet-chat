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

    Maps to the ``generation_failed`` reason. The caller must not try a second
    client, a second model, or Hermes' main model.
    """


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
    """True only on the exact verified target build with the resolver present."""
    if _hermes_version() != SUPPORTED_HERMES:
        return False
    try:
        from agent.auxiliary_client import resolve_provider_client  # noqa: F401
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


def _models_match(requested: str, resolved: Any) -> bool:
    """Confirm the resolver handed back the model we asked for.

    Providers legitimately decorate a slug (prefixing a namespace, appending a
    dated revision), so containment either way counts as the same model; an
    unrelated slug does not.
    """
    if not isinstance(resolved, str) or not resolved:
        return False
    a, b = requested.strip().lower(), resolved.strip().lower()
    return a == b or a in b or b in a


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

    try:
        response = client.chat.completions.create(
            model=resolved_model,
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_text},
            ],
            max_tokens=MAX_COMPLETION_TOKENS,
            temperature=0.8,
            stream=False,
            timeout=timeout,
        )
    except Exception as exc:
        # Every provider-family failure lands here — missing credentials, auth,
        # payment/capacity, model-not-found, rate limit, timeout, connection
        # error, cancellation. All of them stop. None of them escalate.
        raise AdapterFailed("selected provider/model call failed") from exc

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
