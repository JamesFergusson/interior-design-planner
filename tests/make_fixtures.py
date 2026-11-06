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


# Three real rooms with floor plans (geometry from the owner's planners; no address).
SW = [{"name": "Grey", "hex": "#8e8a85"}, {"name": "White", "hex": "#f3f2ee"}, {"name": "Walnut", "hex": "#6b4a32"}, {"name": "Teal", "hex": "#1f6b68"}]
ROOMS["main-bathroom"] = {
    "room": {"name": "Main bathroom", "type": "bathroom", "units": "metric", "currency": "GBP", "length_mm": 4115, "width_mm": 2300, "height_mm": 2470, "budget": 9000,
             "scheme": "Grey floor, white walls, walnut vanity, with a glossy teal tile in the shower as the one accent.",
             "layout": "Main room with a separate WC compartment beyond a stud partition at the far end.", "swatches": SW, "plan_file": "photos/plan.png"},
    "override": {"tile-shower": {"qty": 5.5}, "tile-wall": {"qty": 3}, "paint": {"qty": 20}},
    "options": [
        opt("vanity", "Zotto American Walnut and Anthracite Vanity with Stone Basin 1200", 1199, id="vanity-zotto", status="shortlisted", size={"w": 1200, "d": 470, "h": 845}, image_file="photos/c.png"),
        opt("vanity", "Malta walnut vanity 1000", 749, id="vanity-malta", size={"w": 1000, "d": 460, "h": 850}),
        opt("vanity", "Regent walnut vanity 800", 599, id="vanity-regent"),
        opt("tray", "Harbour Anti Slip Square Tray 800 x 800", 189, id="tray-harbour", status="shortlisted", size={"w": 800, "d": 800, "h": 40}),
        opt("tray", "Harbour Anti Slip Rectangular Tray 1000 x 800", 219, id="tray-harbour-1000", size={"w": 1000, "d": 800, "h": 40}),
        opt("enclosure", "London Matt Black Pivot 800 x 800", 429, id="enc-london", status="shortlisted"),
        opt("towel-rail", "JTP Hix Matt Black Towel Radiator 1200 x 500", 289, id="rail-hix", status="shortlisted", size={"w": 500, "d": 100, "h": 1200}),
        opt("mirror", "JTP Hix Matt Black LED Mirror 600 x 800", 259, id="mirror-hix", status="shortlisted", size={"w": 600, "d": 40, "h": 800}),
        opt("wc", "Close-coupled WC, white", 249, id="wc-cc", status="shortlisted", size={"w": 360, "d": 650, "h": 800}),
        opt("bath", "Steel bath 1700 x 700", 329, id="bath-steel", status="shortlisted", size={"w": 1700, "d": 700, "h": 560}),
        opt("floor", "Berlin Warm Grey Matt 1200 x 600", 39.99, per="m²", id="floor-berlin", status="shortlisted"),
        opt("tile-shower", "Mediterrano Aqua", 69, per="m²", id="tile-aqua", status="shortlisted"),
    ],
    "plan": {
        "corners": [[0, 0], [2300, 0], [2300, 4115], [0, 4115]],
        "partitions": [{"from": [0, 1050], "to": [2300, 1050], "t": 100}],
        "openings": [
            {"type": "door", "wall": "P1", "at": 900, "width": 700, "hinge": "end", "side": "right"},
            {"type": "window", "wall": "D", "at": 3411, "width": 550, "sill": 1100, "head": 1700},
            {"type": "window", "wall": "D", "at": 698, "width": 613, "sill": 1000, "head": 2000},
            {"type": "door", "wall": "B", "at": 2567, "width": 700, "hinge": "end"},
        ],
        "items": [
            {"part": "wc", "against": "D", "from": 3485},
            {"part": "tray", "against": "P1", "side": "+", "from": 0},
            {"part": "enclosure", "name": "Shower door", "kind": "screen", "box": [0, 1890], "rot": 0, "w": 800, "d": 10, "h": 1850, "z": 40, "attach": "shower-tray"},
            {"name": "Shower side panel", "kind": "screen", "box": [790, 1100], "rot": 90, "w": 790, "d": 10, "h": 1850, "z": 40, "attach": "shower-tray"},
            {"part": "vanity", "against": "B", "from": 1100},
            {"part": "mirror", "against": "B", "from": 1400, "z": 1100},
            {"part": "towel-rail", "against": "D", "from": 1315, "z": 200},
            {"part": "bath", "against": "C", "from": 600},
            {"name": "Built-in cupboard", "kind": "cabinet", "against": "C", "from": 0, "w": 550, "d": 698, "h": 2470},
        ],
        "camera": {"x": 1500, "y": 3700, "dir": 0},
    },
}
ROOMS["ensuite"] = {
    "room": {"name": "Ensuite", "type": "bathroom", "units": "metric", "currency": "GBP", "length_mm": 1300, "width_mm": 2600, "height_mm": 2450, "budget": 6000,
             "scheme": "Warm oak, dusty pink, deep green, brushed brass and earthy terrazzo; bright and calm."},
    "drop": ["bath"],
    "override": {"tile-shower": {"qty": 7}, "tile-wall": {"qty": 3.5}, "paint": {"qty": 12}},
    "options": [
        opt("vanity", "Avela oak wall-hung vanity 700", 549, id="v-avela", status="shortlisted", size={"w": 700, "d": 460, "h": 500}),
        opt("vanity", "Groove fluted oak vanity 600", 489, id="v-groove", size={"w": 600, "d": 400, "h": 520}),
        opt("tray", "Merlyn Level slate-effect tray 1300 x 800", 329, id="tr-merlyn", status="shortlisted", size={"w": 1300, "d": 800, "h": 25}),
        opt("wc", "Back-to-wall WC with concealed cistern", 389, id="w-ilife", status="shortlisted", size={"w": 360, "d": 520, "h": 400}),
        opt("mirror", "Arezzo round LED mirror 600", 199, id="m-arezzo", status="shortlisted", size={"w": 600, "d": 35, "h": 600}),
        opt("towel-rail", "Brushed brass towel rail 500 x 800", 229, id="r-brass", status="shortlisted", size={"w": 500, "d": 110, "h": 800}),
    ],
    "plan": {
        "corners": [[0, 0], [2600, 0], [2600, 1300], [0, 1300]],
        "openings": [{"type": "door", "wall": "C", "at": 1070, "width": 686, "hinge": "start"}],
        "items": [
            {"part": "wc", "against": "A", "from": 235},
            {"part": "vanity", "against": "A", "from": 870, "z": 350},
            {"part": "mirror", "against": "A", "from": 920, "z": 1150},
            {"part": "tray", "against": "B", "from": 0},
            {"part": "enclosure", "name": "Glass screen", "kind": "screen", "box": [1790, 0], "rot": 90, "w": 760, "d": 10, "h": 2000, "z": 25, "attach": "shower-tray"},
            {"part": "towel-rail", "against": "C", "from": 1800, "z": 300},
        ],
        "camera": {"x": 1190, "y": 1150, "dir": 0},
    },
}
ROOMS["open-plan-kitchen"] = {
    "room": {"name": "Open-plan kitchen", "type": "kitchen", "units": "metric", "currency": "GBP", "length_mm": 4700, "width_mm": 3900, "height_mm": 2535, "budget": 20000,
             "scheme": "Cream gloss slab doors, copper-brown worktop, brushed brass, white handmade-look tiles, light oak herringbone floor."},
    "drop": ["hood"],
    "extra": [{"id": "stools", "group": "Sink & appliances", "name": "Bar stools", "unit": "item", "qty": 5, "place": "Island"},
              {"id": "open-shelf", "group": "Units & surfaces", "name": "Open shelf", "unit": "item", "qty": 1, "place": "Over the sink"}],
    "override": {"worktop": {"qty": 9}, "splashback": {"qty": 3}, "paint": {"qty": 40}},
    "options": [
        opt("units", "Autograph kitchen in cashmere gloss", 9500, id="units-autograph", status="shortlisted"),
        opt("fridge", "Bosch Series 4 KIN96VFD0G integrated fridge freezer", 899, id="fridge-bosch", status="shortlisted", size={"w": 558, "d": 548, "h": 1935}),
        opt("oven", "Neff N50 Slide and Hide single oven", 749, id="oven-neff", status="shortlisted", size={"w": 594, "d": 548, "h": 595}),
        opt("dishwasher", "Bosch Series 4 SMV4EAX23G integrated dishwasher", 549, id="dw-bosch", status="shortlisted", size={"w": 598, "d": 550, "h": 815}),
        opt("hob", "Bosch Series 4 PVS811B16E venting induction hob", 1199, id="hob-bosch", status="shortlisted", size={"w": 802, "d": 522, "h": 223}),
        opt("sink", "Blanco Subline 700 1.5 bowl undermount sink", 379, id="sink-blanco", status="shortlisted", size={"w": 730, "d": 460, "h": 190}),
        opt("open-shelf", "LACK wall shelf, oak effect, 190 x 26 cm", 45, id="shelf-lack", status="shortlisted", size={"w": 1900, "d": 260, "h": 50}),
        opt("stools", "SKOGSTA bar stool, acacia, 62 cm", 79, id="stool-skogsta", status="shortlisted"),
    ],
    "plan": {
        "corners": [[0, 0], [7320, 0], [7320, 7950], [2620, 7950], [2620, 4050], [0, 4050]],
        "openings": [
            {"type": "window", "wall": "A", "at": 1008, "width": 1800, "sill": 675, "head": 2100},
            {"type": "door", "wall": "A", "at": 4170, "width": 2475, "style": "folding", "side": "out"},
            {"type": "door", "wall": "C", "at": 3838, "width": 762, "hinge": "end"},
            {"type": "door", "wall": "D", "at": 300, "width": 800, "style": "pocket", "side": "out", "hinge": "end"},
        ],
        "items": [
            {"part": "fridge", "name": "Tall unit: fridge freezer", "kind": "fridge", "follow": False, "against": "B", "from": 4050, "w": 600, "d": 600, "h": 2200},
            {"part": "oven", "name": "Tall unit: oven", "kind": "tall", "follow": False, "against": "B", "from": 4650, "w": 600, "d": 600, "h": 2200},
            {"part": "units", "name": "Tall unit: larder", "kind": "tall", "follow": False, "against": "B", "from": 5250, "w": 600, "d": 600, "h": 2200},
            {"part": "units", "name": "Base units, side run", "kind": "units", "follow": False, "against": "B", "from": 5850, "w": 1500, "d": 600, "h": 900},
            {"part": "units", "name": "Wall units, side run", "kind": "wall-unit", "follow": False, "against": "B", "from": 5850, "w": 1500, "d": 330, "h": 720, "z": 1450},
            {"part": "units", "name": "Base units, far run", "kind": "units", "follow": False, "against": "C", "from": 0, "w": 3600, "d": 600, "h": 900},
            {"part": "sink", "against": "C", "from": 1755, "z": 700},
            {"part": "dishwasher", "against": "C", "from": 2487, "inset": True},
            {"part": "open-shelf", "against": "C", "from": 1250, "z": 1500},
            {"name": "Island", "kind": "island", "box": [4520, 3050], "rot": 0, "w": 1200, "d": 3000, "h": 900},
            {"part": "hob", "box": [4859, 5050], "rot": 90, "z": 900},
            {"part": "stools", "box": [4070, 3600], "rot": 90},
            {"part": "stools", "box": [4070, 4300], "rot": 90},
            {"part": "stools", "box": [4070, 5000], "rot": 90},
            {"part": "stools", "box": [4700, 2600], "rot": 0},
            {"part": "stools", "box": [5140, 2600], "rot": 0},
            {"name": "Dining table", "kind": "dining-table", "box": [4900, 700], "rot": 0, "w": 1800, "d": 900},
            {"name": "Sofa", "kind": "sofa", "against": "F", "from": 1000},
            {"name": "Armchair", "kind": "armchair", "box": [1500, 500], "rot": 180},
        ],
        "camera": {"x": 6620, "y": 300, "dir": 180, "fov": 84},
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
        "plan/geometry": {"corners": [{"id": "a", "x": 0, "y": 0}, {"id": "b", "x": "x"}, {"id": "c\"><script>window.__xss=5</script>", "x": 3000, "y": 0}, {"id": "d", "x": 3000, "y": 2000}, {"id": "e", "x": 0, "y": 2000}],
                          "openings": [{"id": "o1", "wall": "zz", "width": -3}, {"id": "o2", "wall": "a", "type": "door", "at": 5000, "width": 800}, {"id": "o3<b>", "wall": "d", "type": "<i>window</i>", "width": "wide"}],
                          "dividers": [{"id": "p", "x1": 0}], "camera": {"x": "no"}, "wallT": "thick", "grid": -1, "underlay": {"src": "https://evil.example/u.png", "mmPerPx": 2}},
        "items/i1": {"kind": "<script>window.__xss=6</script>", "x": "1", "w": -5},
        "items/i2": {"name": "<img src=x onerror=window.__xss=7>", "kind": "wc", "x": 100, "y": 0, "element": "missing", "rot": "sideways"},
        "items/i3": {"kind": "bath", "x": 1500, "y": 1000, "w": 1e9, "d": 0.0001, "shape": "star", "cut": "no"},
    }
    (FIX / "messy").mkdir()
    (FIX / "messy" / "store.json").write_text(json.dumps(messy, indent=1))
    (FIX / "messy" / "blobs.json").write_text("{}")
    print("fixtures built:", ", ".join(sorted(p.name for p in FIX.iterdir())))


if __name__ == "__main__":
    main()
