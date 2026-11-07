"""Windows structural checks; PowerShell parsing/interop compilation where pwsh exists."""
from pathlib import Path
import base64
import os
import re
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
WINDOWS = ROOT / "tools/crashwatch/windows"
sys.path.insert(0, str(ROOT / "tools"))
import crashwatch as reader


def test_native_windows_enumeration_and_no_desktop_control():
    source = (WINDOWS / "watch.ps1").read_text()
    for name in ("EnumWindows", "GetWindowThreadProcessId", "GetClassName", "GetWindowText", "GetProcessWindowStation", "GetUserObjectInformation"):
        assert re.search(r"extern\s+\w+\s+" + name + r"\(", source), name
    assert '"#32770"' in source and 'CrashTitle.IsMatch' in source
    assert "Add-Type -TypeDefinition" in source
    assert "GetProcessesByName('Trackmania')" in source and ".StartTime.ToUniversalTime()" in source
    assert not re.search(r"\b(SetForegroundWindow|SetWindowPos|ShowWindow|SendInput|PostMessage|SendMessage|Stop-Process|taskkill|Start-Process|TcpListener|HttpListener)\b", source, re.I)
    assert "UserInteractive" in source and "SessionId -eq 0" in source


def test_windows_schema_snapshot_and_bounded_rotation():
    source = (WINDOWS / "watch.ps1").read_text()
    for field in ("schema_version", "event", "ts", "host", "watcher_id", "interval_seconds", "active_boxes", "games", "errors", "birth", "window_id", "first_seen", "mtime"):
        assert re.search(r"\b" + field + r"\s*=", source), field
    for kind in ("heartbeat", "crash_box", "crash_box_closed", "crash_log", "game_exit", "watcher_error"):
        assert "'" + kind + "'" in source
    assert "LocalApplicationData" in source and "'events.jsonl'" in source
    assert "[IO.FileShare]::None" in source and "finally" in source
    assert "[IO.File]::Delete($script:EventsPath + '.3')" in source
    assert "'LogCrash_*.txt'" in source and "LastWriteTimeUtc" in source
    assert "ReadAllText" not in source and "Get-Content" not in source
    assert "SnapshotLine" in source and "UTF8Encoding($false)" in source


def test_installer_interactive_per_user_logon_and_hidden_restart():
    source = (WINDOWS / "install.ps1").read_text()
    assert "New-ScheduledTaskTrigger -AtLogOn -User $sid" in source
    assert "-LogonType Interactive -RunLevel Limited" in source
    assert "-WindowStyle Hidden" in source and "New-ScheduledTaskSettingsSet -Hidden" in source
    assert "-RestartCount 999" in source and "-RestartInterval (New-TimeSpan -Minutes 1)" in source
    assert "-ExecutionTimeLimit ([TimeSpan]::Zero)" in source
    assert "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries" in source
    assert "-MultipleInstances IgnoreNew" in source
    assert "'tm-crashwatch-' + $sid" in source
    assert "Assert-OwnedTask $existing[0]" in source
    assert not re.search(r"\b(Register-ScheduledTask[^\n]*-Force|Start-ScheduledTask|RunAs|Copy-Item)\b", source)


def test_uninstaller_checks_ownership_before_stopping_and_preserves_files():
    source = (WINDOWS / "uninstall.ps1").read_text()
    assert source.index("Assert-OwnedTask $existing[0]") < source.index("Stop-ScheduledTask")
    assert source.index("Stop-ScheduledTask") < source.index("Unregister-ScheduledTask")
    assert "'tm-crashwatch-' + $sid" in source and "-TaskPath '\\'" in source
    assert not re.search(r"\b(Remove-Item|Stop-Process|taskkill)\b", source, re.I)


def test_scheduler_paths_refuse_percent_expansion_consistently():
    for name in ("install.ps1", "uninstall.ps1"):
        source = (WINDOWS / name).read_text()
        pattern = re.search(r"if \(\$watchPath -match '([^']+)'\)", source).group(1)
        assert re.search(pattern, r"C:\Users\Max\src\%USERNAME%\watch.ps1")
        assert not re.search(pattern, r"C:\Users\Max\src\with spaces\watch.ps1")
        assert "percent signs" in source


def test_documented_start_blocks_do_not_uninstall():
    source = (ROOT / "docs/crashwatch.md").read_text()
    blocks = re.findall(r"```powershell\n(.*?)```", source, re.S)
    assert blocks
    for block in blocks:
        if "Start-ScheduledTask" in block or "windows\\install.ps1" in block:
            assert "uninstall.ps1" not in block


def remote_script():
    return base64.b64decode(reader.remote_command("x-lappy").split()[-1]).decode("utf-16-le")


def test_remote_reads_share_write_delete_and_require_current():
    script = remote_script()
    assert "ReadAllText" not in script
    assert "[IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete" in script
    assert "$stream.Dispose()" in script and "$r.Dispose()" in script
    assert "Current events incomplete" in script and "Current events missing" in script
    assert len(reader.remote_command("x-lappy")) < 8192


def test_remote_reader_powershell_parses_if_available():
    executable = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not executable:
        pytest.skip("PowerShell absent; remote-command parse check requires Windows CI or pwsh")
    literal = remote_script().replace("'", "''")
    script = (f"$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseInput('{literal}',[ref]$tokens,[ref]$errors); "
              "if($errors.Count){$errors | ForEach-Object { [Console]::Error.WriteLine($_.ToString()) }; exit 1}")
    result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows file-sharing semantics")
def test_local_reader_allows_append_and_rotation_while_handle_open(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"before\n")
    with reader.open_event_file(path) as stream:
        with path.open("ab") as writer:
            writer.write(b"after\n")
        path.rename(tmp_path / "events.jsonl.1")
        path.write_bytes(b"new\n")
        assert stream.read() == b"before\nafter\n"


@pytest.mark.skipif(os.name != "nt", reason="requires actual Windows file-sharing semantics")
def test_remote_reader_handle_allows_dotnet_append_and_rotation(tmp_path):
    executable = shutil.which("powershell.exe") or shutil.which("pwsh")
    assert executable
    path = tmp_path / "events.jsonl"
    path.write_bytes(b"before\n")
    opener = re.search(r"\$stream=\[IO.File\]::Open\(.*?\);", remote_script()).group(0)
    literal = str(path).replace("'", "''")
    script = ("$ErrorActionPreference='Stop'; $f='" + literal + "';" + opener
              + "try{[IO.File]::AppendAllText($f,'after');[IO.File]::Move($f,$f+'.1');[IO.File]::WriteAllText($f,'new')}finally{$stream.Dispose()}")
    result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(f"{path}.1").read_bytes() == b"before\nafter"


@pytest.mark.parametrize("name", ["watch.ps1", "install.ps1", "uninstall.ps1"])
def test_powershell_parser_if_available(name):
    pwsh = shutil.which("pwsh")
    if not pwsh:
        pytest.skip("pwsh absent; structural checks only on this host")
    path = str(WINDOWS / name).replace("'", "''")
    script = (f"$tokens=$null; $errors=$null; [void][System.Management.Automation.Language.Parser]::ParseFile('{path}',[ref]$tokens,[ref]$errors); "
              "if($errors.Count){$errors | ForEach-Object { [Console]::Error.WriteLine($_.ToString()) }; exit 1}")
    result = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_windows_interop_compiles_if_powershell_available(tmp_path):
    executable = shutil.which("pwsh") or shutil.which("powershell.exe")
    if not executable:
        pytest.skip("PowerShell absent; native interop compilation requires Windows CI or pwsh")
    source = (WINDOWS / "watch.ps1").read_text()
    native = re.search(r"\$nativeSource = @'\n(.*?)\n'@", source, re.S).group(1)
    script = tmp_path / "compile-interop.ps1"
    script.write_text("$ErrorActionPreference='Stop'\nAdd-Type -TypeDefinition @'\n" + native + "\n'@ -Language CSharp -ErrorAction Stop\n")
    result = subprocess.run([executable, "-NoProfile", "-NonInteractive", "-File", str(script)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
