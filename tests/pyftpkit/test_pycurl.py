# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import io
import logging
import os
import pathlib
from unittest import mock

import pycurl
import pytest

from pyftpkit._pycurl import PycURL
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError


@pytest.fixture
def connection_parameters(
    host,
    port,
    username,
    password,
):
    return ConnectionParameters.model_validate(
        {
            "host": host,
            "port": port,
            "credentials": {
                "username": username,
                "password": password,
            },
        }
    )


@pytest.fixture
def pycurl_mock(mocker):
    return mocker.patch("pyftpkit._pycurl.pycurl.Curl")


@pytest.fixture
def pycurl_instance(connection_parameters):
    return PycURL(connection_parameters=connection_parameters)


def test_ensure_ftp_url_no_changes(host, port, pycurl_instance):
    url = f"ftp://{host!s}:{port!s}/1/2/3/test.txt"

    assert pycurl_instance._ensure_ftp_url(url) == url


def test_ensure_ftp_url_add_schema(host, port, pycurl_instance):
    url = "/1/2/3/test.txt"

    assert pycurl_instance._ensure_ftp_url(url) == f"ftp://{host!s}:{port!s}{url!s}"


def test_ensure_ftp_url_special_symbols(host, port, pycurl_instance):
    url = "#backet"

    assert pycurl_instance._ensure_ftp_url(url) == f"ftp://{host!s}:{port!s}/%23backet"


def test_ensure_ftp_url_root_path(host, port, pycurl_instance):
    assert pycurl_instance._ensure_ftp_url("/") == f"ftp://{host!s}:{port!s}/"


def test_ensure_ftp_url_no_port(host, connection_parameters):
    connection_parameters.port = 0  # reset port
    pycurl = PycURL(connection_parameters=connection_parameters)

    url = "1/2/test.txt"

    assert pycurl._ensure_ftp_url(url) == f"ftp://{host!s}/{url!s}"


def test_download_no_permissions(caplog, fs, pycurl_instance):
    path = pathlib.Path("/test")
    path.mkdir()
    os.chmod(path, 0o000)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pycurl_instance.download("/test.txt", "/test/documents/test.txt")

    message = "Failed to create a new directory on the current machine."
    assert message in caplog.text

    message = f"Could not create target directory: {path!s}"
    assert message in str(err.value)


def test_download(
    caplog,
    fs,
    pycurl_mock,
    host,
    port,
    username,
    password,
    connection_parameters,
    pycurl_instance,
):
    connection_parameters.extra_options = {
        pycurl.VERBOSE: 1,
    }

    src = "/1/2/3/text.txt"

    dst = pathlib.Path("/test")
    dst.mkdir()
    dst /= "text.txt"

    size = 1024
    pycurl_mock.return_value.getinfo.return_value = size

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        size_bytes = pycurl_instance.download(src, dst)
    assert size_bytes == size

    url = f"ftp://{host!s}:{port!s}{src!s}"

    message = (
        f"Downloading {url!r} from FTP server to {str(dst)!r} on the local machine."
    )
    assert message in caplog.text

    message = (
        "Completed transfer of {0!s} bytes from FTP location {1!r} to {2!r}.".format(
            size, url, str(dst)
        )
    )
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.URL, url),
        mock.call(pycurl.USERPWD, "{0!s}:{1!s}".format(username, password)),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.VERBOSE, 1),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()
    pycurl_mock.return_value.close.assert_called_once()


def test_download_with_error(caplog, fs, host, port, pycurl_instance, pycurl_mock):
    src = "text.txt"
    dst = "text.txt"

    pycurl_mock.return_value.perform.side_effect = pycurl.error("error")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            pycurl_instance.download(src, dst)

    message = "An unexpected error occurred while fetching the data."
    assert message in caplog.text

    message = "Encountered an error while trying to fetch the data from: {0!s}".format(
        f"ftp://{host!s}:{port!s}/{src!s}"
    )
    assert message in str(err.value)


def test_download_with_fs_error(caplog, fs, pycurl_instance, pycurl_mock):
    src = "/text.txt"
    dst = pathlib.Path("/test")
    dst.mkdir()
    dst /= "text.txt"
    dst.mkdir()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pycurl_instance.download(src, dst)

    message = "An error occurred while trying to write the buffer to disk."
    assert message in caplog.text

    message = f"Failed to write buffer data to: {dst!s}"
    assert message in str(err.value)


def test_upload(
    caplog,
    fs,
    pycurl_mock,
    host,
    port,
    username,
    password,
    connection_parameters,
    pycurl_instance,
):
    connection_parameters.extra_options = {
        pycurl.VERBOSE: 1,
    }

    src = pathlib.Path("text.txt")
    src.write_text("test")
    dst = "/1/2/3/text.txt"

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pycurl_instance.upload(src, dst)

    url = f"ftp://{host!s}:{port!s}{dst!s}"

    message = f"Starting file upload from local {str(src)!r} to FTP path {url!r}."
    assert message in caplog.text

    message = f"Completed FTP upload of {str(src)!r} to {url!r}."
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.URL, url),
        mock.call(pycurl.USERPWD, f"{username}:{password}"),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 1),
        mock.call(pycurl.INFILESIZE, os.path.getsize(src)),
        mock.call(pycurl.UPLOAD, 1),
        mock.call(pycurl.VERBOSE, 1),
        mock.call(pycurl.READDATA, mock.ANY),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()
    pycurl_mock.return_value.close.assert_called_once()


def test_upload_with_error(caplog, fs, host, port, pycurl_instance, pycurl_mock):
    src = pathlib.Path("test.txt")
    src.write_text("")
    dst = "/"

    pycurl_mock.return_value.perform.side_effect = pycurl.error("error")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            pycurl_instance.upload(src, dst)

    url = f"ftp://{host!s}:{port!s}{dst!s}"

    message = "File could not be uploaded to the FTP server."
    assert message in caplog.text

    message = f"Could not upload {str(src)!r} to {url!r} on FTP server."
    assert message in str(err.value)


def test_upload_with_fs_error(caplog, fs, pycurl_mock, pycurl_instance):
    src = pathlib.Path("/test")
    src.mkdir()
    dst = "/"

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pycurl_instance.upload(src, dst)

    message = "File read operation failed on local system."
    message in caplog.text

    message = f"An error occurred while accessing the local file: {src!s}."
    assert message in str(err.value)
