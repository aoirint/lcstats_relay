# Changelog

This is the canonical development and GitHub release history. Versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html); entries use
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories.

## Unreleased

### Added

- Relay local tracker events to Google Sheets, retain local JSON archives, and
  retry failed deliveries from a durable queue.
- Provide connection status, receive/delivery counts, configuration and
  memory-only GAS authentication in a desktop monitor.
- Retain operational traces and payload correlation IDs across restarts with
  Python standard logging and file rotation.
- Define release identity in the root `VERSION` file and maintain this history.

### Fixed

- Accept a GAS delivery only after an HTTP success and a JSON acknowledgement
  with Boolean `ok: true`; queue rejected or unexpected responses.

### Security

- Update TLS trust and vulnerable HTTP dependencies. The exact certifi pin and
  the Python/uv security updates use the maintainer-authorized cooldown
  exceptions documented in the development guide.

### Notes

- Initial binary validation uses `0.1.0-alpha.N` versions before `0.1.0`.
- Existing queue records require the current schema and valid correlation ID;
  unsupported records report a read error and remain untouched.
- `VERSION` value `0.0.0` reserves the unreleased development state.
