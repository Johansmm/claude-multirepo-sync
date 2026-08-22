"""Puts a local file into the config repo and links it - how a file joins.

The counterpart to unlink, and the only way in. Where the file lands is
derived from where it already is, so nothing has to be declared anywhere.
"""

import os
import shutil
from pathlib import Path

from claude_multirepo_sync import config, discover


def enclosing_project(path):
    """The git project a file sits in, or None."""
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent
    return None


def destination(path, repo):
    """Where in the config repo this file belongs.

    Under ~/.claude it mirrors onto .claude/; inside a git project, onto that
    project's projects/<slug>/. Raises ValueError when it is neither.
    """
    if path.is_relative_to(config.CLAUDE_HOME):
        return repo / ".claude" / path.relative_to(config.CLAUDE_HOME)

    project = enclosing_project(path)
    if project is None:
        raise ValueError(f"{path} is neither under ~/.claude nor inside a git project")
    slug = discover.project_slug(project)
    if not slug:
        raise ValueError(f"{project} has no origin remote, so there is no slug to file it under")
    return repo / "projects" / slug / path.relative_to(project)


def main(repo, paths):
    linked = []
    for raw in paths:
        # abspath, not resolve: a path is normalised without following the very
        # link we are about to check for.
        path = Path(os.path.abspath(Path(raw).expanduser()))

        if path.is_symlink():
            print(f"Already a link, left alone: {path}")
            continue
        if not path.is_file():
            print(f"Not a file, left alone: {path}")
            continue

        try:
            central = destination(path, repo)
        except ValueError as e:
            print(f"Skipped: {e}")
            continue

        if central.is_file() and discover.file_hash(central) != discover.file_hash(path):
            print(f"Skipped: {central} already holds different content - merge them yourself.")
            continue

        central.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, central)

        pending = []
        staged = discover.relink(path, central, path.name + ".link-staging", pending)
        if staged:
            staged.unlink()
            linked.append(str(path))
            print(f"Linked: {path} -> {central}")
        else:
            print(f"Copied to {central}, but couldn't link it here (missing privilege).")

    print(f"Linked {len(linked)} file(s).")
    return linked
