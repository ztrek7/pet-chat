"""Host API transitions; no installed Hermes or provider credentials needed."""
import builtins
import sys
import unittest
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock, patch

from test_smoke import _load


class CompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ec = _load("pet_chat_compat_exact", "dashboard/exact_client.py")

    def test_canonical_version_overrides_legacy_placeholder(self):
        host = ModuleType("hermes_cli")
        host.__version__ = "0.0.0"
        version = ModuleType("hermes_cli.version_info")
        version.get_version_info = lambda: SimpleNamespace(base_version="0.21.7")
        with patch.dict(sys.modules, {"hermes_cli": host, "hermes_cli.version_info": version}):
            self.assertEqual(self.ec._hermes_version(), (0, 21))

    def test_unknown_canonical_version_cannot_use_stale_legacy_version(self):
        host = ModuleType("hermes_cli")
        host.__version__ = "0.21.0"
        version = ModuleType("hermes_cli.version_info")
        version.get_version_info = lambda: SimpleNamespace(base_version="unknown")
        with patch.dict(sys.modules, {"hermes_cli": host, "hermes_cli.version_info": version}):
            self.assertIsNone(self.ec._hermes_version())

    def test_old_host_without_version_api_still_works(self):
        host = ModuleType("hermes_cli")
        host.__version__ = "0.20.0"
        with patch.dict(sys.modules, {"hermes_cli": host, "hermes_cli.version_info": None}):
            self.assertEqual(self.ec._hermes_version(), (0, 20))

    def test_backend_uses_host_yaml_without_pyyaml(self):
        host_yaml = ModuleType("hermes_yaml")
        real_import = builtins.__import__

        def without_pyyaml(name, *args, **kwargs):
            if name == "yaml":
                raise ModuleNotFoundError("No module named 'yaml'", name="yaml")
            return real_import(name, *args, **kwargs)

        with patch.dict(sys.modules, {"hermes_yaml": host_yaml}), patch(
            "builtins.__import__", side_effect=without_pyyaml
        ):
            api = _load("pet_chat_host_yaml_api", "dashboard/plugin_api.py")
            self.assertIs(api.yaml, host_yaml)

    def test_catalog_receives_profile_provider_definitions(self):
        api = _load("pet_chat_catalog_compat_api", "dashboard/plugin_api.py")
        listing = Mock(return_value=[])
        switch = ModuleType("hermes_cli.model_switch")
        switch.list_authenticated_providers = listing
        config = {"providers": {"example": {"enabled": False}},
                  "custom_providers": [{"name": "my-server", "models": ["small"]}]}
        with patch.dict(sys.modules, {"hermes_cli": ModuleType("hermes_cli"),
                                      "hermes_cli.model_switch": switch}), patch.object(
            api, "_read_config", return_value=config
        ):
            self.assertEqual(api._catalog_rows(), [])
        self.assertEqual(listing.call_args.kwargs.get("user_providers"), config["providers"])
        self.assertEqual(listing.call_args.kwargs.get("custom_providers"), config["custom_providers"])
