# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import logging
import pathlib
import posixpath

import pytest

from pyftpkit._paths_resolver.expander import (
    LocalTreeExpander,
    RemoteFTPExpander,
)
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import (
    FTPPathError,
    FTPPathNotAbsoluteError,
)
from pyftpkit.ftpfs import FTPEntryType


async def _drain_async_iterator(generator):
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
async def test_local_tree_expander_is_file(fs_without_root):
    source_path = pathlib.Path("/a.txt")
    source_path.write_text("")
    destination_path = "/b.txt"

    expander = LocalTreeExpander()

    assert await _drain_async_iterator(
        expander.expand(str(source_path), destination_path)
    ) == [(str(source_path), destination_path)]


@pytest.mark.asyncio
async def test_local_tree_expander_missing_source_raises(fs_without_root, caplog):
    expander = LocalTreeExpander()

    source_path = "/missing"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand(source_path, "/dst"))

    message = "Source does not exist."
    assert message in caplog.text

    message = "The source path provided is invalid or cannot be found: {0!r}".format(
        source_path
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_symlink_source_raises(fs_without_root, caplog):
    target_path = pathlib.Path("/target.txt")
    target_path.write_text("")
    source_path = pathlib.Path("/link.txt")
    source_path.symlink_to(target_path)

    expander = LocalTreeExpander()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand(str(source_path), "/dst"))

    message = "Unsupported source type."
    assert message in caplog.text

    message = "Source points to a symlink and cannot be processed: {0!r}".format(
        str(source_path)
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_directory_skips_symlinks(fs_without_root):
    source_directory = pathlib.Path("/root")
    source_directory.mkdir()
    subdirectory_path = source_directory / "subdir"
    subdirectory_path.mkdir()

    root_file_path = source_directory / "a.txt"
    root_file_path.write_text("")
    subdirectory_file_path = subdirectory_path / "b.txt"
    subdirectory_file_path.write_text("")

    (source_directory / "symlink.txt").symlink_to(root_file_path)

    expander = LocalTreeExpander()

    destination_root = "/dst"
    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(source_directory), destination_root)
    )

    expected_pairs = {
        (str(root_file_path), posixpath.join(destination_root, "a.txt")),
        (
            str(subdirectory_file_path),
            posixpath.join(destination_root, "subdir", "b.txt"),
        ),
    }
    assert set(expanded_pairs) == expected_pairs


@pytest.mark.asyncio
async def test_local_tree_expander_file_with_trailing_slash_raises(
    fs_without_root, caplog
):
    source_path = pathlib.Path("/a.txt")
    source_path.write_text("")

    expander = LocalTreeExpander()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/a.txt/", "/dst"))

    message = "Source path ends with a separator but points to a file."
    assert message in caplog.text

    message = "File path includes an invalid trailing separator: {0!r}".format(
        "/a.txt/"
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_file_short_circuit(
    fs_without_root, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _list_directory(self, path):
        yield (FTPEntryType.FILE, "/a.txt")
        yield (FTPEntryType.FILE, "/b.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir",
        new=_list_directory,
    )
    walk_mock = mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk")

    expanded_pairs = await _drain_async_iterator(expander.expand("/a.txt", "/dst.txt"))

    assert expanded_pairs == [("/a.txt", "/dst.txt")]
    walk_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remote_expander_directory_walk(
    fs_without_root, ftp_server, connection_parameters
):
    home_path = pathlib.Path(ftp_server.home)
    root_path = pathlib.Path(ftp_server.root)
    source_directory = home_path / "data"
    source_directory.mkdir()
    (source_directory / "a.txt").write_text("")
    (source_directory / "subdir").mkdir()
    (source_directory / "subdir" / "b.txt").write_text("")

    expander = RemoteFTPExpander(connection_parameters)

    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(root_path / "data"), "/dst")
    )

    expected_pairs = {
        (str(root_path / "data" / "a.txt"), posixpath.join("/dst", "a.txt")),
        (
            str(root_path / "data" / "subdir" / "b.txt"),
            posixpath.join("/dst", "subdir", "b.txt"),
        ),
    }
    assert set(expanded_pairs) == expected_pairs


@pytest.mark.asyncio
async def test_remote_expander_root(fs_without_root, ftp_server, connection_parameters):
    home_path = pathlib.Path(ftp_server.home)
    root_path = pathlib.Path(ftp_server.root)
    (home_path / "root.txt").write_text("")

    expander = RemoteFTPExpander(connection_parameters)

    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(root_path), "/dst")
    )

    assert (
        str(root_path / "root.txt"),
        posixpath.join("/dst", "root.txt"),
    ) in set(expanded_pairs)


@pytest.mark.asyncio
async def test_remote_expander_root_skips_list_directory(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    list_directory_mock = mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir"
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    expanded_pairs = await _drain_async_iterator(expander.expand("/", "/dst"))

    assert expanded_pairs == [
        ("/data/file.txt", posixpath.join("/dst", "data/file.txt"))
    ]
    list_directory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remote_expander_skips_list_directory_when_no_name(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    mocker.patch(
        "pyftpkit._paths_resolver.expander.posixpath.basename", return_value=""
    )

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    list_directory_mock = mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir"
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]
    list_directory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remote_expander_trailing_slash_uses_walk(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    list_directory_mock = mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir"
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data/", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]
    list_directory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_remote_expander_list_directory_target_is_directory(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _list_directory(*args, **kwargs):
        yield (FTPEntryType.DIRECTORY, "/data")

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]


@pytest.mark.asyncio
async def test_remote_expander_walk_filters_directories(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.DIRECTORY, "/data/dir")
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]


@pytest.mark.asyncio
async def test_remote_expander_walk_outside_root_raises(
    ftp_server, connection_parameters, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/other/file.txt")

    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/data", "/dst"))

    message = "Walk yielded a path outside the requested source directory."
    assert message in caplog.text

    message = "Walk yielded a path outside the requested root: {0!r}".format(
        "/other/file.txt"
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_list_directory_skips_non_matching_entries(
    ftp_server, connection_parameters, mocker
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _list_directory(*args, **kwargs):
        yield (FTPEntryType.FILE, "/other")

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]


@pytest.mark.asyncio
async def test_remote_expander_list_directory_error_propagates(
    ftp_server, connection_parameters, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _list_directory(*args, **kwargs):
        raise RuntimeError("error")
        if False:
            yield

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/data/file.txt", "/dst"))

    assert "error" in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_walk_error_propagates(
    ftp_server, connection_parameters, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _walk(*args, **kwargs):
        raise RuntimeError("error")
        if False:
            yield

    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert "error" in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_relative_source_raises(
    ftp_server, connection_parameters, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters)

    async def _list_directory(*args, **kwargs):
        if False:
            yield

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathNotAbsoluteError) as error:
            await _drain_async_iterator(expander.expand("data", "/dst"))

    message = "The remote path is not absolute and does not start from the root."
    assert message in caplog.text

    message = "Ambiguous remote path: {0!r}".format("data")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_prohibited_segments_raise(
    ftp_server, connection_parameters, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(expander.expand("/data/../escape", "/dst"))

    message = "The remote path must not include relative navigation components."
    assert message in caplog.text

    message = "The remote path {0!r} cannot include '.' or '..' segments.".format(
        "/data/.."
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_empty_directory(fs_without_root):
    source_directory = pathlib.Path("/empty")
    source_directory.mkdir()

    expander = LocalTreeExpander()

    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(source_directory), "/dst")
    )

    assert expanded_pairs == []


@pytest.mark.asyncio
async def test_local_tree_expander_trailing_slash(fs_without_root):
    source_directory = pathlib.Path("/root")
    source_directory.mkdir()
    file_path = source_directory / "a.txt"
    file_path.write_text("")

    expander = LocalTreeExpander()

    expanded_pairs = await _drain_async_iterator(expander.expand("/root/", "/dst"))

    assert expanded_pairs == [(str(file_path), posixpath.join("/dst", "a.txt"))]
