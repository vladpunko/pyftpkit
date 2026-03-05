# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-05

import asyncio
import collections.abc
import enum
import ftplib
import functools
import logging
import posixpath
import re
import typing
from concurrent.futures import ThreadPoolExecutor

from pyftpkit._ftp import FTP
from pyftpkit._pathtrie import PathTrie
from pyftpkit._pool import FTPPoolExecutor
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import (
    FTPError,
    FTPPathError,
    FTPPathNotAbsoluteError,
)

__all__ = ["FTPEntryType", "FTPFileSystem"]

logger = logging.getLogger("pyftpkit")


def _has_prohibited_segments(path: str) -> bool:
    """Validates whether the path contains prohibited traversal segments.

    These segments enable directory traversal and can be used to escape
    a constrained root directory when paths are joined or resolved.
    """
    prohibited = {posixpath.curdir, posixpath.pardir}
    return any(
        segment in prohibited for segment in path.split(posixpath.sep) if segment
    )


class FTPEntryType(int, enum.Enum):
    DIRECTORY = 0
    FILE = 1


class FTPFileSystem:
    """Provides an FTP-backed virtual file system interface.

    This class emulates standard file system operations for files
    stored on a remote FTP server.
    """

    _SYMLINK_SEP: typing.Final[str] = " -> "

    # Use a regular expression instead of naive string splitting to ensure
    # robust parsing of `LIST` output.
    _LIST_ENTRY_REGEX: typing.Final[re.Pattern[str]] = re.compile(
        r"^(?P<perms>.{10})\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s+\S+\s(?P<name>.*)$"
    )

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
            raise FTPPathError(
                "Only string values are permitted for the remote path."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        if not path or not path.strip():
            logger.error(
                "The remote path must include at least one non-whitespace character."
            )
            raise FTPPathError("The remote path must not be empty or whitespace.")

        if _has_prohibited_segments(path):
            logger.error(
                "The remote path must not include relative navigation components."
            )
            raise FTPPathError(
                "The remote path {0!r} cannot include {1!r} or {2!r} segments.".format(
                    path, posixpath.curdir, posixpath.pardir
                )
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path is not absolute and does not start from the root."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous remote path: {path!r}")

        logger.debug("Listing remote directory: %r", path)

        await loop.run_in_executor(self._pool.executor, ftp.cwd, path)

        entries: list[str] = []
        await loop.run_in_executor(
            self._pool.executor, ftp.retrlines, "LIST -a", entries.append
        )
        logger.debug(repr(entries))

        for entry in entries:
            line = entry.rstrip("\r\n")
            # Skip empty or malformed lines.
            # A valid line begins with a 10-character permission field.
            if not line or len(line) < 10:
                logger.debug("Skipping malformed entry: %r", entry)

                continue

            match = self._LIST_ENTRY_REGEX.match(line)
            if not match:
                logger.debug("Skipping entry with no fields: %r", entry)
                continue

            name = match.group("name")
            if name in (posixpath.curdir, posixpath.pardir):
                continue

            if line.startswith("l"):
                try:
                    name, _ = name.split(self._SYMLINK_SEP, maxsplit=1)
                except ValueError:
                    logger.debug("Skipping bad symlink: %r", entry)
                    continue

            if not name:
                logger.debug("Skipping entry with empty name: %r", entry)
                continue

            if name.startswith(posixpath.sep):
                logger.debug("Skipping absolute entry: %r", entry)
                continue

            if posixpath.sep in name or "\\" in name:
                logger.debug("Skipping entry containing path separators: %r", entry)
                continue

            abspath = posixpath.join(path, name)
            if line.startswith("d"):
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
        FTPPathError
            If the provided path is invalid, not a string, or contains prohibited
            traversal segments.

        FTPPathNotAbsoluteError
            If the source path is not absolute and does not start from the root.

        FTPError
            If an FTP-related error occurs during listing.
        """
        async with self._pool.acquire() as ftp:
            try:
                async for entry in self._listdir(path, ftp=ftp):
                    yield entry
            except (FTPPathError, FTPPathNotAbsoluteError):
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
        FTPPathError
            If the provided path is not a string, is empty or whitespace-only, or
            contains prohibited traversal segments.

        FTPPathNotAbsoluteError
            If the path is not absolute.

        RuntimeError
            If an FTP worker encounters a critical error or if the output queue
            fills and traversal aborts. The original exception is attached as the cause.

        Notes
        -----
        The traversal relies on bounded queues to regulate flow control.
        Slow consumption results in workers waiting while the output queue remains full.
        """
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path must be a string.")
            raise FTPPathError(
                "Only string values are permitted for the remote path."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        if not path or not path.strip():
            logger.error(
                "The remote path must include at least one non-whitespace character."
            )
            raise FTPPathError("The remote path must not be empty or whitespace.")

        if _has_prohibited_segments(path):
            logger.error(
                "The remote path must not contain directory traversal segments."
            )
            raise FTPPathError(
                "The remote path {0!r} must not reference {1!r} or {2!r}.".format(
                    path, posixpath.curdir, posixpath.pardir
                )
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path is not absolute and does not start from the root."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous remote path: {path!r}")

        stop_event = asyncio.Event()
        worker_error = loop.create_future()

        queue: asyncio.Queue[str] = asyncio.Queue(
            maxsize=max(1, self._connection_parameters.max_queue_size)
        )
        await queue.put(path)

        output_queue: asyncio.Queue[tuple[str, FTPEntryType, str] | Exception] = (
            asyncio.Queue(maxsize=max(1, self._connection_parameters.max_queue_size))
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
                        logger.debug("Processing directory from queue: %r", dirpath)
                    except asyncio.CancelledError:
                        break

                    try:
                        async for entry_type, entry_path in self._listdir(
                            dirpath, ftp=ftp
                        ):
                            if entry_type == FTPEntryType.DIRECTORY:
                                await queue.put(entry_path)
                            await output_queue.put((dirpath, entry_type, entry_path))
                    except asyncio.CancelledError:
                        raise
                    except Exception as err:
                        logger.exception(
                            "An unexpected error occurred at this program runtime."
                        )
                        stop_event.set()
                        if not worker_error.done():
                            worker_error.set_exception(err)
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
                try:
                    await asyncio.shield(self._pool.release(ftp))
                except asyncio.CancelledError:
                    # Ensure release is not interrupted by cancellation.
                    await asyncio.shield(self._pool.release(ftp))

                    raise

        # Spawn worker tasks.
        workers = [
            asyncio.create_task(_worker())
            for _ in range(self._connection_parameters.max_workers)
        ]

        cancelled = False
        join_task: asyncio.Task[None] | None = None
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
                        output_queue.task_done()
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

            if worker_error.done() and not worker_error.cancelled():
                raise RuntimeError("Walk worker error.") from worker_error.exception()
        except asyncio.CancelledError:
            cancelled = True

            raise
        except GeneratorExit:
            cancelled = True

            raise
        finally:
            stop_event.set()  # signal all workers to stop

            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            if join_task is not None and not join_task.done():
                join_task.cancel()
                await asyncio.gather(join_task, return_exceptions=True)
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
                        output_queue.task_done()
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
                    raise FTPPathError(
                        "The path must be defined using string data."
                        "\nThe path {0!r} has type: {1!s}".format(
                            path, type(path).__name__
                        )
                    )

                if not path or not path.strip():
                    logger.error(
                        "The path must contain at least one non-blank character."
                    )
                    raise FTPPathError("The path cannot be blank or whitespace-only.")

                if _has_prohibited_segments(path):
                    logger.error(
                        "The remote path must not include relative traversal markers."
                    )
                    raise FTPPathError(
                        "The path {0!r} must not reference {1!r} or {2!r}.".format(
                            path, posixpath.curdir, posixpath.pardir
                        )
                    )

                if not path.startswith(posixpath.sep):
                    logger.error(
                        "The path is relative rather than starting at the root."
                    )
                    raise FTPPathNotAbsoluteError(f"Ambiguous path: {path!r}")

                # Parse path using the trie.
                pathtrie.insert(path)

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
                        logger.debug("Creating a new directory: %r", dirpath)
                        # Attempt to create the required directory.
                        await loop.run_in_executor(
                            self._pool.executor, ftp.mkd, dirpath
                        )
                        logger.debug(
                            "Successfully created a new remote directory: %r", dirpath
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
        FTPPathError
            If the path is invalid, empty, or contains prohibited traversal segments.

        FTPPathNotAbsoluteError
            If the path is not absolute and does not start from the root.

        FTPError
            If any directory cannot be created due to permission or FTP errors.
        """
        await self.makedirs([path])

    async def _rm(self, path: str, ftp: FTP) -> None:
        """Remove a single remote path using the provided FTP connection."""
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path cannot be of any type other than string.")
            raise FTPPathError(
                "The remote path must consist of string data."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        if not path or not path.strip():
            logger.error("The remote path cannot consist entirely of spaces or tabs.")
            raise FTPPathError(
                "The remote path must contain at least one non-blank character."
            )

        if _has_prohibited_segments(path):
            logger.error("The remote path must not contain directory escape sequences.")
            raise FTPPathError(
                "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
                    path, posixpath.curdir, posixpath.pardir
                )
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path must be absolute and start from the root directory."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous remote path: {path!r}")

        if posixpath.normpath(path) == posixpath.sep:
            logger.error("The system does not allow deletion of the root directory.")
            raise ValueError(
                f"An attempt to delete the FTP root directory was prevented: {path!r}"
            )

        try:
            logger.debug("Attempting to delete: %r", path)
            await loop.run_in_executor(self._pool.executor, ftp.delete, path)
            logger.debug("File deletion succeeded: %r", path)
        except ftplib.all_errors as err:
            logger.exception(
                "Could not delete file due to an unexpected FTP server response."
            )
            raise FTPError(f"FTP server refused to delete file: {path!r}") from err

    async def rm(self, path: str) -> None:
        """Deletes a single file from the remote FTP server.

        Parameters
        ----------
        path : str
            Absolute path to the file on the FTP server that should be removed.

        Raises
        ------
        FTPPathError
            If the provided path is not a string, is empty or whitespace-only, or
            contains prohibited traversal segments.

        FTPPathNotAbsoluteError
            If the path is not absolute.

        ValueError
            If the path resolves to the root directory.

        FTPError
            If the FTP server refuses the deletion or an unexpected FTP error occurs.
        """
        async with self._pool.acquire() as ftp:
            await self._rm(path, ftp=ftp)

    async def rmtree(self, path: str) -> None:
        """Recursively removes a directory tree from the remote FTP server.

        Parameters
        ----------
        path : str
            Absolute path to the directory tree root on the FTP server to remove.

        Raises
        ------
        FTPPathError
            If the provided path is not a string, is empty or whitespace-only, or
            contains prohibited traversal segments.

        FTPPathNotAbsoluteError
            If the path is not absolute.

        ValueError
            If the path resolves to the root directory.

        FTPError
            Raised when the FTP server returns an error while processing directory
            entries or when a directory listing cannot be parsed.

        Notes
        -----
        This implementation uses a depth-first traversal (DFS) with a single
        FTP connection. Using the same connection avoids potential deadlocks
        with the connection pool that can occur if directory walking and file
        deletion contend for pooled connections. The algorithm is memory-safe.
        """
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path cannot be of any type other than string.")
            raise FTPPathError(
                "The remote path must consist of string data."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        if not path or not path.strip():
            logger.error(
                "The remote path cannot be empty or consist solely of whitespace."
            )
            raise FTPPathError(
                "The remote path cannot consist entirely of spaces or tabs."
            )

        if _has_prohibited_segments(path):
            logger.error(
                "The remote path must not contain upward or self-referencing segments."
            )
            raise FTPPathError(
                "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
                    path, posixpath.curdir, posixpath.pardir
                )
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "The remote path must be absolute and start from the root directory."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous remote path: {path!r}")

        if posixpath.normpath(path) == posixpath.sep:
            logger.error(
                "The root directory cannot be deleted under any circumstances."
            )
            raise ValueError(f"Prevented deletion of the FTP root directory: {path!r}")

        stack: list[tuple[str, bool]] = [(path, False)]
        async with self._pool.acquire() as ftp:
            while stack:
                dirpath, is_visited = stack.pop()

                if is_visited:
                    if dirpath == posixpath.sep:
                        continue

                    try:
                        logger.debug("Attempting to remove directory: %r", dirpath)
                        await loop.run_in_executor(
                            self._pool.executor, ftp.rmd, dirpath
                        )
                        logger.debug("Remote directory has been removed: %r", dirpath)
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

                        logger.debug("Attempting to remove: %r", entry_path)
                        await loop.run_in_executor(
                            self._pool.executor, ftp.delete, entry_path
                        )
                        logger.debug("File has been removed: %r", entry_path)
                except ftplib.all_errors as err:
                    logger.exception(
                        "An FTP error occurred while processing directory entries."
                    )
                    raise FTPError(
                        f"Failed to process directory entries for: {dirpath!r}"
                    ) from err

                except Exception as err:
                    logger.exception(
                        "An unexpected issue arose during directory entry processing."
                    )
                    raise FTPError(f"Unable to process directory: {dirpath!r}") from err

    async def rmtree2(self, path: str) -> None:
        """Recursively removes a directory tree using concurrent traversal.

        Parameters
        ----------
        path : str
            Absolute path to the directory tree root on the FTP server to remove.

        Raises
        ------
        FTPPathError
            If the provided path is not a string, is empty or whitespace-only, or
            contains prohibited traversal segments.

        FTPPathNotAbsoluteError
            If the path is not absolute.

        ValueError
            If the path resolves to the root directory.

        FTPError
            Raised when the FTP server returns an error while processing directory
            entries, when a directory listing cannot be parsed, or when walk yields
            a path outside the requested root directory.

        RuntimeError
            Raised if a walk worker encounters a critical error. The original
            exception is attached as the cause.

        Notes
        -----
        This method reserves one FTP connection up front to avoid deadlocks with the
        walk workers. Directory paths are stored in a trie and removed in post-order
        after files are deleted. This uses additional memory proportional to the
        number of directories, so the single-connection `rmtree` remains the safest
        option for extremely deep or massive trees.
        """
        loop = asyncio.get_running_loop()

        if not isinstance(path, str):
            logger.error("The remote path cannot be anything other than a string.")
            raise FTPPathError(
                "The remote path may consist exclusively of string data."
                "\nThe remote path {0!r} has type: {1!s}".format(
                    path, type(path).__name__
                )
            )

        if not path or not path.strip():
            logger.error("The remote path must include non-whitespace characters.")
            raise FTPPathError(
                "The remote path requires at least one non-whitespace character."
            )

        if _has_prohibited_segments(path):
            logger.error(
                "The remote path must not include relative navigation components."
            )
            raise FTPPathError(
                "The remote path {0!r} must exclude {1!r} and {2!r} elements.".format(
                    path, posixpath.curdir, posixpath.pardir
                )
            )

        if not path.startswith(posixpath.sep):
            logger.error(
                "An absolute path beginning at the root directory is mandatory."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous remote path: {path!r}")

        if posixpath.normpath(path) == posixpath.sep:
            logger.error("The root directory is protected against deletion.")
            raise ValueError(
                f"The FTP root directory is protected and cannot be removed: {path!r}"
            )

        # A backup option when the pool is too small.
        capacity = max(1, self._connection_parameters.max_connections // 2)
        if capacity <= 1:
            await self.rmtree(path)

            return None

        pathtrie = PathTrie()
        root_prefix = path if path.endswith(posixpath.sep) else path + posixpath.sep

        # Reserve one connection up front so walk workers do not exhaust the pool
        # and deadlock when we need a connection for deletions.
        ftp = await self._pool.get()
        try:
            async for _, entry_type, entry_path in self.walk(path):
                if not entry_path.startswith(root_prefix):
                    logger.error(
                        "The walk encountered a path outside the expected directory."
                    )
                    raise FTPError(
                        "Walk yielded a path outside the target root: {0!r}.".format(
                            entry_path
                        )
                    )
                if entry_type == FTPEntryType.DIRECTORY:
                    if path == posixpath.sep:
                        relative_path = entry_path.lstrip(posixpath.sep)
                    else:
                        relative_path = entry_path[len(root_prefix) :]

                    if relative_path:
                        pathtrie.insert(relative_path)

                    continue

                # Try to remove an entry.
                await self._rm(entry_path, ftp=ftp)

            for relative_path in reversed(pathtrie):
                if not relative_path:
                    continue

                dirpath = posixpath.join(path, relative_path)
                if dirpath == posixpath.sep:
                    continue

                try:
                    logger.debug("Attempting to remove directory: %r", dirpath)
                    await loop.run_in_executor(self._pool.executor, ftp.rmd, dirpath)
                    logger.debug("Remote directory has been removed: %r", dirpath)
                except ftplib.all_errors as err:
                    logger.exception("The directory could not be removed.")
                    raise FTPError(
                        f"Failed to remove {dirpath!r} from the FTP server."
                    ) from err

            if path != posixpath.sep:
                try:
                    logger.debug("Attempting to remove target directory: %r", path)
                    await loop.run_in_executor(self._pool.executor, ftp.rmd, path)
                    logger.debug(
                        "The specified target directory no longer exists: %r", path
                    )
                except ftplib.all_errors as err:
                    logger.exception("The target directory could not be removed.")
                    raise FTPError(
                        "Could not delete directory {0!r} on the FTP server.".format(
                            path
                        )
                    ) from err
        finally:
            await self._pool.release(ftp)
