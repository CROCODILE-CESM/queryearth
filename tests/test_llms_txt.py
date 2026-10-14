"""docs/source/llms.txt: its rule file loads and its Python runs as written."""

import os
import re
from pathlib import Path

LLMS = Path(__file__).resolve().parents[1] / "docs" / "source" / "llms.txt"


def blocks(kind):
    return re.findall(rf"```{kind}\n(.*?)```", LLMS.read_text(encoding="utf-8"), re.S)


def test_the_rule_file_and_the_python_run_as_written(tmp_path):
    (rules,) = blocks("json")
    (tmp_path / "rules.geojson").write_text(rules)
    here = os.getcwd()
    os.chdir(tmp_path)
    try:
        namespace = {}
        for code in blocks("python"):
            exec(code, namespace)
    finally:
        os.chdir(here)
    findings = namespace["findings"]
    assert [f.code for f in findings] == ["MINE002", "MINE001"]
    assert str(findings[0]) in LLMS.read_text(encoding="utf-8")  # the example line
    assert [r["code"] for r in namespace["described"]["rules"]] == [
        "MINE001",
        "MINE002",
        "MINE003",
    ]
    assert (tmp_path / "mine.geojson").exists()
