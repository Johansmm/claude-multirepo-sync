import pytest
from filelock import Timeout

from claude_multirepo_sync import config, discover, git_sync, session_sync
from claude_multirepo_sync.errors import SyncError


class BusyLock:
    """Stands in for a lock another process already holds."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        raise Timeout("multirepo-sync.lock")

    def __exit__(self, *args):
        return False


@pytest.fixture
def repo(tmp_path):
    """Never reaches the disk - both steps are stubbed. Under tmp_path anyway, so
    it stays harmless if a test ever stops stubbing them.
    """
    return tmp_path / "config-repo"


def steps_that_record(monkeypatch, git_sync_fails_with=None):
    def git_step(repo):
        if git_sync_fails_with:
            raise git_sync_fails_with
        ran.append("git-sync")

    def discover_step(repo, extra_search_roots=None):
        ran.append("discover")

    ran = []
    monkeypatch.setattr(git_sync, "main", git_step)
    monkeypatch.setattr(discover, "main", discover_step)
    return ran


def test_stays_silent_when_everything_is_clean(repo, monkeypatch):
    ran = steps_that_record(monkeypatch)

    assert session_sync.main(repo) == ""
    assert ran == ["git-sync", "discover"]


def test_discover_still_runs_when_the_sync_fails(repo, monkeypatch):
    # The reason failures propagate instead of exiting: an exit here would have
    # killed the process before discover ever ran.
    marker = config.CONFLICT_MARKER
    ran = steps_that_record(
        monkeypatch, git_sync_fails_with=SyncError("CONFLICT in git pull", marker=marker)
    )

    report = session_sync.main(repo)

    assert ran == ["discover"]
    assert marker.read_text(encoding="utf-8").strip() == "CONFLICT in git pull"
    assert "unresolved git conflict" in report


def test_files_changed_by_the_mirror_are_reported(repo, monkeypatch):
    # The point of the whole exercise: the session loaded these before they changed.
    monkeypatch.setattr(git_sync, "main", lambda repo: None)
    monkeypatch.setattr(
        discover, "main", lambda repo, extra_search_roots=None: [r"C:\Users\x\.claude\CLAUDE.md"]
    )

    report = session_sync.main(repo)

    assert "changed during this session" in report
    assert r"C:\Users\x\.claude\CLAUDE.md" in report


def test_lock_contention_is_reported_without_running_anything(repo, monkeypatch):
    monkeypatch.setattr(session_sync, "FileLock", BusyLock)
    ran = steps_that_record(monkeypatch)

    report = session_sync.main(repo)

    assert ran == []
    assert "sync was skipped" in report
