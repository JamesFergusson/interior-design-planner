# Data model

The planner page reads everything from its database. `scripts/planner.py seed` turns a `room.json` into these
documents; the same shapes apply when adding or changing documents directly with ArtifactData.

## room.json (input to planner.py)

```json
{
  "room": {
    "name": "Living room, 12 Mill Lane",
    "type": "living-room",
    "units": "metric",
    "currency": "GBP",
    "length_mm": 4800, "width_mm": 3600, "height_mm": 2500,
    "budget": 6000,
    "scheme": "warm white, olive green, walnut and aged brass; calm and bright",
    "layout": "Door in the corner of the long wall; bay window opposite; chimney breast with alcoves on the end wall; TV in the left alcove.",
    "swatches": [{"name": "Olive", "hex": "#6b7046"}],
    "keeping": "the grey three-seat sofa and the fireplace",
    "sizesEstimated": false,
    "plan_file": "photos/plan.jpg",
    "photo_file": null
  },
  "drop": ["plants"],
  "override": {"rug": {"place": "Under the front legs of the sofa, 2400 x 1700 mm"}},
  "extra": [{"id": "picture-light", "group": "Lighting", "name": "Picture light", "unit": "item", "qty": 1, "place": "Above the art"}],
  "options": [ { "...": "see Option" } ],
  "picks": {"sofa": "sofa-olive"}
}
```

- Sizes are millimetres, whatever `units` says (`units` only changes what the page shows and the quantity units).
  Convert feet with × 304.8. If the user doesn't know them, estimate a typical room and set `sizesEstimated: true`.
- `keeping`: things that stay as they are (shown on the page and told to ChatGPT so it draws them).
- `currency`: `GBP`, `EUR` or `USD`.
- `drop` removes template parts by id; `override` patches a part (name, place, qty, unit, group, hint);
  `extra` adds parts. To replace the whole part list instead, give `"elements": [...]`.
- Part ids and option ids: lowercase letters, digits and hyphens. Option ids are generated if missing, but set
  them when the option has a photo or is in `picks`.
- `picks` maps part id to option id for products the user has already chosen.

## Part (`elements/<id>`)

| Field | Meaning |
| --- | --- |
| `name` | Shown as the row title, e.g. "Flooring" |
| `group` | Section heading, e.g. "Walls & floor" |
| `order` | Sort order (number) |
| `place` | Where it goes; also used in the ChatGPT prompt |
| `hint` | What a neutral stand-in looks like if nothing is chosen (prompt only) |
| `render` | `false` for parts the picture should leave out (e.g. underfloor heating) |
| `unit` | `item`, `m²`, `m`, `L`, `ft²` or `ft` |
| `qty` | How many units the room needs; `null` if unknown (costs then show "set the quantity") |

## Option (`options/<id>`)

| Field | Meaning |
| --- | --- |
| `element` | The part id it belongs to |
| `name`, `supplier`, `url` | Product name, shop, product page (https) |
| `price` | Number, no currency sign; `null` if unknown |
| `per` | What one `price` buys: `item` (default), the part's unit (`m²`, `m`, …), or `pack`/`box`/`tin`/`can`/`roll`/`tile`/`set`/`pair` |
| `covers` | For packs: how much of the part's unit one pack covers (m² per box, items per set). `null` otherwise |
| `owned` | `true` for something the user already has (no link or price needed) |
| `priceNote` | Price as shown, sale, delivery or "quote needed" |
| `spec` | One line: size, colour, finish, material |
| `note` | One practical point for this room |
| `status` | `idea`, `shortlisted` or `rejected` |
| `image` | `/_blob/<id>` from an upload, or `""` (written by `planner.py seed`; don't set it in room.json) |
| `image_file` | room.json only: path of a downloaded photo, e.g. `photos/sofa-olive.jpg`; `planner.py photos` lists these for upload |
| `source` | `setup`, `link`, `manual`, or `plan` (a "size to test" placeholder made by resizing an item in the floor plan; no product yet) |
| `size` | `{"w", "d", "h"}` in mm: width across the front, depth front to back, height; plus `"from"`: `page`, `estimate` or `manual`. Leave out if unknown |
| `shape` | `""` (rectangle), `rounded`, `round`, `quadrant` or `L`: how the floor plan draws it |
| `order` | Sort order within the part |

### How cost is worked out (page and script use the same rule)

1. `covers` set → packs = round up (part qty ÷ covers); cost = packs × price.
2. `per` equals the part's unit (or both are items) → cost = price × part qty.
3. Otherwise → cost = price (one purchase).

Examples, for flooring with qty 19 m²: `54.99 per m²` → £1,044.81; `32.50 per box, covers 1.8` → 11 boxes, £357.50;
a rug at `420` (part unit item, qty 1) → £420. Paint, 35.7 m² of wall, `59 per tin, covers 16` → 3 tins, £177.
Knobs, 12 needed (unit item), `12.90 per set, covers 4` → 3 sets, £38.70. Floor tiles sold singly,
`16.74 per tile, covers 0.36` on 2.6 m² → 8 tiles, £133.92.

### One purchase covers the part

When a part needs several of something (2 alcove shelves) but an option covers it in one purchase (one bookcase),
give that option `"per": "set", "covers": <the part's qty>` so it costs once.

## Floor plan (room.json `plan`)

Optional. Walls, partitions, doors, windows, the items in the room and a camera position, all in millimetres.
The format, and how to read someone's floor plan, are in `references/floor-plan.md`.

## Starting choices

`state/selection` starts as `picks` plus the first `shortlisted` option in every other part. Two presets are made:
"Suggested" (the same) and "Cheapest" (the cheapest priced, non-rejected option in each part).

## Other documents

- `room/brief`: the `room` section plus `setupDone: true`, `version`, and `plan`/`photo`/`vis` image URLs.
- `state/selection`: `{"map": {"<part id>": "<option id>" or null}}` — the user's current choices.
- `presets/<id>`: `{"name", "order", "map"}` — saved sets of choices; `suggested` (picks + shortlisted) and `cheapest` are made at setup.
- `plan/geometry`: `{"corners": [{"id", "x", "y"}], "wallT", "dividers": [{"id", "x1", "y1", "x2", "y2", "t"}],
  "openings": [{"id", "type", "wall" (a corner id = the wall starting there, or a divider id), "at", "width", "side" (1 or -1),
  "hinge", "style", "sill", "head"}], "camera": {"x", "y", "dir", "fov", "eye"} or null, "underlay": {"src", "x", "y", "mmPerPx",
  "opacity", "show"}, "grid", "version"}`. Written by `planner.py seed` from the `plan` section, and by the page as people edit.
- `plan/saved`: the layout "Reset to brief plan" goes back to: `{"geometry", "items": [{"id", …}], "savedAt", "image"?}`.
  `planner.py seed` writes the starting layout; "Save to room brief" replaces it and puts a drawing of the layout in
  `room/brief.plan` (the drawing it replaced, if any, is kept as `room/brief.planOriginal`).
- `items/<id>`: one thing in the floor plan: `{"name", "kind", "shape", "w", "d", "h", "z", "x", "y", "rot", "flip", "cut",
  "element" (part id or ""), "follow" (take the chosen option's size), "inset", "attach" (id of the item it moves with), "order"}`. `x`, `y` are the middle of its back
  edge; `rot` is clockwise degrees.
- `inbox/<id>`: `{"url", "element", "note", "state", "createdAt", "optionId"?, "error"?}`;
  `state` is `new`, `working`, `queued`, `done` or `failed`.
