"""Runs the whole sync in one process, then reports once."""

from pathlib import Path

from filelock import FileLock, Timeout

from claude_multirepo_sync import discover, git_sync, session_check
from claude_multirepo_sync.errors import SyncError

CLAUDE_HOME = Path.home() / ".claude"
LOCK = CLAUDE_HOME / "multirepo-sync.lock"
LOCK_TIMEOUT_SECONDS = 120


def attempt(step, *args, **kwargs):
    """Run one step, recording a failure instead of letting it skip the next -
    the whole reason failures propagate instead of exiting.
    """
    try:
        return step(*args, **kwargs)
    except SyncError as e:
        e.record()


def run_steps(repo, extra_search_roots):
    """Pull, then mirror. Returns the local files whose content now differs."""
    attempt(git_sync.main, repo)
    changes = attempt(discover.main, repo, extra_search_roots=extra_search_roots) or []
    return changes


def main(repo, extra_search_roots=None):
    """Everything worth telling the session about, or "" to stay silent."""
    notes = []
    changed = []
    try:
        # Waiting, not skipping: the holder is doing the same work, and if it is
        # the SessionEnd process of the last session, walking away would leave
        # its markers unreported for a whole session.
        with FileLock(LOCK, timeout=LOCK_TIMEOUT_SECONDS):
            changed = run_steps(repo, extra_search_roots)
    except Timeout:
        notes.append(
            "## NOTICE: the config sync was skipped\n\n"
            f"Another sync held {LOCK} for over {LOCK_TIMEOUT_SECONDS}s, so this "
            "one gave up. Check for a stuck process."
        )

    # Read the markers last: this run may have resolved what the previous one
    # left behind, and announcing a conflict that just healed is noise.
    notes.append(session_check.report())

    if changed:
        # Stated as a fact, not as an instruction: the woken session receives
        # this as untrusted data and will ignore anything phrased as an order.
        notes.append(
            "## NOTICE: synced config files changed during this session\n\n"
            "This session loaded them before the change, so the copy it holds is "
            "out of date:\n" + "\n".join(f"- {path}" for path in changed)
        )
    return "\n\n".join(note for note in notes if note)
