import shutil
from pathlib import Path

import pytest

from claude_multirepo_sync import config


def test_records_and_reads_back_the_path(config_repo):
    assert config.write_repo(config_repo) == config_repo
    assert config.read_repo() == config_repo


def test_a_relative_path_is_stored_absolute(config_repo, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert config.write_repo(Path(config_repo.name)) == config_repo


def test_nothing_is_read_before_the_machine_is_set_up():
    assert config.read_repo() is None


def test_a_path_that_is_not_a_repo_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not a git repository"):
        config.write_repo(tmp_path)

    assert config.read_repo() is None


def test_a_recorded_repo_that_disappeared_is_still_reported(config_repo):
    # Reported rather than swallowed: gone-since-configured needs a different
    # message from never-configured, and only the caller can phrase that.
    config.write_repo(config_repo)
    shutil.rmtree(config_repo)

    assert config.read_repo() == config_repo
    assert not config.is_repo(config_repo)
