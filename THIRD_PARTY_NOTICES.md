# Third-Party Notices

Unless otherwise specified, repository content is licensed under the
[MIT License](LICENSE). The entry below identifies APM-deployed content whose
upstream license and notices continue to apply.

## aoirint/skills

- Source: [aoirint/skills](https://github.com/aoirint/skills), selected Skill
  directories under `.apm/skills/`
- Pinned commit:
  [`d160f841b2565a018fd97ef1a199e8019221fe44`](https://github.com/aoirint/skills/tree/d160f841b2565a018fd97ef1a199e8019221fe44)
- Deployed paths: selected directories under `.agents/skills/`, as recorded in
  `apm.lock.yaml`
- License: MIT; see the
  [upstream license](https://github.com/aoirint/skills/blob/d160f841b2565a018fd97ef1a199e8019221fe44/LICENSE)
- Copyright: Copyright (c) 2026 aoirint
- Notice: the selected Skill directories contain no additional copyright or
  NOTICE files.
- Cooldown: the selected commit was published on 2026-09-01 and has completed
  the normal seven-day waiting period. Dependencies remain subject to
  independent review.

## Desktop distributions

Binary archives include components under their original licenses. The app's MIT
license does not replace them.

- Flet and its SecureStorage wrapper: Apache-2.0; retain the official Flet
  1.0.4 license in `licenses/FLET-LICENSE.txt`.
- dart_bridge 1.10.0: MIT; retain `licenses/DART-BRIDGE-LICENSE.txt`.
- CPython 3.14.8 and incorporated components: retain the official Windows
  collection and versioned Python license document in
  `licenses/PYTHON-WINDOWS-LICENSE.txt` and `licenses/PYTHON-license.rst`.
  The Windows collection includes Microsoft runtime terms. Unused Tk and debug
  runtime files are excluded. SQLite is public domain. The bundled liblzma
  library is public-domain code; retain `licenses/LIBLZMA-COPYING.txt`.
- Linux CPython 3.14.8: retain the license shipped in the reviewed runtime
  archive as `licenses/PYTHON-LINUX-LICENSE.txt` and the versioned Python license
  document. Its native library matches the 20261013 python-build-standalone
  x86-64-v2 or aarch64 distribution. Retain its embedded-library notices and provenance in
  `licenses/python/`. Unused DBM and Tk extensions are excluded.
  Linux links desktop and system libraries supplied by the target
  distribution; those system packages are not included in the app archive.
- Flutter and Dart: retain their licenses and the generated Flutter
  `data/flutter_assets/NOTICES.Z` collection.
- Runtime Python wheels retain their `.dist-info` license files. Dart package
  licenses are copied to `licenses/dart/`; its `SOURCES.json` lists exact
  versioned source archives and hashes, including source availability for
  covered packages. These upstream sources are unmodified.

Source license copies and their provenance are recorded in
`packaging/licenses/SOURCES.json`. Review build inputs and license collection
again when the native dependency profile changes.
