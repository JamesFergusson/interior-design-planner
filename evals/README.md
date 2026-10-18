# Evals

`scenarios.json` holds realistic first requests with scripted user answers and expectations. To run one, give a
fresh Claude agent the prompt in TESTING.md (layer 3) with the scenario's request and answers, a working folder, and
the test-mode rules (no publishing, stop after `planner.py check`). Then:

    python3 evals/grade.py <working-folder> <scenario-id>

Round 1 (5 scenarios) found that new planners opened with nothing chosen; round 2 (3 scenarios + live inbox runs)
passed with every part given a starting choice and every total inside the budget. A spot-check of 15 products
against their pages found no invented products or prices.
