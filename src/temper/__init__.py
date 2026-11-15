"""Temper adapter for pytest.

Mark a test with what it proves::

    @pytest.mark.covers("store.reserve.never_negative", subject="store.file")
    def test_reserve(): ...

or claim from inside it, which is how a parametrized scenario runner names its
scenario::

    temper.covers(request, "alerts.low_stock", scenario="alerts.sold_out")
"""

from .plugin import add_claim

__all__ = ["covers", "exempts"]


def covers(request, ref, *, subject=None, scenario=None):
    """The running test proves ``ref`` (for ``subject``, when it applies per subject)."""
    add_claim(request, "covers", ref, subject, scenario)


def exempts(request, ref, *, subject=None, scenario=None):
    """The running test proves ``subject`` is excused from ``ref``."""
    add_claim(request, "exempts", ref, subject, scenario)
