# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import typing

class PathTrieIterator:
    def __iter__(self) -> "PathTrieIterator":
        """Returns self as an iterator."""
        ...

    def __next__(self) -> str:
        """Returns the next unique path string."""
        ...


class PathTrie:
    def __iter__(self) -> typing.Iterator[str]:
        """Returns all unique paths as a generator of strings."""
        ...

    def clear(self) -> None:
        """Clears the entire trie."""
        ...

    def insert(self, path: str) -> None:
        """Inserts a single path into a trie."""
        ...
