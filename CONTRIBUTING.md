# Contributing

Thanks for looking. This is a small tool with a deliberately small contract - two directory names,
seven commands - so most changes are about keeping it that way.

## Reporting a bug

Open an issue with the [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml). The output of
`claude-mr-sync check` is the single most useful thing to paste: it is where the tool records what
it could not finish.

One caveat: that output names paths inside your config repo, and a marker can quote git's own
message. Read it before pasting and redact anything private.

## Getting the source

The installed copy is built from a git clone of its own, so it never follows a working tree. To
work on the tool, clone it and let `uv` build the environment:

```
git clone https://github.com/Johansmm/claude-multirepo-sync.git
cd claude-multirepo-sync
uv sync
```

`uv sync` installs the dev dependencies as well, so nothing else needs installing.

## Running from source

Run the source directly, without touching the installed copy:

```
uv run claude-mr-sync check
uv run claude-mr-sync discover
```

Two versions therefore coexist on a development machine, and they are independent:

| | Command | Built from | Used by |
| --- | --- | --- | --- |
| Released | `claude-mr-sync` | the clone `uv tool install` made for itself | the hooks, day to day |
| Working tree | `uv run claude-mr-sync` | this checkout, as it stands | you, while developing |

The hooks in `~/.claude/settings.json` always call the installed one, so editing the source never
changes what a session does. When the installed copy should catch up, reinstall it:

```
uv tool install --reinstall git+https://github.com/Johansmm/claude-multirepo-sync.git
```

Be careful with manual runs of the commands that write: there is no dry-run and no sandbox flag,
so `discover`, `link` and `unlink` act on your real `~/.claude` and your real config repo. Prefer
exercising a change through the tests, and if you do need a manual run, save the current pointer
first (`cat ~/.claude/multirepo-sync.repo`) so you can put it back with `set-repo`.

## Tests

```
uv run pytest                       # all of it
uv run pytest tests/test_link.py    # one file
uv run pytest -k slug               # one case
```

Two things about the suite are worth knowing before adding to it:

- An autouse fixture in `tests/conftest.py` redirects every path the tool writes outside the config
  repo into `tmp_path`. Nothing may reach the real `~/.claude` - if a new module writes somewhere
  new, add it to `claude_home` in the same commit.
- Creating a symlink on Windows needs a privilege that CI and most shells don't have. Tests that
  need one carry `@needs_symlinks` from `tests/helpers.py` and skip without it, so a green run on
  Windows is not necessarily a full run. Keep the assertions that don't need a real link outside
  the marked test.

## Linting

```
uv run ruff format --check .    # fails if a file needs reformatting
uv run ruff check .             # fails on lint errors
```

Both run on every pull request. `uv run ruff format .` applies the formatting fixes in place.

## Code

One module per command (`discover.py`, `link.py`, `git_sync.py`, ...), with `config.py` owning
every path the tool writes and `cli.py` doing nothing but argument parsing and exit codes. A new
command is a new module plus a subparser, not a branch inside an existing one.

Conventions the existing code follows:

- Comments and docstrings say *why*, not what. The reason a thing is done this way and not the
  obvious way is what a reader a year from now cannot recover on their own.
- Wrap at 100 columns.
- No dependency gets added lightly. `filelock` is the only runtime one, and a change that needs a
  second should say in the PR why the standard library isn't enough.
- Failures that are expected - a conflict, an unreachable remote - are `SyncError` and get recorded
  in a marker. Anything else is a bug and is allowed to crash with its traceback.

Test files: constants first, then classes, fixtures, helpers, and tests last. Parametrize rather
than writing near-duplicate test functions, and keep every case inline in the
`@pytest.mark.parametrize` list.

## Commits

[Conventional Commits](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`, in the
imperative mood, subject of 50 characters or less, no trailing period. Common types are `feat`,
`fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci` and `chore`.

One atomic change per commit - if the subject needs an "and", it is two commits. A change ships in
the same commit as the tests that cover it. Add a body only when the title and the diff don't
carry the *why*.

## Pull requests

Fill in the [template](.github/pull_request_template.md); it is short. What it asks for:

- The tests pass, and behaviour changes come with a test that fails without the change.
- The README says what the tool now does, if that changed. Nothing in the README describes internals
  for their own sake, so a refactor usually needs no doc change and a new flag always does.
- A `CHANGELOG.md` entry under `Unreleased`, for anything a user would notice.

Review is about the contract more than the code: whether the new behaviour still holds when the
network is down, when the repo has moved, when two sessions run at once, and when the machine
cannot create a symlink. Saying which of those you thought about saves a round trip.
