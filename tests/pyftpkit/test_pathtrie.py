# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pytest

from pyftpkit._pathtrie import PathTrie


@pytest.mark.parametrize(
    "paths, expected_paths",
    [
        (["../a/b"], ["a", "a/b"]),
        (["./a/b"], ["a", "a/b"]),
        ([""], []),
        (["/.1/2/3"], ["/", "/.1", "/.1/2", "/.1/2/3"]),
        (["/"], ["/"]),
        (["//a///b//c/"], ["/", "/a", "/a/b", "/a/b/c"]),
        (["/😊/файл"], ["/", "/😊", "/😊/файл"]),
        (["/1/2"], ["/", "/1", "/1/2"]),
        (["/1/2/"], ["/", "/1", "/1/2"]),
        (["/a", "/a/b"], ["/", "/a", "/a/b"]),
        (["/a/./b"], ["/", "/a", "/a/b"]),
        (["/a/b", "/c"], ["/", "/c", "/a", "/a/b"]),
        (["/а/б/в"], ["/", "/а", "/а/б", "/а/б/в"]),
        (["/漢字/テスト"], ["/", "/漢字", "/漢字/テスト"]),
    ],
)
def test_insert(paths, expected_paths):
    trie = PathTrie()
    for path in paths:
        trie.insert(path)

    for path, expected_path in zip(trie, expected_paths, strict=True):
        assert path == expected_path


def test_clear():
    trie = PathTrie()
    trie.insert("/1/2")
    trie.insert("/1/3")
    trie.insert("/1/4")
    assert len(list(trie)) > 0

    trie.clear()
    assert len(list(trie)) == 0


def test_get_all_unique_paths():
    trie = PathTrie()
    trie.insert("/1/2")
    trie.insert("/2/3")

    assert set(trie.get_all_unique_paths()) == {
        "/",
        "/2",
        "/2/3",
        "/1",
        "/1/2",
    }
