"""Truth isolation: nothing that serves or decides reads the world's truth or the reviewed cases, and the held-out
data is what was pinned."""

import ast
from pathlib import Path

from pgl import heldout

SRC = Path(__file__).resolve().parents[1] / "src" / "pgl"
SERVING = ["agents", "servers", "pipeline"]


def test_serving_code_never_names_the_truth():
    for part in SERVING:
        for f in (SRC / part).rglob("*.py"):
            text = f.read_text()
            for word in ("truth", "evalcases", "accept_pids", "tasks_dev", "tasks_heldout"):
                assert word not in text, f"{f.name} mentions {word}"


def test_serving_code_never_imports_the_evaluation():
    for part in SERVING:
        for f in (SRC / part).rglob("*.py"):
            for node in ast.walk(ast.parse(f.read_text())):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [node.module or ""] if isinstance(node, ast.ImportFrom) else [a.name for a in node.names]
                    assert not any(n.startswith("pgl.evals") for n in names), f"{f.name} imports {names}"


def test_the_held_out_data_is_what_was_pinned():
    assert heldout.fingerprint() == heldout.pinned()


def test_the_production_log_carries_no_truth(tmp_path):
    from pgl.evals.feedback import LOG

    if LOG.exists():
        text = LOG.read_text()
        assert "accept_pids" not in text and "eta_min" not in text and '"outcome"' not in text
