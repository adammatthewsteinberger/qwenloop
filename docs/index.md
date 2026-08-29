# qwenloop

`qwenloop` is an autonomous, local Qwen 2.5 Coder 14B runner. It uses a
portable llama.cpp/Q5_K_M profile by default and can use BF16 through vLLM on
Linux NVIDIA systems with at least 40 GiB of usable VRAM.

Model installation is always explicit. The package, tests, `doctor`, and Vibey
integration never download model weights.

## Install

Until the first PyPI release, install the runner from the immutable Git tag or
an explicit commit:

```bash
uv tool install \
  'qwenloop @ git+https://github.com/adammatthewsteinberger/qwenloop.git@feature/qwenloop-local-engine'
```

The Python package never bundles model weights.

## Prerequisites

`qwenloop` never installs an inference backend for you. Before `doctor` or
`run` can start a local server, install one of:

- **llama.cpp** (`llama-server` on `PATH`) — required for the default
  `portable` profile. Build from source or use a packaged release from
  [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp); on macOS,
  `brew install llama.cpp` also provides `llama-server`.
- **vLLM** (`vllm` on `PATH`) — only needed for the `nvidia-bf16` profile on
  Linux with an NVIDIA GPU. Install with `pip install vllm` (or `uv tool
  install vllm`) following [vLLM's installation
  guide](https://docs.vllm.ai/en/latest/getting_started/installation.html).

Run `qwenloop doctor` after installing to confirm which backend(s) it found.

## Quick start

```bash
qwenloop model install --profile portable
qwenloop model verify
qwenloop doctor
echo 'Add a LICENSE file with the MIT license text.' > plan.md
qwenloop run plan.md --run-id demo-1 --cwd "$(pwd)"
```

`run` picks a backend automatically (`--backend auto`, the default), starting
or reusing a local inference server, then drives the autonomous coding loop
against `plan.md` for up to `--max-turns` turns (default `40`). It exits:

| Exit code | Meaning |
|---|---|
| `0` | The model produced a `` ```qwenloop-verdict `` fence and the `QWENLOOP_TASK_FULLY_COMPLETE` marker in the same turn. |
| `75` | A `stop`/`wind-down` control message was seen; the run stopped cleanly mid-task. |
| `1` | The turn limit was reached, the model returned an empty response, or the inference server could not start (see stderr). |

While a run is in progress (from another terminal, same `--cwd`):

```bash
qwenloop prompt demo-1 "also add a CHANGELOG entry"   # queue extra guidance
qwenloop wind-down demo-1                             # ask it to stop cleanly (exit 75)
qwenloop stop demo-1                                  # same effect, for scripts
```

### Run directory layout

Every run writes to `<cwd>/.qwenloop/runs/<run-id>/`:

- `meta.json` — the run's backend, profile, repository/revision, and pinned artifact digest, written once at creation.
- `events.jsonl` — an append-only ledger of every text delta, tool call, tool result, completion, and failure for the run.
- `snapshots/latest.json` — the current status, turn count, and token counts, replaced atomically after each turn.
- `control/inbox/*.json` — control messages (`stop`, `wind_down`, `prompt`) dropped by the commands above and consumed on the next turn.

`qwenloop usage --cwd DIR` counts run directories under a given tree;
`qwenloop whoami` reports a fixed local identity (no account, no spend).

See the [architecture overview](architecture/overview.md) for a diagram of
the onion layers and the model trust boundary, [project.mmd](project.mmd)
for the comprehensive map of every source module, CLI surface, run
lifecycle, and release/provenance channel, and the
[capability matrix](capability-matrix.md) for every CLI command,
including which of the claudeloop/codexloop/cursorloop/agyloop command
surface is wired to real local behavior versus a placeholder kept only for
script compatibility.

## Agent tool surface

Inside a run, the model can only act through three typed tools
(`src/qwenloop/infrastructure/inference.py`, `_CODING_TOOLS`), dispatched by
`SandboxTools` (`src/qwenloop/infrastructure/tools.py`):

| Tool | Arguments | Behavior |
|---|---|---|
| `read_file` | `path` | Reads a UTF-8 file resolved against the run's worktree (`--cwd`), truncated to 200,000 characters. Raises if the resolved path escapes the worktree. |
| `write_file` | `path`, `content` | Writes UTF-8 text to a path resolved against the worktree, creating parent directories as needed. Raises on the same worktree-escape check as `read_file`. |
| `shell` | `argv` (list of strings) | Runs `argv` with the worktree as its working directory, a 120 second timeout, and up to 100,000 trailing characters of combined stdout/stderr returned. |

`shell` strips environment variables whose names contain `KEY` or `TOKEN` and
tags the environment as network-disabled unless the run was started with
network access allowed. It refuses to launch exactly four programs —
`sudo`, `rm`, `shutdown`, `reboot` — as `argv[0]`. **It does not otherwise
sandbox filesystem or network access**: unlike `read_file`/`write_file`, a
shell command is not confined to the worktree. See
[SECURITY.md](https://github.com/adammatthewsteinberger/qwenloop/blob/main/SECURITY.md)
and [ADR 0002](architecture/decisions/0002-tool-security.md) before running
plans you do not trust.

`qwenloop tool approve NAME` / `qwenloop tool deny NAME` print an
acknowledgement for operator visibility; they do not currently gate which
tools a running model may call.

## Configuration

`qwenloop.domain.config.QwenConfig` / `parse_config()` define a validated
configuration schema (backend, profile names, timeouts, context window, max
turns) for embedding qwenloop as a library. It is not yet wired to a CLI flag
or a config file — every `qwenloop run`/`server start` invocation today is
configured entirely through command-line options and the pinned profiles in
`src/qwenloop/infrastructure/profiles.py`.

## Inference profiles

| Profile | Backend | Intended hardware | Model installation |
|---|---|---|---|
| `portable` | llama.cpp Q5_K_M | Apple Silicon, Linux CPU, supported offload GPUs | Explicit `qwenloop model install --profile portable` |
| `nvidia-bf16` | vLLM BF16 | Linux NVIDIA with at least 40 GiB free VRAM | Operator-managed pinned Hugging Face/vLLM cache |

Servers bind to loopback and require a per-launch bearer token, generated
fresh each time a server is started. Qwenloop never silently changes backend
during a run: `--backend auto` decides once, before the run starts
(`qwenloop.application.backend_selection.select_backend`), based on OS,
detected NVIDIA VRAM, and whether `vllm` is on `PATH`.

## Interfaces

Qwenloop is a local CLI and an internal OpenAI-compatible HTTP server used to
talk to llama.cpp/vLLM (loopback-only, bearer-token protected, not intended
as a public API). There is currently no distributed Python SDK, no public
hosted API, no MCP server, and no webhook integration — automation should
shell out to the `qwenloop` CLI and poll `snapshots/latest.json` or tail
`events.jsonl` as described above.

## Development

```bash
uv sync --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src/qwenloop
uv run lint-imports
uv run pytest -q
uv run bandit -q -r src/qwenloop
```

First-party code is held to 100% line and branch coverage. Model and hardware
smokes are deliberately separate from the hermetic CI suite.

## Release workflow

Qwenloop uses `develop` as its integration branch and `main` as its release
branch. Every change moves through the pipeline defined in
`.github/workflows/`:

| Workflow | Trigger | What it does |
|---|---|---|
| `ci.yml` | Push/PR to `main`/`develop` | Lint, type-check, import-layering, `bandit`, tests on Python 3.12–3.14, and a build+install smoke. |
| `provenance.yml` | Every branch and PR | Required check that verifies commit provenance fingerprints server-side. |
| `pr-automation.yml` | CI/Provenance completion, PR events | Evaluates the exact PR head, runs an exact-head semantic code/documentation review, and publishes the `PR automation / gate` check. If the review returns no verdict (credentials, credit, or model availability), a local-model fallback reviews the diff instead and says so explicitly in the gate summary. |
| `merge-train.yml` | A green `PR automation / gate` | Merges every currently-ready PR into `develop`. |
| `promote-to-main.yml` | A successful merge train | Opens or updates a `develop` → `main` promotion PR and derives the release version. |
| `release.yml` | Push to `main`/`develop` | Builds distributions and publishes to TestPyPI (`develop`) or PyPI (`main`). |
| `release-surfaces.yml` | A successful `release.yml` run | Publishes an OCI package to GitHub Packages and a versioned docs site to GitHub Pages. |
| `automation-bootstrap.yml` | Manual, admin-authorized | Recovery path for repairing the automation pipeline itself when its own gate is broken; scoped to automation-core paths and requires independent gates to already be green. |

**If a gate is red:** open the failing check's run for its log. `pr-automation`
attempts a bounded, automatic repair commit for PR-level failures (scans or
review findings) before asking a human; a PR labeled
`vibey-gh:repair-exhausted` has used its automatic attempts and needs a manual
fix. `vibey-gh:automation-blocked` means the failure is outside what an
automated repair can fix (credentials, billing, external service
availability, or a repository-settings change) — the PR automation's own
structured verdict names the exact operator action required. See the
[architecture overview](architecture/overview.md) and
[project.mmd](project.mmd) for the full workflow graph.

## Contributing and support

See [CONTRIBUTING](https://github.com/adammatthewsteinberger/qwenloop/blob/main/CONTRIBUTING.md)
for the development workflow and pre-submission checks, and
[CODE_OF_CONDUCT](https://github.com/adammatthewsteinberger/qwenloop/blob/main/CODE_OF_CONDUCT.md)
for participation expectations. Report security vulnerabilities as described
in [SECURITY.md](https://github.com/adammatthewsteinberger/qwenloop/blob/main/SECURITY.md)
rather than filing a public issue. For anything else — bugs, questions,
feature requests — open a GitHub issue.

## Troubleshooting

- **`doctor` reports both backends missing** — see [Prerequisites](#prerequisites)
  above; `qwenloop` never installs `llama-server` or `vllm` for you.
- **`qwenloop run` exits `1` with "inference server could not start"** — the
  backend binary was found but failed to launch or never became healthy
  within 180 seconds; rerun with the backend's own logs visible (`qwenloop
  server start` surfaces the same startup path standalone) to see why.
- **`model verify` fails after previously succeeding** — the installed
  artifact no longer matches its pinned manifest (`src/qwenloop/infrastructure/profiles.py`).
  Re-run `qwenloop model install --profile <name>` to fetch the currently
  pinned artifact.
- **A shell tool call in a run touched files outside the plan's intent** — the
  `shell` tool is not filesystem- or network-sandboxed; see [Agent tool
  surface](#agent-tool-surface) and
  [SECURITY.md](https://github.com/adammatthewsteinberger/qwenloop/blob/main/SECURITY.md)
  before running plans from an untrusted source.

## License

Qwenloop is MIT licensed. Qwen2.5-Coder model artifacts are separately licensed
under Apache License 2.0 and are downloaded only after an explicit operator
command.
