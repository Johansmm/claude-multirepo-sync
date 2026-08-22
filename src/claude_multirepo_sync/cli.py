"""Entry point for the `claude-mr-sync` command."""

import argparse
import sys
import traceback
from pathlib import Path

from claude_multirepo_sync import config, discover, git_sync, session_check, session_sync
from claude_multirepo_sync.errors import SyncError

DESCRIPTIONS = {
    "discover": "Mirror .claude/ and opted-in projects/ onto this machine.",
    "git-sync": "Sync the config repo itself (pull/commit/push).",
    "check": "Show anything left unresolved: a stalled sync, pending links, backups.",
    "session-sync": "Sync the repo and mirror it onto this machine, then report once.",
    "set-repo": "Record where the config repo lives on this machine.",
}

# Wakes a live Claude Code session when the hook runs with asyncRewake.
WAKE_EXIT_CODE = 2


def build_parser():
    parser = argparse.ArgumentParser(
        prog="claude-mr-sync", description="Sync Claude Code configuration from a git repo you own."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name in ("discover", "session-sync"):
        scanner = subparsers.add_parser(
            name, help=DESCRIPTIONS[name], description=DESCRIPTIONS[name]
        )
        scanner.add_argument(
            "--search-root",
            action="append",
            type=Path,
            dest="search_roots",
            help="Root to scan for git repos (repeatable). Defaults to $HOME.",
        )
    subparsers.add_parser(
        "git-sync", help=DESCRIPTIONS["git-sync"], description=DESCRIPTIONS["git-sync"]
    )
    subparsers.add_parser("check", help=DESCRIPTIONS["check"], description=DESCRIPTIONS["check"])
    setter = subparsers.add_parser(
        "set-repo", help=DESCRIPTIONS["set-repo"], description=DESCRIPTIONS["set-repo"]
    )
    setter.add_argument("path", type=Path, help="The config repo to sync from now on.")
    return parser


def resolve_repo():
    """Where the synced files live."""
    repo = config.read_repo()
    if repo is None:
        raise SystemExit("No config repo set. Run: claude-mr-sync set-repo PATH")
    if not config.is_repo(repo):
        raise SystemExit(f"{config.REPO_FILE} points at {repo}, which is no longer a repository.")
    return repo


def set_repo(path):
    try:
        repo = config.write_repo(path)
    except ValueError as e:
        # A typo, not a crash - no traceback and no error marker for it.
        raise SystemExit(str(e)) from e
    print(f"Config repo set to {repo}")


def run(args):
    """Everything worth telling a live session about, or "" to stay silent."""
    if args.command == "set-repo":
        set_repo(args.path)
        return ""
    if args.command == "check":
        # The only command that runs without a working repo: it reads what the
        # others left behind, and the repo pointer only to name paths.
        session_check.main()
        return ""

    repo = resolve_repo()
    if args.command == "discover":
        discover.main(repo, extra_search_roots=args.search_roots)
    elif args.command == "git-sync":
        git_sync.main(repo)
    elif args.command == "session-sync":
        return session_sync.main(repo, extra_search_roots=args.search_roots)
    return ""


def main():
    args = build_parser().parse_args()
    config.ensure_sync_dir()
    crashed = config.error_marker(args.command)

    try:
        report = run(args)
        # Cleared after the report is built, never before: the report is what tells
        # you this command crashed last time, and clearing it here is what says the
        # retry worked. Clearing on the way in would hide the crash forever.
        crashed.unlink(missing_ok=True)
        if report:
            # Silence when there is nothing to say: every wake costs a model turn.
            print(report, file=sys.stderr)
            sys.exit(WAKE_EXIT_CODE)
    except SyncError as e:
        e.record()
        # No traceback here - an expected failure isn't a crash.
        print(f"{e}\nSee {e.marker}", file=sys.stderr)
        sys.exit(1)
    except Exception:
        # One marker per command, so a passing command never erases another's crash.
        crashed.write_text(
            f"Unexpected error running 'claude-mr-sync {args.command}':\n\n"
            + traceback.format_exc(),
            encoding="utf-8",
        )
        raise


if __name__ == "__main__":
    main()
