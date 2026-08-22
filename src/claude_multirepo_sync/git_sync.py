"""Syncs the config repo itself (not the mirrored projects).

A failure is named by the step that stopped, never by reading what git said:
the steps are ours and few, git's wording is unbounded and gets translated.
"""

import platform
import subprocess

from claude_multirepo_sync import config
from claude_multirepo_sync.errors import SyncError

# What each failure leaves behind - not why it happened.
STEP_HINTS = {
    "staging": "Nothing was committed; the working tree is untouched.",
    "commit": "The change is staged but unpublished.",
    "connect": "Origin was unreachable, so nothing was pulled or pushed.",
    "pull": "Nothing was merged, so nothing is half-done.",
    "push check": "Nothing was pushed.",
    "push": "The change is committed locally; the next sync retries.",
    "merge": "A merge is half-finished. Resolve it by hand: git status.",
}


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


def step_failure(step, repo, out="", err=""):
    """The one failure a caller ever raises: which step stopped, what it left,
    and git's own words.
    """
    return SyncError(
        f"The config sync stopped at: {step}",
        STEP_HINTS[step],
        out,
        err,
        f"Config repo: {repo}",
        marker=config.SYNC_MARKER,
    )


def commit_local(repo):
    """Commit whatever changed. Everything here is config, so everything is publishable."""
    if merge_in_progress(repo):
        # Staging a half-merged tree would mark the conflicts resolved and
        # commit the markers with them.
        raise step_failure("merge", repo)

    code, out, err = run_git(repo, "add", "-A")
    if code != 0:
        # Unchecked, this fails silently: nothing gets staged, the check below
        # finds nothing, and the config never syncs again.
        raise step_failure("staging", repo, out, err)

    # The add re-stages the working tree, so the index asks what the commit will answer.
    code, _, _ = run_git(repo, "diff", "--cached", "--quiet")
    if code == 0:
        return

    code, out, err = run_git(repo, "commit", "-m", f"auto: {platform.node()}", "-q")
    if code != 0:
        raise step_failure("commit", repo, out, err)


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
        raise step_failure("push check", repo, out, err)
    return out.strip() != "0"


def main(repo):
    commit_local(repo)

    # Asked up front so no later failure can be the network. One handshake, off
    # the critical path: the hooks that run this are backgrounded.
    code, out, err = run_git(repo, "ls-remote", "origin")
    if code != 0:
        raise step_failure("connect", repo, out, err)

    # Plain merge, not --rebase: a machine with no pull strategy configured would
    # otherwise have git refuse to reconcile at all.
    code, out, err = run_git(repo, "pull", "--no-rebase", "origin", "main")
    # A failure with nothing published yet is just the first push, not a problem.
    if code != 0 and has_remote_main(repo):
        raise step_failure("merge" if merge_in_progress(repo) else "pull", repo, out, err)

    if has_unpushed_commits(repo):
        code, out, err = run_git(repo, "push", "origin", "main")
        if code != 0:
            raise step_failure("push", repo, out, err)

    config.SYNC_MARKER.unlink(missing_ok=True)
