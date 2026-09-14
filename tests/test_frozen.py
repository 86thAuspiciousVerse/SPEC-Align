import sys
from specalign.integration import launch_command, mcp_configuration


def test_frozen_command_does_not_invoke_python(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, 'executable', str(tmp_path / 'specalign.exe'))
    assert launch_command(tmp_path, 'hook') == [sys.executable, '--root', str(tmp_path), 'hook']
    _, text, _ = mcp_configuration(tmp_path, {})
    assert '"-m"' not in text
    assert 'specalign.exe' in text


def test_python_command_preserved(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    assert launch_command(tmp_path, 'serve') == [sys.executable, '-m', 'specalign', '--root', str(tmp_path), 'serve']

