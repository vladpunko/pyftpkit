# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

ARG BASE_IMAGE="vladpunko/python3-pyftpkit:3.12-qemuarm64"

FROM ${BASE_IMAGE}

LABEL maintainer="Vladislav Punko <iam.vlad.punko@gmail.com>"

STOPSIGNAL SIGTERM

ENTRYPOINT ["python3", "-m", "pyftpkit"]
