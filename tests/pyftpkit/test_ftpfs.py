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
from pyftpkit.ftpfs import FTPEntryType, FTPFileSystem


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
            path.write_text("")
            non_directories.append(path)

    for _ in range(10):
        parent = random.choice(directories)

        directory_path = parent / str(uuid.uuid4())
        directory_path.mkdir()
        directories.append(directory_path)

        for _ in range(10):
            path = parent / str(uuid.uuid4())
            path.write_text("")
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
async def test_list_directory(
    fs_without_root, caplog, ftp_server, connection_parameters
):
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
        path.write_text("")
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
async def test_list_directory_with_error(
    fs_without_root, caplog, ftp_server, connection_parameters
):
    path = pathlib.Path(ftp_server.root) / "noop"

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await list_directory(ftp_filesystem, path)

    message = "The FTP server returned an error during directory listing."
    assert message in caplog.text

    message = "Failed to list this directory: {0!r}".format(str(path))
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_invalid_path(
    fs_without_root, caplog, host, port, username, password, mocker
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
        with caplog.at_level(logging.ERROR):
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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

        message = "The remote path must include at least one non-whitespace character."
        assert message in caplog.text

        message = "The remote path must not be empty or whitespace."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

        message = "The remote path is not absolute and does not start from the root."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_trailing_whitespace(
    fs_without_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    directory_name = "dir  "
    subdirectory_name = "subdir"
    file_name = "file.txt"

    target_directory = home / directory_name
    target_directory.mkdir()
    (target_directory / subdirectory_name).mkdir()
    (target_directory / file_name).write_text("")

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
    fs_without_root, ftp_server, connection_parameters, filenames_with_symbols
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    for index, name in enumerate(filenames_with_symbols):
        (home / name).write_text("content # {0!s}".format(index))

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        directories, non_directories = await list_directory(ftp_filesystem, root)

    assert directories == []
    assert set(non_directories) == {str(root / name) for name in filenames_with_symbols}


@pytest.mark.asyncio
async def test_list_directory_parse_error_wrapped(
    fs_without_root, caplog, mocker, connection_parameters
):
    async def _listdir(*args, **kwargs):
        raise KeyError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await drain_async_iterator(ftp_filesystem.listdir(path))

    message = "Failed to parse directory listing from the FTP server."
    assert message in caplog.text

    message = "Failed to parse directory listing for: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_list_directory_bad_entry(
    fs_without_root, mocker, ftp_server, connection_parameters
):
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
    fs_without_root, mocker, ftp_server, connection_parameters
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
async def test_walk(fs_without_root, ftp_server, directory_tree, connection_parameters):
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
async def test_walk_no_permission(
    fs_without_root,
    caplog,
    ftp_server,
    connection_parameters,
    mocker,
):
    root = pathlib.Path(ftp_server.root)

    async def _listdir(*args, **kwargs):
        raise PermissionError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError) as error:
                async for _, _, _ in ftp_filesystem.walk(str(root)):
                    pass

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text

    message = "Walk worker error."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_walk_invalid_path(fs_without_root, caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR):
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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

        message = "The remote path must include at least one non-whitespace character."
        assert message in caplog.text

        message = "The remote path must not be empty or whitespace."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await drain_async_iterator(ftp_filesystem.walk(path))

        message = "The remote path is not absolute and does not start from the root."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_walk_trailing_whitespace(
    fs_without_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    directory_name = "dir  "
    subdirectory_name = "subdir"
    file_name = "file.txt"
    nested_name = "nested.txt"

    root_directory = home / directory_name
    root_directory.mkdir()
    (root_directory / file_name).write_text("")
    subdirectory = root_directory / subdirectory_name
    subdirectory.mkdir()
    (subdirectory / nested_name).write_text("")

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
async def test_walk_queue_full_does_not_hang(
    fs_without_root, mocker, connection_parameters
):
    class QueueWrapper(asyncio.Queue):
        def __init__(self, *args, raise_on_put_nowait=True, **kwargs):
            super().__init__(*args, **kwargs)

            self._raise_on_put_nowait = raise_on_put_nowait

        def put_nowait(self, item):
            if self._raise_on_put_nowait and isinstance(item, Exception):
                raise asyncio.QueueFull()

            return super().put_nowait(item)

    def queue_factory(*args, **kwargs):
        return QueueWrapper(*args, **kwargs)

    async def _listdir(*args, **kwargs):
        raise RuntimeError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.asyncio.Queue", side_effect=queue_factory)
    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await asyncio.wait_for(
            drain_async_iterator(ftp_filesystem.walk(path)), timeout=2
        )


@pytest.mark.asyncio
async def test_walk_was_cancelled(fs_without_root, connection_parameters):
    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        task = asyncio.create_task(drain_async_iterator(ftp_filesystem.walk(path)))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_walk_worker_error_propagates(
    fs_without_root, mocker, connection_parameters
):
    async def delayed_error(*args, **kwargs):
        await asyncio.sleep(0.05)
        raise RuntimeError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=delayed_error)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with pytest.raises(RuntimeError) as error:
            await drain_async_iterator(ftp_filesystem.walk(path))

    assert "Walk worker error." in str(error.value)


@pytest.mark.asyncio
async def test_walk_stop_event_breaks_worker(
    fs_without_root, connection_parameters, mocker
):
    class AlwaysSetEvent(asyncio.Event):
        def is_set(self):
            return True

    async def _listdir(*args, **kwargs):
        await asyncio.sleep(0.2)
        return
        yield

    mocker.patch("pyftpkit.ftpfs.asyncio.Event", new=AlwaysSetEvent)
    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await drain_async_iterator(ftp_filesystem.walk(path))


@pytest.mark.asyncio
async def test_walk_stop_event_breaks_main_loop(
    fs_without_root, connection_parameters, mocker
):
    class QueueWrapper(asyncio.Queue):
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

    async def _listdir(*args, path, **kwargs):
        if path == "/":
            yield (FTPEntryType.DIRECTORY, "/subdir1")
            yield (FTPEntryType.DIRECTORY, "/subdir2")
            await asyncio.sleep(0.05)
            return
        raise RuntimeError("error")
        yield

    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", new=QueueWrapper)
        mocker.patch("pyftpkit.ftpfs.asyncio.wait_for", new=_slow_wait_for)
        mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

        await drain_async_iterator(ftp_filesystem.walk(path))


@pytest.mark.asyncio
async def test_walk_drain_output_queue(
    fs_without_root, mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    directory_path = pathlib.Path(ftp_server.home) / "test"
    directory_path.mkdir()
    path = directory_path / "text.txt"
    path.write_text("")

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
async def test_makedirs_invalid_paths(fs_without_root, caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        paths = object()
        with caplog.at_level(logging.ERROR):
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
        with caplog.at_level(logging.ERROR):
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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.makedirs([path])

        message = "The path must contain at least one non-blank character."
        assert message in caplog.text

        message = "The path cannot be blank or whitespace-only."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.makedirs([path])

        message = "The path is relative rather than starting at the root."
        assert message in caplog.text

        message = "Ambiguous path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_trailing_whitespace(
    fs_without_root, ftp_server, connection_parameters
):
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
    fs_without_root, caplog, mocker, connection_parameters
):
    mocker.patch("pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_temp("tmp"))

    path = "/test"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs([path])

    message = "Failed to validate the remote directory."
    assert message in caplog.text

    message = "Failed to access remote directory: {0!r}.".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_make_directory_permission_error_current_working_directory_fails(
    fs_without_root, caplog, mocker, connection_parameters
):
    mocker.patch("pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_perm("perm"))
    mocker.patch("pyftpkit.ftpfs.FTP.mkd", side_effect=ftplib.error_perm("perm"))

    path = "/test"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs([path])

    message = "Creation of the remote directory did not succeed."
    assert message in caplog.text

    message = "Remote directory setup failed: {0!r}.".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs_make_directory_non_permission_error_current_directory_fails(
    fs_without_root, caplog, mocker, connection_parameters
):
    mocker.patch("pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_perm("perm"))
    mocker.patch("pyftpkit.ftpfs.FTP.mkd", side_effect=ftplib.error_temp("tmp"))

    path = "/test"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs([path])

    message = "The remote directory could not be initialized."
    assert message in caplog.text

    message = "FTP server directory creation failed: {0!r}.".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_makedirs(fs_without_root, caplog, ftp_server, connection_parameters):
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
async def test_makedirs_no_permission(fs_without_root, caplog, ftp_server):
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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.makedirs(path)

    message = "Creation of the remote directory did not succeed."
    assert message in caplog.text

    message = "Remote directory setup failed: {0!r}.".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove(fs_without_root, caplog, ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.home) / "text.txt"
    path.write_text("")

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
async def test_remove_when_path_does_not_exist(
    fs_without_root, caplog, ftp_server, connection_parameters
):
    path = "/test.txt"

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rm(path)

    message = "Could not delete file due to an unexpected FTP server response."
    assert message in caplog.text

    message = "FTP server refused to delete file: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_root_guard(fs_without_root, caplog, connection_parameters):
    path = "/"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError) as error:
                await ftp_filesystem.rm(path)

    message = "Attempting to remove the root directory is disallowed."
    assert message in caplog.text

    message = "Attempt to remove FTP root directory has been prevented: {0!r}".format(
        path
    )
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_invalid_path(fs_without_root, caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR):
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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rm(path)

        message = "The remote path cannot consist entirely of spaces or tabs."
        assert message in caplog.text

        message = "The remote path must contain at least one non-blank character."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.rm(path)

        message = "The remote path must be absolute and start from the root directory."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_trailing_whitespace(
    fs_without_root, ftp_server, connection_parameters
):
    path = pathlib.Path(ftp_server.home) / "text.txt   "
    path.write_text("")

    ftp_path = str(pathlib.Path(ftp_server.root) / "text.txt   ")
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.rm(ftp_path)

    assert not path.exists()


@pytest.mark.asyncio
async def test_remove_tree_invalid_path(fs_without_root, caplog, connection_parameters):
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        path = {}
        with caplog.at_level(logging.ERROR):
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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as error:
                await ftp_filesystem.rmtree(path)

        message = "The remote path cannot be empty or consist solely of whitespace."
        assert message in caplog.text

        message = "The remote path cannot consist entirely of spaces or tabs."
        assert message in str(error.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as error:
                await ftp_filesystem.rmtree(path)

        message = "The remote path must be absolute and start from the root directory."
        assert message in caplog.text

        message = "Ambiguous remote path: {0!r}".format(path)
        assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_trailing_whitespace(
    fs_without_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    target_directory = home / "tree  "
    target_directory.mkdir()
    (target_directory / "file.txt").write_text("")
    (target_directory / "subdir").mkdir()
    (target_directory / "subdir" / "nested.txt").write_text("")
    path = str(root / "tree  ")

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        await ftp_filesystem.rmtree(path)

    assert not target_directory.exists()


@pytest.mark.asyncio
async def test_remove_tree_file_delete_error_wrapped(
    fs_without_root, caplog, connection_parameters, mocker
):
    async def _listdir(_self, path, _ftp=None, **kwargs):
        yield (FTPEntryType.FILE, "{0}/file.txt".format(path))

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)
    mocker.patch("pyftpkit.ftpfs.FTP.delete", side_effect=ftplib.error_perm("perm"))

    path = "/root"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(path)

    message = "An FTP error occurred while processing directory entries."
    assert message in caplog.text

    message = "Failed to process directory entries for: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_directory_remove_error_wrapped(
    fs_without_root, caplog, connection_parameters, mocker
):
    async def _listdir(_self, _path, _ftp=None, **kwargs):
        if False:
            yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)
    mocker.patch("pyftpkit.ftpfs.FTP.rmd", side_effect=ftplib.error_perm("perm"))

    path = "/root"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(path)

    message = "The directory could not be removed."
    assert message in caplog.text

    message = "Failed to remove {0!r} from the FTP server.".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree_unexpected_error_wrapped(
    fs_without_root, caplog, connection_parameters, mocker
):
    async def _listdir(*args, **kwargs):
        raise KeyError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/root"
    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(path)

    message = "An unexpected issue arose during directory entry processing."
    assert message in caplog.text

    message = "Unable to process directory: {0!r}".format(path)
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_remove_tree(
    fs_without_root,
    caplog,
    ftp_server,
    directory_tree,
    connection_parameters,
):
    path = "/"

    async with FTPFileSystem(
        connection_parameters=connection_parameters
    ) as ftp_filesystem:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftp_filesystem.rmtree(path)

    for directory_path in directory_tree.ftp_directories:
        message = "Attempting to remove: {0!r}".format(str(directory_path))
        assert message in caplog.text

        message = "Remote directory has been removed: {0!r}".format(str(directory_path))
        assert message in caplog.text

    assert not list(pathlib.Path(ftp_server.home).iterdir())


@pytest.mark.asyncio
async def test_remove_tree_no_permission(fs_without_root, caplog, ftp_server):
    home = pathlib.Path(ftp_server.home)
    path = home / "test"
    path.mkdir()
    (path / "file.txt").write_text("")

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
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as error:
                await ftp_filesystem.rmtree(ftp_path)

    message = "An FTP error occurred while processing directory entries."
    assert message in caplog.text

    message = "Failed to process directory entries for: '/test'"
    assert message in str(error.value)
