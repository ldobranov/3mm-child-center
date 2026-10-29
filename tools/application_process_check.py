"""Disposable Linux process controller for real standard 3mm activation checks.
No installed systemd unit or Core database is accessed.
"""
from contextlib import contextmanager
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
import three_mm_runtime
from three_mm_runtime.application_activation import activate_application_package
from three_mm_runtime.application_transport import ApplicationServiceClient

class ProcessSupervisor:
    def __init__(self, root, keys, logs):
        self.root, self.keys, self.logs = root, keys, logs
        self.process = None
        self.calls = []
        self.logfile = None

    def is_enabled(self, instance):
        return False

    def stop(self, instance):
        self.calls.append(('stop', instance))
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill(); self.process.wait(timeout=5)
            self.process = None
        if self.logfile:
            self.logfile.close(); self.logfile = None

    def recover_disabled(self, instance):
        self.stop(instance)
        return dict(LoadState='loaded', ActiveState='inactive', SubState='dead',
                    UnitFileState='disabled', MainPID='0', Job='')

    def restart(self, instance):
        self.stop(instance)
        self.calls.append(('restart', instance))
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                   PYTHONPATH=str(Path(three_mm_runtime.__file__).parents[1]))
        self.logfile = self.logs.open('ab')
        self.process = subprocess.Popen([sys.executable, '-m', 'three_mm_runtime.application_host',
            '--instance', instance, '--root', str(self.root), '--key-root', str(self.keys)],
            cwd=self.root.parent, env=env, stdout=self.logfile, stderr=subprocess.STDOUT)


@contextmanager
def disposable_runtime(logs):
    logs = Path(logs).resolve()
    logs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="3mm-app-check-") as folder:
        base = Path(folder)
        supervisor = ProcessSupervisor(base / "a", base / "k", logs / "host.log")
        try:
            yield base, supervisor
        finally:
            supervisor.stop("cleanup")


def activate(base, supervisor, payload, configuration=None):
    sha = hashlib.sha256(payload).hexdigest()
    archive = base / (sha + ".zip")
    archive.write_bytes(payload)
    return activate_application_package(archive, sha, root=supervisor.root,
        key_root=supervisor.keys, supervisor=supervisor, configuration=configuration)


def client(supervisor, instance):
    return ApplicationServiceClient(supervisor.root / instance / "run/service.sock",
        (supervisor.keys / (instance + ".key")).read_bytes(), 3)


def activation_smoke(archive, logs):
    payload = Path(archive).read_bytes()
    with zipfile.ZipFile(io.BytesIO(payload)) as package:
        health_operation = json.loads(package.read('application-extension.json'))['service']['health_operation_id']
    with disposable_runtime(logs) as (base, supervisor):
        first = activate(base, supervisor, payload)
        internal = {"audience": "internal", "correlation_id": "application-check"}
        health = client(supervisor, first.instance_id).invoke(health_operation, {}, internal)
        database = supervisor.root / first.instance_id / "data/state.sqlite3"
        def snapshot():
            with sqlite3.connect(database) as db:
                return "\n".join(db.iterdump())
        before = snapshot()
        second = activate(base, supervisor, payload)
        if second.instance_id != first.instance_id or before != snapshot():
            raise RuntimeError("Reactivation changed the application data snapshot")
        return {"initial_health": health, "reactivated": True, "data_preserved": True,
                "scope": "real host/SDK/AF_UNIX; subprocess controller instead of systemd"}
