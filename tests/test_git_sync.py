import os
import subprocess

import pytest
from helpers import run_git, write

from claude_multirepo_sync import config, git_sync
from claude_multirepo_sync.errors import SyncError


@pytest.fixture
def repo(tmp_path, monkeypatch):
    # Isolate from the developer's git config - core.hooksPath or gpgsign would leak in.
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Test\n\temail = test@example.invalid\n[commit]\n\tgpgsign = false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", os.devnull)

    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    run_git(tmp_path, "init", "--bare", "-b", "main", str(remote))
    run_git(tmp_path, "clone", str(remote), str(work))

    write(work / ".claude" / "CLAUDE.md", "central rules\n")
    write(work / "projects" / "some-slug" / "CLAUDE.local.md", "project rules\n")
    run_git(work, "add", "-A")
    run_git(work, "commit", "-m", "init")
    run_git(work, "push", "-u", "origin", "main")

    return work


def commit_files(repo, paths):
    if not paths:
        return
    for path in paths:
        write(repo / path, "edited\n")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "docs: edited by hand")


def diverge_remote(tmp_path, path, content):
    """Land a commit on origin/main from a second clone, so the repo under test falls behind."""
    other = tmp_path / "other"
    if not other.exists():
        run_git(tmp_path, "clone", str(tmp_path / "remote.git"), str(other))
    write(other / path, content)
    run_git(other, "add", "-A")
    run_git(other, "commit", "-m", "from another machine")
    run_git(other, "push", "origin", "main")


@pytest.mark.parametrize(
    ("edits", "expected"),
    [
        pytest.param([".claude/CLAUDE.md"], [".claude/CLAUDE.md"], id="edited-file"),
        pytest.param(["notes.md"], ["notes.md"], id="new-file-at-the-root"),
        pytest.param([], [], id="nothing-changed"),
    ],
)
def test_commit_covers_everything_that_changed(repo, edits, expected):
    for path in edits:
        write(repo / path, "updated\n")
    head_before = run_git(repo, "rev-parse", "HEAD").stdout.strip()

    git_sync.commit_local(repo)

    committed = run_git(repo, "diff", "--name-only", f"{head_before}..HEAD").stdout.split()
    assert committed == expected


def test_commit_refuses_a_half_merged_tree(repo, tmp_path):
    # Staging it would mark the conflicts resolved and commit the markers with them.
    diverge_remote(tmp_path, ".claude/CLAUDE.md", "their version\n")
    write(repo / ".claude" / "CLAUDE.md", "our version\n")
    run_git(repo, "commit", "-am", "ours")
    subprocess.run(
        ["git", "-C", str(repo), "pull", "--no-rebase", "origin", "main"],
        capture_output=True,
        check=False,
    )
    assert (repo / ".git" / "MERGE_HEAD").exists()

    with pytest.raises(SyncError) as excinfo:
        git_sync.commit_local(repo)
    assert excinfo.value.marker == config.SYNC_MARKER
    assert "<<<<<<<" not in run_git(repo, "show", "HEAD:.claude/CLAUDE.md").stdout


def test_sync_reconciles_without_a_pull_strategy_configured(repo, tmp_path):
    # A fresh machine has no pull.rebase set; git then refuses to reconcile at all.
    diverge_remote(tmp_path, ".claude/from-elsewhere.md", "elsewhere\n")
    write(repo / ".claude" / "CLAUDE.md", "central rules, updated\n")

    git_sync.main(repo)

    assert not config.SYNC_MARKER.exists()
    assert (repo / ".claude" / "from-elsewhere.md").exists()
    pushed = run_git(repo, "show", "--name-only", "--format=", "origin/main~1").stdout
    assert ".claude/CLAUDE.md" in pushed


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        pytest.param([], False, id="nothing-ahead"),
        pytest.param([".claude/new-skill.md"], True, id="claude"),
        pytest.param(["projects/some-slug/settings.local.json"], True, id="projects"),
    ],
)
def test_push_only_when_something_is_ahead(repo, paths, expected):
    commit_files(repo, paths)
    assert git_sync.has_unpushed_commits(repo) is expected


def test_push_allowed_when_there_is_no_origin_main_yet(repo):
    run_git(repo, "remote", "remove", "origin")
    assert git_sync.has_unpushed_commits(repo) is True


def test_first_push_is_not_treated_as_a_conflict(repo, tmp_path):
    # With nothing published yet the pull fails, but that is not a conflict.
    empty = tmp_path / "empty.git"
    run_git(tmp_path, "init", "--bare", "-b", "main", str(empty))
    run_git(repo, "remote", "set-url", "origin", str(empty))
    run_git(repo, "update-ref", "-d", "refs/remotes/origin/main")

    git_sync.main(repo)

    assert not config.SYNC_MARKER.exists()
    assert run_git(repo, "ls-remote", str(empty), "main").stdout.strip()


def test_an_unreachable_remote_is_not_called_a_conflict(repo, tmp_path):
    # The failure that started all this: a transport problem reported as a merge.
    run_git(repo, "remote", "set-url", "origin", str(tmp_path / "gone.git"))

    with pytest.raises(SyncError) as excinfo:
        git_sync.main(repo)

    message = str(excinfo.value)
    assert "stopped at: connect" in message
    assert "merge" not in message.lower()
    assert not git_sync.merge_in_progress(repo)


def test_a_real_merge_conflict_is_reported_as_one(repo, tmp_path):
    diverge_remote(tmp_path, ".claude/CLAUDE.md", "their version\n")
    write(repo / ".claude" / "CLAUDE.md", "our version\n")

    with pytest.raises(SyncError) as excinfo:
        git_sync.main(repo)

    assert "stopped at: merge" in str(excinfo.value)
    assert git_sync.merge_in_progress(repo)
