# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import logging
import logging.config
import os
import pathlib
import tempfile
import typing

__all__ = ["setup"]


def setup(level: str = "INFO", path: str | pathlib.Path | None = None) -> None:
    """Sets up the logging system for the packagae."""
    logging.config.dictConfig(
        {
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(levelname)s :: %(name)s :: %(message)s",
                },
            },
            "handlers": {
                "file": {
                    "class": "logging.FileHandler",
                    "formatter": "default",
                    "filename": os.environ.get(
                        "PYFTPKIT_LOGGER_PATH",
                        (
                            str(path)
                            if path is not None
                            else os.path.join(tempfile.gettempdir(), "pyftpkit.log")
                        ),
                    ),
                    "mode": "at",
                    "encoding": "utf-8",
                },
                "stderr": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stderr",
                },
            },
            "loggers": {
                "pyftpkit": {
                    "handlers": ["file", "stderr"],
                    "level": typing.cast(
                        int,
                        {
                            "CRITICAL": logging.CRITICAL,
                            "ERROR": logging.ERROR,
                            "WARNING": logging.WARNING,
                            "INFO": logging.INFO,
                            "DEBUG": logging.DEBUG,
                            "NOTSET": logging.NOTSET,
                        }.get(os.environ.get("PYFTPKIT_LOGGER_LEVEL", level).upper()),
                    ),
                },
            },
            "version": 1,
        }
    )
