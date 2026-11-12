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
  firewall, or a router with access lists). Source
  and destination are `any`, a network, or a node; the first matching rule wins.

### Two kinds of check

- **Structural checks** guard the model's own consistency: a cable to a node that does
  not exist, a container inside a switch, two cables on one port, a parent that is its
  own grandchild. A project that fails them is refused when loaded, because the
  analysis relies on them. They are implemented in `validation.py`.
- **Design checks** are warnings about the homelab itself: duplicate addresses, a VLAN
  that is not carried by a trunk, a single point of failure. They never block a project.
  They are in `checks.py`.

### Reachability

A flow from A to B is *reachable* when a path of links exists from A to B, the VLAN
membership of every interface on the path allows the traffic to cross it, every routing
hop is a node that routes, no rule on the path denies it, and the destination lists a
service on the port. The result carries the path, and for a blocked flow it names the first
thing that stops it.

How the pieces behave:

- A switch, an access point and a modem carry traffic between their ports without changing
  its VLAN. A router or firewall carries it between networks, and the VLAN may change
  there. Any other device is only the start or the end of a path.
- A port carries its untagged VLAN (the default VLAN, 1, when none is set), and, if it is a
  trunk, the tagged VLANs it lists. A link carries traffic only if both of its ports do.
  A tunnel link is not tied to a VLAN.
- A virtual machine or container is attached to its host without a cable. Its traffic
  leaves through the host's ports and traffic for it arrives through them. A guest with no
  VLAN set follows its host.
- A device that routes applies its rules in order to traffic passing through it, first
  match wins, and allows what no rule matches. Rules never apply to traffic that starts or
  ends on the device itself.
- If several paths exist, the shortest one that no rule denies is the answer. If all are
  denied, the shortest is shown, with the rule that stops it.
- If the destination lists no services, the port is not checked and the answer says so.

Deliberately not modelled: NAT and port forwarding, dynamic routing and routing tables
(a router is assumed to reach every network it touches), ARP, DHCP and DNS, return traffic
(a reply is assumed to be allowed), bandwidth and latency, wireless roaming, the state of a
real firewall, and a virtual machine that itself routes (it is not placed on a path between
other devices). The window lists these next to every result.

### What goes down

Switching a device off removes it and everything inside it from the drawing, runs the same
analysis, and reports the flows that worked and no longer do, and the devices that still run
but have lost their way to the Internet (or, without an Internet device, to the largest
group that is left). Nothing in the project changes.

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
| **M0** (done) | This page, repository scaffold, tooling, CI, git identity. |
| **M1** (done) | Catalogue, model, structural checks and project file, pure and tested. No window. An invented example project ships in `examples/`. |
| **M2** (done) | The canvas: grid, placing devices from the catalogue, moving, selecting, renaming, deleting, undo and redo, save and load, zoom and pan, light and dark themes. A Windows build script and a release workflow whose packaged program checks itself (`--smoke-test`) before anything is attached to a draft pre-release. |
| **M3** (done) | Nesting drawn on the canvas (open a host, drop a card into one), cables you can draw, a details panel with the ports of a device. |
| **M4** (done) | Addresses, VLANs and trunks in the details panel, and the automatic checks (duplicate addresses, VLAN and subnet mismatches, unreachable devices, single points of failure). |
| **M5** (done) | Flows, reachability analysis, services and rules, the "what goes down" view, and the packet along a path. |
| **M6** (done) | Export (PNG, SVG, Markdown, draw.io), Windows installer, Linux AppImage, `.deb` and archive, privacy audit, release checklist. |

After the first release: see [evolutions.md](evolutions.md) for ideas, among them a rack view
in U units, power draw and yearly cost, and imports of a Discovery Now export and of a
`docker-compose.yml`.
