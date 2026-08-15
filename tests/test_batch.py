"""Tests for the shared chunked-apply helper in protonmail_organizer.batch."""

from __future__ import annotations

import pytest

from protonmail_organizer import batch
from protonmail_organizer.constants import BATCH_SIZE


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch):
    monkeypatch.setattr(batch, "BATCH_DELAY_SECONDS", 0)


class TestBatchApply:
    def test_chunks_by_batch_size(self):
        calls = []
        ids = [str(i) for i in range(BATCH_SIZE * 2 + 1)]

        failed = batch.batch_apply(calls.append, ids, "Testing", progress=False)

        assert failed == 0
        assert [len(c) for c in calls] == [BATCH_SIZE, BATCH_SIZE, 1]
        assert [x for c in calls for x in c] == ids

    def test_failed_batch_is_counted_not_fatal(self):
        calls = []

        def flaky(chunk):
            calls.append(chunk)
            if len(calls) == 1:
                raise Exception("API 500")

        ids = [str(i) for i in range(BATCH_SIZE + 3)]
        failed = batch.batch_apply(flaky, ids, "Testing", progress=False)

        assert len(calls) == 2
        assert failed == BATCH_SIZE

    def test_empty_ids_is_noop(self):
        failed = batch.batch_apply(
            lambda c: (_ for _ in ()).throw(AssertionError("must not be called")),
            [],
            "Testing",
        )
        assert failed == 0
