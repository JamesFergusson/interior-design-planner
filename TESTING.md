# Testing

Four layers. Layers 1 runs automatically on every push; 2 and 3 are run before each release; 4 needs people.

## 1. Automated (every change) — `npm test`

- **Page tests** (`tests/page.test.mjs`): the real `planner.html` runs in headless Chromium against an in-memory
  stand-in for Claude's services (`tests/mock-claude.js`: saved data, photo storage, downloads, Claude's replies,
  the desktop browser). Fixture rooms are built by the same script Claude uses (`tests/make_fixtures.py` →
  `planner.py seed`), so the setup pipeline is tested too. Covers: first-run setup (metric and imperial), every
  fixture room rendering with the same total as the script, a grid of 900 cost cases agreeing between page and
  script, choosing/clearing, quantities, budget bar, statuses and filters, presets, adding and editing options with
  validation and photos, removing with undo, adding parts, copy and .csv, the ChatGPT prompt and link length, the
  reference board, backup and restore, the inbox with and without the desktop app, save failures, hostile data
  (no injected script runs), layout at phone and desktop width in light and dark, and an accessibility scan.
- **Script tests** (`tests/test_planner_py.py`): quantities, cost rules, the checks that catch common mistakes,
  seed output (batch sizes, write order, starting choices, photo mapping), room-type templates, and that the
  version number agrees everywhere.
- **Build check**: `tools/build.py --check` fails if `room-types.json` and the page template disagree.
- **Plugin check**: `claude plugin validate` on the plugin and the marketplace.

## 2. Live platform (before release)

Publish a test planner from the template with the skill's exact capabilities, upload photos, send the seed batches,
read everything back (including as a view-only user), and confirm a shared editor can write. Confirm the desktop
browser tool's argument and result shapes match what the page expects.

## 3. Claude using the skill (before release) — `evals/`

Fresh Claude agents follow `SKILL.md` on the scenarios in `evals/scenarios.json` (with scripted user answers),
doing real product research, and stop before publishing. `evals/grade.py <run-dir> <scenario>` grades each run:
check passes, room type/currency/units right, scope respected, enough options per part, prices and links present,
starting choices cover most parts, within budget. A separate agent re-opens a sample of product pages to confirm
names and prices are real. The inbox flow is tested live on a test planner (one dead link, one good link).
Each agent also reports where the instructions were unclear; those reports drive the next revision.

## 4. People (before announcing a release)

Install from GitHub in the Claude desktop app and work through:

1. Ask Claude to plan a room you know. Does it ask sensible questions, once?
2. Open the planner: are the starting choices and total plausible? Are the products real and suitable?
3. Change a quantity; pick a different option; apply "Cheapest" then "Suggested".
4. Paste a product link into the inbox and press **Update**. Does it appear as an option?
5. **Add photo** on a card; **+ Add an option** by hand; remove one and press **Undo**.
6. **Visualise in ChatGPT**: does ChatGPT open with the prompt filled in? Save the reference board and add it.
7. **Save backup**, then **Restore from backup**.
8. Open the planner on your phone.
9. Share it with someone; can they open and change it?
10. Ask Claude to "process my room planner inbox" and "find a cheaper option for …".

Note anything confusing, slow or wrong, with a screenshot.
