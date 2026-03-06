# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-03-01

import abc
import collections.abc
import contextlib
import logging
import os
import posixpath
import typing

from pyftpkit._paths_resolver.expander import Expander
from pyftpkit._paths_resolver.path import Path
from pyftpkit.exceptions import (
    FTPPathError,
    FTPPathNotAbsoluteError,
)

__all__ = ["Resolver", "DownloadResolver", "UploadResolver"]

logger = logging.getLogger("pyftpkit")


def _is_iterable(candidate: typing.Any) -> typing.TypeGuard[collections.abc.Iterable]:
    """Checks if the input is iterable, excluding strings, bytes, and mappings.

    Parameters
    ----------
    candidate : Any
        Object to evaluate.

    Returns
    -------
    bool
        True when the object is iterable and not a string, bytes-like, or mapping
        type, otherwise returns False.
    """
    return isinstance(candidate, collections.abc.Iterable) and not isinstance(
        candidate,
        (
            bytearray,
            bytes,
            collections.abc.Mapping,
            os.PathLike,
            str,
        ),
    )


def _validate_path(path: str | os.PathLike) -> None:
    """Validates a path.

    Parameters
    ----------
    path : str or os.PathLike
        Path string to validate for structural correctness.

    Raises
    ------
    FTPPathError
        If the path is empty, whitespace-only, contains backslashes, or
        includes traversal segments.

    Notes
    -----
    This validation prevents directory traversal and enforces normalized paths
    before performing operations.
    """
    if isinstance(path, os.PathLike):
        path = os.fspath(path)

    if not isinstance(path, str):
        logger.error("Paths must be provided as text strings.")
        raise FTPPathError(
            "Paths must be given as text strings rather than bytes: {0!r}".format(path)
        )

    if not path or not path.strip():
        logger.error("The path must not be blank or empty.")
        raise FTPPathError(
            "The path must contain non-whitespace characters: {0!r}".format(path)
        )

    if "\\" in path:
        logger.error("Paths containing backslashes are not supported.")
        raise FTPPathError(
            "The path contains unsupported backslash characters: {0!r}".format(path)
        )

    if any(
        segment in {posixpath.curdir, posixpath.pardir}
        for segment in path.split(posixpath.sep)
        if segment
    ):
        logger.error("Parent directory references are not supported in paths.")
        raise FTPPathError(
            "Parent directory segments are not permitted in paths: {0!r}".format(path)
        )


class Resolver(abc.ABC, metaclass=abc.ABCMeta):
    """Base resolver for mapping source paths to destinations."""

    def __init__(self, expander: Expander) -> None:
        self._expander = expander

    async def resolve(
        self,
        src: str | os.PathLike | typing.Iterable[str | os.PathLike],
        dst: str | os.PathLike | typing.Iterable[str | os.PathLike],
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves source and destination inputs into concrete file mappings.

        Supported combinations:
            - Single source and single destination.
            - Multiple sources with a single destination.
            - Multiple sources with multiple destinations.

        Yields
        ------
        tuple[str, str]
            Each item mapped from its origin to its destination.

        Raises
        ------
        TypeError:
            If the combination of input types is invalid.
        """
        if isinstance(src, os.PathLike):
            src = os.fspath(src)

        if isinstance(dst, os.PathLike):
            dst = os.fspath(dst)

        # Single source mapped to a single destination.
        if isinstance(src, str) and isinstance(dst, str):
            async for pair in self._one_to_one(src, dst):
                yield pair

            return

        # Multiple sources mapped to a single destination.
        # Destination is treated as a base directory.
        if _is_iterable(src) and isinstance(dst, str):
            src_iter = typing.cast(
                typing.Iterable[str | os.PathLike],
                src,
            )
            async for pair in self._many_to_one(src_iter, dst):
                yield pair

            return

        # One-to-one mapping between several sources and several destinations.
        if _is_iterable(src) and _is_iterable(dst):
            src_iter = typing.cast(
                typing.Iterable[str | os.PathLike],
                src,
            )
            dst_iter = typing.cast(
                typing.Iterable[str | os.PathLike],
                dst,
            )
            async for pair in self._many_to_many(src_iter, dst_iter):
                yield pair

            return

        logger.error("Unsupported argument combination.")
        raise TypeError(
            "Invalid argument types passed to resolve: {0!s} and {1!s}.".format(
                type(src).__name__,
                type(dst).__name__,
            )
        )

    @abc.abstractmethod
    async def _one_to_one(
        self, src: str, dst: str
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        raise NotImplementedError

        yield

    async def _many_to_one(
        self,
        src: typing.Iterable[str | os.PathLike],
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves multiple sources against a single destination.

        Each source path is processed individually and mapped to the destination.
        The destination is treated as a directory base.

        Parameters
        ----------
        src : Iterable[str] or Iterable[os.PathLike]
            An iterable of source paths.

        dst : str
            The destination path (must be a directory or treated as one).

        Yields
        ------
        tuple[str, str]
            Tuples for each source in the iterable.

        Raises
        ------
        FTPPathError
            If any source is not a string.
        """
        for src_path in src:
            if isinstance(src_path, os.PathLike):
                src_path = os.fspath(src_path)

            if not isinstance(src_path, str):
                logger.error("Each source must be a string.")
                raise FTPPathError(
                    "Provided source is not a string: {0!r}".format(src_path)
                )

            async for pair in self._one_to_one(src_path, dst):
                yield pair

    async def _many_to_many(
        self,
        src: typing.Iterable[str | os.PathLike],
        dst: typing.Iterable[str | os.PathLike],
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Pairs each source with its matching destination in a positional mapping.

        The function pairs elements from both iterables positionally.
        Both iterables must contain the same number of elements.

        Parameters
        ----------
        src : Iterable[str] or Iterable[os.PathLike]
            Iterable of source paths.

        dst : Iterable[str] or Iterable[os.PathLike]
            Iterable of destination paths.

        Yields
        ------
        tuple[str, str]
            Tuples representing resolved file mappings for each paired
            source and destination.

        Raises
        ------
        RuntimeError
            If the number of sources and destinations does not match.

        FTPPathError
            If any item in the sequences is not a string.
        """
        pairs = zip(src, dst, strict=True)

        while True:
            try:
                src_path, dst_path = next(pairs)
            except StopIteration:
                break

            except ValueError as err:
                logger.exception("Source and destination iterable length mismatch.")
                raise RuntimeError(
                    "Source and destination iterables must have equal length."
                ) from err

            if isinstance(src_path, os.PathLike):
                src_path = os.fspath(src_path)

            if isinstance(dst_path, os.PathLike):
                dst_path = os.fspath(dst_path)

            if not isinstance(src_path, str) or not isinstance(dst_path, str):
                logger.error("Both source and destination must be strings.")
                raise FTPPathError(
                    "It is not possible to process non-string paths."
                    "\nSource {0!r} has type: {1!s}"
                    "\nDestination {2!r} has type: {3!s}".format(
                        src_path,
                        type(src_path).__name__,
                        dst_path,
                        type(dst_path).__name__,
                    )
                )

            async for pair in self._one_to_one(src_path, dst_path):
                yield pair


class DownloadResolver(Resolver):
    """Resolver for remote FTP sources to local destination paths.

    The resolver applies simple, filesystem-style rules to determine how a single
    remote source maps onto a local destination:

    - A trailing slash or wildcard on the source (contents-only) expands directory
      contents directly under the destination.

    - A directory source without a trailing slash preserves the directory name
      under the destination when the destination is a directory.

    - A file source maps directly to the destination path (rename) unless the
      destination is explicitly a directory.
    """

    async def _one_to_one(
        self, src: str, dst: str
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves a single remote source against a local destination.

        Parameters
        ----------
        src : str
            Remote source path.

        dst : str
            Local destination path.

        Yields
        ------
        tuple[str, str]
            Pairs representing the resolved source and destination paths.

        Raises
        ------
        RuntimeError
            If the destination contains wildcards, points to a non-directory where a
            directory is required, or a file source uses a trailing slash or wildcard.

        FTPPathNotAbsoluteError
            If the remote source path is not absolute and does not start from the root.

        FTPPathError
            If the source or destination path is empty, contains backslashes, or
            includes traversal segments.
        """
        _validate_path(src)
        _validate_path(dst)

        if not src.startswith(posixpath.sep):
            logger.error(
                "The path is not rooted at the root directory and is not absolute."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous path: {src!r}")

        src_path = Path.parse(src)
        dst_path = Path.parse(dst)

        if dst_path.has_wildcard:
            logger.error("The destination must not contain a wildcard.")
            raise RuntimeError(
                "Wildcards are not allowed in the destination: {0!r}".format(
                    dst_path.path
                )
            )

        if (
            dst_path.has_slash
            and os.path.exists(dst_path.path)
            and not os.path.isdir(dst_path.path)
        ):
            logger.error("Existing destination is not a directory path.")
            raise RuntimeError(
                "A directory is required at destination: {0!r}".format(dst_path.path)
            )

        contents_only = src_path.has_wildcard or src_path.has_slash
        dst_is_dir = dst_path.has_slash or os.path.isdir(dst_path.path)
        dst_is_nondir = os.path.exists(dst_path.path) and not os.path.isdir(
            dst_path.path
        )

        if dst_is_nondir and contents_only:
            logger.error("Existing destination is not a directory path.")
            raise RuntimeError(
                "Expected a directory at destination: {0!r}".format(dst_path.path)
            )

        if contents_only:
            # Expand contents directly into destination.
            dst_base = dst_path.path
        elif dst_is_dir:
            dst_base = posixpath.join(dst_path.path, posixpath.basename(src_path.path))
        else:
            # Either rename or place inside destination directory.
            dst_base = dst_path.path

        async with contextlib.aclosing(
            self._expander.expand(src_path.path, dst_base)
        ) as pairs:
            if dst_is_nondir and not contents_only:
                try:
                    expanded_src, expanded_dst = await anext(pairs)
                except StopAsyncIteration:
                    logger.error("Existing destination is not a directory entry.")
                    raise RuntimeError(
                        "A directory is required at destination: {0!r}".format(
                            dst_path.path
                        )
                    ) from None

                if expanded_src != src_path.path:
                    logger.error("Existing destination is not a directory entry.")
                    raise RuntimeError(
                        "A directory is required at destination: {0!r}".format(
                            dst_path.path
                        )
                    )

                yield expanded_src, expanded_dst

                return

            async for expanded_src, expanded_dst in pairs:
                if contents_only and expanded_src == src_path.path:
                    logger.error("The source path uses an unsupported suffix.")
                    raise RuntimeError(
                        "Trailing slash or wildcard is directory-only: {0!r}".format(
                            src_path.path
                        )
                    )

                # Preserve the source directory name when the destination is treated as
                # not-a-directory (based on path syntax or current filesystem state).
                if (
                    not contents_only
                    and not dst_is_dir
                    and expanded_src != src_path.path
                ):
                    relative_path = expanded_src[len(src_path.path) :].lstrip(
                        posixpath.sep
                    )

                    rebased_dst = posixpath.join(
                        dst_path.path,
                        posixpath.basename(src_path.path),
                        relative_path,
                    )
                    yield expanded_src, rebased_dst

                    continue

                yield expanded_src, expanded_dst

    async def _many_to_one(
        self,
        src: typing.Iterable[str | os.PathLike],
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves multiple sources against a single local destination directory.

        The destination is always treated as a directory to keep mappings consistent.
        If the destination exists and is not a directory, an error is raised.
        """
        _validate_path(dst)

        dst_path = Path.parse(dst)

        if os.path.exists(dst_path.path) and not os.path.isdir(dst_path.path):
            logger.error("Destination exists and is not a directory.")
            raise RuntimeError(
                "Destination must be a directory: {0!r}".format(dst_path.path)
            )

        # Normalizing to a directory avoids ambiguous semantics and ensures
        # consistent mapping of multiple sources into one destination folder.
        if not dst_path.has_slash and not dst_path.has_wildcard:
            dst = dst_path.path + posixpath.sep

        async for pair in super()._many_to_one(src, dst):
            yield pair


class UploadResolver(Resolver):
    """Resolver for uploading local sources to remote destinations.

    The resolver applies syntactic rules to determine how a single source
    path should map to a single destination path:

    - If the source ends with a trailing slash or wildcard (contents-only), map
      its contents under the destination base.

    - If the source is a directory (no trailing slash), preserve the source
      directory name under the destination base.

    - If the source is a file and the destination ends with a slash, place it in
      that directory with its original name.

    - Otherwise, treat the destination as a literal target path (file rename).
    """

    async def _one_to_one(
        self, src: str, dst: str
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves a single source against a single destination.

        Parameters
        ----------
        src : str
            Source path.

        dst : str
            Destination path.

        Yields
        ------
        tuple[str, str]
            Tuples mapping concrete source files to their resolved destination paths.

        Raises
        ------
        RuntimeError
            If the source does not exist or is an unsupported type.

        FTPPathNotAbsoluteError
            If the remote destination path is not an absolute path from the root.

        FTPPathError
            If the source or destination path is empty, contains backslashes, or
            includes traversal segments.
        """
        _validate_path(src)
        _validate_path(dst)

        if not dst.startswith(posixpath.sep):
            logger.error(
                "The path is not absolute and does not start from the root directory."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous path: {dst!r}")

        src_path = Path.parse(src)
        dst_path = Path.parse(dst)

        if dst_path.has_wildcard:
            logger.error("Destination must not include a wildcard.")
            raise RuntimeError(
                "Destination must not include a wildcard: {0!r}".format(dst_path.path)
            )

        if not os.path.exists(src_path.path):
            logger.error("Source does not exist.")
            raise RuntimeError(
                "Source path is invalid or missing: {0!r}".format(src_path.path)
            )

        if os.path.islink(src_path.path):
            logger.error("Unsupported source type.")
            raise RuntimeError(
                "Source points to a symlink and cannot be processed: {0!r}".format(
                    src_path.path
                )
            )

        src_is_dir = os.path.isdir(src_path.path)
        if not src_is_dir and (src_path.has_slash or src_path.has_wildcard):
            logger.error("File source has an unsupported suffix.")
            raise RuntimeError(
                "Trailing slash or wildcard applies to directories only: {0!r}".format(
                    src_path.path
                )
            )

        name = os.path.basename(src_path.path)
        if src_is_dir and (src_path.has_slash or src_path.has_wildcard):
            # Contents only: the contents of the source directory are mapped
            # directly under the destination base path.
            dst_base = dst_path.path
        elif src_is_dir:
            # Preserve directory name: the source directory is placed under the
            # destination path.
            dst_base = posixpath.join(dst_path.path, name)
        elif dst_path.has_slash:
            # File to directory: the source is placed inside the destination directory.
            dst_base = posixpath.join(dst_path.path, name)
        else:
            # File rename: the destination is treated as the target path.
            dst_base = dst_path.path

        async for pair in self._expander.expand(src_path.path, dst_base):
            yield pair

    async def _many_to_one(
        self,
        src: typing.Iterable[str | os.PathLike],
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves multiple local sources against a single destination.

        The destination is always treated as a directory to prevent collisions.
        """
        _validate_path(dst)

        if not dst.startswith(posixpath.sep):
            logger.error(
                "The path does not start at the root directory and is not absolute."
            )
            raise FTPPathNotAbsoluteError(f"Ambiguous path: {dst!r}")

        dst_path = Path.parse(dst)

        if not dst_path.has_slash and not dst_path.has_wildcard:
            dst = dst_path.path + posixpath.sep

        async for pair in super()._many_to_one(src, dst):
            yield pair
