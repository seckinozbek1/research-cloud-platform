from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeContext:
    project_root: Path
    runtime_root: Path
    managed_root: Path
    model_cache: Path


def _default_runtime_root() -> Path:
    """
    Resolve a portable per-user runtime location.

    Resolution order:
    1. Explicit RESEARCH_CLOUD_RUNTIME
    2. Existing legacy ~/research-cloud-runtime directory
       for backward-compatible local development
    3. OS-appropriate per-user application data directory
    """

    explicit = os.environ.get(
        "RESEARCH_CLOUD_RUNTIME"
    )

    if explicit:
        return Path(explicit).expanduser().resolve()

    legacy = (
        Path.home()
        / "research-cloud-runtime"
    )

    if legacy.exists():
        return legacy.resolve()

    if os.name == "nt":
        base = os.environ.get(
            "LOCALAPPDATA"
        )

        if base:
            return (
                Path(base)
                / "research-cloud-platform"
            ).resolve()

        return (
            Path.home()
            / "AppData"
            / "Local"
            / "research-cloud-platform"
        ).resolve()

    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "research-cloud-platform"
        ).resolve()

    xdg_data_home = os.environ.get(
        "XDG_DATA_HOME"
    )

    if xdg_data_home:
        return (
            Path(xdg_data_home)
            / "research-cloud-platform"
        ).expanduser().resolve()

    return (
        Path.home()
        / ".local"
        / "share"
        / "research-cloud-platform"
    ).resolve()


def _default_project_root() -> Path:
    """
    The installed repository is discovered relative to this module,
    not from a machine-specific absolute path.
    """

    return Path(__file__).resolve().parents[1]


def get_runtime_context() -> RuntimeContext:
    project_root = Path(
        os.environ.get(
            "RESEARCH_CLOUD_PROJECT_ROOT",
            str(_default_project_root()),
        )
    ).expanduser().resolve()

    runtime_root = _default_runtime_root()

    managed_root = Path(
        os.environ.get(
            "RESEARCH_CLOUD_MANAGED_ROOT",
            str(runtime_root / "agent-managed"),
        )
    ).expanduser().resolve()

    model_cache = Path(
        os.environ.get(
            "RESEARCH_CLOUD_MODEL_CACHE",
            str(
                runtime_root
                / "models"
                / "llama.cpp"
            ),
        )
    ).expanduser().resolve()

    return RuntimeContext(
        project_root=project_root,
        runtime_root=runtime_root,
        managed_root=managed_root,
        model_cache=model_cache,
    )
