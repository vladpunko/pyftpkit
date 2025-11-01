# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

HOMEPAGE = "https://github.com/pydantic/typing-inspection"

LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=07cbaa23fc9dd504fc1ea5acc23b0add"

PYPI_PACKAGE = "typing_inspection"
SRC_URI += "file://0001-fix-the-issue-with-classifiers.patch"
SRC_URI[md5] = "694cee9b0518959cd4b2b7ce2dc5cf2e"
SRC_URI[sha256sum] = "9765c87de36671694a67904bf2c96e395be9c6439bb6c87b5142569dcdd65122"

inherit pypi python_hatchling

BBCLASSEXTEND += "native nativesdk"
