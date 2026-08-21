import sys

import pytest

from claude_multirepo_sync import cli, session_check


def invoke(monkeypatch, command, behaviour):
    monkeypatch.setattr(cli, "run", behaviour)
    monkeypatch.setattr(sys, "argv", ["claude-mr-sync", command])


def test_a_crash_is_recorded_under_its_own_command(monkeypatch):
    def boom(args):
        raise RuntimeError("kaboom")

    invoke(monkeypatch, "discover", boom)

    with pytest.raises(RuntimeError):
        cli.main()

    assert "kaboom" in session_check.error_marker("discover").read_text(encoding="utf-8")


def test_a_passing_command_leaves_another_ones_crash_alone(monkeypatch):
    # A shared marker meant the next command to pass wiped a crash nobody had seen.
    stale = session_check.error_marker("git-sync")
    stale.write_text("crashed last time\n", encoding="utf-8")
    invoke(monkeypatch, "check", lambda args: "")

    cli.main()

    assert stale.exists()


def test_a_crash_is_reported_before_it_is_cleared(monkeypatch):
    # Cleared because this run worked, not because someone looked at it.
    crashed = session_check.error_marker("session-sync")
    crashed.write_text("crashed last time\n", encoding="utf-8")
    invoke(monkeypatch, "session-sync", lambda args: session_check.report())

    with pytest.raises(SystemExit) as excinfo:
        cli.main()

    assert excinfo.value.code == cli.WAKE_EXIT_CODE
    assert not crashed.exists()


def test_a_bad_repo_path_is_not_treated_as_a_crash(tmp_path, monkeypatch):
    # A typo is the user's, not the tool's: no traceback and no crash marker.
    monkeypatch.setattr(sys, "argv", ["claude-mr-sync", "set-repo", str(tmp_path)])

    with pytest.raises(SystemExit):
        cli.main()

    assert not session_check.error_marker("set-repo").exists()
