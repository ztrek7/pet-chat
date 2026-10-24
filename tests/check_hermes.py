"""Offline integration check against a real Hermes source checkout.

Run with Hermes' Python dependencies:
    python tests/check_hermes.py /path/to/hermes-agent

Uses temporary profile config, a fake API key, and an in-memory HTTP transport.
All real socket connections are forbidden; no installed profile is loaded.
"""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


def load_api():
    path = Path(__file__).resolve().parents[1] / "dashboard/plugin_api.py"
    spec = importlib.util.spec_from_file_location("pet_chat_integration_api", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class HermesIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import httpx
        import hermes_yaml
        from agent import auxiliary_client
        from fastapi import FastAPI
        from hermes_cli.version_info import get_version_info

        cls.httpx = httpx
        cls.aux = auxiliary_client
        cls.api = load_api()
        cls.ec = cls.api._load_sibling("exact_client")
        cls.quip = cls.api._load_sibling("quip")
        cls.app = FastAPI()
        cls.app.include_router(cls.api.router, prefix="/api/plugins/pet-chat")
        assert cls.api.yaml is hermes_yaml
        print("Hermes source version:", get_version_info().base_version)

    def setUp(self):
        self.quip._LIMITER.reset()
        self.requests = []
        self.status = 200
        self.client_patch = patch.object(
            self.aux, "_openai_http_client_kwargs",
            side_effect=lambda *args, **kwargs: {
                "http_client": self.httpx.Client(transport=self.httpx.MockTransport(self.respond))
            },
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def respond(self, request):
        self.requests.append(request)
        self.assertEqual(str(request.url), "https://pet-chat.invalid/v1/chat/completions")
        if self.status != 200:
            return self.httpx.Response(self.status, json={"error": {"message": "fixture failure"}})
        return self.httpx.Response(200, json={
            "id": "fixture", "object": "chat.completion", "created": 0,
            "model": "fixture-model", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": "Ambitious for a Tuesday."}}],
        })

    def test_version_and_host_manifest_gate(self):
        from hermes_cli.plugins_manifest import requires_hermes_error
        self.assertTrue(self.ec.is_supported())
        manifest = self.api.yaml.safe_load(
            (Path(__file__).resolve().parents[1] / "plugin.yaml").read_text()
        )
        self.assertTrue(manifest.get("requires_hermes"))
        self.assertIsNone(requires_hermes_error(manifest))
        with patch("hermes_cli.plugins_manifest.running_hermes_version", return_value="0.23.0"):
            self.assertIsNotNone(requires_hermes_error(manifest))

    def test_settings_to_quip_through_real_host_helpers(self):
        async def check():
            async with self.httpx.AsyncClient(
                transport=self.httpx.ASGITransport(app=self.app), base_url="http://test"
            ) as client:
                base = "/api/plugins/pet-chat"
                settings = (await client.get(base + "/settings")).json()
                self.assertTrue(settings["generation_available"])
                self.assertTrue(self.api.catalog_contains(settings["catalog"], "custom:pet-fixture", "fixture-model"), settings)
                response = await client.put(base + "/settings", json={
                    "provider": "custom:pet-fixture", "model": "fixture-model",
                    "attitude": "snarky", "base_revision": settings["settings_revision"],
                })
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["state"], "ready")
                self.assertEqual(self.requests, [])
                response = await client.post(base + "/quip", json={
                    "request_id": "integration", "prompt": "Organize the stars alphabetically.",
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json().get("quip"), "Ambitious for a Tuesday.", response.text)
                self.assertEqual(len(self.requests), 1)
                wire = json.loads(self.requests[0].content)
                self.assertEqual(wire["model"], "fixture-model")
                self.assertEqual([m["role"] for m in wire["messages"]], ["system", "user"])
                self.assertEqual(wire["messages"][1]["content"], "Organize the stars alphabetically.")
                # Hermes intentionally omits token caps on some routes. Any
                # cap it forwards must retain Pet Chat's requested budget.
                for field in ("max_tokens", "max_completion_tokens"):
                    if field in wire:
                        self.assertEqual(wire[field], 64)
                self.assertNotIn("tools", wire)
        asyncio.run(check())

    def test_provider_failures_make_one_request_without_fallback(self):
        for status, reason in ((401, "provider_auth_failed"), (404, "model_unavailable"),
                               (429, "generation_failed"), (500, "generation_failed")):
            with self.subTest(status=status):
                self.status = status
                self.requests.clear()
                with self.assertRaises(self.ec.AdapterFailed) as caught:
                    self.ec.generate(provider="custom:pet-fixture", model="fixture-model",
                                     system_instruction="One line.", user_text="Hello.", timeout=2)
                self.assertEqual(caught.exception.reason, reason)
                self.assertEqual(len(self.requests), 1)

    def test_request_local_profile_survives_worker_thread(self):
        from hermes_constants import set_hermes_home_override, reset_hermes_home_override

        async def check():
            with tempfile.TemporaryDirectory() as other:
                root = Path(other)
                (root / "config.yaml").write_text("plugins:\n  entries:\n    pet-chat:\n      config:\n        attitude: dramatic\n")
                token = set_hermes_home_override(root)
                try:
                    async with self.httpx.AsyncClient(
                        transport=self.httpx.ASGITransport(app=self.app), base_url="http://test"
                    ) as client:
                        response = await client.get("/api/plugins/pet-chat/settings")
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.json()["attitude"], "dramatic")
                        self.assertIsNone(response.json()["pair"])
                finally:
                    reset_hermes_home_override(token)
        asyncio.run(check())


if __name__ == "__main__":
    source = Path(sys.argv.pop(1)).resolve()
    if not (source / "agent/auxiliary_client.py").is_file():
        raise SystemExit("Pass a Hermes source checkout as the first argument")
    sys.path.insert(0, str(source))

    def offline_only(event, args):
        if event == "socket.connect":
            raise OSError("Real network forbidden in compatibility check")
        if event == "subprocess.Popen" and Path(args[0]).name != "git":
            raise OSError("Only local git version inspection is allowed")

    sys.addaudithook(offline_only)
    with tempfile.TemporaryDirectory(prefix="pet-chat-host-check-") as tmp:
        root = Path(tmp)
        (root / "config.yaml").write_text("""custom_providers:
  - name: pet-fixture
    base_url: https://pet-chat.invalid/v1
    api_key: fixture-not-a-secret
    models:
      fixture-model: {}
""")
        (root / "models_dev_cache.json").write_text(json.dumps({"fixture": {"models": {}}}))
        with patch.object(Path, "home", return_value=root), patch.dict(
            os.environ, {"HERMES_HOME": tmp, "PATH": os.environ.get("PATH", "")}, clear=True
        ):
            unittest.main(verbosity=2)
