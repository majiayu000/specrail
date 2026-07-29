---
name: specrail-install
description: Install, update, or inspect the repository-distributed SpecRail skills with a dry-run-first local installer.
---

# Install

1. Identify whether the caller wants inspection, preview, installation, or
   installed-copy verification. Verification is read-only and reports the
   resolved target plus every skill's expected hash, actual hash, and path.
2. Preview without writing:

```sh
python3 tools/install_codex_skills.py --repo .
```

3. Apply only when requested:

```sh
python3 tools/install_codex_skills.py --repo . --apply
```

4. Verify installed hashes when requested:

```sh
python3 tools/install_codex_skills.py --repo . --check-installed
```

An absent target root is reported as `not_installed` and skipped. A present
target with missing, drifted, unreadable, or symlinked skill files returns
non-zero and reports every affected skill. Do not silently install, overwrite
the source skill directory, or follow a symlink outside the target.
