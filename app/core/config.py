from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME: str = "Financial Rag"
    API_V1_STR: str = "/api/v1"

    DEEPSEEK_API_KEY: str = "sk-25b729f6dc8547c79113ad4719eee2ea"
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEFAULT_LLM_PROVIDER: str = "deepseek"

    OLLAMA_BASE_URL: str = "https://localhost:11434"
    OLLAMA_MODEL:str="qwen2:7b"

    #数据库配置
    POSTGRES_URL: str = "postgresql://admin:adminpassword@localhost:5432/financial_rag"
    REDIS_URL: str = "redis://localhost:6379/0"  # ✅ 加上 : str
    QDRANT_URL:str="http://localhost:6333"
    NEO4J_URL:str="bolt://localhost:7687"
    NEo4J_USER:str="neo4j"
    NEO4j_PASSWORD:str="adminpassword"

    model_config=SettingsConfigDict(env_file=".env",env_file_encoding="utf-8",extra="ignore")

settings=Settings()

