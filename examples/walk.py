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
            # For directories with greater depth, it is advisable to allocate more
            # connections to the pool if possible. Remember that each FTP connection
            # consumes two ports on the server, as defined by the FTP protocol standard.
            "max_connections": 10,
            # How many threads we want to run during execution.
            # To achieve maximum performance, it is recommended to use three times more
            # than the number of connections.
            "max_workers": 20,
        }
    )
    print(connection_parameters.model_dump_json(indent=2))

    async with FTPFileSystem(connection_parameters=connection_parameters) as ftpfs:
        async for rootpath, dirs, nondirs in ftpfs.walk("/"):
            print(rootpath)

            for dirpath in dirs:
                print(dirpath)

            for path in nondirs:
                print(path)


if __name__ == "__main__":
    asyncio.run(main())
