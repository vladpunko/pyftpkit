#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio

from pyftpkit.connection_parameters import ConnectionParameters
from pyftpkit.ftpfs import FTPFileSystem


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

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        # Use the absolute path to the file you want to delete. This eliminates
        # ambiguity in the process, since the initial directory is set by the FTP server
        # administrator, and we cannot rely on it.
        await ftpfs.rm("/1/2/3/test.py")


if __name__ == "__main__":
    asyncio.run(main())
