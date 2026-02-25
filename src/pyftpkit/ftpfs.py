# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

# ruff: noqa: C901
# reason: Several complex functions that need to remain unchanged in their current form.

import asyncio
import collections.abc
import enum
import ftplib
import functools
import logging
import posixpath
import typing
from concurrent.futures import ThreadPoolExecutor

from pyftpkit._ftp import FTP
from pyftpkit._pathtrie import PathTrie
from pyftpkit._pool import FTPPoolExecutor
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError

__all__ = ["FTPEntryType", "FTPFileSystem"]

logger = logging.getLogger("pyftpkit")


class FTPEntryType(int, enum.Enum):
    DIRECTORY = 0
    FILE = 1


class FTPFileSystem:
    """Provides an FTP-backed virtual file system interface.

    This class emulates standard file system operations for files
    stored on a remote FTP server.
    """

    _SYMLINK_SEP: typing.Final[str] = " -> "

    # Scales queue sizes by `max_workers` to limit memory use while keeping throughput.
    _QUEUE_SCALE_FACTOR: typing.Final[int] = 256

    def __init__(
        self,
        connection_parameters: ConnectionParameters,
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        self._connection_parameters = connection_parameters

        # Initialize a managed pool of pre-authenticated FTP connections. This design
        # drastically reduces the overhead of repeated handshakes and logins.
        self._pool = FTPPoolExecutor(
            connection_parameters=connection_parameters, executor=executor
        )

    async def __aenter__(self) -> "FTPFileSystem":
        await self._pool.open()

        return self

    async def __aexit__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        await self._pool.close()

    async def _listdir(
        self, path: str, ftp: FTP
    ) -> typing.AsyncIterator[tuple[FTPEntryType, str]]:
        """Retrieves the directory contents from the remote FTP server.

        Notes
        -----
        This method parses the `LIST` command output using Unix-style formatting
        assumptions. FTP servers that do not follow Unix conventions may produce
        responses that are not compatible with this parser.
        """
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path must be a string.")
            raise TypeError(
                "Only string values are permitted for the remote path."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        path = path.strip()

        if not path:
            logger.error(
                "The remote path must include at least one non-whitespace character."
            )
            raise ValueError("The remote path must not be empty or whitespace.")

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path is not absolute and does not start from the root."
            )
            raise RuntimeError(f"Ambiguous remote path: {path!r}")

        logger.debug("Listing remote directory: %s", path)

        await loop.run_in_executor(
            self._pool.executor, ftp.cwd, posixpath.normpath(path)
        )

        entries: list[str] = []
        await loop.run_in_executor(
            self._pool.executor, ftp.retrlines, "LIST -a", entries.append
        )
        logger.debug(repr(entries))

        for entry in entries:
            # Skip empty or malformed lines.
            # A valid line begins with a 10-character permission field.
            if not entry or len(entry) < 10:
                logger.debug("Skipping malformed entry: %r", entry)

                continue

            parts = entry.strip().split(maxsplit=8)
            if not parts:
                logger.debug("Skipping entry with no fields: %r", entry)

                continue

            name = parts[-1]
            if name in (posixpath.curdir, posixpath.pardir):
                continue

            if entry.startswith("l"):
                try:
                    name, _ = name.split(self._SYMLINK_SEP, maxsplit=1)
                except ValueError:
                    continue

            abspath = posixpath.join(path, name)
            if entry.startswith("d"):
                yield FTPEntryType.DIRECTORY, abspath
            else:
                yield FTPEntryType.FILE, abspath

    async def listdir(
        self, path: str
    ) -> typing.AsyncIterator[tuple[FTPEntryType, str]]:
        """Lists the contents of a remote FTP directory.

        Parameters
        ----------
        path : str
            Remote directory path to list.

        Yields
        -------
        tuple[FTPEntryType, str]
            - The entry type.
            - The absolute remote path of the entry.

        Raises
        ------
        ValueError
            If the provided path is invalid.

        TypeError
            If the provided path is not a string.

        RuntimeError
            If the source path is not absolute and does not start from the root.

        FTPError
            If an FTP-related error occurs during listing.
        """
        async with self._pool.acquire() as ftp:
            try:
                async for entry in self._listdir(path, ftp=ftp):
                    yield entry
            except (TypeError, ValueError, RuntimeError):
                raise

            except ftplib.all_errors as err:
                logger.exception(
                    "The FTP server returned an error during directory listing."
                )
                raise FTPError(f"Failed to list this directory: {path!r}") from err

            except Exception as err:
                logger.exception(
                    "Failed to parse directory listing from the FTP server."
                )
                raise FTPError(
                    f"Failed to parse directory listing for: {path!r}"
                ) from err

    async def walk(
        self, path: str
    ) -> typing.AsyncIterator[tuple[str, FTPEntryType, str]]:
        """Asynchronously traverses a remote FTP directory tree.

        - Uses worker coroutines to parallelize listing operations across
          multiple FTP connections managed by the connection pool.

        - Traversal stops when all directories have been processed or when
          an explicit stop signal is triggered.

        Parameters
        ----------
        path : str
            Root directory path on the remote FTP server to begin traversal.

        Yields
        ------
        tuple[str, FTPEntryType, str]
            - The directory being traversed.
            - The entry type (directory or file).
            - The absolute path of the entry.

        Raises
        ------
        RuntimeError
            If an FTP worker encounters a critical error. The original exception
            is attached as the cause.

        Notes
        -----
        The traversal relies on bounded queues to regulate flow control.
        For very large directory trees, this design may deliberately slow down producers
        when consumers cannot keep up.
        """
        if not isinstance(path, str):
            logger.error("The remote path must be a string.")
            raise TypeError(
                "Only string values are permitted for the remote path."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        path = path.strip()

        if not path:
            logger.error(
                "The remote path must include at least one non-whitespace character."
            )
            raise ValueError("The remote path must not be empty or whitespace.")

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path is not absolute and does not start from the root."
            )
            raise RuntimeError(f"Ambiguous remote path: {path!r}")

        stop_event = asyncio.Event()

        queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=max(
                1, self._connection_parameters.max_workers * self._QUEUE_SCALE_FACTOR
            )
        )
        await queue.put(posixpath.normpath(path))

        output_queue: asyncio.Queue[tuple[str, FTPEntryType, str] | Exception] = (
            # Bound the queue so a slow consumer cannot cause unbounded memory usage.
            asyncio.Queue(
                maxsize=max(
                    1,
                    self._connection_parameters.max_workers * self._QUEUE_SCALE_FACTOR,
                )
            )
        )

        async def _worker() -> None:
            """Worker coroutine that retrieves directories from the task queue.

            This coroutine is defined as an inner function to simplify binding
            to the correct event loop.
            """
            ftp = await self._pool.get()
            try:
                while True:
                    try:
                        dirpath = await queue.get()
                        logger.debug("Processing directory from queue: %s", dirpath)
                    except asyncio.CancelledError:
                        break

                    try:
                        async for entry_type, entry_path in self._listdir(
                            dirpath, ftp=ftp
                        ):
                            if entry_type == FTPEntryType.DIRECTORY:
                                await queue.put(entry_path)
                            await output_queue.put((dirpath, entry_type, entry_path))
                    except Exception as err:
                        logger.exception(
                            "An unexpected error occurred at this program runtime."
                        )
                        stop_event.set()
                        try:
                            output_queue.put_nowait(err)
                        except asyncio.QueueFull:
                            # Emit a best-effort error notification while ensuring the
                            # worker does not become blocked.
                            pass

                        break
                    finally:
                        queue.task_done()

                    if stop_event.is_set():
                        break
            finally:
                await self._pool.release(ftp)

        # Spawn worker tasks.
        workers = [
            asyncio.create_task(_worker())
            for _ in range(self._connection_parameters.max_workers)
        ]

        cancelled = False
        try:
            # Create a task to wait for all directories to be processed.
            join_task = asyncio.create_task(queue.join())

            # Wait until all tasks in the queue are done or an exception occurs.
            while not join_task.done():
                if stop_event.is_set():
                    break

                try:
                    # Short timeout to periodically check stop event.
                    output = await asyncio.wait_for(output_queue.get(), timeout=0.1)

                    if isinstance(output, Exception):
                        raise RuntimeError("Walk worker error.") from output

                    yield output

                    output_queue.task_done()
                except asyncio.TimeoutError:
                    # Re-enter the loop to inspect the join task and check
                    # for the stop event.
                    pass

            if stop_event.is_set():
                # Prevent a deadlock when a worker fails with
                # unprocessed items still in the queue.
                join_task.cancel()
                await asyncio.gather(join_task, return_exceptions=True)
                while True:
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    else:
                        queue.task_done()
            else:
                await join_task
        except asyncio.CancelledError:
            cancelled = True

            raise
        finally:
            stop_event.set()  # signal all workers to stop

            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            # Drain any remaining items that might have been
            # placed onto the output queue before the workers were signaled to stop.
            if cancelled:
                while not output_queue.empty():
                    output_queue.get_nowait()
                    output_queue.task_done()
            else:
                while not output_queue.empty():
                    output = await output_queue.get()

                    if isinstance(output, Exception):
                        raise RuntimeError("Walk worker error.") from output

                    yield output

                    output_queue.task_done()

    @functools.singledispatchmethod
    async def makedirs(self, paths: typing.Iterable[str]) -> None:
        """Recursively creates multiple directories on the remote FTP server."""
        loop = asyncio.get_running_loop()

        if not isinstance(paths, collections.abc.Iterable) or isinstance(
            paths, (bytes, bytearray, str)
        ):
            logger.debug(repr(paths))
            logger.error("Expected paths to be a collection of strings.")
            raise TypeError(
                "Invalid type for paths: expected an iterable of path strings."
                "\nAn unsupported type was provided for paths: {0!s}".format(
                    type(paths).__name__
                )
            )

        pathtrie = PathTrie()
        async with self._pool.acquire() as ftp:
            for path in paths:
                if not isinstance(path, str):
                    logger.error("The path must be provided as a string value.")
                    raise TypeError(
                        "The path must be defined using string data."
                        "\nThe path {0!r} has type: {1!s}".format(
                            path, type(path).__name__
                        )
                    )

                path = path.strip()

                if not path:
                    logger.error(
                        "The path must contain at least one non-blank character."
                    )
                    raise ValueError("The path cannot be blank or whitespace-only.")

                if not path.startswith(posixpath.sep):
                    logger.error(
                        "The path is relative rather than starting at the root."
                    )
                    raise RuntimeError(f"Ambiguous path: {path!r}")

                # Parse path using the suffix-tree.
                pathtrie.insert(posixpath.normpath(path))

            for dirpath in pathtrie:
                if dirpath == posixpath.sep:
                    continue

                try:
                    await loop.run_in_executor(self._pool.executor, ftp.cwd, dirpath)
                except ftplib.all_errors as err:
                    if not isinstance(err, ftplib.error_perm):
                        logger.exception("Failed to validate the remote directory.")
                        raise FTPError(
                            f"Failed to access remote directory: {dirpath!r}."
                        ) from err

                    try:
                        logger.debug("Creating a new directory: %s", dirpath)
                        # Attempt to create the required directory.
                        await loop.run_in_executor(
                            self._pool.executor, ftp.mkd, dirpath
                        )
                        logger.debug(
                            "Successfully created a new remote directory: %s", dirpath
                        )
                    except ftplib.error_perm as err:
                        # This accommodates servers that block `MKD` for existing
                        # directories without depending on server response messages.
                        try:
                            await loop.run_in_executor(
                                self._pool.executor, ftp.cwd, dirpath
                            )
                        except ftplib.all_errors:
                            logger.exception(
                                "Creation of the remote directory did not succeed."
                            )
                            raise FTPError(
                                f"Remote directory setup failed: {dirpath!r}."
                            ) from err

                    except ftplib.all_errors as err:
                        # Even on non-permission FTP errors, verify whether the
                        # directory was created before failing hard.
                        try:
                            await loop.run_in_executor(
                                self._pool.executor, ftp.cwd, dirpath
                            )
                        except ftplib.all_errors:
                            logger.exception(
                                "The remote directory could not be initialized."
                            )
                            raise FTPError(
                                f"FTP server directory creation failed: {dirpath!r}."
                            ) from err

    @makedirs.register(str)
    async def _(self, path: str) -> None:
        """Recursively creates a single directory on the remote FTP server.

        The given path must be absolute and use POSIX-style separators. Each directory
        in the hierarchy is created if it does not already exist.

        Parameters
        ----------
        path : str
            Absolute remote path to ensure exists on the FTP server.

        Raises
        ------
        ValueError
            If the provided path is invalid.

        TypeError
            If the provided path is not a string.

        RuntimeError
            If the source path is not absolute and does not start from the root.

        FTPError
            If any directory cannot be created due to permission or FTP errors.
        """
        await self.makedirs([path])

    async def rm(self, path: str) -> None:
        """Deletes a single file from the remote FTP server.

        Parameters
        ----------
        path : str
            Absolute path to the file on the FTP server that should be removed.

        Raises
        ------
        TypeError
            If the provided path is not a string.

        ValueError
            If the path is empty, whitespace-only, or resolves to the root.

        RuntimeError
            If the path is not absolute.

        FTPError
            If the FTP server refuses the deletion or an unexpected FTP error occurs.
        """
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path cannot be of any type other than string.")
            raise TypeError(
                "The remote path must consist of string data."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        path = path.strip()

        if not path:
            logger.error("The remote path cannot consist entirely of spaces or tabs.")
            raise ValueError(
                "The remote path must contain at least one non-blank character."
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path must be absolute and start from the root directory."
            )
            raise RuntimeError(f"Ambiguous remote path: {path!r}")

        if path == posixpath.sep:
            logger.error("Attempting to remove the root directory is disallowed.")
            raise ValueError(
                f"Attempt to remove FTP root directory has been prevented: {path!r}"
            )

        async with self._pool.acquire() as ftp:
            try:
                logger.debug("Attempting to delete: %s", path)
                await loop.run_in_executor(
                    self._pool.executor, ftp.delete, posixpath.normpath(path)
                )
                logger.debug("File deletion succeeded: %s", path)
            except ftplib.all_errors as err:
                logger.exception(
                    "Could not delete file due to an unexpected FTP server response."
                )
                raise FTPError(f"FTP server refused to delete file: {path!r}") from err

    async def rmtree(self, path: str) -> None:
        """Recursively removes a directory tree from the remote FTP server.

        Parameters
        ----------
        path : str
            The absolute path to the root directory on the FTP server to remove.

        Raises
        ------
        TypeError
            If the provided path is not a string.

        ValueError
            If the path is empty, whitespace-only, or resolves to the root.

        RuntimeError
            If the path is not absolute.

        FTPError
            Occurs if deletion of any file or directory fails due to FTP-related
            errors or access restrictions.

        Notes
        -----
        This implementation uses a depth-first traversal (DFS) with a single
        FTP connection. Using the same connection avoids potential deadlocks
        with the connection pool that can occur if directory walking and file
        deletion contend for pooled connections. In practice, directory depths
        are typically small, so the DFS stack remains modest.
        """
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path cannot be of any type other than string.")
            raise TypeError(
                "The remote path must consist of string data."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        path = path.strip()

        if not path:
            logger.error(
                "The remote path cannot be empty or consist solely of whitespace."
            )
            raise ValueError(
                "The remote path cannot consist entirely of spaces or tabs."
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path must be absolute and start from the root directory."
            )
            raise RuntimeError(f"Ambiguous remote path: {path!r}")

        stack: list[tuple[str, bool]] = [(posixpath.normpath(path), False)]
        async with self._pool.acquire() as ftp:
            while stack:
                dirpath, is_visited = stack.pop()

                if is_visited:
                    if dirpath == posixpath.sep:
                        continue

                    try:
                        logger.debug("Attempting to remove: %s", dirpath)
                        await loop.run_in_executor(
                            self._pool.executor, ftp.rmd, dirpath
                        )
                        logger.debug("Remote directory has been removed: %s", dirpath)
                    except ftplib.all_errors as err:
                        logger.exception("The directory could not be removed.")
                        raise FTPError(
                            f"Failed to remove {dirpath!r} from the FTP server."
                        ) from err

                    continue

                stack.append((dirpath, True))

                try:
                    async for entry_type, entry_path in self._listdir(dirpath, ftp=ftp):
                        if entry_type == FTPEntryType.DIRECTORY:
                            stack.append((entry_path, False))

                            continue

                        try:
                            logger.debug("Attempting to remove: %s", entry_path)
                            await loop.run_in_executor(
                                self._pool.executor, ftp.delete, entry_path
                            )
                            logger.debug("File has been removed: %s", entry_path)
                        except ftplib.all_errors as err:
                            logger.exception("File deletion could not be completed.")
                            raise RuntimeError(
                                f"The system failed to remove the file: {entry_path!r}"
                            ) from err
                except RuntimeError:
                    raise

                except ftplib.all_errors as err:
                    logger.exception(
                        "The directory listing failed due to an FTP server error."
                    )
                    raise FTPError(
                        f"Failed to list this directory: {dirpath!r}"
                    ) from err

                except Exception as err:
                    logger.exception(
                        "Directory listing parsing failed for the FTP server response."
                    )
                    raise FTPError(
                        f"Failed to parse directory listing for: {dirpath!r}"
                    ) from err
