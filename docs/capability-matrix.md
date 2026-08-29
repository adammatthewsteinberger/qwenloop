# Capability matrix

Qwenloop exposes the literal top-level command union of claudeloop, codexloop,
cursorloop, and agyloop, so scripts and muscle memory built around those tools
keep working. Every command is registered on the same Typer application
(`qwenloop.cli.app`) and is covered by the CLI command-presence contract test
(`tests/test_cli.py::test_union_commands_are_present`), but only some of them
run local logic — the rest are inert placeholders kept for surface
compatibility.

## Commands with real local behavior

| Command | Behavior |
|---|---|
| `run PLAN --run-id ID --cwd DIR [--backend ...] [--max-turns N]` | Starts or reuses an inference server for the selected backend and runs the autonomous coding loop against `PLAN` until it completes, winds down, or hits `--max-turns`. |
| `model list` | Prints the built-in profiles (`portable`, `nvidia-bf16`). |
| `model inspect [PROFILE]` | Prints a profile's full manifest as JSON. |
| `model install --profile {portable,nvidia-bf16}` | Downloads and verifies the pinned portable GGUF, or explains that the BF16 snapshot is installed through the pinned vLLM/Hugging Face cache. |
| `model verify [PROFILE]` | Confirms an installed model's revision and SHA-256 match its pinned manifest. |
| `model remove PROFILE --yes` | Refuses to delete silently; always points the operator at the cache directory to move to Trash by hand. |
| `server status` / `server start [--backend ...]` / `server stop` | Inspect, launch, or terminate the local llama.cpp/vLLM server process. |
| `doctor` | Reports whether `llama-server` and `vllm` are on `PATH`; never downloads anything. |
| `whoami` | Prints a fixed local identity record (`provider_dollars: 0`). |
| `usage --cwd DIR` | Counts run directories under `DIR/.qwenloop/runs`. |
| `stop RUN_ID --cwd DIR` / `wind-down RUN_ID --cwd DIR` / `prompt RUN_ID TEXT --cwd DIR` | Drop a control message into the run's `control/inbox/` for the next turn to pick up. |
| `tool approve NAME` / `tool deny NAME` | Print an acknowledgement for the named tool; scoped to operator visibility, not an enforcement mechanism. |

## Local-equivalent stub commands

The remaining ~40 commands are registered through `_local_equivalent()` in
`src/qwenloop/cli/app.py`. Each one only prints
`"<name>: local qwenloop equivalent; see qwenloop status and run artifacts"`
and exits `0` — they perform no action, call no vendor API, and store no
state. They exist so a script written against another *loop tool's CLI does
not fail with "unknown command" when pointed at qwenloop.

Vendor account, cloud, resource, speech, and generated-API families:
`resume`, `status`, `logs`, `watch`, `snapshot`, `reset`, `runs`, `sessions`,
`threads`, `agents`, `savepoints`, `unwind`, `capacity`, `models`, `effort`,
`preset`, `permission-mode`, `approval`, `sandbox`, `cwd`, `slash`, `hooks`,
`config`, `attach`, `unattach`, `folder`, `skill`, `plugin`, `connector`,
`memory`, `artifact`, `github`, `research`, `web-search`, `chat`, `response`,
`voice`, `speak`, `cloud`, `api`.

Note the near-collision between the top-level `models` stub above and the
real `model` sub-app (`model list`/`inspect`/`verify`/`install`/`remove`):
`qwenloop models` always prints the placeholder, while `qwenloop model list`
does the real listing.

