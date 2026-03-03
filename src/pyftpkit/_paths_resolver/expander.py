# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import abc
import contextlib
import logging
import os
import posixpath
import typing
from concurrent.futures import ThreadPoolExecutor

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.ftpfs import (
    FTPEntryType,
    FTPFileSystem,
)

__all__ = ["Expander", "LocalTreeExpander", "RemoteFTPExpander"]

logger = logging.getLogger("pyftpkit")


class Expander(abc.ABC, metaclass=abc.ABCMeta):
    """Abstract planner that derives explicit file pairs from a given source."""

    @abc.abstractmethod
    async def expand(
        self,
        src: str,
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        raise NotImplementedError

        # Trick to avoid unexpected behavior regarding asynchronous generators.
        # See information: https://github.com/python/mypy/issues/5070
        yield


class LocalTreeExpander(Expander):
    """Expander that recursively enumerates all files in a local filesystem
    directory tree."""

    async def expand(
        self,
        src: str,
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Expands a local source path into concrete file mappings.

        Parameters
        ----------
        src : str
            Source path to expand.

        dst : str
            Base destination path corresponding to the source.

        Yields
        ------
        tuple[str, str]
            Pairs indicating the origin and destination for every file.

        Raises
        ------
        RuntimeError
            If the source does not exist, is a symlink, ends with a separator while
            pointing to a file, or if a walk yields a path outside the requested root.

        FTPPathError
            If the remote source path is invalid or contains prohibited traversal
            segments.

        FTPPathNotAbsoluteError
            If the remote source path is not absolute.

        Raises
        ------
        RuntimeError
            If the source does not exist or is a symlink.
        """
        if src.endswith(os.path.sep):
            trimmed_src = src.rstrip(os.path.sep)
            if trimmed_src and os.path.isfile(trimmed_src):
                logger.error("Source path ends with a separator but points to a file.")
                raise RuntimeError(
                    "File path includes an invalid trailing separator: {0!r}".format(
                        src
                    )
                )

        if not os.path.exists(src):
            logger.error("Source does not exist.")
            raise RuntimeError(
                "The source path provided is invalid or cannot be found: {0!r}".format(
                    src
                )
            )

        if os.path.islink(src):
            logger.error("Unsupported source type.")
            raise RuntimeError(
                "Source points to a symlink and cannot be processed: {0!r}".format(src)
            )

        # Short-circuit on single files to avoid walking a non-directory.
        if os.path.isfile(src):
            yield src, dst

            return

        for rootpath, _, nondirs in os.walk(src):
            for path in nondirs:
                src_path = posixpath.join(rootpath, path)
                if os.path.islink(src_path) or not os.path.isfile(src_path):
                    continue

                dst_path = posixpath.join(
                    dst,
                    os.path.relpath(src_path, src),
                )

                yield src_path, dst_path


class RemoteFTPExpander(Expander):
    """Expander that enumerates remote FTP files.

    This class is required to build file mappings for an FTP remote server.
    """

    def __init__(
        self,
        connection_parameters: ConnectionParameters,
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        super().__init__()

        self._connection_parameters = connection_parameters
        self._executor = executor

    async def expand(
        self,
        src: str,
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Expands a remote source path into concrete file mappings.

        Parameters
        ----------
        src : str
            Remote source path to expand.

        dst : str
            Base destination path corresponding to the source.

        Yields
        ------
        tuple[str, str]
            Pairs indicating the origin and destination for every file.

        Raises
        ------
        RuntimeError
            If a walk yields a path outside the requested root directory.

        FTPPathError
            If the remote source path is invalid or contains prohibited traversal
            segments.

        FTPPathNotAbsoluteError
            If the remote source path is not absolute.
        """
        async with FTPFileSystem(
            connection_parameters=self._connection_parameters,
            executor=self._executor,
        ) as ftpfs:
            root_prefix = src if src.endswith(posixpath.sep) else src + posixpath.sep
            # Attempt a parent directory lookup to catch a direct file match
            # and avoid walking the tree.
            if src != posixpath.sep:
                dirname = posixpath.dirname(src) or posixpath.sep

                if name := posixpath.basename(src):
                    target_path = posixpath.join(dirname, name)
                    # Ensure the generator is closed before the FTP pool shuts down.
                    async with contextlib.aclosing(
                        ftpfs.listdir(dirname)
                    ) as entries_iterator:
                        async for entry_type, entry_path in entries_iterator:
                            if entry_path != target_path:
                                continue

                            if entry_type == FTPEntryType.FILE:
                                yield src, dst

                                return

                            break

            async for _, entry_type, entry_path in ftpfs.walk(src):
                if entry_type != FTPEntryType.FILE:
                    continue

                if not entry_path.startswith(root_prefix):
                    logger.error(
                        "Walk yielded a path outside the requested source directory."
                    )
                    raise RuntimeError(
                        "Walk yielded a path outside the requested root: {0!r}".format(
                            entry_path
                        )
                    )

                dst_path = posixpath.join(
                    dst,
                    posixpath.relpath(entry_path, src),
                )

                yield entry_path, dst_path
