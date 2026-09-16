"""Chunked application of bulk API calls, shared by cleanup, rules, and undo."""

from __future__ import annotations

import contextlib
import time

from .constants import BATCH_DELAY_SECONDS, BATCH_SIZE
from .display import print_error, progress_context


def batch_apply(func, ids: list, description: str, progress: bool = True) -> int:
    """Apply ``func`` to ``ids`` in BATCH_SIZE chunks, pausing between chunks.

    A failed chunk is reported and skipped rather than aborting the rest, so
    callers can still record what was applied. Returns the number of ids in
    failed chunks (0 means everything was applied).
    """
    failed = 0
    ctx = progress_context() if progress else contextlib.nullcontext()
    with ctx as prog:
        task = prog.add_task(f"{description}...", total=len(ids)) if prog else None
        for i in range(0, len(ids), BATCH_SIZE):
            chunk = ids[i : i + BATCH_SIZE]
            try:
                func(chunk)
            except Exception as e:
                failed += len(chunk)
                print_error(f"Batch failed ({description}): {e}")
            if prog:
                prog.update(task, advance=len(chunk))
            if i + BATCH_SIZE < len(ids):
                time.sleep(BATCH_DELAY_SECONDS)
    return failed
