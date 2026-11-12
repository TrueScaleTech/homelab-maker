# Ideas and possible evolutions

Nothing here is promised. It is a list to choose from, grouped by what it would add, with a
rough size (S: days, M: a couple of weeks, L: a month or more). The first section is what
the first release left out on purpose or found missing while it was being written.

## Known gaps in 0.1.0

- **A virtual machine that routes** (a pfSense or OPNsense VM, say) is not placed on a path
  between other devices: paths only pass through a guest to reach it. Fixing it means
  letting a path go through a guest when its host sits between two of its networks. (M)
- **Zones are rectangles you cannot resize** from the window: they are made around the
  selection and removed by name. Dragging their edges, renaming, and colours would finish
  the job. (S)
- **A rule has no default policy.** What no rule mentions is allowed. A per-device "default
  deny" setting is what a firewall owner expects. (S)
- **No copy and paste**, no align or distribute, no search box, no minimap. (M)
- **Several cables on one port** (a pair of cables between two switches) is refused as
  "port busy". Link aggregation as a first-class thing would allow it. (M)
- **Hosts are opened, not expanded**: you look inside one at a time. Drawing the guests
  inside the host's card is friendlier for small labs. (M)
- **The files are not code-signed**, so Windows SmartScreen warns. Certificates cost money
  and need an identity. (S once there is a certificate)

## More of the model

- **IP address plan.** Subnets as objects: name, VLAN, gateway, DHCP range, a "next free
  address" button, overlap detection, addresses allocated from a plan instead of typed. (M)
- **NAT and port forwarding**, so "reachable from the Internet" can be answered, with the
  rule that exposes it. (M)
- **Routing**: static routes, a second ISP and failover, a VPN that joins two sites. (L)
- **Link speed and PoE**: a 1 Gbit uplink for 2.5 Gbit devices, a switch's PoE budget against
  what is plugged into it. (M)
- **Service dependencies**: this app needs that database, which needs that disk. "What goes
  down" would follow them, not only the cables. (M)
- **Storage and backups**: disks, pools, what is backed up where, a 3-2-1 view and "when did
  I last test a restore". (L)
- **Power and cost** (from the original idea): watts per device, a price per kWh, a yearly
  cost, a UPS and how long it lasts, what goes down when it runs out. (M)
- **Rack view in U units**: devices with a height, a cabinet, patch panels, cable labels. (L)
- **Several pages**: a floor or a room per page, a site-to-site link between pages. (M)
- **Notes, tags and colours** on devices; custom kinds and icons; real device models
  (a particular NAS, a particular switch with its exact ports). (M)

## More analysis

- **Intent that is checked.** A list of flows that *must* work and flows that *must not*,
  saved in the project, with a command-line `homelabmaker check file.homelab.json` that
  fails in CI or a git hook when a change breaks one. (M, and the most useful of the list)
- **Compare two versions of a project**: what a commit changed in the design (a device added,
  a rule moved, a flow that is now blocked). (M)
- **Rule hygiene**: a rule that can never match because an earlier one covers it, a rule no
  flow uses, `any any allow`. (S)
- **A zone matrix**: which zone can reach which, at a glance, and a template such as "IoT must
  not reach the LAN". (M)
- **Suggestions**: when a flow is blocked, offer the rule that would let it through, and say
  what else that rule would allow. (M)
- **Several failures at once**, and a redundancy score. (S)
- **What can be seen from the Internet**: services exposed through NAT, with the path. (M)

## Import and export

- **Import** a `docker-compose.yml` (containers, ports, networks), a Discovery Now export
  (devices and addresses found on a real network, which this application will never scan
  itself), a NetBox export, an inventory CSV. All of them read files; none connects to
  anything. (M each)
- **Export** to Mermaid, PlantUML, an Ansible inventory, NetBox, a printable inventory with
  cable labels and QR codes, PDF. (S to M each)
- **A command line** for exports and checks, so a pipeline can regenerate the documentation
  from the project file. (S)

## Using it

- **Help inside the application** and a gallery of example homelabs: a Proxmox cluster, a
  small office, a house plus a VPS. (S per example)
- **Languages**: the texts are all in one place per module, so a translation is feasible. (M)
- **Accessibility**: a high-contrast theme, full keyboard operation of the canvas, a screen
  reader pass over the panels. (M)
- **Large projects**: only draw what is in view, and a quick find. (M)
- **macOS** build and a signed installer. (M, needs a Mac to test)

## Distribution

- Packages for **winget**, **Scoop**, **Chocolatey**, **Flathub** or **Snap**. (S each,
  after signing)
- **Reproducible builds** and an SBOM attached to each release. (S)
- An **update notice**, only if it can be made opt-in and without any hidden request, which
  is in tension with "makes no network connection"; probably better left to package
  managers. (a decision, not a task)

## Quality

- **Property-based tests** (Hypothesis) of the model and the loader, and a **fuzzing** run on
  the project file reader. (S)
- **Mutation testing** of the analysis in CI: the ten manual mutations tried for 0.1.0 were
  all caught, and a tool would keep it that way. (S)
- **Screenshot regression tests** of the canvas on a fixed font. (M)
- **Performance tests** with a thousand devices. (S)
