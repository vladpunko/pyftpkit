# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio
import ftplib
import logging
import time

import pytest

from pyftpkit._pool import FTPPoolExecutor
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
            "max_connections": 10,
            "max_workers": 20,
            "timeout": 2,
        }
    )


def test_connect_with_error(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            pool._connect()

    message = "Unable to create a new connection."
    assert message in caplog.text

    message = "Could not open an FTP connection to: {0!s}:{1!s}".format(
        connection_parameters.host,
        connection_parameters.port,
    )
    assert message in str(err.value)


def test_connect(caplog, connection_parameters, ftp_server):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pool._connect()

    message = "FTP connection has been created: {0!s}:{1!s}".format(
        connection_parameters.host,
        connection_parameters.port,
    )
    assert message in caplog.text


@pytest.mark.asyncio
async def test_open_connections(caplog, connection_parameters, ftp_server):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        async with FTPPoolExecutor(connection_parameters=connection_parameters) as pool:
            assert pool._pool.qsize() == connection_parameters.max_connections
            assert len(pool._connections) == connection_parameters.max_connections

    message = "FTP connection pool has been initialized with {0!s} connections.".format(
        connection_parameters.max_connections
    )
    assert message in caplog.text


@pytest.mark.asyncio
async def test_open_connections_timeout(mocker, caplog, connection_parameters):
    def _connect(*args, **kwargs):
        time.sleep(5)

    mocker.patch("pyftpkit._pool.FTPPoolExecutor._connect", new=_connect)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            async with FTPPoolExecutor(connection_parameters=connection_parameters):
                pass

    message = "FTP connection pool failed to initialize within the timeout period."
    assert message in caplog.text

    message = "FTP connection pool initialization timed out."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_open_only_once(mocker, connection_parameters, ftp_server):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    connection_parameters.max_connections = 2
    connect_mock = mocker.patch("pyftpkit._pool.FTPPoolExecutor._connect")

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    await pool.open()
    await pool.open()

    assert connect_mock.call_count == 2


@pytest.mark.asyncio
async def test_get_connection_no_pool(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await pool.get()

    message = "There is no active connection pool to acquire an FTP connection from."
    assert message in caplog.text

    message = "Connection pool is not initialized or is closed."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_release_no_pool(caplog, ftp_server, connection_parameters):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    ftp = pool._connect()
    pool._connections.add(ftp)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            await pool.release(ftp)

    message = "No active connection pool available to release the FTP connection."
    assert message in caplog.text

    message = "FTP connection pool does not exist or is closed."
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_release_not_tracked_connection(
    caplog, ftp_server, connection_parameters
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    await pool.open()

    ftp = pool._connect()
    with caplog.at_level(logging.WARNING, logger="pyftpkit"):
        await pool.release(ftp)

    message = "Released FTP connection was not tracked."
    assert message in caplog.text


def test_close_connection(mocker, ftp_server, connection_parameters):
    ftp_mock = mocker.Mock()

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(ftp_mock)

    ftp_mock.quit.assert_called_once()
    ftp_mock.close.assert_not_called()


def test_close_connection_with_exceptions(
    caplog, mocker, ftp_server, connection_parameters
):
    ftp_mock = mocker.Mock()
    ftp_mock.quit.side_effect = ftplib.error_temp("error")
    ftp_mock.close.side_effect = ftplib.error_perm("error")

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as err:
            pool._close_connection(ftp_mock)

    ftp_mock.quit.assert_called_once()
    ftp_mock.close.assert_called_once()

    message = "Unable to close the FTP connection safely."
    assert message in caplog.text

    message = "Failed to safely close the FTP connection to: {0!s}:{1!s}".format(
        connection_parameters.host,
        connection_parameters.port,
    )
    assert message in str(err.value)


@pytest.mark.asyncio
async def test_close_no_pool(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        await pool.close()

    message = "No pool to close."
    assert message in caplog.text


@pytest.mark.asyncio
async def test_close_only_once(mocker, ftp_server, connection_parameters):
    close_connection_mock = mocker.patch(
        "pyftpkit._pool.FTPPoolExecutor._close_connection"
    )

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    connection_parameters.max_connections = 2
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    await pool.open()
    await pool.close()
    await pool.close()

    assert close_connection_mock.call_count == 2


@pytest.mark.asyncio
async def test_close(caplog, ftp_server, connection_parameters):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    await pool.open()

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        await pool.close()

    message = "All FTP connections in the pool and tracked set have been closed."
    assert message in caplog.text

    assert not pool._connections
    assert pool._pool.qsize() == 0


@pytest.mark.asyncio
async def test_ensure_lock_creates_lock(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pool._ensure_lock()

    message = "A new pool lock has been created and bound to the current event loop."
    assert message in caplog.text

    assert isinstance(pool._lock, asyncio.Lock)


def test_ensure_lock_no_running_loop(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as err:
            pool._ensure_lock()

    message = "No running event loop was detected."
    assert message in caplog.text

    message = f"{type(pool).__name__!s} requires an active event loop to open."
    assert message in str(err.value)
