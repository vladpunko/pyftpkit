# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import io
import logging
import os
import pathlib
import urllib.parse

import pycurl

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.exceptions import FTPError

__all__ = ["PycURL"]

logger = logging.getLogger("pyftpkit")


class PycURL:
    """A lightweight cURL wrapper for efficient FTP file transfers."""

    def __init__(self, connection_parameters: ConnectionParameters) -> None:
        self._connection_parameters = connection_parameters

    def _ensure_ftp_url(self, path: str | pathlib.Path) -> str:
        """Ensures a proper FTP URL for the given path using the connection parameters.

        Parameters
        ----------
        path : str or pathlib.Path
            The FTP path to normalize and convert into a URL.

        Returns
        -------
        str
            A fully-qualified FTP URL.
        """
        path = str(path)

        if path.startswith("ftp://"):
            return path

        # Ensure the path is consistently formatted and safely encoded for URL usage.
        normpath = urllib.parse.quote(path.strip().lstrip("/") or "/", safe="/")

        host = self._connection_parameters.host
        port = self._connection_parameters.port
        netloc = f"{host!s}:{port!s}" if port and port > 0 else host

        return urllib.parse.urlunparse(("ftp", netloc, normpath, "", "", ""))

    def download(self, src: str | pathlib.Path, dst: str | pathlib.Path) -> float:
        """Fetches a remote file and writes it to the local filesystem.

        Adds the FTP protocol prefix to the source path if missing.

        Parameters
        ----------
        src : str or pathlib.Path
            The FTP path to the remote file to be downloaded.

        dst : str or pathlib.Path
            The local filesystem path where the file will be saved.

        Returns
        -------
        float
            The total number of bytes successfully downloaded.

        Raises
        ------
        RuntimeError
            If the destination directory cannot be created or written to.

        FTPError
            If any network or FTP-related issue occurs during download.
        """
        if dirname := os.path.dirname(os.path.expanduser(dst)):
            try:
                os.makedirs(dirname, exist_ok=True)
            except OSError as err:
                logger.exception(
                    "Failed to create a new directory on the current machine."
                )
                raise RuntimeError(
                    f"Could not create target directory: {dirname!s}"
                ) from err

        curl = pycurl.Curl()
        curl.setopt(pycurl.CONNECTTIMEOUT, self._connection_parameters.timeout)
        curl.setopt(pycurl.URL, self._ensure_ftp_url(src))
        curl.setopt(
            pycurl.USERPWD,
            "{0!s}:{1!s}".format(
                self._connection_parameters.credentials.username,
                self._connection_parameters.credentials.password.get_secret_value(),
            ),
        )
        curl.setopt(pycurl.FTP_USE_EPSV, 1)
        curl.setopt(pycurl.NOSIGNAL, 1)  # essential for multi-threaded python programs
        curl.setopt(pycurl.BUFFERSIZE, io.DEFAULT_BUFFER_SIZE)
        try:
            with io.open(dst, mode="wb") as buffer:
                curl.setopt(pycurl.WRITEDATA, buffer)
                curl.perform()

                return curl.getinfo(pycurl.SIZE_DOWNLOAD)
        except pycurl.error as err:
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
            curl.close()
