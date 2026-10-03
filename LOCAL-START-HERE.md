# PYQ Studio — complete local app

## Windows
1. Extract this ZIP into a normal folder (do not run inside the ZIP).
2. Install Python 3.11 or 3.12 if needed; enable the Python launcher.
3. Double-click **SETUP-LOCAL.cmd** once. Internet is needed to install Python dependencies.
4. Double-click **START-LOCAL.cmd**. Open http://127.0.0.1:5000.
5. Choose Quiz 1 → LOCAL DEMO course → sample paper → Start exam. Open the scratch board to test drawing, pages and PDF export.

Local admin: **admin@local.test** / **local-preview-123**. These credentials apply only to this local demo.

The frontend is already built. Node is not needed just to run this copy.
The local SQLite database and uploads are stored in `.local-demo` and survive restarts. Bulk catalog processing stays paused; the local upload worker runs with the app. To stop both, press Ctrl+C in the terminal.
This is the complete source code plus a sample paper. Production papers, Supabase/R2 data, OAuth credentials, private configuration and user data are not included. The local launcher uses only local storage and a separate SQLite database. Starting locally does not change the live site.

## Linux / WSL
```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/local_preview.py
```

## Edit frontend source
Install Node 22.10+ or 24+, then run `npm ci` and `npm run build` inside `frontend`. Restart the local app after building.

## Included changes
Scratch notebook with multiple pages, four pen colours, eraser, automatic line/ellipse/rectangle recognition, per-page undo/redo, PDF export with page numbers and session storage. Shape recognition remains heuristic; unclear strokes remain freehand.
Start exam immediately shows an animated indeterminate native progress bar and loading message. It stays visible during exam creation and question loading; it does not invent a percentage.

Use START-LOCAL.cmd for this release. Existing START.cmd and migration scripts are preserved for their older configured deployment workflows.
GitHub and the live deployment have not been updated by creating this ZIP.
