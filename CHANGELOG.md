# Changelog

Versions follow [Semantic Versioning](https://semver.org). While the version starts with
0, the project file format and the way things work may still change between releases; the
file format has its own version number, and a newer file is refused rather than guessed at.

## 0.1.0 - 2026-11-12

The first public release. It is marked as a pre-release: it is complete enough to draw a
homelab and ask questions about it, and it has had no users yet.

### What you can do

- Draw a homelab on a grid with fifteen kinds of device, move them, rename them, delete
  them, undo and redo up to 200 steps, and save the result as one plain JSON file that
  diffs cleanly in git.
- Nest virtual machines and containers inside their hosts and open a host to see inside it.
- Join devices with cables (ethernet, fibre) or wireless and tunnel links. A cable fills a
  port: the ninth cable on an eight-port switch is refused.
- Give ports addresses, a VLAN, an access or trunk mode and tagged VLANs; list the
  services a device listens on; write the rules of a firewall or router.
- Read warnings about the design: duplicate addresses, VLAN and subnet mismatches, a
  device nobody can reach, a single point of failure.
- Describe flows (this talks to that port) and see whether each gets through, along which
  path, and, if it does not, the first thing that stops it. Send a packet along the path.
- Switch a device off on the drawing and see what stops working.
- Export an image (PNG, SVG), a Markdown page, or a draw.io diagram.

### Downloads

A Windows installer and zip, a Linux AppImage, `.deb` package and `tar.gz`. None of them is
signed yet; see the README for what that means on first start.

### Not in this release

Rack view, power draw and cost, import of a Discovery Now export and of a
`docker-compose.yml`. They are listed, with other ideas, in
[docs/evolutions.md](docs/evolutions.md).
