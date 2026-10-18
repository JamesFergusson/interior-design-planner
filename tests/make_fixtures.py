#!/usr/bin/env python3
"""Build test fixtures: room.json files -> planner.py seed -> a store snapshot the mock runtime loads.

Each fixture goes through the same script Claude uses during setup, so the page tests also test the seed pipeline.
Output: tests/fixtures/<name>/store.json  ({"coll/id": body}) and tests/fixtures/<name>/photos/*.png
"""
import json, pathlib, struct, subprocess, sys, zlib, shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "plugins/interior-design-planner/skills/room-planner/scripts/planner.py"
FIX = ROOT / "tests/fixtures"


def png(path, w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def opt(el, name, price, **kw):
    d = {"element": el, "name": name, "supplier": kw.pop("supplier", "Example Shop"), "url": kw.pop("url", f"https://example.com/{el}/{abs(hash(name)) % 9999}"),
         "price": price, "spec": kw.pop("spec", "Example spec"), "note": kw.pop("note", "")}
    d.update(kw)
    return d


ROOMS = {
    "living-room": {
        "room": {"name": "Living room, 12 Mill Lane", "type": "living-room", "units": "metric", "currency": "GBP",
                 "length_mm": 4800, "width_mm": 3600, "height_mm": 2500, "budget": 6000,
                 "scheme": "warm white, olive green, walnut and aged brass; calm and bright",
                 "layout": "Door in the corner of the long wall; bay window opposite; chimney breast with alcoves on the end wall; TV in the left alcove.",
                 "swatches": [{"name": "Warm white", "hex": "#efe9dc"}, {"name": "Olive", "hex": "#6b7046"}, {"name": "Walnut", "hex": "#5a3e2b"}, {"name": "Brass", "hex": "#b08d57"}],
                 "plan_file": "photos/plan.png"},
        "drop": ["plants"],
        "override": {"rug": {"place": "Under the front legs of the sofa and both chairs, 2400 x 1700 mm"}},
        "extra": [{"id": "picture-light", "group": "Lighting", "name": "Picture light", "unit": "item", "qty": 1, "place": "Above the chimney breast art"}],
        "options": [
            opt("paint", "Little Greene Slaked Lime Mid, 2.5 L", 59, per="tin", covers=16, status="shortlisted", id="paint-slaked", image_file="photos/a.png"),
            opt("paint", "Farrow & Ball Pointing, 2.5 L", 62, per="tin", covers=15, id="paint-pointing"),
            opt("flooring", "Engineered oak, natural oiled", 54.99, per="m²", id="floor-oak", image_file="photos/b.png"),
            opt("flooring", "Herringbone LVT, smoked oak", 32.5, per="box", covers=1.8, id="floor-lvt"),
            opt("rug", "Wool flatweave rug 240 x 170", 420, id="rug-wool", image_file="photos/c.png"),
            opt("sofa", "Three-seat sofa in olive velvet", 1495, id="sofa-olive", status="shortlisted", image_file="photos/d.png"),
            opt("sofa", "Linen-look three-seat sofa", 899, id="sofa-linen"),
            opt("sofa", "Modular corner sofa", 2400, id="sofa-corner", status="rejected", note="Too deep for the room"),
            opt("armchair", "Walnut-frame lounge chair", 649, id="chair-walnut"),
            opt("coffee-table", "Round walnut coffee table, 90 cm", 349, id="table-round", image_file="photos/e.png"),
            opt("media-unit", "Low walnut media unit", 499, id="media-walnut"),
            opt("window", "Made-to-measure linen curtains", None, priceNote="Quote needed", id="curtains-linen"),
            opt("ceiling-light", "Brass pendant, 40 cm", 189, id="pendant-brass"),
            opt("floor-lamp", "Arc floor lamp, brass", 159, id="lamp-arc"),
            opt("picture-light", "Brass picture light", 75, id="pic-light"),
        ],
        "picks": {"paint": "paint-slaked", "flooring": "floor-oak", "rug": "rug-wool", "sofa": "sofa-olive", "coffee-table": "table-round", "ceiling-light": "pendant-brass", "window": "curtains-linen"},
    },
    "bedroom-imperial": {
        "room": {"name": "Primary bedroom", "type": "bedroom", "units": "imperial", "currency": "USD",
                 "length_mm": 4267, "width_mm": 3658, "height_mm": 2438, "budget": 4000, "scheme": "Soft blue and white with pale oak"},
        "options": [
            opt("paint", "Benjamin Moore Palladian Blue, 1 gal", 89.99, per="tin", covers=350, id="paint-blue"),
            opt("flooring", "Wool carpet, oat", 6.5, per="ft²", id="carpet-oat"),
            opt("bed", "Oak platform bed, queen", 1199, id="bed-oak"),
            opt("bedside", "Oak nightstand", 249, id="nightstand"),
        ],
        "picks": {"bed": "bed-oak", "bedside": "nightstand", "flooring": "carpet-oat"},
    },
    "bathroom": {
        "room": {"name": "Ensuite", "type": "bathroom", "units": "metric", "currency": "GBP",
                 "length_mm": 2600, "width_mm": 1300, "height_mm": 2450, "budget": 5000,
                 "scheme": "warm oak, dusty pink, deep green, brushed brass and terrazzo"},
        "drop": ["bath"],
        "override": {"tile-shower": {"qty": 7.7}, "tile-wall": {"qty": 2.4, "name": "Far wall tile (pink)"}, "paint": {"qty": 14}},
        "options": [
            opt("tile-shower", "Willaton Rustic Green Gloss 65 x 250", 34.95, per="m²", id="green-gloss"),
            opt("tile-wall", "Asheville Pink Fan", 44.94, per="box", covers=0.53, id="pink-fan"),
            opt("tile-wall", "PVC metro panel 2-pack", 62.46, per="item", id="pink-panel"),
            opt("floor", "Popsical Earth terrazzo 450 x 450", 32.95, per="m²", id="terrazzo"),
            opt("vanity", "Drench Origin 900 fluted oak", 590, id="origin"),
            opt("shower-set", "JTP Vos exposed bar kit", 306, id="vos-bar"),
        ],
        "picks": {"tile-shower": "green-gloss", "tile-wall": "pink-fan", "floor": "terrazzo", "vanity": "origin"},
    },
    "kitchen-eur": {
        "room": {"name": "Cuisine", "type": "kitchen", "units": "metric", "currency": "EUR", "length_mm": 4000, "width_mm": 3000, "height_mm": 2600},
        "override": {"worktop": {"qty": 4.2}, "splashback": {"qty": 3}},
        "options": [
            opt("worktop", "Oak worktop 40 mm", 120, per="m", id="oak-top"),
            opt("splashback", "Zellige tiles", 95, per="m²", id="zellige"),
            opt("handles", "Brass knob", 8.5, id="knob"),
        ],
        "picks": {"worktop": "oak-top", "splashback": "zellige", "handles": "knob"},
    },
}


def main():
    if FIX.exists():
        shutil.rmtree(FIX)
    FIX.mkdir(parents=True)
    colours = [(196, 160, 120), (120, 130, 90), (90, 70, 50), (176, 141, 87), (200, 200, 190)]
    for name, room in ROOMS.items():
        d = FIX / name
        (d / "photos").mkdir(parents=True)
        for i, f in enumerate(["a", "b", "c", "d", "e"]):
            png(d / "photos" / f"{f}.png", 160, 120, colours[i])
        png(d / "photos" / "plan.png", 240, 180, (230, 230, 225))
        (d / "room.json").write_text(json.dumps(room, indent=2, ensure_ascii=False))
        r = subprocess.run([sys.executable, str(SCRIPT), "check", str(d / "room.json")], capture_output=True, text=True)
        if r.returncode:
            print(r.stdout, r.stderr); raise SystemExit(f"fixture {name} failed check")
        photos = json.loads(subprocess.run([sys.executable, str(SCRIPT), "photos", str(d / "room.json")], capture_output=True, text=True, check=True).stdout)
        # Pretend upload: map each key to a /_blob/ id the test server will serve from the file.
        pmap, served = {}, {}
        for n, p in enumerate(photos):
            bid = f"{name.replace('-', '')}{n}"
            pmap[p["key"]] = "/_blob/" + bid
            served[bid] = str(pathlib.Path(p["file"]).relative_to(ROOT))
        (d / "uploaded.json").write_text(json.dumps(pmap))
        subprocess.run([sys.executable, str(SCRIPT), "seed", str(d / "room.json"), "--out", str(d / "seed"), "--photos", str(d / "uploaded.json")], capture_output=True, text=True, check=True)
        batches = json.loads((d / "seed" / "batches.json").read_text())
        store = {}
        for b in batches:
            for w in b:
                store[f"{w['collection']}/{w['doc_id']}"] = json.loads(pathlib.Path(w["file_path"]).read_text())
        (d / "store.json").write_text(json.dumps(store, indent=1, ensure_ascii=False))
        (d / "blobs.json").write_text(json.dumps(served))
    # Hand-made messy store: bypasses the script on purpose (old data, people editing, bad values).
    messy = {
        "room/brief": {"name": "<img src=x onerror=window.__xss=1> Messy room", "type": "not-a-type", "setupDone": True, "length_mm": "4m", "budget": -5,
                       "swatches": [{"hex": "red"}, {"hex": "#123456", "name": "<b>x</b>"}], "plan": "https://evil.example/x.png"},
        "elements/a": {"name": "A part with a very long name " * 6, "group": "Group <script>window.__xss=2</script>", "unit": "m²", "qty": None, "order": 0},
        "elements/b": {"order": 1},
        "elements/c": {"name": "Items", "unit": "item", "qty": "three", "order": 2},
        "options/o1": {"element": "a", "name": "Priced per m² but no quantity", "price": 30, "per": "m²", "url": "javascript:window.__xss=3", "image": "https://evil.example/i.png"},
        "options/o2": {"element": "a", "name": "x" * 400, "price": "12", "status": "weird"},
        "options/o3": {"element": "missing-part", "name": "Orphan", "price": 10},
        "options/o4": {"element": "c", "name": "Pack without covers", "price": 20, "per": "box"},
        "options/o5": {"element": "c", "name": None, "price": 0},
        "state/selection": {"map": {"a": "o1", "c": "o4", "b": "gone"}},
        "presets/p": {"name": "Old set", "order": 0, "map": {"a": "o2", "zzz": "o1"}},
        "inbox/i1": {"url": "https://example.com/x", "state": "strange", "note": "<i>hi</i>"},
    }
    (FIX / "messy").mkdir()
    (FIX / "messy" / "store.json").write_text(json.dumps(messy, indent=1))
    (FIX / "messy" / "blobs.json").write_text("{}")
    print("fixtures built:", ", ".join(sorted(p.name for p in FIX.iterdir())))


if __name__ == "__main__":
    main()
