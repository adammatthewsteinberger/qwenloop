# Security policy

## Reporting a vulnerability

Do not open a public issue for a vulnerability. Use the repository's
[private security advisory form](https://github.com/adammatthewsteinberger/qwenloop/security/advisories/new).

Include the affected version, backend, operating system, reproduction, impact,
and suggested mitigation. Remove credentials, private source code, prompts, and
model outputs that contain sensitive material.

## Security boundaries

Qwenloop treats model output, repository content, tool output, and retrieved
content as untrusted. Model servers bind to loopback and use per-launch bearer
credentials that are generated fresh for every server start. Model weights are
installed only after an explicit operator command.

The model can only act through three typed tools
([ADR 0002](docs/architecture/decisions/0002-tool-security.md)), and the
tools protect different things:

- `read_file` and `write_file` resolve every path against the run's assigned
  worktree and reject any path that would resolve outside it.
- `shell` runs an arbitrary `argv` inside the worktree's current working
  directory and strips environment variables whose names contain `KEY` or
  `TOKEN`, but it does **not** confine the executed program's filesystem or
  network access. It only refuses to launch four literal executables —
  `sudo`, `rm`, `shutdown`, `reboot` — as `argv[0]`; any other program
  (including one that deletes or exfiltrates files, or invokes those same
  binaries indirectly, e.g. `bash -c "rm -rf ~"`) is allowed to run with the
  full permissions of the user running qwenloop.

Because of that gap, run qwenloop under an account and filesystem scope you
are comfortable granting to the plan you hand it, and prefer a disposable
container or VM when running plans from an untrusted source.
