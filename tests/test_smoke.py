#!/usr/bin/env python3
"""Minimal runnable checks — stdlib only, no Hermes install required.

    python3 tests/test_smoke.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    path = ROOT / rel
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class ModelMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ec = _load("pet_chat_exact_client_test", "dashboard/exact_client.py")

    def test_exact_match(self):
        self.assertTrue(self.ec._models_match("gpt-4o", "gpt-4o"))
        self.assertTrue(self.ec._models_match(" GPT-4o ", "gpt-4o"))

    def test_rejects_substring_cousins(self):
        # The bug: bidirectional `in` treated these as the same model.
        for requested, resolved in (
            ("gpt-4", "gpt-4o"),
            ("gpt-4", "gpt-4-turbo"),
            ("gpt-4o", "gpt-4"),
            ("o1", "o1-pro"),
            ("claude-3", "claude-3-5-sonnet"),
        ):
            with self.subTest(requested=requested, resolved=resolved):
                self.assertFalse(self.ec._models_match(requested, resolved))

    def test_vendor_prefix_only(self):
        self.assertTrue(self.ec._models_match("openai/gpt-4o", "gpt-4o"))
        self.assertTrue(self.ec._models_match("gpt-4o", "openai/gpt-4o"))
        self.assertFalse(self.ec._models_match("openai/gpt-4", "gpt-4o"))

    def test_rejects_non_string(self):
        self.assertFalse(self.ec._models_match("gpt-4o", None))
        self.assertFalse(self.ec._models_match("gpt-4o", 12))
        self.assertFalse(self.ec._models_match("gpt-4o", ""))

    def test_provider_failures_are_safely_classified(self):
        self.assertEqual(self.ec._failure_reason(TimeoutError("private")), "generation_timeout")
        self.assertEqual(
            self.ec._failure_reason(SimpleNamespace(status_code=401)), "provider_auth_failed"
        )
        self.assertEqual(
            self.ec._failure_reason(SimpleNamespace(status_code=403)), "generation_failed"
        )
        self.assertEqual(
            self.ec._failure_reason(SimpleNamespace(status_code=404)), "model_unavailable"
        )
        self.assertEqual(
            self.ec._failure_reason(SimpleNamespace(status_code=500)), "generation_failed"
        )

    def test_builds_lightweight_provider_aware_request(self):
        calls = {}
        agent = ModuleType("agent")
        agent.__path__ = []
        auxiliary = ModuleType("agent.auxiliary_client")
        models_dev = ModuleType("agent.models_dev")

        def build(provider, model, messages, **kwargs):
            calls.update(provider=provider, model=model, messages=messages, **kwargs)
            return {"model": model, "messages": messages, "timeout": kwargs["timeout"]}

        setattr(auxiliary, "_build_call_kwargs", build)
        setattr(
            auxiliary,
            "auxiliary_max_tokens_param",
            lambda value, model=None: {"max_completion_tokens": value},
        )
        setattr(
            models_dev,
            "PROVIDER_TO_MODELS_DEV",
            {"example": "vendor", "anthropic": "anthropic"},
        )
        setattr(
            models_dev,
            "fetch_models_dev",
            lambda: {
                "vendor": {
                    "models": {
                        "reasoner": {
                            "reasoning_options": [
                                {"type": "effort", "values": ["low", "medium", "high"]}
                            ]
                        },
                        "pro": {
                            "reasoning_options": [
                                {"type": "effort", "values": ["medium", "high"]}
                            ]
                        },
                        "none-model": {
                            "reasoning_options": [
                                {"type": "effort", "values": ["none", "low"]}
                            ]
                        },
                        "fast-model": {},
                    }
                },
                "anthropic": {
                    "models": {
                        "claude-opus": {
                            "reasoning_options": [
                                {"type": "effort", "values": ["low", "medium", "high"]}
                            ]
                        }
                    }
                },
            },
        )
        modules = {
            "agent": agent,
            "agent.auxiliary_client": auxiliary,
            "agent.models_dev": models_dev,
        }
        messages = [{"role": "user", "content": "hi"}]

        with patch.dict(sys.modules, modules):
            kwargs = self.ec._completion_kwargs(
                provider="example",
                model="reasoner",
                messages=messages,
                timeout=30,
                base_url="https://example.test/v1",
            )
        self.assertEqual(calls["reasoning_config"], {"enabled": True, "effort": "low"})
        self.assertEqual(calls["temperature"], 0.8)
        self.assertEqual(calls["max_tokens"], self.ec.MAX_COMPLETION_TOKENS)
        self.assertNotIn("max_tokens", kwargs)
        self.assertNotIn("max_completion_tokens", kwargs)
        self.assertEqual(kwargs["messages"], messages)

        calls.clear()
        with patch.dict(sys.modules, modules):
            self.ec._completion_kwargs(
                provider="example",
                model="pro",
                messages=messages,
                timeout=30,
                base_url="https://example.test/v1",
            )
        self.assertEqual(calls["reasoning_config"], {"enabled": True, "effort": "medium"})

        calls.clear()
        with patch.dict(sys.modules, modules):
            self.ec._completion_kwargs(
                provider="example",
                model="none-model",
                messages=messages,
                timeout=30,
                base_url="https://example.test/v1",
            )
        self.assertEqual(calls["reasoning_config"], {"enabled": False})

        calls.clear()
        with patch.dict(sys.modules, modules):
            self.ec._completion_kwargs(
                provider="example",
                model="fast-model",
                messages=messages,
                timeout=30,
                base_url="https://example.test/v1",
            )
        self.assertIsNone(calls["reasoning_config"])

        calls.clear()
        with patch.dict(sys.modules, modules):
            self.ec._completion_kwargs(
                provider="example",
                model="brand-new-model",
                messages=messages,
                timeout=30,
                base_url="https://example.test/v1",
            )
        self.assertIsNone(calls["reasoning_config"])

        calls.clear()
        with patch.dict(sys.modules, modules):
            self.ec._completion_kwargs(
                provider="anthropic",
                model="claude-opus",
                messages=messages,
                timeout=30,
                base_url="https://api.anthropic.com",
            )
        self.assertIsNone(calls["reasoning_config"])

    def test_request_builder_failures_are_sanitized(self):
        with (
            patch.object(
                self.ec,
                "resolve_exact",
                return_value=(SimpleNamespace(base_url="https://private.invalid"), "grok-4.5"),
            ),
            patch.object(
                self.ec,
                "_completion_kwargs",
                side_effect=RuntimeError("private provider detail"),
            ),
        ):
            with self.assertRaises(self.ec.AdapterFailed) as caught:
                self.ec.generate(
                    provider="xai-oauth",
                    model="grok-4.5",
                    system_instruction="one line",
                    user_text="hello",
                    timeout=30,
                )
        self.assertEqual(caught.exception.reason, "generation_failed")
        self.assertNotIn("private provider detail", str(caught.exception))


class QuipGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.quip = _load("pet_chat_quip_test", "dashboard/quip.py")

    def test_secret_scan_hits_common_shapes(self):
        self.assertTrue(self.quip.contains_secret("sk-abc123456789"))
        self.assertTrue(self.quip.contains_secret("password: hunter2password"))
        self.assertFalse(self.quip.contains_secret("normal prompt about skates"))

    def test_normalize_output_bounds(self):
        self.assertEqual(self.quip.normalize_output('  "hello there"  '), "hello there")
        self.assertIsNone(self.quip.normalize_output(""))
        self.assertIsNone(self.quip.normalize_output("ok\x00bad"))
        long = "a" * 500
        self.assertEqual(len(self.quip.normalize_output(long)), self.quip.MAX_QUIP_CHARS)

    def test_attitude_prompts_stay_lightweight(self):
        for attitude in self.quip.ATTITUDES:
            instruction = self.quip.system_instruction(attitude)
            with self.subTest(attitude=attitude):
                self.assertLessEqual(len(instruction), 320)
                self.assertIn("never the person", instruction.lower())
                self.assertIn("distressed", instruction.lower())


class TimeoutBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = _load("pet_chat_plugin_api_test", "dashboard/plugin_api.py")
        cls.desktop = (ROOT / "desktop/plugin.js").read_text(encoding="utf-8")

    def test_reasoning_models_get_one_aligned_request_budget(self):
        self.assertEqual(self.api.DEFAULT_TIMEOUT_SECONDS, 30)
        self.assertEqual(self.api.MAX_RESPONSE_AGE_MS, 40000)
        self.assertIn("const REQUEST_TIMEOUT_MS = 35000", self.desktop)
        self.assertIn("const DEFAULT_MAX_RESPONSE_AGE_MS = 40000", self.desktop)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = _load("pet_chat_plugin_api_catalog_test", "dashboard/plugin_api.py")

    def test_picker_excludes_known_non_text_models(self):
        providers = [{"slug": "xai-oauth", "models": ["grok-4.5", "grok-image"]}]
        with patch.object(
            self.api,
            "_model_outputs_text",
            side_effect=lambda provider, model: model == "grok-4.5",
            create=True,
        ):
            catalog = self.api.normalize_catalog(providers)
        self.assertEqual(catalog[0]["models"], [{"id": "grok-4.5", "label": "grok-4.5"}])


class DesktopInstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inst = _load("pet_chat_install_test", "scripts/install-desktop.py")

    def test_refuses_unknown_target_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            td = Path(tmp)
            src = td / "src"
            src.mkdir()
            (src / "plugin.js").write_text("//hi\n", encoding="utf-8")
            (src / "manifest.json").write_text(
                json.dumps(
                    {"id": "pet-chat", "source_commit": "set-by-build", "entry": "plugin.js"}
                ),
                encoding="utf-8",
            )
            target = td / "desktop-plugins" / "pet-chat"
            receipt = td / "receipt.json"

            self.inst.install_desktop(src, target, receipt, "abc123deadbeef")
            self.assertTrue(target.is_dir())
            self.assertEqual(
                json.loads((target / "manifest.json").read_text(encoding="utf-8"))[
                    "source_commit"
                ],
                "abc123deadbeef",
            )

            (target / "plugin.js").write_text("//tampered\n", encoding="utf-8")
            with self.assertRaises(self.inst.LifecycleError):
                self.inst.uninstall_desktop(target, receipt)

            (target / "plugin.js").write_text("//hi\n", encoding="utf-8")
            self.inst.uninstall_desktop(target, receipt)
            self.assertFalse(target.exists())
            self.assertFalse(receipt.exists())

            orphan = td / "desktop-plugins" / "pet-chat"
            orphan.mkdir(parents=True)
            (orphan / "x").write_text("nope", encoding="utf-8")
            with self.assertRaises(self.inst.LifecycleError):
                self.inst.install_desktop(src, orphan, receipt, "abc123deadbeef")


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=2))
