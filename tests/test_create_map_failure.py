"""A failed menu click chain must remain a failed public tool result."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_create_map_preserves_semantic_failure_and_diagnostics():
    text = (ROOT / "src/ManialinkIntrospection.as").read_text()
    body = text[text.index("Json::Value@ CreateMapViaMenu("):text.index("// The native click-dispatch", text.index("Json::Value@ CreateMapViaMenu("))] if "// The native click-dispatch" in text else text[text.index("Json::Value@ CreateMapViaMenu("):]
    assert "return MakeSuccess(rv);" not in body
    assert "return CreateMapMenuResult(rv);" in body
    assert '"CREATE_MAP_FAILED"' in text
    assert 'result["output"] = output;' in text
    assert "EditNewMap" in text
