---
name: python-tests-authoring
description: Write, rename, or update pytest tests for the codebase.
compatibility: universal
---

# Python Tests Authoring

## Overview
Create and maintain pytest coverage for **pyftpkit**, following project conventions for test naming, logging assertions, and error messages.
When active, work **only within the `tests/` directory**. Do **not modify application or source code** outside the test suite.

## Agent Interface
- Display name: Python Tests Authoring
- Short description: Python pytest test authoring guide
- Default prompt: Use this skill when creating, renaming, or updating `pyftpkit` tests. Follow project-specific conventions for naming, caplog usage, mock naming, and error messages, and run `make tests` when requested.

## Workflow
1. Inspect the implementation paths in `src/pyftpkit` that the tests should cover.
2. Enumerate branches and error paths, then design tests for each branch.
3. Apply project conventions (naming, caplog, mocks, error messages).
4. Run `black` and `isort` on the `tests/` folder after writing or updating tests.
5. Run `make tests` when requested and fix any failures.

## Conventions
- Structure tests using AAA (Arrange, Act, Assert).
- Use descriptive test names with no abbreviations.
- Use clear, descriptive exception messages in tests (avoid "boom", "error", etc.).
- Keep tests easy to understand and human-readable: use clear variable names and avoid abbreviations.
- Follow all Python best practices in test code.
- Keep lines within 88 characters.
- For exceptions, assert both the raised error message and the logged message via `caplog`.
- When asserting `caplog` messages, assign `message = "..."` and put the `assert` on the next line (no blank line between them).
- Treat each `message` + `assert message` pair as a block.
- Separate each message block from the code above and below with a blank line.
- For formatted messages, store the original format string in `message`, then call `.format(...)` when constructing the expected value.
- Pattern example:
```python
message = "Unsupported value: {0!r}".format(value)
assert expected in str(error.value)
```
or
```python
message = "Unsupported value: {0!r}"
message.format(value)
assert expected in str(error.value)
```
- Keep tests free of typing annotations.
- All mock variables must end with `_mock`.
- Prefer `tmp_path` when a test needs a temporary directory.
- Use `pathlib` for path construction and manipulation.
- When calling `write_text` or `read_text`, always pass `encoding="utf-8"`.

## Patterns
- Use `@pytest.mark.asyncio` for async tests.
- Use helper async iterator drainers when testing async generators.
- Align expected strings with actual logger messages in source code.
- If a test exercises FTP operations, consider using the `ftp_server` fixture.
- If a test exercises filesystem operations, consider using the `filesystem_without_root` fixture.

## Quality Checks
- Keep tests deterministic and minimal: avoid unnecessary filesystem work.
- When a test expects logging, assert the exact message substring in `caplog.text`.
- When a test should not log, assert `caplog.text == ""`.
