from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )
    
    API_VERSION : str = "0.0.1"
    DEBUG : bool
    
    GEOGRID_USER: str
    GEOGRID_PASSWORD: str
    GEOGRID_API_KEY: str
    
@lru_cache
def get_settings():
    return Settings()