"""Turns links back into real files - the inverse of what discover does.

Run it before moving, re-cloning or deleting the config repo. With the content
copied in place the machine keeps its rules whatever happens to the repo, and
the next discover finds the copies identical and links them back untouched.
"""

import os
import shutil
from pathlib import Path

from claude_multirepo_sync import config, discover


def points_into(link, repo):
    """Whether this is one of our links: it resolves inside the config repo."""
    target = discover.get_link_target(link)
    if target is None:
        return False
    return os.path.normcase(str(target)).startswith(os.path.normcase(str(repo)))


def links_under(local_root, repo):
    if not local_root.is_dir():
        return
    for path in sorted(local_root.rglob("*")):
        if path.is_symlink() and points_into(path, repo):
            yield path


def find_links(repo, search_roots):
    """Every link into the config repo, under ~/.claude and each opted-in project."""
    yield from links_under(config.CLAUDE_HOME, repo)
    for proj_dir, _slug in discover.opted_in_projects(repo, search_roots):
        yield from links_under(proj_dir, repo)


def materialize(link):
    """Replace a link with a copy of the file it points at.

    Copied beside it first: a failure then leaves the link untouched, rather
    than a machine with neither a link nor a file.
    """
    staged = link.with_name(link.name + ".unlink-staging")
    shutil.copy2(link, staged)
    link.unlink()
    staged.rename(link)


def main(repo, paths=None, extra_search_roots=None):
    search_roots = extra_search_roots if extra_search_roots else discover.DEFAULT_SEARCH_ROOTS
    links = [Path(p).expanduser() for p in paths] if paths else list(find_links(repo, search_roots))

    unlinked = []
    for link in links:
        if not link.is_symlink():
            print(f"Not a link, left alone: {link}")
        elif not points_into(link, repo):
            print(f"Not this tool's link, left alone: {link}")
        elif not link.exists():
            # Nothing to copy - whatever it pointed at is already gone.
            print(f"Points at nothing, left alone: {link}")
        else:
            materialize(link)
            unlinked.append(str(link))
            print(f"Unlinked: {link}")

    print(f"Unlinked {len(unlinked)} file(s).")
    return unlinked
