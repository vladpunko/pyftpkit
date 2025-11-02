# pyftpkit

![hooks](https://github.com/vladpunko/pyftpkit/actions/workflows/hooks.yml/badge.svg)
![tests](https://github.com/vladpunko/pyftpkit/actions/workflows/tests.yml/badge.svg)

Asynchronous library for FTP-based file system operations.

## Installation

Since this library relies on [cURL](https://curl.se/) and [PycURL](http://pycurl.io/), you are to install the necessary system packages before proceeding with the installation:

```bash
# On Ubuntu:
set -ex \
    && sudo apt-get update --yes \
    && sudo apt-get install --yes \
        curl \
        libcurl4-openssl-dev \
        libssl-dev \
    && sudo apt-get clean \
    && sudo rm --recursive --force /var/lib/apt/lists/*

# On Fedora:
set -ex \
    && sudo dnf update --assumeyes \
    && sudo dnf install --assumeyes \
        curl \
        libcurl-devel \
        openssl-devel \
    && sudo dnf clean all
```

Use [pip](https://pip.pypa.io/en/stable/) to install `pyftpkit` together with its command-line interface by running the following command:

```bash
python3 -m pip install --user pyftpkit
```

## Basic usage

Here is a list of examples demonstrating the library's usage across various covered scenarios:

* [download](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/download.py)
* [listdir](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/listdir.py)
* [makedirs](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/makedirs.py)
* [rm](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/rm.py)
* [rmtree](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/rmtree.py)
* [upload](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/upload.py)
* [walk](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/walk.py)

Here is a simple example demonstrating how to upload and download data to and from an FTP server using the command-line interface provided by this library:

```bash
# The library provides two main commands -- one for uploading and one for downloading data.
# Since both share the same interface, you can switch between them simply by changing
# the command name in the command-line interface.
docker run \
    --interactive \
    --network host \
    --rm \
    --tty \
    --user "$(id -u):$(id -g)" \  # to avoid permission issues on mounted volumes
    --volume "$(pwd):$(pwd)" \
    --volume /tmp:/tmp \  # this is for the logging system
    --workdir "$(pwd)" \
"docker.io/vladpunko/pyftpkit:${IMAGE_TAG:?err}" upload --src ./examples/* --dst '/'
```

To simplify configuration, the library automatically loads FTP server settings from a [.env](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/.env) file located in the current working directory.

## Contributing

Pull requests are welcome.
Please open an issue first to discuss what should be changed.

Please make sure to update tests as appropriate.

```bash
# Step -- 1.
python3 -m venv .venv && source ./.venv/bin/activate && pip install pre-commit tox

# Step -- 2.
pre-commit install --config .githooks.yml

# Step -- 3.
tox && tox -e lint
```

## License

[MIT](https://choosealicense.com/licenses/mit/)
