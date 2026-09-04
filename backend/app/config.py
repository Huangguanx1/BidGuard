from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_data_dir: Path = ROOT_DIR / "data"
    app_max_upload_mb: int = 20
    app_max_pages: int = 500
    app_max_text_chars: int = 2_000_000
    app_libreoffice_path: str = ""

    model_provider: str = "openai_compatible"
    model_base_url: str = ""
    model_api_key: str = ""
    model_name: str = ""

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def max_upload_bytes(self) -> int:
        return self.app_max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

