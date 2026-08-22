import pytest
from helpers import needs_symlinks, run_git, write

from claude_multirepo_sync import link


def make_project(tmp_path):
    path = tmp_path / "widget"
    path.mkdir(parents=True)
    run_git(path, "init", "-q")
    run_git(path, "remote", "add", "origin", "git@github.com:acme/widget.git")
    return path


def global_file(config_repo, claude_home, tmp_path, rel):
    return write(claude_home / rel, "mine\n")


def project_file(config_repo, claude_home, tmp_path, rel):
    return write(make_project(tmp_path) / rel, "mine\n")


def central_holds_other_content(config_repo, claude_home, tmp_path):
    write(config_repo / ".claude" / "CLAUDE.md", "theirs\n")
    return write(claude_home / "CLAUDE.md", "mine\n")


def belongs_nowhere(config_repo, claude_home, tmp_path):
    return write(tmp_path / "loose" / "notes.md", "mine\n")


def already_a_link(config_repo, claude_home, tmp_path):
    central = write(config_repo / ".claude" / "CLAUDE.md", "central\n")
    local = claude_home / "CLAUDE.md"
    local.symlink_to(central)
    return local


def contents(root):
    return {path: path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize(
    ("place", "rel", "expected"),
    [
        pytest.param(global_file, "CLAUDE.md", ".claude/CLAUDE.md", id="global"),
        pytest.param(
            global_file,
            "skills/review/SKILL.md",
            ".claude/skills/review/SKILL.md",
            id="global-nested",
        ),
        pytest.param(
            project_file,
            "CLAUDE.local.md",
            "projects/github.com_acme_widget/CLAUDE.local.md",
            id="project",
        ),
        pytest.param(
            project_file,
            ".claude/settings.local.json",
            "projects/github.com_acme_widget/.claude/settings.local.json",
            id="project-nested",
        ),
    ],
)
def test_a_file_lands_where_its_own_location_says(config_repo, claude_home, tmp_path, place, rel, expected):
    # Every destination but the first needs directories the repo does not have yet.
    local = place(config_repo, claude_home, tmp_path, rel)

    link.main(config_repo, [local])

    assert (config_repo / expected).read_text(encoding="utf-8") == "mine\n"


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(central_holds_other_content, id="central-holds-other-content"),
        pytest.param(belongs_nowhere, id="belongs-nowhere"),
        pytest.param(already_a_link, id="already-a-link", marks=needs_symlinks),
    ],
)
def test_nothing_moves_when_a_file_cannot_join(config_repo, claude_home, tmp_path, setup):
    local = setup(config_repo, claude_home, tmp_path)
    before = contents(config_repo)
    local_before = local.read_bytes()

    assert link.main(config_repo, [local]) == []
    assert contents(config_repo) == before
    assert local.read_bytes() == local_before


@needs_symlinks
def test_the_local_file_becomes_a_link(config_repo, claude_home):
    local = write(claude_home / "CLAUDE.md", "mine\n")

    assert link.main(config_repo, [local]) == [str(local)]
    assert local.is_symlink()
    assert local.read_text(encoding="utf-8") == "mine\n"
    assert not list(claude_home.glob("*.link-staging"))
