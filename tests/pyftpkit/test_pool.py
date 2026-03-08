# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-28

import asyncio
import ftplib
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from pyftpkit._ftp import FTP
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


def test_connect_raises_error_and_logs(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as error:
            pool._connect()

    message = "Unable to create a new connection."
    assert message in caplog.text

    message = "Could not open an FTP connection to: {0!s}:{1!s}".format(
        connection_parameters.host,
        connection_parameters.port,
    )
    assert message in str(error.value)


def test_connect_logs_success(caplog, connection_parameters, ftp_server):
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


def test_executor_property_uses_injected_executor(connection_parameters):
    executor = ThreadPoolExecutor(max_workers=1)
    pool = FTPPoolExecutor(
        connection_parameters=connection_parameters, executor=executor
    )

    assert pool.executor is executor
    assert not pool._owns_executor

    executor.shutdown()


@pytest.mark.asyncio
async def test_open_initializes_pool_and_logs(
    caplog, connection_parameters, ftp_server
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    expected_size = max(1, connection_parameters.max_connections)

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        async with FTPPoolExecutor(connection_parameters=connection_parameters) as pool:
            assert pool._pool.qsize() == expected_size
            assert len(pool._connections) == expected_size

    message = "FTP connection pool has been initialized with {0!s} connections.".format(
        expected_size
    )

    assert message in caplog.text


@pytest.mark.asyncio
async def test_open_times_out_and_logs_error(mocker, caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    mocker.patch.object(pool, "_connect", return_value=FTP())
    wait_for_mock = mocker.patch(
        "pyftpkit._pool.asyncio.wait_for",
        side_effect=asyncio.TimeoutError(),
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as error:
            await pool.open()

    message = "FTP connection pool failed to initialize within the timeout period."
    assert message in caplog.text

    message = "FTP connection pool initialization timed out."
    assert message in str(error.value)

    assert wait_for_mock.called


@pytest.mark.asyncio
async def test_open_wraps_unexpected_error(caplog, mocker, connection_parameters):
    def _connect(*args, **kwargs):
        raise ValueError("unexpected connection error")

    mocker.patch("pyftpkit._pool.FTPPoolExecutor._connect", new=_connect)

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as error:
            await pool.open()

    message = "Unable to initialize the connection pool."
    assert message in caplog.text

    message = "Error occurred while initializing the FTP connection pool."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_open_closes_connections_after_error(
    mocker, caplog, connection_parameters
):
    connection_parameters.max_connections = 2
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    ftp_connection = FTP()

    connect_mock = mocker.Mock(side_effect=[ftp_connection, FTPError("connect failed")])
    mocker.patch.object(pool, "_connect", connect_mock)
    close_mock = mocker.patch.object(pool, "_close_connection")

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPError) as error:
            await pool.open()

    close_mock.assert_called_once_with(ftp_connection)

    message = "Unable to initialize the connection pool."
    assert message in caplog.text

    assert "connect failed" in str(error.value)


@pytest.mark.asyncio
async def test_open_does_not_reinitialize_when_called_twice(
    mocker, connection_parameters, ftp_server
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    connection_parameters.max_connections = 2

    connect_mock = mocker.patch("pyftpkit._pool.FTPPoolExecutor._connect")

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    await pool.open()
    await pool.open()

    assert connect_mock.call_count == connection_parameters.max_connections


@pytest.mark.asyncio
async def test_open_returns_early_when_double_checked_lock_detects_open_pool(
    mocker, connection_parameters
):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    event = asyncio.Event()

    async def _open_connections():
        await event.wait()

        pool._closed = False

    mocker.patch.object(pool, "_open_connections", side_effect=_open_connections)

    first = asyncio.create_task(pool.open())
    await asyncio.sleep(0)
    second = asyncio.create_task(pool.open())
    await asyncio.sleep(0)
    event.set()
    await asyncio.gather(first, second)

    assert pool._closed is False


@pytest.mark.asyncio
async def test_get_raises_when_pool_missing(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            await pool.get()

    message = "There is no active connection pool to acquire an FTP connection from."
    assert message in caplog.text

    message = "Connection pool is not initialized or is closed."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_release_logs_warning_when_pool_missing(
    caplog, mocker, ftp_server, connection_parameters
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    ftp_connection = pool._connect()
    close_mock = mocker.patch.object(pool, "_close_connection")

    with caplog.at_level(logging.WARNING, logger="pyftpkit"):
        await pool.release(ftp_connection)

    message = "No active connection pool available to release the FTP connection."
    assert message in caplog.text

    close_mock.assert_called_once_with(ftp_connection)


@pytest.mark.asyncio
async def test_release_logs_warning_for_untracked_connection(
    caplog, mocker, ftp_server, connection_parameters
):
    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    await pool.open()

    ftp_connection = pool._connect()
    close_mock = mocker.patch.object(pool, "_close_connection")

    with caplog.at_level(logging.WARNING, logger="pyftpkit"):
        await pool.release(ftp_connection)

    message = "Released FTP connection was not tracked."
    assert message in caplog.text

    close_mock.assert_called_once_with(ftp_connection)


def test_close_connection_quits_cleanly(mocker, ftp_server, connection_parameters):
    ftp_mock = mocker.Mock()
    ftp_mock.sock = object()
    ftp_mock.file = mocker.Mock(closed=False)

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(ftp_mock)

    ftp_mock.quit.assert_called_once()
    ftp_mock.close.assert_not_called()


def test_close_connection_raises_when_quit_and_close_fail(
    caplog, mocker, ftp_server, connection_parameters
):
    ftp_mock = mocker.Mock()
    ftp_mock.sock = object()
    ftp_mock.file = mocker.Mock(closed=False)
    ftp_mock.quit.side_effect = ftplib.error_temp("temporary quit error")
    ftp_mock.close.side_effect = ftplib.error_perm("permanent close error")

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as error:
            pool._close_connection(ftp_mock)

    ftp_mock.quit.assert_called_once()
    ftp_mock.close.assert_called_once()

    message = "Unable to close the FTP connection safely."
    assert message in caplog.text

    message = "Failed to safely close the FTP connection to: {0!s}:{1!s}".format(
        connection_parameters.host,
        connection_parameters.port,
    )
    assert message in str(error.value)


def test_close_connection_skips_closed_socket(
    mocker, ftp_server, connection_parameters
):
    ftp_connection_mock = mocker.Mock()
    ftp_connection_mock.sock = None
    ftp_connection_mock.file = None

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(ftp_connection_mock)

    ftp_connection_mock.quit.assert_not_called()
    ftp_connection_mock.close.assert_not_called()


def test_close_connection_skips_missing_file_handle(
    mocker, ftp_server, connection_parameters
):
    ftp_connection_mock = mocker.Mock()
    ftp_connection_mock.sock = object()
    ftp_connection_mock.file = None

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(ftp_connection_mock)

    ftp_connection_mock.quit.assert_not_called()
    ftp_connection_mock.close.assert_not_called()


def test_close_connection_closes_when_file_handle_is_invalid(
    mocker, ftp_server, connection_parameters
):
    ftp_connection_mock = mocker.Mock()
    ftp_connection_mock.sock = object()
    ftp_connection_mock.file = object()
    ftp_connection_mock.quit.side_effect = ValueError("quit failed with invalid handle")

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(ftp_connection_mock)

    ftp_connection_mock.quit.assert_called_once()
    ftp_connection_mock.close.assert_called_once()


@pytest.mark.asyncio
async def test_close_raises_when_pool_missing(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await pool.close()

    message = "There is no active connection pool available to close."
    assert message in caplog.text

    message = "The connection pool is either inactive or previously closed."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_close_does_not_close_twice(mocker, ftp_server, connection_parameters):
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

    assert close_connection_mock.call_count == connection_parameters.max_connections


@pytest.mark.asyncio
async def test_close_logs_and_clears_pool(caplog, ftp_server, connection_parameters):
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
async def test_close_handles_queue_empty_race_condition(connection_parameters):
    class _FakeQueue:
        def __init__(self):
            self._used = False

        def empty(self):
            if not self._used:
                return False

            return True

        def get_nowait(self):
            self._used = True

            raise asyncio.QueueEmpty

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = _FakeQueue()
    pool._closed = False

    await pool.close()


@pytest.mark.asyncio
async def test_close_does_not_shutdown_external_executor(mocker, connection_parameters):
    executor = ThreadPoolExecutor(max_workers=1)
    pool = FTPPoolExecutor(
        connection_parameters=connection_parameters,
        executor=executor,
    )
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    shutdown_mock = mocker.patch.object(executor, "shutdown", wraps=executor.shutdown)

    await pool.close()

    shutdown_mock.assert_not_called()
    executor.shutdown()


@pytest.mark.asyncio
async def test_close_shuts_down_owned_executor(mocker, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    shutdown_mock = mocker.patch.object(
        pool._executor, "shutdown", wraps=pool._executor.shutdown
    )
    to_thread_mock = mocker.AsyncMock(
        side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
    )
    mocker.patch("asyncio.to_thread", to_thread_mock)

    await pool.close()

    to_thread_mock.assert_called_once()
    shutdown_mock.assert_called_once()


@pytest.mark.asyncio
async def test_close_logs_close_errors(mocker, caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    ftp_mock = mocker.Mock()
    pool._connections.add(ftp_mock)

    close_mock = mocker.patch.object(
        pool, "_close_connection", side_effect=FTPError("close failed")
    )

    loop = asyncio.get_running_loop()
    run_in_executor_mock = mocker.AsyncMock(
        side_effect=lambda executor, func, *args: func(*args)
    )
    mocker.patch.object(loop, "run_in_executor", run_in_executor_mock)

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        await pool.close()

    close_mock.assert_called_once_with(ftp_mock)

    message = "Failed to close an FTP connection."
    assert message in caplog.text


@pytest.mark.asyncio
async def test_get_reconnects_stale_connection(mocker, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    stale_ftp_connection_mock = mocker.Mock()
    stale_ftp_connection_mock.sock = object()
    stale_ftp_connection_mock.file = mocker.Mock(closed=False)
    stale_ftp_connection_mock.voidcmd.side_effect = ftplib.error_temp(
        "stale connection"
    )
    new_ftp_connection_mock = mocker.Mock()

    pool._connections.add(stale_ftp_connection_mock)
    await pool._pool.put(stale_ftp_connection_mock)

    mocker.patch.object(pool, "_connect", return_value=new_ftp_connection_mock)

    loop = asyncio.get_running_loop()
    run_in_executor_mock = mocker.AsyncMock(
        side_effect=lambda executor, func, *args: func(*args)
    )
    mocker.patch.object(loop, "run_in_executor", run_in_executor_mock)

    ftp_connection = await pool.get()

    assert ftp_connection is new_ftp_connection_mock
    assert new_ftp_connection_mock in pool._connections
    stale_ftp_connection_mock.quit.assert_called_once()


@pytest.mark.asyncio
async def test_get_returns_healthy_connection(mocker, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)
    await pool._pool.put(ftp_connection_mock)

    loop = asyncio.get_running_loop()
    run_in_executor_mock = mocker.AsyncMock(
        side_effect=lambda executor, func, *args: func(*args)
    )
    mocker.patch.object(loop, "run_in_executor", run_in_executor_mock)

    ftp_connection = await pool.get()

    assert ftp_connection is ftp_connection_mock
    ftp_connection_mock.voidcmd.assert_called_once()


@pytest.mark.asyncio
async def test_release_returns_connection_to_pool(mocker, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)

    await pool.release(ftp_connection_mock)

    assert pool._pool.qsize() == 1


@pytest.mark.asyncio
async def test_acquire_context_releases_connection(mocker, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = asyncio.Queue()
    pool._closed = False

    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)
    await pool._pool.put(ftp_connection_mock)

    async with pool.acquire() as connection:
        assert connection is ftp_connection_mock

    assert pool._pool.qsize() == 1


@pytest.mark.asyncio
async def test_open_logs_generic_error(mocker, caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    gather_mock = mocker.patch(
        "asyncio.gather", side_effect=RuntimeError("unexpected gather error")
    )

    with caplog.at_level(logging.ERROR, logger="pyftpkit"):
        with pytest.raises(FTPError) as error:
            await pool.open()

    assert gather_mock.called

    message = "Unable to create the FTP connection pool."
    assert message in caplog.text

    message = "Error occurred while initializing the FTP connection pool."
    assert message in str(error.value)


@pytest.mark.asyncio
async def test_ensure_lock_creates_new_lock(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.DEBUG, logger="pyftpkit"):
        pool._ensure_lock()

    message = "A new pool lock has been created and bound to the current event loop."
    assert message in caplog.text

    assert isinstance(pool._lock, asyncio.Lock)


def test_ensure_lock_raises_without_running_loop(caplog, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(RuntimeError) as error:
            pool._ensure_lock()

    message = "No running event loop was detected."
    assert message in caplog.text

    message = "{0!s} requires an active event loop to open.".format(type(pool).__name__)
    assert message in str(error.value)


async def _ensure_lock_twice(pool):
    """Helper to verify the same lock instance is reused across calls."""
    pool._ensure_lock()
    first_lock = pool._lock
    pool._ensure_lock()
    second_lock = pool._lock

    assert first_lock is second_lock


def test_ensure_lock_reuses_existing_lock(connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_ensure_lock_twice(pool))
    finally:
        loop.close()


@pytest.mark.asyncio
async def test_release_closes_connection_without_event_loop(
    mocker, connection_parameters
):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    ftp_connection_mock = mocker.Mock()
    close_mock = mocker.patch.object(pool, "_close_connection")
    mocker.patch(
        "asyncio.get_running_loop",
        side_effect=RuntimeError("no running event loop"),
    )

    await pool.release(ftp_connection_mock)

    close_mock.assert_called_once_with(ftp_connection_mock)


@pytest.mark.asyncio
async def test_release_closes_connection_when_loop_closed(
    mocker, connection_parameters
):
    class _Loop:
        def is_closed(self):
            return True

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    ftp_connection_mock = mocker.Mock()
    close_mock = mocker.patch.object(pool, "_close_connection")
    mocker.patch("asyncio.get_running_loop", return_value=_Loop())

    await pool.release(ftp_connection_mock)

    close_mock.assert_called_once_with(ftp_connection_mock)


@pytest.mark.asyncio
async def test_release_closes_connection_when_queue_put_fails_after_loop_closed(
    mocker, connection_parameters
):
    class _Loop:
        def __init__(self):
            self.calls = 0

        def is_closed(self):
            self.calls += 1
            return self.calls > 1

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = mocker.AsyncMock()
    pool._closed = False

    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)

    pool._pool.put.side_effect = RuntimeError("queue closed during release")
    mocker.patch("asyncio.get_running_loop", return_value=_Loop())
    close_mock = mocker.patch.object(pool, "_close_connection")

    await pool.release(ftp_connection_mock)

    close_mock.assert_called_once_with(ftp_connection_mock)


@pytest.mark.asyncio
async def test_release_raises_when_queue_put_fails_with_open_loop(
    mocker, connection_parameters, caplog
):
    class _Loop:
        def is_closed(self):
            return False

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._lock = asyncio.Lock()
    pool._pool = mocker.AsyncMock()
    pool._closed = False

    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)

    pool._pool.put.side_effect = RuntimeError("queue put failed during release")
    mocker.patch("asyncio.get_running_loop", return_value=_Loop())

    with caplog.at_level(logging.WARNING, logger="pyftpkit"):
        with pytest.raises(RuntimeError) as error:
            await pool.release(ftp_connection_mock)

    assert caplog.text == ""
    assert "queue put failed during release" in str(error.value)


@pytest.mark.asyncio
async def test_close_without_loop_uses_fallback_cleanup(mocker, connection_parameters):
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)

    class _FakeQueue:
        def get_nowait(self):
            raise RuntimeError("queue failure during close")

    pool._pool = _FakeQueue()
    pool._closed = False

    shutdown_mock = mocker.patch.object(pool._executor, "shutdown")
    close_mock = mocker.patch.object(pool, "_close_connection")
    mocker.patch(
        "asyncio.get_running_loop",
        side_effect=RuntimeError("no running event loop"),
    )

    await pool.close()

    close_mock.assert_called_once_with(ftp_connection_mock)
    shutdown_mock.assert_called_once()


@pytest.mark.asyncio
async def test_close_without_loop_logs_error_when_pool_missing(
    mocker, connection_parameters
):
    executor = ThreadPoolExecutor(max_workers=1)
    pool = FTPPoolExecutor(
        connection_parameters=connection_parameters, executor=executor
    )
    ftp_connection_mock = mocker.Mock()
    pool._connections.add(ftp_connection_mock)

    close_mock = mocker.patch.object(
        pool, "_close_connection", side_effect=RuntimeError("close failed")
    )
    shutdown_mock = mocker.patch.object(executor, "shutdown")
    mocker.patch(
        "asyncio.get_running_loop",
        side_effect=RuntimeError("no running event loop"),
    )

    await pool.close()

    close_mock.assert_called_once_with(ftp_connection_mock)
    shutdown_mock.assert_not_called()


@pytest.mark.asyncio
async def test_close_without_loop_handles_empty_pool_queue(
    mocker, connection_parameters
):
    class _EmptyQueue:
        def get_nowait(self):
            raise asyncio.QueueEmpty

    pool = FTPPoolExecutor(connection_parameters=connection_parameters)
    pool._pool = _EmptyQueue()

    shutdown_mock = mocker.patch.object(pool._executor, "shutdown")
    mocker.patch(
        "asyncio.get_running_loop",
        side_effect=RuntimeError("no running event loop"),
    )

    await pool.close()

    shutdown_mock.assert_called_once()


def test_close_connection_closes_when_socket_stream_closed(
    mocker, ftp_server, connection_parameters
):
    ftp_connection_mock = mocker.Mock()
    ftp_connection_mock.sock = object()
    ftp_connection_mock.file = mocker.Mock(closed=True)

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(ftp_connection_mock)

    ftp_connection_mock.close.assert_called_once()
    ftp_connection_mock.quit.assert_not_called()


def test_close_connection_raises_when_socket_stream_close_fails(
    mocker, ftp_server, connection_parameters, caplog
):
    ftp_connection_mock = mocker.Mock()
    ftp_connection_mock.sock = object()
    ftp_connection_mock.file = mocker.Mock(closed=True)
    ftp_connection_mock.close.side_effect = ftplib.error_perm(
        "socket stream close failed"
    )

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(FTPError) as error:
            pool._close_connection(ftp_connection_mock)

    message = "Unable to close the FTP connection safely."
    assert message in caplog.text

    message = "Failed to safely close the FTP connection to: {0!s}:{1!s}".format(
        connection_parameters.host, connection_parameters.port
    )
    assert message in str(error.value)


def test_close_connection_handles_file_disappearing(
    mocker, ftp_server, connection_parameters
):
    class _FakeFTP:
        def __init__(self):
            self.sock = object()
            self._calls = 0

        @property
        def file(self):
            self._calls += 1
            if self._calls == 1:
                return object()
            return None

        def quit(self):
            raise AssertionError("quit should not be called")

        def close(self):
            raise AssertionError("close should not be called")

    connection_parameters.host = ftp_server.host
    connection_parameters.port = ftp_server.port
    pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    pool._close_connection(_FakeFTP())
