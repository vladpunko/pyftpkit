# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2026-03-01

import abc
import collections.abc
import logging
import os
import posixpath
import typing

from pyftpkit._paths_resolver.expander import Expander
from pyftpkit._paths_resolver.path import Path
from pyftpkit.exceptions import FTPPathError

__all__ = ["Resolver", "UploadResolver"]

logger = logging.getLogger("pyftpkit")


def _is_iterable(candidate: typing.Any) -> bool:
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
            str,
            collections.abc.Mapping,
        ),
    )


class Resolver(abc.ABC, metaclass=abc.ABCMeta):
    """Base resolver for mapping source paths to destinations."""

    def __init__(self, expander: Expander) -> None:
        self._expander = expander

    async def resolve(
        self,
        src: str | typing.Iterable[str],
        dst: str | typing.Iterable[str],
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
        match (src, dst):
            # Single source mapped to a single destination.
            case (str(), str()):
                async for pair in self._one_to_one(src, dst):
                    yield pair

            # Multiple sources mapped to a single destination.
            # Destination is treated as a base directory.
            case (_, str()) if _is_iterable(src):
                async for pair in self._many_to_one(src, dst):
                    yield pair

            # One-to-one mapping between several sources and several destinations.
            case (_, _) if _is_iterable(src) and _is_iterable(dst):
                async for pair in self._many_to_many(src, dst):
                    yield pair

            case _:
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
        src: typing.Iterable[str],
        dst: str,
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Resolves multiple sources against a single destination.

        Each source path is processed individually and mapped to the destination.
        The destination is treated as a directory base.

        Parameters
        ----------
        src : Iterable[str]
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
            if not isinstance(src_path, str):
                logger.error("Each source must be a string.")
                raise FTPPathError(
                    "Provided source is not a string: {0!r}".format(src_path)
                )

            async for pair in self._one_to_one(src_path, dst):
                yield pair

    async def _many_to_many(
        self,
        src: typing.Iterable[str],
        dst: typing.Iterable[str],
    ) -> typing.AsyncGenerator[tuple[str, str], None]:
        """Pairs each source with its matching destination in a positional mapping.

        The function pairs elements from both iterables positionally.
        Both iterables must contain the same number of elements.

        Parameters
        ----------
        src : Iterable[str]
            Iterable of source paths.

        dst : Iterable[str]
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
        """
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
        match (
            src_is_dir,
            src_path.has_slash or src_path.has_wildcard,
            dst_path.has_slash,
        ):
            # Contents only: the contents of the source directory are mapped
            # directly under the destination base path.
            case (True, True, _):
                dst_base = dst_path.path

            # Preserve directory name: the source directory is placed under the
            # destination path.
            case (True, False, _):
                dst_base = posixpath.join(dst_path.path, name)

            # File to directory: the source is placed inside the destination directory.
            case (False, False, True):
                dst_base = posixpath.join(dst_path.path, name)

            # File rename: the destination is treated as the target path.
            case (False, False, False):
                dst_base = dst_path.path

        async for pair in self._expander.expand(src_path.path, dst_base):
            yield pair
