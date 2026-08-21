import tempfile
from pathlib import Path

import pytest

from claude_multirepo_sync import discover


def symlinks_available():
    with tempfile.TemporaryDirectory() as tmp:
        try:
            Path(tmp, "link").symlink_to(Path(tmp, "target"))
        except OSError:
            return False
    return True


SYMLINKS_AVAILABLE = symlinks_available()


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    central = tmp_path / "central"
    local = tmp_path / "local"
    central.mkdir()
    local.mkdir()
    # Creating a symlink needs a Windows privilege this test has no reason to
    # depend on; what is under test is which outcomes get reported.
    monkeypatch.setattr(discover, "new_central_link", lambda target, central_file: True)
    return central, local


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
    central, local = dirs
    (central / "CLAUDE.md").write_text(central_content, encoding="utf-8")
    if local_content is not None:
        (local / "CLAUDE.md").write_text(local_content, encoding="utf-8")
    changes = discover.Changes()

    discover.sync_directory(local, central, changes)

    assert bool(changes.changed) is reported


def dangling_link(local):
    """A local link left pointing at a path that does not exist."""
    link = local / "CLAUDE.md"
    link.symlink_to(local / "gone.md")
    return link


@pytest.mark.skipif(not SYMLINKS_AVAILABLE, reason="creating a symlink needs a Windows privilege")
def test_a_link_pointing_elsewhere_is_repointed(dirs):
    central, local = dirs
    (central / "CLAUDE.md").write_text("central rules\n", encoding="utf-8")
    dangling_link(local)
    changes = discover.Changes()

    discover.sync_directory(local, central, changes)

    assert changes.changed == [str(local / "CLAUDE.md")]
    assert not changes.pending_conflict
    # A link carries no content, so there is nothing to keep a backup of.
    assert not list(local.glob("*.conflict-*"))
    assert not list(local.glob("*.discover-staging"))


@pytest.mark.skipif(not SYMLINKS_AVAILABLE, reason="creating a symlink needs a Windows privilege")
def test_a_link_that_cannot_be_repointed_is_left_alone(dirs, monkeypatch):
    monkeypatch.setattr(discover, "new_central_link", lambda target, central_file: False)
    central, local = dirs
    (central / "CLAUDE.md").write_text("central rules\n", encoding="utf-8")
    link = dangling_link(local)
    changes = discover.Changes()

    discover.sync_directory(local, central, changes)

    assert changes.pending_relink == [str(link)]
    assert not changes.changed
    assert not changes.pending_conflict
    assert link.is_symlink()
    assert not list(local.glob("*.discover-staging"))
