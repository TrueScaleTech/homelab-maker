# Release checklist

Everything before the last step is local and can be repeated. Nothing is published until the
last step.

## Before tagging

- [ ] `CHANGELOG.md` has a section `## X.Y.Z - date`. The release workflow uses it as the
      notes and stops if it is missing.
- [ ] `src/homelab_maker/__init__.py` has the version, and `pip install -e .` has been run
      again so that the installed metadata agrees (a test checks it).
- [ ] `ruff check .`, `ruff format --check .`, `mypy` and `pytest` all pass, on Windows and
      on Linux (CI runs both).
- [ ] `python tools/make_screenshots.py docs/images <font file>` was run and the images were
      looked at: the README shows what the window looks like now.
- [ ] Every command in the README was run as written.
- [ ] The privacy audit below is clean.
- [ ] The tree is clean and the commits are signed: `git log --show-signature -5`.

## Privacy audit

Search the tracked files for names, paths and secrets, and for addresses:

```bash
git ls-files | xargs grep -nIiE "password|secret|token|api[_-]?key|c:.users|/home/"
git ls-files | xargs grep -nIE "[0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}[.][0-9]{1,3}"
git log --format='%an <%ae>' | sort -u
```

- Nothing that names a real person, company, client, host or path.
- Every address is in a documentation range (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24)
  or in the private ranges used by the invented example.
- The only author is the project's own name and its no-reply address.

## Tagging

```bash
git tag -s vX.Y.Z -m "HomeLabMaker X.Y.Z"
git push origin main vX.Y.Z
```

The workflow builds Windows and Linux, starts every file once, and creates a **draft**
pre-release with the files and `SHA256SUMS.txt`.

## Publishing

- [ ] Download the files from the draft and compare them with `SHA256SUMS.txt`.
- [ ] Install the Windows installer on a machine that is not the build machine and open the
      example.
- [ ] Run the AppImage on a Linux desktop and open the example.
- [ ] Edit the draft: untick "pre-release" only when the project is ready to be called stable.
- [ ] Publish.

## After publishing

- [ ] Private vulnerability reporting, secret scanning and Dependabot are on.
- [ ] The release page shows the files and the notes.
