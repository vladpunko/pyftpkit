# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pytest

from pyftpkit._pathtrie import PathTrie


@pytest.mark.parametrize(
    "paths, expected_paths",
    [
        (["/"], ["/"]),
        (["/1/2"], ["/", "/1", "/1/2"]),
        (["/1/2/"], ["/", "/1", "/1/2"]),
        ([""], []),
        (["//a///b//c/"], ["/", "/a", "/a/b", "/a/b/c"]),
        (["/a/b", "/c"], ["/", "/c", "/a", "/a/b"]),
        (["/a", "/a/b"], ["/", "/a", "/a/b"]),
        (["/a/./b"], ["/", "/a", "/a/b"]),
        (["./a/b"], ["a", "a/b"]),
        (["/.1/2/3"], ["/", "/.1", "/.1/2", "/.1/2/3"]),
        (["../a/b"], ["/", "/a", "/a/b"]),
    ],
)
def test_insert(paths, expected_paths):
    trie = PathTrie()
    for path in paths:
        trie.insert(path)

    for path, expected_path in zip(trie, expected_paths):
        assert path == expected_path


def test_clear():
    trie = PathTrie()
    trie.insert("/1/2")
    trie.insert("/1/3")
    trie.insert("/1/4")
    assert list(trie) == ["/", "/1", "/1/4", "/1/3", "/1/2"]

    trie.clear()
    assert list(trie) == []


def test_get_all_unique_paths():
    trie = PathTrie()
    trie.insert("/1/2")
    trie.insert("/2/3")

    assert trie.get_all_unique_paths() == [
        "/",
        "/2",
        "/2/3",
        "/1",
        "/1/2",
    ]
