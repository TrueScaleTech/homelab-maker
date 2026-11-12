#!/usr/bin/env bash
# Builds HomeLabMaker for Linux (x86_64): the application as a folder, a tar.gz, a .deb
# package and an AppImage.
#
#   packaging/build-linux.sh [OUTPUT_DIR]        (default: dist)
#
# Run it from a clean virtual environment on the oldest Linux you want to support: the
# result needs at least the C library of the machine it was built on. The release workflow
# builds on Ubuntu 22.04 for that reason.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo"
out="$(mkdir -p "${1:-dist}" && cd "${1:-dist}" && pwd)"

python -m pip install --quiet -e ".[build]"
version="$(python -c 'import homelab_maker; print(homelab_maker.__version__)')"
echo "Building HomeLabMaker $version"

# The icon is drawn in code; write it out as a PNG for the launcher and the packages.
QT_QPA_PLATFORM=offscreen python -m homelab_maker.gui.icons "$out/homelab-maker.png"

rm -rf "$out/work" "$out/homelabmaker"
python -m PyInstaller packaging/launcher.py \
    --noconfirm --clean --windowed --onedir \
    --name homelabmaker \
    --paths src \
    --distpath "$out" \
    --workpath "$out/work" \
    --specpath "$out/work"

app="$out/homelabmaker"
test -x "$app/homelabmaker"

desktop_entry() {
    # $1 is what to run, $2 is the icon name or path
    cat <<EOF
[Desktop Entry]
Type=Application
Name=HomeLabMaker
GenericName=Homelab planner
Comment=Draw your homelab on a grid and ask what can reach what
Exec=$1 %f
Icon=$2
Terminal=false
Categories=Network;Utility;
MimeType=application/json;
StartupWMClass=homelabmaker
EOF
}

# --- tar.gz: unpack anywhere and run ./HomeLabMaker/homelabmaker
tar_name="HomeLabMaker-$version-linux-x86_64"
rm -rf "$out/stage" && mkdir -p "$out/stage"
cp -a "$app" "$out/stage/HomeLabMaker"
cp LICENSE README.md "$out/stage/HomeLabMaker/"
tar -C "$out/stage" -czf "$out/$tar_name.tar.gz" HomeLabMaker
echo "Archive   $out/$tar_name.tar.gz"

# --- .deb: installs under /opt, with a command, a menu entry and an icon
deb_root="$out/deb"
rm -rf "$deb_root"
mkdir -p "$deb_root/DEBIAN" "$deb_root/opt" "$deb_root/usr/bin" \
    "$deb_root/usr/share/applications" "$deb_root/usr/share/icons/hicolor/256x256/apps" \
    "$deb_root/usr/share/doc/homelab-maker"
cp -a "$app" "$deb_root/opt/homelab-maker"
ln -s /opt/homelab-maker/homelabmaker "$deb_root/usr/bin/homelabmaker"
cp "$out/homelab-maker.png" "$deb_root/usr/share/icons/hicolor/256x256/apps/homelab-maker.png"
desktop_entry /usr/bin/homelabmaker homelab-maker >"$deb_root/usr/share/applications/homelab-maker.desktop"
cp LICENSE "$deb_root/usr/share/doc/homelab-maker/copyright"
size_kb="$(du -sk "$deb_root" | cut -f1)"
cat >"$deb_root/DEBIAN/control" <<EOF
Package: homelab-maker
Version: $version
Section: net
Priority: optional
Architecture: amd64
Installed-Size: $size_kb
Maintainer: TrueScaleTech <95164073+TrueScaleTech@users.noreply.github.com>
Homepage: https://github.com/TrueScaleTech/homelab-maker
Depends: libc6 (>= 2.35), libegl1, libgl1, libxkbcommon0, libxkbcommon-x11-0, libfontconfig1, libdbus-1-3, libglib2.0-0, libxcb-cursor0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1, libxcb-render-util0, libxcb-shape0, libxcb-xinerama0
Description: Draw your homelab on a grid and ask what can reach what
 HomeLabMaker is a desktop application for planning and documenting a homelab. Place
 devices on a grid, nest virtual machines and containers in their hosts, join ports with
 cables and describe which service talks to which. It tells you whether a flow can get
 from A to B, along which path, and what stops it. It makes no network connection.
EOF
deb_name="homelab-maker_${version}_amd64.deb"
dpkg-deb --root-owner-group --build "$deb_root" "$out/$deb_name" >/dev/null
echo "Package   $out/$deb_name"

# --- AppImage: one file that runs on most distributions without installing anything
appdir="$out/HomeLabMaker.AppDir"
rm -rf "$appdir" && mkdir -p "$appdir"
cp -a "$app" "$appdir/homelabmaker"
cp "$out/homelab-maker.png" "$appdir/homelab-maker.png"
desktop_entry homelabmaker homelab-maker >"$appdir/homelab-maker.desktop"
cat >"$appdir/AppRun" <<'EOF'
#!/bin/sh
here="$(dirname "$(readlink -f "$0")")"
exec "$here/homelabmaker/homelabmaker" "$@"
EOF
chmod +x "$appdir/AppRun"
tool="${APPIMAGETOOL:-}"
if [ -z "$tool" ]; then
    # A fixed release, checked against the digest GitHub shows for it: the tool runs on
    # the build machine, so it is not taken from the moving "continuous" build.
    tool="$out/appimagetool"
    url="https://github.com/AppImage/appimagetool/releases/download/1.9.1/appimagetool-x86_64.AppImage"
    sha="ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0"
    if [ ! -x "$tool" ]; then
        curl -fsSL -o "$tool" "$url"
        echo "$sha  $tool" | sha256sum -c - >/dev/null
        chmod +x "$tool"
    fi
fi
appimage="$out/HomeLabMaker-$version-x86_64.AppImage"
# Run the tool without needing FUSE, which build machines often lack.
ARCH=x86_64 "$tool" --appimage-extract-and-run "$appdir" "$appimage" >/dev/null
echo "AppImage  $appimage"
