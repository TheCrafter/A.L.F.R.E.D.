import uuid
from datetime import datetime, timezone

from pydantic import BaseModel


def new_id() -> str:
    return f"brain-{uuid.uuid4()}"


def now_ts() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def dump(model: BaseModel) -> dict:
    # mode="json" so enums/datetimes become JSON-native; exclude_none so optional
    # fields are omitted (the schema forbids null).
    return model.model_dump(mode="json", exclude_none=True)
