from __future__ import annotations

import csv
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional, Tuple

from flask import (
    Flask,
    jsonify,
    request,
    send_file,
    render_template,
    after_this_request,
)
from werkzeug.middleware.proxy_fix import ProxyFix
import logging


# ----------------------------------------------------------------------------
# DB / App setup
# ----------------------------------------------------------------------------
SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  type TEXT NOT NULL,           -- rest, nearfar, saccade, contrast(optional)
  duration_sec INTEGER NOT NULL DEFAULT 0,
  meta TEXT DEFAULT ''          -- JSON string (optional)
);
CREATE TABLE IF NOT EXISTS metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,           -- YYYY-MM-DD (local)
  fatigue_score INTEGER,        -- 1-5
  near_work_min INTEGER,        -- 近業時間（分）
  breaks INTEGER,               -- 休憩回数
  contrast_min_readable REAL    -- 最小可読コントラスト（任意）
);
"""


def _get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _insert_session(db_path: str, s_type: str, duration_sec: int, meta: str = "") -> Tuple[bool, Optional[str], int]:
    ts = int(time.time())
    try:
        with _get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO sessions(ts, type, duration_sec, meta) VALUES(?,?,?,?)",
                (ts, s_type, duration_sec, meta),
            )
            conn.commit()
        return True, None, ts
    except Exception as e:
        return False, str(e), ts


def _insert_metric(
    db_path: str,
    date: str,
    fatigue: Optional[int],
    near_min: Optional[int],
    breaks: Optional[int],
    contrast: Optional[float],
) -> Tuple[bool, Optional[str]]:
    try:
        with _get_conn(db_path) as conn:
            conn.execute(
                "INSERT INTO metrics(date, fatigue_score, near_work_min, breaks, contrast_min_readable) VALUES(?,?,?,?,?)",
                (date, fatigue, near_min, breaks, contrast),
            )
            conn.commit()
        return True, None
    except Exception as e:
        return False, str(e)


def _export_to_csv(db_path: str, outfile: Path) -> None:
    with _get_conn(db_path) as conn, outfile.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["# sessions"])
        w.writerow(["id", "ts", "type", "duration_sec", "meta"])
        for row in conn.execute("SELECT id, ts, type, duration_sec, meta FROM sessions ORDER BY id"):
            w.writerow(row)
        w.writerow([])
        w.writerow(["# metrics"])
        w.writerow(["id", "date", "fatigue_score", "near_work_min", "breaks", "contrast_min_readable"])
        for row in conn.execute(
            "SELECT id, date, fatigue_score, near_work_min, breaks, contrast_min_readable FROM metrics ORDER BY id"
        ):
            w.writerow(row)


def create_app() -> Flask:
    # Use instance-relative config so instance/ is writable for DB by default
    app = Flask(__name__, instance_relative_config=True)

    # Ensure instance dir exists (for SQLite on production)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except Exception:
        # If the instance path cannot be created, fallback will be env DB_PATH
        pass

    # Resolve DB path; default to file in CWD unless env overrides
    app.config["DB_PATH"] = os.environ.get(
        "DB_PATH",
        os.path.join(app.instance_path, "presbyopia_app.sqlite3"),
    )

    # Honour reverse proxy headers when behind a load balancer if enabled
    if os.environ.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)  # type: ignore[assignment]

    # Configure logging to integrate with gunicorn if present
    try:
        gunicorn_logger = logging.getLogger("gunicorn.error")
        if gunicorn_logger and gunicorn_logger.handlers:
            app.logger.handlers = gunicorn_logger.handlers
            app.logger.setLevel(gunicorn_logger.level)
    except Exception:
        pass

    # Initialize DB on startup
    with _get_conn(app.config["DB_PATH"]) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    @app.route("/")
    def index():
        return render_template("index.html", now=datetime.now().strftime("%Y-%m-%d %H:%M"))

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True}), 200

    @app.route("/api/log", methods=["POST"])
    def log_api():
        """セッションやメトリクスを保存する。"""
        data: Dict[str, Any] = request.get_json(silent=True) or {}
        kind = data.get("kind")

        if kind == "session":
            s_type = str(data.get("type", "")).strip()
            duration = _coerce_int(data.get("duration_sec"), 0)
            meta = str(data.get("meta", ""))
            if not s_type or duration <= 0:
                return jsonify({"ok": False, "error": "invalid session payload"}), 400
            ok, err, ts = _insert_session(app.config["DB_PATH"], s_type, duration, meta)
            if not ok:
                return jsonify({"ok": False, "error": err or "db error"}), 500
            return jsonify({"ok": True, "saved": {"ts": ts, "type": s_type, "duration_sec": duration}})

        if kind == "metric":
            date = str(data.get("date", "")).strip()
            if not date:
                return jsonify({"ok": False, "error": "date required"}), 400
            fatigue = data.get("fatigue_score")
            near_min = data.get("near_work_min")
            breaks = data.get("breaks")
            contrast = data.get("contrast_min_readable")
            ok, err = _insert_metric(app.config["DB_PATH"], date, fatigue, near_min, breaks, contrast)
            if not ok:
                return jsonify({"ok": False, "error": err or "db error"}), 500
            return jsonify({"ok": True, "saved": {"date": date}})

        return jsonify({"ok": False, "error": "invalid kind"}), 400

    @app.route("/api/export.csv")
    def export_csv():
        """sessions と metrics をCSVでダウンロード"""
        # Use NamedTemporaryFile with delete=False so send_file can read it
        tmp = NamedTemporaryFile(prefix="export_presbyopia_", suffix=".csv", delete=False)
        tmp_path = Path(tmp.name)
        tmp.close()
        _export_to_csv(app.config["DB_PATH"], tmp_path)

        @after_this_request
        def cleanup(response):  # type: ignore[unused-ignore]
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
            return response

        return send_file(tmp_path, as_attachment=True, download_name="export_presbyopia.csv")

    return app


if __name__ == "__main__":
    # Default debug False for safety in accidental production usage
    debug = os.environ.get("FLASK_DEBUG", "0") not in {"0", "false", "False"}
    host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    app = create_app()
    app.run(debug=debug, host=host, port=port)
