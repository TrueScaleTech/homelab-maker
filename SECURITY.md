# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[security advisories](https://github.com/TrueScaleTech/homelab-maker/security/advisories/new)
rather than in a public issue. A first reply usually arrives within a few days.

Useful things to include: what you did, what happened, the platform and Python
version, and how serious you think it is.

## Status

HomeLabMaker is pre-alpha and has no application yet. What follows are the
commitments the application is being built to keep. They are written down first so
that the code, and its tests, are held to them. Each one will be checked against the
code before the first release.

## What the application does, and does not do

It will:

- open and save project files that you choose, and keep its own settings in your
  user configuration folder;
- draw and analyse the model you built.

It will not:

- make any network connection of its own, scan a network or probe a device;
- connect to, configure or change any real device;
- send a project, or anything about it, off your machine. There is no telemetry, no
  update check, no account and no cloud component;
- execute anything found in a project file.

## Guards

- A project file is plain JSON. Loading it never executes code.
- A file larger than a fixed limit, or written by a newer version of the format than
  the application knows, is refused with a message instead of being guessed at.
- No administrator or root privileges are required or requested.

## Your data

A project file describes your network: the address plan, the services, how it is
segmented. Treat it as sensitive. The `.gitignore` of this repository excludes the
places where your own projects would sit, but a project you save elsewhere and commit
is yours to protect. Examples shipped in this repository are invented.
