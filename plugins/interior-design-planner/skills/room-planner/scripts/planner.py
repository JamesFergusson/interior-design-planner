#!/usr/bin/env python3
"""Room Planner helper: check a room.json, list photos to upload, and build the database writes.

Standard library only. Run with python3.

  python3 planner.py new <type> [--units metric|imperial] > room.json   start a room.json from a room type
  python3 planner.py check room.json                                    find problems before publishing
  python3 planner.py photos room.json                                   list photo files to upload, in order
  python3 planner.py seed room.json --out DIR [--photos uploaded.json]  write one JSON file per document
                                                                        and print the batches to send

room.json format: see references/data-model.md (the floor plan section: references/floor-plan.md).
"""
import json, math, os, re, sys, pathlib

HERE = pathlib.Path(__file__).resolve().parent
TYPES_PATH = HERE.parent / "references" / "room-types.json"
VERSION = "0.2.0"

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
    errors += check_sizes(data)
    if not errors and data.get("plan") is not None:
        _, _, pe, pw, _ = build_plan(data, types, starting_selection(data, types))
        errors += pe
        warnings += pw
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
    if data.get("plan") is not None:
        lines += build_plan(data, types, start)[4]
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
        if isinstance(o.get("size"), dict):
            doc["size"] = {k: o["size"][k] for k in ("w", "d", "h") if pos(o["size"].get(k))}
            doc["size"]["from"] = o["size"].get("from", "page")
        if o.get("shape"):
            doc["shape"] = o["shape"]
        docs.append(("options", oid, doc))
    start = starting_selection(data, types)
    if data.get("plan") is not None:
        geometry, items, _, _, _ = build_plan(data, types, start)
        if geometry:
            if photo_map.get("room:plan"):
                u = geometry.get("underlay") or {"x": 0, "y": 0, "mmPerPx": None, "opacity": 0.45}
                # the drawing is for tracing and checking; once items are placed it would show their old positions
                geometry["underlay"] = {**u, "src": photo_map["room:plan"], "show": not items}
            elif geometry.get("underlay"):
                geometry.pop("underlay")
            docs.append(("plan", "geometry", geometry))
            for iid, body in items:
                docs.append(("items", iid, body))
            # the layout as set up is what "Reset to brief plan" comes back to until the person saves another
            docs.append(("plan", "saved", {"geometry": geometry, "items": [{"id": iid, **body} for iid, body in items], "savedAt": 0}))
    docs.append(("state", "selection", {"map": start}))
    if start:
        docs.append(("presets", "suggested", {"name": "Suggested", "order": 0, "map": start}))
    cheap = cheapest_selection(data, types)
    if cheap and cheap != start:
        docs.append(("presets", "cheapest", {"name": "Cheapest", "order": 1, "map": cheap}))
    return docs


# ---------------------------------------------------------------- floor plan
# room.json "plan" section -> plan/geometry document + items/<id> documents. Same geometry rules as the page.
KINDS_PATH = HERE.parent / "references" / "plan-kinds.json"
SHAPES = {"rect", "rounded", "round", "quadrant", "L"}
OPENING_TYPES = {"door", "window", "opening"}
DOOR_STYLES = {"hinged", "double", "sliding", "pocket", "folding"}


def load_kinds():
    k = json.loads(KINDS_PATH.read_text())
    return k["kinds"], k["parts"]


def letter(i):
    return chr(65 + i) if i < 26 else chr(65 + i % 26) + str(i // 26 + 1)


def poly_area(pts):
    return sum(p[0] * q[1] - q[0] * p[1] for p, q in zip(pts, pts[1:] + pts[:1])) / 2


def outline_walls(corners):
    cw = poly_area(corners) >= 0
    out = []
    for i, a in enumerate(corners):
        b = corners[(i + 1) % len(corners)]
        L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = (-uy, ux) if cw else (uy, -ux)
        out.append({"id": f"c{i + 1}", "name": "wall " + letter(i), "letter": letter(i), "a": a, "b": b, "len": L, "u": (ux, uy), "n": (nx, ny), "kind": "wall"})
    return out


def divider_wall(d, i):
    a, b = (d["x1"], d["y1"]), (d["x2"], d["y2"])
    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1e-9
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    return {"id": d["id"], "name": f"partition {i + 1}", "letter": f"P{i + 1}", "a": a, "b": b, "len": L, "u": (ux, uy), "n": (-uy, ux), "t": d.get("t") or 100, "kind": "divider"}


def divider_rect(w):
    h = w["t"] / 2
    (ax, ay), (bx, by), (nx, ny) = w["a"], w["b"], w["n"]
    return [(ax + nx * h, ay + ny * h), (bx + nx * h, by + ny * h), (bx - nx * h, by - ny * h), (ax - nx * h, ay - ny * h)]


def rot_pt(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def local_parts(it):
    w, d, hw, s = it["w"], it["d"], it["w"] / 2, it.get("shape") or "rect"
    if s == "round":
        return [[(math.cos(i / 32 * 2 * math.pi) * hw, d / 2 + math.sin(i / 32 * 2 * math.pi) * d / 2) for i in range(32)]]
    if s == "quadrant":
        return [[(-hw, 0)] + [(-hw + math.cos(i / 12 * math.pi / 2) * w, math.sin(i / 12 * math.pi / 2) * d) for i in range(13)]]
    if s == "L":
        cut = it.get("cut") or {}
        cw = min(max(cut.get("w") or w / 2, 1), w - 1)
        cd = min(max(cut.get("d") or d / 2, 1), d - 1)
        return [[(-hw, 0), (hw, 0), (hw, d - cd), (-hw, d - cd)], [(-hw, d - cd), (hw - cw, d - cd), (hw - cw, d), (-hw, d)]]
    return [[(-hw, 0), (hw, 0), (hw, d), (-hw, d)]]


def world_parts(it):
    out = []
    for part in local_parts(it):
        pts = []
        for x, y in part:
            qx, qy = rot_pt(-x if it.get("flip") else x, y, it.get("rot") or 0)
            pts.append((it["x"] + qx, it["y"] + qy))
        out.append(pts)
    return out


def bbox(pts):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def convex_overlap(P, Q, tol=0.5):
    for poly in (P, Q):
        for i in range(len(poly)):
            a, b = poly[i], poly[(i + 1) % len(poly)]
            nx, ny = -(b[1] - a[1]), b[0] - a[0]
            L = math.hypot(nx, ny)
            if L < 1e-9:
                continue
            pp = [(p[0] * nx + p[1] * ny) / L for p in P]
            qq = [(p[0] * nx + p[1] * ny) / L for p in Q]
            if min(max(pp), max(qq)) - max(min(pp), min(qq)) <= tol:
                return False
    return True


def parts_overlap(A, B):
    return any(convex_overlap(p, q) for p in A for q in B)


def dist_to_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = 0 if not L2 else min(1, max(0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def point_in_poly(p, pts, tol=0.6):
    if any(dist_to_seg(p, pts[i], pts[(i + 1) % len(pts)]) <= tol for i in range(len(pts))):
        return True
    inside, j = False, len(pts) - 1
    for i in range(len(pts)):
        a, b = pts[i], pts[j]
        if (a[1] > p[1]) != (b[1] > p[1]) and p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
        j = i
    return inside


def half(x):
    return round(x * 2) / 2


def swing_poly(op, wall):
    """Quarter circle a hinged door sweeps (one per leaf)."""
    if op["type"] != "door" or op.get("style", "hinged") not in ("hinged", "double"):
        return []
    at, w = op["at"], op["width"]
    (ax, ay), (ux, uy), (nx, ny) = wall["a"], wall["u"], wall["n"]
    side = -1 if op.get("side") == -1 else 1
    sx, sy = nx * side, ny * side
    j1, j2 = (ax + ux * at, ay + uy * at), (ax + ux * (at + w), ay + uy * (at + w))
    leaves = [(j1, w / 2, 1), (j2, w / 2, -1)] if op.get("style") == "double" else [((j2, w, -1) if op.get("hinge") == "end" else (j1, w, 1))]
    out = []
    for h, r, d in leaves:
        pts = [h] + [(h[0] + r * (ux * d * math.cos(t) + sx * math.sin(t)), h[1] + r * (uy * d * math.cos(t) + sy * math.sin(t))) for t in (i / 8 * math.pi / 2 for i in range(9))]
        out.append(pts)
    return out


def build_plan(data, types, start_sel):
    """Resolve room.json's plan section. Returns (geometry, items, errors, warnings, lines)."""
    plan = data.get("plan")
    errors, warnings, lines = [], [], []
    if plan is None:
        return None, [], errors, warnings, lines
    if not isinstance(plan, dict):
        return None, [], ["plan must be an object."], warnings, lines
    kinds, part_kind = load_kinds()
    raw = plan.get("corners") or []
    corners = []
    for c in raw:
        xy = (c.get("x"), c.get("y")) if isinstance(c, dict) else tuple(c) if isinstance(c, (list, tuple)) and len(c) == 2 else (None, None)
        if not (num(xy[0]) and num(xy[1])):
            errors.append(f"plan.corners: {c!r} must be [x, y] in millimetres."); continue
        corners.append((float(xy[0]), float(xy[1])))
    if len(corners) < 3:
        errors.append("plan.corners needs at least 3 corners (the inside faces of the walls, in order round the room).")
        return None, [], errors, warnings, lines
    if abs(poly_area(corners)) < 1e5:
        errors.append("plan.corners encloses almost no area: are they in millimetres and in order round the room?")
        return None, [], errors, warnings, lines
    for i in range(len(corners)):
        a, b = corners[i], corners[(i + 1) % len(corners)]
        if math.hypot(b[0] - a[0], b[1] - a[1]) < 1:
            errors.append(f"plan.corners {i + 1} and {i + 2} are the same point.")
    walls = outline_walls(corners)
    by_name = {w["letter"]: w for w in walls}
    dividers, divs = [], []
    for i, d in enumerate(plan.get("partitions") or plan.get("dividers") or []):
        if isinstance(d, dict) and "from" in d and "to" in d:
            d = {"x1": d["from"][0], "y1": d["from"][1], "x2": d["to"][0], "y2": d["to"][1], "t": d.get("t", d.get("thickness", 100))}
        if not (isinstance(d, dict) and all(num(d.get(k)) for k in ("x1", "y1", "x2", "y2"))):
            errors.append(f"plan.partitions[{i}] needs from: [x, y] and to: [x, y]."); continue
        doc = {"id": f"p{i + 1}", "x1": d["x1"], "y1": d["y1"], "x2": d["x2"], "y2": d["y2"], "t": d.get("t") if pos(d.get("t")) else 100}
        dividers.append(doc)
        w = divider_wall(doc, i)
        divs.append(w)
        by_name[w["letter"]] = w
        for end in (w["a"], w["b"]):
            if not point_in_poly(end, corners):
                warnings.append(f"partition P{i + 1} ends outside the room at {end}.")
    openings = []
    for i, o in enumerate(plan.get("openings") or []):
        where = f"plan.openings[{i}]"
        if not isinstance(o, dict):
            errors.append(f"{where} is not an object."); continue
        t = o.get("type", "door")
        if t not in OPENING_TYPES:
            errors.append(f"{where}: type must be door, window or opening."); continue
        w = by_name.get(str(o.get("wall", "")).upper())
        if not w:
            errors.append(f"{where}: wall {o.get('wall')!r} is not a wall letter ({', '.join(sorted(by_name))})."); continue
        width, at = o.get("width"), o.get("at", o.get("from", 0))
        if not pos(width):
            errors.append(f"{where}: width must be a positive number of mm."); continue
        if not (num(at) and at >= 0):
            errors.append(f"{where}: at (distance from the start of wall {w['letter']}) must be a number of mm."); continue
        if at + width > w["len"] + 0.5:
            errors.append(f"{where}: {t} {width} mm at {at} mm runs past the end of wall {w['letter']} ({w['len']:.0f} mm)."); continue
        style = o.get("style", "hinged") if t == "door" else None
        if t == "door" and style not in DOOR_STYLES:
            errors.append(f"{where}: style must be one of {', '.join(sorted(DOOR_STYLES))}."); continue
        side = o.get("side", "in")
        side = -1 if side in (-1, "out", "-", "right") else 1
        doc = {"id": f"op{i + 1}", "type": t, "wall": w["id"], "at": at, "width": width, "side": side, "hinge": "end" if o.get("hinge") == "end" else "start"}
        if t == "door":
            doc.update({"style": style, "head": o.get("head", 2040)})
        if t == "window":
            doc.update({"sill": o.get("sill", 900), "head": o.get("head", 2100)})
        openings.append((doc, w))
    # items
    opts = {o.get("id"): o for o in data.get("options") or [] if isinstance(o, dict)}
    els = {e["id"]: e for e in resolve_elements(data, types)}
    items, resolved = [], []
    used = set()
    for i, it in enumerate(plan.get("items") or []):
        where = f"plan.items[{i}]"
        if not isinstance(it, dict):
            errors.append(f"{where} is not an object."); continue
        part = it.get("part")
        if part and part not in els:
            errors.append(f"{where}: part {part!r} is not a part of this room."); continue
        kind = it.get("kind") or (part_kind.get(part) if part else None) or "box"
        if kind not in kinds:
            errors.append(f"{where}: kind {kind!r} is not one of: {', '.join(sorted(kinds))}."); continue
        k = kinds[kind]
        label = it.get("name") or (els[part]["name"] if part else k["label"])
        where = f"{where} ({label})"
        o = opts.get(start_sel.get(part)) if part and it.get("follow", True) else None
        size = o.get("size") if o and isinstance(o.get("size"), dict) and pos(o["size"].get("w")) and pos(o["size"].get("d")) else None
        w = size["w"] if size else it.get("w", k["w"])
        d = size["d"] if size else it.get("d", k["d"])
        h = (size.get("h") if size and pos(size.get("h")) else None) or it.get("h", k["h"])
        if not (pos(w) and pos(d)):
            errors.append(f"{where}: needs w and d in mm (or a part whose chosen option has a size)."); continue
        shape = (o.get("shape") if size and o.get("shape") else None) or it.get("shape") or k.get("shape", "rect")
        if shape not in SHAPES:
            errors.append(f"{where}: shape must be one of {', '.join(sorted(SHAPES))}."); continue
        r = {"w": w, "d": d, "shape": shape, "cut": it.get("cut"), "flip": bool(it.get("flip"))}
        if it.get("against"):
            wall = by_name.get(str(it["against"]).upper())
            if not wall:
                errors.append(f"{where}: against {it['against']!r} is not a wall letter ({', '.join(sorted(by_name))})."); continue
            (ax, ay), (ux, uy), (nx, ny) = wall["a"], wall["u"], wall["n"]
            if wall["kind"] == "divider":
                s = -1 if it.get("side") in (-1, "-", "right") else 1
                nx, ny = nx * s, ny * s
                ax, ay = ax + nx * wall["t"] / 2, ay + ny * wall["t"] / 2
            gap = it.get("gap", 0) or 0
            if num(it.get("from")):
                along = it["from"] + w / 2
            elif num(it.get("from_end")):
                along = wall["len"] - it["from_end"] - w / 2
            else:
                errors.append(f"{where}: with against, give from (mm from the start of wall {wall['letter']} to the item's nearer side) or from_end."); continue
            rr = (math.degrees(math.atan2(-nx, ny)) + 360) % 360
            r.update({"x": half(ax + ux * along + nx * gap), "y": half(ay + uy * along + ny * gap), "rot": round(rr, 1) % 360})
            r["where"] = f"against {wall['name']}, {it.get('from', it.get('from_end'))} mm from its {'start' if num(it.get('from')) else 'end'}"
        elif isinstance(it.get("box"), (list, tuple)) and len(it["box"]) == 2:
            rr = (it.get("rot") or 0) % 360
            if rr not in (0, 90, 180, 270):
                errors.append(f"{where}: box placement needs rot 0, 90, 180 or 270."); continue
            x0, y0 = it["box"]
            ax, ay = {0: (x0 + w / 2, y0), 90: (x0 + d, y0 + w / 2), 180: (x0 + w / 2, y0 + d), 270: (x0, y0 + w / 2)}[rr]
            r.update({"x": half(ax), "y": half(ay), "rot": rr})
            r["where"] = f"box from ({x0}, {y0})"
        elif num(it.get("x")) and num(it.get("y")):
            r.update({"x": it["x"], "y": it["y"], "rot": (it.get("rot") or 0) % 360})
            r["where"] = f"anchor ({it['x']}, {it['y']})"
        else:
            errors.append(f"{where}: give its position with against + from, or box: [x, y] (+ rot), or x, y (+ rot)."); continue
        iid = it.get("id") or re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40] or f"item-{i + 1}"
        base, n = iid, 2
        while iid in used:
            iid = f"{base}-{n}"; n += 1
        used.add(iid)
        doc = {"name": it.get("name", ""), "kind": kind, "shape": it.get("shape") or k.get("shape", "rect"), "w": it.get("w", w), "d": it.get("d", d), "h": it.get("h", h),
               "z": it.get("z", k.get("z", 0)), "x": r["x"], "y": r["y"], "rot": r["rot"], "flip": bool(it.get("flip")), "element": part or "",
               "follow": bool(it.get("follow", True)), "inset": bool(it.get("inset", False)), "order": i, "createdAt": 0}
        if it.get("cut"):
            doc["cut"] = it["cut"]
        if it.get("attach"):
            doc["attach"] = it["attach"]
        items.append((iid, doc))
        resolved.append({"id": iid, "label": label, "kind": kind, "w": w, "d": d, "h": h, "z": doc["z"], "x": r["x"], "y": r["y"], "rot": r["rot"], "shape": shape,
                         "cut": it.get("cut"), "flip": doc["flip"], "inset": doc["inset"], "layer": k.get("layer"), "where": r["where"], "sized_by": o.get("name") if size else None})
    ids = {iid for iid, _ in items}
    for iid, doc in items:
        if doc.get("attach") and (doc["attach"] not in ids or doc["attach"] == iid):
            errors.append(f"plan item {iid!r}: attach {doc['attach']!r} must be the id of another item in the plan ({', '.join(sorted(ids - {iid}))}).")
    attached = {(iid, doc.get("attach")) for iid, doc in items if doc.get("attach")}
    # checks
    for r in resolved:
        pts = [p for part in world_parts(r) for p in part]
        if not all(point_in_poly(p, corners) for p in pts):
            warnings.append(f"plan item {r['label']!r} goes outside the room (check its position and rotation).")
    solid = [r for r in resolved if not r["layer"] and not r["inset"]]
    for i in range(len(solid)):
        for j in range(i + 1, len(solid)):
            a, b = solid[i], solid[j]
            if (a["id"], b["id"]) in attached or (b["id"], a["id"]) in attached:
                continue
            if min(a["z"] + a["h"], b["z"] + b["h"]) - max(a["z"], b["z"]) > 0.5 and parts_overlap(world_parts(a), world_parts(b)):
                warnings.append(f"plan items {a['label']!r} and {b['label']!r} overlap.")
    for w in divs:
        for r in solid:
            if parts_overlap(world_parts(r), [divider_rect(w)]):
                warnings.append(f"plan item {r['label']!r} runs into partition {w['letter']}.")
    for doc, w in openings:
        for sw in swing_poly(doc, w):
            for r in solid:
                if r["z"] < 2000 and parts_overlap([sw], world_parts(r)):
                    warnings.append(f"the door in {w['name']} hits {r['label']!r} when it opens.")
    for e in els.values():
        if e["id"] in {it.get("part") for it in plan.get("items") or [] if isinstance(it, dict)}:
            for o in data.get("options") or []:
                if isinstance(o, dict) and o.get("element") == e["id"] and not o.get("size") and o.get("status") != "rejected":
                    warnings.append(f"option {o.get('name')!r} ({e['id']}) is placed in the floor plan but has no size; the plan will use the item's own size when it is chosen.")
    # summary
    lines.append("  Floor plan: " + ", ".join(f"wall {w['letter']} {w['len']:.0f}" for w in walls) + f"; floor {abs(poly_area(corners)) / 1e6:.2f} m²"
                 + (f"; {len(divs)} partition(s)" if divs else "") + f"; {len(openings)} door(s)/window(s); {len(resolved)} item(s).")
    for r in resolved:
        x0, y0, x1, y1 = bbox([p for part in world_parts(r) for p in part])
        x0, y0, x1, y1 = (0.0 if abs(v) < 0.5 else v for v in (x0, y0, x1, y1))
        lines.append(f"    {r['label'][:30]:30} {r['w']:g} x {r['d']:g}{' x ' + format(r['h'], 'g') if r['h'] else ''} mm{' (size of ' + r['sized_by'][:30] + ')' if r['sized_by'] else ''}; {r['where']}; spans x {x0:.0f}-{x1:.0f}, y {y0:.0f}-{y1:.0f}")
    geometry = {"corners": [{"id": f"c{i + 1}", "x": x, "y": y} for i, (x, y) in enumerate(corners)], "wallT": plan.get("wall_thickness", 100),
                "dividers": dividers, "openings": [d for d, _ in openings], "camera": None, "grid": plan.get("grid", 10), "version": 1}
    cam = plan.get("camera")
    if isinstance(cam, dict):
        if num(cam.get("x")) and num(cam.get("y")):
            geometry["camera"] = {"x": cam["x"], "y": cam["y"], "dir": (cam.get("dir") or 0) % 360, "fov": cam.get("fov", 75), "eye": cam.get("eye", 1600)}
            if not point_in_poly((cam["x"], cam["y"]), corners):
                warnings.append("plan.camera is outside the room.")
        else:
            errors.append("plan.camera needs x and y (mm) and dir (degrees: 0 looks up the plan, 90 right, 180 down, 270 left).")
    u = plan.get("underlay")
    if isinstance(u, dict) and pos(u.get("mm_per_px")):
        geometry["underlay"] = {"src": None, "x": u.get("x", 0), "y": u.get("y", 0), "mmPerPx": u["mm_per_px"], "opacity": 0.45, "show": True}
    return geometry, items, errors, warnings, lines


def check_sizes(data):
    errors = []
    for n, o in enumerate(data.get("options") or []):
        if not isinstance(o, dict):
            continue
        where = f"option {n + 1} ({o.get('name', '?')!s})"
        z = o.get("size")
        if z is not None:
            if not (isinstance(z, dict) and pos(z.get("w")) and pos(z.get("d")) and (z.get("h") is None or pos(z.get("h")))):
                errors.append(f"{where}: size must be {{\"w\": mm, \"d\": mm, \"h\": mm}} with positive numbers (h may be left out).")
            elif max(z["w"], z["d"]) > 12000 or (z["w"] < 20 and z["d"] < 20):
                errors.append(f"{where}: size {z['w']} x {z['d']} looks wrong; sizes are millimetres (60 cm = 600).")
        if o.get("shape") and o["shape"] not in SHAPES:
            errors.append(f"{where}: shape must be one of {', '.join(sorted(SHAPES))}.")
    return errors


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
