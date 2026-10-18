"""Entry point used when packaging the app (PyInstaller needs a plain script)."""
from pdfshrink.app import main

if __name__ == "__main__":
    raise SystemExit(main())
