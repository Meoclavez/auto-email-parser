"""Server-Sent Events (SSE) live streaming route for real-time intake updates."""

import time
import json
from flask import Blueprint, Response, current_app
from src.web.auth import login_required

events_bp = Blueprint("events", __name__)


@events_bp.route("/api/events/stream", methods=["GET"])
@login_required
def sse_event_stream():
    """Streams live intake logs and metrics via Server-Sent Events with safe disconnect handling."""
    state_db = current_app.config["STATE_DB"]

    def event_generator():
        # Stream for up to 60 iterations (2 minutes) then close cleanly; browser EventSource auto-reconnects
        for _ in range(60):
            try:
                stats = state_db.get_stats()
                data = json.dumps({"type": "STATS_UPDATE", "stats": stats})
                yield f"data: {data}\n\n"
                time.sleep(2)
            except (GeneratorExit, StopIteration):
                break
            except Exception:
                break

    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
