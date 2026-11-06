# Changelog

## 0.2.0 — 2026-11-06

Floor plan.

- Floor plan editor in the planner page, in millimetres: walls of any shape, partitions, doors (hinged, pairs,
  sliding, pocket, folding) and windows, and every item at its real size with a plan symbol. Drag to move, with
  snapping to walls, other items and a grid; arrow keys move 1, 10 or 100 mm; type exact sizes, heights, turns and
  the clear gap on each side. Live distances to the nearest wall or item. Clashes, items outside the room and doors
  that hit things are flagged. Measure tool, undo and redo, zoom and pan, touch.
- Items linked to a part take the chosen product's size, and change when the choice changes.
- The person's floor plan image can sit underneath, scaled from two points a known distance apart.
- Floor and wall areas from the plan, with a "Use plan" button on paint and flooring quantities.
- ChatGPT: the prompt gives every wall, opening and item with its size and position, and the view from a camera
  placed on the plan; "Save plan image" makes a labelled drawing to attach, also used on the reference board.
- Options gain a size and shape (form fields, link reading, setup script).
- Setup script: a `plan` section in room.json (walls, partitions, openings, items placed against walls or by
  position, camera), checked for mistakes, clashes and door swings, and written to the planner.
- Resize items by dragging handles on their edges and corners. Resizing something that takes its size from a
  chosen product adds a "size to test" option to that part and chooses it, so a bigger shower can be tried
  without a product; resizing again updates it, and picking a real product goes back.
- Items can be attached to another (shower screens to their tray): they move, turn and resize with it, and a
  wider product chosen in the list keeps its wall-side edge where it was.
- Doors and windows: "+ Door" and "+ Window" on the toolbar, and handles on each edge to resize them by dragging.
- "Save to room brief" makes the current layout the room's plan (the brief shows a drawing of it; the original
  drawing is kept) and keeps it as a version. "Go back to…" returns to the original plan, any saved version, or
  the layout as it was when the page was opened; Undo returns to the latest changes.
- Pictures from ChatGPT: add them back to the planner (choose files, drop them on the panel, or paste). Each keeps
  the date, the choices and prompt it was made from, and a note; one can be the room brief's design study.
- Backup and restore include the floor plan, the saved plan and the pictures.
- Paint-chip labels pick whichever text colour reads better.

## 0.1.0 — 2026-10-18

First release.

- Planner page: options per part with photos, prices and links; quantities and costs; budget bar; shopping schedule
  (copy and .csv); link inbox with in-page reading in the Claude desktop app; ChatGPT prompt and reference board;
  backup and restore; undo for removals; add options, parts and photos by hand; first-run setup screen.
- Room types: living room, bedroom, bathroom, kitchen, dining room, home office, hallway, child's bedroom, other.
- Setup script that checks room.json and builds the database writes; starting choices from the shortlist, with
  "Suggested" and "Cheapest" sets.
