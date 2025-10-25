# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pathlib
import typing

from pyftpkit.connection_parameters import ConnectionParameters

__all__: list[str] = ["FTPLoader"]

class FTPLoader:
    DEFAULT_LOGGING_INTERVAL: typing.Final[int]
    def __init__(
        self, connections_parameters: ConnectionParameters, *, log_interval: int = ...
    ) -> None: ...
    @property
    def log_interval(self) -> int: ...
    @log_interval.setter
    def log_interval(self, value: typing.Any) -> None: ...
    @typing.overload
    async def download(
        self,
        src: typing.Collection[str | pathlib.Path],
        dst: str | pathlib.Path | list[str | pathlib.Path],
        /,
    ) -> None: ...
    @typing.overload
    async def download(
        self, src: str | pathlib.Path, dst: str | pathlib.Path, /
    ) -> None: ...
    @typing.overload
    async def upload(
        self,
        src: typing.Collection[str | pathlib.Path],
        dst: str | pathlib.Path | list[str | pathlib.Path],
        /,
    ) -> None: ...
    @typing.overload
    async def upload(
        self, src: str | pathlib.Path, dst: str | pathlib.Path, /
    ) -> None: ...
