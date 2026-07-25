"""Pet Chat Hermes plugin registration.

Slice 2 owns the backend source of truth: exactly one ``pet_chat`` auxiliary
task whose routing starts empty, plus the settings/readiness API in
``dashboard/plugin_api.py``.

Registration deliberately performs no model call, resolves no provider, and
writes no configuration. Installing and enabling the plugin must never select
a provider/model pair on the user's behalf (spec v6 §3.1–3.2).
"""
from __future__ import annotations

from typing import Any, Dict

PLUGIN_ID = "pet-chat"
PLUGIN_VERSION = "0.1.0-dev"

#: Config key for the plugin-owned auxiliary task: ``auxiliary.pet_chat.*``.
AUX_TASK_KEY = "pet_chat"

#: Routing starts empty, not ``auto``. An empty pair is the "unconfigured"
#: state that ``/status`` reports and that ``/quip`` fails closed on. An
#: empty ``fallback_chain`` records the no-fallback contract in config; the
#: generation path (Slice 3) never consults a fallback chain at all.
AUX_TASK_DEFAULTS: Dict[str, Any] = {
    "provider": "",
    "model": "",
    "fallback_chain": [],
    "timeout": 8,
}


def register(ctx) -> None:
    """Register the single Pet Chat auxiliary task.

    ``ctx`` is Hermes' ``PluginContext``. Nothing else is registered here:
    Pet Chat contributes no tools, hooks, middleware, or CLI commands to the
    agent, and its HTTP routes are mounted by the dashboard plugin system
    from ``dashboard/manifest.json``.
    """
    ctx.register_auxiliary_task(
        key=AUX_TASK_KEY,
        display_name="Pet Chat quip",
        description="Desktop pet quip generation (exact provider/model, no fallback)",
        defaults=dict(AUX_TASK_DEFAULTS),
    )
