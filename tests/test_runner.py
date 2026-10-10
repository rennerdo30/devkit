"""POSIX worker process safety tests; no Unity installation required."""
import importlib.machinery
import importlib.util
import io
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

@unittest.skipUnless(os.name == "posix", "runner uses POSIX process groups and flock")
class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("runner_test_module", str(Path(__file__).resolve().parents[1] / "bin/devkit"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.runner = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.runner)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.log = io.StringIO()
        self.ctx = self.runner.Ctx({"id": "fixture", "project": "fixture"}, self.log, self.tmp.name)
        self.ctx.cancel_file = str(Path(self.tmp.name) / "cancel")
        self.save = mock.patch.object(self.runner, "save")
        self.save.start()
        self.addCleanup(self.save.stop)

    def run_script(self, script, **kwargs):
        return self.ctx.run([sys.executable, "-u", "-c", script], **kwargs)

    def test_continuous_output_deadline(self):
        start = time.monotonic()
        with self.assertRaises(self.runner.Fail):
            self.run_script("import os;\nwhile True: os.write(1, b'x' * 4096)", timeout=0.15)
        self.assertLess(time.monotonic() - start, 3)
        self.assertIn("x", self.log.getvalue())
        self.assertIsNone(self.ctx.st["pid"])

    def test_ignores_term_and_unterminated_output(self):
        start = time.monotonic()
        with self.assertRaises(self.runner.Fail):
            self.run_script("import signal,time,sys; signal.signal(signal.SIGTERM,signal.SIG_IGN); sys.stdout.write('partial'); sys.stdout.flush(); time.sleep(30)", timeout=0.15)
        self.assertLess(time.monotonic() - start, 3)
        self.assertIn("partial", self.log.getvalue())
        self.assertEqual(self.ctx.st["steps"][-1]["exit"], -signal.SIGKILL)

    def test_cancel_kills_ignoring_process(self):
        timer = threading.Timer(0.15, lambda: Path(self.ctx.cancel_file).touch())
        timer.start()
        self.addCleanup(timer.cancel)
        with self.assertRaises(self.runner.Cancelled):
            self.run_script("import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)", timeout=10)
        self.assertIsNone(self.ctx.st["pid"])

    def test_group_signal_errors_fall_back_and_reap_tree(self):
        # Exercise EPERM and ESRCH on live groups as well as already-exited leaders.
        for error in (PermissionError, ProcessLookupError):
            for cancel in (False, True):
                with self.subTest(error=error, cancel=cancel):
                    Path(self.ctx.cancel_file).unlink(missing_ok=True)
                    out = []
                    timer = threading.Timer(0.4, lambda: Path(self.ctx.cancel_file).touch()) if cancel else None
                    if timer:
                        timer.start()
                    script = (
                        "import os,signal,subprocess,sys,time; "
                        "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                        "child=subprocess.Popen([sys.executable,'-u','-c',"
                        "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); print(\"child ready\",flush=True); time.sleep(30)']); "
                        "print('pids',os.getpid(),child.pid,flush=True); time.sleep(30)"
                    )
                    start = time.monotonic()
                    try:
                        with mock.patch.object(self.runner.os, "killpg", side_effect=error), self.assertRaises(
                                self.runner.Cancelled if cancel else self.runner.Fail):
                            self.run_script(script, timeout=10 if cancel else 0.4, out=out)
                    finally:
                        if timer:
                            timer.cancel()
                    self.assertLess(time.monotonic() - start, 4)
                    self.assertEqual(self.ctx.st["steps"][-1]["exit"], -signal.SIGKILL)
                    self.assertIsNone(self.ctx.st["pid"])
                    pids = next(line.split()[1:] for line in out if line.startswith("pids "))
                    snapshot = self.runner.process_snapshot()
                    for pid in map(int, pids):
                        self.assertTrue(pid not in snapshot or snapshot[pid][2].startswith("Z"), pid)

    def test_group_eperm_after_leader_exit_cleans_descendant(self):
        out = []
        with mock.patch.object(self.runner.os, "killpg", side_effect=PermissionError):
            self.run_script("import subprocess,sys; child=subprocess.Popen([sys.executable,'-c',"
                            "'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)']); "
                            "print('descendant',child.pid,flush=True)", timeout=5, out=out)
        pid = int(next(line.split()[1] for line in out if line.startswith("descendant ")))
        snapshot = self.runner.process_snapshot()
        self.assertTrue(pid not in snapshot or snapshot[pid][2].startswith("Z"))
        self.assertIsNone(self.ctx.st["pid"])

    def test_snapshot_failure_still_kills_and_reaps_parent(self):
        with mock.patch.object(self.runner, "process_snapshot", side_effect=OSError("fixture ps failure")), self.assertRaises(OSError):
            self.run_script("import time; time.sleep(30)", timeout=5)
        self.assertEqual(self.ctx.st["steps"][-1]["exit"], -signal.SIGKILL)
        self.assertIsNone(self.ctx.st["pid"])

    def test_recycled_child_identity_is_not_signalled(self):
        children = self.runner.ProcessChildren(100)
        with mock.patch.object(self.runner, "process_snapshot", return_value={100: (1, 100, "S", "root birth"), 101: (100, 100, "S", "old birth")}):
            self.assertEqual(children.alive(), [101])
        with mock.patch.object(self.runner, "process_snapshot", return_value={101: (1, 200, "S", "new birth")}):
            self.assertEqual(children.alive(), [])

    def test_recycled_root_does_not_adopt_foreign_group(self):
        children = self.runner.ProcessChildren(100)
        with mock.patch.object(self.runner, "process_snapshot", return_value={100: (1, 100, "S", "original")}):
            self.assertEqual(children.alive(), [])
        with mock.patch.object(self.runner, "process_snapshot", return_value={100: (1, 100, "S", "recycled"),
                                                                           101: (100, 100, "S", "foreign")}):
            self.assertEqual(children.alive(), [])
            self.assertFalse(children.group_owned)

    def test_denied_all_signals_reaches_bounded_reap(self):
        original_kill = os.kill
        launched = []
        original_popen = self.runner.subprocess.Popen

        def launch(*args, **kwargs):
            child = original_popen(*args, **kwargs)
            if args[0][0] != "/bin/ps":
                launched.append(child)
            return child

        start = time.monotonic()
        try:
            with mock.patch.object(self.runner.subprocess, "Popen", side_effect=launch), \
                    mock.patch.object(self.runner.os, "killpg", side_effect=PermissionError), \
                    mock.patch.object(self.runner.os, "kill", side_effect=PermissionError), \
                    self.assertRaises(subprocess.TimeoutExpired):
                self.run_script("import time; time.sleep(30)", timeout=0.15)
            self.assertLess(time.monotonic() - start, 6)
        finally:
            for child in launched:
                if child.poll() is None:
                    original_kill(child.pid, signal.SIGKILL)
                child.wait(timeout=2)

    def test_descendant_retains_stdout(self):
        start = time.monotonic()
        self.run_script("import subprocess,sys; subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)']); print('parent done')", timeout=5)
        self.assertLess(time.monotonic() - start, 3)
        self.assertIn("parent done", self.log.getvalue())

    def test_job_deadline_caps_step(self):
        self.ctx.unity_deadline = time.monotonic() + 0.15
        with self.assertRaises(self.runner.Fail):
            self.run_script("import time; time.sleep(30)", timeout=30)

    def test_slot_serializes_roots_before_checkout_and_logs_failures(self):
        import fcntl
        root = Path(self.tmp.name)
        jobs, artifacts = root / "jobs", root / "artifacts"
        (jobs / "fixture").mkdir(parents=True)
        st = {"id": "fixture", "project": "fixture", "commit": "main", "kind": "unity-test", "target": None, "repo": "fixture"}
        lock = root / "account-host-unity.lock"
        entered = threading.Event()
        with lock.open("a") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch.multiple(self.runner, JOBS=str(jobs), ARTIFACTS=str(artifacts), UNITY_SLOT=str(lock)), mock.patch.object(self.runner, "keep_awake", return_value=None), mock.patch.object(self.runner.devkit_kinds, "validate_unity_params", return_value=None), mock.patch.object(self.runner.devkit_kinds, "unity_timeout", return_value=5), mock.patch.object(self.runner, "checkout", side_effect=lambda *a: (entered.set(), (_ for _ in ()).throw(self.runner.Fail("checkout fixture failure")))[1]):
                thread = threading.Thread(target=self.runner.execute, args=(st,))
                thread.start()
                time.sleep(0.2)
                self.assertFalse(entered.is_set())
                fcntl.flock(owner, fcntl.LOCK_UN)
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
        self.assertTrue(entered.is_set())
        artifact = artifacts / "fixture" / "main" / "fixture" / "job.log"
        self.assertIn("checkout fixture failure", artifact.read_text())
        self.assertEqual(st["state"], "failed")

    def test_log_publish_failure_finishes_and_releases_slot(self):
        import fcntl
        root = Path(self.tmp.name)
        jobs, artifacts = root / "jobs", root / "artifacts"
        (jobs / "fixture").mkdir(parents=True)
        st = {"id": "fixture", "project": "fixture", "commit": "main", "kind": "unity-test", "target": None, "repo": ""}
        lock = root / "account-host-unity.lock"
        with mock.patch.multiple(self.runner, JOBS=str(jobs), ARTIFACTS=str(artifacts), UNITY_SLOT=str(lock)), mock.patch.object(self.runner, "keep_awake", return_value=None), mock.patch.object(self.runner.devkit_kinds, "validate_unity_params", return_value=None), mock.patch.object(self.runner.devkit_kinds, "unity_timeout", return_value=5), mock.patch.dict(self.runner.devkit_kinds.KINDS, {"unity-test": lambda ctx: None}), mock.patch.object(self.runner.shutil, "copyfile", side_effect=OSError("fixture disk full")):
            self.runner.execute(st)
        self.assertEqual(st["state"], "failed")
        self.assertIsNone(st["pid"])
        self.assertIn("could not publish job.log", (jobs / "fixture" / "log.txt").read_text())
        with lock.open("a") as contender:
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_cancelled_slot_wait_publishes_log(self):
        import fcntl
        root = Path(self.tmp.name)
        jobs, artifacts = root / "jobs", root / "artifacts"
        (jobs / "fixture").mkdir(parents=True)
        st = {"id": "fixture", "project": "fixture", "commit": "main", "kind": "unity-test", "target": None, "repo": ""}
        lock = root / "account-host-unity.lock"
        with lock.open("a") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            timer = threading.Timer(0.15, lambda: (jobs / "fixture" / "cancel").touch())
            timer.start()
            self.addCleanup(timer.cancel)
            with mock.patch.multiple(self.runner, JOBS=str(jobs), ARTIFACTS=str(artifacts), UNITY_SLOT=str(lock)), mock.patch.object(self.runner, "keep_awake", return_value=None), mock.patch.object(self.runner.devkit_kinds, "validate_unity_params", return_value=None), mock.patch.object(self.runner.devkit_kinds, "unity_timeout", return_value=5):
                self.runner.execute(st)
        self.assertEqual(st["state"], "cancelled")
        self.assertIn("DEVKIT state=cancelled", (artifacts / "fixture" / "main" / "fixture" / "job.log").read_text())

    def test_lock_inherited_by_child(self):
        import fcntl
        path = Path(self.tmp.name) / "unity.lock"
        with path.open("a") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"], pass_fds=(owner.fileno(),))
        self.addCleanup(lambda: child.poll() is None and child.kill())
        with path.open("a") as contender:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
            child.wait(timeout=3)
            fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)

if __name__ == "__main__":
    unittest.main()
