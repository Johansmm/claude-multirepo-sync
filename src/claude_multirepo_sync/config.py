"""Where this tool keeps its own files on this machine.

The pointer to the config repo is kept in the user's own config rather than
baked into the package at install time: an installed wheel is meant to be
relocatable, and a path compiled into one would be silently lost on the next
reinstall - which is exactly what a dependency change forces.

Every other path is gathered here for the same reason it matters at all: they
are the only things this tool writes outside the config repo, and one module
owning them is what keeps a test from ever writing into a real ~/.claude.
"""

from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
REPO_FILE = CLAUDE_HOME / "multirepo-sync.repo"
CONFLICT_MARKER = CLAUDE_HOME / "multirepo-sync.conflict"
PENDING_MARKER = CLAUDE_HOME / "multirepo-sync.pending"
LOCK = CLAUDE_HOME / "multirepo-sync.lock"
ERROR_PREFIX = "multirepo-sync.error."


def error_marker(command):
    """Where a crash in this command is recorded.

    One per command: a shared marker meant the next command to pass wiped a
    crash nobody had seen yet.
    """
    return CLAUDE_HOME / f"{ERROR_PREFIX}{command}"


def is_repo(path):
    """Whether a path can serve as the config repo. Implies the directory exists."""
    return (path / ".git").exists()


def read_repo():
    """The recorded repo, or None if this machine has not been set up.

    Deliberately does not check the path is still valid: gone-since-configured
    and never-configured need different messages, and only the caller knows how
    to phrase them.
    """
    try:
        stored = REPO_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        # Missing or unreadable is the same answer: not configured yet.
        return None
    return Path(stored).expanduser() if stored else None


def write_repo(path):
    """Record the repo, refusing anything that is not one, and return it.

    Refusing here is the point: a typo costs one message now instead of a broken
    hook on every session start.
    """
    repo = Path(path).expanduser().resolve()
    if not is_repo(repo):
        raise ValueError(f"{repo} is not a git repository.")
    CLAUDE_HOME.mkdir(parents=True, exist_ok=True)
    REPO_FILE.write_text(f"{repo}\n", encoding="utf-8")
    return repo
