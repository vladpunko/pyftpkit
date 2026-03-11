# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-27

import asyncio
import collections
import contextlib
import ftplib
import logging
import os
import pathlib
import posixpath
import random
import types
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import (
    FTPError,
    FTPPathError,
    FTPPathNotAbsoluteError,
)
from pyftpkit.ftpfs import (
    FTPEntryType,
    FTPFileSystem,
)


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
def directory_tree(ftp_server):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    directories = []
    non_directories = []

    for _ in range(10):
        directory_path = home / str(uuid.uuid4())
        directory_path.mkdir()
        directories.append(directory_path)

        for _ in range(10):
            path = directory_path / str(uuid.uuid4())
            path.write_text("", encoding="utf-8")
            non_directories.append(path)

    for _ in range(10):
        parent = random.choice(directories)

        directory_path = parent / str(uuid.uuid4())
        directory_path.mkdir()
        directories.append(directory_path)

        for _ in range(10):
            path = parent / str(uuid.uuid4())
            path.write_text("", encoding="utf-8")
            non_directories.append(path)

    return types.SimpleNamespace(
        directories=directories,
        ftp_directories=[
            root / directory_path.relative_to(home) for directory_path in directories
        ],
        non_directories=non_directories,
        ftp_non_directories=[root / path.relative_to(home) for path in non_directories],
    )


async def list_directory(ftp_filesystem, path):
    """Helper to collect listdir output."""
    directories = []
    non_directories = []

    async for entry_type, entry_path in ftp_filesystem.listdir(str(path)):
        if entry_type == FTPEntryType.DIRECTORY:
            directories.append(entry_path)
        else:
            non_directories.append(entry_path)

    return directories, non_directories


async def drain_async_iterator(iterator):
    async for _ in iterator:
        pass


@pytest.mark.asyncio
async def test_list_directory(caplog, ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    expected_directories = []
    for _ in range(3):
        name = str(uuid.uuid4())
        directory_path = home / name
        directory_path.mkdir()
        expected_directories.append(root / name)

    expected_non_directories = []
    for _ in range(3):
        name = str(uuid.uuid4())
        path = home / name
        path.write_text("", encoding="utf-8")
        expected_non_directories.append(root / name)

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            directories, non_directories = await list_directory(ftp_filesystem, root)

            assert collections.Counter(directories) == collections.Counter(
                map(str, expected_directories)
            )
            assert collections.Counter(non_directories) == collections.Counter(
                map(str, expected_non_directories)
            )

    message = "Listing remote directory: {0!r}".format(str(root))
    assert message in caplog.text


@pytest.mark.asyncio
async def test_list_directory_accepts_pathlike_root(
    caplog, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    (home / "dir").mkdir()
    (home / "file.txt").write_text("", encoding="utf-8")

    directories = []
    non_directories = []

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            async for entry_type, entry_path in ftp_filesystem.listdir(root):
                if entry_type == FTPEntryType.DIRECTORY:
                    directories.append(entry_path)
                else:
                    non_directories.append(entry_path)

    assert set(directories) == {str(root / "dir")}
    assert set(non_directories) == {str(root / "file.txt")}
    message = "Listing remote directory: {0!r}".format(str(root))
    assert message in caplog.text


@pytest.mark.asyncio
async def test_list_directory_with_error(caplog, ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.root) / "noop"

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await list_directory(ftp_filesystem, path)

    message = "The FTP server returned an error during directory listing."
    assert message in caplog.text

    message = "Failed to list this directory: {0!r}".format(str(path))
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_invalid_path(
    caplog, host, port, username, password, mocker
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 1,
            "max_workers": 1,
        }
    )

    @contextlib.asynccontextmanager
    async def _acquire():
        yield object()

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", mocker.MagicMock(acquire=_acquire))

        path = {}
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

        message = "The remote path must be a string."
        assert message in caplog.text

        message = (
            "Only string values are permitted for the remote path."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(error.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

        message = "The remote path must include at least one non-whitespace character."
        assert message in caplog.text

        message = "The remote path must not be empty or whitespace."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

        message = "The remote path is not absolute and does not start from the root."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_relative_segments(caplog, connection_parameters):
    path = "/root/../escape"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await list_directory(ftp_filesystem, path)

    message = "The remote path must not include relative navigation components."
    assert message in caplog.text

    message = "The remote path {0!r} cannot include {1!r} or {2!r} segments.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_trailing_whitespace(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    directory_name = "dir  "
    subdirectory_name = "subdir"
    file_name = "file.txt"

    target_directory = home / directory_name
    target_directory.mkdir()
    (target_directory / subdirectory_name).mkdir()
    (target_directory / file_name).write_text("", encoding="utf-8")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(
            ftp_filesystem, str(root / directory_name)
        )

    assert set(directories) == {str(root / directory_name / subdirectory_name)}
    assert set(non_directories) == {str(root / directory_name / file_name)}


@pytest.mark.asyncio
async def test_list_directory_special_symbols(
    ftp_server, connection_parameters, filenames_with_symbols
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    for index, name in enumerate(filenames_with_symbols):
        (home / name).write_text("content # {0!s}".format(index), encoding="utf-8")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == []
    assert set(non_directories) == {str(root / name) for name in filenames_with_symbols}


@pytest.mark.asyncio
async def test_list_directory_parse_error_wrapped(
    caplog, mocker, connection_parameters
):
    async def _listdir(*args, **kwargs):
        raise KeyError("listing parser failure")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

    message = "Failed to parse directory listing from the FTP server."
    assert message in caplog.text

    message = "Failed to parse directory listing for: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_bad_entry(mocker, ftp_server, connection_parameters):
    root = pathlib.Path(ftp_server.root)
    entries = [
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:12 dir",
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 text.txt",
        "lrwxrwxrwx   1 owner group          11 Oct 27 09:17 symlink -> test.txt",
        "lrwxrwxrwx   1 owner group          11 Oct 27 09:17 bad_symlink",
        "",
        "error",
        "          ",
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:20 .",
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:21 ..",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == [str(root / "dir")]
    assert non_directories == [
        str(root / "text.txt"),
        str(root / "symlink"),
    ]


@pytest.mark.asyncio
async def test_list_directory_name_with_symlink_token_preserved(
    mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    entries = [
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 name -> target.txt",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == []
    assert non_directories == [str(root / "name -> target.txt")]


@pytest.mark.asyncio
async def test_list_directory_skips_absolute_entries(
    mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    entries = [
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:12 /absdir",
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 file.txt",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == []
    assert non_directories == [str(root / "file.txt")]


@pytest.mark.asyncio
async def test_list_directory_skips_empty_name(
    mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    entries = [
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 ",
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 valid.txt",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == []
    assert non_directories == [str(root / "valid.txt")]


@pytest.mark.asyncio
async def test_list_directory_skips_entries_with_separators(
    mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    entries = [
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:12 bad/dir",
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 bad\\file.txt",
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 good.txt",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == []
    assert non_directories == [str(root / "good.txt")]


@pytest.mark.asyncio
async def test_walk_traverses_directory_tree(
    ftp_server, directory_tree, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    collected_dirs = []
    collected_nondirs = []

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        async for _, entry_type, entry_path in ftp_filesystem.walk(str(root)):
            if entry_type == FTPEntryType.DIRECTORY:
                collected_dirs.append(entry_path)
            else:
                collected_nondirs.append(entry_path)

    assert len(collected_dirs) == len(directory_tree.ftp_directories)
    assert len(collected_nondirs) == len(directory_tree.ftp_non_directories)

    assert set(collected_dirs) == {str(path) for path in directory_tree.ftp_directories}
    assert set(collected_nondirs) == {
        str(path) for path in directory_tree.ftp_non_directories
    }


@pytest.mark.asyncio
async def test_walk_with_minimal_queue_capacity_traverses_deep_tree(
    ftp_server, connection_parameters, caplog
):
    connection_parameters = connection_parameters.model_copy(
        update={"max_queues_size": 1, "max_workers": 1}
    )
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    expected_directories = set()
    expected_files = set()

    for outer_index in range(5):
        current = home / "dir-{0}".format(outer_index)
        current.mkdir()
        expected_directories.add(str(root / current.relative_to(home)))

        for depth_index in range(5):
            current = current / "nested-{0}".format(depth_index)
            current.mkdir()
            expected_directories.add(str(root / current.relative_to(home)))

            file_path = current / "file-{0}-{1}.txt".format(outer_index, depth_index)
            file_path.write_text("", encoding="utf-8")
            expected_files.add(str(root / file_path.relative_to(home)))

    async def _collect_walk(ftp_filesystem, walk_root):
        directories = set()
        files = set()

        async for _, entry_type, entry_path in ftp_filesystem.walk(str(walk_root)):
            if entry_type == FTPEntryType.DIRECTORY:
                directories.add(entry_path)
            else:
                files.add(entry_path)

        return directories, files

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            collected_dirs, collected_files = await asyncio.wait_for(
                _collect_walk(ftp_filesystem, root), timeout=10
            )

    assert collected_dirs == expected_directories
    assert collected_files == expected_files
    assert caplog.text == ""


@pytest.mark.asyncio
async def test_walk_accepts_pathlike_root(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    (home / "dir").mkdir()
    (home / "dir" / "file.txt").write_text("", encoding="utf-8")

    collected = []

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        async for _, entry_type, entry_path in ftp_filesystem.walk(root):
            collected.append((entry_type, entry_path))

    assert (FTPEntryType.DIRECTORY, str(root / "dir")) in collected
    assert (FTPEntryType.FILE, str(root / "dir" / "file.txt")) in collected


@pytest.mark.asyncio
async def test_walk_no_permission(
    caplog,
    ftp_server,
    connection_parameters,
    mocker,
):
    root = pathlib.Path(ftp_server.root)

    async def _listdir(*args, **kwargs):
        raise PermissionError("permission denied during listing")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                async for _, _, _ in ftp_filesystem.walk(str(root)):
                    pass

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text

    message = "Walk worker error."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_walk_invalid_path(caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

        message = "The remote path must be a string."
        assert message in caplog.text

        message = (
            "Only string values are permitted for the remote path."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(error.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

        message = "The remote path must include at least one non-whitespace character."
        assert message in caplog.text

        message = "The remote path must not be empty or whitespace."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

        message = "The remote path is not absolute and does not start from the root."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_walk_relative_segments(caplog, connection_parameters):
    path = "/root/../escape"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

    message = "The remote path must not contain directory traversal segments."
    assert message in caplog.text

    message = "The remote path {0!r} must not reference {1!r} or {2!r}.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_walk_trailing_whitespace(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    directory_name = "dir  "
    subdirectory_name = "subdir"
    file_name = "file.txt"
    nested_name = "nested.txt"

    root_directory = home / directory_name
    root_directory.mkdir()
    (root_directory / file_name).write_text("", encoding="utf-8")
    subdirectory = root_directory / subdirectory_name
    subdirectory.mkdir()
    (subdirectory / nested_name).write_text("", encoding="utf-8")

    collected_dirs = []
    collected_nondirs = []

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        async for _, entry_type, entry_path in ftp_filesystem.walk(
            str(root / directory_name)
        ):
            if entry_type == FTPEntryType.DIRECTORY:
                collected_dirs.append(entry_path)
            else:
                collected_nondirs.append(entry_path)

    expected_directory = str(root / directory_name / subdirectory_name)
    expected_files = {
        str(root / directory_name / file_name),
        str(root / directory_name / subdirectory_name / nested_name),
    }

    assert set(collected_dirs) == {expected_directory}
    assert set(collected_nondirs) == expected_files


@pytest.mark.asyncio
async def test_walk_queue_full_does_not_hang(mocker, connection_parameters, caplog):
    class _QueueWrapper(asyncio.Queue):
        def __init__(self, *args, raise_on_put_nowait=True, **kwargs):
            super().__init__(*args, **kwargs)

            self._raise_on_put_nowait = raise_on_put_nowait

        def put_nowait(self, item):
            if self._raise_on_put_nowait and isinstance(item, Exception):
                raise asyncio.QueueFull()

            return super().put_nowait(item)

    def _queue_factory(*args, **kwargs):
        return _QueueWrapper(*args, **kwargs)

    async def _listdir(*args, **kwargs):
        raise RuntimeError("listing worker failed")
        yield

    mocker.patch("pyftpkit.ftpfs.asyncio.Queue", side_effect=_queue_factory)
    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await asyncio.wait_for(
                    drain_async_iterator(ftp_filesystem.walk(path)), timeout=2
                )

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text
    assert "Walk worker error." in str(error.value)


@pytest.mark.asyncio
async def test_walk_discovery_queue_full_does_not_hang(mocker, connection_parameters):
    class _QueueWrapper(asyncio.Queue):
        def __init__(self, *args, raise_on_put_nowait=False, **kwargs):
            super().__init__(*args, **kwargs)

            self._raise_on_put_nowait = raise_on_put_nowait

        def put_nowait(self, item):
            if self._raise_on_put_nowait:
                raise asyncio.QueueFull()

            return super().put_nowait(item)

    queue_calls = {"count": 0}

    def _queue_factory(*args, **kwargs):
        queue_calls["count"] += 1
        raise_on_put_nowait = queue_calls["count"] == 3

        return _QueueWrapper(*args, raise_on_put_nowait=raise_on_put_nowait, **kwargs)

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.DIRECTORY, "/root/subdir")
        return
        yield

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", side_effect=_queue_factory)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)

        output = []
        async for directory_path, entry_type, entry_path in ftp_filesystem.walk(
            "/root"
        ):
            output.append((directory_path, entry_type, entry_path))

    expected_output = ("/root", FTPEntryType.DIRECTORY, "/root/subdir")
    assert expected_output in output


@pytest.mark.asyncio
async def test_walk_drains_output_queue_after_timeout(mocker, connection_parameters):
    async def _wait_for_timeout(awaitable, *args, **kwargs):
        await asyncio.sleep(0)
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.FILE, "/root/file.txt")

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch("pyftpkit.ftpfs.asyncio.wait_for", new=_wait_for_timeout)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)

        output = []
        async for directory_path, entry_type, entry_path in ftp_filesystem.walk(
            "/root"
        ):
            output.append((directory_path, entry_type, entry_path))

    expected_output = ("/root", FTPEntryType.FILE, "/root/file.txt")
    assert output == [expected_output]


@pytest.mark.asyncio
async def test_walk_drains_output_queue_exception_after_timeout(
    mocker, connection_parameters, caplog
):
    async def _wait_for_timeout(awaitable, timeout, *args, **kwargs):
        if timeout == 0.1 and asyncio.iscoroutine(awaitable):
            await asyncio.sleep(0)
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise asyncio.TimeoutError
        return await real_wait_for(awaitable, timeout, *args, **kwargs)

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.FILE, "/root/file.txt")

    class _OutputExceptionQueue(asyncio.Queue):
        async def put(self, item):
            if not isinstance(item, Exception):
                item = RuntimeError("queued output failure")
            await super().put(item)

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    real_wait_for = asyncio.wait_for
    original_queue = asyncio.Queue

    def _queue_factory(*args, **kwargs):
        maxsize = kwargs.get("maxsize", 0)
        if maxsize:
            return _OutputExceptionQueue(*args, **kwargs)
        return original_queue(*args, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", side_effect=_queue_factory)
        mocker.patch("pyftpkit.ftpfs.asyncio.wait_for", new=_wait_for_timeout)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await drain_async_iterator(ftp_filesystem.walk("/root"))

    message = "Walk worker error."
    assert message in str(error.value)
    assert caplog.text == ""


@pytest.mark.asyncio
async def test_walk_was_cancelled(connection_parameters, caplog):
    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        task = asyncio.create_task(drain_async_iterator(ftp_filesystem.walk(path)))
        await asyncio.sleep(0.01)
        with caplog.at_level(logging.WARNING, logger="pyftpkit"):
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as error:
                await task

    assert str(error.value) == ""
    assert caplog.text == ""


@pytest.mark.asyncio
async def test_walk_cancel_timeout_logs_warning(mocker, connection_parameters, caplog):
    async def _slow_listdir(*args, **kwargs):
        await asyncio.sleep(10)
        if False:
            yield

    real_wait_for = asyncio.wait_for

    async def _fake_wait_for(awaitable, timeout, *args, **kwargs):
        if timeout == 0.1 and not asyncio.iscoroutine(awaitable):
            raise asyncio.TimeoutError
        return await real_wait_for(awaitable, timeout, *args, **kwargs)

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_slow_listdir)
    mocker.patch("pyftpkit.ftpfs.asyncio.wait_for", new=_fake_wait_for)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        task = asyncio.create_task(drain_async_iterator(ftp_filesystem.walk(path)))
        await asyncio.sleep(0.05)
        with caplog.at_level(logging.WARNING, logger="pyftpkit"):
            task.cancel()
            with pytest.raises(asyncio.CancelledError) as error:
                await task

    assert str(error.value) == ""
    message = "The walk operation was cancelled."
    assert message in caplog.text


@pytest.mark.asyncio
async def test_walk_worker_error_propagates(mocker, connection_parameters, caplog):
    async def _delayed_error(*args, **kwargs):
        await asyncio.sleep(0.05)
        raise RuntimeError("listing worker failed")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_delayed_error)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text
    assert "Walk worker error." in str(error.value)


@pytest.mark.asyncio
async def test_walk_worker_error_propagates_when_output_queue_full(
    mocker, connection_parameters, caplog
):
    connection_parameters = connection_parameters.model_copy(
        update={"max_workers": 1, "max_queues_size": 1}
    )

    async def _listdir(*args, **kwargs):
        raise RuntimeError("output queue worker failed")
        if False:
            yield

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        original_put_nowait = asyncio.Queue.put_nowait

        def _put_nowait(self, item):
            if isinstance(item, Exception):
                raise asyncio.QueueFull()
            return original_put_nowait(self, item)

        mocker.patch("asyncio.Queue.put_nowait", new=_put_nowait)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await drain_async_iterator(ftp_filesystem.walk("/root"))

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text
    assert "Walk worker error." in str(error.value)


@pytest.mark.asyncio
async def test_walk_exception_items_mark_task_done(
    mocker, connection_parameters, caplog
):
    connection_parameters = connection_parameters.model_copy(
        update={"max_workers": 1, "max_queues_size": 1}
    )

    class _QueueSpy(asyncio.Queue):
        created = []

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            _QueueSpy.created.append(self)

    async def _listdir(*args, **kwargs):
        raise RuntimeError("listing failed for queued item")
        if False:
            yield

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", new=_QueueSpy)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await drain_async_iterator(ftp_filesystem.walk("/root"))

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text

    message = "Walk worker error."
    assert message in str(error.value)

    assert len(_QueueSpy.created) >= 2
    output_queue = _QueueSpy.created[1]
    assert output_queue._unfinished_tasks == 0


@pytest.mark.asyncio
async def test_walk_output_queue_full_fails_fast(
    mocker, host, port, username, password, caplog
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 1,
            "max_workers": 1,
            "max_queues_size": 1,
        }
    )

    class _QueueWrapper(asyncio.Queue):
        def put_nowait(self, item):
            if isinstance(item, tuple):
                raise asyncio.QueueFull()
            return super().put_nowait(item)

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.FILE, "/root/file.txt")

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", new=_QueueWrapper)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await drain_async_iterator(ftp_filesystem.walk("/root"))

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text
    assert "Walk worker error." in str(error.value)


@pytest.mark.asyncio
async def test_walk_generator_close_does_not_raise(mocker, connection_parameters):
    connection_parameters = connection_parameters.model_copy(
        update={"max_workers": 1, "max_queues_size": 10}
    )

    async def _listdir(*args, **kwargs):
        for index in range(5):
            yield (FTPEntryType.FILE, f"/root/file{index}.txt")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)
        iterator = ftp_filesystem.walk("/root")
        await anext(iterator)
        await asyncio.sleep(0.05)
        await iterator.aclose()


@pytest.mark.asyncio
async def test_walk_cancels_join_task_on_close(mocker, connection_parameters):
    connection_parameters = connection_parameters.model_copy(
        update={"max_workers": 1, "max_queues_size": 1}
    )
    join_tasks = []
    original_create_task = asyncio.create_task

    class _QueueJoinSpy(asyncio.Queue):
        async def join(self):
            future = asyncio.get_running_loop().create_future()
            return await future

    def _create_task_spy(coroutine, *args, **kwargs):
        task = original_create_task(coroutine, *args, **kwargs)
        if getattr(coroutine, "cr_code", None) and coroutine.cr_code.co_name == "join":
            join_tasks.append(task)
        return task

    async def _listdir(*args, **kwargs):
        yield (FTPEntryType.FILE, "/root/file.txt")
        await asyncio.sleep(1)

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", new=_QueueJoinSpy)
        mocker.patch("pyftpkit.ftpfs.asyncio.create_task", new=_create_task_spy)
        mocker.patch.object(ftp_filesystem, "_listdir", _listdir)

        iterator = ftp_filesystem.walk("/root")
        await anext(iterator)
        await iterator.aclose()

    assert join_tasks
    assert all(task.cancelled() or task.done() for task in join_tasks)


@pytest.mark.asyncio
async def test_walk_stop_event_breaks_worker(connection_parameters, mocker):
    class _AlwaysSetEvent(asyncio.Event):
        def is_set(self):
            return True

    async def _listdir(*args, **kwargs):
        await asyncio.sleep(0.2)
        return
        yield

    mocker.patch("pyftpkit.ftpfs.asyncio.Event", new=_AlwaysSetEvent)
    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await drain_async_iterator(ftp_filesystem.walk(path))


@pytest.mark.asyncio
async def test_walk_stop_event_breaks_main_loop(connection_parameters, mocker, caplog):
    class _QueueWrapper(asyncio.Queue):
        def put_nowait(self, item):
            if isinstance(item, Exception):
                raise asyncio.QueueFull()

            return super().put_nowait(item)

    original_wait_for = asyncio.wait_for

    async def _slow_wait_for(awaitable, timeout):
        try:
            await asyncio.sleep(0.2)

            return await original_wait_for(awaitable, timeout)
        except asyncio.CancelledError:
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise

    async def _listdir(*args, **kwargs):
        path = args[1]
        if path == "/":
            yield (FTPEntryType.DIRECTORY, "/subdir1")
            yield (FTPEntryType.DIRECTORY, "/subdir2")
            await asyncio.sleep(0.05)
            return
        raise RuntimeError("listing failed for subdirectory")
        yield

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", new=_QueueWrapper)
        mocker.patch("pyftpkit.ftpfs.asyncio.wait_for", new=_slow_wait_for)
        mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text
    assert "Walk worker error." in str(error.value)


@pytest.mark.asyncio
async def test_walk_drain_output_queue(mocker, ftp_server, connection_parameters):
    root = pathlib.Path(ftp_server.root)
    directory_path = pathlib.Path(ftp_server.home) / "test"
    directory_path.mkdir()
    path = directory_path / "text.txt"
    path.write_text("", encoding="utf-8")

    expected_directory = str(root / "test")
    expected_output = (
        expected_directory,
        FTPEntryType.FILE,
        str(root / "test" / "text.txt"),
    )

    original_listdir = FTPFileSystem._listdir

    async def _listdir(self, path, **keyword_arguments):
        ftp_connection = keyword_arguments["ftp"]
        if os.path.basename(str(path)) == "test":
            await asyncio.sleep(random.uniform(0.1, 0.5))  # short delay

        async for entry in original_listdir(self, path, ftp=ftp_connection):
            yield entry

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    output = []

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        root_str = str(root)

        async for directory_path_out, entry_type, entry_path in ftp_filesystem.walk(
            root_str
        ):
            output.append((directory_path_out, entry_type, entry_path))
            if directory_path_out == root_str:
                break

        async for directory_path_out, entry_type, entry_path in ftp_filesystem.walk(
            root_str
        ):
            output.append((directory_path_out, entry_type, entry_path))

    drained_item = next(
        (item for item in output if item[0] == expected_directory), None
    )
    assert drained_item is not None
    assert drained_item == expected_output


@pytest.mark.asyncio
async def test_makedirs_invalid_paths(caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        paths = object()
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(TypeError) as error:
                await ftp_filesystem.makedirs(paths)

        message = "Expected paths to be a collection of strings."
        assert message in caplog.text

        message = (
            "Invalid type for paths: expected an iterable of path strings."
            "\nAn unsupported type was provided for paths: {0!s}".format(
                type(paths).__name__
            )
        )
        assert message in str(error.value)

        path = {}
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.makedirs([path])

        message = "The path must be provided as a string value."
        assert message in caplog.text

        message = (
            "The path must be defined using string data."
            "\nThe path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(error.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.makedirs([path])

        message = "The path must contain at least one non-blank character."
        assert message in caplog.text

        message = "The path cannot be blank or whitespace-only."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.makedirs([path])

        message = "The path is relative rather than starting at the root."
        assert message in caplog.text

        message = "Ambiguous path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_accepts_pathlike_entries(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    path = pathlib.Path("/alpha/beta")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.makedirs([path])

    assert (home / "alpha").is_dir()
    assert (home / "alpha" / "beta").is_dir()


@pytest.mark.asyncio
async def test_makedirs_relative_segments(caplog, connection_parameters):
    path = "/root/../escape"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.makedirs([path])

    message = "The remote path must not include relative traversal markers."
    assert message in caplog.text

    message = "The path {0!r} must not reference {1!r} or {2!r}.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_trailing_whitespace(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.makedirs(["/a/b   ", "/c/d   "])

    assert (home / "a").is_dir()
    assert (home / "a" / "b   ").is_dir()
    assert (home / "c").is_dir()
    assert (home / "c" / "d   ").is_dir()


@pytest.mark.asyncio
async def test_makedirs_current_working_directory_non_permission_error(
    caplog, mocker, connection_parameters
):
    mocker.patch(
        "pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_temp("temporary failure")
    )

    path = "/test"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs([path])

    message = "Failed to validate the remote directory."
    assert message in caplog.text

    message = "Failed to access remote directory: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_make_directory_permission_error_current_working_directory_fails(
    caplog, mocker, connection_parameters
):
    mocker.patch(
        "pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_perm("permission denied")
    )
    mocker.patch(
        "pyftpkit.ftpfs.FTP.mkd", side_effect=ftplib.error_perm("permission denied")
    )

    path = "/test"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs([path])

    message = "Creation of the remote directory did not succeed."
    assert message in caplog.text

    message = "Remote directory setup failed: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_make_directory_non_permission_error_current_directory_fails(
    caplog, mocker, connection_parameters
):
    mocker.patch(
        "pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_perm("permission denied")
    )
    mocker.patch(
        "pyftpkit.ftpfs.FTP.mkd", side_effect=ftplib.error_temp("temporary failure")
    )

    path = "/test"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs([path])

    message = "The remote directory could not be initialized."
    assert message in caplog.text

    message = "FTP server directory creation failed: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_creates_directories(caplog, ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftp_filesystem.makedirs("/1")
            await ftp_filesystem.makedirs("/1/2/3")
            await ftp_filesystem.makedirs(
                [
                    "/2/3",
                    "/2/3/4",
                    "/2/5",
                ]
            )

    expected_directories = [
        "/1",
        "/1/2",
        "/1/2/3",
        "/2",
        "/2/3",
        "/2/3/4",
        "/2/5",
    ]
    for directory_name in expected_directories:
        message = "Creating a new directory: {0!r}".format(directory_name)
        assert message in caplog.text

    expected_paths = [
        home / directory_name.lstrip("/") for directory_name in expected_directories
    ]
    for path in expected_paths:
        assert path.exists() and path.is_dir()


@pytest.mark.asyncio
async def test_makedirs_no_permission(caplog, ftp_server):
    path = "/test"

    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": ftp_server.host,
            "port": ftp_server.port,
            "credentials": {
                "username": "",
                "password": "",
            },
        }
    )

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs(path)

    message = "Creation of the remote directory did not succeed."
    assert message in caplog.text

    message = "Remote directory setup failed: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_deletes_file(caplog, ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.home) / "text.txt"
    path.write_text("", encoding="utf-8")

    assert path.is_file()

    ftp_path = str(pathlib.Path(ftp_server.root) / "text.txt")
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftp_filesystem.rm(ftp_path)

    message = "Attempting to delete: {0!r}".format(ftp_path)
    assert message in caplog.text

    message = "File deletion succeeded: {0!r}".format(ftp_path)
    assert message in caplog.text


@pytest.mark.asyncio
async def test_remove_accepts_pathlike_file(caplog, ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.home) / "pathlike.txt"
    path.write_text("", encoding="utf-8")

    ftp_path = pathlib.Path(ftp_server.root) / "pathlike.txt"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftp_filesystem.rm(ftp_path)

    assert not path.exists()

    message = "Attempting to delete: {0!r}".format(str(ftp_path))
    assert message in caplog.text

    message = "File deletion succeeded: {0!r}".format(str(ftp_path))
    assert message in caplog.text


@pytest.mark.asyncio
async def test_remove_when_path_does_not_exist(
    caplog, ftp_server, connection_parameters
):
    path = "/test.txt"

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rm(path)

    message = "Could not delete file due to an unexpected FTP server response."
    assert message in caplog.text

    message = "FTP server refused to delete file: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_root_guard(caplog, connection_parameters):
    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(ValueError) as error:
                await ftp_filesystem.rm(path)

    message = "The system does not allow deletion of the root directory."
    assert message in caplog.text

    message = "An attempt to delete the FTP root directory was prevented: {0!r}".format(
        path
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_root_guard_normalized(caplog, connection_parameters):
    path = "/dir/.."
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rm(path)

    message = "The remote path must not contain directory escape sequences."
    assert message in caplog.text

    message = "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_invalid_path(caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rm(path)

        message = "The remote path cannot be of any type other than string."
        assert message in caplog.text

        message = (
            "The remote path must consist of string data."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(error.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rm(path)

        message = "The remote path cannot consist entirely of spaces or tabs."
        assert message in caplog.text

        message = "The remote path must contain at least one non-blank character."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.rm(path)

        message = "The remote path must be absolute and start from the root directory."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_relative_segments(caplog, connection_parameters):
    path = "/root/../escape"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rm(path)

    message = "The remote path must not contain directory escape sequences."
    assert message in caplog.text

    message = "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_trailing_whitespace(ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.home) / "text.txt   "
    path.write_text("", encoding="utf-8")

    ftp_path = str(pathlib.Path(ftp_server.root) / "text.txt   ")
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.rm(ftp_path)

    assert not path.exists()


@pytest.mark.asyncio
async def test_remove_tree_invalid_path(caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree(path)

        message = "The remote path cannot be of any type other than string."
        assert message in caplog.text

        message = (
            "The remote path must consist of string data."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(error.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree(path)

        message = "The remote path cannot be empty or consist solely of whitespace."
        assert message in caplog.text

        message = "The remote path cannot consist entirely of spaces or tabs."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.rmtree(path)

        message = "The remote path must be absolute and start from the root directory."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_relative_segments(caplog, connection_parameters):
    path = "/root/../escape"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree(path)

    message = "The remote path must not contain upward or self-referencing segments."
    assert message in caplog.text

    message = "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_root_guard(caplog, connection_parameters):
    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(ValueError) as error:
                await ftp_filesystem.rmtree(path)

    message = "The root directory cannot be deleted under any circumstances."
    assert message in caplog.text

    message = "Prevented deletion of the FTP root directory: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_trailing_whitespace(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    target_directory = home / "tree  "
    target_directory.mkdir()
    (target_directory / "file.txt").write_text("", encoding="utf-8")
    (target_directory / "subdir").mkdir()
    (target_directory / "subdir" / "nested.txt").write_text("", encoding="utf-8")
    path = str(root / "tree  ")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.rmtree(path)

    assert not target_directory.exists()


@pytest.mark.asyncio
async def test_remove_tree_accepts_pathlike_root(ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    target_directory = home / "pathlike-tree"
    target_directory.mkdir()
    (target_directory / "file.txt").write_text("", encoding="utf-8")
    (target_directory / "subdir").mkdir()
    (target_directory / "subdir" / "nested.txt").write_text("", encoding="utf-8")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.rmtree(root / "pathlike-tree")

    assert not target_directory.exists()


@pytest.mark.asyncio
async def test_remove_tree_file_delete_error_wrapped(
    caplog, connection_parameters, mocker
):
    async def _listdir(_self, path, _ftp=None, **kwargs):
        yield (FTPEntryType.FILE, "{0}/file.txt".format(path))

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)
    mocker.patch(
        "pyftpkit.ftpfs.FTP.delete",
        side_effect=ftplib.error_perm("permission denied"),
    )

    path = "/root"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(path)

    message = "An FTP error occurred while processing directory entries."
    assert message in caplog.text

    message = "Failed to process directory entries for: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_directory_remove_error_wrapped(
    caplog, connection_parameters, mocker
):
    async def _listdir(_self, _path, _ftp=None, **kwargs):
        if False:
            yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)
    mocker.patch(
        "pyftpkit.ftpfs.FTP.rmd", side_effect=ftplib.error_perm("permission denied")
    )

    path = "/root"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(path)

    message = "The directory could not be removed."
    assert message in caplog.text

    message = "Failed to remove {0!r} from the FTP server.".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_unexpected_error_wrapped(
    caplog, connection_parameters, mocker
):
    async def _listdir(*args, **kwargs):
        raise KeyError("unexpected listing parser failure")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/root"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(path)

    message = "An unexpected issue arose during directory entry processing."
    assert message in caplog.text

    message = "Unable to process directory: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_skips_root_on_visit(host, port, username, password, mocker):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 2,
            "max_workers": 1,
        }
    )

    class _FakeFTP:
        def rmd(self, _path):
            return None

        def delete(self, _path):
            return None

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        @contextlib.asynccontextmanager
        async def acquire(self):
            yield fake_ftp

    async def _fake_listdir(self, dirpath, ftp=None):
        if dirpath == "/root":
            yield (FTPEntryType.DIRECTORY, "/")
            return
        if False:
            yield

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "_listdir", types.MethodType(_fake_listdir, ftp_filesystem)
        )

        await ftp_filesystem.rmtree("/root")


@pytest.mark.asyncio
async def test_remove_tree_deletes_directories_and_files(
    caplog,
    ftp_server,
    connection_parameters,
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    base_dir = home / "tree"
    base_dir.mkdir()
    (base_dir / "file.txt").write_text("", encoding="utf-8")
    (base_dir / "subdir").mkdir()
    (base_dir / "subdir" / "nested.txt").write_text("", encoding="utf-8")
    path = str(root / base_dir.relative_to(home))

    expected_directories = [
        root / base_dir.relative_to(home),
        root / base_dir.relative_to(home) / "subdir",
    ]

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftp_filesystem.rmtree(path)

    for directory_path in expected_directories:
        message = "Attempting to remove directory: {0!r}".format(str(directory_path))
        assert message in caplog.text

        message = "Remote directory has been removed: {0!r}".format(str(directory_path))
        assert message in caplog.text

    assert not base_dir.exists()


@pytest.mark.asyncio
async def test_remove_tree_no_permission(caplog, ftp_server):
    home = pathlib.Path(ftp_server.home)
    path = home / "test"
    path.mkdir()
    (path / "file.txt").write_text("", encoding="utf-8")

    ftp_path = str(pathlib.Path(ftp_server.root) / "test")

    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": ftp_server.host,
            "port": ftp_server.port,
            "credentials": {
                "username": "",
                "password": "",
            },
        }
    )

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(ftp_path)

    message = "An FTP error occurred while processing directory entries."
    assert message in caplog.text

    message = "Failed to process directory entries for: '/test'"
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree2_invalid_path(caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree2(path)

        message = "The remote path cannot be anything other than a string."
        assert message in caplog.text

        message = (
            "The remote path may consist exclusively of string data."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(error.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree2(path)

        message = "The remote path must include non-whitespace characters."
        assert message in caplog.text

        message = "The remote path requires at least one non-whitespace character."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.rmtree2(path)

        message = "An absolute path beginning at the root directory is mandatory."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree2_relative_segments(caplog, connection_parameters):
    path = "/root/../escape"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree2(path)

    message = "The remote path must not include relative navigation components."
    assert message in caplog.text

    message = "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
        path, posixpath.curdir, posixpath.pardir
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree2_accepts_pathlike_root(
    host, port, username, password, mocker
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    removed = []
    removed_directories = []
    captured = {}

    class _FakeFTP:
        def rmd(self, path):
            removed_directories.append(path)

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, ftp):
            assert ftp is fake_ftp
            return None

    async def _fake_walk(self, root_path):
        captured["path"] = root_path
        yield ("/root", FTPEntryType.FILE, "/root/file.txt")

    async def _fake_rm(self, path, ftp=None):
        assert ftp is fake_ftp
        removed.append(path)

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )

        await ftp_filesystem.rmtree2(pathlib.Path("/root"))

    assert captured["path"] == "/root"
    assert removed == ["/root/file.txt"]
    assert removed_directories == ["/root"]


@pytest.mark.asyncio
async def test_remove_tree2_rejects_entries_outside_root(
    mocker, connection_parameters, caplog
):
    connection_parameters = connection_parameters.model_copy(
        update={"max_connections": 4, "max_workers": 1, "max_queues_size": 1}
    )

    async def _fake_walk(self, _path):
        yield ("/root", FTPEntryType.FILE, "/other/file.txt")

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return object()

        async def release(self, _ftp):
            return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree2("/root")

    message = "The walk encountered a path outside the expected directory."
    assert message in caplog.text

    message = "Walk yielded a path outside the target root: {0!r}.".format(
        "/other/file.txt"
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree2_root_guard(caplog, connection_parameters):
    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(ValueError) as error:
                await ftp_filesystem.rmtree2(path)

    message = "The root directory is protected against deletion."
    assert message in caplog.text

    message = "The FTP root directory is protected and cannot be removed: {0!r}".format(
        path
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree2_trailing_whitespace(ftp_server, connection_parameters):
    connection_parameters = connection_parameters.model_copy(
        update={"max_connections": 4}
    )
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    target_directory = home / "tree  "
    target_directory.mkdir()
    (target_directory / "file.txt").write_text("", encoding="utf-8")
    (target_directory / "subdir").mkdir()
    (target_directory / "subdir" / "nested.txt").write_text("", encoding="utf-8")
    path = str(root / "tree  ")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.rmtree2(path)

    assert not target_directory.exists()


@pytest.mark.asyncio
async def test_remove_tree2_removes_tree_with_spaces(
    caplog,
    ftp_server,
    connection_parameters,
):
    connection_parameters = connection_parameters.model_copy(
        update={"max_connections": 4}
    )
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    base_directory = home / "space root"
    base_directory.mkdir()
    (base_directory / "file.txt").write_text("", encoding="utf-8")
    space_directory = base_directory / "space dir"
    space_directory.mkdir()
    (space_directory / "with space.txt").write_text("", encoding="utf-8")

    path = str(root / base_directory.relative_to(home))

    expected_directories = [
        root / base_directory.relative_to(home) / "space dir",
    ]

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftp_filesystem.rmtree2(path)

    for directory_path in expected_directories:
        message = "Attempting to remove directory: {0!r}".format(str(directory_path))
        assert message in caplog.text

    message = "Attempting to remove target directory: {0!r}".format(path)
    assert message in caplog.text

    assert not base_directory.exists()


@pytest.mark.asyncio
async def test_remove_tree2_falls_back_with_small_pool(
    host, port, username, password, mocker
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 1,
            "max_workers": 1,
        }
    )
    ftp_filesystem = FTPFileSystem(connection_parameters=connection_parameters)
    rmtree_mock = mocker.AsyncMock()
    mocker.patch.object(ftp_filesystem, "rmtree", rmtree_mock)

    path = "/root"
    await ftp_filesystem.rmtree2(path)

    rmtree_mock.assert_awaited_once_with(path)


@pytest.mark.asyncio
async def test_remove_tree2_reserves_connection_before_walk(
    host, port, username, password, mocker
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    acquired = asyncio.Event()
    released = asyncio.Event()

    class _FakeFTP:
        def rmd(self, _path):
            return None

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            acquired.set()
            return fake_ftp

        async def release(self, ftp):
            assert ftp is fake_ftp
            released.set()

    async def _fake_walk(self, _path):
        assert acquired.is_set()
        yield ("/root", FTPEntryType.FILE, "/root/file.txt")

    async def _fake_rm(self, _path, ftp):
        assert ftp is fake_ftp

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )

        await ftp_filesystem.rmtree2("/root")

    assert released.is_set()


@pytest.mark.asyncio
async def test_remove_tree2_propagates_walk_error(
    host, port, username, password, mocker, caplog
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    released = asyncio.Event()
    fake_ftp = object()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, ftp):
            assert ftp is fake_ftp
            released.set()

    async def _fake_walk(self, _path):
        raise RuntimeError("Walk worker error.") from ftplib.error_perm(
            "permission denied"
        )
        if False:
            yield

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(RuntimeError) as error:
                await ftp_filesystem.rmtree2("/root")

    message = "Walk worker error."
    assert message in str(error.value)
    assert caplog.text == ""
    assert released.is_set()


@pytest.mark.asyncio
async def test_remove_tree2_propagates_rm_error(
    host, port, username, password, mocker, caplog
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    fake_ftp = object()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, _ftp):
            return None

    async def _fake_walk(self, _path):
        yield ("/root", FTPEntryType.FILE, "/root/file.txt")

    async def _fake_rm(self, _path, ftp=None):
        raise FTPError("simulated removal failure")

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError, match="simulated removal failure"):
                await ftp_filesystem.rmtree2("/root")

    assert caplog.text == ""


@pytest.mark.asyncio
async def test_remove_tree2_root_branch_strips_leading_separator(
    host, port, username, password, mocker
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    removals = []

    class _FakeFTP:
        def rmd(self, path):
            removals.append(path)

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, _ftp):
            return None

    async def _fake_walk(self, _path):
        yield ("/", FTPEntryType.DIRECTORY, "/child")

    async def _fake_rm(self, _path, ftp=None):
        return None

    original_normpath = posixpath.normpath

    def _fake_normpath(path):
        if path == posixpath.sep:
            return "not-root"
        return original_normpath(path)

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )
        mocker.patch("pyftpkit.ftpfs.posixpath.normpath", new=_fake_normpath)

        await ftp_filesystem.rmtree2(posixpath.sep)

    assert removals == ["/child"]


@pytest.mark.asyncio
async def test_remove_tree2_skips_empty_and_root_paths(
    host, port, username, password, mocker
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    removals = []

    class _FakeFTP:
        def rmd(self, path):
            removals.append(path)

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, _ftp):
            return None

    class _DummyTrie:
        def insert(self, _path):
            return None

        def __reversed__(self):
            return iter(["", "/"])

    async def _fake_walk(self, _path):
        yield ("/root", FTPEntryType.FILE, "/root/file.txt")

    async def _fake_rm(self, _path, ftp=None):
        return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )
        mocker.patch("pyftpkit.ftpfs.PathTrie", new=_DummyTrie)

        await ftp_filesystem.rmtree2("/root")

    assert removals == ["/root"]


@pytest.mark.asyncio
async def test_remove_tree2_directory_remove_error_wrapped(
    host, port, username, password, mocker, caplog
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )

    class _FakeFTP:
        def rmd(self, _path):
            raise ftplib.error_perm("nope")

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, _ftp):
            return None

    class _DummyTrie:
        def insert(self, _path):
            return None

        def __reversed__(self):
            return iter(["child"])

    async def _fake_walk(self, _path):
        yield ("/root", FTPEntryType.FILE, "/root/file.txt")

    async def _fake_rm(self, _path, ftp=None):
        return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )
        mocker.patch("pyftpkit.ftpfs.PathTrie", new=_DummyTrie)

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree2("/root")

    message = "The directory could not be removed."
    assert message in caplog.text

    message = "Failed to remove {0!r} from the FTP server.".format("/root/child")
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree2_target_directory_remove_error_wrapped(
    host, port, username, password, mocker, caplog
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )

    class _FakeFTP:
        def rmd(self, path):
            if path == "/root":
                raise ftplib.error_perm("nope")
            return None

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, _ftp):
            return None

    async def _fake_walk(self, _path):
        yield ("/root", FTPEntryType.FILE, "/root/file.txt")

    async def _fake_rm(self, _path, ftp=None):
        return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )

        with caplog.at_level(logging.ERROR, logger="pyftpkit"):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree2("/root")

    message = "The target directory could not be removed."
    assert message in caplog.text

    message = "Could not delete directory {0!r} on the FTP server.".format("/root")
    assert message in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "root_path, entry_path, expected_removals",
    [
        ("/root", "/root/subdir", ["/root/subdir", "/root"]),
    ],
)
async def test_remove_tree2_collects_directory_paths(
    host,
    port,
    username,
    password,
    mocker,
    root_path,
    entry_path,
    expected_removals,
):
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 4,
            "max_workers": 1,
        }
    )
    removals = []

    class _FakeFTP:
        def rmd(self, path):
            removals.append(path)

    fake_ftp = _FakeFTP()

    class _FakePool:
        def __init__(self, executor):
            self.executor = executor

        async def get(self):
            return fake_ftp

        async def release(self, _ftp):
            return None

    async def _fake_walk(self, _path):
        yield (root_path, FTPEntryType.DIRECTORY, entry_path)

    async def _fake_rm(self, _path, ftp=None):
        return None

    with ThreadPoolExecutor(max_workers=1) as executor:
        ftp_filesystem = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftp_filesystem, "_pool", _FakePool(executor))
        mocker.patch.object(
            ftp_filesystem, "walk", types.MethodType(_fake_walk, ftp_filesystem)
        )
        mocker.patch.object(
            ftp_filesystem, "_rm", types.MethodType(_fake_rm, ftp_filesystem)
        )

        await ftp_filesystem.rmtree2(root_path)

    assert removals == expected_removals
