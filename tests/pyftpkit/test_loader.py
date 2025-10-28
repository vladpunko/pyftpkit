# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import logging
import os
import pathlib

import pycurl
import pytest

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.loader import FTPLoader, _is_dirpath


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
            "max_connections": 1,
            "max_workers": 1,
            "timeout": 5,
            "extra_options": {
                pycurl.VERBOSE: 1,
            },
        }
    )


@pytest.mark.parametrize(
    "path, is_dirpath",
    [
        ("some/", True),
        (pathlib.Path("abc/"), True),
        ("text.txt", False),
        (".hidden", False),
        (".hiddendir/", True),
        ("dir", True),
        ("my.directory", False),
        (pathlib.Path("notes.md"), False),
        ("/usr/local/share/", True),
        ("/usr/local/share", True),
    ],
)
def test_is_dirpath(path, is_dirpath):
    assert _is_dirpath(path) is is_dirpath


def test_set_log_interval_with_error(connection_parameters):
    loader = FTPLoader(connections_parameters=connection_parameters)

    with pytest.raises(ValueError) as err:
        loader.log_interval = -10

    message = "Logging interval must be a positive integer."
    assert message in str(err.value)


def test_set_log_interval(connection_parameters):
    log_interval = 5
    loader = FTPLoader(connections_parameters=connection_parameters)
    loader.log_interval = log_interval

    assert loader.log_interval == log_interval


@pytest.mark.asyncio
async def test_download_file_to_file(tmp_path, ftp_server, connection_parameters):
    content = "test"
    path = ftp_server.home / "test.txt"
    path.write_text(content)

    src = ftp_server.root / "test.txt"
    dst = tmp_path / "1.txt"

    loader = FTPLoader(connections_parameters=connection_parameters)
    await loader.download(src, dst)

    assert dst.is_file()
    assert dst.read_text() == content


@pytest.mark.asyncio
async def test_download_with_passed_dirpath(caplog, ftp_server, connection_parameters):
    loader = FTPLoader(connections_parameters=connection_parameters)

    path = "/test/"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.download([path], "")

    message = "It is not feasible to handle directories during FTP batch downloading."
    assert message in caplog.text

    message = f"Invalid path for batch download: {path!s}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_download_mismatch_source_and_destination(
    caplog, ftp_server, connection_parameters
):
    loader = FTPLoader(connections_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.download(
                [
                    "/1.txt",
                    "/2.txt",
                    "/3.txt",
                ],
                ["/1.txt"],
            )

    message = "Length of source list does not match length of destination list."
    assert message in caplog.text

    message = "Source and destination path counts must be equal."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_download_target_path_is_directory_with_error(
    caplog, ftp_server, connection_parameters
):
    loader = FTPLoader(connections_parameters=connection_parameters)

    path = "/test/"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.download(["/1.txt", "/2.txt"], ["/1.txt", path])

    message = "One or more target paths are directories."
    assert message in caplog.text

    message = f"Cannot include directory {path!r} in batch downloads."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_download_target_path_is_directory(
    tmp_path, caplog, ftp_server, connection_parameters
):
    path = ftp_server.home / "1.txt"
    path.write_text("")
    path = ftp_server.home / "test"
    path.mkdir()
    path /= "2.txt"
    path.write_text("")

    src = [
        ftp_server.root / "1.txt",
        ftp_server.root / "test" / "2.txt",
    ]
    dst = tmp_path

    loader = FTPLoader(connections_parameters=connection_parameters, log_interval=1)
    with caplog.at_level(logging.INFO, logger="pyftpkit"):
        await loader.download(src, dst)

    assert len(list(tmp_path.iterdir())) == 2
    assert set(tmp_path.iterdir()) == {
        tmp_path / "1.txt",
        tmp_path / "2.txt",
    }

    message = "Downloaded: 1 / 2"
    assert message in caplog.text

    message = "All downloads finished: 2 / 2"
    assert message in caplog.text


@pytest.mark.asyncio
async def test_download_file_to_directory(tmp_path, ftp_server, connection_parameters):
    path = ftp_server.home / "1.txt"
    path.write_text("")

    src = ftp_server.root / "1.txt"
    dst = tmp_path

    loader = FTPLoader(connections_parameters=connection_parameters)
    await loader.download(src, dst)

    assert (dst / "1.txt").is_file()


@pytest.mark.asyncio
async def test_download_directory_to_file(caplog, ftp_server, connection_parameters):
    src = "/test/"
    dst = "text.txt"

    loader = FTPLoader(connections_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.download(src, dst)

    message = "Only directory destinations are valid for directory sources."
    assert message in caplog.text

    message = f"Cannot download a directory into: {dst!s}"
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_download_directory_to_directory(
    caplog, tmp_path, ftp_server, connection_parameters
):
    loader = FTPLoader(connections_parameters=connection_parameters)

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        await loader.download("/", tmp_path)

    message = "No data found to download."
    assert message in caplog.text

    path = ftp_server.home / "1.txt"
    path.write_text("")
    path = ftp_server.home / "1"
    path.mkdir()
    path /= "1.txt"
    path.write_text("")
    path = ftp_server.home / "2"
    path.mkdir()
    path /= "2.txt"
    path.write_text("")

    await loader.download("/", tmp_path)

    assert os.path.isdir(tmp_path / "1")
    assert os.path.isdir(tmp_path / "2")

    assert os.path.isfile(tmp_path / "1.txt")
    assert os.path.isfile(tmp_path / "1" / "1.txt")
    assert os.path.isfile(tmp_path / "2" / "2.txt")


@pytest.mark.asyncio
async def test_upload_file_to_file(tmp_path, ftp_server, connection_parameters):
    content = "test"
    src = tmp_path / "1.txt"
    src.write_text(content)
    dst = "/1.txt"

    loader = FTPLoader(connections_parameters=connection_parameters)
    await loader.upload(src, dst)

    dst = ftp_server.home / "1.txt"
    assert dst.is_file()
    assert dst.read_text() == content


@pytest.mark.asyncio
async def test_upload_file_to_directory(tmp_path, ftp_server, connection_parameters):
    content = "test"
    src = tmp_path / "text.txt"
    src.write_text(content)
    dst = ftp_server.root / "documents"

    path = ftp_server.home / "documents"
    path.mkdir()

    loader = FTPLoader(connections_parameters=connection_parameters)
    await loader.upload(src, dst)

    path /= "text.txt"
    assert path.is_file()
    assert path.read_text() == content


@pytest.mark.asyncio
async def test_upload_directory_to_file(caplog, tmp_path, connection_parameters):
    src = tmp_path / "test"
    src.mkdir()
    dst = "documents.txt"

    loader = FTPLoader(connections_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.upload(src, dst)

    message = "Cannot upload a directory to a single file destination."
    assert message in caplog.text

    message = (
        "Directories in source require destinations of directory type."
        f"\nSource: {src!s}"
        f"\nDestination: {dst!s}"
    )
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_upload_directory_to_directory(
    caplog, tmp_path, ftp_server, connection_parameters
):
    path = tmp_path / "1.txt"
    path.write_text("")
    path = tmp_path / "1"
    path.mkdir()
    path /= "1.txt"
    path.write_text("")
    path = tmp_path / "2"
    path.mkdir()
    path /= "2.txt"
    path.write_text("")

    src = tmp_path
    dst = "/"

    loader = FTPLoader(connections_parameters=connection_parameters, log_interval=1)

    with caplog.at_level(logging.INFO, logger="pyftpkit"):
        await loader.upload(src, dst)

    message = "Uploaded: 1 / 3"
    assert message in caplog.text

    message = "All uploads finished: 3 / 3"
    assert message in caplog.text

    assert os.path.isdir(ftp_server.home / "1")
    assert os.path.isdir(ftp_server.home / "2")

    assert os.path.isfile(ftp_server.home / "1.txt")
    assert os.path.isfile(ftp_server.home / "1" / "1.txt")
    assert os.path.isfile(ftp_server.home / "2" / "2.txt")


@pytest.mark.asyncio
async def test_upload_mismatch_source_and_destination(caplog, connection_parameters):
    loader = FTPLoader(connections_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.upload(
                [
                    "/1.txt",
                    "/2.txt",
                ],
                [
                    "/1.txt",
                    "/2.txt",
                    "/3.txt",
                ],
            )

    message = "Source and destination lists must match one-to-one."
    assert message in caplog.text

    message = "Number of sources does not match number of destinations."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_upload_target_path_is_directory_with_error(
    caplog, tmp_path, ftp_server, connection_parameters
):
    src = [tmp_path / "1.txt"]
    src[0].write_text("")

    loader = FTPLoader(connections_parameters=connection_parameters)

    path = "/test/"
    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await loader.upload(src, [path])

    message = "Directories are not allowed as destination paths."
    assert message in caplog.text

    message = f"Upload failed due to invalid destination path: {path!s}"
    assert message in str(err.value)
