#!/usr/bin/env python3
"""Inject references/room-types.json into assets/planner.html (single source of truth).

Usage: python3 tools/build.py          # rewrite planner.html in place
       python3 tools/build.py --check  # exit 1 if planner.html is out of date
"""
import json, re, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/interior-design-planner/skills/room-planner"
HTML = SKILL / "assets/planner.html"
TYPES = SKILL / "references/room-types.json"
PLUGIN = ROOT / "plugins/interior-design-planner/.claude-plugin/plugin.json"

def build():
    types = {k: v for k, v in json.loads(TYPES.read_text()).items() if not k.startswith("_")}
    block = "/* ROOM_TYPES_START */\nconst ROOM_TYPES = " + json.dumps(types, ensure_ascii=False, separators=(",", ":")) + ";\n/* ROOM_TYPES_END */"
    html = HTML.read_text()
    new = re.sub(r"/\* ROOM_TYPES_START \*/.*?/\* ROOM_TYPES_END \*/", lambda m: block, html, flags=re.S)
    version = json.loads(PLUGIN.read_text())["version"] if PLUGIN.exists() else None
    if version:
        new = re.sub(r'(<meta name="room-planner-version" content=")[^"]*(">)', rf"\g<1>{version}\g<2>", new)
        new = re.sub(r'(const VERSION = ")[^"]*(";)', rf"\g<1>{version}\g<2>", new)
    return html, new

if __name__ == "__main__":
    old, new = build()
    if "--check" in sys.argv:
        if old != new:
            print("planner.html is out of date: run python3 tools/build.py")
            sys.exit(1)
        print("planner.html is up to date")
    else:
        HTML.write_text(new)
        print("planner.html rebuilt" if old != new else "planner.html already up to date")
