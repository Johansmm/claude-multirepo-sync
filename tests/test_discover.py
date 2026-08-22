import pytest
from helpers import needs_symlinks, write

from claude_multirepo_sync import discover


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    central = tmp_path / "central"
    local = tmp_path / "local"
    backups = tmp_path / "backups"
    central.mkdir()
    local.mkdir()
    # Creating a symlink needs a Windows privilege this test has no reason to
    # depend on; what is under test is which outcomes get reported.
    monkeypatch.setattr(discover, "new_central_link", lambda target, central_file: True)
    return central, local, backups


@pytest.mark.parametrize(
    ("local_content", "central_content", "reported"),
    [
        pytest.param(None, "central rules\n", True, id="new-link"),
        pytest.param("mine\n", "theirs\n", True, id="conflict-replaced"),
        pytest.param("same\n", "same\n", False, id="identical"),
        pytest.param("mine\n", "", False, id="adopted"),
    ],
)
def test_only_real_content_changes_are_reported(dirs, local_content, central_content, reported):
    # Adopting or linking an identical file leaves the local bytes alone, so a
    # session holding them is still up to date and does not need telling.
    central, local, backups = dirs
    write(central / "CLAUDE.md", central_content)
    if local_content is not None:
        write(local / "CLAUDE.md", local_content)
    changes = discover.Changes()

    discover.sync_directory(local, central, backups, changes)

    assert bool(changes.changed) is reported


def dangling_link(local):
    """A local link left pointing at a path that does not exist."""
    link = local / "CLAUDE.md"
    link.symlink_to(local / "gone.md")
    return link


@needs_symlinks
def test_a_link_pointing_elsewhere_is_repointed(dirs):
    central, local, backups = dirs
    write(central / "CLAUDE.md", "central rules\n")
    dangling_link(local)
    changes = discover.Changes()

    discover.sync_directory(local, central, backups, changes)

    assert changes.changed == [str(local / "CLAUDE.md")]
    assert not changes.pending_conflict
    # A link carries no content, so there is nothing to keep a backup of.
    assert not list(local.glob("*.conflict-*"))
    assert not list(local.glob("*.discover-staging"))


@needs_symlinks
def test_a_link_that_cannot_be_repointed_is_left_alone(dirs, monkeypatch):
    monkeypatch.setattr(discover, "new_central_link", lambda target, central_file: False)
    central, local, backups = dirs
    write(central / "CLAUDE.md", "central rules\n")
    link = dangling_link(local)
    changes = discover.Changes()

    discover.sync_directory(local, central, backups, changes)

    assert changes.pending_relink == [str(link)]
    assert not changes.changed
    assert not changes.pending_conflict
    assert link.is_symlink()
    assert not list(local.glob("*.discover-staging"))


def test_a_conflict_backup_lands_under_the_backups_dir(dirs):
    central, local, backups = dirs
    write(central / "CLAUDE.md", "theirs\n")
    write(local / "CLAUDE.md", "mine\n")

    discover.sync_directory(local, central, backups, discover.Changes())

    kept = list(backups.glob("CLAUDE.md.conflict-*"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == "mine\n"
    assert not list(local.glob("*.conflict-*"))
    assert not list(local.glob("*.discover-staging"))


def test_a_nested_conflict_keeps_its_relative_path(dirs):
    # The relative path is what tells the two backups of a same-named file apart.
    central, local, backups = dirs
    write(central / "skills" / "review" / "SKILL.md", "theirs\n")
    write(local / "skills" / "review" / "SKILL.md", "mine\n")

    discover.sync_directory(local, central, backups, discover.Changes())

    assert list((backups / "skills" / "review").glob("SKILL.md.conflict-*"))


def test_a_backup_that_cannot_be_moved_stays_beside_the_file(dirs, monkeypatch):
    # These bytes exist nowhere else, so keeping them beats a tidy tree.
    def boom(src, dst):
        raise OSError("no room")

    monkeypatch.setattr(discover.shutil, "move", boom)
    central, local, backups = dirs
    write(central / "CLAUDE.md", "theirs\n")
    write(local / "CLAUDE.md", "mine\n")

    discover.sync_directory(local, central, backups, discover.Changes())

    kept = list(local.glob("CLAUDE.md.conflict-*"))
    assert len(kept) == 1
    assert kept[0].read_text(encoding="utf-8") == "mine\n"
    assert not list(local.glob("*.discover-staging"))
