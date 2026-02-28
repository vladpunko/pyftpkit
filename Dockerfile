# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-11-02

ARG BASE_IMAGE="vladpunko/python3-pyftpkit:3.12-qemuarm64"

FROM ${BASE_IMAGE}

LABEL maintainer="Vladislav Punko <iam.vlad.punko@gmail.com>"

STOPSIGNAL SIGTERM

ENTRYPOINT ["python3", "-m", "pyftpkit"]
