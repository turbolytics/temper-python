"""Helpers for running an inner pytest, as a runner would, and reading what it wrote."""

import json
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

VARS = ("TEMPER_LEVEL", "TEMPER_EVIDENCE", "TEMPER_RUN")


class Inner:
    """Runs a test file in a fresh pytest process with an explicit Temper environment."""

    def __init__(self, pytester, monkeypatch, tmp_path):
        self.pytester = pytester
        self.monkeypatch = monkeypatch
        self.dir = tmp_path / "evidence"

    def run(self, source, *args, level="unit", run=None, runner=True, evidence=None):
        for name in VARS:
            self.monkeypatch.delenv(name, raising=False)
        if runner:
            self.monkeypatch.setenv("TEMPER_LEVEL", level)
            self.monkeypatch.setenv("TEMPER_EVIDENCE", str(evidence or self.dir))
            if run:
                self.monkeypatch.setenv("TEMPER_RUN", run)
        self.pytester.makepyfile(test_inner=source)
        return self.pytester.runpytest_subprocess(*args)

    def files(self):
        return sorted(self.dir.glob("*.jsonl")) if self.dir.exists() else []

    def lines(self):
        out = []
        for f in self.files():
            out.extend(f.read_bytes().decode("utf-8").splitlines(keepends=True))
        return out

    def records(self):
        return [json.loads(line) for line in self.lines()]

    def outcomes(self):
        """test name -> outcome, for inner files with one claim per test."""
        return {r["test"].split("::", 1)[1]: r["outcome"] for r in self.records()}


@pytest.fixture
def inner(pytester, monkeypatch, tmp_path):
    return Inner(pytester, monkeypatch, tmp_path)
