# -*- coding: utf-8 -*-

# Copyright 2025 (c) Vladislav Punko <iam.vlad.punko@gmail.com>

HOMEPAGE = "https://github.com/pydantic/pydantic-settings"

LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://LICENSE;md5=9adde1a30a7e74a03e57e456551c19ae"

PYPI_PACKAGE = "pydantic_settings"
SRC_URI[md5sum] = "bfd7d2cc366483b19181428756e6a58a"
SRC_URI[sha256sum] = "d0e87a1c7d33593beb7194adb8470fc426e95ba02af83a0f23474a04c9a08180"

RDEPENDS:${PN} = "\
    python3-dotenv \
    python3-pydantic \
    python3-typing-extensions \
    python3-typing-inspection \
"

inherit pypi python_hatchling

BBCLASSEXTEND = "native nativesdk"
