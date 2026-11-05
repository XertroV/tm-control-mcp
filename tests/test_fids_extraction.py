"""Verify extraction completeness policy in production AngelScript."""
from pathlib import Path
import subprocess
from test_pack_updates import as_runner

ROOT = Path(__file__).resolve().parents[1]


def test_extraction_requires_disk_evidence(as_runner, tmp_path):
    case = tmp_path / "extract.as"
    case.write_text('''
void RunTests() {
    using namespace TmMcp;
    Check(FidsExtractionState(true, true, 5666, 4096) == "size_mismatch", "API true cannot hide truncation");
    Check(FidsExtractionState(true, true, 5666, 5666) == "verified", "matching expected byte count");
    Check(FidsExtractionState(true, false, 5666, 0) == "missing", "missing output");
    Check(FidsExtractionState(false, true, 5666, 5666) == "api_failed", "stale file cannot turn API failure into success");
    Check(FidsExtractionState(true, true, 0, 100) == "size_unknown", "unknown expected size is not verification");
    Check(FidsExtractionState(true, true, 100, 0) == "size_mismatch", "zero byte output");
}
''')
    result = subprocess.run([str(as_runner), str(ROOT / "src/FidsExtractionPolicy.as"), str(case)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
