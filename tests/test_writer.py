"""The evidence file writer, directly."""

import json
import os
import re

import pytest

from temper import _evidence


@pytest.mark.covers("adapter.never_truncates", subject="adapter.python")
def test_each_record_is_one_write_in_append_mode(tmp_path, monkeypatch):
    writes = []
    real = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: (writes.append(data), real(fd, data))[1])
    w = _evidence.Writer(tmp_path, "unit")
    for i in range(5):
        w.write({"covers": f"c.{i}", "test": "t", "level": "unit", "outcome": "pass"})
    w.close()
    assert len(writes) == 5
    assert all(d.endswith(b"\n") and d.count(b"\n") == 1 for d in writes)
    (f,) = tmp_path.glob("*.jsonl")
    assert re.fullmatch(r"unit-%d-[0-9a-f]{8}\.jsonl" % os.getpid(), f.name)
    assert len(f.read_bytes().splitlines()) == 5


@pytest.mark.covers("adapter.never_truncates", subject="adapter.python")
def test_two_writers_never_share_a_file(tmp_path):
    a = _evidence.Writer(tmp_path, "unit")
    b = _evidence.Writer(tmp_path, "unit")
    a.write({"test": "t", "level": "unit", "outcome": "pass"})
    b.write({"test": "t", "level": "unit", "outcome": "pass"})
    a.close()
    b.close()
    assert len(list(tmp_path.glob("*.jsonl"))) == 2


@pytest.mark.covers("adapter.never_truncates", subject="adapter.python")
def test_nothing_is_created_until_the_first_record(tmp_path):
    target = tmp_path / "evidence"
    w = _evidence.Writer(target, "unit")
    w.close()
    assert not target.exists()


@pytest.mark.covers("adapter.python")
def test_a_forked_child_writes_to_its_own_file(tmp_path):
    if not hasattr(os, "fork"):
        pytest.skip("no fork on this platform")
    w = _evidence.Writer(tmp_path, "unit")
    w.write({"test": "parent", "level": "unit", "outcome": "pass"})
    pid = os.fork()
    if pid == 0:
        try:
            w.write({"test": "child", "level": "unit", "outcome": "pass"})
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    w.close()
    files = sorted(tmp_path.glob("*.jsonl"))
    assert len(files) == 2
    for f in files:
        assert len(f.read_bytes().splitlines()) == 1


@pytest.mark.covers("adapter.python")
def test_a_lone_surrogate_in_a_test_id_is_escaped_not_fatal(tmp_path):
    w = _evidence.Writer(tmp_path, "unit")
    w.write({"test": "bad\ud800id", "level": "unit", "outcome": "pass"})
    w.close()
    (f,) = tmp_path.glob("*.jsonl")
    assert json.loads(f.read_bytes())["test"] == "bad\ud800id"


@pytest.mark.covers("adapter.python")
def test_non_ascii_is_written_as_utf8_not_escaped(tmp_path):
    w = _evidence.Writer(tmp_path, "unit")
    w.write({"test": "héllo日本", "level": "unit", "outcome": "pass"})
    w.close()
    (f,) = tmp_path.glob("*.jsonl")
    assert "héllo日本".encode("utf-8") in f.read_bytes()


@pytest.mark.covers("adapter.python")
def test_a_level_cannot_escape_the_directory_through_the_file_name(tmp_path):
    w = _evidence.Writer(tmp_path / "ev", "../../x/y")
    w.write({"test": "t", "level": "../../x/y", "outcome": "pass"})
    w.close()
    (f,) = (tmp_path / "ev").glob("*.jsonl")
    assert "/" not in f.name
