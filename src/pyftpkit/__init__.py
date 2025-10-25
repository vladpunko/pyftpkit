# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

import logging
import logging.config
import os
import typing

logging.config.dictConfig(
    {
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(levelname)s :: %(name)s :: %(message)s",
            },
        },
        "handlers": {
            "stderr": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stderr",
            },
            "logfile": {
                "class": "logging.FileHandler",
                "formatter": "default",
                "filename": os.environ.get("PYFTPKIT_LOGGER_PATH", "/tmp/pyftpkit.log"),
                "mode": "at",
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "pyftpkit": {
                "handlers": ["stderr", "logfile"],
                "level": typing.cast(
                    int,
                    {
                        "CRITICAL": logging.CRITICAL,
                        "ERROR": logging.ERROR,
                        "WARNING": logging.WARNING,
                        "INFO": logging.INFO,
                        "DEBUG": logging.DEBUG,
                        "NOTSET": logging.NOTSET,
                    }.get(os.environ.get("PYFTPKIT_LOGGER_LEVEL", "warning").upper()),
                ),
            },
        },
        "version": 1,
    }
)
