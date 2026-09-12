# LESSONS.md — every CI red we've earned, and how to never repeat it

Rule zero: a red build is a question ("which job? which step? which line?"),
never a mood. Read the failing step first; fix second.

## A. Missing build dependencies

**Reds:** `build-essential` absent (`dpkg-checkbuilddeps` error);
`pybuild-plugin-pyproject` absent (PEP517 plugin error).
**Rule:** every tool named in `debian/control` Build-Depends must appear in
the CI install line. When adding a build backend/plugin, update both files
in the same commit.
**Current script** (`.github/workflows/release.yml`, build job):
```yaml
run: sudo apt-get update -q && sudo apt-get install -y -q build-essential debhelper dh-python pybuild-plugin-pyproject devscripts python3-setuptools
```

## B. Invalid workflow file

**Reds:** non-existent `workflows: write` permission scope (that scope is for
GitHub App / fine-grained tokens, NOT the workflow `permissions:` block);
duplicated `run:` key that local YAML parsers silently accept.
**Rule:** after touching the workflow, run the strict self-check (duplicate
keys fail). CI runs this check on itself before building anything.
**Current script** (build job, first step after checkout):
```yaml
- name: Validate workflow YAML (strict, duplicate keys fail)
  run: |
    pip install -q pyyaml
    python3 - <<'EOF'
    import yaml
    class Strict(yaml.SafeLoader): pass
    def nodup(loader, node, deep=False):
        mapping = {}
        for k, v in node.value:
            key = loader.construct_object(k, deep=True)
            if key in mapping:
                raise ValueError(f"duplicate key: {key}")
            mapping[key] = loader.construct_object(v, deep=True)
        return mapping
    Strict.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, nodup)
    yaml.load(open('.github/workflows/release.yml'), Loader=Strict)
    print('workflow YAML OK')
    EOF
```

## C. Action version rot (Node warnings)

**Reds (warnings):** Node 20 deprecation annotations on `checkout@v4`,
`setup-python@v5`, `upload-artifact@v4`, third-party release action.
**Rule:** first-party actions at latest majors (`checkout@v5`,
`setup-python@v6`); prefer `gh` CLI over third-party Node actions;
delete steps whose output duplicates the release itself (`upload-artifact`
died this way). Zero Node actions = zero Node warnings, permanently.

## D. Tests assuming the runner looks like the dev machine

**Reds:** `import rich` on bare runners; `yt-dlp` missing on macOS (test
expected fetch mode, app correctly showed the install hint instead);
bare `import curses` on Windows (its `curses/__init__` self-destructs);
Unix-only path assertions on Windows.
**Rule:** every external capability a test needs gets EITHER a pip install
in CI or a `skipUnless`/`skipTest` guard — never assume. Platform modules
in tests always import with fallback to the app's own shim. Path
assertions branch on `sys.platform`.
**Current script** (test job):
```yaml
- name: Install test deps (ffmpeg + pip packages)
  if: runner.os == 'Linux'
  run: |
    sudo apt-get update -q && sudo apt-get install -y -q ffmpeg
    pip install -q yt-dlp
- name: Install test deps (pip packages)
  if: runner.os != 'Linux'
  run: pip install -q yt-dlp
```
```python
@unittest.skipUnless(HAS_RICH, "no rich on this machine")
# and: try: import curses / except ImportError: from tilawah.tui import curses
```

## E. Races and teardown crashes

**Reds:** green suite followed by exit 139 (segfault) — background worker
mid-SQLite-write during interpreter teardown; duplicate concurrent release
runs racing `gh release create` (HTTP 422 for the loser).
**Rule:** workers are cancelled and joined before stores close
(`App.close()`); unit tests never spawn network/SQLite threads
(`refresh=False`, stop-then-close discipline). Releases are serialized
and idempotent:
```yaml
concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: true
```
```bash
if gh release view "$TAG" >/dev/null 2>&1; then
  echo "release exists - uploading assets only"
else
  gh release create "$TAG" ... && fi
gh release upload "$TAG" ... --clobber
```

## F. Version discipline

**Reds (silent killer):** v1.0.4 tagged without bumping code — CI went
green building a `.deb` stamped 1.0.3, the APT repo "updated" to the same
version, and `apt upgrade` correctly found nothing for days.
**Rule:** tag == code == changelog head, enforced in CI before anything
builds:
```yaml
- name: Version consistency (tag == code == changelog)
  run: |
    TAG="${{ github.ref_name }}"
    CODE="$(python3 -c 'import tilawah; print(tilawah.__version__)')"
    [ "$TAG" = "v$CODE" ] || { echo "tag $TAG != code v$CODE"; exit 1; }
    head -1 debian/changelog | grep -q "($CODE-1)" || { echo "changelog top != $CODE-1"; exit 1; }
```

## G. Read the failure, not the dashboard

**Reds:** fail-fast cancelled Ubuntu mid-green-run, hiding a full pass
behind one Windows red; duplicate rows per tag looked like new failures.
**Rule:** `fail-fast: false` on the test matrix so every OS reports
independently. Triage order: open the failed *job*, read the failing
*step*, ignore cancelled dominoes.
```yaml
strategy:
  fail-fast: false
  matrix:
    os: [ubuntu-latest, macos-latest, windows-latest]
```

## Checklist before every tag push

1. `python3 -m unittest discover -s tests` green locally.
2. `dpkg-parsechangelog -l debian/changelog -S Version` matches the tag.
3. Workflow edited? Strict YAML check passes.
4. New test needs a tool/file/OS feature? Guard or pip-install decided.
5. After push: one green run per OS, then check the *server*
   (`curl .../Packages`) — green CI without a moved server version
   means the deploy step failed silently.
