# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

First release. Everything below is what `0.1.0` will ship with.

### Added

- `set-repo`, recording where the config repo lives on this machine and refusing a path that is not
  a git repository.
- `discover`, mirroring the config repo's `.claude/` onto `~/.claude/` and each opted-in
  `projects/<slug>/` onto that project's root. A new file is linked, an identical one is linked in
  place, and a real conflict is backed up rather than overwritten.
- `link`, moving a local file into the config repo and replacing it with a link, deriving the
  destination from where the file already lives.
- `unlink`, replacing links with real files so the config repo can be moved, re-cloned or deleted
  without the machine losing its rules.
- `git-sync`, committing, pulling and pushing the config repo unattended, and naming the step that
  stopped rather than guessing from git's output.
- `session-sync`, running the whole sync under a lock and reporting once, so it can be driven from
  a `SessionStart` hook.
- `check`, reporting whatever is still unresolved - a sync that didn't finish, files that could not
  be linked, conflict backups waiting to be merged, unexpected errors - and running even when the
  config repo is unreachable.
- `--search-root`, limiting the scan for opted-in projects to given roots instead of `$HOME`.
- Graceful behaviour where Windows denies the symlink privilege: `discover` records what it could
  not link instead of failing.
