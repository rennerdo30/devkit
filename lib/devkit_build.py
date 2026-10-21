"""Build identity shared by the source runner and bundled app. No runtime data."""
import hashlib
import json
from pathlib import Path
import subprocess

VERSION = "0.6.0"


def identity(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    manifest = root / "build-info.json"
    if manifest.is_file():
        return json.loads(manifest.read_text())
    digest = hashlib.sha256()
    for folder in ("bin", "lib", "web", "app/Sources"):
        for file in sorted((root / folder).rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
                digest.update(str(file.relative_to(root)).encode() + b"\0" + file.read_bytes())
    def git(*args):
        try:
            return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL,
                                           timeout=5, text=True).strip()
        except (OSError, subprocess.SubprocessError):
            return None
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"version": VERSION, "commit": git("rev-parse", "HEAD"),
            "dirty": bool(status) if status is not None else None, "source_sha256": digest.hexdigest()}
