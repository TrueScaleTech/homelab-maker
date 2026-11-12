# Security policy

## Reporting a vulnerability

Please report security issues privately through GitHub's
[security advisories](https://github.com/TrueScaleTech/homelab-maker/security/advisories/new)
rather than in a public issue. A first reply usually arrives within a few days.

Useful things to include: what you did, what happened, the platform and Python
version, and how serious you think it is.

## Status

HomeLabMaker 0.1.0 is the first release. The commitments below were written before the code
and have been checked against it for this release; where a check can be automated it is a
test, named here.

## What the application does, and does not do

It does:

- open and save project files that you choose, and keep its own settings in your
  user configuration folder;
- draw and analyse the model you built.

It does not:

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
