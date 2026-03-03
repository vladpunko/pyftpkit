# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import dataclasses
import functools
import io
import posixpath

__all__ = ["Path"]


@dataclasses.dataclass(frozen=True, slots=True)
class Path:
    """Immutable path descriptor."""

    path: str
    has_slash: bool
    has_wildcard: bool

    @classmethod
    @functools.lru_cache(maxsize=io.DEFAULT_BUFFER_SIZE)
    def parse(cls: type["Path"], path: str) -> "Path":
        """Converts an unprocessed path string into a parsed path instance."""
        has_wildcard = path.endswith("/*")
        if has_wildcard:
            path = path[:-2]
            if not path:
                path = posixpath.sep

        has_slash = path.endswith("/")

        # Keep root as "/" instead of empty.
        if path != posixpath.sep:
            path = path.rstrip(posixpath.sep)
            if not path:
                path = posixpath.sep

        return cls(
            path=path,
            has_slash=has_slash,
            has_wildcard=has_wildcard,
        )
