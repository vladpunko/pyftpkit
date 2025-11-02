# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio
import functools
import logging
import os
import pathlib
import typing
from concurrent.futures import ThreadPoolExecutor

from pyftpkit._pycurl import PycURL
from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.ftpfs import FTPFileSystem

__all__ = ["FTPLoader"]

logger = logging.getLogger("pyftpkit")


def _is_dirpath(path: str | pathlib.Path) -> bool:
    """Detects if a path is a directory using its trailing slash or separator."""
    if str(path).endswith(os.sep):
        return True

    path = pathlib.Path(path)

    if path.name.startswith(".") or path.suffix:
        return False

    return True


class FTPLoader:
    """Asynchronous FTP loader for performing concurrent file system operations.

    Provides an interface for FTP file uploads and downloads with configurable
    concurrency and periodic progress logging.
    """

    DEFAULT_LOGGER_INTERVAL: typing.Final[int] = int(
        os.environ.get("PYFTPKIT_LOGGER_INTERVAL", 10)
    )

    def __init__(
        self,
        connections_parameters: ConnectionParameters,
        *,
        log_interval: int = DEFAULT_LOGGER_INTERVAL,
    ) -> None:
        self._connections_parameters = connections_parameters

        # Interval for logging progress during transfers.
        self._log_interval = log_interval

        # Thread pool executor shared across all related classes to ensure a single
        # pool of threads is used and prevent unexpected resource leaks.
        self._executor = ThreadPoolExecutor(
            max_workers=self._connections_parameters.max_workers
        )

        self._pycurl = PycURL(connection_parameters=self._connections_parameters)

    @property
    def log_interval(self) -> int:
        """Returns the current logging interval for upload progress."""
        return self._log_interval

    @log_interval.setter
    def log_interval(self, value: typing.Any) -> None:
        """Sets the logging interval."""
        if not isinstance(value, int) or value <= 0:
            raise ValueError("Logging interval must be a positive integer.")

        self._log_interval = value

    @functools.singledispatchmethod
    async def download(
        self,
        src: typing.Collection[str | pathlib.Path],
        dst: str | pathlib.Path | list[str | pathlib.Path],
        /,
    ) -> None:
        """Downloads one or more files from the FTP server in batch mode."""
        loop = asyncio.get_running_loop()

        for path in (path for path in src if _is_dirpath(path)):
            logger.error(
                "It is not feasible to handle directories during FTP batch downloading."
            )
            raise RuntimeError(f"Invalid path for batch download: {path!s}")

        # Prepare destination paths.
        if isinstance(dst, (str, pathlib.Path)):
            dst = [os.path.join(dst, os.path.basename(path)) for path in src]
        else:
            if len(src) != len(dst):
                logger.error(
                    "Length of source list does not match length of destination list."
                )
                raise RuntimeError("Source and destination path counts must be equal.")

            for path in (path for path in dst if _is_dirpath(path)):
                logger.error("One or more target paths are directories.")
                raise RuntimeError(
                    f"Cannot include directory {str(path)!r} in batch downloads."
                )

        tasks = [
            loop.run_in_executor(
                self._executor, self._pycurl.download, source, destination
            )
            for source, destination in zip(src, dst, strict=True)
        ]
        index: int = 0
        for future in asyncio.as_completed(tasks):
            await future
            index += 1

            if index % self._log_interval == 0:
                logger.info("Downloaded: %d / %d", index, len(src))

        logger.info("All downloads finished: %d / %d", len(src), len(dst))

    @download.register(pathlib.Path)
    @download.register(str)
    async def _(self, src: str | pathlib.Path, dst: str | pathlib.Path, /) -> None:
        """Downloads files or directories from the remote FTP server.

        Parameters
        ----------
        src : str or pathlib.Path, or collection of paths
            Source path(s) on the remote FTP server.

        dst : str or pathlib.Path, or list of paths
            Local destination path(s).

        Raises
        ------
        RuntimeError
            If attempting to download a directory into a file destination.
        """
        src = str(src).rstrip("*")

        match (_is_dirpath(src), _is_dirpath(dst)):
            case (False, False):  # file to file
                await self.download([src], [dst])

            case (False, True):  # file to directory
                await self.download([src], dst)

            case (True, False):  # directory to file
                logger.error(
                    "Only directory destinations are valid for directory sources."
                )
                raise RuntimeError(f"Cannot download a directory into: {dst!s}")

            case (True, True):  # directory to directory
                async with FTPFileSystem(
                    connection_parameters=self._connections_parameters,
                    executor=self._executor,
                ) as ftpfs:
                    paths: list[tuple[pathlib.Path, str]] = []
                    async for _, _, other in ftpfs.walk(src):
                        for path in other:
                            dst_path = os.path.join(dst, os.path.relpath(path, src))
                            paths.append((path, dst_path))

                    if not paths:
                        logger.warning("No data found to download.")

                        return None

                    src_paths, dst_paths = zip(*paths, strict=True)
                    await self.download(src_paths, dst_paths)

    @functools.singledispatchmethod
    async def upload(
        self,
        src: typing.Collection[str | pathlib.Path],
        dst: str | pathlib.Path | list[str | pathlib.Path],
        /,
    ) -> None:
        """Asynchronously uploads a single file to the specified destination."""
        loop = asyncio.get_running_loop()

        sources: list[pathlib.Path] = []
        for path in src:
            match (path := pathlib.Path(path)):
                case _ if path.is_dir():
                    sources.extend((item for item in path.rglob("*") if item.is_file()))

                case _ if path.is_file():
                    sources.append(path)

                case _:
                    logger.warning("Skipping invalid path: %s", path)

        # Build list of target paths.
        if isinstance(dst, (str, pathlib.Path)):
            dst = pathlib.Path(dst)

            if not sources:
                logger.warning("No data to upload.")

                return None

            commonpath = pathlib.Path(os.path.commonpath(sources))

            dst = [
                (
                    dst / source.name
                    if source == commonpath
                    else dst / source.relative_to(commonpath)
                )
                for source in sources
            ]
        else:
            if len(sources) != len(dst):
                logger.error("Source and destination lists must match one-to-one.")
                raise RuntimeError(
                    "Number of sources does not match number of destinations."
                )

            for path in (path for path in dst if _is_dirpath(path)):
                logger.error("Directories are not allowed as destination paths.")
                raise RuntimeError(
                    f"Upload failed due to invalid destination path: {path!s}"
                )

        async with FTPFileSystem(
            connection_parameters=self._connections_parameters,
            executor=self._executor,
        ) as ftpfs:
            # Tests indicate that building the directory hierarchy before upload leads
            # to better performance in concurrent transfer scenarios.
            await ftpfs.makedirs({pathlib.Path(path).parent for path in dst})

        tasks = [
            loop.run_in_executor(
                self._executor, self._pycurl.upload, source, destination
            )
            for source, destination in zip(sources, dst, strict=True)
        ]
        index: int = 0
        for future in asyncio.as_completed(tasks):
            await future
            index += 1

            if index % self._log_interval == 0:
                logger.info("Uploaded: %d / %d", index, len(sources))

        logger.info("All uploads finished: %d / %d", len(sources), len(dst))

    @upload.register(pathlib.Path)
    @upload.register(str)
    async def _(self, src: str | pathlib.Path, dst: str | pathlib.Path, /) -> None:
        """Uploads single or multiple files and directories asynchronously.

        Parameters
        ----------
        src : str or pathlib.Path, or collection of paths
            Source file(s) or directory(s) to upload.

        dst : str or pathlib.Path, or list of paths
            Destination path(s).

        Raises
        ------
        RuntimeError
            Upload failed because there are no files, a destination is a directory, or
            a directory was mapped to a file
        """
        src = str(src).rstrip("*")

        match (os.path.isfile(src), os.path.isdir(src), _is_dirpath(dst)):
            case (True, _, False):  # file to file
                await self.upload([src], [dst])

            case (True, _, True):  # file to directory
                await self.upload([src], dst)

            case (_, True, False):  # directory to file
                logger.error("Cannot upload a directory to a single file destination.")
                raise RuntimeError(
                    "Directories in source require destinations of directory type."
                    f"\nSource: {src!s}"
                    f"\nDestination: {dst!s}"
                )

            case (_, True, True):  # directory to directory
                await self.upload([src], dst)
