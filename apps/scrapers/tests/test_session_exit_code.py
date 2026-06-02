"""Tests for the session-level exit-code signal (observability for blocked runs).

A scraper that gets DataDome-403'd / bot-walled exits cleanly with 0 items. Before
EXIT_SCRAPED_NOTHING the process returned 0, so a fully-blocked portal showed up as
a green step and only the global smoke test caught it. These tests pin the contract:
0 items found -> non-zero exit, any items found -> 0.
"""

from __future__ import annotations

import asyncio

import pytest

from scrapers.base import (
    EXIT_SCRAPED_NOTHING,
    ScrapeResult,
    fetch_with_retry,
    session_exit_code,
)


class _StubLogger:
    """Stand-in for the structlog logger the scrapers pass: swallows kwargs."""

    def info(self, *args, **kwargs):  # noqa: D102
        pass

    def warning(self, *args, **kwargs):  # noqa: D102
        pass

    def error(self, *args, **kwargs):  # noqa: D102
        pass


_log = _StubLogger()


def test_zero_found_returns_nonzero_exit():
    assert session_exit_code(ScrapeResult(items_found=0), logger=_log) == EXIT_SCRAPED_NOTHING


def test_zero_found_with_errors_still_nonzero():
    # A 403 challenge bumps errors but leaves found at 0 — must surface as failure.
    result = ScrapeResult(items_found=0, errors=2)
    assert session_exit_code(result, logger=_log) == EXIT_SCRAPED_NOTHING


def test_some_found_returns_zero_exit():
    result = ScrapeResult(items_found=5, items_created=3, items_updated=2)
    assert session_exit_code(result, logger=_log) == 0


def test_merge_accumulates_all_counters():
    total = ScrapeResult()
    total.merge(ScrapeResult(items_found=4, items_created=4, errors=1))
    total.merge(ScrapeResult(items_found=3, items_updated=3))
    assert total.items_found == 7
    assert total.items_created == 4
    assert total.items_updated == 3
    assert total.errors == 1


# --- fetch_with_retry (T6: sobrevivir fallos transitorios sin abortar la zona) ---


def test_fetch_with_retry_succeeds_after_transient_failures():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("transient")
        return "ok"

    result = asyncio.run(fetch_with_retry(flaky, attempts=3, base_delay=0, logger=_log))
    assert result == "ok"
    assert calls["n"] == 3  # 2 fallos + 1 éxito


def test_fetch_with_retry_reraises_after_exhausting_attempts():
    calls = {"n": 0}

    async def always_fail():
        calls["n"] += 1
        raise TimeoutError("nope")

    with pytest.raises(TimeoutError):
        asyncio.run(fetch_with_retry(always_fail, attempts=2, base_delay=0, logger=_log))
    assert calls["n"] == 2  # no reintenta de más
