from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
    )

    API_VERSION: str = '0.3.1'
    DEBUG: bool
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    SESSION_TTL_MINUTES: int = 20

    GEOGRID_USER: str
    GEOGRID_PASSWORD: str

    DATABASE_URL: str


@lru_cache
def get_settings():
    return Settings()
