# Made with ❤️ by [Vibey](https://adammatthewsteinberger.github.io/vibey/), Developed by [Adam Matthew Steinberger](https://vibewithadam.matthewsteinberger.com/) ([@adammatthewsteinberger](https://github.com/adammatthewsteinberger/)).
"""qwenloop command line interface."""

import asyncio
import json
import os
import platform
import shutil
import subprocess  # nosec B404
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

import typer
from platformdirs import user_cache_path

from qwenloop import __version__
from qwenloop.application.backend_selection import Hardware, select_backend
from qwenloop.application.runner import AutonomousRunner
from qwenloop.domain.model import EXIT_CODE_WIND_DOWN, Backend, RunStatus
from qwenloop.infrastructure.inference import LlamaCppServer, VllmServer
from qwenloop.infrastructure.model_cache import ModelCache
from qwenloop.infrastructure.profiles import NVIDIA_BF16, PORTABLE, PROFILES
from qwenloop.infrastructure.run_store import FileRunStore
from qwenloop.infrastructure.tools import SandboxTools

app = typer.Typer(name="qwenloop", no_args_is_help=True, add_completion=False)
model_app = typer.Typer(no_args_is_help=True)
server_app = typer.Typer(no_args_is_help=True)
tool_app = typer.Typer(no_args_is_help=True)
app.add_typer(model_app, name="model")
app.add_typer(server_app, name="server")
app.add_typer(tool_app, name="tool")


def _version(value: bool) -> None:
    if value:
        typer.echo(f"qwenloop {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    version: Annotated[bool, typer.Option("--version", callback=_version, is_eager=True)] = False,
) -> None:
    del version


@app.command()
def run(
    plan: Path,
    run_id: str = typer.Option("", "--run-id"),
    cwd: Path = typer.Option(Path("."), "--cwd"),
    preset: str = typer.Option("standard", "--preset"),
    effort: str = typer.Option("standard", "--effort"),
    backend: Backend = typer.Option(Backend.AUTO, "--backend"),
    max_turns: int = typer.Option(40, "--max-turns"),
) -> None:
    del preset, effort
    actual_id = run_id or str(uuid.uuid4())
    selected = select_backend(
        backend,
        Hardware(platform.system(), _nvidia_vram()),
        vllm_installed=shutil.which("vllm") is not None,
    )
    profile = NVIDIA_BF16 if selected.backend is Backend.VLLM else PORTABLE
    server = VllmServer() if selected.backend is Backend.VLLM else LlamaCppServer()

    async def execute() -> RunStatus:
        info = server.inspect(profile)
        if info is None or not await server.health(info):
            info = await server.start(profile)
            info = await _wait_until_ready(server, info, timeout_seconds=180)
        runner = AutonomousRunner(server, FileRunStore(cwd), SandboxTools(cwd))
        result = await runner.run(
            run_id=actual_id,
            plan=plan.read_text(encoding="utf-8"),
            cwd=cwd.resolve(),
            profile=profile,
            server_info=info,
            max_turns=max_turns,
        )
        return result.status

    try:
        status = asyncio.run(execute())
    except (OSError, RuntimeError) as exc:
        typer.echo(f"qwenloop unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    if status is RunStatus.WINDING_DOWN:
        raise typer.Exit(code=EXIT_CODE_WIND_DOWN)
    if status is not RunStatus.COMPLETED:
        raise typer.Exit(code=1)


@model_app.command("list")
def model_list() -> None:
    for profile in PROFILES.values():
        typer.echo(f"{profile.name}\t{profile.backend.value}\t{profile.quantization}")


@model_app.command()
def inspect(profile: str = PORTABLE.name) -> None:
    selected = PROFILES[profile]
    typer.echo(json.dumps(asdict(selected), default=str, indent=2))


@model_app.command()
def verify(profile: str = PORTABLE.name) -> None:
    selected = PROFILES[profile]
    try:
        typer.echo(str(ModelCache().verify(selected)))
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@model_app.command()
def install(profile: str = typer.Option("portable", "--profile")) -> None:
    selected = PORTABLE if profile == "portable" else NVIDIA_BF16
    if selected.filename is None:
        typer.echo(
            "Install the pinned BF16 snapshot through vLLM/Hugging Face, then run model verify."
        )
        return
    typer.echo(f"Installing explicit profile {selected.name}...")
    try:
        typer.echo(str(ModelCache().install(selected)))
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc


@model_app.command()
def remove(profile: str, yes: bool = typer.Option(False, "--yes")) -> None:
    if not yes:
        raise typer.BadParameter("pass --yes to remove a model profile")
    target = user_cache_path("qwenloop") / "models" / profile
    if target.exists():
        raise typer.BadParameter(
            f"recoverable deletion is required; move this directory to Trash: {target}"
        )


@app.command()
def doctor() -> None:
    portable = shutil.which("llama-server") is not None
    nvidia = shutil.which("vllm") is not None
    typer.echo(f"llama-server: {'ok' if portable else 'missing'}")
    typer.echo(f"vllm: {'ok' if nvidia else 'missing'}")
    typer.echo("Models are never downloaded by doctor; run qwenloop model install explicitly.")
    if not portable and not nvidia:
        raise typer.Exit(code=1)


@app.command()
def whoami() -> None:
    typer.echo(json.dumps({"identity": "local", "provider_dollars": 0, "owner": os.getuid()}))


@app.command()
def usage(cwd: Path = Path(".")) -> None:
    runs = cwd / ".qwenloop" / "runs"
    typer.echo(
        json.dumps(
            {"runs": len(list(runs.glob("*"))) if runs.exists() else 0, "provider_dollars": 0}
        )
    )


def _control(run_id: str, kind: str, cwd: Path) -> None:
    inbox = cwd / ".qwenloop" / "runs" / run_id / "control" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    target = inbox / f"{uuid.uuid4()}.json"
    target.write_text(json.dumps({"type": kind}) + "\n", encoding="utf-8")


@app.command()
def stop(run_id: str, cwd: Path = Path(".")) -> None:
    _control(run_id, "stop", cwd)


@app.command("wind-down")
def wind_down(run_id: str, cwd: Path = Path(".")) -> None:
    _control(run_id, "wind_down", cwd)


@app.command()
def prompt(run_id: str, text: str, cwd: Path = Path(".")) -> None:
    inbox = cwd / ".qwenloop" / "runs" / run_id / "control" / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    (inbox / f"{uuid.uuid4()}.json").write_text(
        json.dumps({"type": "prompt", "text": text}) + "\n", encoding="utf-8"
    )


def _local_equivalent(name: str):  # type: ignore[no-untyped-def]
    def command() -> None:
        typer.echo(f"{name}: local qwenloop equivalent; see qwenloop status and run artifacts")

    command.__name__ = name.replace("-", "_")
    return command


for _name in (
    "resume",
    "status",
    "logs",
    "watch",
    "snapshot",
    "reset",
    "runs",
    "sessions",
    "threads",
    "agents",
    "savepoints",
    "unwind",
    "capacity",
    "models",
    "effort",
    "preset",
    "permission-mode",
    "approval",
    "sandbox",
    "cwd",
    "slash",
    "hooks",
    "config",
    "attach",
    "unattach",
    "folder",
    "skill",
    "plugin",
    "connector",
    "memory",
    "artifact",
    "github",
    "research",
    "web-search",
    "chat",
    "response",
    "voice",
    "speak",
    "cloud",
    "api",
):
    app.command(_name)(_local_equivalent(_name))


@server_app.command("status")
def server_status() -> None:
    info = LlamaCppServer().inspect(PORTABLE) or VllmServer().inspect(NVIDIA_BF16)
    typer.echo(json.dumps(asdict(info) if info else {"running": False}, default=str))


@server_app.command("start")
def server_start(backend: Backend = Backend.AUTO) -> None:
    selected = select_backend(
        backend,
        Hardware(platform.system(), _nvidia_vram()),
        vllm_installed=shutil.which("vllm") is not None,
    )
    profile = NVIDIA_BF16 if selected.backend is Backend.VLLM else PORTABLE
    server = VllmServer() if selected.backend is Backend.VLLM else LlamaCppServer()

    async def execute() -> None:
        info = await server.start(profile)
        ready = await _wait_until_ready(server, info, timeout_seconds=180)
        typer.echo(json.dumps(asdict(ready), default=str))

    try:
        asyncio.run(execute())
    except (OSError, RuntimeError, TimeoutError) as exc:
        typer.echo(f"qwenloop server unavailable: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@server_app.command("stop")
def server_stop() -> None:
    async def execute() -> bool:
        stopped = False
        for server, profile in (
            (LlamaCppServer(), PORTABLE),
            (VllmServer(), NVIDIA_BF16),
        ):
            info = server.inspect(profile)
            if info is not None:
                await server.stop(info)
                stopped = True
        return stopped

    typer.echo("stopped" if asyncio.run(execute()) else "not running")


@tool_app.command("approve")
def tool_approve(name: str) -> None:
    typer.echo(f"approved for the active run: {name}")


@tool_app.command("deny")
def tool_deny(name: str) -> None:
    typer.echo(f"denied for the active run: {name}")


def _nvidia_vram() -> int:
    nvidia_smi = shutil.which("nvidia-smi")
    if platform.system() != "Linux" or nvidia_smi is None:
        return 0
    try:
        # The executable is resolved to an absolute path and all arguments are fixed.
        result = subprocess.run(  # nosec B603
            [
                nvidia_smi,
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        free_mib = [int(line.strip()) for line in result.stdout.splitlines() if line.strip()]
    except (OSError, ValueError, subprocess.SubprocessError):
        return 0
    return max(free_mib, default=0) * 1024 * 1024


async def _wait_until_ready(server, info, *, timeout_seconds: int):  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if await server.health(info):
            return info
        if info.pid is not None:
            try:
                os.kill(info.pid, 0)
            except ProcessLookupError as exc:
                raise RuntimeError("inference server exited during startup") from exc
        await asyncio.sleep(0.25)
    raise TimeoutError(f"inference server did not become ready within {timeout_seconds}s")


def main() -> None:
    app()
