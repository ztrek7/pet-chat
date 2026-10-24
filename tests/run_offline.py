"""Run only mock regressions with a disposable home and no Python network access."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

root = Path(__file__).resolve().parents[1]
os.chdir(root)
sys.path.insert(0, str(root))
if len(sys.argv) > 1:
    sys.path.insert(0, str(Path(sys.argv[1]).resolve()))

def offline(event, _args):
    if event in {"socket.connect", "socket.getaddrinfo"}:
        raise RuntimeError("Network forbidden during offline regression tests")

sys.addaudithook(offline)
with tempfile.TemporaryDirectory(prefix="plugin-regression-") as temp:
    path = os.environ.get("PATH", os.defpath)
    os.environ.clear()
    os.environ.update(HOME=temp, HERMES_HOME=temp + "/hermes", PATH=path,
                      PYTHONDONTWRITEBYTECODE="1")
    suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
