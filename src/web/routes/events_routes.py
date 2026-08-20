"""Server-Sent Events (SSE) live streaming route for real-time intake updates."""

import time
import json
from flask import Blueprint, Response, current_app, g
from src.web.auth import login_required

events_bp = Blueprint("events", __name__)


@events_bp.route("/api/events/stream", methods=["GET"])
@login_required
def sse_event_stream():
    """Streams live intake logs and metrics via Server-Sent Events."""
    state_db = current_app.config["STATE_DB"]

    def event_generator():
        last_stat_time = 0
        while True:
            # Yield stats heartbeat every 5 seconds
            now = time.time()
            if now - last_stat_time > 5:
                stats = state_db.get_stats()
                data = json.dumps({"type": "STATS_UPDATE", "stats": stats})
                yield f"data: {data}\n\n"
                last_stat_time = now
            time.sleep(2)

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )
