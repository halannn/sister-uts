import os
from pydantic import BaseModel

# app settings
class Settings(BaseModel):
    dedup_db_path: str = os.getenv("DEDUP_DB_PATH", "data/dedup.db")

settings = Settings()
