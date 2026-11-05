"""Execute the server supervision decision without a socket or live timeout."""
from pathlib import Path
import subprocess
from test_pack_updates import as_runner

ROOT = Path(__file__).resolve().parents[1]


def test_restart_only_after_owned_worker_terminates(as_runner, tmp_path):
    case = tmp_path / "server.as"
    case.write_text('''
void RunTests() {
    Check(!TmMcp::ShouldRestartSocketLoop(false, true, false), "shutdown never restarts");
    Check(!TmMcp::ShouldRestartSocketLoop(true, true, true), "live worker remains owned even during stall");
    Check(!TmMcp::ShouldRestartSocketLoop(true, false, false), "unassigned worker not presumed dead");
    Check(TmMcp::ShouldRestartSocketLoop(true, true, false), "terminated worker must be replaced");
}
''')
    result = subprocess.run([str(as_runner), str(ROOT / "src/ServerPolicy.as"), str(case)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_startup_and_shutdown_own_supervisor_and_worker():
    text = (ROOT / "src/Server.as").read_text()
    assert "@g_serverWorker = startnew" in text
    assert "startnew(CoroutineFunc(SuperviseServerLoop))" in text
    assert "g_serverWorker.IsRunning()" in text
    assert "ShouldRestartSocketLoop(g_running" in text
    body = text[text.index("void SuperviseServerLoop("):text.index("void StartServerAfterDelay(")]
    assert body.index("CloseListener();") < body.index("@g_serverWorker = startnew")
