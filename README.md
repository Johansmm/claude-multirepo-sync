# claude-multirepo-sync

Keeps a machine's Claude Code configuration in sync with a git repo you own, fanning one central
repo out over `~/.claude/` and any number of project repos. Nothing is copied between machines -
the local files *are* symlinks into that repo, so editing one of them anywhere is editing the
versioned file directly.

## Commands

- [`set-repo`](#setup) records where the config repo lives on this machine. Run once per machine,
  at setup - nothing else works until it has.
- [`discover`](#setup) creates and repairs the links, file by file, without overwriting local
  content it hasn't checked against the central copy first (a new file, an identical one and a
  real conflict are each handled differently).
- [`link`](#adding-files-to-the-config-repo) puts local files into the config repo and links them
  from then on. The only way a file joins.
- [`git-sync`](#automating-the-sync) keeps the config repo itself up to date (commit/pull/push).
- [`session-sync`](#automating-the-sync) is what the hooks run: it takes a lock, does the
  `git-sync` then the `discover`, and reports once at the end.
- [`check`](#when-something-needs-your-attention) surfaces anything left unresolved - a sync that
  didn't finish, a file that couldn't be linked, a conflict backup you haven't merged yet, an
  unexpected error.
- [`unlink`](#moving-or-replacing-the-config-repo) turns the links back into real files, so the
  config repo can be moved or replaced without the machine losing its rules.

Every command takes `--help`.

## Setup

1. Install [`uv`](https://docs.astral.sh/uv/) if it's not already on the machine.

2. Install the CLI:

   ```
   uv tool install claude-multirepo-sync
   ```

   The installed command is `claude-mr-sync`; `claude-multirepo-sync` is the package name, which
   is what `uv tool list` and `uv tool uninstall` want.

   Re-run it with `--reinstall` to pick up a newer release. To track `main` instead, install from
   git explicitly:

   ```
   uv tool install --reinstall git+https://github.com/Johansmm/claude-multirepo-sync.git@main
   ```

3. Create the [config repo](#the-config-repo), if you don't have one yet. An empty private
   git repo is enough and only one repo is needed for all your machines.

4. Clone it anywhere on the machine, and point the tool at it:

   ```
   git clone <your-config-repo>
   claude-mr-sync set-repo /path/to/your-config-repo
   ```

   It records the path in `~/.claude/multirepo-sync.repo` and refuses anything that is not a git
   repository. The tool and the configuration it syncs are deliberately separate repos: a `git
   pull` on the configuration can then never land on the code that is running it.

5. Run `claude-mr-sync discover` to create the links.

That is one machine set up, and everything up to here is by hand. What the repo can hold comes
next; [adding files to it](#adding-files-to-the-config-repo) is how it grows, and
[automating the sync](#automating-the-sync) is how it stops needing you.

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

## Adding files to the config repo

`link` is how a file joins. Point it at a file you already have and it moves the content into the
repo, at the path that maps back onto where the file lives, then replaces the file with a link to
it:

```
claude-mr-sync link ~/.claude/CLAUDE.md
claude-mr-sync link /path/to/project/CLAUDE.local.md .claude/settings.local.json
```

Nothing is declared anywhere - the destination is derived from where the file already is:

- Under `~/.claude/` it lands in `.claude/`, same relative path. `~/.claude/skills/review/SKILL.md`
  becomes `.claude/skills/review/SKILL.md`.
- Inside a git project it lands in `projects/<slug>/`, relative to the project root, where
  `<slug>` comes from that project's `origin` URL - `git@github.com:acme/widget.git` becomes
  `github.com_acme_widget`. Missing directories are created, so a project that has never synced
  anything needs no setup.
- Anywhere else it is refused: there is no destination to derive.

Then commit and push the config repo (or let [the hooks](#automating-the-sync) do it). Every other
machine picks the file up on its next `discover` - identical content is linked in place, and
content that differs is a conflict, [backed up](#conflict-backups) and reported.

`link` never overwrites. If the repo already holds that path with different content, it says so
and leaves both sides alone; if the file is already a link, it leaves it alone too.

### What not to put there

A synced file is one file shared by every machine, so anything that has to differ per machine
cannot live there. `~/.claude/settings.json` is the main one: it holds that machine's hooks and
whatever absolute paths its tools live at, so it stays local and unsynced - the
[hook block](#automating-the-sync) is added by hand, once per machine.

## Automating the sync

Two hooks in that machine's `~/.claude/settings.json` are what make the sync happen on its own,
at the start and end of every Claude Code session:

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

`SessionStart` brings the machine up to date - `session-sync` takes a lock, runs the `git-sync`
and then the `discover`, and reports once. `SessionEnd` publishes whatever the session changed.

Both hooks run in the background, so neither delays the session. The network round trips to the
git host are the slow part - around 5s for a pull plus a push - and they no longer sit on the
critical path.

`asyncRewake` is what makes the result visible. When `session-sync` finishes with something worth
saying - an unresolved conflict, files it could not link - it exits 2 and Claude Code injects the
message into the session you are already working in. With nothing to report it exits 0 and stays
quiet, which is deliberate: every wake costs a model turn.

`SessionEnd` uses plain `async`: there is no session left to wake, and the hook outlives the
session that started it. Whatever it finds is left in a marker file and reported by the next
session's `session-sync`.

`session-sync` scans `$HOME` by default to find opted-in projects, which is slow on a large home
directory. Pass `--search-root PATH` to scan somewhere else instead - repeat the flag for more
than one root. Either way the scan stops 4 levels below each root, so a project nested deeper
than that is never found.

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
    └── backups/                 # your side of a conflict, kept aside
```

The pointer sits outside the directory because it is what says where everything else lives. The
rest is how the tool talks to you between sessions: none of it is written unless something needs
you, and what each one means is [next](#when-something-needs-your-attention).

## When something needs your attention

Nothing here interrupts you, and nothing is dropped either: each case leaves a file behind in
`multirepo-sync/`, and `check` reads them all back.

```
claude-mr-sync check
```

It names whatever is still unresolved and stays silent when there is nothing to say. It is also
the one command that runs without a working config repo, so it still answers when `discover`
refuses to. `session-sync` prints the same report at the start of a session; `check` is how you
ask for it at any other moment - after a failed sync, or to confirm you have finished dealing with
one.

### A sync that didn't finish

`git-sync` reports **which of its own steps stopped** - staging, commit, connect, pull, push check,
push, merge - and **what state that left the repo in**, then hands git's output over untouched as
evidence. It never reads that output to decide what went wrong: the steps are this tool's and
there is a handful of them, while git's wording is unbounded and gets translated by the machine's
locale, and its exit codes do not tell a timed-out connection apart from a merge conflict. A wrong
diagnosis is worse than none - it sends you to fix something that isn't broken.

Two of the steps answer the question on their own, because each one is a command run to settle it:

- **connect** is `git ls-remote origin`, asked before pulling: the remote was unreachable, so
  nothing was pulled or pushed, and no later failure can be the network. Usually a VPN that isn't
  up.
- **merge** is `git rev-parse MERGE_HEAD`: a merge is half-finished. That is the only state git
  cannot get itself out of, so it is the only one that asks for your hands - open the config repo
  and finish it, starting from `git status`.

The rest leave nothing half-done and the next sync retries them; read git's output under the step
if the retries keep failing. Either way the marker stays until a sync succeeds, so `check` keeps
reporting it.

### Conflict backups

The first time `discover` runs on a machine that already had its own `CLAUDE.md`, the local file
and the central one are both real content with no history in common - git would have nothing to
merge, and neither has this tool. So it links the central copy and keeps yours under `backups/`,
at the path it came from: `backups/.claude/CLAUDE.md.conflict-<stamp>` for a global file,
`backups/<slug>/CLAUDE.local.md.conflict-<stamp>` for a project one.

They go there rather than beside the file they came from so that a project's working copy never
grows an untracked file it didn't ask for.

`check` keeps naming what is in that directory - the file it came from, what is linked in its
place, and where the backup is - until you deal with it. Merge whatever is worth keeping into the
linked file (editing it writes straight into the config repo), then delete the backup. Deleting it
is what clears the notice.

### Files not yet linked

Creating real symlinks on Windows needs either Developer Mode enabled or an elevated shell (no
such restriction on Linux/macOS). Without it, `discover` still runs safely: it lists what it could
not link in a `multirepo-sync/pending` marker instead of failing. That blocks nothing - those
files keep the content they already had - and re-running `discover` with the privilege in place is
what resolves it, whenever you get to it.

## Moving or replacing the config repo

The local files are links, not copies, so deleting or moving the repo leaves every one of them
pointing at nothing. The tool will not repair that on its own either: once the recorded path stops
being a repository, `discover` refuses to run at all.

`unlink` is what makes it safe. It replaces each link with a real copy of what it points at, so the
machine keeps its rules whatever happens to the repo next:

```
claude-mr-sync unlink                      # every file this tool has linked
claude-mr-sync unlink ~/.claude/CLAUDE.md  # or only some of them
```

Then move, re-clone or delete the repo, say where it ended up, and link everything back:

```
claude-mr-sync set-repo /new/path/to/config-repo
claude-mr-sync discover
```

`discover` finds each copy identical to its central file and links it again without a backup, so
the round trip leaves nothing behind. Don't dawdle between the two, though: a session starting in
the middle runs `discover` and links the files straight back to the old path.

It only ever undoes its own work. A link pointing outside the config repo is left alone, and so is
one whose target is already gone - there would be nothing to copy into its place.

If the repo is already deleted, there is nothing left to copy from: clone it again to the same
path and the links resolve on their own.

## Contributing

Bug reports, ideas and patches are welcome - [CONTRIBUTING.md](CONTRIBUTING.md) covers running the
tool from source, what the test suite expects, and how a change gets reviewed.
[CHANGELOG.md](CHANGELOG.md) records what each release changed.

## License

MIT - see [LICENSE](LICENSE).
