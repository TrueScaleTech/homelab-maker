# Contributing

Thanks for taking a look. Issues and pull requests are welcome.

## Getting set up

```bash
python -m venv venv
venv/bin/pip install -e ".[dev]"   # Windows: venv\Scripts\pip
```

On Windows, create the virtual environment on a short path (for example under your
profile, outside the project folder). Qt ships files whose paths exceed the
260-character limit when the project sits in a deep folder.

## Before opening a pull request

```bash
ruff check .
ruff format --check .
mypy
pytest
```

CI runs the same four on Linux and Windows, for Python 3.11, 3.12 and 3.13.

## House rules

- **Commits** follow [Conventional Commits](https://www.conventionalcommits.org):
  `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:`, `chore:`. One change per
  commit, with a message that says why.
- **Tests** come with behaviour. The suite needs neither a network nor a screen: the
  model and the analysis are plain Python, and the window is tested on Qt's `offscreen`
  platform by simulating real clicks and drags, not by calling internal methods.
- **A bug becomes a test.** Write the test first and watch it fail.
- **Keep decisions out of widgets.** The model, the analysis and the view-models do not
  import Qt. The widgets only draw what they decided.
- **Comments** explain why, not what. Every `noqa` or lint exception says why.

## What belongs here, and what does not

HomeLabMaker draws a model and answers questions about it. Features that emulate device
firmware, connect to real devices, scan networks, or send a user's project off their
machine are out of scope. See [docs/scope.md](docs/scope.md).

Please do not include real network data in issues, tests or examples: addresses,
hostnames and device names describe a real network. Invent them.
