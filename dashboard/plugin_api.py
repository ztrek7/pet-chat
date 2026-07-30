"""Pet Chat backend API.

Mounted at ``/api/plugins/pet-chat/`` by Hermes' dashboard plugin system.
Authentication is enforced by the host before any handler here runs, and the
host's runtime gate refuses requests while the plugin is disabled; "no
generation" in this module means "no model call", never "no auth".

Contract (spec v6 §5–§7):

* the **active profile's** config is the only source of truth for the saved
  provider/model pair — Desktop storage never routes spend;
* ``GET /status`` and ``GET /settings`` and ``PUT /settings`` never call a
  model;
* writes touch only the five Pet Chat-owned config paths, under an exclusive
  lock, with an opaque ``settings_revision`` compare-and-swap so a stale write
  is refused instead of clobbering;
* ``POST /quip`` fails closed on every gate it cannot satisfy.

Profile scoping is inherited, not reimplemented: Hermes points ``HERMES_HOME``
at the active profile directory, so ``$HERMES_HOME/config.yaml`` *is* the
active profile's config. Two profiles cannot see each other's pair because
they are two different files.

The generation adapter itself is Slice 3. Until ``exact_client.py`` exists
beside this file, the capability probe reports ``generation_available: false``
and ``/quip`` returns ``generation_unavailable`` rather than pretending to
work.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml

try:  # pragma: no cover - exercised only inside a full Hermes dashboard
    from fastapi import APIRouter, Request
    from fastapi.responses import JSONResponse
except Exception:  # Allows unit tests without dashboard dependencies.
    APIRouter = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

try:  # pragma: no cover - trivial fallback
    from hermes_constants import get_hermes_home
except ImportError:
    def get_hermes_home() -> Path:  # type: ignore[misc]
        value = (os.environ.get("HERMES_HOME") or "").strip()
        return Path(value) if value else Path.home() / ".hermes"


API_VERSION = 1
PLUGIN_ID = "pet-chat"
AUX_TASK_KEY = "pet_chat"

ATTITUDES: Tuple[str, ...] = ("snarky", "supportive", "dramatic", "minimal")
DEFAULT_ATTITUDE = "snarky"

#: Routing values that name a router rather than a concrete provider. None of
#: these may ever be saved or resolved (spec v6 §3.5).
VIRTUAL_ROUTING = frozenset({"", "auto", "main", "moa", "default", "none"})

MAX_REQUEST_ID_CHARS = 80
MAX_PROMPT_CHARS = 4000
COST_WARNING_TTL_SECONDS = 300

#: Bubble lifetime, and the window in which the renderer may still display a
#: response at all. Both are advisory values the renderer re-checks locally.
DISMISS_MS = 8000
MAX_RESPONSE_AGE_MS = 40000

DISCLOSURE = (
    "Quips send the submitted text to the selected provider; provider costs "
    "and provider-side behavior may apply."
)

#: Fixed, bounded copy for user-actionable failures (spec v6 §4.5.1). The
#: renderer may show these verbatim; raw exception text never leaves here.
USER_MESSAGES: Dict[str, str] = {
    "not_configured": "No Quip model is selected. Configure Pet Chat first.",
    "invalid_routing": "The selected provider/model is unavailable. Choose another Quip model.",
    "generation_unavailable": "Quips are unavailable on this Hermes version.",
    "generation_failed": "The selected provider/model failed. No fallback was used.",
    "generation_timeout": "The selected model took too long. No fallback was used.",
    "provider_auth_failed": "The selected provider needs authentication.",
    "model_unavailable": "The selected model is unavailable from this provider.",
    "invalid_output": "The selected model returned unusable output.",
    "sensitive_input": "I did not send that prompt because it may contain a secret.",
    "busy": "I am still working on the previous quip.",
    "cooldown": "Quip cooldown is active; try again shortly.",
    "backend_unreachable": "Pet Chat could not reach its backend.",
    "settings_conflict": "Pet Chat settings changed elsewhere. Refresh and try again.",
    "cost_check_unavailable": "I could not verify this model's cost. Nothing was saved.",
}

#: The exact config paths this plugin owns. Nothing outside this tuple is ever
#: written, and the settings revision is computed over exactly these values so
#: an unrelated concurrent config edit does not manufacture a false conflict.
OWNED_PATHS: Tuple[Tuple[str, ...], ...] = (
    ("auxiliary", AUX_TASK_KEY, "provider"),
    ("auxiliary", AUX_TASK_KEY, "model"),
    ("auxiliary", AUX_TASK_KEY, "fallback_chain"),
    ("auxiliary", AUX_TASK_KEY, "timeout"),
    ("plugins", "entries", PLUGIN_ID, "config", "attitude"),
)

_PROVIDER_PATH, _MODEL_PATH, _FALLBACK_PATH, _TIMEOUT_PATH, _ATTITUDE_PATH = OWNED_PATHS

DEFAULT_TIMEOUT_SECONDS = 30


class SettingsConflict(RuntimeError):
    """A ``base_revision`` no longer matches the stored Pet Chat settings."""


# ---------------------------------------------------------------------------
# Config plumbing — narrow, atomic, active-profile scoped
# ---------------------------------------------------------------------------

def config_path() -> Path:
    return get_hermes_home() / "config.yaml"


def _lock_path() -> Path:
    return get_hermes_home() / ".pet-chat-settings.lock"


def _read_config() -> Dict[str, Any]:
    """Read the active profile's raw config.

    Reads the file directly rather than through ``hermes_cli.config``'s
    mtime-keyed cache: a compare-and-swap is only sound against the bytes that
    are actually on disk right now.
    """
    path = config_path()
    try:
        text = path.read_text(encoding="utf-8")
    except (FileNotFoundError, NotADirectoryError):
        return {}
    except OSError:
        return {}
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        # A config we cannot parse is one we must not rewrite.
        raise RuntimeError("active profile config.yaml is not valid YAML")
    return loaded if isinstance(loaded, dict) else {}


def _write_config(data: Dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".config.yaml.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            yaml.safe_dump(data, handle, sort_keys=False, default_flow_style=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


@contextmanager
def _settings_lock():
    """Serialize the read/verify/merge/write transaction across processes."""
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            # No advisory locking available: the in-process lock below still
            # serializes this process, and the revision CAS still refuses a
            # write that raced with another writer.
            pass
        with _PROCESS_LOCK:
            yield
    finally:
        handle.close()


_PROCESS_LOCK = threading.RLock()


def _get_path(data: Any, path: Sequence[str]) -> Any:
    node = data
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _set_path(data: Dict[str, Any], path: Sequence[str], value: Any) -> None:
    node = data
    for key in path[:-1]:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[path[-1]] = value


def _owned_snapshot(config: Dict[str, Any]) -> List[Any]:
    return [_get_path(config, path) for path in OWNED_PATHS]


def settings_revision(config: Dict[str, Any]) -> str:
    """Opaque revision over the Pet Chat-owned subtree only.

    Scoping the revision to owned paths means a concurrent unrelated config
    edit does not invalidate a user's in-flight save, while any competing
    write to Pet Chat's own settings does.
    """
    canonical = json.dumps(_owned_snapshot(config), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _saved_pair(config: Dict[str, Any]) -> Tuple[str, str]:
    provider = _get_path(config, _PROVIDER_PATH)
    model = _get_path(config, _MODEL_PATH)
    provider = provider.strip() if isinstance(provider, str) else ""
    model = model.strip() if isinstance(model, str) else ""
    return provider, model


def _saved_attitude(config: Dict[str, Any]) -> str:
    attitude = _get_path(config, _ATTITUDE_PATH)
    if isinstance(attitude, str) and attitude in ATTITUDES:
        return attitude
    return DEFAULT_ATTITUDE


def _saved_timeout(config: Dict[str, Any]) -> float:
    """Use one fixed request budget so saved pre-fix values cannot shorten it."""
    return float(DEFAULT_TIMEOUT_SECONDS)


def pair_is_concrete(provider: str, model: str) -> bool:
    """True only for a complete, non-virtual provider/model pair."""
    return bool(
        provider
        and model
        and provider.lower() not in VIRTUAL_ROUTING
        and model.lower() not in VIRTUAL_ROUTING
    )


# ---------------------------------------------------------------------------
# Provider/model catalog — safe display rows only, never generative
# ---------------------------------------------------------------------------

def _catalog_rows(refresh: bool = False) -> Optional[List[Dict[str, Any]]]:
    """Return safe provider/model display rows, or ``None`` if unavailable.

    Uses Hermes' authenticated-provider inventory, which reads curated model
    lists and cached provider catalogs. It resolves no client and makes no
    completion call. Only slug/label/model-id strings cross this boundary: no
    key, endpoint, base URL, or raw config row is exposed.
    """
    try:
        from hermes_cli.model_switch import list_authenticated_providers
    except Exception:
        return None
    try:
        providers = list_authenticated_providers(
            for_picker=True,
            refresh=refresh,
            probe_custom_providers=False,
            excluded_providers=["moa"],
        )
    except Exception:
        return None
    return normalize_catalog(providers)


def _excluded_providers() -> frozenset:
    try:
        return frozenset(_load_sibling("exact_client").EXCLUDED_PROVIDERS)
    except Exception:
        return frozenset()


def _model_outputs_text(provider: str, model: str) -> bool:
    """Keep unknown models, but hide models known to produce no text."""
    try:
        from agent.models_dev import get_model_info

        info = get_model_info(provider, model)
    except Exception:
        return True
    return info is None or not info.output_modalities or "text" in info.output_modalities


def normalize_catalog(providers: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    """Reduce Hermes provider rows to the safe subset the picker needs."""
    rows: List[Dict[str, Any]] = []
    for entry in providers or []:
        if not isinstance(entry, dict):
            continue
        slug = entry.get("slug")
        if not isinstance(slug, str):
            continue
        slug = slug.strip()
        if not slug or slug.lower() in VIRTUAL_ROUTING:
            continue
        if slug.lower() in _excluded_providers():
            # Failed the Gate E no-fallback matrix on this build; it must not
            # be selectable, not merely fail later.
            continue
        models: List[Dict[str, str]] = []
        seen: set = set()
        for model in entry.get("models") or []:
            if not isinstance(model, str):
                continue
            model = model.strip()
            if not model or model.lower() in VIRTUAL_ROUTING or model in seen:
                continue
            if not _model_outputs_text(slug, model):
                continue
            seen.add(model)
            models.append({"id": model, "label": model})
        if not models:
            continue
        label = entry.get("name")
        rows.append({
            "provider": slug,
            "label": label.strip() if isinstance(label, str) and label.strip() else slug,
            "models": models,
        })
    rows.sort(key=lambda row: row["provider"])
    return rows


def catalog_contains(catalog: Optional[Sequence[Dict[str, Any]]], provider: str, model: str) -> bool:
    for row in catalog or []:
        if row.get("provider") != provider:
            continue
        return any(entry.get("id") == model for entry in row.get("models") or [])
    return False


# ---------------------------------------------------------------------------
# Capability probe and readiness state
# ---------------------------------------------------------------------------

def _load_sibling(name: str):
    """Import a sibling module by path.

    The dashboard loads ``plugin_api.py`` as a standalone module, not as part
    of a package, so ``from . import quip`` is unavailable at runtime.
    """
    import importlib.util
    import sys

    cached = sys.modules.get(f"pet_chat_{name}")
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parent / f"{name}.py"
    if not path.is_file():
        raise ImportError(name)
    spec = importlib.util.spec_from_file_location(f"pet_chat_{name}", path)
    if spec is None or spec.loader is None:
        raise ImportError(name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"pet_chat_{name}"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(f"pet_chat_{name}", None)
        raise
    return module


def generation_available() -> bool:
    """True only when the verified target build *and* the adapter are present.

    The build-compatibility check lives in ``exact_client`` alone (spec v6 §8:
    "Hermes version compatibility is checked in one place"), so this delegates
    rather than re-deriving it. Deliberately independent of whether the user
    has configured a pair: an unconfigured profile on a good build reports
    ``generation_available: true``.
    """
    try:
        return bool(_load_sibling("exact_client").is_supported())
    except Exception:
        return False


def readiness_state(
    *,
    pair_saved: bool,
    pair_in_catalog: bool,
    available: bool,
) -> str:
    """Collapse readiness into the four renderer-visible states.

    Capability is checked first: on a build where generation cannot run,
    "Quips are unavailable on this Hermes version" is the truthful message
    even for a profile that also has no pair saved.
    """
    if not available:
        return "generation_unavailable"
    if not pair_saved:
        return "not_configured"
    if not pair_in_catalog:
        return "invalid_routing"
    return "ready"


def _readiness(config: Dict[str, Any], catalog: Optional[Sequence[Dict[str, Any]]]) -> Dict[str, Any]:
    provider, model = _saved_pair(config)
    pair_saved = pair_is_concrete(provider, model)
    # An unavailable catalog must not silently demote a saved pair to
    # "invalid": it is unknown, not wrong. Treat it as in-catalog and let the
    # generation path fail closed if the pair really is gone.
    pair_in_catalog = (
        pair_saved and (catalog is None or catalog_contains(catalog, provider, model))
    )
    available = generation_available()
    return {
        "pair_saved": pair_saved,
        "pair_in_catalog": bool(pair_in_catalog),
        "generation_available": available,
        "state": readiness_state(
            pair_saved=pair_saved,
            pair_in_catalog=bool(pair_in_catalog),
            available=available,
        ),
    }


# ---------------------------------------------------------------------------
# Cost warnings — bound to an exact pair, single use, expiring
# ---------------------------------------------------------------------------

_PENDING_WARNINGS: Dict[str, Dict[str, Any]] = {}
_WARNINGS_LOCK = threading.Lock()


class CostCheckUnavailable(RuntimeError):
    """Hermes' cost classifier could not answer; nothing may be saved."""


def _classify_cost(provider: str, model: str) -> Optional[str]:
    """Ask Hermes' real cost guard about a pair.

    Returns ``None`` when the guard says the pair is under threshold, the
    guard's own message when it is over, and raises
    :class:`CostCheckUnavailable` when the guard is missing or fails — in
    which case the caller writes nothing (spec v6 §6, ``PUT /settings`` rule 4).
    """
    try:
        from hermes_cli.model_cost_guard import expensive_model_warning
    except Exception as exc:
        raise CostCheckUnavailable("cost guard unavailable") from exc
    try:
        warning = expensive_model_warning(model, provider=provider)
    except Exception as exc:
        raise CostCheckUnavailable("cost guard failed") from exc
    if warning is None:
        return None
    return getattr(warning, "message", "") or ""


def _cost_warning(provider: str, model: str) -> Optional[Dict[str, Any]]:
    """Mint a single-use, expiring confirmation bound to this exact pair."""
    message = _classify_cost(provider, model)
    if message is None:
        return None
    warning_id = secrets.token_urlsafe(16)
    record = {
        "warning_id": warning_id,
        "provider": provider,
        "model": model,
        "message": message,
        "expires_at": time.time() + COST_WARNING_TTL_SECONDS,
    }
    with _WARNINGS_LOCK:
        _prune_warnings_locked()
        _PENDING_WARNINGS[warning_id] = record
    return {
        "warning_id": warning_id,
        "provider": provider,
        "model": model,
        "message": record["message"],
        "expires_in_seconds": COST_WARNING_TTL_SECONDS,
    }


def _prune_warnings_locked() -> None:
    now = time.time()
    for key in [k for k, v in _PENDING_WARNINGS.items() if v["expires_at"] <= now]:
        _PENDING_WARNINGS.pop(key, None)


def _consume_warning(warning_id: Any, provider: str, model: str) -> bool:
    """Redeem a warning id bound to exactly this pair. Single use."""
    if not isinstance(warning_id, str) or not warning_id:
        return False
    with _WARNINGS_LOCK:
        _prune_warnings_locked()
        record = _PENDING_WARNINGS.get(warning_id)
        if record is None:
            return False
        if record["provider"] != provider or record["model"] != model:
            return False
        _PENDING_WARNINGS.pop(warning_id, None)
        return True


# ---------------------------------------------------------------------------
# Handlers — pure functions returning (http_status, payload)
# ---------------------------------------------------------------------------

def _error(code: str, status: int = 400, **extra: Any) -> Tuple[int, Dict[str, Any]]:
    payload: Dict[str, Any] = {"error": code}
    if code in USER_MESSAGES:
        payload["user_message"] = USER_MESSAGES[code]
    payload.update(extra)
    return status, payload


def status_payload() -> Tuple[int, Dict[str, Any]]:
    config = _read_config()
    readiness = _readiness(config, _catalog_rows())
    return 200, {
        "api_version": API_VERSION,
        "plugin": PLUGIN_ID,
        "route_ready": True,
        "task_registered": True,
        **readiness,
    }


def get_settings_payload(refresh: bool = False) -> Tuple[int, Dict[str, Any]]:
    config = _read_config()
    catalog = _catalog_rows(refresh=refresh)
    readiness = _readiness(config, catalog)
    provider, model = _saved_pair(config)
    pair = (
        {"provider": provider, "model": model} if readiness["pair_saved"] else None
    )
    return 200, {
        "api_version": API_VERSION,
        "plugin": PLUGIN_ID,
        "pair": pair,
        "attitude": _saved_attitude(config),
        "attitudes": list(ATTITUDES),
        "catalog": catalog or [],
        "catalog_available": catalog is not None,
        "disclosure": DISCLOSURE,
        "settings_revision": settings_revision(config),
        **readiness,
    }


def put_settings(body: Any) -> Tuple[int, Dict[str, Any]]:
    """Validate, cost-check, and atomically merge the Pet Chat-owned settings.

    Never calls a model. Writes nothing on any rejection path.
    """
    if not isinstance(body, dict):
        return _error("invalid_body")
    allowed = {"provider", "model", "attitude", "base_revision", "confirmation"}
    unknown = sorted(set(body) - allowed)
    if unknown:
        return _error("invalid_body", unknown_fields=unknown)

    provider = body.get("provider")
    model = body.get("model")
    attitude = body.get("attitude", DEFAULT_ATTITUDE)
    base_revision = body.get("base_revision")

    if not isinstance(provider, str) or not isinstance(model, str):
        return _error("invalid_body")
    provider = provider.strip()
    model = model.strip()
    if len(provider) > 120 or len(model) > 200:
        return _error("invalid_body")
    if not isinstance(attitude, str) or attitude not in ATTITUDES:
        return _error("invalid_attitude")
    if not isinstance(base_revision, str) or not base_revision:
        return _error("invalid_body")

    if not pair_is_concrete(provider, model):
        return _error("invalid_routing")

    catalog = _catalog_rows()
    if catalog is None:
        # Without a catalog we cannot prove the pair is real, and saving an
        # unverifiable spend target is exactly what §3 forbids.
        return _error("invalid_routing")
    if not catalog_contains(catalog, provider, model):
        return _error("invalid_routing")

    try:
        warning = _cost_warning(provider, model)
    except CostCheckUnavailable:
        return _error("cost_check_unavailable", status=503)
    if warning is not None:
        confirmation = body.get("confirmation")
        confirmed = isinstance(confirmation, dict) and _consume_warning(
            confirmation.get("warning_id"), provider, model
        )
        if not confirmed:
            return 409, {"error": "confirmation_required", "cost_warning": warning}

    try:
        with _settings_lock():
            config = _read_config()
            if settings_revision(config) != base_revision:
                raise SettingsConflict()
            _set_path(config, _PROVIDER_PATH, provider)
            _set_path(config, _MODEL_PATH, model)
            _set_path(config, _FALLBACK_PATH, [])
            _set_path(config, _TIMEOUT_PATH, DEFAULT_TIMEOUT_SECONDS)
            _set_path(config, _ATTITUDE_PATH, attitude)
            _write_config(config)
    except SettingsConflict:
        return _error("settings_conflict", status=409)
    except RuntimeError:
        return _error("settings_unwritable", status=500)

    # Re-read from disk so the response reflects what was actually persisted.
    return get_settings_payload()


def post_quip(body: Any) -> Tuple[int, Dict[str, Any]]:
    """Generation entry point.

    Gates 1–5 of spec v6 §7 run here; gates 6–10 (secret scan, excerpt,
    busy/cooldown, the single bounded call, output bounds) run in ``quip``.
    Every rejection path is proven to make zero model calls.
    """
    if not isinstance(body, dict):
        return _error("invalid_body")
    unknown = sorted(set(body) - {"request_id", "prompt"})
    if unknown:
        return _error("invalid_body", unknown_fields=unknown)

    request_id = body.get("request_id")
    prompt = body.get("prompt")
    if not isinstance(request_id, str) or not isinstance(prompt, str):
        return _error("invalid_body")
    request_id = request_id.strip()
    if not (1 <= len(request_id) <= MAX_REQUEST_ID_CHARS):
        return _error("invalid_body")
    if not request_id.isprintable():
        return _error("invalid_body")
    if len(prompt) > MAX_PROMPT_CHARS:
        return _error("invalid_body")

    if not prompt.strip():
        return _no_quip(request_id, "empty")

    config = _read_config()
    catalog = _catalog_rows()
    state = _readiness(config, catalog)["state"]
    if state != "ready":
        return _no_quip(request_id, state)

    provider, model = _saved_pair(config)
    try:
        quip_module = _load_sibling("quip")
    except Exception:
        return _no_quip(request_id, "generation_unavailable")

    reason, quip = quip_module.generate_quip(
        prompt=prompt,
        provider=provider,
        model=model,
        attitude=_saved_attitude(config),
        timeout=_saved_timeout(config),
    )
    if reason != "ok" or not quip:
        return _no_quip(request_id, reason)

    return 200, {
        "request_id": request_id,
        "quip": quip,
        "attitude": _saved_attitude(config),
        "dismiss_ms": DISMISS_MS,
        "max_response_age_ms": MAX_RESPONSE_AGE_MS,
    }


def _no_quip(request_id: str, reason: str) -> Tuple[int, Dict[str, Any]]:
    """Uniform no-quip envelope: opaque id, null quip, one bounded reason."""
    payload: Dict[str, Any] = {"request_id": request_id, "quip": None, "reason": reason}
    if reason in USER_MESSAGES:
        payload["user_message"] = USER_MESSAGES[reason]
    return 200, payload


# ---------------------------------------------------------------------------
# FastAPI wiring
# ---------------------------------------------------------------------------

if APIRouter is not None:  # pragma: no cover - requires the dashboard runtime
    router = APIRouter()

    def _respond(result: Tuple[int, Dict[str, Any]]):
        status, payload = result
        return JSONResponse(status_code=status, content=payload)

    async def _json_body(request: "Request") -> Any:
        try:
            return await request.json()
        except Exception:
            return None

    @router.get("/status")
    async def get_status():
        return _respond(status_payload())

    @router.get("/settings")
    async def get_settings(refresh: bool = False):
        return _respond(get_settings_payload(refresh=refresh))

    @router.put("/settings")
    async def put_settings_route(request: "Request"):
        return _respond(put_settings(await _json_body(request)))

    @router.post("/quip")
    async def post_quip_route(request: "Request"):
        return _respond(post_quip(await _json_body(request)))
