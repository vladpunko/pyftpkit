# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio
import logging
import os
import pathlib
import random
import types
import uuid

import pytest

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError
from pyftpkit.ftpfs import FTPFileSystem


@pytest.fixture
def connection_parameters(username, password, ftp_server):
    return ConnectionParameters.model_validate(
        {
            "host": ftp_server.host,
            "port": ftp_server.port,
            "credentials": {
                "username": username,
                "password": password,
            },
            "max_connections": 2,
            "max_workers": 4,
        }
    )


@pytest.fixture
def dirtree(ftp_server):
    dirs = []
    nondirs = []

    for _ in range(10):
        dirpath = ftp_server.home / str(uuid.uuid4())
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
        ftp_dirs=[
            ftp_server.root / dirpath.relative_to(ftp_server.home) for dirpath in dirs
        ],
        nondirs=nondirs,
        ftp_nondirs=[
            ftp_server.root / path.relative_to(ftp_server.home) for path in nondirs
        ],
    )


@pytest.mark.asyncio
async def test_listdir(fs, caplog, ftp_server, connection_parameters):
    dirs = []
    for _ in range(3):
        name = str(uuid.uuid4())
        dirpath = ftp_server.home / name
        dirpath.mkdir()
        dirs.append(ftp_server.root / name)

    nondirs = []
    for _ in range(3):
        name = str(uuid.uuid4())
        path = ftp_server.home / name
        path.write_text("")
        nondirs.append(ftp_server.root / name)

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            listed_dir, listed_nondirs = await ftpfs.listdir(ftp_server.root)

            assert set(listed_dir) == set(dirs)
            assert set(listed_nondirs) == set(nondirs)

    message = "Listing remote directory: {0!s}".format(ftp_server.root)
    assert message in caplog.text


@pytest.mark.asyncio
async def test_listdir_with_error(caplog, ftp_server, connection_parameters):
    path = ftp_server.root / "not-found"

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.listdir(path)

    message = "The FTP server returned an error during directory listing."
    assert message in caplog.text

    message = f"Failed to list this directory: {path!s}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_listdir_bad_entry(mocker, ftp_server, connection_parameters):
    entries = [
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:12 dir",
        "-rw-r--r--   1 owner group         512 Oct 27 09:15 text.txt",
        "lrwxrwxrwx   1 owner group          11 Oct 27 09:17 symlink -> test.txt",
        "",
        "error",
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:20 .",
        "drwxr-xr-x   2 owner group        4096 Oct 27 09:21 ..",
    ]
    retrlines_mock = mocker.patch("pyftpkit.ftpfs.FTP.retrlines")
    retrlines_mock.side_effect = lambda _, callback: list(map(callback, entries))

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        dirs, nondirs = await ftpfs.listdir(ftp_server.root)

    assert dirs == [
        ftp_server.root / "dir",
    ]
    assert nondirs == [
        ftp_server.root / "text.txt",
        ftp_server.root / "symlink",
    ]


@pytest.mark.asyncio
async def test_walk(ftp_server, dirtree, connection_parameters):
    collected_dirs = []
    collected_nondirs = []

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        async for _, dirs, nondirs in ftpfs.walk(ftp_server.root):
            for dirpath in dirs:
                collected_dirs.append(dirpath)

            for path in nondirs:
                collected_nondirs.append(path)

    assert len(collected_dirs) == len(dirtree.ftp_dirs)
    assert len(collected_nondirs) == len(dirtree.ftp_nondirs)

    assert set(collected_dirs) == set(dirtree.ftp_dirs)
    assert set(collected_nondirs) == set(dirtree.ftp_nondirs)


@pytest.mark.asyncio
async def test_walk_no_permission(caplog, ftp_server, dirtree, connection_parameters):
    os.chmod(random.choice(dirtree.dirs), 0o000)

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(RuntimeError) as err:
                async for _, _, _ in ftpfs.walk(ftp_server.root):
                    pass

    message = "An unexpected error occurred at this program runtime."
    assert message in caplog.text

    message = "Walk worker error."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_walk_drain_output_queue(mocker, ftp_server, connection_parameters):
    dirpath = ftp_server.home / "test"
    dirpath.mkdir()
    path = dirpath / "text.txt"
    path.write_text("")

    expected_output = (
        pathlib.Path(ftp_server.root) / "test",
        [],
        [pathlib.Path(ftp_server.root) / "test" / "text.txt"],
    )

    original_listdir = FTPFileSystem._listdir

    async def listdir(self, path, ftp):
        if path.name == "test":
            await asyncio.sleep(random.uniform(0.1, 0.5))  # short delay
        return await original_listdir(self, path, ftp)

    mocker.patch(
        "pyftpkit.ftpfs.FTPFileSystem._listdir",
        new=listdir,
    )

    output = []

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        async for dirpath_out, dirs_out, nondirs_out in ftpfs.walk(ftp_server.root):
            output.append((dirpath_out, dirs_out, nondirs_out))
            if dirpath_out.name == "":
                break

        async for dirpath_out, dirs_out, nondirs_out in ftpfs.walk(ftp_server.root):
            output.append((dirpath_out, dirs_out, nondirs_out))

    drained_item = next((item for item in output if item[0].name == "test"), None)
    assert drained_item is not None
    assert drained_item == expected_output


@pytest.mark.asyncio
async def test_makedirs(caplog, ftp_server, connection_parameters):
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
        message = f"Creating a new directory: {dirname!s}"
        assert message in caplog.text

    expected_paths = [
        ftp_server.home / dirname.lstrip("/") for dirname in expected_dirs
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

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.makedirs("/test")

    message = "Remote directory could not be created."
    assert message in caplog.text

    message = f"Unable to create directory on FTP server: {path!s}."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rm(caplog, ftp_server, connection_parameters):
    path = ftp_server.home / "text.txt"
    path.write_text("")

    assert path.is_file()

    ftp_path = ftp_server.root / "text.txt"
    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftpfs.rm(ftp_path)

    message = f"Attempting to delete: {ftp_path!s}"
    assert message in caplog.text

    message = f"File deletion succeeded: {ftp_path!s}"
    assert message in caplog.text


@pytest.mark.asyncio
async def test_rm_not_exists(caplog, ftp_server, connection_parameters):
    path = "/test.txt"

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.ERROR):
            with pytest.raises(FTPError) as err:
                await ftpfs.rm(path)

    message = "Could not delete file due to an unexpected FTP server response."
    assert message in caplog.text

    message = f"FTP server refused to delete file: {path!s}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_rmtree(caplog, ftp_server, dirtree, connection_parameters):
    path = "/"

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
            await ftpfs.rmtree(path)

    message = f"Deleting {len(dirtree.ftp_nondirs)} files from the FTP server..."
    assert message in caplog.text

    message = f"Deleting {len(dirtree.ftp_dirs)+1} directories..."
    assert message in caplog.text

    for dirpath in dirtree.ftp_dirs:
        message = f"Attempting to delete: {dirpath!s}"
        assert message in caplog.text

        message = f"Remote directory removed: {dirpath!s}"
        assert message in caplog.text

    assert not list(ftp_server.home.iterdir())


@pytest.mark.asyncio
async def test_rmtree_no_permission(caplog, ftp_server):
    path = ftp_server.home / "test"
    path.mkdir()

    ftp_path = ftp_server.root / "test"

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

    message = "Could not remove directory because of an unexpected FTP error."
    assert message in caplog.text

    message = f"Failed to remove directory {str(ftp_path)!r} from the FTP server."
    assert message in str(err.value)
