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
    sync_dir = home / "multirepo-sync"
    monkeypatch.setattr(config, "CLAUDE_HOME", home)
    monkeypatch.setattr(config, "REPO_FILE", home / "multirepo-sync.repo")
    monkeypatch.setattr(config, "SYNC_DIR", sync_dir)
    monkeypatch.setattr(config, "BACKUPS_DIR", sync_dir / "backups")
    monkeypatch.setattr(config, "SYNC_MARKER", sync_dir / "sync")
    monkeypatch.setattr(config, "PENDING_MARKER", sync_dir / "pending")
    monkeypatch.setattr(config, "LOCK", sync_dir / "lock")
    config.ensure_sync_dir()
    return home


@pytest.fixture
def config_repo(tmp_path):
    """A directory that satisfies config.is_repo(), for anything that only needs
    the repo to exist.
    """
    path = tmp_path / "config-repo"
    (path / ".git").mkdir(parents=True)
    return path.resolve()
