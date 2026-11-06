# Interior Design Planner

A Claude plugin that sets up an interactive planner for redecorating a room. You tell Claude about the room;
Claude finds real products for each part of it and builds you a page where you can:

- compare options side by side, with photos, prices and links, and pick one per part;
- see quantities and costs worked out for your room (paint by wall area, flooring by floor area, tiles by the box);
- lay the room out on a floor plan drawn to the millimetre: drag furniture and fittings around, type exact sizes and
  gaps, add or move doors, windows and partition walls. Give Claude your floor plan and it draws it for you;
- keep an eye on the total against your budget;
- copy or download a shopping schedule;
- paste product links you find and have Claude add them;
- open ChatGPT with a ready-made prompt to picture the room, giving the exact size and position of everything, plus
  a labelled plan image and a reference board of your choices, then keep the pictures ChatGPT makes in the planner;
- save and restore a backup.

Works for living rooms, bedrooms, bathrooms, kitchens, dining rooms, home offices, hallways and children's rooms.

## Install

**Claude desktop app (Cowork)**

1. Open **Customize** in the sidebar, then **Plugins**.
2. Choose **Add marketplace** and enter `JamesFergusson/interior-design-planner`.
3. Find **Interior Design Planner** and click **Install**.

**Skill only (other Claude apps)**

Download `room-planner.zip` from the latest release, then go to **Customize › Skills**, click **+**, choose
**Upload a skill** and select the zip. Code execution must be turned on in your settings. The planner needs Claude
to be able to publish pages that keep saved data; the Claude desktop app is the tested route.

## Use

Start a new task and say something like:

> Help me plan my living room. It's about 4.8 by 3.6 metres, I like warm white, olive and walnut, budget £6,000.

Claude asks a few questions (all optional), researches products, and gives you the planner. Later you can say:

- "Process my room planner inbox" — adds the links you pasted into the page.
- "Find me a cheaper rug for the planner."
- "Update my room planner" — moves an older planner to the latest version, keeping your choices.

Good to know:

- Each planner is private to you until you share it. Anyone you share it with can see and change it.
- Pasting a link and pressing **Update** inside the page needs the Claude desktop app. Elsewhere, ask Claude to
  process the inbox.
- Prices are estimates taken when each option was added. Check them before ordering. Fitting and delivery are not
  included.
- If Claude can't download product photos in your setup, add them yourself with **Add photo** on each card.

## Updating

Cowork checks the marketplace for updates; use **Check for updates** on the marketplace or turn on automatic sync.
Existing planners keep working; ask Claude to "update my room planner" to get the newest page.

## For developers

See [TESTING.md](TESTING.md) for how the plugin is tested, and [CHANGELOG.md](CHANGELOG.md) for changes.

```
plugins/interior-design-planner/
  .claude-plugin/plugin.json
  skills/room-planner/
    SKILL.md                    instructions Claude follows
    assets/planner.html         the page template (never edited per room)
    scripts/planner.py          checks room.json, lists photos, builds the database writes
    references/                 data model, floor plan, research guide, troubleshooting, room types, plan symbols
tests/                          automated tests (page in headless Chromium + Python)
evals/                          scenarios and grader for testing Claude's use of the skill
tools/build.py                  copies room-types.json and plan-kinds.json into the page template
```

Licence: MIT.
