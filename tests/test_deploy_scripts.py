"""The deploy scripts set the system up; they never install packages.

The gun installs like the rest of the project (`uv sync` with extras), and
system dependencies are the user's to install with whatever package
manager their system has, as the guide lists them.
"""

from __future__ import annotations

import re
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"

PACKAGE_MANAGERS = re.compile(
    r"\b(apt-get|apt|aptitude|dpkg|dnf|yum|zypper|pacman|apk|emerge|brew|snap|flatpak)"
    r"\s+(install|add|-S|update|upgrade)\b"
    r"|\bpip3?\s+install\b|\buv\s+(pip|tool)\s+install\b"
)


def _scripts() -> list[Path]:
    return [
        path
        for path in DEPLOY.rglob("*")
        if path.is_file() and path.suffix in {"", ".sh", ".service", ".desktop"}
    ]


def test_there_are_deploy_scripts_to_check() -> None:
    assert any(path.name == "install.sh" for path in _scripts())


def test_no_deploy_script_runs_a_package_manager() -> None:
    offenders = []
    for path in _scripts():
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            code = line.split("#", 1)[0]
            if PACKAGE_MANAGERS.search(code):
                offenders.append(f"{path.relative_to(DEPLOY)}:{number}: {line.strip()}")
    assert offenders == []


def test_the_service_runs_the_gun_from_the_checkouts_venv() -> None:
    unit = (DEPLOY / "pi" / "boresight-gun.service").read_text()
    script = (DEPLOY / "pi" / "install.sh").read_text()

    assert "ExecStart=@GUN@ " in unit
    assert 'GUN="$REPO/.venv/bin/boresight-gun"' in script
    assert "s|@GUN@|$GUN|" in script
