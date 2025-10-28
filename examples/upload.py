#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.loader import FTPLoader


async def main() -> None:
    connection_parameters = ConnectionParameters.model_validate(
        {
            "host": "127.0.0.1",
            "port": 21,
            "credentials": {
                "username": "test",
                "password": "test",
            },
        }
    )
    print(connection_parameters.model_dump_json(indent=2))

    ftp_loader = FTPLoader(connections_parameters=connection_parameters, log_interval=1)

    # Upload a single file to a specific file path on the server.
    # The file will be renamed to the specified name, and necessary directories will
    # be created.
    await ftp_loader.upload("./test/4f8202d1faa24c8a81062ff2721cd508.png", "/1/1.png")

    # Upload a single file into a target directory on the server.
    # Parent directories from the local path are ignored -- the file is placed directly
    # in the specified directory.
    await ftp_loader.upload("./test/e8b99852f6074e458062f613e219c0ad.png", "/images/")

    # Upload a batch of files into a single directory on the server.
    # Directory structure from the local paths is not preserved -- all files are placed
    # directly into the target directory.
    await ftp_loader.upload(
        [
            "./test/4f8202d1faa24c8a81062ff2721cd508.png",
            "./test/babf1f87eae04fb8a4fae44df0d7b26d.png",
            "./test/e8b1f46e714f411b88473b5b2feaed9a.png",
        ],
        "/images/",
    )

    # Upload a batch of files with new names and optional directory structure.
    # Each file is mapped to a specific path provided in the second argument.
    # All required directories are created automatically.
    await ftp_loader.upload(
        [
            "./test/babf1f87eae04fb8a4fae44df0d7b26d.png",
            "./test/e8b1f46e714f411b88473b5b2feaed9a.png",
        ],
        [
            "/images/test/1.png",
            "/images/test/2.png",
        ],
    )

    # Upload all files resolved from the provided source(s), computing a common
    # base directory to maintain their relative structure under the destination
    # path. The resulting uploads mirror the local directory hierarchy rooted at
    # the common path on the remote target.
    await ftp_loader.upload("./test/all/*", "/test/")


if __name__ == "__main__":
    asyncio.run(main())
