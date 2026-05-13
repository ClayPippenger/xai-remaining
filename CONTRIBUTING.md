# Contributing

Thanks for improving xAI Remaining. This project is intentionally small: a local Windows tray utility for xAI prepaid credit.

## Development Setup

```bat
py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
```

Run local diagnostics without starting the tray or calling xAI:

```bat
py -3 xai_remaining.py --diagnose
```

Run compile verification:

```bat
py -3 -m py_compile xai_remaining.py providers\base.py providers\xai_provider.py providers\__init__.py
```

Check the rebuild workflow safely:

```bat
cmd /c rebuild_and_run.bat --dry-run
```

## Pull Requests

- Keep changes focused and Windows-friendly.
- Include a short summary and verification notes.
- Mention any changes to environment variables, cache behavior, API endpoints, or build scripts.
- Do not add unrelated providers, telemetry, charts, popups, or GUI windows without discussion.

## Safety Rules

- Do not commit real `XAI_MGMT_KEY` or `XAI_TEAM_ID` values.
- Do not paste Management Keys, team IDs, or full billing payloads in issues, logs, tests, or screenshots.
- Do not commit runtime cache files from `state/` or `dist/state/`.
- Do not commit generated `build/`, `dist/`, `*.spec`, `__pycache__/`, or `.venv/` output.
- Avoid dumping full xAI billing JSON. Use the existing safe debug commands for field discovery.
