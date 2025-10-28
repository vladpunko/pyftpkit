# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio
import ftplib
import logging
import typing
import weakref
from concurrent.futures import ThreadPoolExecutor

from pyftpkit._ftp import FTP
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError

__all__ = ["FTPPoolExecutor"]

logger = logging.getLogger("pyftpkit")


class FTPPoolExecutor:
    """Asynchronous FTP connection pool executor.

    This class manages a pool of active FTP connections that can be reused
    across multiple asynchronous tasks. Although the FTP protocol is
    command-oriented and not inherently asynchronous, pooling allows the
    application to efficiently handle multiple concurrent FTP operations
    without blocking the event loop.
    """

    def __init__(
        self,
        connection_parameters: ConnectionParameters,
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._connection_parameters = connection_parameters

        # We need to track all connections for proper cleanup.
        self._connections: weakref.WeakSet[FTP] = weakref.WeakSet()

        # We need to ensure that all asynchronous objects are created during
        # pool initialization so they are bound to the correct event loop.
        self._lock: asyncio.Lock
        self._pool: asyncio.Queue[FTP]

        self._closed: bool = True

        # External executor or an internal one for blocking calls.
        self._executor = executor or ThreadPoolExecutor(
            max_workers=self._connection_parameters.max_workers
        )

    @property
    def executor(self) -> ThreadPoolExecutor:
        return self._executor

    async def __aenter__(self) -> "FTPPoolExecutor":
        await self.open()

        return self

    async def __aexit__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        await self.close()
        self._executor.shutdown(wait=True)

        logger.info("The FTP connection pool is now closed.")

    def _ensure_lock(self) -> None:
        """Makes sure the pool lock is created."""
        try:
            asyncio.get_running_loop()
        except RuntimeError as err:
            logging.exception("No running event loop was detected.")
            raise RuntimeError(
                f"{type(self).__name__!s} requires an active event loop to open."
            ) from err

        try:
            self._lock  # noqa: B018
        except AttributeError:
            self._lock = asyncio.Lock()
            logger.debug(
                "A new pool lock has been created and bound to the current event loop."
            )

    def _connect(self) -> FTP:
        """Opens a new FTP session using the provided connection parameters.

        Passive mode is enabled by default.

        Returns
        -------
        FTP
            A ready-to-use FTP client with an active authenticated connection.

        Raises
        ------
        FTPError
            If the connection or login fails due to network or authentication issues.
        """
        try:
            ftp = FTP()
            ftp.connect(
                self._connection_parameters.host,
                self._connection_parameters.port,
                timeout=self._connection_parameters.timeout,
            )
            ftp.login(
                self._connection_parameters.credentials.username,
                self._connection_parameters.credentials.password.get_secret_value(),
            )
            ftp.set_pasv(True)
            logger.debug(
                "FTP connection has been created: %s:%s",
                self._connection_parameters.host,
                self._connection_parameters.port,
            )

            return ftp
        except ftplib.all_errors as err:
            logger.exception("Unable to create a new connection.")
            raise FTPError(
                "Could not open an FTP connection to: {0!s}:{1!s}".format(
                    self._connection_parameters.host,
                    self._connection_parameters.port,
                )
            ) from err

    async def _open_connections(self) -> None:
        """Creates and populates an FTP connection pool with active connections."""
        loop = asyncio.get_running_loop()

        tasks = [
            loop.run_in_executor(self._executor, self._connect)
            for _ in range(self._connection_parameters.max_connections)
        ]
        try:
            # Wait for all connections to be established.
            connections: list[FTP] = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=False),
                timeout=self._connection_parameters.timeout,
            )
        except asyncio.TimeoutError as err:
            logger.exception(
                "FTP connection pool failed to initialize within the timeout period."
            )
            raise FTPError("FTP connection pool initialization timed out.") from err

        for connection in connections:
            self._connections.add(connection)
            await self._pool.put(connection)

        logger.debug(
            "FTP connection pool has been initialized with %d connections.",
            self._connection_parameters.max_connections,
        )

        self._closed = False

    async def open(self) -> None:
        """Initializes the FTP connection pool.

        Ensures that the pool lock exists and prevents concurrent initializations.

        Raises
        ------
        FTPError
            If the pool cannot be initialized.
        """
        if not self._closed:
            return None

        # Make sure the lock is created after there is an event loop.
        self._ensure_lock()

        async with self._lock:
            self._pool = asyncio.Queue(
                maxsize=self._connection_parameters.max_connections
            )

            await self._open_connections()

    async def get(self) -> FTP:
        """Acquires an FTP connection from the pool.

        Returns
        -------
        FTP
            An active FTP connection from the pool.

        Raises
        ------
        RuntimeError
            If the connection pool has not been initialized.
        """
        if self._closed or getattr(self, "_pool", None) is None:
            logger.error(
                "There is no active connection pool to acquire an FTP connection from."
            )
            raise RuntimeError("Connection pool is not initialized or is closed.")

        return await self._pool.get()

    async def release(self, ftp: FTP) -> None:
        """Returns an FTP connection back to the pool for reuse.

        Parameters
        ----------
        ftp : FTP
            The FTP connection to be returned to the pool.
        """
        if self._closed or getattr(self, "_pool", None) is None:
            logger.error(
                "No active connection pool available to release the FTP connection."
            )
            raise RuntimeError("FTP connection pool does not exist or is closed.")

        # Ensure the connection is still in the weak set before putting it back.
        if ftp not in self._connections:
            logger.warning("Released FTP connection was not tracked.")

            return None

        await self._pool.put(ftp)

    def _close_connection(self, ftp: FTP) -> None:
        """Safely closes a single FTP connection."""
        try:
            ftp.quit()
        except ftplib.all_errors:
            try:
                ftp.close()
            except ftplib.all_errors as err:
                logger.exception("Unable to close the FTP connection safely.")
                raise FTPError(
                    "Failed to safely close the FTP connection to: {0!s}:{1!s}".format(
                        self._connection_parameters.host,
                        self._connection_parameters.port,
                    )
                ) from err

    async def close(self) -> None:
        """Safely closes all FTP connections in the pool."""
        if getattr(self, "_pool", None) is None:
            logger.debug("No pool to close.")

            return None

        connections: set[FTP] = set()
        async with self._lock:
            if self._closed:
                return None

            loop = asyncio.get_running_loop()

            while not self._pool.empty():  # drain the pool queue
                connections.add(await self._pool.get())
            connections.update(self._connections)

            # Clear the weakset now that we have a strong reference to all connections.
            self._connections.clear()

            tasks = [
                loop.run_in_executor(self._executor, self._close_connection, connection)
                for connection in connections
            ]
            await asyncio.gather(*tasks)

            self._closed = True

        logger.debug(
            "All FTP connections in the pool and tracked set have been closed."
        )
