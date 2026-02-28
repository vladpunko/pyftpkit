# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-26

import gc
import posixpath
import tracemalloc

import pytest

from pyftpkit._pathtrie import PathTrie


@pytest.mark.parametrize(
    "paths, expected_paths",
    [
        (["../a/b"], ["a", "a/b"]),
        ([".", "..", ""], []),
        (["./a/b"], ["a", "a/b"]),
        ([""], []),
        (["/../"], ["/"]),
        (["/./"], ["/"]),
        (["/.1/2/3"], ["/", "/.1", "/.1/2", "/.1/2/3"]),
        (["/"], ["/"]),
        (["//a///b//c/"], ["/", "/a", "/a/b", "/a/b/c"]),
        (["/😊/файл"], ["/", "/😊", "/😊/файл"]),
        (["/1/2"], ["/", "/1", "/1/2"]),
        (["/1/2/"], ["/", "/1", "/1/2"]),
        (["/a", "/a/b"], ["/", "/a", "/a/b"]),
        (["/a/./b"], ["/", "/a", "/a/b"]),
        (["/a/b", "/c"], ["/", "/a", "/a/b", "/c"]),
        (["/а/б/в"], ["/", "/а", "/а/б", "/а/б/в"]),
        (["/漢字/テスト"], ["/", "/漢字", "/漢字/テスト"]),
        (["a//b"], ["a", "a/b"]),
        (["a/b/"], ["a", "a/b"]),
        (["a/b/c"], ["a", "a/b", "a/b/c"]),
    ],
)
def test_insert(paths, expected_paths):
    trie = PathTrie()
    for path in paths:
        trie.insert(path)

    for path, expected_path in zip(trie, expected_paths, strict=True):
        assert path == expected_path


def test_iter_deterministic_order():
    trie = PathTrie()
    trie.insert("/b/2")
    trie.insert("/a/1")
    trie.insert("/c")

    assert list(trie) == ["/", "/a", "/a/1", "/b", "/b/2", "/c"]


def test_get_all_unique_paths_deterministic_order():
    trie = PathTrie()
    trie.insert("/b/2")
    trie.insert("/a/1")
    trie.insert("/c")

    assert trie.get_all_unique_paths() == ["/", "/a", "/a/1", "/b", "/b/2", "/c"]


def test_relative_and_absolute_paths_are_separate():
    trie = PathTrie()
    trie.insert("a/b")
    trie.insert("/a/b")

    assert list(trie) == ["/", "/a", "/a/b", "a", "a/b"]


def test_duplicate_paths_are_ignored():
    trie = PathTrie()
    trie.insert("/a/b")
    trie.insert("/a")
    trie.insert("/a/b")
    trie.insert("/a/b")

    assert list(trie) == ["/", "/a", "/a/b"]


def test_long_paths_do_not_leak_memory():
    tracemalloc.start()
    baseline_snapshot = tracemalloc.take_snapshot()

    for cycle in range(3):
        trie = PathTrie()
        for index in range(500_000):
            path = posixpath.join(
                "/",
                "start" * 20,
                "{0:02d}-{1:04d}".format(cycle, index),
                "end" * 20,
            )
            trie.insert(path)

        trie.get_all_unique_paths()
        trie.clear()
        gc.collect()

    current_snapshot = tracemalloc.take_snapshot()

    memory_difference = current_snapshot.compare_to(
        baseline_snapshot, key_type="lineno"
    )
    tracemalloc.stop()

    total_growth = sum(stat.size_diff for stat in memory_difference)
    assert total_growth < 5 * 1024 * 1024  # 5MB


def test_clear():
    trie = PathTrie()
    trie.insert("/1/2")
    trie.insert("/1/3")
    trie.insert("/1/4")
    assert trie.get_all_unique_paths()

    trie.clear()
    assert not trie.get_all_unique_paths()


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
