"""Offline runtime lifecycle check. Run with Hermes' prepared Python:

    python tests/check_lifecycle.py /path/to/hermes-agent

No provider calls, dependency installation, live config, or Desktop process.
This exercises discovery/allow-list/unload/remove, not PM dependency publication.
"""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main():
    source = Path(sys.argv[1]).resolve()
    package = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(source))
    sys.dont_write_bytecode = True
    def offline(event, _args):
        if event in {'socket.connect', 'socket.getaddrinfo'}:
            raise RuntimeError('Network is forbidden during lifecycle validation')
    sys.addaudithook(offline)
    with tempfile.TemporaryDirectory(prefix='plugin-lifecycle-') as temp:
        home = Path(temp)
        os.environ.clear()
        os.environ.update(HOME=temp, HERMES_HOME=temp, PATH='/usr/bin:/bin',
                          HERMES_BUNDLED_PLUGINS=str(home / 'empty-bundled'),
                          HERMES_ENABLE_PROJECT_PLUGINS='0', PYTHONDONTWRITEBYTECODE='1')
        (home / 'empty-bundled').mkdir()
        import hermes_yaml as yaml
        from hermes_cli.plugins import PluginManager
        from hermes_cli.plugin_validate import validate_plugin_dir
        from hermes_cli.plugin_dev import doctor_plugin
        manifest = yaml.safe_load((package / 'plugin.yaml').read_text())
        name = manifest['name']
        target = home / 'plugins' / name
        shutil.copytree(package, target, ignore=shutil.ignore_patterns('.git', '__pycache__', '.venv'))
        config = {'sentinel': 'preserved', 'plugins': {'enabled': [], 'disabled': []}}
        def save():
            (home / 'config.yaml').write_text(yaml.safe_dump(config))
        save()
        manager = PluginManager()
        manager.discover_and_load()
        assert not manager._plugins[name].enabled, 'fresh package must be inert'
        config['plugins']['enabled'] = [name]
        save()
        for _ in range(2):
            manager.discover_and_load(force=True)
            loaded = manager._plugins[name]
            assert loaded.enabled and not loaded.error, loaded.error
        config['plugins']['enabled'] = []
        config['plugins']['disabled'] = [name]
        save()
        manager.discover_and_load(force=True)
        assert not manager._plugins[name].enabled
        manager.unload()
        shutil.rmtree(target)
        manager.discover_and_load(force=True)
        assert name not in manager._plugins
        assert yaml.safe_load((home / 'config.yaml').read_text())['sentinel'] == 'preserved'
        report = validate_plugin_dir(package)
        assert report.ok, report.failures
        doctor = doctor_plugin(package)
        errors = [f.message for f in doctor.findings if f.level == 'error']
        assert not errors, errors
        print(json.dumps({'plugin': name, 'lifecycle': 'passed',
                          'validation_checks': len(report.checks),
                          'warnings': report.warnings + [f.message for f in doctor.findings if f.level == 'warning']}))


if __name__ == '__main__':
    main()
