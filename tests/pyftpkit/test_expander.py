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


@pytest.fixture
def connection_parameters_no_connect(host, port, username, password):
    return ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 1,
            "max_workers": 2,
        }
    )


@pytest.fixture
def ftp_filesystem_no_connect(mocker):
    async def _enter(self):
        return self

    async def _exit(self, *args, **kwargs):
        return None

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.__aenter__", new=_enter
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.__aexit__", new=_exit)


@pytest.mark.asyncio
async def test_local_tree_expander_rejects_bytes_paths(caplog):
    expander = LocalTreeExpander()

    path = b"/data"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(expander.expand(path, "/dst"))

    message = "Bytes are not allowed for paths."
    assert message in caplog.text

    message = "Paths must be given as text strings rather than bytes: {0!r}".format(
        path
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_rejects_non_string_paths(caplog):
    expander = LocalTreeExpander()

    path = 123
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(expander.expand(path, "/dst"))

    message = "Path values must be string-like."
    assert message in caplog.text

    message = "Paths must be given in a string-like representation: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_rejects_bytes_destination(caplog):
    expander = LocalTreeExpander()

    path = b"/dst"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(expander.expand("/missing", path))

    message = "Bytes are not allowed for paths."
    assert message in caplog.text

    message = "Paths must be given as text strings rather than bytes: {0!r}".format(
        path
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_accepts_pathlike_arguments(filesystem_without_root):
    source_path = pathlib.Path("/a.txt")
    source_path.write_text("", encoding="utf-8")
    destination_path = pathlib.Path("/b.txt")

    expander = LocalTreeExpander()

    assert await _drain_async_iterator(
        expander.expand(source_path, destination_path)
    ) == [(str(source_path), str(destination_path))]


@pytest.mark.asyncio
async def test_local_tree_expander_returns_single_pair_for_file(
    filesystem_without_root,
):
    source_path = pathlib.Path("/a.txt")
    source_path.write_text("", encoding="utf-8")
    destination_path = "/b.txt"

    expander = LocalTreeExpander()

    assert await _drain_async_iterator(
        expander.expand(str(source_path), destination_path)
    ) == [(str(source_path), destination_path)]


@pytest.mark.asyncio
async def test_local_tree_expander_raises_for_missing_source(
    filesystem_without_root, caplog
):
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
async def test_local_tree_expander_raises_for_symlink_source(
    filesystem_without_root, caplog
):
    target_path = pathlib.Path("/target.txt")
    target_path.write_text("", encoding="utf-8")
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
async def test_local_tree_expander_skips_symlinks_in_directory(filesystem_without_root):
    source_directory = pathlib.Path("/root")
    source_directory.mkdir()
    subdirectory_path = source_directory / "subdir"
    subdirectory_path.mkdir()

    root_file_path = source_directory / "a.txt"
    root_file_path.write_text("", encoding="utf-8")
    subdirectory_file_path = subdirectory_path / "b.txt"
    subdirectory_file_path.write_text("", encoding="utf-8")

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
async def test_local_tree_expander_raises_for_file_with_trailing_slash(
    filesystem_without_root, caplog
):
    source_path = pathlib.Path("/a.txt")
    source_path.write_text("", encoding="utf-8")

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
async def test_remote_expander_short_circuits_for_file(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

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
async def test_remote_expander_falls_back_to_walk_when_list_directory_returns_directory(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

    async def _list_directory():
        yield (FTPEntryType.DIRECTORY, "/data")

    list_directory_mock = mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir"
    )
    list_directory_mock.return_value = _list_directory()

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    walk_mock = mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk")
    walk_mock.return_value = _walk()

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]
    assert list_directory_mock.called
    assert walk_mock.called


@pytest.mark.asyncio
async def test_remote_expander_walks_directory_tree(ftp_server, connection_parameters):
    home_path = pathlib.Path(ftp_server.home)
    root_path = pathlib.Path(ftp_server.root)
    source_directory = home_path / "data"
    source_directory.mkdir()
    (source_directory / "a.txt").write_text("", encoding="utf-8")
    (source_directory / "subdir").mkdir()
    (source_directory / "subdir" / "b.txt").write_text("", encoding="utf-8")

    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

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
async def test_remote_expander_skips_non_file_entries_from_walk(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

    async def _list_directory():
        if False:
            yield

    list_directory_mock = mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir"
    )
    list_directory_mock.return_value = _list_directory()

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.DIRECTORY, "/data/subdir")
        yield ("", FTPEntryType.FILE, "/data/file.txt")

    walk_mock = mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk")
    walk_mock.return_value = _walk()

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert expanded_pairs == [("/data/file.txt", posixpath.join("/dst", "file.txt"))]
    assert list_directory_mock.called
    assert walk_mock.called


@pytest.mark.asyncio
async def test_remote_expander_handles_root_directory(
    ftp_server, connection_parameters
):
    home_path = pathlib.Path(ftp_server.home)
    root_path = pathlib.Path(ftp_server.root)
    (home_path / "root.txt").write_text("", encoding="utf-8")

    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(root_path), "/dst")
    )

    assert (
        str(root_path / "root.txt"),
        posixpath.join("/dst", "root.txt"),
    ) in set(expanded_pairs)


@pytest.mark.asyncio
async def test_remote_expander_skips_list_directory_for_root(
    ftp_server, connection_parameters
):
    home_path = pathlib.Path(ftp_server.home)
    source_directory = home_path / "data"
    source_directory.mkdir()
    (source_directory / "file.txt").write_text("", encoding="utf-8")

    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

    expanded_pairs = await _drain_async_iterator(expander.expand("/", "/dst"))

    root_path = pathlib.Path(ftp_server.root)
    expected_pairs = {
        (
            str(root_path / "data" / "file.txt"),
            posixpath.join("/dst", "data", "file.txt"),
        )
    }
    assert set(expanded_pairs) == expected_pairs


@pytest.mark.asyncio
async def test_remote_expander_skips_list_directory_when_basename_missing(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

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
async def test_remote_expander_uses_walk_for_trailing_slash(
    ftp_server, connection_parameters
):
    home_path = pathlib.Path(ftp_server.home)
    source_directory = home_path / "data"
    source_directory.mkdir()
    (source_directory / "file.txt").write_text("", encoding="utf-8")

    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data/", "/dst"))

    root_path = pathlib.Path(ftp_server.root)
    expected_pairs = {
        (str(root_path / "data" / "file.txt"), posixpath.join("/dst", "file.txt"))
    }
    assert set(expanded_pairs) == expected_pairs


@pytest.mark.asyncio
async def test_remote_expander_list_directory_treats_target_as_directory(
    ftp_server, connection_parameters
):
    home_path = pathlib.Path(ftp_server.home)
    source_directory = home_path / "data"
    source_directory.mkdir()
    (source_directory / "file.txt").write_text("", encoding="utf-8")

    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    root_path = pathlib.Path(ftp_server.root)
    expected_pairs = {
        (str(root_path / "data" / "file.txt"), posixpath.join("/dst", "file.txt"))
    }
    assert set(expanded_pairs) == expected_pairs


@pytest.mark.asyncio
async def test_remote_expander_walk_filters_directories(
    ftp_server, connection_parameters
):
    home_path = pathlib.Path(ftp_server.home)
    source_directory = home_path / "data"
    source_directory.mkdir()
    (source_directory / "file.txt").write_text("", encoding="utf-8")
    nested_directory = source_directory / "subdir"
    nested_directory.mkdir()
    (nested_directory / "nested.txt").write_text("", encoding="utf-8")

    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

    expanded_pairs = await _drain_async_iterator(expander.expand("/data", "/dst"))

    root_path = pathlib.Path(ftp_server.root)
    expected_pairs = {
        (str(root_path / "data" / "file.txt"), posixpath.join("/dst", "file.txt")),
        (
            str(root_path / "data" / "subdir" / "nested.txt"),
            posixpath.join("/dst", "subdir", "nested.txt"),
        ),
    }
    assert set(expanded_pairs) == expected_pairs


@pytest.mark.asyncio
async def test_remote_expander_raises_when_walk_yields_outside_root(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

    async def _list_directory(*args, **kwargs):
        if False:
            yield

    async def _walk(*args, **kwargs):
        yield ("", FTPEntryType.FILE, "/other/file.txt")

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )
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
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

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
async def test_remote_expander_list_directory_error_bubbles_up(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

    async def _list_directory(*args, **kwargs):
        raise RuntimeError("list directory failed")
        if False:
            yield

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk")

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/data/file.txt", "/dst"))

    assert caplog.text == ""
    assert "list directory failed" in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_walk_error_bubbles_up(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

    async def _list_directory(*args, **kwargs):
        if False:
            yield

    async def _walk(*args, **kwargs):
        raise RuntimeError("walk failed")
        if False:
            yield

    mocker.patch(
        "pyftpkit._paths_resolver.expander.FTPFileSystem.listdir", new=_list_directory
    )
    mocker.patch("pyftpkit._paths_resolver.expander.FTPFileSystem.walk", new=_walk)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/data", "/dst"))

    assert caplog.text == ""
    assert "walk failed" in str(error.value)


@pytest.mark.asyncio
async def test_remote_expander_raises_for_relative_source(
    connection_parameters_no_connect, ftp_filesystem_no_connect, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters_no_connect)

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
async def test_remote_expander_raises_for_prohibited_segments(
    ftp_server, connection_parameters, mocker, caplog
):
    expander = RemoteFTPExpander(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as error:
            await _drain_async_iterator(expander.expand("/data/../escape", "/dst"))

    message = "The remote path must not include relative navigation components."
    assert message in caplog.text

    message = "The remote path {0!r} cannot include {1!r} or {2!r} segments.".format(
        "/data/..", posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_returns_empty_for_empty_directory(
    filesystem_without_root,
):
    source_directory = pathlib.Path("/empty")
    source_directory.mkdir()

    expander = LocalTreeExpander()

    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(source_directory), "/dst")
    )

    assert expanded_pairs == []


@pytest.mark.asyncio
async def test_local_tree_expander_raises_when_walk_errors(
    filesystem_without_root, mocker, caplog
):
    source_directory = pathlib.Path("/root")
    source_directory.mkdir()

    expander = LocalTreeExpander()

    walk_error = OSError("permission denied")

    def _walk(*args, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror is not None:
            onerror(walk_error)
        if False:
            yield ("", [], [])

    mocker.patch("pyftpkit._paths_resolver.expander.os.walk", new=_walk)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await _drain_async_iterator(expander.expand("/root", "/dst"))

    message = "Error occurred while traversing the source directory."
    assert message in caplog.text

    message = "Could not traverse the source directory: {0!r}".format("/root")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_local_tree_expander_trailing_slash_preserves_directory(
    filesystem_without_root,
):
    source_directory = pathlib.Path("/root")
    source_directory.mkdir()
    file_path = source_directory / "a.txt"
    file_path.write_text("", encoding="utf-8")

    expander = LocalTreeExpander()

    expanded_pairs = await _drain_async_iterator(expander.expand("/root/", "/dst"))

    assert expanded_pairs == [(str(file_path), posixpath.join("/dst", "a.txt"))]


@pytest.mark.asyncio
async def test_local_tree_expander_skips_non_file_entries_from_walk(
    filesystem_without_root, mocker
):
    source_directory = pathlib.Path("/root")
    source_directory.mkdir()

    expander = LocalTreeExpander()

    def _walk(*args, **kwargs):
        yield (str(source_directory), [], ["not-a-file"])

    mocker.patch("pyftpkit._paths_resolver.expander.os.walk", new=_walk)
    mocker.patch("pyftpkit._paths_resolver.expander.os.path.isfile", return_value=False)
    mocker.patch("pyftpkit._paths_resolver.expander.os.path.islink", return_value=False)

    expanded_pairs = await _drain_async_iterator(
        expander.expand(str(source_directory), "/dst")
    )

    assert expanded_pairs == []
