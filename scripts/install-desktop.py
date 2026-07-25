#!/usr/bin/env python3
"""Receipt-backed, scoped Desktop artifact lifecycle for Pet Chat.

This helper deliberately does not manage the Python checkout. Hermes' native
Git installer owns that checkout; this module receives the already-resolved
commit and verifies the Desktop artifact came from the same source.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

RECEIPT_VERSION = 1
PLUGIN_VERSION = "0.1.0-dev"


class LifecycleError(RuntimeError):
    """A safe refusal or failed atomic lifecycle operation."""


@dataclass(frozen=True)
class InstallState:
    receipt_exists: bool
    target_exists: bool
    target_owned: bool
    target_verified: bool
    backend_enabled: Optional[bool]
    desktop_decision: Optional[bool]
    source_commit: Optional[str]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.is_file():
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    elif path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file():
                digest.update(child.relative_to(path).as_posix().encode())
                digest.update(_sha256(child).encode())
    else:
        raise LifecycleError(f"path does not exist: {path}")
    return digest.hexdigest()


def _file_hashes(root: Path) -> Dict[str, str]:
    if not root.is_dir():
        raise LifecycleError(f"Desktop artifact is not a directory: {root}")
    return {p.relative_to(root).as_posix(): _sha256(p) for p in sorted(root.rglob("*")) if p.is_file()}


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise LifecycleError(f"invalid JSON state: {path}") from exc
    if not isinstance(value, dict):
        raise LifecycleError(f"JSON state must be an object: {path}")
    return value


def load_receipt(receipt_path: Path) -> Optional[Dict[str, Any]]:
    return _read_json(receipt_path)


def discover_state(target: Path, receipt_path: Path, state_dir: Optional[Path] = None) -> InstallState:
    receipt = load_receipt(receipt_path)
    target_exists = target.exists()
    target_owned = bool(receipt and str(target) in receipt.get("owned_paths", []))
    target_verified = bool(
        receipt and target.is_dir() and receipt.get("artifact_hashes") == _file_hashes(target)
    ) if target_exists and target_owned else False
    backend_enabled = desktop_decision = None
    if state_dir:
        backend = _read_json(state_dir / "backend-decision.json")
        desktop = _read_json(state_dir / "desktop-decision.json")
        backend_enabled = backend.get("enabled") if backend else None
        desktop_decision = desktop.get("enabled") if desktop else None
    return InstallState(
        receipt_exists=receipt is not None,
        target_exists=target_exists,
        target_owned=target_owned,
        target_verified=target_verified,
        backend_enabled=backend_enabled,
        desktop_decision=desktop_decision,
        source_commit=receipt.get("resolved_commit") if receipt else None,
    )


def classify_state(state: InstallState) -> str:
    if not state.receipt_exists and not state.target_exists:
        return "clean_install"
    if not state.receipt_exists and state.target_exists:
        return "unknown_target"
    if state.receipt_exists and not state.target_exists:
        return "repair"
    if state.receipt_exists and not state.target_owned:
        return "conflict"
    if state.desktop_decision is False and state.target_verified:
        return "update_backend_disabled"
    if state.target_verified:
        return "update"
    return "repair"


def _manifest_commit(source_dir: Path) -> str:
    manifest = _read_json(source_dir / "manifest.json")
    if not manifest or not isinstance(manifest.get("source_commit"), str):
        raise LifecycleError("Desktop manifest must declare source_commit")
    return manifest["source_commit"]


def _materialize_source_commit(staged: Path, resolved_commit: str) -> None:
    manifest_path = staged / "manifest.json"
    manifest = _read_json(manifest_path)
    if not manifest:
        raise LifecycleError("Desktop manifest is missing")
    declared = manifest.get("source_commit")
    if declared not in {"set-by-build", resolved_commit}:
        raise LifecycleError("source_commit mismatch; installation aborted before replacement")
    manifest["source_commit"] = resolved_commit
    _write_json_atomic(manifest_path, manifest)


def _write_json_atomic(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _receipt(target: Path, receipt_path: Path, source_commit: str, hashes: Dict[str, str], state: str) -> Dict[str, Any]:
    return {
        "receipt_version": RECEIPT_VERSION,
        "plugin_id": "pet-chat",
        "plugin_version": PLUGIN_VERSION,
        "compatibility": ">=0.19.0,<0.20.0",
        "source_url": "https://github.com/ztrek7/pet-chat",
        "resolved_commit": source_commit,
        "desktop": {"source_commit": source_commit},
        "owned_paths": [str(target)],
        "artifact_hashes": hashes,
        "lifecycle_state": state,
        "installed_at": _utc_now(),
        "receipt_path": str(receipt_path),
    }


def install_desktop(source_dir: Path, target: Path, receipt_path: Path, resolved_commit: str,
                    state_dir: Optional[Path] = None) -> Dict[str, Any]:
    if not resolved_commit or resolved_commit in {"main", "HEAD"}:
        raise LifecycleError("resolved_commit must be the concrete commit returned by Git")
    if _manifest_commit(source_dir) not in {"set-by-build", resolved_commit}:
        raise LifecycleError("source_commit mismatch; installation aborted before replacement")
    state = discover_state(target, receipt_path, state_dir)
    classification = classify_state(state)
    if classification in {"unknown_target", "conflict"}:
        raise LifecycleError(f"refusing {classification}: existing state is not Pet Chat-owned")

    target.parent.mkdir(parents=True, exist_ok=True)
    backup_dir = Path(tempfile.mkdtemp(prefix="pet-chat-backup-", dir=str(target.parent)))
    backup_target = backup_dir / "artifact"
    backup_exists = False
    stage = Path(tempfile.mkdtemp(prefix="pet-chat-stage-", dir=str(target.parent)))
    try:
        staged = stage / "artifact"
        shutil.copytree(source_dir, staged)
        _materialize_source_commit(staged, resolved_commit)
        hashes = _file_hashes(staged)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            os.replace(target, backup_target)
            backup_exists = True
        os.replace(staged, target)
        receipt = _receipt(target, receipt_path, resolved_commit, _file_hashes(target), classification)
        _write_json_atomic(receipt_path, receipt)
        return receipt
    except Exception as exc:
        if target.exists():
            shutil.rmtree(target)
        if backup_exists:
            os.replace(backup_target, target)
        raise LifecycleError("Desktop installation failed; prior verified state restored") from exc
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        shutil.rmtree(backup_dir, ignore_errors=True)


def uninstall_desktop(target: Path, receipt_path: Path) -> Dict[str, str]:
    receipt = load_receipt(receipt_path)
    if not receipt or str(target) not in receipt.get("owned_paths", []):
        raise LifecycleError("refusing uninstall: Pet Chat receipt does not own target")
    if not target.is_dir() or receipt.get("artifact_hashes") != _file_hashes(target):
        raise LifecycleError("refusing uninstall: target was modified or is missing")
    shutil.rmtree(target)
    receipt_path.unlink()
    return {"state": "uninstalled"}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    install = sub.add_parser("install")
    install.add_argument("--source", type=Path, required=True)
    install.add_argument("--target", type=Path, required=True)
    install.add_argument("--receipt", type=Path, required=True)
    install.add_argument("--source-commit", required=True)
    uninstall = sub.add_parser("uninstall")
    uninstall.add_argument("--target", type=Path, required=True)
    uninstall.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "install":
        result = install_desktop(args.source, args.target, args.receipt, args.source_commit)
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(uninstall_desktop(args.target, args.receipt), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
