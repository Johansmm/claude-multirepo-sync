import pytest

from claude_multirepo_sync import config, discover, git_sync, session_check, session_sync


@pytest.fixture(autouse=True)
def claude_home(tmp_path, monkeypatch):
    """Redirect everything the tool writes outside the repo into tmp_path.

    Autouse on purpose: markers and the lock live in the developer's real
    ~/.claude, so a test that forgot to redirect them would write there.
    """
    home = tmp_path / "claude-home"
    home.mkdir()
    monkeypatch.setattr(git_sync, "CLAUDE_HOME", home)
    monkeypatch.setattr(git_sync, "MARKER", home / "multirepo-sync.conflict")
    monkeypatch.setattr(discover, "CLAUDE_HOME", home)
    monkeypatch.setattr(discover, "PENDING_MARKER", home / "multirepo-sync.pending")
    monkeypatch.setattr(session_check, "CLAUDE_HOME", home)
    monkeypatch.setattr(session_check, "CONFLICT_MARKER", home / "multirepo-sync.conflict")
    monkeypatch.setattr(session_check, "PENDING_MARKER", home / "multirepo-sync.pending")
    monkeypatch.setattr(session_sync, "LOCK", home / "multirepo-sync.lock")
    monkeypatch.setattr(config, "CLAUDE_HOME", home)
    monkeypatch.setattr(config, "REPO_FILE", home / "multirepo-sync.repo")
    return home
