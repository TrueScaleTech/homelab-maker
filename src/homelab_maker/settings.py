"""What the window remembers between runs: theme, window size, the last folder used.

These are preferences, not data. They live in ``gui.ini`` in the user's configuration
folder, which ``HOMELAB_MAKER_CONFIG_DIR`` can move, so tests and the build's smoke check
never touch the real one. A missing or damaged file is never an error: the defaults apply.
"""

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

import platformdirs

from homelab_maker.gui.theme import Scheme

CONFIG_DIR_VARIABLE = "HOMELAB_MAKER_CONFIG_DIR"
_SECTION = "window"


def _scheme(text: str) -> Scheme:
    if text == "light":
        return "light"
    if text == "dark":
        return "dark"
    return "system"


def config_dir() -> Path:
    override = os.environ.get(CONFIG_DIR_VARIABLE)
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("HomeLabMaker", "TrueScaleTech", roaming=False))


def settings_path() -> Path:
    return config_dir() / "gui.ini"


@dataclass(slots=True)
class Preferences:
    scheme: Scheme = "system"
    last_directory: str = ""
    geometry: str = ""  # base64 of Qt's saved window geometry


def load() -> Preferences:
    parser = configparser.ConfigParser()
    try:
        parser.read(settings_path(), encoding="utf-8")
    except (OSError, configparser.Error, UnicodeError):
        return Preferences()
    section = parser[_SECTION] if parser.has_section(_SECTION) else {}
    return Preferences(
        scheme=_scheme(section.get("scheme", "system")),
        last_directory=section.get("last_directory", ""),
        geometry=section.get("geometry", ""),
    )


def save(preferences: Preferences) -> None:
    """Write the preferences. A disk that refuses is not worth interrupting the user for."""
    parser = configparser.ConfigParser()
    parser[_SECTION] = {
        "scheme": preferences.scheme,
        "last_directory": preferences.last_directory,
        "geometry": preferences.geometry,
    }
    path = settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            parser.write(handle)
    except OSError:
        return
