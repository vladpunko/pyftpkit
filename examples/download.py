#!/usr/bin/env python3

# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import asyncio

import pycurl

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
            # You can provide additional cURL options if you have
            # specific requirements.
            # See information: https://curl.se/libcurl/c/curl_easy_setopt.html
            "extra_options": {
                pycurl.VERBOSE: 1,
            },
        }
    )
    print(connection_parameters.model_dump_json(indent=2))

    ftp_loader = FTPLoader(connections_parameters=connection_parameters, log_interval=1)

    # Download a file to the specified location. All necessary directories will be
    # created automatically, and the file will be renamed according to the name
    # you specify.
    await ftp_loader.download("/546e2c53e11f40c8873e3bfdaef31c11.jpg", "./test/1.jpg")

    # Download a file into the specified directory. Parent directories from the server's
    # file path will not be recreated -- the file will simply be placed in the directory
    # you specify.
    await ftp_loader.download(
        "/6b50dcff/babf1f87eae04fb8a4fae44df0d7b26d.png", "./test/"
    )

    # Download a batch of files. All files will be placed in the specified directory
    # without preserving the original folder structure.
    await ftp_loader.download(
        [
            "/6b50dcff/145ad816/4f8202d1faa24c8a81062ff2721cd508.png",
            "/6b50dcff/145ad816/e8b99852f6074e458062f613e219c0ad.png",
            "/6b50dcff/47265533/e8b1f46e714f411b88473b5b2feaed9a.png",
        ],
        "./test/",
    )

    # Download a batch of files and rename each according to the new names you provide.
    # Each file will be associated with an entity from the second function argument, and
    # all necessary directories will be created automatically.
    await ftp_loader.download(
        [
            "/6b50dcff/145ad816/1a06ad22/0c4eda13a88b474897728d5ea4350552.png",
            "/6b50dcff/145ad816/1a06ad22/46135f4fe27c41e387fbb22476b2472c.png",
        ],
        [
            "./test/1.png",
            "./test/2.png",
        ],
    )

    # You can specify a path to a directory on the server. In this case, the directory
    # will be traversed, and all collected files will be downloaded while preserving
    # the original directory structure.
    await ftp_loader.download("/*", "./test/all/")


if __name__ == "__main__":
    asyncio.run(main())
