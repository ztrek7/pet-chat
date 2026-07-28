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
