# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pathlib
import typing
from concurrent.futures import ThreadPoolExecutor

from pyftpkit.connection_parameters import ConnectionParameters

__all__: list[str] = ["FTPFileSystem"]

class FTPFileSystem:
    def __init__(
        self,
        connection_parameters: ConnectionParameters,
        *,
        executor: ThreadPoolExecutor | None = None,
    ) -> None: ...
    async def __aenter__(self) -> FTPFileSystem: ...
    async def __aexit__(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    async def listdir(
        self, path: str | pathlib.Path
    ) -> tuple[list[pathlib.Path], list[pathlib.Path]]: ...
    def walk(
        self, path: str | pathlib.Path
    ) -> typing.AsyncIterator[
        tuple[pathlib.Path, list[pathlib.Path], list[pathlib.Path]]
    ]: ...
    @typing.overload
    async def makedirs(self, paths: typing.Collection[str | pathlib.Path]) -> None: ...
    @typing.overload
    async def makedirs(self, path: str | pathlib.Path) -> None: ...
    async def rm(self, path: str | pathlib.Path) -> None: ...
    async def rmtree(self, path: str | pathlib.Path) -> None: ...
