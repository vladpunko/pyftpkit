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
def dirtree(ftp_server):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    dirs = []
    nondirs = []

    for _ in range(10):
        dirpath = home / str(uuid.uuid4())
        dirpath.mkdir()
        dirs.append(dirpath)

        for _ in range(10):
            path = dirpath / str(uuid.uuid4())
            path.write_text("")
            nondirs.append(path)

    for _ in range(10):
        parent = random.choice(dirs)

        dirpath = parent / str(uuid.uuid4())
        dirpath.mkdir()
        dirs.append(dirpath)

        for _ in range(10):
            path = parent / str(uuid.uuid4())
            path.write_text("")
            nondirs.append(path)

    return types.SimpleNamespace(
        dirs=dirs,
        ftp_dirs=[root / dirpath.relative_to(home) for dirpath in dirs],
        nondirs=nondirs,
        ftp_nondirs=[root / path.relative_to(home) for path in nondirs],
    )


async def listdir(ftpfs, path):
    dirs = []
    nondirs = []

    async for entry_type, entry_path in ftpfs.listdir(str(path)):
        if entry_type == FTPEntryType.DIRECTORY:
            dirs.append(entry_path)
        else:
            nondirs.append(entry_path)

    return dirs, nondirs


async def drain_async_iterator(iterator):
    async for _ in iterator:
        pass


@pytest.mark.asyncio
async def test_listdir(fs_no_root, caplog, ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    expected_dirs = []
    for _ in range(3):
        name = str(uuid.uuid4())
        dirpath = home / name
        dirpath.mkdir()
        expected_dirs.append(root / name)

    expected_nondirs = []
    for _ in range(3):
        name = str(uuid.uuid4())
        path = home / name
        path.write_text("")
        expected_nondirs.append(root / name)

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            dirs, nondirs = await listdir(ftpfs, root)

            assert collections.Counter(dirs) == collections.Counter(
                map(str, expected_dirs)
            )
            assert collections.Counter(nondirs) == collections.Counter(
                map(str, expected_nondirs)
            )

    message = "Listing remote directory: {0!r}".format(str(root))
    assert message in caplog.text


@pytest.mark.asyncio
async def test_listdir_with_error(
    fs_no_root, caplog, ftp_server, connection_parameters
):
    path = pathlib.Path(ftp_server.root) / "noop"

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await listdir(ftpfs, path)

    message = "The FTP server returned an error during directory listing."
    assert message in caplog.text

    message = f"Failed to list this directory: {str(path)!r}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_listdir_invalid_path(
    fs_no_root, caplog, host, port, username, password, mocker
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
        ftpfs = FTPFileSystem(
            connection_parameters=connection_parameters, executor=executor
        )
        mocker.patch.object(ftpfs, "_pool", mocker.MagicMock(acquire=_acquire))

        path = {}
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await drain_async_iterator(ftpfs.listdir(path))

        message = "The remote path must be a string."
        assert message in caplog.text

        message = (
            "Only string values are permitted for the remote path."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(err.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await drain_async_iterator(ftpfs.listdir(path))

        message = "The remote path must include at least one non-whitespace character."
        assert message in caplog.text

        message = "The remote path must not be empty or whitespace."
        assert message in str(err.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as err:
                await drain_async_iterator(ftpfs.listdir(path))

        message = "The remote path is not absolute and does not start from the root."
        assert message in caplog.text

        message = f"Ambiguous remote path: {path!r}"
        assert message in str(err.value)


@pytest.mark.asyncio
async def test_listdir_trailing_whitespace(
    fs_no_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    dirname = "dir  "
    subdir_name = "subdir"
    file_name = "file.txt"

    target_dir = home / dirname
    target_dir.mkdir()
    (target_dir / subdir_name).mkdir()
    (target_dir / file_name).write_text("")

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        dirs, nondirs = await listdir(ftpfs, str(root / dirname))

    assert set(dirs) == {str(root / dirname / subdir_name)}
    assert set(nondirs) == {str(root / dirname / file_name)}


@pytest.mark.asyncio
async def test_listdir_special_symbols(
    fs_no_root, ftp_server, connection_parameters, filenames_with_symbols
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)

    for index, name in enumerate(filenames_with_symbols):
        (home / name).write_text(f"content # {index!s}")

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        dirs, nondirs = await listdir(ftpfs, root)

    assert dirs == []
    assert set(nondirs) == {str(root / name) for name in filenames_with_symbols}


@pytest.mark.asyncio
async def test_listdir_parse_error_wrapped(
    fs_no_root, caplog, mocker, connection_parameters
):
    async def _listdir(*args, **kwargs):
        raise KeyError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await drain_async_iterator(ftpfs.listdir(path))

    message = "Failed to parse directory listing from the FTP server."
    assert message in caplog.text

    message = f"Failed to parse directory listing for: {path!r}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_listdir_bad_entry(fs_no_root, mocker, ftp_server, connection_parameters):
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

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        dirs, nondirs = await listdir(ftpfs, root)

    assert dirs == [str(root / "dir")]
    assert nondirs == [
        str(root / "text.txt"),
        str(root / "symlink"),
    ]


@pytest.mark.asyncio
async def test_listdir_name_with_symlink_token_preserved(
    fs_no_root, mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    entries = [
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 name -> target.txt",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        dirs, nondirs = await listdir(ftpfs, root)

    assert dirs == []
    assert nondirs == [str(root / "name -> target.txt")]


@pytest.mark.asyncio
async def test_walk(fs_no_root, ftp_server, dirtree, connection_parameters):
    root = pathlib.Path(ftp_server.root)
    collected_dirs = []
    collected_nondirs = []

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        async for _, entry_type, entry_path in ftpfs.walk(str(root)):
            if entry_type == FTPEntryType.DIRECTORY:
                collected_dirs.append(entry_path)
            else:
                collected_nondirs.append(entry_path)

    assert len(collected_dirs) == len(dirtree.ftp_dirs)
    assert len(collected_nondirs) == len(dirtree.ftp_nondirs)

    assert set(collected_dirs) == {str(path) for path in dirtree.ftp_dirs}
    assert set(collected_nondirs) == {str(path) for path in dirtree.ftp_nondirs}


@pytest.mark.asyncio
async def test_walk_no_permission(
    fs_no_root, caplog, ftp_server, connection_parameters, mocker
):
    root = pathlib.Path(ftp_server.root)

    async def _listdir(*args, **kwargs):
        raise PermissionError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError) as err:
                async for _, _, _ in ftpfs.walk(str(root)):
                    pass

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text

    message = "Walk worker error."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_walk_invalid_path(fs_no_root, caplog, connection_parameters):
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        path = {}
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await drain_async_iterator(ftpfs.walk(path))

        message = "The remote path must be a string."
        assert message in caplog.text

        message = (
            "Only string values are permitted for the remote path."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(err.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await drain_async_iterator(ftpfs.walk(path))

        message = "The remote path must include at least one non-whitespace character."
        assert message in caplog.text

        message = "The remote path must not be empty or whitespace."
        assert message in str(err.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as err:
                await drain_async_iterator(ftpfs.walk(path))

        message = "The remote path is not absolute and does not start from the root."
        assert message in caplog.text

        message = f"Ambiguous remote path: {path!r}"
        assert message in str(err.value)


@pytest.mark.asyncio
async def test_walk_trailing_whitespace(fs_no_root, ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    dirname = "dir  "
    subdir_name = "subdir"
    file_name = "file.txt"
    nested_name = "nested.txt"

    root_dir = home / dirname
    root_dir.mkdir()
    (root_dir / file_name).write_text("")
    subdir = root_dir / subdir_name
    subdir.mkdir()
    (subdir / nested_name).write_text("")

    collected_dirs = []
    collected_nondirs = []

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        async for _, entry_type, entry_path in ftpfs.walk(str(root / dirname)):
            if entry_type == FTPEntryType.DIRECTORY:
                collected_dirs.append(entry_path)
            else:
                collected_nondirs.append(entry_path)

    expected_dir = str(root / dirname / subdir_name)
    expected_files = {
        str(root / dirname / file_name),
        str(root / dirname / subdir_name / nested_name),
    }

    assert set(collected_dirs) == {expected_dir}
    assert set(collected_nondirs) == expected_files


@pytest.mark.asyncio
async def test_walk_queue_full_does_not_hang(fs_no_root, mocker, connection_parameters):
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
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        await asyncio.wait_for(drain_async_iterator(ftpfs.walk(path)), timeout=2)


@pytest.mark.asyncio
async def test_walk_was_cancelled(fs_no_root, connection_parameters):
    path = "/"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        task = asyncio.create_task(drain_async_iterator(ftpfs.walk(path)))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_walk_worker_error_propagates(fs_no_root, mocker, connection_parameters):
    async def delayed_error(*args, **kwargs):
        await asyncio.sleep(0.05)
        raise RuntimeError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=delayed_error)

    path = "/"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with pytest.raises(RuntimeError) as err:
            await drain_async_iterator(ftpfs.walk(path))

    assert "Walk worker error." in str(err.value)


@pytest.mark.asyncio
async def test_walk_stop_event_breaks_worker(fs_no_root, connection_parameters, mocker):
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
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        await drain_async_iterator(ftpfs.walk(path))


@pytest.mark.asyncio
async def test_walk_stop_event_breaks_main_loop(
    fs_no_root, connection_parameters, mocker
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
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        mocker.patch("pyftpkit.ftpfs.asyncio.Queue", new=QueueWrapper)
        mocker.patch("pyftpkit.ftpfs.asyncio.wait_for", new=_slow_wait_for)
        mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

        await drain_async_iterator(ftpfs.walk(path))


@pytest.mark.asyncio
async def test_walk_drain_output_queue(
    fs_no_root, mocker, ftp_server, connection_parameters
):
    root = pathlib.Path(ftp_server.root)
    dirpath = pathlib.Path(ftp_server.home) / "test"
    dirpath.mkdir()
    path = dirpath / "text.txt"
    path.write_text("")

    expected_dir = str(root / "test")
    expected_output = (
        expected_dir,
        FTPEntryType.FILE,
        str(root / "test" / "text.txt"),
    )

    original_listdir = FTPFileSystem._listdir

    async def _listdir(self, path, ftp):
        if os.path.basename(str(path)) == "test":
            await asyncio.sleep(random.uniform(0.1, 0.5))  # short delay

        async for entry in original_listdir(self, path, ftp):
            yield entry

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    output = []

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        root_str = str(root)

        async for dirpath_out, entry_type, entry_path in ftpfs.walk(root_str):
            output.append((dirpath_out, entry_type, entry_path))
            if dirpath_out == root_str:
                break

        async for dirpath_out, entry_type, entry_path in ftpfs.walk(root_str):
            output.append((dirpath_out, entry_type, entry_path))

    drained_item = next((item for item in output if item[0] == expected_dir), None)
    assert drained_item is not None
    assert drained_item == expected_output


@pytest.mark.asyncio
async def test_makedirs_invalid_paths(fs_no_root, caplog, connection_parameters):
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        paths = object()
        with caplog.at_level(logging.ERROR):
            with pytest.raises(TypeError) as err:
                await ftpfs.makedirs(paths)

        message = "Expected paths to be a collection of strings."
        assert message in caplog.text

        message = (
            "Invalid type for paths: expected an iterable of path strings."
            "\nAn unsupported type was provided for paths: {0!s}".format(
                type(paths).__name__
            )
        )
        assert message in str(err.value)

        path = {}
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await ftpfs.makedirs([path])

        message = "The path must be provided as a string value."
        assert message in caplog.text

        message = (
            "The path must be defined using string data."
            "\nThe path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(err.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await ftpfs.makedirs([path])

        message = "The path must contain at least one non-blank character."
        assert message in caplog.text

        message = "The path cannot be blank or whitespace-only."
        assert message in str(err.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as err:
                await ftpfs.makedirs([path])

        message = "The path is relative rather than starting at the root."
        assert message in caplog.text

        message = f"Ambiguous path: {path!r}"
        assert message in str(err.value)


@pytest.mark.asyncio
async def test_makedirs_trailing_whitespace(
    fs_no_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        await ftpfs.makedirs(["/a/b   ", "/c/d   "])

    assert (home / "a").is_dir()
    assert (home / "a" / "b   ").is_dir()
    assert (home / "c").is_dir()
    assert (home / "c" / "d   ").is_dir()


@pytest.mark.asyncio
async def test_makedirs_cwd_non_perm_error(
    fs_no_root, caplog, mocker, connection_parameters
):
    mocker.patch("pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_temp("tmp"))

    path = "/test"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.makedirs([path])

    message = "Failed to validate the remote directory."
    assert message in caplog.text

    message = f"Failed to access remote directory: {path!r}."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_makedirs_mkd_perm_error_cwd_fails(
    fs_no_root, caplog, mocker, connection_parameters
):
    mocker.patch("pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_perm("perm"))
    mocker.patch("pyftpkit.ftpfs.FTP.mkd", side_effect=ftplib.error_perm("perm"))

    path = "/test"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.makedirs([path])

    message = "Creation of the remote directory did not succeed."
    assert message in caplog.text

    message = f"Remote directory setup failed: {path!r}."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_makedirs_mkd_non_perm_error_cwd_fails(
    fs_no_root, caplog, mocker, connection_parameters
):
    mocker.patch("pyftpkit.ftpfs.FTP.cwd", side_effect=ftplib.error_perm("perm"))
    mocker.patch("pyftpkit.ftpfs.FTP.mkd", side_effect=ftplib.error_temp("tmp"))

    path = "/test"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.makedirs([path])

    message = "The remote directory could not be initialized."
    assert message in caplog.text

    message = f"FTP server directory creation failed: {path!r}."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_makedirs(fs_no_root, caplog, ftp_server, connection_parameters):
    home = pathlib.Path(ftp_server.home)
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftpfs.makedirs("/1")
            await ftpfs.makedirs("/1/2/3")
            await ftpfs.makedirs(
                [
                    "/2/3",
                    "/2/3/4",
                    "/2/5",
                ]
            )

    expected_dirs = [
        "/1",
        "/1/2",
        "/1/2/3",
        "/2",
        "/2/3",
        "/2/3/4",
        "/2/5",
    ]
    for dirname in expected_dirs:
        message = f"Creating a new directory: {dirname!r}"
        assert message in caplog.text

    expected_paths = [home / dirname.lstrip("/") for dirname in expected_dirs]
    for path in expected_paths:
        assert path.exists() and path.is_dir()


@pytest.mark.asyncio
async def test_makedirs_no_permission(fs_no_root, caplog, ftp_server):
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

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.makedirs(path)

    message = "Creation of the remote directory did not succeed."
    assert message in caplog.text

    message = f"Remote directory setup failed: {path!r}."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rm(fs_no_root, caplog, ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.home) / "text.txt"
    path.write_text("")

    assert path.is_file()

    ftp_path = str(pathlib.Path(ftp_server.root) / "text.txt")
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftpfs.rm(ftp_path)

    message = f"Attempting to delete: {ftp_path!r}"
    assert message in caplog.text

    message = f"File deletion succeeded: {ftp_path!r}"
    assert message in caplog.text


@pytest.mark.asyncio
async def test_rm_not_exists(fs_no_root, caplog, ftp_server, connection_parameters):
    path = "/test.txt"

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.rm(path)

    message = "Could not delete file due to an unexpected FTP server response."
    assert message in caplog.text

    message = f"FTP server refused to delete file: {path!r}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rm_root_guard(fs_no_root, caplog, connection_parameters):
    path = "/"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ValueError) as err:
                await ftpfs.rm(path)

    message = "Attempting to remove the root directory is disallowed."
    assert message in caplog.text

    message = f"Attempt to remove FTP root directory has been prevented: {path!r}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rm_invalid_path(fs_no_root, caplog, connection_parameters):
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        path = {}
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await ftpfs.rm(path)

        message = "The remote path cannot be of any type other than string."
        assert message in caplog.text

        message = (
            "The remote path must consist of string data."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(err.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await ftpfs.rm(path)

        message = "The remote path cannot consist entirely of spaces or tabs."
        assert message in caplog.text

        message = "The remote path must contain at least one non-blank character."
        assert message in str(err.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as err:
                await ftpfs.rm(path)

        message = "The remote path must be absolute and start from the root directory."
        assert message in caplog.text

        message = f"Ambiguous remote path: {path!r}"
        assert message in str(err.value)


@pytest.mark.asyncio
async def test_rm_trailing_whitespace(fs_no_root, ftp_server, connection_parameters):
    path = pathlib.Path(ftp_server.home) / "text.txt   "
    path.write_text("")

    ftp_path = str(pathlib.Path(ftp_server.root) / "text.txt   ")
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        await ftpfs.rm(ftp_path)

    assert not path.exists()


@pytest.mark.asyncio
async def test_rmtree_invalid_path(fs_no_root, caplog, connection_parameters):
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        path = {}
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await ftpfs.rmtree(path)

        message = "The remote path cannot be of any type other than string."
        assert message in caplog.text

        message = (
            "The remote path must consist of string data."
            "\nThe remote path {0!r} has type: {1!s}".format(path, type(path).__name__)
        )
        assert message in str(err.value)

        path = "\t\t"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathError) as err:
                await ftpfs.rmtree(path)

        message = "The remote path cannot be empty or consist solely of whitespace."
        assert message in caplog.text

        message = "The remote path cannot consist entirely of spaces or tabs."
        assert message in str(err.value)

        path = "not/from/root"
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPPathNotAbsoluteError) as err:
                await ftpfs.rmtree(path)

        message = "The remote path must be absolute and start from the root directory."
        assert message in caplog.text

        message = f"Ambiguous remote path: {path!r}"
        assert message in str(err.value)


@pytest.mark.asyncio
async def test_rmtree_trailing_whitespace(
    fs_no_root, ftp_server, connection_parameters
):
    home = pathlib.Path(ftp_server.home)
    root = pathlib.Path(ftp_server.root)
    target_dir = home / "tree  "
    target_dir.mkdir()
    (target_dir / "file.txt").write_text("")
    (target_dir / "subdir").mkdir()
    (target_dir / "subdir" / "nested.txt").write_text("")
    path = str(root / "tree  ")

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        await ftpfs.rmtree(path)

    assert not target_dir.exists()


@pytest.mark.asyncio
async def test_rmtree_file_delete_error_wrapped(
    fs_no_root, caplog, connection_parameters, mocker
):
    async def _listdir(_self, path, _ftp=None, **kwargs):
        yield (FTPEntryType.FILE, f"{path}/file.txt")

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)
    mocker.patch("pyftpkit.ftpfs.FTP.delete", side_effect=ftplib.error_perm("perm"))

    path = "/root"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.rmtree(path)

    message = "An FTP error occurred while processing directory entries."
    assert message in caplog.text

    message = f"Failed to process directory entries for: {path!r}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rmtree_dir_remove_error_wrapped(
    fs_no_root, caplog, connection_parameters, mocker
):
    async def _listdir(_self, _path, _ftp=None, **kwargs):
        if False:
            yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)
    mocker.patch("pyftpkit.ftpfs.FTP.rmd", side_effect=ftplib.error_perm("perm"))

    path = "/root"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.rmtree(path)

    message = "The directory could not be removed."
    assert message in caplog.text

    message = f"Failed to remove {path!r} from the FTP server."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rmtree_unexpected_error_wrapped(
    fs_no_root, caplog, connection_parameters, mocker
):
    async def _listdir(*args, **kwargs):
        raise KeyError("error")
        yield

    mocker.patch("pyftpkit.ftpfs.FTPFileSystem._listdir", new=_listdir)

    path = "/root"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.rmtree(path)

    message = "An unexpected issue arose during directory entry processing."
    assert message in caplog.text

    message = f"Unable to process directory: {path!r}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rmtree(fs_no_root, caplog, ftp_server, dirtree, connection_parameters):
    path = "/"

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftpfs.rmtree(path)

    for dirpath in dirtree.ftp_dirs:
        message = f"Attempting to remove: {str(dirpath)!r}"
        assert message in caplog.text

        message = f"Remote directory has been removed: {str(dirpath)!r}"
        assert message in caplog.text

    assert not list(pathlib.Path(ftp_server.home).iterdir())


@pytest.mark.asyncio
async def test_rmtree_no_permission(fs_no_root, caplog, ftp_server):
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

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.rmtree(ftp_path)

    message = "An FTP error occurred while processing directory entries."
    assert message in caplog.text

    message = "Failed to process directory entries for: '/test'"
    assert message in str(err.value)
