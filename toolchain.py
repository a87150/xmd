"""Locate or bootstrap the gallery-dl and yt-dlp executables."""



from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path





def is_windows() -> bool:
    return os.name == "nt"

def venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if is_windows() else "bin")

def venv_executable_name(name: str) -> str:
    return f"{name}.exe" if is_windows() else name

def ensure_toolchain(venv_dir: Path, skip_bootstrap: bool) -> tuple[Path, Path]:
    global_gallery = shutil.which("gallery-dl")
    global_ytdlp = shutil.which("yt-dlp")
    if global_gallery and global_ytdlp:
        return Path(global_gallery), Path(global_ytdlp)

    venv_dir = venv_dir.expanduser().resolve()
    venv_bin = venv_bin_dir(venv_dir)
    gallery_bin = venv_bin / venv_executable_name("gallery-dl")
    ytdlp_bin = venv_bin / venv_executable_name("yt-dlp")

    if gallery_bin.exists() and ytdlp_bin.exists():
        return gallery_bin, ytdlp_bin

    if skip_bootstrap:
        raise RuntimeError(
            "gallery-dl and yt-dlp were not both found. "
            "Install them first or rerun without --skip-bootstrap."
        )

    bootstrap_toolchain(venv_dir)
    if not gallery_bin.exists() or not ytdlp_bin.exists():
        raise RuntimeError("Bootstrapping finished, but gallery-dl or yt-dlp is still missing.")

    return gallery_bin, ytdlp_bin

def candidate_python_executables() -> list[Path]:
    candidates = [
        os.environ.get("PYTHON_FOR_VENV"),
        getattr(sys, "_base_executable", None),
        sys.executable,
        shutil.which("python3"),
        shutil.which("python"),
    ]
    if not is_windows():
        candidates.insert(1, "/usr/bin/python3")
    resolved: list[Path] = []
    seen: set[str] = set()

    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)

    return resolved

def can_create_virtualenv(python_executable: Path) -> bool:
    try:
        with tempfile.TemporaryDirectory(prefix="xmd-venv-probe-") as temp_dir:
            probe_dir = Path(temp_dir) / "probe"
            result = subprocess.run(
                [str(python_executable), "-m", "venv", str(probe_dir)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
    except OSError:
        return False

    return result.returncode == 0

def resolve_bootstrap_python() -> Path:
    for candidate in candidate_python_executables():
        if can_create_virtualenv(candidate):
            return candidate

    raise RuntimeError(
        "Could not find a usable Python interpreter for virtualenv bootstrap. "
        "Install python3 or set PYTHON_FOR_VENV to a Python 3 executable."
    )

def bootstrap_toolchain(venv_dir: Path) -> None:
    print(f"[bootstrap] Preparing local virtualenv at {venv_dir}", file=sys.stderr)
    bootstrap_python = resolve_bootstrap_python()
    if venv_dir.exists():
        print(f"[bootstrap] Rebuilding virtualenv with {bootstrap_python}", file=sys.stderr)
        shutil.rmtree(venv_dir)
    run_checked([str(bootstrap_python), "-m", "venv", str(venv_dir)])

    venv_python = venv_bin_dir(venv_dir) / venv_executable_name("python")
    if not venv_python.exists():
        raise RuntimeError(f"Virtualenv python not found at {venv_python}")

    run_checked([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])
    run_checked([str(venv_python), "-m", "pip", "install", "--upgrade", "gallery-dl", "yt-dlp"])

def run_checked(command: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.run(command, check=True, env=env)
