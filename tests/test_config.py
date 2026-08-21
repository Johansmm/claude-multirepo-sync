import shutil
from pathlib import Path

import pytest

from claude_multirepo_sync import config


def make_repo(path):
    (path / ".git").mkdir(parents=True)
    return path.resolve()


def test_records_and_reads_back_the_path(tmp_path):
    repo = make_repo(tmp_path / "config-repo")

    assert config.write_repo(repo) == repo
    assert config.read_repo() == repo


def test_a_relative_path_is_stored_absolute(tmp_path, monkeypatch):
    repo = make_repo(tmp_path / "config-repo")
    monkeypatch.chdir(tmp_path)

    assert config.write_repo(Path("config-repo")) == repo


def test_nothing_is_read_before_the_machine_is_set_up():
    assert config.read_repo() is None


def test_a_path_that_is_not_a_repo_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not a git repository"):
        config.write_repo(tmp_path)

    assert config.read_repo() is None


def test_a_recorded_repo_that_disappeared_is_still_reported(tmp_path):
    # Reported rather than swallowed: gone-since-configured needs a different
    # message from never-configured, and only the caller can phrase that.
    repo = make_repo(tmp_path / "config-repo")
    config.write_repo(repo)
    shutil.rmtree(repo)

    assert config.read_repo() == repo
    assert not config.is_repo(repo)
