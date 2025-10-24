from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field, field_validator

# event model
class Event(BaseModel):
    topic: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    timestamp: str
    source: str = Field(min_length=1)
    payload: dict[str, Any]

    @field_validator("timestamp")
    @classmethod
    def valid_iso8601(cls, v: str) -> str:
        # minimal ISO8601 check
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except Exception as e:
            raise ValueError(f"timestamp must be ISO8601: {e}")
        return v

# publish request model
class PublishRequest(BaseModel):
    events: list[Event]