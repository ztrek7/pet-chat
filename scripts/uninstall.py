#!/usr/bin/env python3
"""Remove only a verified Pet Chat Desktop artifact and its receipt."""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path


_HELPER = Path(__file__).with_name("install-desktop.py")
_SPEC = importlib.util.spec_from_file_location("pet_chat_install_desktop", _HELPER)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError("could not load install-desktop.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["pet_chat_install_desktop"] = _MODULE
_SPEC.loader.exec_module(_MODULE)
uninstall_desktop = _MODULE.uninstall_desktop


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    result = uninstall_desktop(args.target, args.receipt)
    print(result["state"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
