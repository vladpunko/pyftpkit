# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-25

import enum
import typing
from concurrent.futures import ThreadPoolExecutor

from pyftpkit.connection_parameters import ConnectionParameters

__all__: list[str] = ["FTPEntryType", "FTPFileSystem"]

class FTPEntryType(int, enum.Enum):
    DIRECTORY: int
    FILE: int

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
        self, path: str
    ) -> typing.AsyncIterator[tuple[FTPEntryType, str]]: ...
    def walk(
        self, path: str
    ) -> typing.AsyncIterator[tuple[str, FTPEntryType, str]]: ...
    @typing.overload
    async def makedirs(self, paths: typing.Iterable[str]) -> None: ...
    @typing.overload
    async def makedirs(self, path: str) -> None: ...
    async def rm(self, path: str) -> None: ...
    async def rmtree(self, path: str) -> None: ...
    async def rmtree2(self, path: str) -> None: ...
