"""Syncs the config repo itself (not the mirrored projects)."""

import platform
import subprocess

from claude_multirepo_sync import config
from claude_multirepo_sync.errors import SyncError


def run_git(repo, *args):
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def has_remote_main(repo):
    code, _, _ = run_git(repo, "rev-parse", "--verify", "--quiet", "origin/main")
    return code == 0


def merge_in_progress(repo):
    code, _, _ = run_git(repo, "rev-parse", "--verify", "--quiet", "MERGE_HEAD")
    return code == 0


def commit_local(repo):
    """Commit whatever changed. Everything here is config, so everything is publishable."""
    if merge_in_progress(repo):
        # Staging a half-merged tree marks the conflicts resolved, which would
        # commit the markers along with them.
        raise SyncError(
            "CONFLICT left by an earlier pull",
            f"Resolve it by hand: cd {repo}; git status",
            marker=config.CONFLICT_MARKER,
        )

    code, out, err = run_git(repo, "add", "-A")
    if code != 0:
        # Unchecked, this fails silently: nothing gets staged, the check below
        # finds nothing, and the config never syncs again.
        raise SyncError("ERROR staging config repo changes", out, err, marker=config.CONFLICT_MARKER)

    # The add re-stages the working tree, so the index asks what the commit will answer.
    code, _, _ = run_git(repo, "diff", "--cached", "--quiet")
    if code == 0:
        return

    code, out, err = run_git(repo, "commit", "-m", f"auto: {platform.node()}", "-q")
    if code != 0:
        raise SyncError("ERROR committing config repo changes", out, err, marker=config.CONFLICT_MARKER)


def has_unpushed_commits(repo):
    """Whether there is anything ahead of origin/main.

    Every commit here is publishable: these files are live symlinks on every machine, so
    they have no local-only state worth holding back.
    """
    if not has_remote_main(repo):
        # Nothing published yet - first push ever, publish everything.
        return True

    code, out, err = run_git(repo, "rev-list", "--count", "origin/main..HEAD")
    if code != 0:
        raise SyncError("ERROR counting the commits ahead of origin/main", err, marker=config.CONFLICT_MARKER)
    return out.strip() != "0"


def main(repo):
    commit_local(repo)

    # Plain merge, not --rebase: a machine with no pull strategy configured would
    # otherwise have git refuse to reconcile at all.
    code, out, err = run_git(repo, "pull", "--no-rebase", "origin", "main")
    # A failure with nothing published yet is just the first push, not a conflict.
    if code != 0 and has_remote_main(repo):
        _, status_out, _ = run_git(repo, "status", "--porcelain", "--branch")
        raise SyncError(
            "CONFLICT in git pull",
            out,
            err,
            status_out,
            f"Resolve it by hand: cd {repo}; git status",
            marker=config.CONFLICT_MARKER,
        )

    if config.CONFLICT_MARKER.exists():
        config.CONFLICT_MARKER.unlink()

    if has_unpushed_commits(repo):
        code, out, err = run_git(repo, "push", "origin", "main")
        if code != 0:
            raise SyncError(
                "ERROR in git push (someone probably pushed first)", out, err, marker=config.CONFLICT_MARKER
            )
