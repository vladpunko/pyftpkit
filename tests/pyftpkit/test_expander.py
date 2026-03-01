# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import os
import pathlib

import pytest

from pyftpkit._paths_resolver.expander import (
    LocalTreeExpander,
    RemoteFTPExpander,
)
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.ftpfs import FTPEntryType


async def _drain_async_for(generator):
    items = []
    async for item in generator:
        items.append(item)

    return items


@pytest.fixture
def connection_parameters(ftp_server, username, password):
    return ConnectionParameters.model_validate(
        {
            "host": ftp_server.host,
            "port": ftp_server.port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 1,
            "max_workers": 2,
        }
    )


@pytest.mark.asyncio
async def test_local_tree_expander_is_file(fs_no_root):
    src = pathlib.Path("/a.txt")
    src.write_text("")
    dst = "/b.txt"

    expander = LocalTreeExpander()

    assert await _drain_async_for(expander.expand(str(src), dst)) == [(str(src), dst)]


@pytest.mark.asyncio
async def test_local_tree_expander_directory_skips_symlinks(fs_no_root):
    src = pathlib.Path("/root")
    src.mkdir()
    (src / "subdir").mkdir()

    a_path = src / "a.txt"
    a_path.write_text("")
    b_path = src / "subdir" / "b.txt"
    b_path.write_text("")

    (src / "symlink.txt").symlink_to(a_path)

    expander = LocalTreeExpander()

    dst = "/dst"
    pairs = await _drain_async_for(expander.expand(str(src), dst))

    expected = {
        (str(a_path), os.path.join(dst, "a.txt")),
        (str(b_path), os.path.join(dst, "subdir", "b.txt")),
    }
    assert set(pairs) == expected


@pytest.mark.asyncio
async def test_remote_expander_file_short_circuit(
    fs_no_root, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _listdir(self, path):
        yield (FTPEntryType.FILE, "/a.txt")
        yield (FTPEntryType.FILE, "/b.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir",
        new=_listdir,
    )
    walk_mock = mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk")

    pairs = await _drain_async_for(expander.expand("/a.txt", "/dst.txt"))

    assert pairs == [("/a.txt", "/dst.txt")]
    walk_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remote_expander_directory_walk(
    fs_no_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    src_dir = home / "data"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("")
    (src_dir / "subdir").mkdir()
    (src_dir / "subdir" / "b.txt").write_text("")

    expander = RemoteFTPExpander(connection_parameters)

    pairs = await _drain_async_for(expander.expand(str(root / "data"), "/dst"))

    expected = {
        (str(root / "data" / "a.txt"), os.path.join("/dst", "a.txt")),
        (
            str(root / "data" / "subdir" / "b.txt"),
            os.path.join("/dst", "subdir", "b.txt"),
        ),
    }
    assert set(pairs) == expected


@pytest.mark.asyncio
async def test_remote_expander_root(fs_no_root, ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    (home / "root.txt").write_text("")

    expander = RemoteFTPExpander(connection_parameters)

    pairs = await _drain_async_for(expander.expand(str(root), "/dst"))

    assert (str(root / "root.txt"), os.path.join("/dst", "root.txt")) in set(pairs)


@pytest.mark.asyncio
async def test_remote_expander_skips_listdir_when_no_name(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    mocker.patch(
        "pyftpkit._paths_resolver.expander.posixpath.basename", return_value=""
    )

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    listdir_mock = mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir"
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    pairs = await _drain_async_for(expander.expand("/data", "/dst"))

    assert pairs == [("/data/file.txt", os.path.join("/dst", "file.txt"))]
    listdir_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remote_expander_listdir_target_is_directory(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.DIRECTORY, "/data")

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_listdir
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    pairs = await _drain_async_for(expander.expand("/data", "/dst"))

    assert pairs == [("/data/file.txt", os.path.join("/dst", "file.txt"))]


@pytest.mark.asyncio
async def test_remote_expander_listdir_skips_non_matching_entries(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.FILE, "/other")

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_listdir
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    pairs = await _drain_async_for(expander.expand("/data", "/dst"))

    assert pairs == [("/data/file.txt", os.path.join("/dst", "file.txt"))]
