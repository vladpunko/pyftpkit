# docker

A minimal root filesystem image was built using the [Yocto Project](https://www.yoctoproject.org/) to reduce Docker image size and avoid unnecessary dependencies. This image contains only the [Python interpreter](https://www.python.org/), [cURL](https://curl.se/) with SSL support, and the required Python packages, providing a compact and controlled runtime environment optimized for the target application. Yocto's granular package management enables a compact image footprint without compromising functionality.

## Build

First, install [git-repo](https://gerrit.googlesource.com/git-repo/) on your machine to simplify managing Yocto dependencies and multiple repositories. Then, follow the commands below to create a minimal Docker-compatible image using the Yocto Project and the `meta-pyftpkit` layer:

```bash
# Step -- 1.
repo init \
    --manifest-branch=master \
    --manifest-name=manifest.xml \
    --manifest-url=https://github.com/vladpunko/pyftpkit
repo sync

cd ./docker/poky/

# Step -- 2.
source ./oe-init-build-env

bitbake-layers -h  # to validate

# Step -- 3.
bitbake-layers add-layer ../meta-openembedded/meta-oe
bitbake-layers add-layer ../meta-openembedded/meta-python
bitbake-layers add-layer ../../meta-pyftpkit
```

Open the `conf/local.conf` file in your preferred editor and locate the relevant configuration line. Modify it to set your preferred target architecture.

```conf
MACHINE ??= "qemuarm64"  # for ARM-based systems

# or

MACHINE ??= "qemux86-64"  # for x86_64-based systems
```

To reduce the number of installed packages in the Docker image, it is recommended to use the `ipk` package format. Configure this by adding the following line to your configuration file:

```conf
PACKAGE_CLASSES ?= "package_ipk"
```

Next, build the base image by running the following commands in order:

```bash
# Step -- 1.
bitbake python3-pyftpkit-image

# Step -- 2.
docker import "$(find "./tmp/deploy/images/${MACHINE:?err}" -name 'python3-image-*.tar.bz2' | head -n 1)" "python3-pyftpkit:3-12-${MACHINE:?err}"

# Step -- 3.
docker run --rm "python3-pyftpkit:3-12-${MACHINE:?err}" python3 -c 'print(__import__("sys").executable)'
```

To maintain architecture compatibility when using `docker import`, include the `--platform` flag **only** if the image was built for a different architecture than your host system. By default, Docker imports images for [the daemon's native platform](https://docs.docker.com/reference/cli/docker/image/import/#platform). To avoid runtime issues across different CPU architectures, specify the platform explicitly -- use `--platform=linux/arm64` for ARM targets or `--platform=linux/amd64` for x86 systems.
