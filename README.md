eye-training

Usage
- Install dependencies (at minimum `Flask`).
- Run the app: `python app.py`
- Open http://127.0.0.1:5000/

Notes
- Database path: set `DB_PATH` to change SQLite file location.
- CSV export cleans up a temporary file after download.

Production (WSGI)
- Entry point: `wsgi:app` (created via `wsgi.py`).
- Run with gunicorn: `gunicorn wsgi:app` (or `gunicorn 'app:create_app()'`).
- Environment:
  - `DB_PATH`: optional absolute path to SQLite file.
    - Default is `instance/presbyopia_app.sqlite3` when writable; otherwise falls back to `/tmp/presbyopia_app.sqlite3`.
  - `TRUST_PROXY=1`: enable proxy header handling behind reverse proxy/LB.
  - `PORT`, `FLASK_RUN_HOST`: when running `python app.py`.
    - If not set and not in debug, the app binds to `0.0.0.0` for PaaS compatibility.
- Healthcheck: `GET /healthz` returns `{ "ok": true }`.

Instance Directory
- Flask creates/uses a writable `instance/` directory (ignored by VCS) for the DB by default.
- Ensure the process user can write to it, or set `DB_PATH` to a writable location.
  - On read-only filesystems, the app automatically falls back to `/tmp/presbyopia_app.sqlite3`.
