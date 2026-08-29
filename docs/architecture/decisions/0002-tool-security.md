# ADR 0002: Treat model output as untrusted

All model tool calls cross typed validation before dispatch
(`qwenloop.infrastructure.tools.SandboxTools`). `read_file` and `write_file`
resolve their `path` argument against the run's worktree and reject any
result outside it. `shell` runs `argv` with the worktree as its current
directory, drops environment variables whose names contain `KEY` or `TOKEN`,
tags the subprocess environment as network-disabled unless the run explicitly
allows network access, and enforces a 120 second timeout and a 100,000
character trailing output cap. It denies exactly four literal `argv[0]`
values (`sudo`, `rm`, `shutdown`, `reboot`); it does not sandbox the
filesystem or network access of whatever program it runs, so it is a policy
speed bump against a careless model, not a security boundary against a
malicious one. Every tool proposal, denial, and result is appended to the
run's `events.jsonl` ledger (see `docs/index.md#run-directory-layout`).

