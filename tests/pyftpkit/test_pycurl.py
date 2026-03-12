# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-26

import contextlib
import io
import logging
import pathlib
import queue
import urllib.parse
from unittest import mock

import pycurl
import pytest

from pyftpkit._pycurl import PycURL, PycURLPoolManager
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import (
    FTPError,
    FTPPathError,
    FTPPathNotAbsoluteError,
)


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
def pycurl_instance(connection_parameters, pycurl_mock):
    return PycURL(connection_parameters=connection_parameters)


@pytest.fixture
def pycurl_pool_manager(connection_parameters, pycurl_mock):
    return PycURLPoolManager(connection_parameters=connection_parameters)


def test_ensure_file_transfer_protocol_uniform_resource_locator_no_changes(
    host, port, pycurl_instance
):
    ftp_url = "ftp://{0!s}:{1!s}/1/2/3/test.txt".format(host, port)

    assert pycurl_instance._ensure_ftp_url(ftp_url) == ftp_url


def test_ensure_file_transfer_protocol_uniform_resource_locator_adds_schema(
    host, port, pycurl_instance
):
    remote_path = "/1/2/3/test.txt"

    assert pycurl_instance._ensure_ftp_url(
        remote_path
    ) == "ftp://{0!s}:{1!s}{2!s}".format(host, port, remote_path)


def test_ensure_file_transfer_protocol_uniform_resource_locator_encodes_special_symbols(
    host, port, pycurl_instance
):
    remote_path = "#basket"

    assert pycurl_instance._ensure_ftp_url(
        remote_path
    ) == "ftp://{0!s}:{1!s}/%23basket".format(host, port)


def test_ensure_file_transfer_protocol_uniform_resource_locator_root_path(
    host, port, pycurl_instance
):
    assert pycurl_instance._ensure_ftp_url("/") == "ftp://{0!s}:{1!s}/".format(
        host, port
    )


def test_ensure_file_transfer_protocol_address_collapses_leading_slashes(
    host, port, pycurl_instance
):
    raw_path = "///1/2/3/test.txt"

    assert pycurl_instance._ensure_ftp_url(
        raw_path
    ) == "ftp://{0!s}:{1!s}/1/2/3/test.txt".format(host, port)


def test_ensure_file_transfer_protocol_address_preserves_trailing_whitespace(
    host, port, pycurl_instance
):
    raw_path = "/1/2/3/test.txt  \t"

    assert pycurl_instance._ensure_ftp_url(
        raw_path
    ) == "ftp://{0!s}:{1!s}/1/2/3/test.txt%20%20%09".format(host, port)


def test_ensure_file_transfer_protocol_uniform_resource_locator_without_port(
    host, connection_parameters
):
    connection_parameters.port = 0  # reset port
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    relative_path = "1/2/test.txt"

    assert pycurl_client._ensure_ftp_url(relative_path) == "ftp://{0!s}/{1!s}".format(
        host, relative_path
    )


def test_ensure_file_transfer_protocol_address_encodes_symbol_filenames(
    host, port, pycurl_instance, filenames_with_symbols
):
    for name in filenames_with_symbols:
        remote_path = "/" + name
        encoded_path = urllib.parse.quote(remote_path, safe="/")
        expected_url = "ftp://{0!s}:{1!s}{2!s}".format(host, port, encoded_path)
        assert pycurl_instance._ensure_ftp_url(remote_path) == expected_url


def test_connection_parameters_apply_extra_options(connection_parameters, pycurl_mock):
    connection_parameters.extra_options = {
        pycurl.VERBOSE: 1,
    }

    PycURL(connection_parameters=connection_parameters)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.VERBOSE, 1)


def test_download_no_permissions(caplog, filesystem_without_root, pycurl_instance):
    restricted_directory = pathlib.Path("/test")
    restricted_directory.mkdir()
    restricted_directory.chmod(0o000)

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            pycurl_instance.download(
                "/test.txt",
                str(restricted_directory / "documents" / "test.txt"),
            )

    message = "Failed to create a new directory on the current machine."
    assert message in caplog.text

    message = "Could not create target directory: {0!r}"
    message = message.format(str(restricted_directory / "documents"))
    assert message in str(error.value)


def test_download_sets_curl_options_and_logs_transfer(
    caplog,
    filesystem_without_root,
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

    remote_source_path = "/1/2/3/text.txt"

    local_destination_path = pathlib.Path("/test")
    local_destination_path.mkdir()
    local_destination_path = str(local_destination_path / "text.txt")

    expected_size_bytes = 1024
    pycurl_mock.return_value.getinfo.return_value = expected_size_bytes

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        size_bytes = pycurl_instance.download(
            remote_source_path, local_destination_path
        )
    assert size_bytes == expected_size_bytes

    ftp_url = "ftp://{0!s}:{1!s}{2!s}".format(host, port, remote_source_path)

    message = "Starting FTP download of {0!r} to {1!r} on the local machine."
    message = message.format(ftp_url, local_destination_path)
    assert message in caplog.text

    message = "Finished moving {0!s} bytes from the FTP server {1!r} to {2!r}."
    message = message.format(expected_size_bytes, ftp_url, local_destination_path)
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.USERPWD, "{0!s}:{1!s}".format(username, password)),
        mock.call(pycurl.FORBID_REUSE, 0),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.URL, ftp_url),
        mock.call(pycurl.WRITEFUNCTION, mock.ANY),
        mock.call(pycurl.WRITEFUNCTION, mock.ANY),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()


def test_download_pathlike_source_and_destination(
    caplog,
    filesystem_without_root,
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

    remote_source_path = pathlib.PurePosixPath("/1/2/3/text.txt")

    local_destination_path = pathlib.Path("/test")
    local_destination_path.mkdir()
    local_destination_path = local_destination_path / "text.txt"

    expected_size_bytes = 1024
    pycurl_mock.return_value.getinfo.return_value = expected_size_bytes

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        size_bytes = pycurl_instance.download(
            remote_source_path, local_destination_path
        )
    assert size_bytes == expected_size_bytes

    ftp_url = "ftp://{0!s}:{1!s}{2!s}".format(host, port, str(remote_source_path))

    message = "Starting FTP download of {0!r} to {1!r} on the local machine."
    message = message.format(ftp_url, str(local_destination_path))
    assert message in caplog.text

    message = "Finished moving {0!s} bytes from the FTP server {1!r} to {2!r}."
    message = message.format(expected_size_bytes, ftp_url, str(local_destination_path))
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.USERPWD, "{0!s}:{1!s}".format(username, password)),
        mock.call(pycurl.FORBID_REUSE, 0),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.URL, ftp_url),
        mock.call(pycurl.WRITEFUNCTION, mock.ANY),
        mock.call(pycurl.WRITEFUNCTION, mock.ANY),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()


@pytest.mark.parametrize(
    "source_path, destination_path",
    [
        (None, "dst"),
        ("src", None),
    ],
)
def test_download_validation_type_errors(
    caplog, pycurl_instance, source_path, destination_path
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            pycurl_instance.download(source_path, destination_path)

    message = "The source and destination paths must both be strings."
    assert message in caplog.text

    message = (
        "Source and destination paths are required to be strings."
        "\nSource {0!r} has type: {1!s}"
        "\nDestination {2!r} has type: {3!s}"
    )
    message = message.format(
        source_path,
        type(source_path).__name__,
        destination_path,
        type(destination_path).__name__,
    )
    assert message in str(error.value)


@pytest.mark.parametrize(
    "source_path, destination_path",
    [
        ("", "dst"),
        (" ", "dst"),
    ],
)
def test_download_validation_source_value_errors(
    caplog, pycurl_instance, source_path, destination_path
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            pycurl_instance.download(source_path, destination_path)

    message = "The source path cannot be empty or whitespace."
    assert message in caplog.text

    message = "The source path must not be empty or consist only of whitespace."
    assert message in str(error.value)


@pytest.mark.parametrize(
    "source_path, destination_path",
    [
        ("/src", ""),
        ("/src", " "),
    ],
)
def test_download_validation_destination_value_errors(
    caplog, pycurl_instance, source_path, destination_path
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            pycurl_instance.download(source_path, destination_path)

    message = "The destination path cannot be empty or whitespace."
    assert message in caplog.text

    message = "The destination path must not be empty or consist only of whitespace."
    assert message in str(error.value)


def test_download_validation_no_root_slash(caplog, pycurl_instance):
    relative_source_path = "src"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathNotAbsoluteError) as error:
            pycurl_instance.download(relative_source_path, "dst")

    message = "The source path is not absolute and does not start from the root."
    assert message in caplog.text

    message = "Ambiguous source path: {0!r}"
    message = message.format(relative_source_path)
    assert message in str(error.value)


def test_download_trailing_whitespace_preserves_remote_path(
    filesystem_without_root, pycurl_mock, connection_parameters, host, port
):
    remote_source_path = "/1/2/3/text.txt   "
    local_destination_path = "text.txt"
    ftp_url = "ftp://{0!s}:{1!s}/1/2/3/text.txt%20%20%20".format(host, port)

    pycurl_client = PycURL(connection_parameters=connection_parameters)
    pycurl_client.download(remote_source_path, local_destination_path)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, ftp_url)


def test_download_trailing_tabs_preserves_remote_path(
    filesystem_without_root, pycurl_mock, connection_parameters, host, port
):
    remote_source_path = "/1/2/3/text.txt\t\t"
    local_destination_path = "tabbed.txt"
    ftp_url = "ftp://{0!s}:{1!s}/1/2/3/text.txt%09%09".format(host, port)

    pycurl_client = PycURL(connection_parameters=connection_parameters)
    pycurl_client.download(remote_source_path, local_destination_path)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, ftp_url)


def test_download_with_error(
    caplog, filesystem_without_root, host, port, pycurl_instance, pycurl_mock, mocker
):
    remote_source_path = "/text.txt"
    local_destination_path = pathlib.Path("text.txt")
    local_destination_path.write_text("test", encoding="utf-8")

    pycurl_mock.return_value.perform.side_effect = pycurl.error()
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPError) as error:
            pycurl_instance.download(remote_source_path, str(local_destination_path))

    assert not local_destination_path.exists()
    sleep_mock.assert_not_called()
    assert pycurl_mock.return_value.perform.call_count == 1

    message = "An unexpected error occurred while fetching the data."
    assert message in caplog.text

    message = "Encountered an error while trying to fetch the data from: {0!r}"
    message = message.format(
        "ftp://{0!s}:{1!s}{2!s}".format(host, port, remote_source_path)
    )
    assert message in str(error.value)


def test_download_retries_on_connect_error(
    filesystem_without_root, connection_parameters, pycurl_mock, mocker
):
    connection_parameters.transfer_retry_count = 1
    connection_parameters.transfer_retry_backoff = 0.01
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    remote_source_path = "/text.txt"
    local_destination_path = pathlib.Path("text.txt")

    pycurl_mock.return_value.getinfo.return_value = 1
    pycurl_mock.return_value.perform.side_effect = [
        pycurl.error(pycurl.E_COULDNT_CONNECT, "connect failed"),
        None,
    ]
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")

    pycurl_client.download(remote_source_path, str(local_destination_path))

    assert pycurl_mock.return_value.perform.call_count == 2
    sleep_mock.assert_called_once_with(0.01)


def test_download_returns_without_attempts_for_negative_retry_count(
    caplog, filesystem_without_root, connection_parameters, pycurl_instance, pycurl_mock
):
    connection_parameters.transfer_retry_count = -1

    pycurl_instance._perform_with_retries()

    assert caplog.text == ""
    pycurl_mock.return_value.perform.assert_not_called()


def test_download_does_not_retry_for_non_integer_error_code(
    caplog, connection_parameters, pycurl_mock, mocker
):
    connection_parameters.transfer_retry_count = 1
    connection_parameters.transfer_retry_backoff = 0.01
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    pycurl_mock.return_value.perform.side_effect = pycurl.error(
        "non-integer error code"
    )
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")

    with pytest.raises(pycurl.error) as error:
        pycurl_client._perform_with_retries()

    assert caplog.text == ""
    assert pycurl_mock.return_value.perform.call_count == 1
    sleep_mock.assert_not_called()
    message = "non-integer error code"
    assert message in str(error.value)


def test_download_raises_without_retry_for_zero_retry_count(
    caplog, connection_parameters, pycurl_mock, mocker
):
    connection_parameters.transfer_retry_count = 0
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    pycurl_mock.return_value.perform.side_effect = pycurl.error(
        pycurl.E_COULDNT_CONNECT, "connect failed"
    )
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")

    with pytest.raises(pycurl.error) as error:
        pycurl_client._perform_with_retries()

    assert caplog.text == ""
    assert pycurl_mock.return_value.perform.call_count == 1
    sleep_mock.assert_not_called()
    message = "connect failed"
    assert message in str(error.value)


def test_download_sleeps_between_transfers_to_reduce_time_wait(
    filesystem_without_root, connection_parameters, pycurl_mock, mocker
):
    connection_parameters.transfer_pause_seconds = 0.5
    pycurl_client = PycURL(connection_parameters=connection_parameters)
    pycurl_mock.return_value.getinfo.return_value = 1
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")

    destination_path = pathlib.Path("text.txt")

    pycurl_client.download("/text.txt", str(destination_path))
    pycurl_client.download("/text.txt", str(destination_path))

    sleep_mock.assert_has_calls([mock.call(0.5), mock.call(0.5)])
    assert sleep_mock.call_count == 2


def test_download_resets_write_function_on_error(
    caplog, filesystem_without_root, connection_parameters, pycurl_mock
):
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    remote_source_path = "/text.txt"
    local_destination_path = pathlib.Path("text.txt")
    local_destination_path.write_text("test", encoding="utf-8")

    pycurl_mock.return_value.perform.side_effect = pycurl.error(
        "simulated download failure from test"
    )

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPError) as error:
            pycurl_client.download(remote_source_path, str(local_destination_path))

    message = "An unexpected error occurred while fetching the data."
    assert message in caplog.text

    message = "Encountered an error while trying to fetch the data from: {0!r}"
    message = message.format(
        "ftp://{0!s}:{1!s}{2!s}".format(
            connection_parameters.host,
            connection_parameters.port,
            remote_source_path,
        )
    )
    assert message in str(error.value)

    last_call = pycurl_mock.return_value.setopt.call_args_list[-1]
    assert last_call == mock.call(pycurl.WRITEFUNCTION, mock.ANY)


def test_download_with_filesystem_error(
    caplog, filesystem_without_root, pycurl_instance, pycurl_mock
):
    remote_source_path = "/text.txt"
    local_destination_path = pathlib.Path("/test")
    local_destination_path.mkdir()
    local_destination_path = local_destination_path / "text.txt"
    local_destination_path.mkdir()
    local_destination_path = str(local_destination_path)

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            pycurl_instance.download(remote_source_path, local_destination_path)

    message = "An error occurred while trying to write the buffer to disk."
    assert message in caplog.text

    message = "Failed to write buffer data to: {0!r}"
    message = message.format(str(local_destination_path))
    assert message in str(error.value)


def test_upload_sets_curl_options_and_logs_transfer(
    caplog,
    filesystem_without_root,
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

    local_source_path = pathlib.Path("text.txt")
    local_source_path.write_text("test", encoding="utf-8")
    remote_destination_path = "/1/2/3/text.txt"

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pycurl_instance.upload(str(local_source_path), remote_destination_path)

    ftp_url = "ftp://{0!s}:{1!s}{2!s}".format(host, port, remote_destination_path)

    message = "Uploading {0!r} from local system to {1!r} on the FTP server."
    message = message.format(str(local_source_path), ftp_url)
    assert message in caplog.text

    message = "Finished uploading {0!r} to {1!r} on the FTP server."
    message = message.format(str(local_source_path), ftp_url)
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.USERPWD, "{0}:{1}".format(username, password)),
        mock.call(pycurl.FORBID_REUSE, 0),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.URL, ftp_url),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 1),
        mock.call(pycurl.INFILESIZE, local_source_path.stat().st_size),
        mock.call(pycurl.UPLOAD, 1),
        mock.call(pycurl.READFUNCTION, mock.ANY),
        mock.call(pycurl.INFILESIZE, -1),
        mock.call(pycurl.READFUNCTION, mock.ANY),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 0),
        mock.call(pycurl.UPLOAD, 0),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()


def test_upload_pathlike_source_and_destination(
    caplog,
    filesystem_without_root,
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

    local_source_path = pathlib.Path("text.txt")
    local_source_path.write_text("test", encoding="utf-8")
    remote_destination_path = pathlib.PurePosixPath("/1/2/3/text.txt")

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pycurl_instance.upload(local_source_path, remote_destination_path)

    ftp_url = "ftp://{0!s}:{1!s}{2!s}".format(host, port, str(remote_destination_path))

    message = "Uploading {0!r} from local system to {1!r} on the FTP server."
    message = message.format(str(local_source_path), ftp_url)
    assert message in caplog.text

    message = "Finished uploading {0!r} to {1!r} on the FTP server."
    message = message.format(str(local_source_path), ftp_url)
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.USERPWD, "{0}:{1}".format(username, password)),
        mock.call(pycurl.FORBID_REUSE, 0),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.URL, ftp_url),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 1),
        mock.call(pycurl.INFILESIZE, local_source_path.stat().st_size),
        mock.call(pycurl.UPLOAD, 1),
        mock.call(pycurl.READFUNCTION, mock.ANY),
        mock.call(pycurl.INFILESIZE, -1),
        mock.call(pycurl.READFUNCTION, mock.ANY),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 0),
        mock.call(pycurl.UPLOAD, 0),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()


def test_upload_with_error(
    caplog, filesystem_without_root, host, port, pycurl_instance, pycurl_mock, mocker
):
    local_source_path = pathlib.Path("test.txt")
    local_source_path.write_text("", encoding="utf-8")
    remote_destination_path = "/"

    pycurl_mock.return_value.perform.side_effect = pycurl.error(
        "simulated upload failure from test"
    )
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPError) as error:
            pycurl_instance.upload(str(local_source_path), remote_destination_path)

    ftp_url = "ftp://{0!s}:{1!s}{2!s}".format(host, port, remote_destination_path)

    message = "File could not be uploaded to the FTP server."
    assert message in caplog.text
    sleep_mock.assert_not_called()
    assert pycurl_mock.return_value.perform.call_count == 1

    message = "Could not upload {0!r} to {1!r} on FTP server."
    message = message.format(str(local_source_path), ftp_url)
    assert message in str(error.value)


def test_upload_retries_on_connect_error(
    filesystem_without_root, connection_parameters, pycurl_mock, mocker
):
    connection_parameters.transfer_retry_count = 1
    connection_parameters.transfer_retry_backoff = 0.02
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    local_source_path = pathlib.Path("test.txt")
    local_source_path.write_text("", encoding="utf-8")
    remote_destination_path = "/"

    pycurl_mock.return_value.perform.side_effect = [
        pycurl.error(pycurl.E_COULDNT_CONNECT, "connect failed"),
        None,
    ]
    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")

    pycurl_client.upload(str(local_source_path), remote_destination_path)

    assert pycurl_mock.return_value.perform.call_count == 2
    sleep_mock.assert_called_once_with(0.02)


def test_upload_sleeps_between_transfers_to_reduce_time_wait(
    filesystem_without_root, connection_parameters, pycurl_mock, mocker
):
    connection_parameters.transfer_pause_seconds = 0.5
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    source_path = pathlib.Path("upload.txt")
    source_path.write_text("data", encoding="utf-8")

    sleep_mock = mocker.patch("pyftpkit._pycurl.time.sleep")

    pycurl_client.upload(str(source_path), "/upload.txt")
    pycurl_client.upload(str(source_path), "/upload.txt")

    sleep_mock.assert_has_calls([mock.call(0.5), mock.call(0.5)])
    assert sleep_mock.call_count == 2


def test_upload_resets_transfer_options_on_error(
    caplog, filesystem_without_root, connection_parameters, pycurl_mock
):
    pycurl_client = PycURL(connection_parameters=connection_parameters)

    local_source_path = pathlib.Path("test.txt")
    local_source_path.write_text("", encoding="utf-8")
    remote_destination_path = "/"

    pycurl_mock.return_value.perform.side_effect = pycurl.error(
        "simulated upload failure from test"
    )

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPError) as error:
            pycurl_client.upload(str(local_source_path), remote_destination_path)

    message = "File could not be uploaded to the FTP server."
    assert message in caplog.text

    message = "Could not upload {0!r} to {1!r} on FTP server."
    message = message.format(
        str(local_source_path),
        "ftp://{0!s}:{1!s}{2!s}".format(
            connection_parameters.host,
            connection_parameters.port,
            remote_destination_path,
        ),
    )
    assert message in str(error.value)

    expected_tail = [
        mock.call(pycurl.INFILESIZE, -1),
        mock.call(pycurl.READFUNCTION, mock.ANY),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 0),
        mock.call(pycurl.UPLOAD, 0),
    ]
    assert pycurl_mock.return_value.setopt.call_args_list[-4:] == expected_tail


@pytest.mark.parametrize(
    "local_source_path, remote_destination_path, prepare",
    [
        ("/missing.txt", "/upload.txt", None),
        ("/test", "/", "mkdir"),
    ],
)
def test_upload_with_filesystem_error(
    caplog,
    filesystem_without_root,
    pycurl_mock,
    pycurl_instance,
    local_source_path,
    remote_destination_path,
    prepare,
):
    source_path = pathlib.Path(local_source_path)
    if prepare == "mkdir":
        source_path.mkdir()

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            pycurl_instance.upload(str(source_path), remote_destination_path)

    message = "File read operation failed on local system."
    assert message in caplog.text

    message = "An error occurred while accessing the local file: {0!r}."
    message = message.format(str(source_path))
    assert message in str(error.value)


@pytest.mark.parametrize(
    "source_path, destination_path",
    [
        (None, "dst"),
        ("src", None),
    ],
)
def test_upload_validation_type_errors(
    caplog, pycurl_instance, source_path, destination_path
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            pycurl_instance.upload(source_path, destination_path)

    message = "The source path and the destination path must each be a string."
    assert message in caplog.text

    message = (
        "Both the source and destination need to be strings."
        "\nSource {0!r} has type: {1!s}"
        "\nDestination {2!r} has type: {3!s}"
    )
    message = message.format(
        source_path,
        type(source_path).__name__,
        destination_path,
        type(destination_path).__name__,
    )
    assert message in str(error.value)


@pytest.mark.parametrize(
    "source_path, destination_path",
    [
        ("", "dst"),
        (" ", "dst"),
    ],
)
def test_upload_validation_source_value_errors(
    caplog, pycurl_instance, source_path, destination_path
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            pycurl_instance.upload(source_path, destination_path)

    message = "A source path of only whitespace is invalid."
    assert message in caplog.text

    message = "The source path must include at least one non-whitespace character."
    assert message in str(error.value)


@pytest.mark.parametrize(
    "source_path, destination_path",
    [
        ("/src", ""),
        ("/src", " "),
    ],
)
def test_upload_validation_destination_value_errors(
    caplog, pycurl_instance, source_path, destination_path
):
    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathError) as error:
            pycurl_instance.upload(source_path, destination_path)

    message = "A destination path of only whitespace is invalid."
    assert message in caplog.text

    message = "The destination path cannot be empty or contain only blank characters."
    assert message in str(error.value)


def test_upload_validation_no_root_slash(caplog, pycurl_instance):
    relative_destination_path = "dst"

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPPathNotAbsoluteError) as error:
            pycurl_instance.upload("src", relative_destination_path)

    message = "The destination path is not absolute and does not start from the root."
    assert message in caplog.text

    message = "Ambiguous destination path: {0!r}"
    message = message.format(relative_destination_path)
    assert message in str(error.value)


def test_upload_trailing_whitespace_preserves_remote_path(
    filesystem_without_root, pycurl_mock, connection_parameters, host, port
):
    local_source_path = pathlib.Path("upload.txt")
    local_source_path.write_text("data", encoding="utf-8")
    local_source_path_string = str(local_source_path)
    remote_destination_path = "/uploads/upload.txt   "
    ftp_url = "ftp://{0!s}:{1!s}/uploads/upload.txt%20%20%20".format(host, port)

    pycurl_client = PycURL(connection_parameters=connection_parameters)
    pycurl_client.upload(local_source_path_string, remote_destination_path)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, ftp_url)


def test_upload_trailing_tabs_preserves_remote_path(
    filesystem_without_root, pycurl_mock, connection_parameters, host, port
):
    local_source_path = pathlib.Path("upload_tabs.txt")
    local_source_path.write_text("data", encoding="utf-8")
    local_source_path_string = str(local_source_path)
    remote_destination_path = "/uploads/upload_tabs.txt\t\t"
    ftp_url = "ftp://{0!s}:{1!s}/uploads/upload_tabs.txt%09%09".format(host, port)

    pycurl_client = PycURL(connection_parameters=connection_parameters)
    pycurl_client.upload(local_source_path_string, remote_destination_path)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, ftp_url)


def test_pool_manager_initialization(connection_parameters):
    connection_parameters.max_connections = 4

    pool_manager = PycURLPoolManager(connection_parameters=connection_parameters)

    assert pool_manager._pool.maxsize == 4
    assert pool_manager._pool.qsize() == 4
    assert pool_manager._shutdown is False


def test_pool_manager_initialization_minimum_maximum(connection_parameters):
    connection_parameters.max_connections = 1

    pool_manager = PycURLPoolManager(connection_parameters)

    assert pool_manager._pool.maxsize == 1
    assert pool_manager._pool.qsize() == 1


def test_pool_manager_close(pycurl_pool_manager, mocker):
    pycurl_instance_mock = mocker.MagicMock()

    # Replace instances with mocks inside pool.
    pool_items = []
    while not pycurl_pool_manager._pool.empty():
        pool_items.append(pycurl_pool_manager._pool.get())
    for _ in pool_items:
        pycurl_pool_manager._pool.put(pycurl_instance_mock)

    pycurl_pool_manager.close()

    assert pycurl_pool_manager._shutdown is True
    assert pycurl_pool_manager._pool.empty()
    pycurl_instance_mock.close.assert_called()


def test_pool_manager_close_queue_empty(pycurl_pool_manager, mocker):
    mocker.patch.object(pycurl_pool_manager._pool, "empty", return_value=False)
    mocker.patch.object(
        pycurl_pool_manager._pool, "get_nowait", side_effect=queue.Empty
    )

    pycurl_pool_manager.close()

    assert pycurl_pool_manager._shutdown is True


def test_pool_manager_close_idempotent(pycurl_pool_manager):
    pycurl_instance_mocks = []

    while not pycurl_pool_manager._pool.empty():
        pycurl_pool_manager._pool.get()

    for _ in range(pycurl_pool_manager._pool.maxsize):
        pycurl_instance_mock = mock.MagicMock()
        pycurl_instance_mocks.append(pycurl_instance_mock)
        pycurl_pool_manager._pool.put(pycurl_instance_mock)

    pycurl_pool_manager.close()
    pycurl_pool_manager.close()

    for pycurl_instance_mock in pycurl_instance_mocks:
        pycurl_instance_mock.close.assert_called_once()


def test_pool_manager_acquire(pycurl_pool_manager):
    assert pycurl_pool_manager._pool.qsize() > 0

    with pycurl_pool_manager.acquire() as pycurl_instance:
        assert isinstance(pycurl_instance, PycURL)
        assert (
            pycurl_pool_manager._pool.qsize() == pycurl_pool_manager._pool.maxsize - 1
        )

    assert pycurl_pool_manager._pool.qsize() == pycurl_pool_manager._pool.maxsize


def test_pool_manager_acquire_closed_pool_raises(caplog, pycurl_pool_manager):
    pycurl_pool_manager._shutdown = True

    with pytest.raises(RuntimeError) as error:
        with pycurl_pool_manager.acquire():
            pass

    assert caplog.text == ""

    message = "Cannot acquire from a closed pool."
    assert message in str(error.value)


def test_pool_manager_acquire_shutdown_while_waiting(
    caplog, pycurl_pool_manager, mocker
):
    def _get(*args, **kwargs):
        pycurl_pool_manager._shutdown = True

        raise queue.Empty

    mocker.patch.object(pycurl_pool_manager._pool, "get", side_effect=_get)

    with pytest.raises(RuntimeError) as error:
        with pycurl_pool_manager.acquire():
            pass

    assert caplog.text == ""

    message = "Cannot acquire from a closed pool."
    assert message in str(error.value)


def test_pool_manager_acquire_retries_until_available(pycurl_pool_manager, mocker):
    pycurl_instance_mock = mocker.MagicMock()
    get_mock = mocker.patch.object(
        pycurl_pool_manager._pool,
        "get",
        side_effect=[queue.Empty, pycurl_instance_mock],
    )
    put_mock = mocker.patch.object(pycurl_pool_manager._pool, "put")

    with pycurl_pool_manager.acquire() as pycurl_instance:
        assert pycurl_instance is pycurl_instance_mock

    assert get_mock.call_count == 2
    put_mock.assert_called_once_with(pycurl_instance_mock)


def test_pool_manager_acquire_with_shutdown(pycurl_pool_manager, mocker):
    with pycurl_pool_manager.acquire() as pycurl_instance:
        # Simulate an external thread closing the pool.
        pycurl_pool_manager.close()

        # Mock the instance's close method right before context exit.
        close_mock = mocker.patch.object(pycurl_instance, "close")

    close_mock.assert_called_once()
    assert pycurl_pool_manager._pool.qsize() == 0


def test_pool_manager_acquire_returns_on_exception(caplog, pycurl_pool_manager):
    initial_size = pycurl_pool_manager._pool.qsize()
    message = "Forced exception to verify pool returns instances."

    with pytest.raises(ValueError) as error:
        with pycurl_pool_manager.acquire():
            raise ValueError(message)

    assert caplog.text == ""
    assert message in str(error.value)
    assert pycurl_pool_manager._pool.qsize() == initial_size


def test_pool_manager_download(pycurl_pool_manager, mocker):
    pycurl_instance_mock = mocker.MagicMock()
    mocker.patch.object(
        pycurl_pool_manager,
        "acquire",
        return_value=mocker.MagicMock(
            __enter__=mocker.MagicMock(return_value=pycurl_instance_mock),
            __exit__=mocker.MagicMock(),
        ),
    )

    remote_source_path = "/test.txt"
    local_destination_path = "test.txt"

    pycurl_pool_manager.download(remote_source_path, local_destination_path)

    pycurl_instance_mock.download.assert_called_once_with(
        remote_source_path, local_destination_path
    )


def test_pool_manager_upload(pycurl_pool_manager, mocker):
    pycurl_instance_mock = mocker.MagicMock()
    mocker.patch.object(
        pycurl_pool_manager,
        "acquire",
        return_value=mocker.MagicMock(
            __enter__=mocker.MagicMock(return_value=pycurl_instance_mock),
            __exit__=mocker.MagicMock(),
        ),
    )

    local_source_path = "test.txt"
    remote_destination_path = "/test.txt"

    pycurl_pool_manager.upload(local_source_path, remote_destination_path)

    pycurl_instance_mock.upload.assert_called_once_with(
        local_source_path, remote_destination_path
    )


def test_upload_special_symbol_files_to_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path, filenames_with_symbols
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    file_contents_by_remote_path = {}
    with contextlib.closing(
        PycURL(connection_parameters=connection_parameters)
    ) as pycurl_client:
        for index, name in enumerate(filenames_with_symbols):
            content = "content # {0!s}".format(index)
            local_source_path = tmp_path / name
            local_source_path.write_text(content, encoding="utf-8")
            remote_destination_path = "/" + name
            file_contents_by_remote_path[remote_destination_path] = content
            pycurl_client.upload(str(local_source_path), remote_destination_path)

        for remote_path, content in file_contents_by_remote_path.items():
            server_path = pathlib.Path(ftp_server.home) / remote_path.lstrip("/")
            assert server_path.read_text(encoding="utf-8") == content


def test_download_special_symbol_files_from_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path, filenames_with_symbols
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    file_contents_by_remote_path = {}
    with contextlib.closing(
        PycURL(connection_parameters=connection_parameters)
    ) as pycurl_client:
        for index, name in enumerate(filenames_with_symbols):
            content = "content # {0!s}".format(index)
            remote_path = "/" + name
            file_contents_by_remote_path[remote_path] = content
            server_path = pathlib.Path(ftp_server.home) / remote_path.lstrip("/")
            server_path.write_text(content, encoding="utf-8")

        for index, (remote_path, content) in enumerate(
            file_contents_by_remote_path.items()
        ):
            local_destination_path = tmp_path / "download_{0!s}.txt".format(index)
            size_bytes = pycurl_client.download(
                remote_path, str(local_destination_path)
            )

            assert size_bytes == len(content.encode("utf-8"))
            assert local_destination_path.read_text(encoding="utf-8") == content


def test_upload_files_to_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    file_contents_by_remote_path = {}
    with contextlib.closing(
        PycURL(connection_parameters=connection_parameters)
    ) as pycurl_client:
        for index in range(10):
            content = "content # {0!s}".format(index)
            local_source_path = tmp_path / "{0!s}.txt".format(index)
            local_source_path.write_text(content, encoding="utf-8")
            remote_destination_path = "/" + local_source_path.name
            file_contents_by_remote_path[remote_destination_path] = content
            pycurl_client.upload(str(local_source_path), remote_destination_path)

        for remote_path, content in file_contents_by_remote_path.items():
            server_path = pathlib.Path(ftp_server.home) / remote_path.lstrip("/")
            assert server_path.read_text(encoding="utf-8") == content


def test_download_files_from_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    file_contents_by_remote_path = {}
    with contextlib.closing(
        PycURL(connection_parameters=connection_parameters)
    ) as pycurl_client:
        for index in range(10):
            content = "content # {0!s}".format(index)
            file_name = "{0!s}.txt".format(index)
            remote_destination_path = "/" + file_name
            file_contents_by_remote_path[remote_destination_path] = content
            server_path = pathlib.Path(
                ftp_server.home
            ) / remote_destination_path.lstrip("/")
            server_path.write_text(content, encoding="utf-8")

        for remote_path, content in file_contents_by_remote_path.items():
            local_destination_path = tmp_path / pathlib.PurePosixPath(remote_path).name
            size_bytes = pycurl_client.download(
                remote_path, str(local_destination_path)
            )

            assert size_bytes == len(content.encode("utf-8"))
            assert local_destination_path.read_text(encoding="utf-8") == content


def test_upload_and_download_rush_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    with contextlib.closing(
        PycURL(connection_parameters=connection_parameters)
    ) as pycurl_client:
        upload_one_content = "content # 1"
        upload_one_source_path = tmp_path / "1.txt"
        upload_one_source_path.write_text(upload_one_content, encoding="utf-8")
        upload_one_destination_path = "/1.txt"
        pycurl_client.upload(str(upload_one_source_path), upload_one_destination_path)

        download_source_path = "/2.txt"
        download_content = "content # 2"
        server_path = pathlib.Path(ftp_server.home) / download_source_path.lstrip("/")
        server_path.write_text(download_content, encoding="utf-8")
        download_destination_path = tmp_path / "rush_downloaded.txt"
        pycurl_client.download(download_source_path, str(download_destination_path))

        upload_two_content = "content # 3"
        upload_two_source_path = tmp_path / "3.txt"
        upload_two_source_path.write_text(upload_two_content, encoding="utf-8")
        upload_two_destination_path = "/3.txt"
        pycurl_client.upload(str(upload_two_source_path), upload_two_destination_path)

        server_upload_one_path = pathlib.Path(
            ftp_server.home
        ) / upload_one_destination_path.lstrip("/")
        server_upload_two_path = pathlib.Path(
            ftp_server.home
        ) / upload_two_destination_path.lstrip("/")

        assert download_destination_path.read_text(encoding="utf-8") == download_content
        assert server_upload_one_path.read_text(encoding="utf-8") == upload_one_content
        assert server_upload_two_path.read_text(encoding="utf-8") == upload_two_content


def test_pool_manager_upload_files_to_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    file_contents_by_remote_path = {}
    with contextlib.closing(
        PycURLPoolManager(connection_parameters=connection_parameters)
    ) as pool_manager:
        for index in range(10):
            content = "content # {0!s}".format(index)
            local_source_path = tmp_path / "{0!s}.txt".format(index)
            local_source_path.write_text(content, encoding="utf-8")
            remote_destination_path = "/" + local_source_path.name
            file_contents_by_remote_path[remote_destination_path] = content
            size_bytes = pool_manager.upload(
                str(local_source_path), remote_destination_path
            )

            assert size_bytes == len(content.encode("utf-8"))

        for remote_path, content in file_contents_by_remote_path.items():
            server_path = pathlib.Path(ftp_server.home) / remote_path.lstrip("/")
            assert server_path.read_text(encoding="utf-8") == content


def test_pool_manager_download_files_from_file_transfer_protocol_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    file_contents_by_remote_path = {}
    with contextlib.closing(
        PycURLPoolManager(connection_parameters=connection_parameters)
    ) as pool_manager:
        for index in range(10):
            content = "content # {0!s}".format(index)
            file_name = "{0!s}.txt".format(index)
            remote_destination_path = "/" + file_name
            file_contents_by_remote_path[remote_destination_path] = content
            server_path = pathlib.Path(
                ftp_server.home
            ) / remote_destination_path.lstrip("/")
            server_path.write_text(content, encoding="utf-8")

        for remote_path, content in file_contents_by_remote_path.items():
            local_destination_path = tmp_path / pathlib.PurePosixPath(remote_path).name
            size_bytes = pool_manager.download(remote_path, str(local_destination_path))

            assert size_bytes == len(content.encode("utf-8"))
            assert local_destination_path.read_text(encoding="utf-8") == content
