"""
core/config.py
--------------
Configuration loader for ai-social-engine.
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    @property
    def apify_api_token(self) -> str:
        return os.environ.get("APIFY_API_KEY") or os.environ.get("APIFY_API_TOKEN") or ""

    @property
    def groq_api_key(self) -> str:
        return os.environ.get("GROQ_API_KEY") or ""

    @property
    def supabase_url(self) -> str:
        return os.environ.get("SUPABASE_URL") or ""

    @property
    def supabase_key(self) -> str:
        return os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY") or ""

    @property
    def openrouter_api_key(self) -> str:
        return os.environ.get("OPENROUTER_API_KEY") or ""

    @property
    def openrouter_model(self) -> str:
        return os.environ.get("OPENROUTER_MODEL") or "meta-llama/llama-3.3-70b-instruct"

    @property
    def huggingface_api_key(self) -> str:
        return os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN") or ""


config = Config()
