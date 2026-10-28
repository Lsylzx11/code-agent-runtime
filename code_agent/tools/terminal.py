from __future__ import annotations

import subprocess
from pathlib import Path


def run_command(workspace: Path, command: str, timeout_seconds: int = 120) -> tuple[str, int, bool]:
    """Run in the workspace, with bounded output and a portable timeout."""
    try:
        done = subprocess.run(command, cwd=workspace, shell=True, text=True,
                              encoding="utf-8", errors="replace", capture_output=True,
                              timeout=max(1, int(timeout_seconds)))
    except subprocess.TimeoutExpired as exc:
        output = ((exc.stdout or "") + (exc.stderr or ""))[:50_000]
        return output + "\nError: command timed out", -1, True
    output = (done.stdout + done.stderr).strip()[:50_000] or "(no output)"
    return output, done.returncode, False

