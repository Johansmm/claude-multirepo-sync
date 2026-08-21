import pytest

from claude_multirepo_sync import config


@pytest.fixture(autouse=True)
def claude_home(tmp_path, monkeypatch):
    """Redirect everything the tool writes outside the repo into tmp_path.

    Autouse on purpose: markers and the lock live in the developer's real
    ~/.claude, so a test that forgot to redirect them would write there.
    """
    home = tmp_path / "claude-home"
    home.mkdir()
    monkeypatch.setattr(config, "CLAUDE_HOME", home)
    monkeypatch.setattr(config, "REPO_FILE", home / "multirepo-sync.repo")
    monkeypatch.setattr(config, "CONFLICT_MARKER", home / "multirepo-sync.conflict")
    monkeypatch.setattr(config, "PENDING_MARKER", home / "multirepo-sync.pending")
    monkeypatch.setattr(config, "LOCK", home / "multirepo-sync.lock")
    return home
