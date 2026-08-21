"""Surfaces any unresolved markers, so they show up regardless
of which machine you're on.
"""

from pathlib import Path

from claude_multirepo_sync import config

FENCE = "```"


def show(marker, title, body_lines):
    if not marker.exists():
        return ""
    return "\n".join(
        [
            f"## {title}",
            "",
            *body_lines,
            "Marker content:",
            FENCE,
            marker.read_text(encoding="utf-8").rstrip("\n"),
            FENCE,
        ]
    )


def describe(backup):
    """Where a backup came from, told from its own path.

    The path is the whole record: <scope>/<relative path>.conflict-<stamp>, the
    scope being ".claude" for the global mirror and the project's slug for the
    rest. A project's root on disk stays out of it - the slug names the project
    without ambiguity, and looking the root up would mean the scan check exists
    to avoid.
    """
    rel = backup.relative_to(config.BACKUPS_DIR)
    scope = rel.parts[0]
    source = Path(*rel.parts[1:])
    source = source.with_name(source.name.rsplit(".conflict-", 1)[0])
    if scope == ".claude":
        return str(config.CLAUDE_HOME / source), Path(".claude") / source
    return f"project {scope}, {source}", Path("projects") / scope / source


def backups():
    """The conflict backups still on disk, or "" when there are none.

    Read back off the directory instead of from a marker: deleting a backup is
    how you say the merge is done, and that has to hold whatever wrote it.
    """
    kept = sorted(path for path in config.BACKUPS_DIR.rglob("*") if path.is_file())
    if not kept:
        return ""

    repo = config.read_repo()
    entries = []
    for backup in kept:
        local, in_repo = describe(backup)
        entries.append(f"- {local}")
        if repo:
            entries.append(f"  linked to: {repo / in_repo}")
        entries.append(f"  backup:    {backup}")

    return "\n".join(
        [
            "## NOTICE: there are conflict backups waiting to be merged",
            "",
            "Your copy of these files differed from the central one. The central copy is",
            "what is linked now, and yours was moved aside rather than dropped. Merge",
            "anything worth keeping into the linked file, then delete the backup -",
            "deleting it is what clears this notice.",
            "",
            *entries,
        ]
    )


def report():
    """Everything still unresolved, or "" when there is nothing to say.

    Returned rather than printed: session-sync sends it to stderr to wake the
    live session, while check prints it as session context.
    """
    sections = [
        show(
            config.CONFLICT_MARKER,
            "WARNING: the config repo has an unresolved git conflict",
            [
                "It happened in a previous session or machine and was never resolved.",
                "Until it's resolved (cd into the config repo and run git status),",
                "the global CLAUDE.md and this machine's rules may be out of date.",
            ],
        ),
        show(
            config.PENDING_MARKER,
            "NOTICE: there are config files not yet linked on this machine",
            [
                "They couldn't be created due to missing privilege (symlink). This doesn't",
                "block anything - it's your call to re-run discover (e.g. with privilege)",
                "whenever you want to resolve it.",
            ],
        ),
        backups(),
        *(
            show(
                marker,
                f"WARNING: 'claude-mr-sync {marker.name[len(config.ERROR_PREFIX) :]}' "
                "hit an unexpected error",
                [
                    "This is likely a bug, not a normal conflict. See the traceback below.",
                ],
            )
            for marker in sorted(config.SYNC_DIR.glob(f"{config.ERROR_PREFIX}*"))
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def main():
    text = report()
    if text:
        print(text)

