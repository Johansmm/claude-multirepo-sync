import subprocess
import tempfile
from pathlib import Path

import pytest


def symlinks_available():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            Path(tmp, "link").symlink_to(Path(tmp, "target"))
        except OSError:
            return False
    return True


# Shared so a test can say what it needs instead of repeating the reason.
needs_symlinks = pytest.mark.skipif(
    not symlinks_available(), reason="creating a symlink needs a Windows privilege"
)


def write(path, content):
    """Write a file, creating the directories above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def run_git(cwd, *args):
    return subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
