#!/usr/bin/env python3
"""Check that an installer left a working copy of easel in both skill folders.

CI runs this after install.sh and after install.ps1. It checks the home folder of the
user who runs it: each file is present and matches this clone, and the helper starts and
reports the version in VERSION.

    python easel/tools/check_install.py
"""
import subprocess
import sys
from pathlib import Path

FILES = ["SKILL.md", "VERSION", "scripts/easel.py", "scripts/scrape.js", "scripts/viewer.js"]
CLONE = Path(__file__).resolve().parent.parent / "skills" / "easel"


def main():
    for kit in (Path.home() / ".claude" / "skills" / "easel", Path.home() / ".agents" / "skills" / "easel"):
        missing = [f for f in FILES if not (kit / f).is_file()]
        if missing:
            sys.exit(f"{kit}: missing {', '.join(missing)}")
        differ = [f for f in FILES if (kit / f).read_bytes() != (CLONE / f).read_bytes()]
        if differ:
            sys.exit(f"{kit}: differs from this clone in {', '.join(differ)}")
        want = (kit / "VERSION").read_text(encoding="utf-8").split()[0]
        got = subprocess.run([sys.executable, str(kit / "scripts" / "easel.py"), "version"],
                             capture_output=True, text=True, check=True).stdout.strip()
        if got != want:
            sys.exit(f"{kit}: the helper reports {got}, but VERSION says {want}")
        print(f"ok: {kit} holds easel {got}")


if __name__ == "__main__":
    main()
