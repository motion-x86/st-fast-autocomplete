#!/usr/bin/env python3
"""
build.py
Builds st-fast-autocomplete.sublime-package for distribution.

A .sublime-package is a ZIP archive containing all plugin files.
Sublime Text extracts it automatically on install.

Usage:
    python build.py                  # builds to dist/
    python build.py --version 1.2.0  # embeds version in output filename
    python build.py --out /tmp       # custom output directory
    python build.py --clean          # remove dist/ before building

Outputs:
    dist/st-fast-autocomplete.sublime-package
    dist/st-fast-autocomplete-<version>.sublime-package  (if --version given)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import zipfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PACKAGE_NAME = "st_fast_autocomplete"

# Files and directories included in the package (relative to repo root)
INCLUDE: list[str] = [
    "sublime-package.json",
    "python_version",
    "fast_autocomplete.py",
    "fast_autocomplete.sublime-settings",
    "Default.sublime-keymap",
    "Default.sublime-commands",
    "Main.sublime-menu",
    "package-metadata.json",
    "messages.json",
    "README.md",
    "messages/",
    "plugin/",
    "vendor/",
    "tests/",
]

# Glob patterns excluded even if their parent directory is included
EXCLUDE_PATTERNS: list[str] = [
    "**/__pycache__/",
    "**/*.pyc",
    "**/*.pyo",
    "**/.DS_Store",
    "**/Thumbs.db",
    "**/.git/",
    "**/.github/",
    "**/*.egg-info/",
    "**/dist/",
    "**/build.py",
    "**/.env",
]


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build(version: str | None, out_dir: Path, clean: bool) -> Path:
    repo_root = Path(__file__).parent.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    if clean and out_dir.exists():
        shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True)
        print(f"[build] Cleaned {out_dir}")

    # Output filename
    if version:
        pkg_filename = f"{PACKAGE_NAME}-{version}.sublime-package"
    else:
        pkg_filename = f"{PACKAGE_NAME}.sublime-package"

    pkg_path = out_dir / pkg_filename

    if pkg_path.exists():
        pkg_path.unlink()

    collected = _collect_files(repo_root)

    with zipfile.ZipFile(pkg_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, arc_name in sorted(collected):
            zf.write(abs_path, arc_name)
            print(f"  + {arc_name}")

    size_kb = pkg_path.stat().st_size / 1024
    print(f"\n[build] ✓ {pkg_path}  ({size_kb:.1f} KB, {len(collected)} files)")

    # Unversioned zip copy
    unversioned = out_dir / f"{PACKAGE_NAME}.sublime-package"
    shutil.copy2(pkg_path, unversioned)
    print(f"[build] ✓ {unversioned}  (zipped — for Package Control)")

    # Unpacked directory for direct Packages/ installation.
    # ST4 only adds unpacked Packages/ dirs to sys.path — zipped
    # .sublime-package files use a custom import hook that does NOT
    # expose the package to normal Python imports. Installing unpacked
    # is required for reliable plugin loading outside of Package Control.
    unpacked_dir = out_dir / "unpacked" / PACKAGE_NAME
    if unpacked_dir.exists():
        shutil.rmtree(unpacked_dir)
    unpacked_dir.mkdir(parents=True)
    with zipfile.ZipFile(pkg_path) as zf:
        zf.extractall(unpacked_dir)
    print(f"[build] ✓ {unpacked_dir}/  (unpacked — use this for manual install)")

    return pkg_path


def _collect_files(root: Path) -> list[tuple[Path, str]]:
    """
    Walk INCLUDE entries, skip anything matching EXCLUDE_PATTERNS,
    and return (absolute_path, archive_name) pairs.
    """
    results: list[tuple[Path, str]] = []

    for entry in INCLUDE:
        target = root / entry

        if entry.endswith("/"):
            # Directory — walk recursively
            if not target.is_dir():
                print(f"[build] WARNING: included directory not found: {target}")
                continue
            for abs_path in target.rglob("*"):
                if abs_path.is_file() and not _is_excluded(abs_path, root):
                    arc_name = abs_path.relative_to(root).as_posix()
                    results.append((abs_path, arc_name))
        else:
            # Single file
            if not target.is_file():
                print(f"[build] WARNING: included file not found: {target}")
                continue
            if not _is_excluded(target, root):
                arc_name = target.relative_to(root).as_posix()
                results.append((target, arc_name))

    return results


def _is_excluded(path: Path, root: Path) -> bool:
    """Return True if path matches any exclusion pattern."""
    rel = path.relative_to(root)
    rel_str = rel.as_posix()

    for pattern in EXCLUDE_PATTERNS:
        # Strip leading **/ for simple suffix matching
        bare = pattern.lstrip("*").lstrip("/").rstrip("/")
        if bare and (rel_str.endswith(bare) or f"/{bare}/" in f"/{rel_str}/"):
            return True
        # Direct fnmatch on the full relative path
        if rel.match(pattern):
            return True

    return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Build {PACKAGE_NAME}.sublime-package"
    )
    parser.add_argument(
        "--version", "-v",
        metavar="VERSION",
        help="Version string to embed in the output filename (e.g. 1.0.0)",
    )
    parser.add_argument(
        "--out", "-o",
        metavar="DIR",
        type=Path,
        default=Path("dist"),
        help="Output directory (default: ./dist)",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove output directory before building",
    )
    args = parser.parse_args()

    try:
        build(version=args.version, out_dir=args.out, clean=args.clean)
    except Exception as exc:
        print(f"[build] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
