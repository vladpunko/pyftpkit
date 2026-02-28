# -*- coding: utf-8 -*-

# Created by: Vladislav Punko <iam.vlad.punko@gmail.com>
# Created date: 2025-11-01

# Tell yocto to build the image in a container-compatible format.
IMAGE_FSTYPES = "container"

inherit core-image

# Prevent generation of an empty container layer.
IMAGE_CONTAINER_NO_DUMMY = "1"

# Specify a list of packages to be included in the final image.
IMAGE_INSTALL = "\
    python3-core \
    python3-asyncio \
    python3-logging \
    python3-pyftpkit \
"

# Specify the locale for the image.
GLIBC_GENERATE_LOCALES = "C.UTF-8"
