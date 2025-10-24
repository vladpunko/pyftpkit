# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio
import ftplib
import functools
import logging
import os
import pathlib
import typing

from pyftpkit._pathtrie import PathTrie
from pyftpkit._pool import FTPPoolExecutor
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError
from pyftpkit.ftp import FTP

__all__ = ["FTPFileSystem"]

logger = logging.getLogger("pyftpkit")


class FTPFileSystem:
    """Provides an FTP-backed virtual file system interface.

    This class emulates standard file system operations for files
    stored on a remote FTP server.
    """

    def __init__(self, connection_parameters: ConnectionParameters) -> None:
        self._connection_parameters = connection_parameters

        # Initialize a managed pool of pre-authenticated FTP connections. This design
        # drastically reduces the overhead of repeated handshakes and logins.
        self._pool = FTPPoolExecutor(connection_parameters=connection_parameters)

    async def __aenter__(self) -> "FTPFileSystem":
        await self._pool.open()

        return self

    async def __aexit__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        await self._pool.close()

    async def _listdir(
        self, path: str | pathlib.Path, *, ftp: FTP
    ) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
        """Retrieve the directory contents from the remote FTP server."""
        loop = asyncio.get_running_loop()

        await loop.run_in_executor(self._pool.executor, ftp.cwd, str(path))

        entries: list[str] = []
        await loop.run_in_executor(
            self._pool.executor, ftp.retrlines, "LIST", entries.append
        )

        dirs = []
        nondirs = []
        for entry in entries:
            # Skip empty or malformed lines.
            # A valid line begins with a 10-character permission field.
            if not (entry) or len(entry) < 10:
                continue

            name = entry.strip().split(maxsplit=8).pop()
            if name in (".", ".."):
                continue

            if entry.startswith("l"):
                name, _ = name.split(" -> ", maxsplit=1)

            abspath = pathlib.Path(path) / name
            if entry.startswith("d"):
                dirs.append(abspath)
            else:
                nondirs.append(abspath)

        return dirs, nondirs

    async def listdir(
        self, path: str | pathlib.Path
    ) -> tuple[list[pathlib.Path], list[pathlib.Path]]:
        """Lists the contents of a remote FTP directory.

        Parameters
        ----------
        path : str or pathlib.Path
            Remote directory path to list.

        Returns
        -------
        tuple[list[pathlib.Path], list[pathlib.Path]]
            - A list of directory paths.
            - A list of non-directory (files) paths.

        Raises
        ------
        FTPError
            If an FTP-related error occurs during listing.
        """
        ftp = await self._pool.get()
        try:
            return await self._listdir(path, ftp=ftp)
        except ftplib.all_errors as err:
            logger.exception(
                "The FTP server returned an error during directory listing."
            )
            raise FTPError(f"Failed to list this directory: {path!s}") from err

        finally:
            await self._pool.release(ftp)

    async def walk(
        self, path: str | pathlib.Path
    ) -> typing.AsyncGenerator[
        tuple[pathlib.Path, list[pathlib.Path], list[pathlib.Path]], None
    ]:
        """Asynchronously traverses a remote FTP directory tree.

        - Uses worker coroutines to parallelize listing operations across
          multiple FTP connections managed by the connection pool.

        - Traversal stops when all directories have been processed or when
          an explicit stop signal is triggered.

        Parameters
        ----------
        path : str or pathlib.Path
            Root directory path on the remote FTP server to begin traversal.

        Yields
        ------
        tuple[pathlib.Path, list[pathlib.Path], list[pathlib.Path]]
            - The current directory path.
            - A list of subdirectory paths under the current directory.
            - A list of file paths under the current directory.
        """
        stop_event = asyncio.Event()

        queue: asyncio.Queue[pathlib.Path] = asyncio.Queue()
        await queue.put(pathlib.Path(path))

        output_queue: asyncio.Queue[
            tuple[pathlib.Path, list[pathlib.Path], list[pathlib.Path]]
        ] = asyncio.Queue()

        async def _worker() -> None:
            """Worker coroutine that retrieves directories from the task queue.

            This coroutine is defined as an inner function to simplify binding
            to the correct event loop.
            """
            ftp = await self._pool.get()
            try:
                while not stop_event.is_set():
                    dirpath = None
                    try:
                        dirpath = await asyncio.wait_for(
                            queue.get(), timeout=self._connection_parameters.timeout
                        )
                    except asyncio.TimeoutError:
                        if stop_event.is_set():
                            break

                        continue

                    try:
                        dirs, nondirs = await self._listdir(dirpath, ftp=ftp)
                        await output_queue.put((pathlib.Path(dirpath), dirs, nondirs))
                        for subdirpath in dirs:
                            await queue.put(subdirpath)
                    except Exception:
                        logger.exception(
                            "An unexpected error occurred at this program runtime."
                        )
                        stop_event.set()
                    finally:
                        if dirpath is not None:
                            queue.task_done()
            except asyncio.CancelledError:
                pass
            finally:
                await self._pool.release(ftp)

        # Spawn worker tasks.
        workers = [
            asyncio.create_task(_worker())
            for _ in range(self._connection_parameters.max_workers)
        ]

        # Wait for either new results or traversal completion.
        traversal_task = asyncio.create_task(queue.join())
        get_output_task = asyncio.create_task(output_queue.get())
        try:
            pending_tasks: set[asyncio.Future[typing.Any]] = set(
                workers + [traversal_task, get_output_task]
            )
            while True:
                completed_tasks, pending_tasks = await asyncio.wait(
                    pending_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in completed_tasks:
                    if task is traversal_task:
                        break

                    if task in workers:
                        if task.exception() is not None:
                            raise task.exception()

                    if task is get_output_task:
                        if (output := task.result()) is not None:
                            yield output

                        # Replace the task.
                        get_output_task = asyncio.create_task(output_queue.get())
                        pending_tasks.add(get_output_task)

                if traversal_task.done():
                    # All directories processed.
                    break

            # Yield the final result.
            if get_output_task.done():
                if (output := get_output_task.result()) is not None:
                    yield output

            # Drain any remaining items that might have been
            # placed onto the output queue before the workers were signaled to stop.
            while not output_queue.empty():
                if (output := await output_queue.get()) is not None:
                    yield output
                output_queue.task_done()
        finally:
            stop_event.set()  # signal all workers to stop

            tasks_to_cleanup: list[asyncio.Task[typing.Any]] = workers + [
                traversal_task
            ]
            if not get_output_task.done():
                tasks_to_cleanup.append(get_output_task)

            for task in tasks_to_cleanup:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks_to_cleanup, return_exceptions=True)

    @functools.singledispatchmethod
    async def makedirs(self, path: str | pathlib.Path) -> None:
        """Recursively creates a single directory on the remote FTP server.

        The given path must be absolute and use POSIX-style separators. Each directory
        in the hierarchy is created if it does not already exist.

        Parameters
        ----------
        path : str or pathlib.Path
            Absolute remote path to ensure exists on the FTP server.

        Raises
        ------
        FTPError
            If any directory cannot be created due to permission or FTP errors.
        """
        await self.makedirs([path])

    @makedirs.register(list)
    async def _(self, paths: list[str | pathlib.Path]) -> None:
        """Recursively creates multiple directories on the remote FTP server."""
        loop = asyncio.get_running_loop()

        ftp = await self._pool.get()
        try:
            pathtrie = PathTrie()
            for path in paths:
                pathtrie.insert(str(path))

            for dirpath in pathtrie:
                if dirpath == os.sep:
                    continue

                try:
                    await loop.run_in_executor(
                        self._pool.executor, ftp.cwd, str(dirpath)
                    )
                except ftplib.all_errors as err:
                    try:
                        await loop.run_in_executor(
                            self._pool.executor, ftp.mkd, str(dirpath)
                        )
                    except ftplib.error_perm as err:
                        logger.exception("Remote directory could not be created.")
                        raise FTPError(
                            f"Unable to create directory on FTP server: {dirpath!s}."
                        ) from err
        finally:
            await self._pool.release(ftp)
