from pathlib import Path

import pytest

from homelab_maker import settings
from homelab_maker.settings import Preferences


def test_without_a_file_the_defaults_apply() -> None:
    assert settings.load() == Preferences()
    assert Preferences().scheme == "system"


def test_preferences_survive_a_round_trip(private_preferences: Path) -> None:
    prefs = Preferences(scheme="dark", last_directory="C:/labs", geometry="AAEC")
    settings.save(prefs)
    assert (private_preferences / "gui.ini").is_file()
    assert settings.load() == prefs


def test_the_configuration_folder_can_be_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(settings.CONFIG_DIR_VARIABLE, str(tmp_path / "elsewhere"))
    assert settings.config_dir() == tmp_path / "elsewhere"
    assert settings.settings_path() == tmp_path / "elsewhere" / "gui.ini"


def test_without_the_override_it_is_the_users_own_folder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(settings.CONFIG_DIR_VARIABLE)
    assert "HomeLabMaker" in str(settings.config_dir())


def test_a_damaged_file_gives_the_defaults(private_preferences: Path) -> None:
    private_preferences.mkdir(parents=True)
    (private_preferences / "gui.ini").write_text("this is [not an ini\nfile", encoding="utf-8")
    assert settings.load() == Preferences()


def test_a_file_that_is_not_text_gives_the_defaults(private_preferences: Path) -> None:
    private_preferences.mkdir(parents=True)
    (private_preferences / "gui.ini").write_bytes(b"\xff\xfe\x00\x80")
    assert settings.load() == Preferences()


def test_an_unknown_theme_falls_back_to_the_system_one(private_preferences: Path) -> None:
    private_preferences.mkdir(parents=True)
    (private_preferences / "gui.ini").write_text("[window]\nscheme = neon\n", encoding="utf-8")
    assert settings.load().scheme == "system"


def test_a_disk_that_refuses_is_not_an_error(
    private_preferences: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The configuration "folder" is a file, so nothing can be written under it.
    private_preferences.parent.mkdir(parents=True, exist_ok=True)
    private_preferences.write_text("in the way", encoding="utf-8")
    settings.save(Preferences(scheme="dark"))
    assert settings.load() == Preferences()
