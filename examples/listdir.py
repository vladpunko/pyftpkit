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
        dirs, nondirs = await ftpfs.listdir("/")

        for dirpath in dirs:
            print(dirpath)

        for path in nondirs:
            print(path)


if __name__ == "__main__":
    asyncio.run(main())
