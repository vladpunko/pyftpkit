# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import pathlib
import typing

from pyftpkit.config import Config

__all__: list[str] = ["FTPLoader"]

class FTPLoader:
    def __init__(self, config: Config) -> None: ...
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
