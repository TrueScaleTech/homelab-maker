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

- **Node**: a thing on the grid. It has a kind from the catalogue (router, switch,
  access point, NAS, mini PC, virtual machine, container, and so on), a name, a
  position in whole grid cells, an optional parent (nesting), interfaces, the services
  it listens on, and, for a node that forwards traffic, an ordered list of rules. A
  node with a parent is placed relative to it, so moving a host moves what is inside.
  The catalogue decides what a kind may contain: a NAS may host virtual machines and
  containers, a switch may host nothing.
- **Interface**: a named port on a node, with addresses, a VLAN and a mode (access or
  trunk). A switch node has the number of ports its kind says it has.
- **Link**: a cable or a wireless link between two interfaces, with a medium and a
  speed.
- **Zone**: a named area on the grid (LAN, IoT, guests, DMZ) that groups nodes by
  purpose.
- **Flow**: a statement that one node talks to a service of another, over a protocol
  and a port.
- **Rule**: a simplified allow or deny entry on a node that forwards traffic (a
  firewall, a router with access lists, a virtual machine that runs a firewall). Source
  and destination are `any`, a network, or a node; the first matching rule wins.

### Two kinds of check

- **Structural checks** guard the model's own consistency: a cable to a node that does
  not exist, a container inside a switch, two cables on one port, a parent that is its
  own grandchild. A project that fails them is refused when loaded, because the
  analysis relies on them. They are implemented in `validation.py`.
- **Design checks** are warnings about the homelab itself: duplicate addresses, a VLAN
  that is not carried by a trunk, a single point of failure. They never block a project.
  They arrive in M4.

### Reachability, first version

A flow from A to B is *reachable* when a path of links exists from A to B, the VLAN
membership of every interface on the path allows the traffic to cross it, every
routing hop is a node that routes, and no rule on the path denies it. The result
carries the path, and for a blocked flow it names the first thing that stops it.

Deliberately not modelled in the first version: NAT, dynamic routing protocols, ARP
and DHCP behaviour, bandwidth and latency, wireless roaming, and the state of a real
firewall's connection table. The application lists these next to every result.

## Project file

A project is one JSON file, by convention named `<name>.homelab.json`: a format
version, the nodes, the links, the zones, the flows. Keys are sorted, collections are
ordered by id and the layout is fixed, so the same homelab always gives the same bytes
and the file diffs cleanly in git. A diagram can live next to the infrastructure it
describes.

The file is data only. Loading it never executes anything, and it is read strictly: an
unknown field, a value of the wrong type, a reference to something that does not exist,
a file over 5 MiB, or a file from a newer format version than the application knows is
refused with a message that names where the problem is. A save writes a temporary file
first and replaces the old one only when the new one is complete.

## Milestones

| Milestone | Content |
| --- | --- |
| **M0** | This page, repository scaffold, tooling, CI, git identity. |
| **M1** (done) | Catalogue, model, structural checks and project file, pure and tested. No window. An invented example project ships in `examples/`. |
| **M2** | The canvas: grid, placing devices from the catalogue, moving, selecting, undo and redo, save and load. First packaged build on a provisional tag, to find packaging problems while there is little code. |
| **M3** | Nesting (host, virtual machine, container, service), ports and links. |
| **M4** | Interfaces, addresses, VLANs, and the automatic checks (duplicate addresses, ports over capacity, trunk and VLAN mismatches). |
| **M5** | Flows, reachability analysis, the "what goes down" view, and the animation of a packet along its path. |
| **M6** | Export (PNG, SVG, Markdown, draw.io), documentation, installer, privacy audit and release checklist. |

Roadmap, after the first release: rack view in U units, power draw and yearly cost,
import of a Discovery Now export, import of a `docker-compose.yml`.
