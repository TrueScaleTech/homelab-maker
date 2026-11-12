"""The file PyInstaller turns into the application: it only starts the real entry point."""

from homelab_maker.app import main

raise SystemExit(main())
