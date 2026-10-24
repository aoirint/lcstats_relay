# Changelog

This is the canonical development and release history. Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html); entries use
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories.

## Unreleased

## 0.2.0 - 2026-10-24

### Added

- Linux amd64 and arm64 portable desktop binaries.

### Changed

- Name release archives `lcstats-relay-v{VERSION}-{OS}-{ARCH}`, using lowercase
  OS names and `amd64` or `arm64` architecture labels.
- Bundle Noto Sans JP for Japanese text rendering, including Linux ARM64 where
  the upstream engine lacks CJK system-font fallback.
- Run desktop builds on main and on explicit candidate requests, keeping routine
  pull-request CI focused on source checks and tests.

### Notes

- Linux builds target Ubuntu 22.04 with X11 and GNOME Keyring providing Secret
  Service. Linux amd64 requires an x86-64-v2 CPU.
- Windows amd64 remains supported. Windows ARM64 is unavailable because the
  current Flet runtime supports x64 Windows output only.

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
