"""Runtime configuration for the local DBA workbench."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Optional, Tuple


VALID_MODES = {"local", "development", "lan"}
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _csv(value: str) -> Tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _boolean(value: str, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be true or false")


@dataclass(frozen=True)
class Settings:
    mode: str
    host: str
    port: int
    reload: bool
    open_browser: bool
    allowed_hosts: Tuple[str, ...]
    cors_origins: Tuple[str, ...]

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "Settings":
        env = os.environ if environ is None else environ
        mode = env.get("DBA_MODE", "local").strip().lower()
        if mode not in VALID_MODES:
            raise ValueError("DBA_MODE must be local, development, or lan")
        if mode == "lan":
            raise ValueError(
                "DBA_MODE=lan is disabled until authentication and LAN hardening are implemented"
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

        return cls(
            mode=mode,
            host=host,
            port=port,
            reload=reload_enabled,
            open_browser=open_browser,
            allowed_hosts=allowed_hosts,
            cors_origins=cors_origins,
        )


settings = Settings.from_env()
