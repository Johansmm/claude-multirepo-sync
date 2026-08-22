# claude-multirepo-sync

Keeps a machine's Claude Code configuration in sync with a git repo you own, fanning one central
repo out over `~/.claude/` and any number of project repos. Nothing is copied between machines -
the local files *are* symlinks into that repo, so editing one of them anywhere is editing the
versioned file directly.

## Commands

- `set-repo` records where the config repo lives on this machine. Run once per machine, at setup
  - nothing else works until it has.
- `discover` creates and repairs the links, file by file, without overwriting local content it
  hasn't checked against the central copy first (new file, adopt, identical, or real conflict are
  each handled differently).
- `git-sync` keeps the config repo itself up to date (commit/pull/push).
- `session-sync` is what the hooks actually run: it takes a lock, does the `git-sync` then the
  `discover`, and reports once at the end.
- `check` surfaces anything left unresolved (a sync that didn't finish, a file that couldn't be
  linked, a conflict backup you haven't merged yet, or an unexpected error). Run it by hand whenever you
  want the current state; `session-sync` reports the same thing on its own.

## The config repo

The repo holding the configuration is yours, kept separate from this tool and named whatever you
like. This tool never creates it, and holds no list of what is inside it: two directory names are
the entire contract, and both are optional.

- `.claude/` mirrors onto `~/.claude/`, unconditionally, on every machine.
- `projects/<slug>/` mirrors onto one project's root, and only for projects that have a folder
  there - nothing syncs just because a git repo exists on disk.

Naming a directory exactly like its destination is what keeps the mapping readable, and `<slug>`
is derived mechanically from the project's remote URL, so matching is automatic with no manifest
to maintain.

Every commit in that repo is publishable - that is what lets `git-sync` commit and push on its
own, unattended. Keep anything you would not publish out of it.

## Setup

1. Install [`uv`](https://docs.astral.sh/uv/) if it's not already on the machine.

2. Install the CLI. `uv` clones and builds it for you, so this machine never needs a working copy
   of the tool:

   ```
   uv tool install git+https://github.com/Johansmm/claude-multirepo-sync.git
   ```

   The installed command is `claude-mr-sync`; `claude-multirepo-sync` is the package name, which
   is what `uv tool list` and `uv tool uninstall` want.

   Re-run it with `--reinstall` to pick up a newer version.

3. Create the config repo, if you don't have one yet. An empty private git repo is enough - the
   layout above is all it needs, and both directories can be filled later. Only one repo is
   needed for all your machines.

4. Clone it anywhere on the machine, and point the tool at it:

   ```
   git clone <your-config-repo>
   claude-mr-sync set-repo /path/to/your-config-repo
   ```

   It records the path in `~/.claude/multirepo-sync.repo` and refuses anything that is not a git
   repository. The tool and the configuration it syncs are deliberately separate repos: a `git
   pull` on the configuration can then never land on the code that is running it.

5. Add the hooks to that machine's `~/.claude/settings.json`:

   ```json
   {
     "hooks": {
       "SessionStart": [
         { "hooks": [
           { "type": "command", "command": "claude-mr-sync session-sync", "asyncRewake": true, "timeout": 120 }
         ] }
       ],
       "SessionEnd": [
         { "hooks": [
           { "type": "command", "command": "claude-mr-sync git-sync", "async": true, "timeout": 60 }
         ] }
       ]
     }
   }
   ```

   Both hooks run in the background, so neither delays the session. The network round trips to
   the git host are the slow part - around 5s for a pull plus a push - and they no longer sit on
   the critical path.

   `asyncRewake` is what makes the result visible. When `session-sync` finishes with something
   worth saying - an unresolved conflict, files it could not link - it exits 2 and Claude Code
   injects the message into the session you are already working in. With nothing to report it
   exits 0 and stays quiet, which is deliberate: every wake costs a model turn.

   `SessionEnd` uses plain `async`: there is no session left to wake, and the hook outlives the
   session that started it. Whatever it finds is left in a marker file and reported by the next
   session's `session-sync`.

6. Run `claude-mr-sync discover` once by hand to verify the initial link.

`session-sync` scans `$HOME` by default to find opted-in projects, which is slow on a large home
directory. Pass `--search-root PATH` to scan somewhere else instead - repeat the flag for more
than one root. Either way the scan stops 4 levels below each root, so a project nested deeper
than that is never found.

## Filling the config repo

There is nothing to declare anywhere: a file's path in the repo is what decides where it lands.

### Global files, onto `~/.claude/`

Put them under `.claude/`, at the same relative path they should have at the destination.
`.claude/CLAUDE.md` becomes `~/.claude/CLAUDE.md`; `.claude/skills/review/SKILL.md` becomes
`~/.claude/skills/review/SKILL.md`. Commit, push, and `discover` links them on every machine.

### One project's files, onto its root

1. Get the project's remote URL: `git -C /path/to/project config --get remote.origin.url`

2. Turn that into a `<slug>`: drop the protocol (`https://`) or user (`git@`) prefix and the
   trailing `.git`, then replace every `:`, `/` or `\` with `_`.

   Example: `git@github.com:acme/widget.git` becomes `github.com_acme_widget`. This is exactly
   what `get_slug()` in `discover.py` computes, so it is guaranteed to match what `discover`
   looks for.

3. Create `projects/<slug>/` in the config repo and add whatever should sync onto that project's
   root (`CLAUDE.local.md`, `.claude/settings.local.json`, ...) - same file-by-file rules as
   `.claude/`.

4. Commit and push. `discover` picks it up next time it runs, on any machine where that project
   exists locally with the same remote.

### What not to put there

A synced file is one file shared by every machine, so anything that has to differ per machine
cannot live there. `~/.claude/settings.json` is the main one: it holds that machine's hooks and
whatever absolute paths its tools live at, so it stays local and unsynced - the hook block in
step 5 is added by hand, once per machine.

## Where the tool keeps its own files

Everything this tool writes on a machine lives under one directory, and none of it is synced:

```
~/.claude/
├── multirepo-sync.repo          # where the config repo is, on this machine
└── multirepo-sync/
    ├── sync                     # why the last git-sync did not finish
    ├── pending                  # links that couldn't be created
    ├── error.<command>          # one per command that crashed
    ├── lock                     # session-sync's lock
    └── backups/                 # your side of a resolved conflict
```

The pointer sits outside the directory because it is what says where everything else lives.

### How a failed sync is reported

`git-sync` never reads what git said in order to decide what went wrong. It reports **which step
stopped** - staging, commit, pull, push - and **what state the repo was left in**, then hands git's
own output over untouched as evidence.

The reason is that the steps are this tool's and there is a handful of them, while git's wording
is unbounded, gets translated by the machine's locale, and its exit codes do not tell a timed-out
connection apart from a merge conflict. A tool that guesses will eventually guess wrong, and a
wrong diagnosis is worse than none: it sends you to fix something that isn't broken.

Two questions are asked, both by running a command that answers them rather than by reading prose:

- `git ls-remote origin`, before pulling, answers whether the remote is reachable at all. With that
  settled up front, no later failure can be the network.
- `git rev-parse MERGE_HEAD` answers whether a merge is half-finished. That is the only state git
  cannot get itself out of, so it is the only one that asks for your hands.

Everything else says which step stopped and leaves the reading to you.

### Conflict backups

The first time `discover` runs on a machine that already had its own `CLAUDE.md`, the local file
and the central one are both real content with no history in common - git would have nothing to
merge, and neither has this tool. So it links the central copy and keeps yours under `backups/`,
at the path it came from: `backups/.claude/CLAUDE.md.conflict-<stamp>` for a global file,
`backups/<slug>/CLAUDE.local.md.conflict-<stamp>` for a project one.

They go there rather than beside the file they came from so that a project's working copy never
grows an untracked file it didn't ask for.

`check` reads that directory and keeps naming what is in it - the file it came from, what is
linked in its place, and where the backup is - until you deal with it. Merge whatever is worth
keeping into the linked file (editing it writes straight into the config repo), then delete the
backup. Deleting it is what clears the notice.

## Working on the tool

The installed copy is built from a git clone of its own, so it does not follow a working tree.
Run the source directly while developing:

```
uv run claude-mr-sync ...
uv run pytest
```

and reinstall when the installed copy should catch up.

## Notes on symlink privilege

Creating real symlinks on Windows needs either Developer Mode enabled or an elevated shell (no
such restriction on Linux/macOS). Without it, `discover` still runs safely - it leaves a
`multirepo-sync/pending` marker instead of failing, and the next session's `session-sync` reports
it - or `claude-mr-sync check` does, whenever you ask.
