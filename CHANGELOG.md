# Changelog

## [Version: 0.0.0] - 2025-04-12

### Added

- Established the initial implementation.

### Changed

- No changes in this release.

### Fixed

- No bug fixes in this release.

---

## [Version: 0.1.0] - 2025-10-29

### Added

- Created an asynchronous FTP package for high-speed operations.
- Added CLI commands to the FTP package for convenient file upload and download.
- Developed a filesystem module with utility functions:
    * `listdir` -- list files and directories.
    * `walk` -- recursively traverse directories.
    * `rm` -- remove a file.
    * `rmtree` -- recursively remove a directory.
    * `makedirs` -- create directories, including parent directories as needed.

### Changed

- No changes in this release.

### Fixed

- No bug fixes in this release.

---

## [Version: 0.1.1] - 2025-11-04

### Added

- Add the ability to pass connection parameters via CLI:
    * `--host`
    * `--port`
    * `--username`
    * `--password`
    * `--timeout`
    * `--max-connections`
    * `--max-workers`
- CLI arguments now override corresponding `.env` or environment variable settings.

### Changed

- The CLI loads environment variables from the `.env` file automatically at startup.

### Fixed

- Resolved a problem preventing logger and log interval environment variables from taking effect in CLI runs.
- Fixed the issue that allowed negative values for port, maximum connections, or maximum workers.
