"""Tests for autostart.py, using an in-memory fake registry."""

from contextlib import contextmanager
from pathlib import Path

from remote_mouse import autostart


class FakeRegistry:
    """Mimics the parts of `winreg` that autostart.py uses."""

    HKEY_CURRENT_USER = "HKCU"
    KEY_READ = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values: dict[str, str] = {}

    @contextmanager
    def OpenKey(self, root, path, reserved, access):  # noqa: N802 (winreg naming)
        yield path

    CreateKeyEx = OpenKey  # noqa: N815

    def QueryValueEx(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):  # noqa: N802
        self.values[name] = value

    def DeleteValue(self, key, name):  # noqa: N802
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_command_for_packaged_exe():
    cmd = autostart.build_command(r"C:\Apps\RemoteMouse.exe", frozen=True)
    assert cmd == r'"C:\Apps\RemoteMouse.exe" --background'


def test_command_from_source_prefers_pythonw(tmp_path):
    (tmp_path / "python.exe").write_text("")
    (tmp_path / "pythonw.exe").write_text("")
    launcher = Path(r"C:\src\remote_mouse_launcher.py")
    cmd = autostart.build_command(str(tmp_path / "python.exe"), frozen=False, launcher=launcher)
    assert cmd == f'"{tmp_path / "pythonw.exe"}" "{launcher}" --background'


def test_command_from_source_falls_back_to_python(tmp_path):
    (tmp_path / "python.exe").write_text("")
    cmd = autostart.build_command(str(tmp_path / "python.exe"), frozen=False, launcher=Path("l.py"))
    assert cmd.startswith(f'"{tmp_path / "python.exe"}"')


def test_enable_disable_roundtrip():
    reg = FakeRegistry()
    assert not autostart.is_enabled(reg)
    autostart.enable(reg, command="cmd")
    assert autostart.is_enabled(reg)
    assert reg.values[autostart.VALUE_NAME] == "cmd"
    autostart.disable(reg)
    assert not autostart.is_enabled(reg)


def test_disable_when_already_disabled_is_harmless():
    autostart.disable(FakeRegistry())


def test_refresh_updates_stale_path():
    reg = FakeRegistry()
    reg.values[autostart.VALUE_NAME] = '"C:\\old\\RemoteMouse.exe" --background'
    autostart.refresh_if_enabled(reg)
    assert reg.values[autostart.VALUE_NAME] == autostart.current_command()


def test_refresh_does_nothing_when_disabled():
    reg = FakeRegistry()
    autostart.refresh_if_enabled(reg)
    assert reg.values == {}


def test_real_registry_query_does_not_crash():
    # Read-only check against the real registry (never writes).
    assert isinstance(autostart.is_enabled(), bool)
