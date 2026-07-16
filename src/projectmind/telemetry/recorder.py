import json

from ..core.db import Database
from ..core.models import TelemetryEvent


def record(db: Database, event: TelemetryEvent) -> dict:
    db.execute(
        "INSERT OR IGNORE INTO telemetry(event_id,action,ref,justification,status,payload,created_at) VALUES(?,?,?,?,?,?,?)",
        (
            event.event_id,
            event.action,
            event.ref,
            event.justification,
            event.status,
            json.dumps(event.payload, default=str),
            event.created_at.isoformat(),
        ),
    )
    return event.model_dump(mode="json")
