import os
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator

load_dotenv()


class Settings(BaseModel):
    """Application settings loaded from environment: OpenAI API key and model names, Qdrant URL and collection, file/chunk/retrieval limits, and prompt version.
    Why available: Single source of configuration so all modules use consistent limits and model names."""
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("QDRANT_COLLECTION", "meeting_chunks")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    chat_model: str = os.getenv("CHAT_MODEL", "gpt-4o-mini")
    max_file_kb: int = int(os.getenv("MAX_FILE_KB", "1024"))  # 1 MB max upload
    chunk_turns: int = int(os.getenv("CHUNK_TURNS", "8"))
    retrieve_top_k: int = int(os.getenv("RETRIEVE_TOP_K", "10"))
    prompt_version: str = os.getenv("PROMPT_VERSION", "v1")

   
    @field_validator("max_file_kb", "chunk_turns", "retrieve_top_k")
    @classmethod
    def must_be_positive(cls, v):
        """Ensure max_file_kb, chunk_turns, and retrieve_top_k are positive integers. Prevents invalid config from env."""
        if v <= 0:
            raise ValueError("must be > 0")
        return v


settings = Settings()
