import os
import sys


def resource_path(*parts):
    """Absolute path to a read-only resource bundled with the app.

    Handles both running from source (resources live at the project root) and
    PyInstaller one-file builds, where files added via ``--add-data`` are
    unpacked under ``sys._MEIPASS``. Centralizing this avoids the ``dirname()``
    miscounting bugs that previously broke the Telemt ``config.toml`` lookup.
    """
    base = getattr(sys, '_MEIPASS', None)
    if not base:
        # managers/paths.py -> managers -> project root
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
