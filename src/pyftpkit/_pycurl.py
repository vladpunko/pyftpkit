# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import contextlib
import io
import logging
import os
import posixpath
import queue
import typing
import urllib.parse

import pycurl

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError

__all__ = ["PycURL", "PycURLPoolManager"]

logger = logging.getLogger("pyftpkit")


class PycURL:
    """A lightweight cURL wrapper for efficient FTP file transfers."""

    def __init__(self, connection_parameters: ConnectionParameters) -> None:
        self._connection_parameters = connection_parameters

        # Initialize a single cURL instance to retain connection state.
        # This allows efficient reuse of existing network sessions
        # instead of establishing a new connection per request.
        self._curl = pycurl.Curl()
        self._curl.setopt(pycurl.CONNECTTIMEOUT, self._connection_parameters.timeout)
        self._curl.setopt(
            pycurl.USERPWD,
            "{0!s}:{1!s}".format(
                self._connection_parameters.credentials.username,
                self._connection_parameters.credentials.password.get_secret_value(),
            ),
        )
        self._curl.setopt(pycurl.FORBID_REUSE, 0)  # keep connection in cache for reuse
        self._curl.setopt(pycurl.FTP_FILEMETHOD, pycurl.FTPMETHOD_NOCWD)
        self._curl.setopt(pycurl.FTP_USE_EPSV, 1)
        self._curl.setopt(pycurl.NOSIGNAL, 1)  # important for multi-threading
        self._curl.setopt(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE)
        for option, value in self._connection_parameters.extra_options.items():
            self._curl.setopt(option, value)

    def _ensure_ftp_url(self, path: str) -> str:
        """Ensures a proper FTP URL for the given path using the connection parameters.

        Parameters
        ----------
        path : str
            The FTP path to normalize and convert into a URL.

        Returns
        -------
        str
            A fully-qualified FTP URL.
        """
        if path.startswith("ftp://"):
            return path

        # Ensure the path is consistently formatted and safely encoded for URL usage.
        # Use a double slash at the root to indicate an absolute FTP path
        # in compliance with RFC 1738.
        if path.startswith("/"):
            path = "/" + path.lstrip("/")

        normpath = urllib.parse.quote(path, safe="/")

        host = self._connection_parameters.host
        port = self._connection_parameters.port
        netloc = f"{host!s}:{port!s}" if port and port > 0 else host

        return urllib.parse.urlunparse(("ftp", netloc, normpath, "", "", ""))

    def close(self) -> None:
        """Releases all resources."""
        self._curl.close()

    def download(self, src: str, dst: str) -> float:
        """Fetches a remote file and writes it to the local filesystem.

        Adds the FTP protocol prefix to the source path if missing.

        Parameters
        ----------
        src : str
            The FTP path to the remote file to be downloaded.

        dst : str
            The local filesystem path where the file will be saved.

        Returns
        -------
        float
            The total number of bytes successfully downloaded.

        Raises
        ------
        TypeError
            If either the source or destination path is not a string.

        ValueError
            If the source or destination path is empty or contains only whitespace.

        RuntimeError
            If the source path is ambiguous (not absolute) or
            if the destination directory cannot be created or written to.

        FTPError
            If any network or FTP-related issue occurs during download.
        """
        if not isinstance(src, str) or not isinstance(dst, str):
            logger.error("The source and destination paths must both be strings.")
            raise TypeError(
                "Source and destination paths are required to be strings."
                "\nSource {0!r} has type: {1!s}"
                "\nDestination {2!r} has type: {3!s}".format(
                    src,
                    type(src).__name__,
                    dst,
                    type(dst).__name__,
                )
            )

        if not src or not src.strip():
            logger.error("The source path cannot be empty or whitespace.")
            raise ValueError(
                "The source path must not be empty or consist only of whitespace."
            )

        if not dst or not dst.strip():
            logger.error("The destination path cannot be empty or whitespace.")
            raise ValueError(
                "The destination path must not be empty or consist only of whitespace."
            )

        if not src.startswith("/"):
            logger.error(
                "The source path is not absolute and does not start from the root."
            )
            raise RuntimeError(f"Ambiguous source path: {src!s}")

        src = posixpath.normpath(src.strip())
        dst = os.path.normpath(os.path.expanduser(dst.strip()))

        if dirname := os.path.dirname(dst):
            try:
                os.makedirs(dirname, exist_ok=True)
            except OSError as err:
                logger.exception(
                    "Failed to create a new directory on the current machine."
                )
                raise RuntimeError(
                    f"Could not create target directory: {dirname!s}"
                ) from err

        src = self._ensure_ftp_url(src)
        logger.debug(
            "Starting FTP download of '%s' to '%s' on the local machine.", src, dst
        )

        try:
            self._curl.setopt(pycurl.URL, src)
            with io.open(dst, mode="wb") as buffer:
                self._curl.setopt(pycurl.WRITEFUNCTION, buffer.write)
                self._curl.perform()

                size_bytes = typing.cast(
                    float, self._curl.getinfo(pycurl.SIZE_DOWNLOAD)  # type: ignore
                )
                logger.debug(
                    "Finished moving %d bytes from the FTP server '%s' to '%s'.",
                    size_bytes,
                    src,
                    dst,
                )

                return size_bytes
        except pycurl.error as err:
            # The file should be deleted so that no damaged or incomplete data remains.
            if os.path.exists(dst):
                with contextlib.suppress(OSError):
                    os.remove(dst)

            logger.exception("An unexpected error occurred while fetching the data.")
            raise FTPError(
                f"Encountered an error while trying to fetch the data from: {src!s}"
            ) from err

        except (IOError, OSError) as err:
            logger.exception(
                "An error occurred while trying to write the buffer to disk."
            )
            raise RuntimeError(f"Failed to write buffer data to: {dst!s}") from err

        finally:
            # Override this option to prevent retaining a reference to a file
            # that has already been closed.
            self._curl.setopt(pycurl.WRITEFUNCTION, lambda x: len(x))

    def upload(self, src: str, dst: str) -> None:
        """Uploads a local file to the remote FTP server.

        Automatically converts the destination path to a full FTP URL and supports
        passive mode transfers. All missing directories must be created before
        uploading to the remote server.

        Parameters
        ----------
        src : str
            Path to the local file to upload.

        dst : str
            Path on the FTP server where the file should be placed.

        Raises
        ------
        TypeError
            If either the source or destination path is not a string.

        ValueError
            If the source or destination path is empty or contains only whitespace.

        RuntimeError
            If the destination path is ambiguous (not absolute) or
            if reading the local file fails.

        FTPError
            If the FTP upload fails due to network or server-side issues.
        """
        if not isinstance(src, str) or not isinstance(dst, str):
            logger.error(
                "The source path and the destination path must each be a string."
            )
            raise TypeError(
                "Both the source and destination need to be strings."
                "\nSource {0!r} has type: {1!s}"
                "\nDestination {2!r} has type: {3!s}".format(
                    src,
                    type(src).__name__,
                    dst,
                    type(dst).__name__,
                )
            )

        if not src or not src.strip():
            logger.error("A source path of only whitespace is invalid.")
            raise ValueError(
                "The source path must include at least one non-whitespace character."
            )

        if not dst or not dst.strip():
            logger.error("A destination path of only whitespace is invalid.")
            raise ValueError(
                "The destination path cannot be empty or contain only blank characters."
            )

        if not dst.startswith("/"):
            logger.error(
                "The destination path is not absolute and does not start from the root."
            )
            raise RuntimeError(f"Ambiguous destination path: {dst!s}")

        src = os.path.normpath(os.path.expanduser(src.strip()))
        dst = posixpath.normpath(dst.strip())

        dst = self._ensure_ftp_url(dst)
        logger.debug(
            "Uploading '%s' from local system to '%s' on the FTP server.", src, dst
        )

        try:
            self._curl.setopt(pycurl.URL, dst)
            # Create any missing remote directories in the destination path
            # before attempting the upload operation.
            self._curl.setopt(pycurl.FTP_CREATE_MISSING_DIRS, 1)
            self._curl.setopt(pycurl.INFILESIZE, os.path.getsize(src))
            self._curl.setopt(pycurl.UPLOAD, 1)
            with io.open(src, mode="rb") as stream:
                self._curl.setopt(pycurl.READFUNCTION, stream.read)
                self._curl.perform()
                logger.debug(
                    "Finished uploading '%s' to '%s' on the FTP server.", src, dst
                )
        except pycurl.error as err:
            logger.exception("File could not be uploaded to the FTP server.")
            raise FTPError(
                f"Could not upload {src!r} to {dst!r} on FTP server."
            ) from err

        except (IOError, OSError) as err:
            logger.exception("File read operation failed on local system.")
            raise RuntimeError(
                f"An error occurred while accessing the local file: {src!s}."
            ) from err

        finally:
            # Clear transfer-specific settings to make the handle
            # ready for the next request.
            self._curl.setopt(pycurl.INFILESIZE, -1)
            self._curl.setopt(pycurl.READFUNCTION, lambda x: b"")
            self._curl.setopt(pycurl.UPLOAD, 0)


class PycURLPoolManager:
    """Pool of reusable `PycURL` instances to enable concurrent FTP transfers
    while minimizing connection overhead.

    Each `PycURL` instance maintains a persistent cURL handle that can be reused
    for multiple uploads or downloads, allowing efficient handling of many
    small files without repeatedly establishing new connections."""

    _pool: queue.LifoQueue[PycURL]

    def __init__(self, connection_parameters: ConnectionParameters) -> None:
        self._connection_parameters = connection_parameters

        self._pool = queue.LifoQueue(
            maxsize=max(1, self._connection_parameters.max_connections // 2)
        )
        for _ in range(self._pool.maxsize):
            self._pool.put(PycURL(connection_parameters=self._connection_parameters))

        # Indicator used to ensure active connections are not returned
        # to a pool that has already been closed.
        self._shutdown = False

    def close(self) -> None:
        """Closes all `PycURL` instances in the pool and releases resources."""
        self._shutdown = True

        while not self._pool.empty():
            try:
                curl = self._pool.get_nowait()  # retrieve without blocking
                curl.close()
            except queue.Empty:
                break

    @contextlib.contextmanager
    def acquire(self) -> typing.Iterator[PycURL]:
        """Context manager for safely acquiring a `PycURL` instance from the pool.

        The instance is automatically returned to the pool after the context exits.
        If the pool manager is shut down while an instance is in use, the instance
        will be closed upon release.

        Yields
        ------
        PycURL
            A reusable instance for performing uploads or downloads.
        """
        curl = self._pool.get()
        logger.debug("Acquired instance: %d", id(curl))
        try:
            yield curl
        finally:
            if self._shutdown:
                logger.debug("Closing instance during shutdown: %d", id(curl))
                curl.close()
            else:
                self._pool.put(curl)
                logger.debug("Released instance: %d", id(curl))

    def download(self, src: str, dst: str) -> None:
        """Downloads a file from the FTP server using a pooled `PycURL` instance.

        Parameters
        ----------
        src : str
            Remote FTP path of the file to download.

        dst : str
            Local path where the file will be saved.
        """
        with self.acquire() as curl:
            curl.download(src, dst)

    def upload(self, src: str, dst: str) -> None:
        """Uploads a local file to the FTP server using a pooled `PycURL` instance.

        Parameters
        ----------
        src : str
            Path to the local file to upload.

        dst : str
            Destination path on the FTP server.
        """
        with self.acquire() as curl:
            curl.upload(src, dst)
