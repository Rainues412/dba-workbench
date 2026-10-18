"""Runtime configuration for the local DBA workbench."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple


VALID_MODES = {"local", "development", "lan"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_ACTIONS = {"check", "edit", "folder", "open", "pick-folder", "run", "scan"}
RUN_EXTENSIONS = {".bat", ".cmd", ".ps1", ".py", ".sh"}


def _csv(value: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


def _paths(value: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in value.split(os.pathsep) if item.strip())


@dataclass(frozen=True)
class Settings:
    mode: str
    host: str
    port: int
    reload: bool
    open_browser: bool
    allowed_hosts: Tuple[str, ...]
    cors_origins: Tuple[str, ...]
    local_capabilities: bool
    allowed_roots: Tuple[str, ...]
    allowed_local_actions: Tuple[str, ...]
    allowed_run_extensions: Tuple[str, ...]

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        mode = env.get("DBA_MODE", "local").strip().lower()
        if mode not in VALID_MODES:
            raise ValueError("DBA_MODE must be local, development, or lan")
        if mode == "lan":
            raise ValueError(
                "DBA_MODE=lan is disabled until HTTPS and LAN hardening are implemented"
            )

        host = env.get("DBA_HOST", "127.0.0.1").strip()
        if host not in LOOPBACK_HOSTS:
            raise ValueError("local and development modes must bind to a loopback host")

        try:
            port = int(env.get("DBA_PORT", "8686"))
        except ValueError as exc:
            raise ValueError("DBA_PORT must be an integer") from exc
        if not 1 <= port <= 65535:
            raise ValueError("DBA_PORT must be between 1 and 65535")

        default_reload = mode == "development"
        reload_enabled = _boolean(
            env.get("DBA_RELOAD", str(default_reload)), "DBA_RELOAD"
        )
        if reload_enabled and mode != "development":
            raise ValueError("DBA_RELOAD is only allowed in development mode")

        default_open_browser = mode == "local"
        open_browser = _boolean(
            env.get("DBA_OPEN_BROWSER", str(default_open_browser)),
            "DBA_OPEN_BROWSER",
        )

        allowed_hosts = _csv(
            env.get("DBA_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
        )
        if not allowed_hosts or "*" in allowed_hosts:
            raise ValueError("DBA_ALLOWED_HOSTS must be a non-empty explicit allowlist")

        default_origins = f"http://localhost:{port},http://127.0.0.1:{port}"
        cors_origins = _csv(env.get("DBA_CORS_ORIGINS", default_origins))
        if "*" in cors_origins:
            raise ValueError("DBA_CORS_ORIGINS must not contain a wildcard")

        local_capabilities = _boolean(
            env.get("DBA_LOCAL_CAPABILITIES", "false"),
            "DBA_LOCAL_CAPABILITIES",
        )
        raw_roots = _paths(env.get("DBA_ALLOWED_ROOTS", ""))
        for root in raw_roots:
            if root.startswith(("\\\\", "//")) or not Path(root).is_absolute():
                raise ValueError(
                    f"DBA_ALLOWED_ROOTS contains a non-local or relative path: {root}"
                )
        allowed_roots = tuple(str(Path(root).resolve()) for root in raw_roots)
        if local_capabilities and not allowed_roots:
            raise ValueError(
                "DBA_ALLOWED_ROOTS must contain at least one absolute directory "
                "when local capabilities are enabled"
            )
        for root in allowed_roots:
            path = Path(root)
            if not path.is_dir():
                raise ValueError(f"DBA_ALLOWED_ROOTS contains an invalid directory: {root}")

        allowed_local_actions = tuple(
            action.lower()
            for action in _csv(
                env.get(
                    "DBA_ALLOWED_LOCAL_ACTIONS",
                    "check,edit,folder,open,pick-folder,scan",
                )
            )
        )
        unknown_actions = set(allowed_local_actions) - LOCAL_ACTIONS
        if unknown_actions:
            raise ValueError(
                "DBA_ALLOWED_LOCAL_ACTIONS contains unsupported actions: "
                + ", ".join(sorted(unknown_actions))
            )

        allowed_run_extensions = tuple(
            extension.lower()
            for extension in _csv(env.get("DBA_ALLOWED_RUN_EXTENSIONS", ""))
        )
        unknown_extensions = set(allowed_run_extensions) - RUN_EXTENSIONS
        if unknown_extensions:
            raise ValueError(
                "DBA_ALLOWED_RUN_EXTENSIONS contains unsupported extensions: "
                + ", ".join(sorted(unknown_extensions))
            )
        if "run" in allowed_local_actions and not allowed_run_extensions:
            raise ValueError(
                "DBA_ALLOWED_RUN_EXTENSIONS is required when the run action is enabled"
            )

        return cls(
            mode=mode,
            host=host,
            port=port,
            reload=reload_enabled,
            open_browser=open_browser,
            allowed_hosts=allowed_hosts,
            cors_origins=cors_origins,
            local_capabilities=local_capabilities,
            allowed_roots=allowed_roots,
            allowed_local_actions=allowed_local_actions,
            allowed_run_extensions=allowed_run_extensions,
        )


settings = Settings.from_env()
