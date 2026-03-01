# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-10-26

import logging
import logging.config
import os
import posixpath
import tempfile
import typing

__all__ = ["setup"]


def setup(level: str = "INFO", path: str | None = None) -> None:
    """Sets up the logging system for the package."""
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
                            path
                            if path is not None
                            else posixpath.join(tempfile.gettempdir(), "pyftpkit.log")
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
                        }.get(
                            os.environ.get("PYFTPKIT_LOGGER_LEVEL", level).upper(),
                            logging.INFO,  # fallback if provided unknown value
                        ),
                    ),
                },
            },
            "version": 1,
        }
    )
