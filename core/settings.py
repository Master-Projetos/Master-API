from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )
    
    API_VERSION : str = "0.2.0"
    DEBUG : bool
    
    SESSION_TTL_MINUTES: int = 20
    
    GEOGRID_USER: str
    GEOGRID_PASSWORD: str
    
@lru_cache
def get_settings():
    return Settings()