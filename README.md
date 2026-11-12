# HomeLabMaker

Draw your homelab on a grid and ask what can reach what.

HomeLabMaker is a desktop application for planning and documenting a homelab. You place
devices on a grid, nest virtual machines, containers and services inside their hosts,
join real ports with cables, and describe which service talks to which. From that model
it tells you whether a flow can get from A to B, along which path, and what stops it.

> **Status: pre-alpha, there is no application to run yet.** This repository holds the
> scope and the project scaffold. The roadmap below says what is built and what is not.

## What makes it different

- **Not a drawing tool.** In a diagramming tool a switch is a rectangle. Here a switch
  has the ports its kind says it has, and nine cables on eight ports is flagged.
- **Not a network simulator.** It does not emulate vendor firmware or a command line.
  It reasons about the model you drew, and says so next to every answer.
- **Built for a homelab.** Hosts contain virtual machines, which contain containers,
  which run services, and the catalogue is a NAS, a mini PC and a few switches rather
  than an exam topology.
- **Local only.** A project is a plain JSON file on your disk. The application makes no
  network connection, has no account and sends nothing anywhere.

The full statement of purpose, of what it will never do, and of the model is in
[docs/scope.md](docs/scope.md).

## Roadmap

- [x] Scope and project scaffold
- [ ] Model and project file
- [ ] Canvas: grid, devices, undo and redo, save and load
- [ ] Nesting, ports and links
- [ ] Addresses, VLANs and automatic checks
- [ ] Flows, reachability and the "what goes down" view
- [ ] Export (PNG, SVG, Markdown, draw.io) and an installer
- [ ] Later: rack view, power and cost, Discovery Now import, `docker-compose.yml` import

## Development

You need Python 3.11 or newer. On Windows, create the virtual environment on a short
path: Qt ships files whose paths exceed the 260-character limit when the project sits
in a deep folder.

```bash
python -m venv venv
venv/bin/pip install -e ".[dev]"   # Windows: venv\Scripts\pip
```

The four checks that CI runs:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

## About this project

Developed with the assistance of an AI coding assistant (Claude). Example data is
invented; no real network data is used anywhere in the repository.

## License

[MIT](LICENSE)
