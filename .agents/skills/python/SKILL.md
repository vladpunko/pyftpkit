---
name: python
description: Develop or refactor the codebase.
compatibility: universal
---

# Python

## Overview
Use this skill for Python changes for `pyftpkit` package.
Prioritize correctness for FTP path semantics, logging, and error handling.
Optimize for speed when it does not compromise correctness.

## Agent Interface
- Display name: Python
- Short description: Python develop and refactor guide
- Default prompt: Use for `pyftpkit` Python changes. Follow conventions, keep correctness first, optimize for speed when safe, and run `make tests` if asked.

## Workflow
1. Identify the target module under `src/pyftpkit/` and related tests.
2. Keep error and logger messages unchanged. Tests assert exact text.
3. Update the `.pyi` stub when public APIs change.
4. Use `posixpath` for remote FTP paths. Keep validation consistent with helpers.
5. Run `black`, then `isort` on touched files.
6. Use `make tests` for test runs when requested.

## Conventions
- Use Python best practices and project patterns, favoring clarity, correctness, and maintainability over cleverness.
- Keep messages and exception types aligned with existing patterns.
- Use `logger = logging.getLogger("pyftpkit")` and log before exceptions.
- For logs and exception messages, prefer `%r` (or `!r` when formatting strings) for string values. Use `%s` only for type names.
- Don't catch or raise generic exceptions (`Exception`, `BaseException`). Use the most specific types available.
- Normalize paths early by coercing `os.PathLike` with `os.fspath`, rejecting `bytes`, and validating emptiness or whitespace before deeper logic.
- Remote path validation: string-like, non-empty, absolute (`/`), no `.` or `..` segments, and no `\\`.
- Use `posixpath.curdir` and `posixpath.pardir` when checking traversal segments.
- Raise `FTPPathNotAbsoluteError` for non-absolute paths with `"Ambiguous ... path: {path!r}"` wording.
- Assume FTP servers use POSIX paths. Windows paths are not supported.
- Use `os.path` for local filesystem paths and `posixpath` for remote FTP paths. Avoid `pathlib` for remote paths, but accept `os.PathLike` via `os.fspath`.
- For FTP operations, catch `ftplib.all_errors`, log with `logger.exception`, and wrap in `FTPError` instead of propagating raw FTP errors.
- Use `asyncio.get_running_loop` and `run_in_executor` for blocking FTP calls.
- Functions must handle exceptions and ensure clean shutdown on `Ctrl+C` or errors.
- Prevent hangs by giving loops and waits clear exit conditions.
- Use `asyncio.wait_for` around potentially blocking async operations, such as pool initialization, queue drains, and output reads, to prevent hangs.
- With `asyncio.gather(..., return_exceptions=True)`, close successfully created resources before raising the first error.
- Avoid `yield` statements inside `finally` blocks to prevent generator shutdown hazards.
- Guard pool, queue, and worker sizes with `max(1, ...)` when sizing executors and queues.
- Reduce FTP control and data churn with reuse, throttling, and bounded concurrency to avoid `TIME_WAIT` and ephemeral port exhaustion.
- Prefer Python 3.10+ features and pragmatic techniques for performance, and favor speed only when correctness is preserved.
- Prefer memory-efficient approaches and avoid heavy allocations when possible.
- Cache pure parsing helpers with `functools.lru_cache` using a bounded size.
- Use `typing.Final` for module constants and numeric separators for large ints.
- Pydantic models should use `Field` metadata with constraints and descriptions.
- Prefer `@dataclasses.dataclass(..., slots=True)` and use `frozen=True` for immutable data holders.
- Add a stub `yield` after `raise NotImplementedError` in async abstract generators to satisfy mypy.
- Place private helpers (e.g., `_func`) near the functions that use them to make review and reading easier.
- Don't alias attributes locally (e.g., `var = self.obj.var`). Use direct access for faster attribute loads.
- Don't use `global` or `nonlocal`. Only use nested functions in rare cases.
- Deliver architecture-level solutions with clear tradeoffs and assumptions.
- Keep a peer-to-peer tone and assume deep experience.

## Async Producer and Consumer Patterns
- Use `max_queues_size` to size bounded output queues for backpressure.
- Cap outstanding work with a semaphore and pair bounded queues with bounded worker concurrency to prevent memory spikes.
- Use separate queues for work scheduling, discovery reporting, and outputs to prevent deadlocks at low queue sizes.
- Ensure producers stop on the first fatal error signal to prevent backlog.
- Send the first worker error via a `Future` and optionally forward a best-effort exception to the output queue for deterministic consumer exit.
- Track completion with counters or events instead of `queue.empty()`.
- Pair `queue.get()` with `task_done()` in `finally` blocks.
- Use short timeouts in the consumer loop to poll stop and error flags and avoid indefinite `get()` blocking.
- Use `asyncio.wait_for` around queue drains or shutdown steps to avoid hangs.
- On abort or cancel, set a stop signal, cancel workers, and drain queues in `finally` blocks, releasing semaphore slots for unprocessed items.
- Shield resource cleanup (e.g., pool releases) from cancellation signals.

## Code Style and Formatting
- Respect `.editorconfig`: 4-space indent, LF, trim trailing whitespace, final newline.
- Keep line length to 88 for `.py` and 130 for `.pyi`.
- Always run `black` and `isort` (profile: `black`) on touched files.
- Group imports as stdlib, third-party, then local, and keep them sorted.
- Prefer absolute imports over relative imports.
- Use module-qualified types with `import typing` and `import collections.abc`, not `from typing import ...`.
- Type-annotate all defs and prefer PEP 604 unions (`str | os.PathLike`) and builtin generics (`list[str]`).
- Exposed public API modules should define `__all__` near the top.
- Use NumPy-style docstrings and `name : type` entries for `Parameters`, `Returns`, `Yields`, `Raises`, and `Notes`.
- Use lazy `%`-style logger formatting, avoid f-strings, and prefer `%r` for values (`%s` only for type names).
- End messages with a period for f-strings and `%`-style formatting unless the last token is `%r` or `!r`. Then use `"...: %r"` or `"...: {0!r}"` or `"...: {var!r}"`.
