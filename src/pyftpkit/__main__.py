#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import argparse
import asyncio
import enum
import errno
import logging
import os
import sys
import typing
from importlib import metadata

import dotenv
import pydantic

from pyftpkit import logger_wrapper
from pyftpkit.config import Config
from pyftpkit.ftpfs import FTPFileSystem
from pyftpkit.loader import FTPLoader

logger = logging.getLogger("pyftpkit")


class FTPCommand(enum.Enum):
    DOWNLOAD = "DOWNLOAD"
    UPLOAD = "UPLOAD"
    LIST = "LIST"


class SingleOrList(argparse.Action):
    """Convert single-item lists to a single object automatically."""

    @typing.no_type_check
    def __call__(self, parser, namespace, values, *args, **kwargs) -> None:
        """Converts single-item lists into a single value and sets it on namespace.

        Called by argparse when the argument is parsed.
        """
        first, *other = values

        setattr(namespace, self.dest, first if not other else values)


class ArgumentsNamespace(argparse.Namespace):
    """Typed namespace representing all supported CLI parameters."""

    host: str | None
    port: int | None
    username: str | None
    password: str | None
    timeout: int | None
    max_connections: int | None
    max_workers: int | None

    logger_level: str
    logger_interval: int | None

    # This argument is required to allow overriding the file from which
    # environment variables are loaded.
    dotenv_path: str | None

    cmd: FTPCommand
    src: str | list[str] | None
    dst: str | list[str] | None
    recursive: bool


def parse_arguments() -> ArgumentsNamespace:
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
    parser.add_argument(
        "--logger-level",
        type=str.upper,
        metavar="LEVEL",
        choices=[
            "CRITICAL",
            "ERROR",
            "WARNING",
            "INFO",
            "DEBUG",
            "NOTSET",
        ],
        default="INFO",
        help="choose the logging level that controls message visibility",
    )
    parser.add_argument(
        "--logger-interval",
        type=int,
        metavar="NUMBER",
        help="interval for logging progress during transfers",
    )
    parser.add_argument(
        "--dotenv-path",
        type=str,
        metavar="PATH",
        default=None,
        help="path to the file with environment variables for configuration",
    )

    subparsers = parser.add_subparsers(dest="cmd", required=True)

    subparser = subparsers.add_parser(
        FTPCommand.DOWNLOAD.value.lower(), help="Download files or directories."
    )
    subparser.add_argument(
        "-s",
        "--src",
        type=str,
        required=True,
        nargs="+",
        metavar="SRC",
        action=SingleOrList,
        help="remote file(s) or directory(ies) on the FTP server to download",
    )
    subparser.add_argument(
        "-d",
        "--dst",
        type=str,
        required=True,
        nargs="+",
        metavar="DST",
        action=SingleOrList,
        help="local destination path(s) where the files or directories will be saved",
    )

    subparser = subparsers.add_parser(
        FTPCommand.UPLOAD.value.lower(), help="Upload local files or directories."
    )
    subparser.add_argument(
        "-s",
        "--src",
        type=str,
        required=True,
        nargs="+",
        metavar="SRC",
        action=SingleOrList,
        help="local file(s) or directory(ies) to upload to the FTP server",
    )
    subparser.add_argument(
        "-d",
        "--dst",
        type=str,
        required=True,
        nargs="+",
        metavar="DST",
        action=SingleOrList,
        help="remote destination path(s) on the FTP server",
    )

    subparser = subparsers.add_parser(
        FTPCommand.LIST.value.lower(), help="List files on the remote FTP server."
    )
    subparser.add_argument(
        "-R",
        "--recursive",
        action="store_true",
        help="walk through subdirectories and display their contents",
    )
    subparser.add_argument(
        "src",
        type=str,
        metavar="SRC",
        help="remote directory path to list",
    )

    return parser.parse_args(namespace=ArgumentsNamespace())


async def run() -> None:  # noqa: C901
    """Main asynchronous entry point of the application."""
    try:
        arguments = parse_arguments()

        # Assign a new severity level to the logging system.
        logger_wrapper.setup(arguments.logger_level)

        dotenv.load_dotenv(arguments.dotenv_path)
        config = Config.from_arguments(vars(arguments))

        match FTPCommand(arguments.cmd):
            case FTPCommand.DOWNLOAD:
                await FTPLoader(config=config).download(arguments.src, arguments.dst)

            case FTPCommand.UPLOAD:
                await FTPLoader(config=config).upload(arguments.src, arguments.dst)

            case FTPCommand.LIST:
                async with FTPFileSystem(
                    connection_parameters=config.connection_parameters
                ) as ftpfs:
                    # The argument parser for the listing command returns only one path
                    # as a string and no options for static verification.
                    src: str = typing.cast(str, arguments.src)

                    if arguments.recursive:
                        async for _, _, nondirs in ftpfs.walk(src):
                            for path in nondirs:
                                print(path)
                    else:
                        _, nondirs = await ftpfs.listdir(src)
                        if not nondirs:
                            logger.warning("There are no files in the provided path.")

                        for path in nondirs:
                            print(path)
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
    asyncio.run(run())


if __name__ == "__main__":
    main()
