"""Mirrors this repo's ".claude/" onto ~/.claude, and each opted-in
"projects/<slug>/" onto that project's root, file by file.
"""

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from claude_multirepo_sync import config

DEFAULT_SEARCH_ROOTS = [Path.home()]
MAX_DEPTH = 4


def get_slug(remote_url):
    slug = re.sub(r"^[a-zA-Z]+://", "", remote_url)
    slug = re.sub(r"^[a-zA-Z0-9_.-]+@", "", slug)
    slug = re.sub(r"\.git$", "", slug)
    slug = re.sub(r"[:/\\]+", "_", slug)
    return slug


def get_link_target(path):
    if not path.is_symlink():
        return None
    target = path.readlink()
    if not target.is_absolute():
        target = path.parent / target
    # Windows readlink() can return an extended-length "\\?\" path even for
    # a plain link - strip it so string comparisons against a normal path
    # (built via os.path.normcase, not resolve()) still match.
    if os.name == "nt":
        target_str = str(target)
        if target_str.startswith("\\\\?\\"):
            target = Path(target_str[4:])
    return target


def find_git_dirs(root, max_depth):
    """Yield project dirs (parents of a .git) under root, up to max_depth
    levels deep. Uses os.walk with early pruning - unlike Path.rglob, it
    never descends past max_depth, and tolerates a directory disappearing
    mid-scan (errors -> skip that branch instead of raising).
    """
    for dirpath, dirnames, _ in os.walk(root, onerror=lambda _e: None):
        depth = len(Path(dirpath).relative_to(root).parts)
        if depth >= max_depth:
            dirnames[:] = []
            continue
        if ".git" in dirnames:
            yield Path(dirpath)


def project_slug(proj_dir):
    """The slug for a project on disk, or "" when it has no origin to derive one from."""
    result = subprocess.run(
        ["git", "-C", str(proj_dir), "config", "--get", "remote.origin.url"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    remote = result.stdout.strip()
    return get_slug(remote) if remote else ""


def opted_in_projects(repo, search_roots):
    """Yield (project dir, slug) for each project the config repo has a folder for.

    Nothing syncs just because a git repo exists on disk: the folder in the
    repo is the opt-in, and the slug is what matches the two.
    """
    projects_central = repo / "projects"
    if not projects_central.is_dir():
        return
    central_slugs = {p.name for p in projects_central.iterdir() if p.is_dir()}
    if not central_slugs:
        return

    for root in search_roots:
        if not root.is_dir():
            continue
        for proj_dir in find_git_dirs(root, MAX_DEPTH):
            slug = project_slug(proj_dir)
            if slug in central_slugs:
                yield proj_dir, slug


def remove_orphan_links(local_root, central_dir, changes):
    if not local_root.is_dir():
        return
    central_norm = os.path.normcase(str(central_dir))
    for path in local_root.rglob("*"):
        if not path.is_symlink():
            continue
        target = get_link_target(path)
        if (
            target
            and os.path.normcase(str(target)).startswith(central_norm)
            and not target.exists()
        ):
            path.unlink()
            changes.changed.append(str(path))
            print(f"Cleaned orphan: {path}")


def new_central_link(target_path, central_file):
    try:
        target_path.symlink_to(central_file)
        return True
    except OSError:
        return False


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def relink(target, central_file, backup_name, pending_list):
    """Rename target aside, then try to link. Roll back the rename if the link
    can't be created, so nothing is ever left half-done. Returns the backup
    path on success (so the caller can keep or discard it), else None.
    """
    backup = target.with_name(backup_name)
    target.rename(backup)
    if new_central_link(target, central_file):
        return backup
    backup.rename(target)
    pending_list.append(str(target))
    return None


def stash(staged, destination):
    """Move a staged file under the backups directory, stamped with the time.

    Falls back to leaving it beside the file it came from if the move fails:
    these bytes exist nowhere else, so keeping them beats a tidy tree.
    """
    # Naive local time is fine here - it's just a filename suffix.
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")  # noqa: DTZ005
    name = f"{destination.name}.conflict-{stamp}"
    backup = destination.with_name(name)
    try:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(backup))
    except OSError:
        backup = staged.with_name(name)
        staged.rename(backup)
    return backup


@dataclass
class Changes:
    """What a pass did, and what it could not do.

    "changed" is only content that differs on disk now: a new link or a
    replaced conflict. Linking an identical file leaves the local bytes alone,
    so a session holding them is still up to date.
    """

    changed: list = field(default_factory=list)
    pending_new: list = field(default_factory=list)
    pending_relink: list = field(default_factory=list)
    pending_conflict: list = field(default_factory=list)


def sync_directory(local_root, central_dir, backup_root, changes):
    if not central_dir.is_dir():
        return

    remove_orphan_links(local_root, central_dir, changes)

    for central_file in central_dir.rglob("*"):
        if not central_file.is_file():
            continue
        rel = central_file.relative_to(central_dir)
        target = local_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.is_symlink():
            try:
                if os.path.samefile(target, central_file):
                    continue
            except OSError:
                pass
            # Points somewhere else, or at nothing at all. A link holds no
            # content of its own, so there is nothing here worth keeping a
            # backup of - repoint it and discard what was there.
            backup = relink(
                target, central_file, target.name + ".discover-staging", changes.pending_relink
            )
            if backup:
                backup.unlink()
                changes.changed.append(str(target))
                print(f"Repointed: {target} -> {central_file}")
            continue

        if not target.exists():
            if new_central_link(target, central_file):
                changes.changed.append(str(target))
                print(f"Linked (new): {target} -> {central_file}")
            else:
                changes.pending_new.append(str(target))
            continue

        if file_hash(target) == file_hash(central_file):
            backup = relink(
                target, central_file, target.name + ".discover-staging", changes.pending_new
            )
            if backup:
                backup.unlink()
                print(f"Identical, linked: {target}")
            continue

        # Real content that differs: stage it aside, link, then move the staged
        # copy out of the tree being mirrored - a project's working copy is not
        # this tool's to litter, and the backup outlives the session anyway.
        staged = relink(
            target, central_file, target.name + ".discover-staging", changes.pending_conflict
        )
        if staged:
            backup = stash(staged, backup_root / rel)
            changes.changed.append(str(target))
            print(
                f"CONFLICT: {target} differed from central. Backup: {backup}. "
                f"Now linked to: {central_file}. Merge the backup by hand if it "
                "had rules you didn't want to lose."
            )


def main(repo, extra_search_roots=None):
    changes = Changes()
    search_roots = extra_search_roots if extra_search_roots else DEFAULT_SEARCH_ROOTS
    bad_roots = [r for r in search_roots if not r.is_dir()]
    if bad_roots:
        raise ValueError(f"search root(s) do not exist: {bad_roots}")

    global_central = repo / ".claude"
    sync_directory(config.CLAUDE_HOME, global_central, config.BACKUPS_DIR / ".claude", changes)

    for proj_dir, slug in opted_in_projects(repo, search_roots):
        central = repo / "projects" / slug
        sync_directory(proj_dir, central, config.BACKUPS_DIR / slug, changes)

    reports = (
        (
            "New, not yet synced (couldn't create the symlink, missing privilege):",
            changes.pending_new,
        ),
        ("Linked elsewhere (couldn't repoint, missing privilege):", changes.pending_relink),
        ("Differ from central (couldn't resolve, missing privilege):", changes.pending_conflict),
    )
    lines = []
    for header, paths in reports:
        if paths:
            lines.append(header)
            lines += [f"  - {p}" for p in paths]

    if lines:
        config.PENDING_MARKER.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Unresolved pending items, see {config.PENDING_MARKER}")
    else:
        config.PENDING_MARKER.unlink(missing_ok=True)

    print("Discovery complete.")
    return changes.changed

