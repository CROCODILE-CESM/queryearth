"""The docs run as written: llms.txt's rule file and Python, and the README's Labels."""

import inspect
import os
import re
from pathlib import Path

import queryearth as qe

ROOT = Path(__file__).resolve().parents[1]


def blocks(path, kind):
    return re.findall(rf"```{kind}\n(.*?)```", path.read_text(encoding="utf-8"), re.S)


def test_llms_txt_runs_as_written(tmp_path):
    llms = ROOT / "docs" / "source" / "llms.txt"
    (rules,) = blocks(llms, "json")
    (tmp_path / "rules.geojson").write_text(rules)
    here, namespace = os.getcwd(), {}
    os.chdir(tmp_path)
    try:
        for code in blocks(llms, "python"):
            exec(code, namespace)
    finally:
        os.chdir(here)
    assert [rule.code for rule in namespace["findings"]] == ["MINE002", "MINE001"]
    written = qe.Registry.from_file(
        tmp_path / "mine.geojson", dimensions=[qe.Axis("resolution", "km")]
    )
    assert [rule.code for rule in written.rules] == ["ARCTIC001"]


def test_the_readme_shows_the_source_of_labels():
    assert inspect.getsource(qe.Labels).strip() in "".join(
        blocks(ROOT / "README.md", "python")
    )
