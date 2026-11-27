"""ADR-0008 status and scoring text (QA-006, QA-048)."""

import re
from pathlib import Path

ADR_DIR = Path(__file__).resolve().parents[2] / "docs" / "adr"


def _adr() -> str:
    return (ADR_DIR / "0008-mvp-scope.md").read_text(encoding="utf-8")


def test_qa_006_adr_0008_accepted() -> None:
    text = _adr()
    front = re.match(r"---\n(.*?)\n---", text, re.S)
    assert front is not None
    assert "status: accepted" in front.group(1)
    index = (ADR_DIR / "index.md").read_text(encoding="utf-8")
    row = next(line for line in index.splitlines() if "ADR-0008" in line)
    assert "Accepted" in row
    flat = " ".join(text.split())
    assert "`Citation` is a value object" in flat
    assert "Persistence is deferred" in flat
    assert "0.4 and 0.6 are provisional" in flat


def test_qa_048_weights_provisional() -> None:
    flat = " ".join(_adr().split())
    assert "0.4 * retrieval + 0.6 * rerank" in flat
    assert "provisional" in flat
    assert "until the evaluation runs" in flat
