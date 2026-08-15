"""Regression tests for the read-only Higgsfield corpus analyzer."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "analyze_hg_corpus.py"


def run_analyzer(corpus_dir: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(corpus_dir), str(output_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def test_empty_corpus_writes_zeroed_asset(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    output_path = tmp_path / "asset.json"

    result = run_analyzer(corpus_dir, output_path)

    assert result.returncode == 0, result.stderr
    asset = json.loads(output_path.read_text(encoding="utf-8"))
    assert asset["corpus_prompts"] == 0
    assert set(asset["block_frequency_pct"].values()) == {0.0}


def test_output_path_inside_corpus_is_rejected(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    output_path = corpus_dir / "asset.json"

    result = run_analyzer(corpus_dir, output_path)

    assert result.returncode != 0
    assert "output_path must be outside corpus_dir" in result.stderr
    assert not output_path.exists()
