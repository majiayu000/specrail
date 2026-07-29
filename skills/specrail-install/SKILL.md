---
name: specrail-install
description: Install, update, or inspect the repository-distributed SpecRail skills with a dry-run-first local installer.
---

# Install

1. Identify whether the caller wants inspection, preview, installation, or
   installed-copy verification.
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

Report the target directory and every changed or mismatched skill. Do not
overwrite the source skill directory.
