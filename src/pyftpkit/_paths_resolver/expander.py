# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-02-28

import abc
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
        """
        # Short-circuit on single files to avoid walking a non-directory.
        if os.path.isfile(src) and not os.path.islink(src):
            yield src, dst

            return

        for rootpath, _, nondirs in os.walk(src):
            for path in nondirs:
                src_path = os.path.join(rootpath, path)
                if os.path.islink(src_path) or not os.path.isfile(src_path):
                    continue

                dst_path = os.path.join(
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
        connections_parameters: ConnectionParameters,
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None:
        super().__init__()

        self._connections_parameters = connections_parameters
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
        """
        async with FTPFileSystem(
            connection_parameters=self._connections_parameters,
            executor=self._executor,
        ) as ftpfs:
            src = posixpath.normpath(src)
            # Attempt a parent directory lookup to catch a direct file match
            # and avoid walking the tree.
            if src != posixpath.sep:
                dirname = posixpath.dirname(src) or posixpath.sep

                if name := posixpath.basename(src):
                    target_path = posixpath.join(dirname, name)
                    async for entry_type, entry_path in ftpfs.listdir(dirname):
                        if entry_path != target_path:
                            continue

                        if entry_type == FTPEntryType.FILE:
                            yield src, dst

                            return

                        break

            async for _, entry_type, entry_path in ftpfs.walk(src):
                if entry_type != FTPEntryType.FILE:
                    continue

                dst_path = os.path.join(
                    dst,
                    posixpath.relpath(entry_path, src),
                )

                yield entry_path, dst_path
