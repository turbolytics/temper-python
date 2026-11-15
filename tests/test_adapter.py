"""The adapter contract (docs/adapters.md in turbolytics/temper), proven through real pytest runs."""

import json
import re
from pathlib import Path

import pytest

SUBJECT = "adapter.python"
CLAIM = '@pytest.mark.covers("demo.claim")\n'


def inner_test(body, mark=CLAIM, name="test_it"):
    return "import pytest\n\n" + mark + f"def {name}():\n" + "".join(
        f"    {line}\n" for line in body.strip().splitlines()
    )


@pytest.mark.covers("adapter.python")
@pytest.mark.covers("outcomes/pass", subject=SUBJECT)
def test_pass_writes_one_exact_record(inner):
    inner.run(
        "import pytest\n\n"
        '@pytest.mark.covers("sink.flush.keeps_batch", subject="sink.kafka")\n'
        "def test_flush():\n    assert True\n",
        run="ci-1",
    )
    (line,) = inner.lines()
    assert line.endswith("\n") and not line.endswith("\n\n")
    rec = json.loads(line)
    assert list(rec) == ["covers", "subject", "test", "level", "outcome", "run", "at"]
    assert rec["covers"] == "sink.flush.keeps_batch"
    assert rec["subject"] == "sink.kafka"
    assert rec["test"] == "test_inner.py::test_flush"
    assert (rec["level"], rec["outcome"], rec["run"]) == ("unit", "pass", "ci-1")
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rec["at"])
    assert line == json.dumps(rec, separators=(",", ":"), ensure_ascii=False) + "\n"


@pytest.mark.covers("adapter.python")
def test_empty_optional_keys_are_left_out(inner):
    inner.run(inner_test("pass"))
    (rec,) = inner.records()
    assert list(rec) == ["covers", "test", "level", "outcome", "at"]


@pytest.mark.covers("adapter.python")
def test_unmarked_tests_record_nothing(inner):
    inner.run("def test_plain():\n    assert True\n")
    assert inner.files() == []


# --- adapter.failure_never_passes ------------------------------------------------

FAILURES = {
    "assert": ("assert 1 == 2", "fail"),
    "pytest_fail": ("pytest.fail('no')", "fail"),
    "exception": ("raise ValueError('boom')", "error"),
    "xfail_fails": ("pytest.xfail('expected')", "fail"),
}


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
@pytest.mark.covers("outcomes/fail", subject=SUBJECT)
@pytest.mark.covers("outcomes/error", subject=SUBJECT)
@pytest.mark.parametrize("name", sorted(FAILURES))
def test_a_failing_body_never_records_pass(inner, name):
    body, want = FAILURES[name]
    inner.run(inner_test(body))
    (rec,) = inner.records()
    assert rec["outcome"] == want


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
@pytest.mark.covers("outcomes/error", subject=SUBJECT)
def test_a_setup_error_records_error(inner):
    inner.run(
        "import pytest\n\n"
        "@pytest.fixture\ndef broken():\n    raise RuntimeError('setup')\n\n"
        '@pytest.mark.covers("demo.claim")\n'
        "def test_it(broken):\n    assert True\n"
    )
    (rec,) = inner.records()
    assert rec["outcome"] == "error"


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
@pytest.mark.covers("outcomes/error", subject=SUBJECT)
def test_a_teardown_error_after_a_passing_body_records_error_not_pass(inner):
    inner.run(
        "import pytest\n\n"
        "@pytest.fixture\ndef leaky():\n    yield\n    raise RuntimeError('teardown')\n\n"
        '@pytest.mark.covers("demo.claim")\n'
        "def test_it(leaky):\n    assert True\n"
    )
    (rec,) = inner.records()  # exactly one record, written after teardown
    assert rec["outcome"] == "error"


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
@pytest.mark.covers("outcomes/fail", subject=SUBJECT)
@pytest.mark.parametrize(
    "mark",
    ["@pytest.mark.xfail", "@pytest.mark.xfail(strict=True)"],
    ids=["xfail", "strict"],
)
def test_xfail_never_records_pass(inner, mark):
    # fails as expected -> fail; passes unexpectedly -> fail
    for body in ("assert False", "assert True"):
        inner.run(inner_test(body, mark=mark + "\n" + CLAIM), "-p", "no:cacheprovider")
    assert [r["outcome"] for r in inner.records()] == ["fail", "fail"]


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
def test_fail_then_skip_records_fail(inner):
    inner.run(
        "import pytest\n\n"
        "@pytest.fixture\ndef skipper():\n    yield\n    pytest.skip('late')\n\n"
        '@pytest.mark.covers("demo.claim")\n'
        "def test_it(skipper):\n    assert False\n"
    )
    (rec,) = inner.records()
    assert rec["outcome"] == "fail"


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
def test_a_crashing_run_is_never_recorded_as_pass(inner):
    # the process dies mid-test: nothing is written for it (no record, so no pass)
    inner.run(
        "import os\nimport pytest\n\n" + CLAIM + "def test_it():\n    os._exit(7)\n"
    )
    assert inner.records() == []


@pytest.mark.covers("adapter.failure_never_passes", subject=SUBJECT)
@pytest.mark.covers("outcomes/error", subject=SUBJECT)
@pytest.mark.parametrize("phase", ["setup", "teardown"])
def test_an_assertion_in_setup_or_teardown_is_an_error_not_a_test_failure(inner, phase):
    fixture = (
        "    assert False\n    yield\n" if phase == "setup" else "    yield\n    assert False\n"
    )
    inner.run(
        "import pytest\n\n@pytest.fixture\ndef fx():\n" + fixture + "\n"
        '@pytest.mark.covers("demo.claim")\n'
        "def test_it(fx):\n    assert True\n"
    )
    (rec,) = inner.records()
    assert rec["outcome"] == "error"


# --- adapter.skip_records_skip ---------------------------------------------------

SKIPS = {
    "runtime": inner_test("pytest.skip('later')"),
    "skipif": inner_test("assert True", mark='@pytest.mark.skipif(True, reason="x")\n' + CLAIM),
    "skip_mark": inner_test("assert True", mark='@pytest.mark.skip\n' + CLAIM),
    "importorskip": inner_test("pytest.importorskip('no_such_module_xyz')"),
}


@pytest.mark.covers("adapter.skip_records_skip", subject=SUBJECT)
@pytest.mark.covers("outcomes/skip", subject=SUBJECT)
@pytest.mark.parametrize("name", sorted(SKIPS))
def test_a_skipped_test_records_skip(inner, name):
    inner.run(SKIPS[name])
    (rec,) = inner.records()
    assert rec["outcome"] == "skip"


@pytest.mark.covers("adapter.skip_records_skip", subject=SUBJECT)
def test_a_skip_in_setup_records_skip(inner):
    inner.run(
        "import pytest\n\n"
        "@pytest.fixture\ndef need():\n    pytest.skip('no service')\n\n"
        '@pytest.mark.covers("demo.claim")\n'
        "def test_it(need):\n    assert True\n"
    )
    (rec,) = inner.records()
    assert rec["outcome"] == "skip"


# --- adapter.level_from_runner ---------------------------------------------------


@pytest.mark.covers("adapter.level_from_runner", subject=SUBJECT)
def test_the_level_is_the_runners_verbatim(inner):
    inner.run(inner_test("pass"), level="integration")
    (rec,) = inner.records()
    assert rec["level"] == "integration"


@pytest.mark.covers("adapter.level_from_runner", subject=SUBJECT)
def test_a_test_that_changes_its_environment_cannot_change_level_or_place(inner, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    inner.run(
        inner_test(
            "import os\n"
            "os.environ['TEMPER_LEVEL'] = 'release'\n"
            f"os.environ['TEMPER_EVIDENCE'] = {str(elsewhere)!r}\n"
            "os.environ['TEMPER_RUN'] = 'forged'"
        ),
        run="real",
    )
    (rec,) = inner.records()
    assert (rec["level"], rec["run"]) == ("unit", "real")
    assert not elsewhere.exists()


@pytest.mark.covers("adapter.level_from_runner", subject=SUBJECT)
def test_a_mark_cannot_set_a_level(inner):
    result = inner.run(
        "import pytest\n\n"
        '@pytest.mark.covers("demo.claim", level="release")\n'
        "def test_it():\n    assert True\n"
    )
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*level*"])
    assert inner.records() == []


# --- adapter.silent_without_runner -----------------------------------------------


@pytest.mark.covers("adapter.silent_without_runner", subject=SUBJECT)
@pytest.mark.parametrize("missing", ["TEMPER_LEVEL", "TEMPER_EVIDENCE", "both", "empty"])
def test_without_the_runner_environment_nothing_is_recorded(inner, tmp_path, monkeypatch, missing):
    src = inner_test("assert True") + "\n" + inner_test("assert False", name="test_bad")
    inner.pytester.makepyfile(test_inner=src)
    for name in ("TEMPER_LEVEL", "TEMPER_EVIDENCE", "TEMPER_RUN"):
        monkeypatch.delenv(name, raising=False)
    if missing in ("TEMPER_EVIDENCE",):
        monkeypatch.setenv("TEMPER_LEVEL", "unit")
    if missing == "TEMPER_LEVEL":
        monkeypatch.setenv("TEMPER_EVIDENCE", str(inner.dir))
    if missing == "empty":
        monkeypatch.setenv("TEMPER_LEVEL", "")
        monkeypatch.setenv("TEMPER_EVIDENCE", "")
    with_plugin = inner.pytester.runpytest_subprocess()
    without = inner.pytester.runpytest_subprocess("-p", "no:temper")
    assert not inner.dir.exists()
    assert with_plugin.ret == without.ret
    # Without the plugin the marks are unknown and pytest warns; the results are the same.
    def results(r):
        return {k: v for k, v in r.parseoutcomes().items() if k != "warnings"}

    assert results(with_plugin) == results(without)


@pytest.mark.covers("adapter.silent_without_runner", subject=SUBJECT)
def test_a_malformed_mark_is_ignored_without_the_runner(inner):
    result = inner.run(
        "import pytest\n\n"
        '@pytest.mark.covers(42)\n'
        "def test_it():\n    assert True\n",
        runner=False,
    )
    assert result.ret == 0


# --- adapter.never_truncates -----------------------------------------------------


@pytest.mark.covers("adapter.never_truncates", subject=SUBJECT)
def test_existing_evidence_is_untouched_and_each_process_has_its_own_file(inner):
    inner.dir.mkdir()
    old = inner.dir / "unit-1-deadbeef.jsonl"
    old.write_bytes(b'{"covers":"old.claim","test":"t","level":"unit","outcome":"pass"}\n')
    stray = inner.dir / "notes.txt"
    stray.write_bytes(b"keep me")
    inner.run(inner_test("pass"))
    inner.run(inner_test("pass"))
    assert old.read_bytes().startswith(b'{"covers":"old.claim"')
    assert old.read_bytes().count(b"\n") == 1
    assert stray.read_bytes() == b"keep me"
    new = [f for f in inner.files() if f != old]
    assert len(new) == 2
    for f in new:
        assert re.fullmatch(r"unit-\d+-[0-9a-f]{8}\.jsonl", f.name)


@pytest.mark.covers("adapter.never_truncates", subject=SUBJECT)
def test_the_evidence_directory_is_created_when_missing(inner, tmp_path):
    deep = tmp_path / "a" / "b" / "evidence"
    inner.run(inner_test("pass"), evidence=deep)
    assert len(list(deep.glob("*.jsonl"))) == 1


# --- claims ----------------------------------------------------------------------


@pytest.mark.covers("adapter.python")
def test_each_claim_is_its_own_record_with_the_same_outcome(inner):
    inner.run(
        "import pytest\n\n"
        '@pytest.mark.covers("a.one")\n'
        '@pytest.mark.covers("b.two", subject="s.x")\n'
        '@pytest.mark.exempts("c.three", subject="s.y")\n'
        "def test_it():\n    assert False\n"
    )
    recs = inner.records()
    assert len(recs) == 3
    assert {r["outcome"] for r in recs} == {"fail"}
    by = {r.get("covers") or r["exempts"]: r for r in recs}
    assert "exempts" in by["c.three"] and "covers" not in by["c.three"]
    assert by["c.three"]["subject"] == "s.y"
    assert "subject" not in by["a.one"]


@pytest.mark.covers("adapter.python")
def test_class_and_module_marks_apply_to_each_test_inside(inner):
    inner.run(
        "import pytest\n\n"
        'pytestmark = pytest.mark.covers("mod.claim")\n\n'
        '@pytest.mark.covers("cls.claim", subject="s")\n'
        "class TestGroup:\n"
        "    def test_a(self):\n        assert True\n"
        "    def test_b(self):\n        assert True\n"
    )
    seen = sorted((r["test"].split("::")[-1], r["covers"]) for r in inner.records())
    assert seen == [
        ("test_a", "cls.claim"),
        ("test_a", "mod.claim"),
        ("test_b", "cls.claim"),
        ("test_b", "mod.claim"),
    ]


@pytest.mark.covers("adapter.python")
def test_the_same_claim_twice_is_one_record(inner):
    inner.run(
        "import pytest\n\n"
        'pytestmark = pytest.mark.covers("same.claim", subject="s")\n\n'
        '@pytest.mark.covers("same.claim", subject="s")\n'
        "def test_it():\n    assert True\n"
    )
    assert len(inner.records()) == 1


@pytest.mark.covers("adapter.python")
def test_a_scenario_is_recorded_for_parametrized_scenario_runners(inner):
    inner.run(
        "import pytest\nimport temper\n\n"
        '@pytest.mark.parametrize("sid", ["alerts.sold_out", "alerts.low"])\n'
        "def test_scenario(request, sid):\n"
        '    temper.covers(request, "alerts.low_stock", scenario=sid)\n'
        '    temper.covers(request, sid, scenario=sid)\n'
    )
    recs = inner.records()
    assert len(recs) == 4
    assert {(r["covers"], r["scenario"]) for r in recs} == {
        ("alerts.low_stock", "alerts.sold_out"),
        ("alerts.sold_out", "alerts.sold_out"),
        ("alerts.low_stock", "alerts.low"),
        ("alerts.low", "alerts.low"),
    }
    assert list(recs[0]) == ["covers", "scenario", "test", "level", "outcome", "at"]


@pytest.mark.covers("adapter.python")
def test_a_runtime_claim_follows_the_tests_outcome(inner):
    inner.run(
        "import temper\n\n"
        "def test_it(request):\n"
        '    temper.covers(request, "late.claim")\n'
        "    assert False\n"
    )
    (rec,) = inner.records()
    assert (rec["covers"], rec["outcome"]) == ("late.claim", "fail")


@pytest.mark.covers("adapter.python")
def test_exempts_has_a_runtime_form_too(inner):
    inner.run(
        "import temper\n\n"
        "def test_it(request):\n"
        '    temper.exempts(request, "inv.x", subject="s")\n'
    )
    (rec,) = inner.records()
    assert (rec["exempts"], rec["subject"], rec["outcome"]) == ("inv.x", "s", "pass")


MALFORMED = {
    "no reference": "@pytest.mark.covers()",
    "empty reference": '@pytest.mark.covers("")',
    "non-string reference": "@pytest.mark.covers(42)",
    "second positional": '@pytest.mark.covers("a.b", "c")',
    "unknown keyword": '@pytest.mark.covers("a.b", subjcet="s")',
    "non-string subject": '@pytest.mark.covers("a.b", subject=3)',
    "empty subject": '@pytest.mark.covers("a.b", subject="")',
}


@pytest.mark.covers("adapter.python")
@pytest.mark.parametrize("name", sorted(MALFORMED))
def test_a_malformed_mark_stops_the_run_loudly(inner, name):
    result = inner.run(
        "import pytest\n\n" + MALFORMED[name] + "\ndef test_it():\n    assert True\n"
    )
    assert result.ret != 0
    result.stderr.fnmatch_lines(["*test_inner.py::test_it*"])
    assert inner.records() == []


@pytest.mark.covers("adapter.python")
def test_an_unwritable_evidence_directory_stops_the_run_loudly(inner, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    result = inner.run(inner_test("pass"), evidence=blocker / "evidence")
    assert result.ret != 0


@pytest.mark.covers("adapter.python")
def test_parallel_workers_write_separate_whole_lines(inner):
    body = "".join(
        f'@pytest.mark.covers("demo.claim")\ndef test_{i}():\n    assert True\n\n'
        for i in range(40)
    )
    result = inner.run("import pytest\n\n" + body, "-n", "3")
    assert result.ret == 0
    assert len(inner.files()) >= 2
    assert len(inner.records()) == 40
    for line in inner.lines():
        assert line.endswith("\n")
