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
        await ftpfs.makedirs("/1/2/3/4/5/6")

        # At once creates the entire directory tree on the
        # server (faster than calling the creation function several times).
        await ftpfs.makedirs(
            [
                "/1/2/3",
                "/1/3/3",
                "/1/3/5/6/8",
                "/2/3/4/5/6/7",
                "/5/1/2/3",
                "/5/2",
                "/8/8",
            ]
        )


if __name__ == "__main__":
    asyncio.run(main())
