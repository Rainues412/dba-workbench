"""Identify the local Workbench service without waiting on unused ports."""

from __future__ import annotations

import socket
import urllib.request


def probe_workbench(host: str, port: int) -> str:
    """Return ``dba``, ``other``, or ``down`` for the local endpoint."""
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        # Winsock may take a full connection timeout to report an unused port.
        # A successful exclusive bind lets the common cold-start path skip that.
        try:
            with socket.socket() as probe:
                probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                probe.bind((host, port))
        except OSError:
            pass
        else:
            return "down"

    try:
        with urllib.request.urlopen(f"http://{host}:{port}/", timeout=1.0) as response:
            body = response.read(4096).decode("utf-8", errors="ignore")
            return "dba" if "DBA 工作台" in body else "other"
    except OSError:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return "other"
        except OSError:
            return "down"
