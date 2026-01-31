from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()


class Settings(BaseModel):
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "meeting_chunks")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4o-mini")
    max_file_kb: int = int(os.getenv("MAX_FILE_KB", "500"))  # safety
    chunk_turns: int = int(os.getenv("CHUNK_TURNS", "8"))
    retrieve_top_k: int = int(os.getenv("RETRIEVE_TOP_K", "10"))


settings = Settings()
