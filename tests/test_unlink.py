import shutil

import pytest
from helpers import needs_symlinks, write

from claude_multirepo_sync import discover, unlink


@pytest.fixture
def repo(config_repo):
    write(config_repo / ".claude" / "CLAUDE.md", "central rules\n")
    return config_repo


def a_real_file(path, repo):
    path.write_text("mine\n", encoding="utf-8")


def our_link(path, repo):
    path.symlink_to(repo / ".claude" / "CLAUDE.md")


def someone_elses_link(path, repo):
    outside = path.parent / "elsewhere.md"
    outside.write_text("not ours\n", encoding="utf-8")
    path.symlink_to(outside)


def dangling_link(path, repo):
    path.symlink_to(repo / ".claude" / "gone.md")


@pytest.mark.parametrize(
    ("setup", "unlinked"),
    [
        pytest.param(a_real_file, False, id="a-real-file"),
        pytest.param(our_link, True, id="our-link", marks=needs_symlinks),
        pytest.param(someone_elses_link, False, id="someone-elses-link", marks=needs_symlinks),
        pytest.param(dangling_link, False, id="dangling-link", marks=needs_symlinks),
    ],
)
def test_only_our_own_resolvable_links_are_unlinked(repo, tmp_path, setup, unlinked):
    # A dangling link is left alone too: there is nothing to copy into its place.
    path = tmp_path / "CLAUDE.md"
    setup(path, repo)

    assert unlink.main(repo, [path]) == ([str(path)] if unlinked else [])


@needs_symlinks
def test_an_unlinked_file_outlives_the_repo(repo, tmp_path):
    # The whole point: the machine keeps its rules with the repo gone.
    link = tmp_path / "CLAUDE.md"
    our_link(link, repo)

    unlink.main(repo, [link])
    shutil.rmtree(repo)

    assert not link.is_symlink()
    assert link.read_text(encoding="utf-8") == "central rules\n"


@needs_symlinks
def test_unlinked_files_link_again_without_a_conflict(repo, tmp_path):
    # The round trip that makes moving the repo safe: discover finds the copy
    # identical to central and links it back, leaving no backup behind.
    local = tmp_path / "local"
    local.mkdir()
    our_link(local / "CLAUDE.md", repo)
    unlink.main(repo, [local / "CLAUDE.md"])
    backups = tmp_path / "backups"

    discover.sync_directory(local, repo / ".claude", backups, discover.Changes())

    assert (local / "CLAUDE.md").is_symlink()
    assert not list(backups.rglob("*.conflict-*"))
