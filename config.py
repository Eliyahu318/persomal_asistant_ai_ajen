from pydantic_settings import BaseSettings
from pydantic import Field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):
    # --- API keys ---
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    twilio_account_sid: str | None = Field(None, env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str | None = Field(None, env="TWILIO_AUTH_TOKEN")

    # --- Paths ---
    data_dir: Path = BASE_DIR / "data"
    todo_template: str = "todo_list_{name}.json"
    chat_template: str = "chat_log_{name}.json"
    log_todo_template: str = "deleted_tasks_{name}.jsonl"
    log_chat_file: str = "deleted_messages_{name}.jsonl"

    # --- Bot params ---
    gpt_model: str = "gpt-4o"
    temperature: float = 0.3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
