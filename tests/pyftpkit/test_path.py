# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import pytest

from pyftpkit._paths_resolver.path import Path


def test_parse_has_wildcard():
    parsed = Path.parse("/a/b/*")

    assert parsed.path == "/a/b"
    assert parsed.has_wildcard is True
    assert parsed.has_slash is False


def test_parse_root_wildcard():
    parsed = Path.parse("/*")

    assert parsed.path == "/"
    assert parsed.has_wildcard is True
    assert parsed.has_slash is True


def test_parse_has_slash():
    parsed = Path.parse("/a/b/")

    assert parsed.path == "/a/b"
    assert parsed.has_slash is True
    assert parsed.has_wildcard is False


def test_parse_root_keeps_slash():
    parsed = Path.parse("/")

    assert parsed.path == "/"
    assert parsed.has_slash is True
    assert parsed.has_wildcard is False


def test_parse_root_collapse_from_only_separators():
    parsed = Path.parse("////")

    assert parsed.path == "/"
    assert parsed.has_slash is True
    assert parsed.has_wildcard is False


def test_parse_cache_identity():
    first_parse = Path.parse("/cache")
    second_parse = Path.parse("/cache")

    assert first_parse is second_parse


def test_parse_empty_string():
    parsed = Path.parse("")

    assert parsed.path == "/"
    assert parsed.has_slash is False
    assert parsed.has_wildcard is False


@pytest.mark.parametrize(
    "input_path, expected_path, has_slash, has_wildcard",
    [
        ("a/b", "a/b", False, False),
        ("a/b/", "a/b", True, False),
        ("a/b/*", "a/b", False, True),
        ("/a/*/b", "/a/*/b", False, False),
        ("/a/*/", "/a/*", True, False),
        ("/a///", "/a", True, False),
        ("/a/*", "/a", False, True),
    ],
)
def test_parse_edge_cases(
    input_path,
    expected_path,
    has_slash,
    has_wildcard,
):
    parsed = Path.parse(input_path)

    assert parsed.path == expected_path
    assert parsed.has_slash is has_slash
    assert parsed.has_wildcard is has_wildcard
