# Plan

## Current direction

Keep SpecRail small: reusable skills, templates, installation support, and an
optional queue runner. Target repositories retain their own development and
review policy.

## Completed in this direction

- Removed the repository enforcement and evidence execution layer.
- Removed dedicated verdict schemas, fixtures, and CI jobs.
- Simplified skills to direct playbooks.
- Moved earlier specs and changelog into `archive/` for provenance.

## Next work

- Use normal unit tests and Python compilation for this repository.
- Keep skill installer behavior covered by tests.
- Review future feature requests against the lightweight scope.
- Add automation only after its manual workflow has been proven and the caller
  explicitly requests it.
