"""The promises of SECURITY.md that can be checked by reading the code."""

import ast
from pathlib import Path

SOURCE = Path(__file__).parent.parent / "src" / "homelab_maker"

# Anything that could open a connection, run a program or send something away.
FORBIDDEN = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "subprocess",
    "webbrowser",
    "PySide6.QtNetwork",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
}


def imported_names(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def test_no_module_of_the_application_can_reach_the_network_or_run_a_program() -> None:
    offenders = {}
    for path in sorted(SOURCE.rglob("*.py")):
        found = {
            name
            for name in imported_names(path)
            if name in FORBIDDEN or name.split(".")[0] in FORBIDDEN
        }
        if found:
            offenders[path.name] = sorted(found)
    assert offenders == {}


def test_the_check_itself_would_notice(tmp_path: Path) -> None:
    sample = tmp_path / "bad.py"
    sample.write_text("import socket\nfrom urllib import request\n", encoding="utf-8")
    names = imported_names(sample)
    assert {"socket", "urllib", "urllib.request"} <= names
