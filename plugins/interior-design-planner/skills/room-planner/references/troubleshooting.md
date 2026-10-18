# Troubleshooting

| Problem | What to do |
| --- | --- |
| `planner.py check` reports errors | Fix room.json and run check again. Each message names the field. |
| Publish refused mentioning `mcp` or `host:claude_browser` | Publish again without the `mcp` and `sample` entries. Links will then queue for you to process. |
| Publish refused for another reason | Report the reason to the user in one line; do not hand-build another page. |
| Photo upload refused | Continue without photos; say the user can add them with "Add photo". |
| A batch write fails with `quota_exceeded` | The planner's database is full. Remove old inbox items or rejected options. |
| A batch write fails because a document exists | The planner already has data. Do not re-seed; add or update individual documents with `if_version`. |
| The page shows "Set up your room" after seeding | `room/brief` was not written or lacks `setupDone: true`. Check the last batch went through. |
| The page shows "Open this page in Claude" | It was opened outside Claude (e.g. a downloaded copy). Open the planner's link in Claude. |
| Totals look wrong | Check the part's `qty` and `unit`, and the option's `per` and `covers` (see data-model.md). |
| Image downloads fail (403 or not an image) | The environment blocks those sites. Skip photos; the user can add them with "Add photo". |
| A shop page can't be read | Some shops block automated visits. Ask the user to paste the price and size, or pick another shop. |
| The ChatGPT chat opens empty | The prompt is also copied; paste it. The page's "See or edit the prompt" shows it. |
