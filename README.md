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

> WARNING: It is important to note that paths on an FTP server have to be absolute and start from the root. Additionally, when specifying a directory path, include a trailing `/` to clearly distinguish it from a file path.

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
# It is recommended to create a local wrapper script to simplify running this command.
docker run \
    --interactive \
    --network=host \
    --rm \
    --tty \
    --user="$(id -u):$(id -g)" \  # to avoid permission issues on mounted volumes
    --volume="$(pwd):$(pwd)" \
    --volume=/tmp:/tmp \  # this is for the logging system
    --workdir="$(pwd)" \
"docker.io/vladpunko/pyftpkit:${IMAGE_TAG:?err}" "$@"
```

To simplify configuration, the library automatically loads FTP server settings from a [.env](https://raw.githubusercontent.com/vladpunko/pyftpkit/refs/heads/master/examples/.env) file located in the current working directory.

Below are sample CLI usage scenarios, assuming a `.env` file is already present and may supply part or all of the configuration parameters:

#### Example №1

Upload one file to the target FTP directory without altering its filename.
Update the host and port using the values provided during transfer, replacing any previously loaded settings from the file.
If the destination directory is missing, create it before uploading.

```bash
pyftpkit -H 0.0.0.0 -P 2222 upload --src 1.txt --dst '/1.txt'
```

#### Example №2

Upload a batch of files to the specified directory without modifying their filenames.
Use the configuration settings defined in the file.
If the destination directory is not present, create it before uploading.

```bash
pyftpkit upload --src 1.txt 2.txt 3.txt --dst '/documents/'
```

#### Example №3

Download all content from the FTP server into the designated local folder while preserving the full directory structure.
Apply the host, port, and credentials values provided through the CLI, replacing any corresponding settings previously loaded from the file.

```bash
pyftpkit -H 0.0.0.0 -P 2222 -u admin -p admin download --src '/' --dst ./data/
```

#### Example №4

Download a selected group of files as a batch, applying new filenames during retrieval.
Use the FTP connection settings defined in the configuration file.

```bash
pyftpkit download --src 1.txt 2.txt --dst passwords.txt data.txt
```

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
