"""Surfaces any unresolved markers, so they show up regardless
of which machine you're on.
"""

from pathlib import Path

CLAUDE_HOME = Path.home() / ".claude"
CONFLICT_MARKER = CLAUDE_HOME / "multirepo-sync.conflict"
PENDING_MARKER = CLAUDE_HOME / "multirepo-sync.pending"
ERROR_PREFIX = "multirepo-sync.error."
FENCE = "```"


def error_marker(command):
    """Where a crash in this command is recorded.

    One per command: a shared marker meant the next command to pass wiped a
    crash nobody had seen yet.
    """
    return CLAUDE_HOME / f"{ERROR_PREFIX}{command}"


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
            CONFLICT_MARKER,
            "WARNING: the config repo has an unresolved git conflict",
            [
                "It happened in a previous session or machine and was never resolved.",
                "Until it's resolved (cd into the config repo and run git status),",
                "the global CLAUDE.md and this machine's rules may be out of date.",
            ],
        ),
        show(
            PENDING_MARKER,
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
                f"WARNING: 'claude-mr-sync {marker.name[len(ERROR_PREFIX) :]}' "
                "hit an unexpected error",
                [
                    "This is likely a bug, not a normal conflict. See the traceback below.",
                ],
            )
            for marker in sorted(CLAUDE_HOME.glob(f"{ERROR_PREFIX}*"))
        ),
    ]
    return "\n\n".join(section for section in sections if section)


def main():
    text = report()
    if text:
        print(text)

