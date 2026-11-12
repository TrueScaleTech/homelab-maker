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
- **Break it on purpose.** When you add a rule to the analysis, change the code so the
  rule is wrong and check that a test fails. A test that cannot fail proves nothing.
- **A bug becomes a test.** Write the test first and watch it fail.
- **Keep decisions out of widgets.** The model, the analysis and the view-models do not
  import Qt. The widgets only draw what they decided.
- **Comments** explain why, not what. Every `noqa` or lint exception says why.

## How the code is divided

- `model.py`, `catalog.py`, `validation.py`, `storage.py`: the homelab as immutable values,
  what each kind of device is, the consistency rules, and the project file. No Qt.
- `operations.py`, `document.py`: every edit is a pure function from one project to
  another (placing, moving, nesting, cabling, ports, services, rules, flows, zones), and the
  document keeps the undo history. No Qt.
- `checks.py`: warnings about the design (duplicate addresses, VLAN mismatches, single
  points of failure). No Qt.
- `reachability.py`, `outage.py`: whether a flow gets through and what stops it, and what
  goes down when something is switched off. No Qt.
- `export.py`, `fields.py`, `viewmodel.py`, `grid.py`, `settings.py`: the Markdown and
  draw.io writers, what is typed turned into values, what the window says and where things
  sit, and the preferences. No Qt.
- `gui/`: the window. `theme.py` holds every colour (as plain strings, so contrast is
  tested), `icons.py` draws every icon on one 24-unit grid, `canvas.py` turns gestures into
  calls to `operations`, `inspector.py`, `flows.py` and `findings.py` are the panels, and
  `main_window.py` owns the menus and the files.

Put a new decision in the modules without Qt, and keep the widgets a layer that draws it.
Never hard-code a colour in a widget: one of the two themes will go wrong and the contrast
tests will not be watching it. Add an icon in `gui/icons.py` rather than reaching for a
character from a font. `tests/test_privacy.py` fails if a module imports anything that can
open a connection or run a program.

## Testing the window

`tests/helpers.py` sends real mouse, wheel and drop events to the canvas, and the tests
use key presses and double-clicks as a person would, rather than calling the canvas's
methods. That is how a dead button or a card that does not snap is found. Close what you
open: the `window` fixture does it, and widgets that pile up make the suite slow. Modal
dialogs are replaced in the tests so that nothing waits for a click.

Qt's invisible platform has no fonts, so labels render as boxes in a screenshot taken
there. `tools/make_screenshots.py` takes a font file for exactly that reason.

## What belongs here, and what does not

HomeLabMaker draws a model and answers questions about it. Features that emulate device
firmware, connect to real devices, scan networks, or send a user's project off their
machine are out of scope. See [docs/scope.md](docs/scope.md).

Please do not include real network data in issues, tests or examples: addresses,
hostnames and device names describe a real network. Invent them.
