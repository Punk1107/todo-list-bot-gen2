"""
utils/webserver.py — Lightweight Flask keep-alive server.
Runs in a daemon thread so it never blocks the bot event loop.
"""
from __future__ import annotations

import logging
import threading

from flask import Flask, jsonify

from core.config import config

log = logging.getLogger(__name__)

app = Flask(__name__)

# Silence Flask's default request logs to avoid mixing with bot logs
logging.getLogger("werkzeug").setLevel(logging.ERROR)


@app.route("/")
def index():
    return jsonify({"status": "online", "service": "To-Do List Bot Gen 2"})


@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200


def start() -> None:
    if not config.webserver.enabled:
        log.info("Webserver disabled — skipping")
        return

    def _run():
        app.run(
            host=config.webserver.host,
            port=config.webserver.port,
            debug=False,
            use_reloader=False,
        )

    thread = threading.Thread(target=_run, daemon=True, name="webserver")
    thread.start()
    log.info("Keep-alive webserver started on %s:%d", config.webserver.host, config.webserver.port)
