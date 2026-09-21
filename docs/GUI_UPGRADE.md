# Harborlight GUI refinement

This update refines the existing Harborlight frontend while keeping the existing FastAPI endpoints, classification, comparison logic, review persistence and exports unchanged.

## What changed

- Evidence-first decision brief for each case, derived from the selected case's seven field outcomes. Clearly distinguishes confirmed differences, unresolved evidence and aligned fields.
- Review and source buttons move directly to the existing tabs.
- Mismatched fields appear first in the comparison table and receive stronger highlighting while the SI reference remains visually distinct.
- Quick outcome filters remain synchronized with the existing dropdown.
- Case queue shows category and import timestamp alongside its existing status, risk number and review state.
- Upload dialog gives clearer file-selection feedback; successful imports provide a dismissible summary.
- More consistent card shape, contrast, active states and responsive layout. Reduced-motion preferences remain supported.

## Apply to an existing Windows installation with 532 cases

1. Stop the server in VS Code with `Ctrl+C`.
2. Back up your existing project folder, especially `var/harborlight.sqlite3`.
3. From `Harborlight_GUI_Patch.zip`, copy its **web** folder into the project root (the folder with `run.py`), allowing replacement of the three existing web files.
4. Keep your local `var` folder and `.venv` folder. **Do not copy a new database over your existing one.** This GUI patch does not include a database.
5. In your activated virtual environment run `python run.py`, then hard-refresh the browser with `Ctrl+Shift+R`.
6. Select an existing discrepancy case to verify the decision brief, highlighted fields, source tabs and review shortcuts. The case totals should remain unchanged because no database migration is involved.

## Clean source ZIP

`Harborlight_GUI_Updated_Source.zip` is a clean source-code handoff and has no private imported inbox, uploaded dataset, local SQLite database, virtual environment or secrets. Fresh installations show 12 synthetic demo cases until permitted data is imported. Do not put live customer inboxes or a local database into a public repository without explicit authorization.

## Validation

- Automated Python suite: 110 passed, 38 subtests passed in an isolated source workspace.
- Node.js syntax check for web/app.js: passed.
- Browser interaction smoke on **mocked HTTP responses with 12 synthetic demo cases**: selection, filters, decision brief, source/review navigation, import success feedback, and no uncaught JavaScript errors.
- The runtime also returned HTTP 200 for `/api/health` when started with a separate temporary SQLite path. Direct Chromium navigation to localhost is restricted by the test environment, so the visual test used locally rendered HTML and mocked API responses.

The preview is illustrative only. Recheck the full workflow against your Windows database before demo day.
