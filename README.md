# qwenloop

`qwenloop` is an autonomous, local Qwen 2.5 Coder 14B runner. It uses a
portable llama.cpp/Q5_K_M profile by default and can use BF16 through vLLM on
Linux NVIDIA systems with at least 40 GiB of usable VRAM.

Model installation is always explicit. The package, tests, `doctor`, and Vibey
integration never download model weights.

```bash
qwenloop model install --profile portable
qwenloop run plan.md --run-id <uuid> --cwd <worktree>
```

The stable run contract is `.qwenloop/runs/<run-id>/`, exit code `75` for a
graceful wind-down, the `QWENLOOP_TASK_FULLY_COMPLETE` marker, and a
`qwenloop-verdict` result fence.

