from jevdbt.stats import StatsSnapshot, format_cost
from jevdbt.ticker import format_ticker_line, ticker_enabled


class FakeStream:
    def __init__(self, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_ticker_disabled_by_default():
    assert ticker_enabled({}, FakeStream(True)) is False


def test_ticker_disabled_without_progress_env_even_on_tty():
    assert ticker_enabled({"JEV_PROGRESS": "0"}, FakeStream(True)) is False


def test_ticker_disabled_on_progress_env_without_tty():
    assert ticker_enabled({"JEV_PROGRESS": "1"}, FakeStream(False)) is False


def test_ticker_disabled_when_stream_has_no_isatty():
    class NoTtyAttr:
        pass

    assert ticker_enabled({"JEV_PROGRESS": "1"}, NoTtyAttr()) is False


def test_ticker_enabled_requires_both_env_and_tty():
    assert ticker_enabled({"JEV_PROGRESS": "1"}, FakeStream(True)) is True


def _snap(**kw) -> StatsSnapshot:
    base = dict(
        judgments=612, unique=500, sent=300, requests=40, input_tokens=200_000, errors=0,
        wall_seconds=0.0,
    )
    base.update(kw)
    return StatsSnapshot(**base)


def test_format_ticker_line_matches_spec_shape():
    line = format_ticker_line(_snap(), elapsed=24.1, frame="⠋")
    assert line == f"  Jev · 612 judgments · 24.1 s · {format_cost(_snap().cost_usd)} ⠋"
    assert line == "  Jev · 612 judgments · 24.1 s · $0.008 ⠋"


def test_format_ticker_line_uses_thousands_separator():
    line = format_ticker_line(_snap(judgments=1234), elapsed=0.0, frame="⠙")
    assert "1,234 judgments" in line
