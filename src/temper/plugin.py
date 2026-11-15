"""The pytest plugin: reads what each test claims, records how it ended.

The level and the evidence directory come from ``TEMPER_LEVEL`` and
``TEMPER_EVIDENCE``, read once when pytest starts. Without both, the plugin
does nothing.
"""

import os
from datetime import datetime, timezone

import pytest

from ._evidence import Writer

CLAIM_KINDS = ("covers", "exempts")
_KEYWORDS = ("subject", "scenario")

_CLAIMS = pytest.StashKey()  # runtime claims made through temper.covers / temper.exempts
_OUTCOMES = pytest.StashKey()  # one outcome per phase report
_STATE = pytest.StashKey()

_PRECEDENCE = ("error", "fail", "skip", "pass")  # first one present wins


class _State:
    def __init__(self, level, directory, run):
        self.level = level
        self.run = run
        self.writer = Writer(directory, level)


def _claim(kind, args, kwargs, where):
    """Validate one claim and return (kind, ref, subject, scenario)."""
    if len(args) != 1 or not isinstance(args[0], str) or not args[0]:
        raise ValueError(f"{where}: {kind} takes one non-empty reference, as a string")
    for key in kwargs:
        if key not in _KEYWORDS:
            hint = " (the level comes from the runner, never the test)" if key == "level" else ""
            raise ValueError(f"{where}: {kind} has no keyword {key!r}{hint}; use subject or scenario")
    for key in _KEYWORDS:
        value = kwargs.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            raise ValueError(f"{where}: {kind} {key} must be a non-empty string")
    return kind, args[0], kwargs.get("subject"), kwargs.get("scenario")


def add_claim(request, kind, ref, subject=None, scenario=None):
    """Claim from inside a test; the claim follows the test's outcome."""
    node = getattr(request, "node", None)
    if not isinstance(node, pytest.Item):
        raise TypeError(f"temper.{kind} needs the `request` fixture of a test")
    kwargs = {k: v for k, v in (("subject", subject), ("scenario", scenario)) if v is not None}
    claim = _claim(kind, (ref,), kwargs, node.nodeid)
    node.stash.setdefault(_CLAIMS, []).append(claim)


def _claims(item):
    seen, out = set(), []
    marked = [_claim(m.name, m.args, m.kwargs, item.nodeid) for m in item.iter_markers() if m.name in CLAIM_KINDS]
    for claim in marked + item.stash.get(_CLAIMS, []):
        if claim not in seen:
            seen.add(claim)
            out.append(claim)
    return out


def pytest_configure(config):
    config.addinivalue_line("markers", "covers(ref, subject=None, scenario=None): the test proves this Temper claim")
    config.addinivalue_line("markers", "exempts(ref, subject=None, scenario=None): the test proves this exemption")
    level = os.environ.get("TEMPER_LEVEL", "")
    directory = os.environ.get("TEMPER_EVIDENCE", "")
    if not level or not directory:
        return
    state = _State(level, directory, os.environ.get("TEMPER_RUN", ""))
    try:
        state.writer.ensure_directory()
    except OSError as err:
        raise pytest.UsageError(f"temper: cannot write evidence to TEMPER_EVIDENCE={directory!r}: {err}")
    config.stash[_STATE] = state


def pytest_unconfigure(config):
    state = config.stash.get(_STATE, None)
    if state is not None:
        state.writer.close()


def pytest_collection_modifyitems(config, items):
    if config.stash.get(_STATE, None) is None:
        return
    for item in items:
        try:
            _claims(item)
        except ValueError as err:
            raise pytest.UsageError(f"temper: {err}")


def _outcome(report, call):
    if hasattr(report, "wasxfail"):
        return "fail"  # an expected failure never proves anything, whichever way it went
    if report.skipped:
        return "skip"
    if report.passed:
        return "pass"
    if report.when != "call":
        return "error"  # setup or teardown broke
    excinfo = call.excinfo
    if excinfo is None or isinstance(excinfo.value, (AssertionError, pytest.fail.Exception)):
        return "fail"
    return "error"


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    if item.config.stash.get(_STATE, None) is None:
        return
    item.stash.setdefault(_OUTCOMES, []).append(_outcome(outcome.get_result(), call))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    yield
    state = item.config.stash.get(_STATE, None)
    outcomes = item.stash.get(_OUTCOMES, None)
    if state is None or not outcomes:
        return
    final = next(o for o in _PRECEDENCE if o in outcomes)
    at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for kind, ref, subject, scenario in _claims(item):
        record = {kind: ref}
        if subject:
            record["subject"] = subject
        if scenario:
            record["scenario"] = scenario
        record.update(test=item.nodeid, level=state.level, outcome=final)
        if state.run:
            record["run"] = state.run
        record["at"] = at
        state.writer.write(record)
