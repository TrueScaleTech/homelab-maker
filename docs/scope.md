# HomeLabMaker: scope and limits

This page is written before the code on purpose. It says what HomeLabMaker is for and
what it will never do. The README and `SECURITY.md` are derived from it, and a feature
that contradicts it needs this page changed first.

## Purpose

HomeLabMaker is a desktop application for drawing a homelab on a grid and asking
questions about the drawing.

It sits between a diagramming tool and a network simulator:

- A diagramming tool (draw.io) draws shapes. A switch is a rectangle, and nothing
  checks that its eight ports are not hosting nine cables.
- A network simulator (Packet Tracer) emulates vendor firmware. It is powerful, and it
  is built for exam topologies and for vendor devices, not for a NAS, a mini PC and a
  few VMs on a shelf.

HomeLabMaker keeps a **model** of the homelab. Devices have ports, addresses and
services. Hosts contain virtual machines, which contain containers, which run
services. Cables join real ports. Flows say which service talks to which. From that
model the application answers: *can A reach B, along which path, and what stops it?*
and *what goes down if this device is switched off?*

## Principles

1. **One engine, one drawing layer.** The model and the analysis do not import the GUI
   toolkit. The window only draws what they decided, so almost everything is tested
   without a display.
2. **The answer is about the model, not about the network.** Reachability is computed
   from what the user drew. The application says so wherever it shows a result, and it
   lists what it does not model.
3. **Nothing leaves the computer.** A project file describes a network: its address
   plan, its services, how it is segmented. That is sensitive. The application makes
   no network connection of its own and has no telemetry, no account and no update
   check.
4. **Every decision lives in one place.** Colours, grid size, the catalogue of device
   kinds and the file format version are each defined once and read everywhere.
5. **Claims are verified.** A command in the README has been run. A rule in the
   analysis has a test that failed before it passed.

## What it will never do

- Emulate the firmware or the command line of a real device.
- Connect to, configure or push anything to a real device.
- Scan the network or discover devices. That is what Discovery Now does; an import of
  its export is possible later, but this application does not probe anything itself.
- Send a project, or anything about it, off the machine.
- Require an account, a server or a cloud service.

## The model, in outline

This is a sketch, not an interface. Names will settle while the model is written.

- **Node**: a thing on the grid. It has a kind (router, switch, access point, NAS,
  mini PC, virtual machine, container, service, and so on), a name, a position, an
  optional parent (nesting), interfaces and services.
- **Interface**: a named port on a node, with addresses, a VLAN and a mode (access or
  trunk). A switch node has the number of ports its kind says it has.
- **Link**: a cable or a wireless link between two interfaces, with a medium and a
  speed.
- **Zone**: a named area on the grid (LAN, IoT, guests, DMZ) that groups nodes by
  purpose.
- **Flow**: a statement that one service talks to another, over a protocol and a port.
- **Rule**: a simplified allow or deny entry on a node that filters traffic (a
  firewall, a router with access lists).

### Reachability, first version

A flow from A to B is *reachable* when a path of links exists from A to B, the VLAN
membership of every interface on the path allows the traffic to cross it, every
routing hop is a node that routes, and no rule on the path denies it. The result
carries the path, and for a blocked flow it names the first thing that stops it.

Deliberately not modelled in the first version: NAT, dynamic routing protocols, ARP
and DHCP behaviour, bandwidth and latency, wireless roaming, and the state of a real
firewall's connection table. The application lists these next to every result.

## Project file

A project is one JSON file: a format version, the nodes, the links, the zones, the
flows. Keys are sorted and the layout is stable, so the file diffs cleanly in git and
a diagram can live next to the infrastructure it describes. The file is data only:
loading it never executes anything, and a file over a size limit, or from a newer format
version than the application knows, is refused with a message rather than guessed at.

## Milestones

| Milestone | Content |
| --- | --- |
| **M0** | This page, repository scaffold, tooling, CI, git identity. |
| **M1** | Model and project file, pure and tested. No window. |
| **M2** | The canvas: grid, placing devices from the catalogue, moving, selecting, undo and redo, save and load. First packaged build on a provisional tag, to find packaging problems while there is little code. |
| **M3** | Nesting (host, virtual machine, container, service), ports and links. |
| **M4** | Interfaces, addresses, VLANs, and the automatic checks (duplicate addresses, ports over capacity, trunk and VLAN mismatches). |
| **M5** | Flows, reachability analysis, the "what goes down" view, and the animation of a packet along its path. |
| **M6** | Export (PNG, SVG, Markdown, draw.io), documentation, installer, privacy audit and release checklist. |

Roadmap, after the first release: rack view in U units, power draw and yearly cost,
import of a Discovery Now export, import of a `docker-compose.yml`.
