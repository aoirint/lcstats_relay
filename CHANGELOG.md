# Changelog

This is the canonical development and release history. Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html); entries use
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories.

## Unreleased

### Added

- Build Linux amd64 desktop archives and verify rendering and GNOME Keyring
  credential persistence across separate application launches.

### Changed

- Include the `v` version prefix, lowercase OS and CPU architecture in release
  archive names, for example `lcstats-relay-v0.1.1-windows-amd64.zip`.

- Run desktop builds on main and on explicit candidate requests, keeping routine
  pull-request CI focused on source checks and tests.

## 0.1.0 - 2026-10-24

### Changed

- Promote `0.1.0-alpha.1` to the first stable Windows x64 release.

### Notes

- Application features and platform support are unchanged from `0.1.0-alpha.1`.

## 0.1.0-alpha.1 - 2026-10-24

### Added

- First public Windows x64 portable desktop release of LCStats Relay.
- Receive statistics from LCStatsTracker and save the original JSON locally.
- Optionally forward statistics to Google Sheets through a Google Apps Script
  web app, with persistent retries for failed deliveries.
- Display connection status and received/delivered counts in the desktop monitor.
- Configure the tracker endpoint, local save directory and GAS authentication
  from the app.
- Keep diagnostic logs across sessions for troubleshooting.

### Notes

- Windows x64 is the packaged platform for this initial release.
- Google Sheets delivery requires a configured Google Apps Script web app.
  See [setup instructions](README.md#configure-and-use).
