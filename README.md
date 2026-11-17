# temper-python

The [Temper by Turbolytics](https://github.com/turbolytics/temper) adapter for
pytest. A test states what it proves; the adapter records how it ended;
`temper matrix` turns those records into a matrix of what is proven and what
is not.

Website: <https://turbolytics.github.io/temper/>, with a
[tutorial](https://turbolytics.github.io/temper/tutorial/) on designing with
Temper.

## Getting started

You need the `temper` CLI ([install](https://github.com/turbolytics/temper#install))
and a project with `temper.yml` and a `temper/` directory of declarations.
`temper guide` explains both.

**1. Install the adapter.**

```sh
pip install temper-python
```

It is a pytest plugin: nothing to import or enable.

**2. Mark each test with what it proves.**

```python
import pytest

@pytest.mark.covers("store.reserve.never_negative", subject="store.file")
def test_reserve_never_goes_negative(): ...

@pytest.mark.exempts("store.persists_across_restart", subject="store.memory")
def test_memory_store_forgets_on_restart(): ...
```

**3. Run the tests through `temper run`, then build the matrix.**

```sh
temper clean
temper run --level unit -- pytest
temper matrix --all-levels
```

That is the whole integration. Plain `pytest` behaves exactly as before: without
the variables `temper run` sets, the plugin records nothing.

## What a test can say

| Mark | Meaning |
|---|---|
| `@pytest.mark.covers(ref)` | The test proves a feature or lattice member (`lattice/key`). |
| `@pytest.mark.covers(ref, subject=id)` | The test proves an invariant or lattice member for that subject. |
| `@pytest.mark.exempts(ref, subject=id)` | The test proves the subject is excused. Use it only in the test a declaration names in `proven_by`. |
| `scenario=id` (on either) | The claim came from that declared scenario. |

Marks on a class or a module apply to every test inside. A test may carry many
marks; each is one record with the same outcome.

A scenario runner that parametrizes one test over many scenarios claims from
inside the test, where the scenario is known:

```python
import temper

@pytest.mark.parametrize("sid", SCENARIOS)
def test_scenario(request, sid):
    temper.covers(request, "alerts.low_stock", scenario=sid)
    temper.covers(request, sid, scenario=sid)
    ...
```

`temper.exempts(request, ref, subject=...)` is the same for exemptions.

There is no way to set a level. The runner does (`temper run --level`), and a
test that changes `TEMPER_LEVEL` in its own environment changes nothing: the
environment is read once, when pytest starts.

A malformed mark (no reference, a stray keyword such as `level=`, a non-string)
stops the run with a message naming the test, when the runner is active.

## How outcomes are recorded

A record is written once the test is final, after fixtures have torn down.

| Outcome | When |
|---|---|
| `pass` | The test, its setup and its teardown all passed. The only outcome that counts. |
| `fail` | An assertion failed, `pytest.fail` was called, or the test was `xfail` (whether it failed or passed). |
| `skip` | The test was skipped, in any phase. |
| `error` | An exception other than a failed assertion, or any failure in setup or teardown. |

A test that fails and then skips records `fail`. Evidence goes to one new file
per process, `<level>-<pid>-<8 hex>.jsonl`, opened for append, one write per
line. Existing evidence is never truncated, so `pytest-xdist` works without
configuration. The contract every adapter follows is
[docs/adapters.md](https://github.com/turbolytics/temper/blob/main/docs/adapters.md).

Not verified: retry plugins such as `pytest-rerunfailures`.

## Development

```sh
python -m venv .venv && .venv/bin/pip install -e '.[dev]'
make matrix        # clean, run the tests through temper, rebuild MATRIX.md
make check-matrix  # fail if the committed matrix is stale
```

This project is declared with Temper in `temper/`, and its own tests prove the
adapter claims with the adapter: see [MATRIX.md](MATRIX.md).

## Releasing

Set `version` in `pyproject.toml`, merge, then push the matching tag:

```sh
git tag v0.1.0 && git push origin v0.1.0
```

The release workflow checks the tag matches the version, runs the tests, builds,
and publishes to PyPI through trusted publishing.
