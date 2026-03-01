# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

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


def test_parse_cache_identity():
    a = Path.parse("/cache")
    b = Path.parse("/cache")

    assert a is b
