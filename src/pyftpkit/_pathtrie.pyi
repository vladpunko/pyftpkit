# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-05

import typing

__all__: list[str] = [
    "PathTrieIterator",
    "PathTrieIteratorPreOrder",
    "PathTrieIteratorPostOrder",
    "PathTrie",
]

class PathTrieIterator:
    def __iter__(self) -> "PathTrieIterator":
        """Returns self as an iterator."""
        ...

    def __next__(self) -> str:
        """Returns the next unique path string."""
        ...

class PathTrieIteratorPreOrder(PathTrieIterator):
    def __iter__(self) -> "PathTrieIteratorPreOrder":
        """Returns self as an iterator."""
        ...

class PathTrieIteratorPostOrder(PathTrieIterator):
    def __iter__(self) -> "PathTrieIteratorPostOrder":
        """Returns self as an iterator."""
        ...

    def __next__(self) -> str:
        """Returns the next unique path string in post-order."""
        ...

class PathTrie:
    def __iter__(self) -> typing.Iterator[str]:
        """Returns an iterator over all unique paths.

        Do not mutate the trie while iterating."""
        ...

    def __reversed__(self) -> typing.Iterator[str]:
        """Returns an iterator over all unique paths in post-order.

        Do not mutate the trie while iterating."""
        ...

    def clear(self) -> None:
        """Clears the entire trie."""
        ...

    def insert(self, path: str) -> None:
        """Inserts a single path into a trie."""
        ...

    def get_all_unique_paths(self) -> typing.List[str]:
        """Returns all unique paths as a list of strings."""
        ...
