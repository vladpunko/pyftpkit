# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-26

import io
import logging
import pathlib
import queue
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
def pycurl_instance(connection_parameters):
    return PycURL(connection_parameters=connection_parameters)


@pytest.fixture
def pycurl_pool_manager(connection_parameters):
    return PycURLPoolManager(connection_parameters=connection_parameters)


def test_ensure_ftp_url_no_changes(host, port, pycurl_instance):
    url = f"ftp://{host!s}:{port!s}/1/2/3/test.txt"

    assert pycurl_instance._ensure_ftp_url(url) == url


def test_ensure_ftp_url_add_schema(host, port, pycurl_instance):
    url = "/1/2/3/test.txt"

    assert pycurl_instance._ensure_ftp_url(url) == f"ftp://{host!s}:{port!s}{url!s}"


def test_ensure_ftp_url_special_symbols(host, port, pycurl_instance):
    url = "#basket"

    assert pycurl_instance._ensure_ftp_url(url) == f"ftp://{host!s}:{port!s}/%23basket"


def test_ensure_ftp_url_root_path(host, port, pycurl_instance):
    assert pycurl_instance._ensure_ftp_url("/") == f"ftp://{host!s}:{port!s}/"


def test_ensure_ftp_url_collapses_leading_slashes(host, port, pycurl_instance):
    url = "///1/2/3/test.txt"

    assert (
        pycurl_instance._ensure_ftp_url(url)
        == f"ftp://{host!s}:{port!s}/1/2/3/test.txt"
    )


def test_ensure_ftp_url_preserves_trailing_whitespace(host, port, pycurl_instance):
    url = "/1/2/3/test.txt  \t"

    assert (
        pycurl_instance._ensure_ftp_url(url)
        == f"ftp://{host!s}:{port!s}/1/2/3/test.txt%20%20%09"
    )


def test_ensure_ftp_url_no_port(host, connection_parameters):
    connection_parameters.port = 0  # reset port
    curl = PycURL(connection_parameters=connection_parameters)

    url = "1/2/test.txt"

    assert curl._ensure_ftp_url(url) == f"ftp://{host!s}/{url!s}"


def test_connection_parameters_extra_options(connection_parameters, pycurl_mock):
    connection_parameters.extra_options = {
        pycurl.VERBOSE: 1,
    }

    PycURL(connection_parameters=connection_parameters)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.VERBOSE, 1)


def test_download_no_permissions(caplog, fs_no_root, pycurl_instance):
    path = pathlib.Path("/test")
    path.mkdir()
    path.chmod(0o000)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pycurl_instance.download("/test.txt", str(path / "documents" / "test.txt"))

    message = "Failed to create a new directory on the current machine."
    assert message in caplog.text

    message = "Could not create target directory: {0!r}".format(str(path / "documents"))
    assert message in str(err.value)


def test_download(
    caplog,
    fs_no_root,
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
    dst = str(dst / "text.txt")

    size = 1024
    pycurl_mock.return_value.getinfo.return_value = size

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        size_bytes = pycurl_instance.download(src, dst)
    assert size_bytes == size

    url = f"ftp://{host!s}:{port!s}{src!s}"

    message = f"Starting FTP download of '{url!s}' to '{dst!s}' on the local machine."
    assert message in caplog.text

    message = (
        "Finished moving {0!s} bytes from the FTP server '{1!s}' to '{2!s}'.".format(
            size, url, dst
        )
    )
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.USERPWD, "{0!s}:{1!s}".format(username, password)),
        mock.call(pycurl.FORBID_REUSE, 0),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.URL, url),
        mock.call(pycurl.WRITEFUNCTION, mock.ANY),
        mock.call(pycurl.WRITEFUNCTION, mock.ANY),
    ]
    pycurl_mock.return_value.setopt.assert_has_calls(expected_calls, any_order=False)
    pycurl_mock.return_value.perform.assert_called_once()


@pytest.mark.parametrize(
    "src, dst",
    [
        (None, "dst"),
        ("src", None),
    ],
)
def test_download_validation_type_errors(caplog, pycurl_instance, src, dst):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as err:
            pycurl_instance.download(src, dst)

    message = "The source and destination paths must both be strings."
    assert message in caplog.text

    message = (
        "Source and destination paths are required to be strings."
        "\nSource {0!r} has type: {1!s}"
        "\nDestination {2!r} has type: {3!s}".format(
            src,
            type(src).__name__,
            dst,
            type(dst).__name__,
        )
    )
    assert message in str(err.value)


@pytest.mark.parametrize(
    "src, dst",
    [
        ("", "dst"),
        (" ", "dst"),
    ],
)
def test_download_validation_source_value_errors(caplog, pycurl_instance, src, dst):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as err:
            pycurl_instance.download(src, dst)

    message = "The source path cannot be empty or whitespace."
    assert message in caplog.text

    message = "The source path must not be empty or consist only of whitespace."
    assert message in str(err.value)


@pytest.mark.parametrize(
    "src, dst",
    [
        ("/src", ""),
        ("/src", " "),
    ],
)
def test_download_validation_destination_value_errors(
    caplog, pycurl_instance, src, dst
):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as err:
            pycurl_instance.download(src, dst)

    message = "The destination path cannot be empty or whitespace."
    assert message in caplog.text

    message = "The destination path must not be empty or consist only of whitespace."
    assert message in str(err.value)


def test_download_validation_no_root_slash(caplog, pycurl_instance):
    src = "src"

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathNotAbsoluteError) as err:
            pycurl_instance.download(src, "dst")

    message = "The source path is not absolute and does not start from the root."
    assert message in caplog.text

    message = f"Ambiguous source path: {src!r}"
    assert message in str(err.value)


def test_download_trailing_whitespace_preserves_remote_path(
    fs_no_root, pycurl_mock, connection_parameters, host, port
):
    src = "/1/2/3/text.txt   "
    dst = "text.txt"
    url = f"ftp://{host!s}:{port!s}/1/2/3/text.txt%20%20%20"

    curl = PycURL(connection_parameters=connection_parameters)
    curl.download(src, dst)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, url)


def test_download_trailing_tabs_preserves_remote_path(
    fs_no_root, pycurl_mock, connection_parameters, host, port
):
    src = "/1/2/3/text.txt\t\t"
    dst = "tabbed.txt"
    url = f"ftp://{host!s}:{port!s}/1/2/3/text.txt%09%09"

    curl = PycURL(connection_parameters=connection_parameters)
    curl.download(src, dst)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, url)


def test_download_with_error(
    caplog, fs_no_root, host, port, pycurl_instance, pycurl_mock
):
    src = "/text.txt"
    dst = pathlib.Path("text.txt")
    dst.write_text("test", encoding="utf-8")

    pycurl_mock.return_value.perform.side_effect = pycurl.error("error")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            pycurl_instance.download(src, str(dst))

    assert not dst.exists()

    message = "An unexpected error occurred while fetching the data."
    assert message in caplog.text

    message = "Encountered an error while trying to fetch the data from: {0!r}".format(
        f"ftp://{host!s}:{port!s}{src!s}"
    )
    assert message in str(err.value)


def test_download_resets_write_function_on_error(
    fs_no_root, connection_parameters, pycurl_mock
):
    curl = PycURL(connection_parameters=connection_parameters)

    src = "/text.txt"
    dst = pathlib.Path("text.txt")
    dst.write_text("test", encoding="utf-8")

    pycurl_mock.return_value.perform.side_effect = pycurl.error("error")

    with pytest.raises(FTPError):
        curl.download(src, str(dst))

    last_call = pycurl_mock.return_value.setopt.call_args_list[-1]
    assert last_call == mock.call(pycurl.WRITEFUNCTION, mock.ANY)


def test_download_with_fs_error(caplog, fs_no_root, pycurl_instance, pycurl_mock):
    src = "/text.txt"
    dst = pathlib.Path("/test")
    dst.mkdir()
    dst = dst / "text.txt"
    dst.mkdir()
    dst = str(dst)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pycurl_instance.download(src, dst)

    message = "An error occurred while trying to write the buffer to disk."
    assert message in caplog.text

    message = f"Failed to write buffer data to: {str(dst)!r}"
    assert message in str(err.value)


def test_upload(
    caplog,
    fs_no_root,
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
    src.write_text("test", encoding="utf-8")
    dst = "/1/2/3/text.txt"

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pycurl_instance.upload(str(src), dst)

    url = f"ftp://{host!s}:{port!s}{dst!s}"

    message = (
        f"Uploading '{str(src)!s}' from local system to '{url!s}' on the FTP server."
    )
    assert message in caplog.text

    message = f"Finished uploading '{str(src)!s}' to '{url!s}' on the FTP server."
    assert message in caplog.text

    expected_calls = [
        mock.call(pycurl.CONNECTTIMEOUT, connection_parameters.timeout),
        mock.call(pycurl.USERPWD, f"{username}:{password}"),
        mock.call(pycurl.FORBID_REUSE, 0),
        mock.call(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD),
        mock.call(pycurl.FTP_USE_EPSV, 1),
        mock.call(pycurl.NOSIGNAL, 1),
        mock.call(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE),
        mock.call(pycurl.URL, url),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 1),
        mock.call(pycurl.INFILESIZE, src.stat().st_size),
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
    caplog, fs_no_root, host, port, pycurl_instance, pycurl_mock
):
    src = pathlib.Path("test.txt")
    src.write_text("", encoding="utf-8")
    dst = "/"

    pycurl_mock.return_value.perform.side_effect = pycurl.error("error")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            pycurl_instance.upload(str(src), dst)

    url = f"ftp://{host!s}:{port!s}{dst!s}"

    message = "File could not be uploaded to the FTP server."
    assert message in caplog.text

    message = f"Could not upload {str(src)!r} to {url!r} on FTP server."
    assert message in str(err.value)


def test_upload_resets_transfer_options_on_error(
    fs_no_root, connection_parameters, pycurl_mock
):
    curl = PycURL(connection_parameters=connection_parameters)

    src = pathlib.Path("test.txt")
    src.write_text("", encoding="utf-8")
    dst = "/"

    pycurl_mock.return_value.perform.side_effect = pycurl.error("error")

    with pytest.raises(FTPError):
        curl.upload(str(src), dst)

    expected_tail = [
        mock.call(pycurl.INFILESIZE, -1),
        mock.call(pycurl.READFUNCTION, mock.ANY),
        mock.call(pycurl.FTP_CREATE_MISSING_DIRS, 0),
        mock.call(pycurl.UPLOAD, 0),
    ]
    assert pycurl_mock.return_value.setopt.call_args_list[-4:] == expected_tail


@pytest.mark.parametrize(
    "src, dst, prepare",
    [
        ("/missing.txt", "/upload.txt", None),
        ("/test", "/", "mkdir"),
    ],
)
def test_upload_with_fs_error(
    caplog, fs_no_root, pycurl_mock, pycurl_instance, src, dst, prepare
):
    src_path = pathlib.Path(src)
    if prepare == "mkdir":
        src_path.mkdir()

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pycurl_instance.upload(str(src_path), dst)

    message = "File read operation failed on local system."
    assert message in caplog.text

    message = f"An error occurred while accessing the local file: {str(src_path)!r}."
    assert message in str(err.value)


@pytest.mark.parametrize(
    "src, dst",
    [
        (None, "dst"),
        ("src", None),
    ],
)
def test_upload_validation_type_errors(caplog, pycurl_instance, src, dst):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as err:
            pycurl_instance.upload(src, dst)

    message = "The source path and the destination path must each be a string."
    assert message in caplog.text

    message = (
        "Both the source and destination need to be strings."
        "\nSource {0!r} has type: {1!s}"
        "\nDestination {2!r} has type: {3!s}".format(
            src,
            type(src).__name__,
            dst,
            type(dst).__name__,
        )
    )
    assert message in str(err.value)


@pytest.mark.parametrize(
    "src, dst",
    [
        ("", "dst"),
        (" ", "dst"),
    ],
)
def test_upload_validation_source_value_errors(caplog, pycurl_instance, src, dst):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as err:
            pycurl_instance.upload(src, dst)

    message = "A source path of only whitespace is invalid."
    assert message in caplog.text

    message = "The source path must include at least one non-whitespace character."
    assert message in str(err.value)


@pytest.mark.parametrize(
    "src, dst",
    [
        ("/src", ""),
        ("/src", " "),
    ],
)
def test_upload_validation_destination_value_errors(caplog, pycurl_instance, src, dst):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathError) as err:
            pycurl_instance.upload(src, dst)

    message = "A destination path of only whitespace is invalid."
    assert message in caplog.text

    message = "The destination path cannot be empty or contain only blank characters."
    assert message in str(err.value)


def test_upload_validation_no_root_slash(caplog, pycurl_instance):
    dst = "dst"

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPPathNotAbsoluteError) as err:
            pycurl_instance.upload("src", dst)

    message = "The destination path is not absolute and does not start from the root."
    assert message in caplog.text

    message = f"Ambiguous destination path: {dst!r}"
    assert message in str(err.value)


def test_upload_trailing_whitespace_preserves_remote_path(
    fs_no_root, pycurl_mock, connection_parameters, host, port
):
    src = pathlib.Path("upload.txt")
    src.write_text("data", encoding="utf-8")
    src = str(src)
    dst = "/uploads/upload.txt   "
    url = f"ftp://{host!s}:{port!s}/uploads/upload.txt%20%20%20"

    curl = PycURL(connection_parameters=connection_parameters)
    curl.upload(src, dst)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, url)


def test_upload_trailing_tabs_preserves_remote_path(
    fs_no_root, pycurl_mock, connection_parameters, host, port
):
    src = pathlib.Path("upload_tabs.txt")
    src.write_text("data", encoding="utf-8")
    src = str(src)
    dst = "/uploads/upload_tabs.txt\t\t"
    url = f"ftp://{host!s}:{port!s}/uploads/upload_tabs.txt%09%09"

    curl = PycURL(connection_parameters=connection_parameters)
    curl.upload(src, dst)

    pycurl_mock.return_value.setopt.assert_any_call(pycurl.URL, url)


def test_pool_manager_initialization(connection_parameters):
    connection_parameters.max_connections = 4

    pool_manager = PycURLPoolManager(connection_parameters=connection_parameters)

    assert pool_manager._pool.maxsize == 2
    assert pool_manager._pool.qsize() == 2
    assert pool_manager._shutdown is False


def test_pool_manager_initialization_min_max(connection_parameters):
    connection_parameters.max_connections = 1

    pool_manager = PycURLPoolManager(connection_parameters)

    assert pool_manager._pool.maxsize == 1
    assert pool_manager._pool.qsize() == 1


def test_pool_manager_close(pycurl_pool_manager, mocker):
    curl_mock = mocker.MagicMock()

    # Replace instances with mocks inside pool.
    items = []
    while not pycurl_pool_manager._pool.empty():
        items.append(pycurl_pool_manager._pool.get())
    for _ in items:
        pycurl_pool_manager._pool.put(curl_mock)

    pycurl_pool_manager.close()

    assert pycurl_pool_manager._shutdown is True
    assert pycurl_pool_manager._pool.empty()
    curl_mock.close.assert_called()


def test_pool_manager_close_queue_empty(pycurl_pool_manager, mocker):
    mocker.patch.object(pycurl_pool_manager._pool, "empty", return_value=False)
    mocker.patch.object(
        pycurl_pool_manager._pool, "get_nowait", side_effect=queue.Empty
    )

    pycurl_pool_manager.close()

    assert pycurl_pool_manager._shutdown is True


def test_pool_manager_close_idempotent(pycurl_pool_manager):
    curl_mocks = []

    while not pycurl_pool_manager._pool.empty():
        pycurl_pool_manager._pool.get()

    for _ in range(pycurl_pool_manager._pool.maxsize):
        curl_mock = mock.MagicMock()
        curl_mocks.append(curl_mock)
        pycurl_pool_manager._pool.put(curl_mock)

    pycurl_pool_manager.close()
    pycurl_pool_manager.close()

    for curl_mock in curl_mocks:
        curl_mock.close.assert_called_once()


def test_pool_manager_acquire(pycurl_pool_manager):
    assert pycurl_pool_manager._pool.qsize() > 0

    with pycurl_pool_manager.acquire() as curl:
        assert isinstance(curl, PycURL)
        assert (
            pycurl_pool_manager._pool.qsize() == pycurl_pool_manager._pool.maxsize - 1
        )

    # Should be put back.
    assert pycurl_pool_manager._pool.qsize() == pycurl_pool_manager._pool.maxsize


def test_pool_manager_acquire_closed_pool_raises(pycurl_pool_manager):
    pycurl_pool_manager._shutdown = True

    with pytest.raises(RuntimeError) as err:
        with pycurl_pool_manager.acquire():
            pass

    message = "Cannot acquire from a closed pool."
    assert message in str(err.value)


def test_pool_manager_acquire_shutdown_while_waiting(pycurl_pool_manager, mocker):
    def _get(*args, **kwargs):
        pycurl_pool_manager._shutdown = True

        raise queue.Empty

    mocker.patch.object(pycurl_pool_manager._pool, "get", side_effect=_get)

    with pytest.raises(RuntimeError) as err:
        with pycurl_pool_manager.acquire():
            pass

    message = "Cannot acquire from a closed pool."
    assert message in str(err.value)


def test_pool_manager_acquire_retries_until_available(pycurl_pool_manager, mocker):
    curl_mock = mocker.MagicMock()
    get_mock = mocker.patch.object(
        pycurl_pool_manager._pool,
        "get",
        side_effect=[queue.Empty, curl_mock],
    )
    put_mock = mocker.patch.object(pycurl_pool_manager._pool, "put")

    with pycurl_pool_manager.acquire() as curl:
        assert curl is curl_mock

    assert get_mock.call_count == 2
    put_mock.assert_called_once_with(curl_mock)


def test_pool_manager_acquire_with_shutdown(pycurl_pool_manager, mocker):
    with pycurl_pool_manager.acquire() as curl:
        # Simulate an external thread closing the pool.
        pycurl_pool_manager.close()

        # Mock the instance's close method right before context exit.
        close_mock = mocker.patch.object(curl, "close")

    close_mock.assert_called_once()
    assert pycurl_pool_manager._pool.qsize() == 0


def test_pool_manager_acquire_returns_on_exception(pycurl_pool_manager):
    initial_size = pycurl_pool_manager._pool.qsize()

    with pytest.raises(ValueError):
        with pycurl_pool_manager.acquire():
            raise ValueError("error")

    assert pycurl_pool_manager._pool.qsize() == initial_size


def test_pool_manager_download(pycurl_pool_manager, mocker):
    curl_mock = mocker.MagicMock()
    mocker.patch.object(
        pycurl_pool_manager,
        "acquire",
        return_value=mocker.MagicMock(
            __enter__=mocker.MagicMock(return_value=curl_mock),
            __exit__=mocker.MagicMock(),
        ),
    )

    src = "/test.txt"
    dst = "test.txt"

    pycurl_pool_manager.download(src, dst)

    curl_mock.download.assert_called_once_with(src, dst)


def test_pool_manager_upload(pycurl_pool_manager, mocker):
    curl_mock = mocker.MagicMock()
    mocker.patch.object(
        pycurl_pool_manager,
        "acquire",
        return_value=mocker.MagicMock(
            __enter__=mocker.MagicMock(return_value=curl_mock),
            __exit__=mocker.MagicMock(),
        ),
    )

    src = "test.txt"
    dst = "/test.txt"

    pycurl_pool_manager.upload(src, dst)

    curl_mock.upload.assert_called_once_with(src, dst)


def test_upload_special_symbol_files_to_ftp_server(
    ftp_server, connection_parameters, tmp_path, filenames_with_symbols
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    curl = PycURL(connection_parameters=connection_parameters)

    files = {}
    try:
        for index, name in enumerate(filenames_with_symbols):
            content = f"content # {index!s}"
            src = tmp_path / name
            src.write_text(content, encoding="utf-8")
            dst = "/" + name
            files[dst] = content
            curl.upload(str(src), dst)

        for ftp_path, content in files.items():
            server_path = pathlib.Path(ftp_server.home) / ftp_path.lstrip("/")
            assert server_path.read_text(encoding="utf-8") == content
    finally:
        curl.close()


def test_download_special_symbol_files_from_ftp_server(
    ftp_server, connection_parameters, tmp_path, filenames_with_symbols
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    curl = PycURL(connection_parameters=connection_parameters)

    files = {}
    try:
        for index, name in enumerate(filenames_with_symbols):
            content = f"content # {index!s}"
            ftp_path = "/" + name
            files[ftp_path] = content
            server_path = pathlib.Path(ftp_server.home) / ftp_path.lstrip("/")
            server_path.write_text(content, encoding="utf-8")

        for index, (ftp_path, content) in enumerate(files.items()):
            path = tmp_path / f"download_{index!s}.txt"
            size_bytes = curl.download(ftp_path, str(path))

            assert size_bytes == len(content.encode("utf-8"))
            assert path.read_text(encoding="utf-8") == content
    finally:
        curl.close()


def test_upload_files_to_ftp_server(ftp_server, connection_parameters, tmp_path):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    curl = PycURL(connection_parameters=connection_parameters)

    files = {}
    try:
        for index in range(10):
            content = f"content # {index!s}"
            src = tmp_path / f"{index!s}.txt"
            src.write_text(content, encoding="utf-8")
            dst = "/" + src.name
            files[dst] = content
            curl.upload(str(src), dst)

        for ftp_path, content in files.items():
            server_path = pathlib.Path(ftp_server.home) / ftp_path.lstrip("/")
            assert server_path.read_text(encoding="utf-8") == content
    finally:
        curl.close()


def test_download_files_from_ftp_server(ftp_server, connection_parameters, tmp_path):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    curl = PycURL(connection_parameters=connection_parameters)

    files = {}
    try:
        for index in range(10):
            content = f"content # {index!s}"
            src = f"{index!s}.txt"
            dst = "/" + src
            files[dst] = content
            server_path = pathlib.Path(ftp_server.home) / dst.lstrip("/")
            server_path.write_text(content, encoding="utf-8")

        for ftp_path, content in files.items():
            path = tmp_path / pathlib.PurePosixPath(ftp_path).name
            size_bytes = curl.download(ftp_path, str(path))

            assert size_bytes == len(content.encode("utf-8"))
            assert path.read_text(encoding="utf-8") == content
    finally:
        curl.close()


def test_upload_download_rush_ftp_server(ftp_server, connection_parameters, tmp_path):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    curl = PycURL(connection_parameters=connection_parameters)

    upload_one_content = "content # 1"
    upload_one_src = tmp_path / "1.txt"
    upload_one_src.write_text(upload_one_content, encoding="utf-8")
    upload_one_dst = "/1.txt"
    curl.upload(str(upload_one_src), upload_one_dst)

    download_src = "/2.txt"
    download_content = "content # 2"
    server_path = pathlib.Path(ftp_server.home) / download_src.lstrip("/")
    server_path.write_text(download_content, encoding="utf-8")
    download_dst = tmp_path / "rush_downloaded.txt"
    curl.download(download_src, str(download_dst))

    upload_two_content = "content # 3"
    upload_two_src = tmp_path / "3.txt"
    upload_two_src.write_text(upload_two_content, encoding="utf-8")
    upload_two_dst = "/3.txt"
    curl.upload(str(upload_two_src), upload_two_dst)

    server_upload_one = pathlib.Path(ftp_server.home) / upload_one_dst.lstrip("/")
    server_upload_two = pathlib.Path(ftp_server.home) / upload_two_dst.lstrip("/")

    assert download_dst.read_text(encoding="utf-8") == download_content
    assert server_upload_one.read_text(encoding="utf-8") == upload_one_content
    assert server_upload_two.read_text(encoding="utf-8") == upload_two_content

    curl.close()


def test_pool_manager_upload_files_to_ftp_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    pool_manager = PycURLPoolManager(connection_parameters=connection_parameters)

    files = {}
    try:
        for index in range(10):
            content = f"content # {index!s}"
            src = tmp_path / f"{index!s}.txt"
            src.write_text(content, encoding="utf-8")
            dst = "/" + src.name
            files[dst] = content
            pool_manager.upload(str(src), dst)

        for ftp_path, content in files.items():
            server_path = pathlib.Path(ftp_server.home) / ftp_path.lstrip("/")
            assert server_path.read_text(encoding="utf-8") == content
    finally:
        pool_manager.close()


def test_pool_manager_download_files_from_ftp_server(
    ftp_server, connection_parameters, tmp_path
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    pool_manager = PycURLPoolManager(connection_parameters=connection_parameters)

    files = {}
    try:
        for index in range(10):
            content = f"content # {index!s}"
            src = f"{index!s}.txt"
            dst = "/" + src
            files[dst] = content
            server_path = pathlib.Path(ftp_server.home) / dst.lstrip("/")
            server_path.write_text(content, encoding="utf-8")

        for ftp_path, content in files.items():
            path = tmp_path / pathlib.PurePosixPath(ftp_path).name
            pool_manager.download(ftp_path, str(path))
            assert path.read_text(encoding="utf-8") == content
    finally:
        pool_manager.close()
