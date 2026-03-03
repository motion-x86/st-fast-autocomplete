"""
vendor/__init__.py
Ensures the vendor directory is on sys.path so that bundled packages
(keyring, jaraco.classes) are importable without a system-level install.
"""
import sys
import os

# Resolve path relative to this file — works both from .sublime-package
# zip extraction and from an unpacked development install.
_vendor_path = os.path.dirname(os.path.abspath(__file__))
if _vendor_path not in sys.path:
    sys.path.insert(0, _vendor_path)