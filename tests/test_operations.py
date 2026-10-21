"""Recovery and maintenance invariants using disposable data only."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.env = patch.dict(os.environ, DEVKIT_DATA=self.tmp.name)
        self.env.start()
        self.addCleanup(self.env.stop)
        loader = importlib.machinery.SourceFileLoader("operations_runner", str(Path(__file__).resolve().parents[1] / "bin/devkit"))
        self.dk = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
        loader.exec_module(self.dk)
        (self.root / "jobs").mkdir()

    def job(self, jid="job1", state="succeeded", **kwargs):
        art = self.root / "artifacts/game/abc" / jid
        art.mkdir(parents=True)
        (art / "result.txt").write_text("result")
        (self.root / "jobs" / jid).mkdir()
        st = dict(id=jid, project="game", commit="abc", kind="echo", seq=len(self.dk.all_jobs()),
                  artifact_dir=str(art), state=state, finished="2020-01-01T00:00:00+0900", params={})
        st.update(kwargs)
        self.dk.save(st)
        return st, art

    def cleanup(self, apply=False):
        return self.dk.v_cleanup(argparse.Namespace(keep_last=1, older_than_days=30, apply=apply))

    def test_cleanup_preview_apply_and_dependency_protection(self):
        first, first_art = self.job()
        second, second_art = self.job("job2")
        newest, newest_art = self.job("job3", params={"from_job": "job1"})
        preview = self.cleanup()
        self.assertTrue(preview["dry_run"])
        self.assertEqual([c["id"] for c in preview["candidates"]], ["job2"])
        self.assertTrue(second_art.exists())
        self.assertEqual(self.cleanup(True)["removed"], ["job2"])
        self.assertTrue(first_art.exists())
        self.assertTrue(newest_art.exists())
        self.assertTrue(self.dk.load("job2")["artifacts_expired"])

    def test_cleanup_refuses_active_queue_and_escaped_artifacts(self):
        first, art = self.job()
        self.job("job2", state="queued")
        with self.assertRaises(self.dk.Fail):
            self.cleanup(True)
        second = self.dk.load("job2")
        second["state"] = "succeeded"
        self.dk.save(second)
        first["artifact_dir"] = self.tmp.name
        self.dk.save(first)
        self.assertEqual(self.cleanup(True)["removed"], [])
        self.assertTrue(art.exists())

    def test_cleanup_never_follows_symlinks(self):
        st, art = self.job()
        self.job("job2")
        outside = self.root / "retained"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep")
        (art / "link").symlink_to(outside, target_is_directory=True)
        self.cleanup(True)
        self.assertEqual((outside / "keep.txt").read_text(), "keep")

    def test_recovery_marks_abandoned_jobs_failed_without_replaying(self):
        st, art = self.job(state="running", pid=99999999, process_group=99999999)
        self.assertTrue(self.dk.recover_jobs())
        self.assertEqual(self.dk.load(st["id"])["state"], "failed")
        self.assertTrue(art.exists())

    def test_recovery_preserves_live_or_ambiguous_processes(self):
        st, art = self.job(state="running", pid=os.getpid())
        self.assertFalse(self.dk.recover_jobs())
        self.assertEqual(self.dk.load(st["id"])["state"], "running")
        with patch.object(self.dk.os, "kill", side_effect=PermissionError):
            self.assertFalse(self.dk.recover_jobs())

    def test_low_disk_refuses_admission_before_creating_job(self):
        a = argparse.Namespace(project="game", commit="abc", kind="echo", target=None, params={}, repo=None, device=None, args=None)
        with patch.object(self.dk, "disk_status", return_value={"ready": False}), patch.object(self.dk.subprocess, "Popen") as popen:
            with self.assertRaises(self.dk.Fail):
                self.dk.v_queue(a)
            popen.assert_not_called()
        self.assertEqual(self.dk.all_jobs(), [])

    def test_dot_and_newline_paths_are_rejected(self):
        for value in (".", "..", "name\n", "../game"):
            self.assertIsNone(self.dk.SAFE_NAME.match(value))

    def test_concurrent_admission_assigns_distinct_fifo_sequences(self):
        a = argparse.Namespace(project="game", commit="abc", kind="echo", target=None, params={}, repo=None, device=None, args=None)
        with patch.object(self.dk, "disk_status", return_value={"ready": True}), patch.object(self.dk.subprocess, "Popen"):
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(lambda _: self.dk.v_queue(a), range(12)))
        self.assertEqual([j["seq"] for j in self.dk.all_jobs()], list(range(1, 13)))

    def test_worker_does_not_replay_interrupted_job(self):
        st, art = self.job(state="running", pid=99999999)
        queued, _ = self.job("queued", state="queued")
        with patch.object(self.dk, "execute") as execute:
            # Mimic the completed result so the real worker can drain and return.
            execute.side_effect = lambda job: self.dk.save(dict(job, state="succeeded"))
            self.dk.worker()
        execute.assert_called_once()
        self.assertEqual(execute.call_args.args[0]["id"], queued["id"])
        self.assertEqual(self.dk.load(st["id"])["state"], "failed")

    def test_build_fingerprint_changes_and_manifest_survives_without_git(self):
        build = self.dk.devkit_build
        (self.root / "bin").mkdir()
        file = self.root / "bin/tool"
        file.write_text("first")
        first = build.identity(self.root)
        file.write_text("second")
        second = build.identity(self.root)
        self.assertNotEqual(first["source_sha256"], second["source_sha256"])
        (self.root / "build-info.json").write_text(json.dumps(first))
        self.assertEqual(build.identity(self.root), first)

    def test_worker_lock_is_inherited_by_running_step(self):
        lock = open(self.dk.LOCK, "a")
        self.addCleanup(lock.close)
        self.dk.fcntl.flock(lock, self.dk.fcntl.LOCK_EX)
        import io
        st, art = self.job()
        ctx = self.dk.Ctx(st, io.StringIO(), str(art))
        with patch.object(self.dk, "WORKER_LOCK_FD", lock.fileno()):
            ctx.run([sys.executable, "-c",
                     "import os,sys,fcntl; os.fstat(int(sys.argv[1])); f=open(sys.argv[2], 'a'); "
                     "\ntry: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)"
                     "\nexcept BlockingIOError: pass"
                     "\nelse: raise RuntimeError('worker lock was not retained')",
                     str(lock.fileno()), self.dk.LOCK])
        self.assertIsNone(st["process_group"])
