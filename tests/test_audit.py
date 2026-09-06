"""Regression checks: python3 -m unittest discover -s tests -v.

Uses PyYAML from Hermes. HTTP checks also use its FastAPI/httpx packages.
No provider calls or changes to the user's config.
"""
import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_smoke import _load


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.api = _load("pet_chat_audit_api", "dashboard/plugin_api.py")
        cls.ec = cls.api._load_sibling("exact_client")
        cls.inst = _load("pet_chat_audit_install", "scripts/install-desktop.py")

    def test_unscoped_custom_route_is_refused_before_resolution(self):
        self.assertFalse(self.api.pair_is_concrete("custom", "same-model"))
        with patch.object(self.ec, "is_supported") as probe:
            with self.assertRaises(self.ec.AdapterUnavailable):
                self.ec.resolve_exact("custom", "same-model")
            probe.assert_not_called()
        self.assertEqual(self.api.normalize_catalog([
            {"slug": "custom", "models": ["same-model"]}
        ]), [])

    def test_different_vendor_names_are_not_the_same_model(self):
        self.assertFalse(self.ec._models_match("vendor-a/model", "vendor-b/model"))

    def test_adapter_never_retries_a_failed_completion(self):
        from unittest.mock import Mock

        create = Mock(side_effect=TimeoutError("private provider detail"))
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
        with (
            patch.object(self.ec, "resolve_exact", return_value=(client, "model")),
            patch.object(self.ec, "_completion_kwargs", return_value={"model": "model"}),
            self.assertRaises(self.ec.AdapterFailed) as caught,
        ):
            self.ec.generate(provider="test", model="model", system_instruction="one line",
                             user_text="hello", timeout=30)
        self.assertEqual(caught.exception.reason, "generation_timeout")
        create.assert_called_once()
        for retries, accepted in ((0, True), (1, False), (None, False)):
            self.assertEqual(self.ec._retries_are_disabled(SimpleNamespace(max_retries=retries)), accepted)

    def test_unknown_hermes_version_fails_closed(self):
        self.assertEqual(self.ec.SUPPORTED_HERMES, {(0, 20), (0, 21)})
        for version in (None, (0, 19), (0, 22), (1, 0)):
            with patch.object(self.ec, "_hermes_version", return_value=version):
                self.assertFalse(self.ec.is_supported())

    def test_worker_imports_use_the_shared_lock(self):
        from concurrent.futures import ThreadPoolExecutor

        entered = threading.Event()

        def load():
            entered.set()
            return self.api._load_sibling("exact_client")

        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.api._PROCESS_LOCK:
                pending = pool.submit(load)
                self.assertTrue(entered.wait(1))
                self.assertFalse(pending.done())
            self.assertIs(pending.result(timeout=1), self.ec)

    def test_one_call_failure_and_full_prompt_secret_gate(self):
        quip = self.api._load_sibling("quip")
        quip._LIMITER.reset()
        args = dict(provider="test", model="model", attitude="snarky", timeout=30)
        with patch.object(self.ec, "generate") as generate:
            result = quip.generate_quip(prompt="a" * 500 + " password: test-secret", **args)
            self.assertEqual(result, ("sensitive_input", None))
            generate.assert_not_called()
            generate.side_effect = self.ec.AdapterFailed("private detail")
            self.assertEqual(quip.generate_quip(prompt="hello", **args), ("generation_failed", None))
            self.assertEqual(quip.generate_quip(prompt="again", **args), ("cooldown", None))
            generate.assert_called_once()
        quip._LIMITER.reset()

    def test_settings_refuse_unreadable_and_non_mapping_config(self):
        with patch.object(Path, "read_text", side_effect=PermissionError("private path")):
            with self.assertRaises((OSError, RuntimeError)):
                self.api._read_config()
        for text in ("- not-a-config\n", "42\n", "plugins: [\n"):
            with self.subTest(text=text), patch.object(Path, "read_text", return_value=text):
                with self.assertRaises(RuntimeError):
                    self.api._read_config()

    def test_settings_conflict_and_failed_write_are_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.yaml"
            path.write_text("unrelated: keep\n", encoding="utf-8")
            catalog = [{"provider": "test", "models": [{"id": "model"}]}]
            with (
                patch.object(self.api, "get_hermes_home", return_value=Path(tmp)),
                patch.object(self.api, "_catalog_rows", return_value=catalog),
                patch.object(self.api, "_classify_cost", return_value=None),
            ):
                body = dict(provider="test", model="model", attitude="snarky",
                            base_revision=self.api.settings_revision(self.api._read_config()))
                with patch.object(self.api, "_write_config", side_effect=OSError("private path")):
                    self.assertEqual(self.api.put_settings(body)[1]["error"], "settings_unwritable")
                self.assertEqual(path.read_text(), "unrelated: keep\n")
                self.assertEqual(self.api.put_settings(body)[0], 200)
                self.assertEqual(self.api._read_config()["unrelated"], "keep")
                self.assertEqual(self.api.put_settings(body)[0], 409)

    def test_install_failure_keeps_previous_artifact_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, target, receipt = root / "source", root / "target", root / "receipt.json"
            source.mkdir()
            (source / "plugin.js").write_text("// original\n")
            (source / "manifest.json").write_text(json.dumps({"source_commit": "set-by-build"}))
            self.inst.install_desktop(source, target, receipt, "a" * 40)
            original_receipt = receipt.read_bytes()
            original_write = self.inst._write_json_atomic

            def fail_receipt(path, value):
                if path == receipt:
                    raise OSError("write failed")
                return original_write(path, value)

            for failure in ("copytree", "receipt"):
                with self.subTest(failure=failure):
                    failing = (patch.object(self.inst.shutil, "copytree", side_effect=OSError("copy failed"))
                               if failure == "copytree" else
                               patch.object(self.inst, "_write_json_atomic", side_effect=fail_receipt))
                    with failing, self.assertRaises(self.inst.LifecycleError):
                        self.inst.install_desktop(source, target, receipt, "b" * 40)
                    self.assertEqual((target / "plugin.js").read_text(), "// original\n")
                    self.assertEqual(receipt.read_bytes(), original_receipt)
            self.inst.install_desktop(source, target, receipt, "b" * 40)
            self.assertEqual(list(root.glob("pet-chat-backup-*")), [])

    def test_quip_route_does_not_block_server_event_loop(self):
        if self.api.APIRouter is None:
            self.skipTest("FastAPI not installed; run in Hermes environment")
        entered, release = threading.Event(), threading.Event()

        def slow_quip(body):
            entered.set()
            release.wait(2)
            return 200, {"quip": "test double"}

        async def check():
            with patch.object(self.api, "post_quip", side_effect=slow_quip):
                request = SimpleNamespace(json=self._body)
                task = asyncio.create_task(self.api.post_quip_route(request))
                try:
                    for _ in range(100):
                        if entered.is_set():
                            break
                        await asyncio.sleep(0.005)
                    self.assertTrue(entered.is_set())
                    self.assertFalse(task.done(), "generation blocked the event loop")
                finally:
                    release.set()
                    await task

        asyncio.run(check())

    @staticmethod
    async def _body():
        return {"request_id": "test", "prompt": "hello"}


if __name__ == "__main__":
    unittest.main(verbosity=2)
