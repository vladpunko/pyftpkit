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
    path = pathlib.Path(path)

    if str(path).endswith(os.sep):
        return True

    if path.name.startswith(".") or path.suffix:
        return False

    return True


class FTPLoader:
    """"""

    DEFAULT_LOG_INTERVAL: typing.Final[int] = 10

    def __init__(
        self,
        connections_parameters: ConnectionParameters,
        *,
        log_interval: int = DEFAULT_LOG_INTERVAL,
    ) -> None:
        self._connections_parameters = connections_parameters

        #
        self._log_interval = log_interval

        #
        self._executor = ThreadPoolExecutor(
            max_workers=self._connections_parameters.max_workers
        )

        #
        self._pycurl = PycURL(connection_parameters=self._connections_parameters)

    @functools.singledispatchmethod
    async def download(
        self,
        src: typing.Collection[str | pathlib.Path],
        dst: str | pathlib.Path | list[str | pathlib.Path],
        /,
    ) -> None:
        """Downloads one or more files from the FTP server in batch mode."""
        loop = asyncio.get_running_loop()

        if any(map(_is_dirpath, src)):
            logger.error(
                "It is not feasible to handle directories during FTP batch downloading."
            )
            raise RuntimeError("Only file paths are allowed for batch downloads.")

        # Prepare destination paths.
        if isinstance(dst, (str, pathlib.Path)):
            dst = [os.path.join(dst, os.path.basename(path)) for path in src]
        else:
            if len(src) != len(dst):
                logger.error(
                    "Length of source list does not match length of destination list."
                )
                raise RuntimeError("Source and destination path counts must be equal.")

            if any(map(_is_dirpath, dst)):
                logger.error("One or more target paths are directories.")
                raise RuntimeError(
                    "Directories are not supported when performing a batch download."
                )

        async def _worker(
            source: str | pathlib.Path, destination: str | pathlib.Path, /, index: int
        ) -> None:
            """Worker function to download a single file."""
            await loop.run_in_executor(
                self._executor, self._pycurl.download, source, destination
            )

            if self._log_interval > 0 and index % self._log_interval == 0:
                logger.info("Downloaded %d / %d", index + 1, len(src))

        tasks = [
            _worker(source, destination, index)
            for index, (source, destination) in enumerate(zip(src, dst, strict=True))
        ]
        await asyncio.gather(*tasks)

    @download.register(pathlib.Path)
    @download.register(str)
    async def _(self, src: str | pathlib.Path, dst: str | pathlib.Path, /) -> None:
        """Downloads files or directories from the remote FTP server.

        Parameters
        ----------
        src : str or pathlib.Path
            Source path on the remote FTP server.

        dst : str or pathlib.Path
            Local destination path.

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

                    src_paths, dst_paths = zip(*paths, strict=True)
                    await self.download(src_paths, dst_paths)
