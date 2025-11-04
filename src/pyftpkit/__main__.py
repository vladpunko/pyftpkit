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

import dotenv

# This must occur before importing any package components that depend
# on environment-based settings.
dotenv.load_dotenv(".env")

import pydantic  # noqa: E402

from pyftpkit import logger_wrapper  # noqa: E402
from pyftpkit.connection_parameters import ConnectionParameters  # noqa: E402
from pyftpkit.loader import FTPLoader  # noqa: E402

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
    parser.add_argument(
        "-H",
        "--host",
        type=str,
        metavar="HOST",
        help="FTP server hostname or IP address to connect to",
    )
    parser.add_argument(
        "-P",
        "--port",
        type=int,
        metavar="PORT",
        help="FTP server port number",
    )
    parser.add_argument(
        "-u",
        "--username",
        type=str,
        metavar="USERNAME",
        help="username for FTP authentication",
    )
    parser.add_argument(
        "-p",
        "--password",
        type=str,
        metavar="PASSWORD",
        help="password for FTP authentication",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="connection timeout in seconds",
    )
    parser.add_argument(
        "--max-connections",
        type=int,
        metavar="N",
        help="maximum number of simultaneous FTP connections",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        metavar="N",
        help=(
            "maximum number of worker threads for parallel operations"
            "\n(threads per connection)"
        ),
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

    logger_wrapper.setup()
    try:
        arguments = parser.parse_args()

        ftp_loader = FTPLoader(
            connections_parameters=ConnectionParameters.from_arguments(arguments)
        )
        match FTPCommand(arguments.cmd):
            case FTPCommand.DOWNLOAD:
                await ftp_loader.download(arguments.src, arguments.dst)

            case FTPCommand.UPLOAD:
                await ftp_loader.upload(arguments.src, arguments.dst)
    except pydantic.ValidationError as err:
        logger.error("Failed to load and set configuration.")
        logger.error(err)
        logger.warning(
            "Configuration parameters may be unset, improperly loaded, or invalid."
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
