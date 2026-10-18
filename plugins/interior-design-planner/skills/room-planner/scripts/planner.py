#!/usr/bin/env python3
"""Room Planner helper: check a room.json, list photos to upload, and build the database writes.

Standard library only. Run with python3.

  python3 planner.py new <type> [--units metric|imperial] > room.json   start a room.json from a room type
  python3 planner.py check room.json                                    find problems before publishing
  python3 planner.py photos room.json                                   list photo files to upload, in order
  python3 planner.py seed room.json --out DIR [--photos uploaded.json]  write one JSON file per document
                                                                        and print the batches to send

room.json format: see references/data-model.md.
"""
import json, math, os, re, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
TYPES_PATH = HERE.parent / "references" / "room-types.json"
VERSION = "0.1.0"

UNITS = {"item", "m²", "m", "L", "ft²", "ft"}
IMPERIAL_UNIT = {"m²": "ft²", "m": "ft"}
TO_IMPERIAL = {"m²": 10.7639, "m": 3.28084}
PACKS = {"pack", "box", "tin", "can", "roll", "tile", "set", "pair"}
STATUSES = {"idea", "shortlisted", "rejected"}
CURRENCIES = {"GBP", "EUR", "USD"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,59}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
URL_RE = re.compile(r"^https?://[^\s]+$")
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_PHOTO = 8 * 1024 * 1024
BATCH = 50


def load_types():
    return {k: v for k, v in json.loads(TYPES_PATH.read_text()).items() if not k.startswith("_")}


def round1(x):
    return math.floor(x * 10 + 0.5) / 10


def round2(x):
    return math.floor(x * 100 + 0.5 + 1e-9) / 100


def pos(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x > 0


def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def areas(room):
    L, W, H = (room.get(k) for k in ("length_mm", "width_mm", "height_mm"))
    if not (pos(L) and pos(W)):
        return None
    L, W = L / 1000, W / 1000
    floor, perimeter = L * W, 2 * (L + W)
    return {"floor": floor, "ceiling": floor, "perimeter": perimeter,
            "walls": perimeter * (H / 1000) * 0.85 if pos(H) else None}


def quantity_for(tpl, room):
    q = tpl.get("qtyFrom")
    if num(q):
        return q
    if not isinstance(q, str):
        return None
    a = areas(room)
    if not a or not num(a.get(q)):
        return None
    v = a[q] * (1 + (tpl.get("waste") or 0) / 100)
    if room.get("units") == "imperial" and tpl.get("unit") in TO_IMPERIAL:
        v *= TO_IMPERIAL[tpl["unit"]]
    return round1(v)


def unit_for(unit, room):
    if room.get("units") == "imperial" and unit in IMPERIAL_UNIT:
        return IMPERIAL_UNIT[unit]
    return unit or "item"


def cost(o, el):
    """Mirror of RP.cost in planner.html. Returns (cost, buy) or None."""
    price = o.get("price")
    if not num(price) or price < 0:
        return None
    unit = el.get("unit") or "item"
    qty = el.get("qty") if pos(el.get("qty")) else (1 if unit == "item" else None)
    if pos(o.get("covers")):
        if qty is None:
            return None
        buy = math.ceil(qty / o["covers"] - 1e-9)
        return round2(buy * price), buy
    per = o.get("per") or "item"
    if per == unit or (unit == "item" and per in ("item", "each")):
        if qty is None:
            return None
        return round2(price * qty), qty
    return round2(price), 1


def resolve_elements(data, types):
    room = data["room"]
    if isinstance(data.get("elements"), list):
        els = [dict(e) for e in data["elements"]]
    else:
        tpl = types.get(room.get("type")) or types["other"]
        els = []
        for e in tpl["elements"]:
            els.append({"id": e["id"], "group": e["group"], "name": e["name"], "place": e.get("place", ""),
                        "hint": e.get("hint", ""), "unit": unit_for(e.get("unit"), room), "qty": quantity_for(e, room)})
    drop = set(data.get("drop") or [])
    els = [e for e in els if e.get("id") not in drop]
    for oid, patch in (data.get("override") or {}).items():
        for e in els:
            if e.get("id") == oid and isinstance(patch, dict):
                e.update(patch)
    for e in data.get("extra") or []:
        els.append(dict(e))
    for i, e in enumerate(els):
        e["order"] = i
        e.setdefault("unit", "item")
        if e["unit"] == "item" and e.get("qty") is None:
            e["qty"] = 1
    return els


def check(data, base_dir, types):
    errors, warnings = [], []
    if not isinstance(data, dict) or not isinstance(data.get("room"), dict):
        return ["room.json must be an object with a \"room\" section."], []
    room = data["room"]
    if not str(room.get("name", "")).strip():
        errors.append("room.name is missing.")
    if room.get("type") not in types:
        errors.append(f"room.type must be one of: {', '.join(types)}.")
    if room.get("units", "metric") not in ("metric", "imperial"):
        errors.append("room.units must be \"metric\" or \"imperial\".")
    if room.get("currency", "GBP") not in CURRENCIES:
        errors.append(f"room.currency must be one of {', '.join(sorted(CURRENCIES))}.")
    for k in ("length_mm", "width_mm", "height_mm"):
        v = room.get(k)
        if v is not None and not pos(v):
            errors.append(f"room.{k} must be a positive number of millimetres (or null).")
        elif pos(v) and v < 300:
            errors.append(f"room.{k} = {v} looks wrong: sizes are millimetres (4.2 m = 4200).")
        elif pos(v) and v > 30000:
            warnings.append(f"room.{k} = {v} mm looks wrong (over 30 m). Is it in millimetres?")
    if room.get("budget") is not None and not pos(room.get("budget")):
        errors.append("room.budget must be a positive number or null.")
    for s in room.get("swatches") or []:
        if not (isinstance(s, dict) and HEX_RE.match(str(s.get("hex", "")))):
            errors.append(f"swatch {s!r} needs a hex colour like #6b7046.")
    if errors:
        return errors, warnings

    els = resolve_elements(data, types)
    ids = [e.get("id") for e in els]
    for e in els:
        eid = e.get("id")
        if not isinstance(eid, str) or not ID_RE.match(eid):
            errors.append(f"part id {eid!r} must be lowercase letters, digits and hyphens.")
        if not str(e.get("name", "")).strip():
            errors.append(f"part {eid!r} has no name.")
        if e.get("unit") not in UNITS:
            errors.append(f"part {eid!r} unit {e.get('unit')!r} must be one of {', '.join(sorted(UNITS))}.")
        if e.get("qty") is not None and not pos(e.get("qty")):
            errors.append(f"part {eid!r} qty must be a positive number or null.")
        if e.get("qty") is None:
            warnings.append(f"part {eid!r} ({e.get('name')}) has no quantity; its options can't be costed until one is set.")
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        errors.append(f"duplicate part ids: {', '.join(sorted(map(str, dupes)))}.")

    by_el = {e["id"]: e for e in els if isinstance(e.get("id"), str)}
    opts = data.get("options") or []
    if not isinstance(opts, list):
        return errors + ["options must be a list."], warnings
    oids = []
    for n, o in enumerate(opts):
        where = f"option {n + 1} ({o.get('name', '?')!s})" if isinstance(o, dict) else f"option {n + 1}"
        if not isinstance(o, dict):
            errors.append(f"{where} is not an object."); continue
        oid = o.get("id")
        if oid is not None and (not isinstance(oid, str) or not ID_RE.match(oid)):
            errors.append(f"{where}: id must be lowercase letters, digits and hyphens.")
        oids.append(oid)
        el = by_el.get(o.get("element"))
        if not el:
            errors.append(f"{where}: element {o.get('element')!r} is not a part of this room."); continue
        if not str(o.get("name", "")).strip():
            errors.append(f"{where}: name is missing.")
        url = o.get("url")
        if url and not URL_RE.match(str(url)):
            errors.append(f"{where}: url must start with http:// or https://.")
        if not url and not o.get("owned"):
            warnings.append(f"{where}: no product link.")
        price = o.get("price")
        if price is not None and not (num(price) and price >= 0):
            errors.append(f"{where}: price must be a number (no currency sign) or null.")
        if price is None and not o.get("priceNote") and not o.get("owned"):
            warnings.append(f"{where}: no price and no priceNote.")
        per = o.get("per", "item")
        if per not in UNITS | PACKS | {"each"}:
            errors.append(f"{where}: per {per!r} must be 'item', the part's unit, or one of {', '.join(sorted(PACKS))}.")
        if per in PACKS and el.get("unit") != "item" and not pos(o.get("covers")):
            errors.append(f"{where}: sold per {per}, so covers (how much of {el.get('unit')} one {per} covers) is needed.")
        if o.get("covers") is not None and not pos(o.get("covers")):
            errors.append(f"{where}: covers must be a positive number or null.")
        if per in UNITS and per not in ("item",) and per != el.get("unit"):
            errors.append(f"{where}: priced per {per} but the part is measured in {el.get('unit')}.")
        if o.get("status", "idea") not in STATUSES:
            errors.append(f"{where}: status must be idea, shortlisted or rejected.")
        img = o.get("image_file")
        if img:
            p = (base_dir / img) if not os.path.isabs(img) else pathlib.Path(img)
            if not p.is_file():
                errors.append(f"{where}: image_file {img} not found.")
            elif p.suffix.lower() not in IMG_EXT:
                errors.append(f"{where}: image_file {img} must be .jpg, .png, .webp or .gif.")
            elif p.stat().st_size > MAX_PHOTO:
                errors.append(f"{where}: image_file {img} is over 8 MB; shrink it.")
            elif not looks_like_image(p):
                errors.append(f"{where}: image_file {img} is not a real image (maybe an HTML error page was saved).")
        if num(price) and pos(el.get("qty")):
            c = cost(o, el)
            if c and c[0] > 50000:
                warnings.append(f"{where}: costs {c[0]:,.0f} for this room. Check the price, per and covers.")
    od = {i for i in oids if i and oids.count(i) > 1}
    if od:
        errors.append(f"duplicate option ids: {', '.join(sorted(od))}.")
    for e in els:
        n = sum(1 for o in opts if isinstance(o, dict) and o.get("element") == e.get("id"))
        if n == 0:
            warnings.append(f"part {e.get('id')!r} ({e.get('name')}) has no options yet.")
    picks = data.get("picks") or {}
    named = {o.get("id") for o in opts if isinstance(o, dict)}
    for k, v in picks.items():
        if k not in by_el:
            errors.append(f"picks: {k!r} is not a part.")
        elif v is not None and v not in named:
            errors.append(f"picks: {v!r} is not an option id (give the option an \"id\").")
        else:
            o = next((x for x in opts if isinstance(x, dict) and x.get("id") == v), None)
            if o and o.get("element") != k:
                errors.append(f"picks: option {v!r} belongs to {o.get('element')!r}, not {k!r}.")
    return errors, warnings


def looks_like_image(p):
    head = p.read_bytes()[:16]
    return (head.startswith(b"\xff\xd8\xff") or head.startswith(b"\x89PNG") or head[:4] == b"GIF8"
            or (head[:4] == b"RIFF" and head[8:12] == b"WEBP"))


def assign_option_ids(data):
    used = set()
    for n, o in enumerate(data.get("options") or []):
        if not o.get("id"):
            base = re.sub(r"[^a-z0-9]+", "-", f"{o.get('element', 'opt')}-{o.get('name', n)}".lower()).strip("-")[:48] or f"opt-{n}"
            oid, k = base, 2
            while oid in used:
                oid = f"{base}-{k}"; k += 1
            o["id"] = oid
        used.add(o["id"])


def starting_selection(data, types):
    """What the page starts with: the user's picks, then the first shortlisted option in each other part."""
    els = resolve_elements(data, types)
    opts = data.get("options") or []
    sel = {k: v for k, v in (data.get("picks") or {}).items()}
    for e in els:
        if sel.get(e["id"]):
            continue
        s = next((o for o in opts if o.get("element") == e["id"] and o.get("status") == "shortlisted"), None)
        if s:
            sel[e["id"]] = s["id"]
    return sel


def cheapest_selection(data, types):
    els = resolve_elements(data, types)
    sel = {}
    for e in els:
        best = None
        for o in data.get("options") or []:
            if o.get("element") != e["id"] or o.get("status") == "rejected":
                continue
            c = cost(o, e)
            if c and (best is None or c[0] < best[0]):
                best = (c[0], o["id"])
        if best:
            sel[e["id"]] = best[1]
    return sel


def selection_total(data, types, sel):
    els = {e["id"]: e for e in resolve_elements(data, types)}
    byid = {o.get("id"): o for o in data.get("options") or []}
    total, unpriced = 0.0, 0
    for k, v in sel.items():
        o, e = byid.get(v), els.get(k)
        c = cost(o, e) if o and e else None
        if c:
            total += c[0]
        elif o:
            unpriced += 1
    return round2(total), unpriced


def summary(data, types):
    els = resolve_elements(data, types)
    opts = data.get("options") or []
    cur = data["room"].get("currency", "GBP")
    sym = {"GBP": "£", "EUR": "€", "USD": "$"}.get(cur, "")
    start = starting_selection(data, types)
    lines = []
    for e in els:
        mine = [o for o in opts if o.get("element") == e["id"]]
        pick = next((o for o in mine if o.get("id") == start.get(e["id"])), None)
        c = cost(pick, e) if pick else None
        q = f"{e['qty']:g} {e['unit']}" if pos(e.get("qty")) else "qty ?"
        lines.append(f"  {e['name'][:34]:34} {q:>12}  {len(mine):>2} options  {('start: ' + pick['name'][:30]) if pick else ''}{(' ' + sym + format(c[0], ',.2f')) if c else (' (no price)' if pick else '')}")
    budget = data["room"].get("budget")
    t, un = selection_total(data, types, start)
    ch, chu = selection_total(data, types, cheapest_selection(data, types))
    lines.append(f"  Starting choices (picks + shortlisted): {sym}{t:,.2f}" + (f", {un} without a price" if un else "") + (f" — {'over' if t > budget else 'within'} the {sym}{budget:,.0f} budget" if pos(budget) else ""))
    lines.append(f"  Cheapest option in every part: {sym}{ch:,.2f}")
    lines.append(f"  Parts with nothing chosen at the start: {sum(1 for e in els if e['id'] not in start)} of {len(els)}")
    return "\n".join(lines)


def build_docs(data, types, photo_map):
    room = dict(data["room"])
    room.setdefault("units", "metric")
    room.setdefault("currency", "GBP")
    room.update({"setupDone": True, "version": VERSION})
    for k in ("plan_file", "photo_file", "vis_file"):
        key = k[:-5]
        if room.get(k) and photo_map.get("room:" + key):
            room[key] = photo_map["room:" + key]
        room.pop(k, None)
    docs = [("room", "brief", room)]
    for e in resolve_elements(data, types):
        eid = e.pop("id")
        docs.append(("elements", eid, {k: v for k, v in e.items() if v is not None or k == "qty"}))
    for n, o in enumerate(data.get("options") or []):
        o = dict(o)
        oid = o.pop("id")
        img = o.pop("image_file", None)
        doc = {"element": o["element"], "name": o["name"], "supplier": o.get("supplier", ""), "url": o.get("url", ""), "owned": bool(o.get("owned")),
               "price": o.get("price"), "per": o.get("per", "item"), "covers": o.get("covers"),
               "priceNote": o.get("priceNote", ""), "spec": o.get("spec", ""), "note": o.get("note", ""),
               "status": o.get("status", "idea"), "source": "setup", "order": n,
               "image": photo_map.get(oid, "") if img or oid in photo_map else ""}
        docs.append(("options", oid, doc))
    start = starting_selection(data, types)
    docs.append(("state", "selection", {"map": start}))
    if start:
        docs.append(("presets", "suggested", {"name": "Suggested", "order": 0, "map": start}))
    cheap = cheapest_selection(data, types)
    if cheap and cheap != start:
        docs.append(("presets", "cheapest", {"name": "Cheapest", "order": 1, "map": cheap}))
    return docs


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__); return 0
    types = load_types()
    cmd = argv[1]
    if cmd == "new":
        t = argv[2] if len(argv) > 2 else "living-room"
        if t not in types:
            print(f"Unknown room type {t!r}. Choose one of: {', '.join(types)}", file=sys.stderr); return 2
        units = argv[argv.index("--units") + 1] if "--units" in argv else "metric"
        print(json.dumps({"room": {"name": "", "type": t, "units": units, "currency": "GBP" if units == "metric" else "USD",
                                   "length_mm": None, "width_mm": None, "height_mm": None, "budget": None,
                                   "sizesEstimated": False, "scheme": "", "layout": "", "keeping": "", "swatches": [],
                                   "plan_file": None, "photo_file": None},
                          "drop": [], "override": {}, "extra": [], "options": [], "picks": {}}, indent=2, ensure_ascii=False))
        return 0
    if len(argv) < 3:
        print("Give the path to room.json.", file=sys.stderr); return 2
    path = pathlib.Path(argv[2])
    try:
        data = json.loads(path.read_text())
    except Exception as e:  # noqa: BLE001
        print(f"Can't read {path}: {e}", file=sys.stderr); return 2
    if isinstance(data, dict):
        assign_option_ids(data)
    errors, warnings = check(data, path.parent, types)
    if cmd == "check":
        for w in warnings:
            print("warning:", w)
        for e in errors:
            print("ERROR:", e)
        if not errors:
            print(summary(data, types))
            print(f"OK: {len(errors)} errors, {len(warnings)} warnings.")
        return 1 if errors else 0
    if errors:
        for e in errors:
            print("ERROR:", e)
        print("Fix the errors first (run: planner.py check room.json).", file=sys.stderr)
        return 1
    if cmd == "photos":
        files = []
        for k in ("plan_file", "photo_file", "vis_file"):
            if data["room"].get(k):
                files.append(("room:" + k[:-5], data["room"][k]))
        files += [(o["id"], o["image_file"]) for o in data.get("options") or [] if o.get("image_file")]
        print(json.dumps([{"key": k, "file": str((path.parent / f).resolve()) if not os.path.isabs(f) else f} for k, f in files], indent=2))
        return 0
    if cmd == "seed":
        out = pathlib.Path(argv[argv.index("--out") + 1]) if "--out" in argv else path.parent / "seed"
        photo_map = {}
        if "--photos" in argv:
            photo_map = json.loads(pathlib.Path(argv[argv.index("--photos") + 1]).read_text())
            bad = [k for k, v in photo_map.items() if not re.match(r"^/_blob/[A-Za-z0-9_-]+$", str(v))]
            if bad:
                print("ERROR: photo map values must look like /_blob/<id>: " + ", ".join(bad), file=sys.stderr); return 1
        out.mkdir(parents=True, exist_ok=True)
        docs = build_docs(data, types, photo_map)
        writes = []
        for coll, did, body in docs:
            f = (out / f"{coll}__{did}.json").resolve()
            f.write_text(json.dumps(body, ensure_ascii=False))
            writes.append({"op": "set", "collection": coll, "doc_id": did, "file_path": str(f)})
        # room/brief last, so the page leaves its setup screen only once everything else is in place
        writes.sort(key=lambda w: w["collection"] == "room")
        batches = [writes[i:i + BATCH] for i in range(0, len(writes), BATCH)]
        (out / "batches.json").write_text(json.dumps(batches, indent=1))
        missing = [o["id"] for o in data.get("options") or [] if o.get("image_file") and o["id"] not in photo_map]
        print(f"{len(writes)} documents in {len(batches)} batch(es). Send each batch with ArtifactData action \"batch\" (writes = the list below), in order.")
        if missing:
            print(f"note: {len(missing)} option photo(s) have no uploaded URL and will show 'No photo yet': {', '.join(missing)}")
        for n, b in enumerate(batches, 1):
            print(f"--- batch {n} of {len(batches)} ---")
            print(json.dumps(b))
        return 0
    print(f"Unknown command {cmd!r}.\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
