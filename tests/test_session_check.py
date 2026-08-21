import pytest

from claude_multirepo_sync import config, session_check


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "config-repo"
    (path / ".git").mkdir(parents=True)
    config.write_repo(path)
    return path.resolve()


def make_backup(rel):
    path = config.BACKUPS_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("mine\n", encoding="utf-8")
    return path


def test_stays_silent_with_nothing_unresolved():
    assert session_check.report() == ""


def test_a_global_backup_names_the_file_it_came_from(repo):
    backup = make_backup(".claude/CLAUDE.md.conflict-20260821-235205")

    report = session_check.report()

    assert "waiting to be merged" in report
    assert str(config.CLAUDE_HOME / "CLAUDE.md") in report
    assert str(repo / ".claude" / "CLAUDE.md") in report
    assert str(backup) in report


def test_a_project_backup_is_named_by_its_slug(repo):
    # check never learns where that project sits on disk; the slug is enough.
    make_backup("github.com_acme_widget/CLAUDE.local.md.conflict-20260822-101500")

    report = session_check.report()

    assert "project github.com_acme_widget, CLAUDE.local.md" in report
    assert str(repo / "projects" / "github.com_acme_widget" / "CLAUDE.local.md") in report


def test_a_nested_backup_keeps_its_relative_path(repo):
    make_backup(".claude/skills/review/SKILL.md.conflict-20260822-101500")

    report = session_check.report()

    assert str(config.CLAUDE_HOME / "skills" / "review" / "SKILL.md") in report


def test_the_notice_goes_once_the_backup_is_deleted(repo):
    backup = make_backup(".claude/CLAUDE.md.conflict-20260821-235205")
    assert session_check.report() != ""

    backup.unlink()

    assert session_check.report() == ""


def test_the_central_path_is_left_out_when_no_repo_is_recorded():
    backup = make_backup(".claude/CLAUDE.md.conflict-20260821-235205")

    report = session_check.report()

    assert str(backup) in report
    assert "linked to:" not in report
