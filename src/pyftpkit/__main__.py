#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import argparse
import asyncio
import enum
import errno
import logging
import os
import pathlib
import sys
import typing
from importlib import metadata

import pydantic

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.loader import FTPLoader

logger = logging.getLogger("pyftpkit")


class FTPCommand(enum.Enum):
    DOWNLOAD = "download"
    UPLOAD = "upload"


class SingleOrList(argparse.Action):
    """Convert single-item lists to a single object automatically."""

    @typing.no_type_check
    def __call__(self, parser, namespace, values, *args, **kwargs) -> None:
        """Converts single-item lists into a single value and sets it on namespace.

        Called by argparse when the argument is parsed.
        """
        first, *other = values

        setattr(namespace, self.dest, first if not other else values)


async def _main() -> None:
    """The command-line interface."""
    parser = argparse.ArgumentParser(
        description="A command-line tool for FTP file transfers and management."
    )
    parser.add_argument(
        "-v", "--version", action="version", version=metadata.version("pyftpkit")
    )

    subparsers = parser.add_subparsers(dest="cmd", required=True)

    download_parser = subparsers.add_parser(
        FTPCommand.DOWNLOAD.value, help="Download files or directories."
    )
    download_parser.add_argument(
        "-s",
        "--src",
        type=pathlib.Path,
        required=True,
        nargs="+",
        metavar="SRC",
        action=SingleOrList,
        help="remote file(s) or directory(ies) on the FTP server to download",
    )
    download_parser.add_argument(
        "-d",
        "--dst",
        type=pathlib.Path,
        required=True,
        nargs="+",
        metavar="DST",
        action=SingleOrList,
        help="local destination path(s) where the files or directories will be saved",
    )

    upload_parser = subparsers.add_parser(
        FTPCommand.UPLOAD.value, help="Upload local files or directories."
    )
    upload_parser.add_argument(
        "-s",
        "--src",
        type=pathlib.Path,
        required=True,
        nargs="+",
        metavar="SRC",
        action=SingleOrList,
        help="local file(s) or directory(ies) to upload to the FTP server",
    )
    upload_parser.add_argument(
        "-d",
        "--dst",
        type=pathlib.Path,
        required=True,
        nargs="+",
        metavar="DST",
        action=SingleOrList,
        help="remote destination path(s) on the FTP server",
    )

    try:
        arguments = parser.parse_args()

        ftp_loader = FTPLoader(connections_parameters=ConnectionParameters())
        match FTPCommand(arguments.cmd):
            case FTPCommand.DOWNLOAD:
                await ftp_loader.download(arguments.src, arguments.dst)

            case FTPCommand.UPLOAD:
                await ftp_loader.upload(arguments.src, arguments.dst)
    except pydantic.ValidationError as err:
        logger.error("Failed to load configuration.")
        logger.error(err)
        logger.warning(
            "Environment variables are likely not set or not loaded from the file."
        )

        sys.exit(os.EX_CONFIG)

    except Exception as err:
        logger.exception("An unexpected error occurred at this program runtime.")
        # Stop this program runtime and return the exit status code.
        sys.exit(getattr(err, "errno", errno.EPERM))

    except KeyboardInterrupt:
        logger.info(
            "Abort this program runtime as a consequence of a keyboard interrupt."
        )
        # Terminate the execution of this program due to a keyboard interruption.
        sys.exit(os.EX_OK)


def main() -> None:
    """This function is only necessary for creating an entry point script."""
    asyncio.run(_main())


if __name__ == "__main__":
    main()
