"""Surfaces any unresolved markers, so they show up regardless
of which machine you're on.
"""

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

