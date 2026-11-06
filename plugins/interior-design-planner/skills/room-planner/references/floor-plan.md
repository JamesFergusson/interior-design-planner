# Floor plan

The planner page has a floor plan editor: walls, partitions, doors, windows and every item at its real size, in
millimetres. The person drags things around and types exact sizes and gaps. You set it up through the `plan`
section of room.json (new planners) or the `plan` and `items` collections (existing planners).

## Coordinates

- Millimetres. x runs right across the plan, y runs **down** the plan (as on a screen). Put the origin at the
  inside top-left corner of the room.
- Draw the plan the way the person's drawing is oriented, so their image and yours match.
- `corners` are the **inside faces** of the walls, in order round the room (either direction). Wall A runs from
  corner 1 to corner 2, wall B from corner 2 to corner 3, and so on; the last wall closes back to corner 1.
  `planner.py check` prints the length of every wall: compare them with the drawing.
- Partitions are lettered P1, P2… in the order you list them.

## room.json `plan` section

```json
"plan": {
  "corners": [[0, 0], [2300, 0], [2300, 4115], [0, 4115]],
  "partitions": [{"from": [0, 1050], "to": [2300, 1050], "t": 100}],
  "openings": [
    {"type": "door", "wall": "P1", "at": 900, "width": 700, "hinge": "end", "side": "out"},
    {"type": "window", "wall": "D", "at": 698, "width": 613, "sill": 1000, "head": 2000},
    {"type": "door", "wall": "B", "at": 2567, "width": 700, "hinge": "end"}
  ],
  "items": [
    {"part": "wc", "against": "D", "from": 3485},
    {"part": "tray", "against": "P1", "side": "+", "from": 0},
    {"part": "vanity", "against": "B", "from": 1100},
    {"part": "mirror", "against": "B", "from": 1400, "z": 1100},
    {"name": "Built-in cupboard", "kind": "cabinet", "against": "C", "from": 0, "w": 550, "d": 698, "h": 2470},
    {"name": "Shower side panel", "kind": "screen", "box": [790, 1100], "rot": 90, "w": 790, "d": 10, "h": 1850, "z": 40}
  ],
  "camera": {"x": 1500, "y": 3700, "dir": 0}
}
```

### Openings

- `wall`: a wall letter, or P1, P2… for a partition. `at`: mm from the start of that wall (the corner it shares
  with the previous wall; for a partition, its `from` end) to the near side of the opening. `width`: the opening.
- Doors: `style` `hinged` (default), `double`, `sliding`, `pocket` or `folding`; `hinge` `start` or `end` (which
  jamb the hinges are on, counted along the wall); `side` `in` (default: opens into the room) or `out`. For a
  partition, `side` `+` or `-` says which face it opens towards (`+` is the left side going from `from` to `to`).
  A pocket door slides into the wall on its hinge side. `head`: door height (default 2040).
- Windows: `sill` and `head` heights above the floor (defaults 900 and 2100).
- Use `"type": "opening"` for a doorway with no door.

### Items

Every item is a box (or one of the other shapes) at its real size. Give:

- `part`: the part of the room it is (links it to the options; its size then comes from the chosen option's
  `size`). Leave it out for things that stay or aren't being bought (a built-in cupboard, an existing sofa).
- `kind`: the plan symbol (`wc`, `basin`, `bath`, `shower`, `screen`, `towel-rail`, `radiator`, `mirror`, `units`,
  `wall-unit`, `tall`, `island`, `sink`, `hob`, `oven`, `fridge`, `dishwasher`, `sofa`, `armchair`, `chair`,
  `dining-chair`, `coffee-table`, `side-table`, `dining-table`, `desk`, `bed`, `bedside`, `wardrobe`, `drawers`,
  `cabinet`, `sideboard`, `shelving`, `media-unit`, `rug`, `plant`, `lamp`, `box`… the full list with standard UK
  sizes is `references/plan-kinds.json`). A part normally implies its kind.
- Size: `w` (across the front), `d` (front to back), `h` (height), `z` (height of its bottom above the floor, for
  wall-hung things), all mm. Needed when the item has no part, when its option has no size, or with
  `"follow": false` (keep this size whatever product is chosen, e.g. a 600 mm unit housing an integrated fridge).
- `shape`: `rect` (default), `rounded`, `round`, `quadrant` (corner shower: straight back and left side, curved
  front) or `L` (with `"cut": {"w": .., "d": ..}`, the missing front-right corner). `flip: true` mirrors it.
- `inset: true` for something built into a unit or worktop (an integrated dishwasher, an undermount sink), so it
  isn't reported as clashing with the unit.
- Position, one of:
  - `against` + `from`: back to that wall, facing into the room, with its nearer side `from` mm from the start of
    the wall (or `from_end` mm from the end). `gap` leaves a gap behind it. For a partition add `side`.
    This is the right choice for almost everything that stands against a wall.
  - `box: [x, y]` + `rot` 0, 90, 180 or 270: the top-left corner of the space it takes up on the plan. Good for
    free-standing things (an island, a dining table) and for thin screens.
  - `x`, `y`, `rot`: the middle of its back edge, turned `rot` degrees clockwise (0 = back towards the top).

### Camera

`{"x", "y", "dir", "fov", "eye"}`: where someone would stand for the picture, `dir` in degrees (0 looks up the
plan, 90 right, 180 down, 270 left), field of view (default 75) and eye height (default 1600). The ChatGPT prompt
describes the walls as far, left, right and behind from here.

## Reading someone's floor plan

1. Find the overall inside dimensions first, then each wall's length. Use dimensions written on the plan exactly.
   If a length is only drawn, scale it from a written dimension on the same drawing and say in the hand-over which
   figures you scaled. Estate-agent plans are often drawn to the widest point and rounded: treat them as
   approximate and say so.
2. Go round the room clockwise from the top-left inside corner, writing the corners. Recesses, chimney breasts and
   boxing-in are extra corners.
3. Place doors and windows by their distance from a corner. If the plan doesn't give it, scale it.
4. Place the fittings that are staying, then the parts being planned, using the person's layout or a sensible one.
5. Run `planner.py check room.json`. It prints every wall's length and every item's position and size, and warns
   about clashes, items outside the room and doors that hit things. Fix the plan until it matches the drawing and
   has no clashes you didn't intend.
6. Set `room.plan_file` to the drawing so it sits under the plan in the page (the person can set its scale there).
   If you know the drawing's scale, add `"underlay": {"mm_per_px": <mm per image pixel>, "x": <mm>, "y": <mm>}`.
   It starts hidden when the plan has items (it shows their old positions); the "Plan image" button shows it.

Tell the person to check the walls against a tape measure before ordering anything that has to fit.

## Existing planners

The page stores the plan in `plan/geometry` and one document per item in `items/<id>`. To draw a plan for an
existing planner, write a room.json with the plan section, run `planner.py seed` to a scratch folder and send only
the `plan/geometry` and `items/…` writes (not the room or the options). Read `plan/geometry` and pin its `version`
before changing an existing plan; the person may have edited it.
