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
    def apify_api_tokens(self) -> list[str]:
        """Returns ordered list of unique Apify API tokens available for failover."""
        tokens: list[str] = []
        # Primary
        primary = os.environ.get("APIFY_API_KEY") or os.environ.get("APIFY_API_TOKEN") or ""
        if primary.strip():
            tokens.append(primary.strip())
        # Backups 1..9
        for i in range(1, 10):
            val = (os.environ.get(f"APIFY_API_KEY_BACKUP_{i}") or os.environ.get(f"APIFY_BACKUP_KEY_{i}") or "").strip()
            if val and val not in tokens:
                tokens.append(val)
        # Comma-separated pool
        csv_pool = os.environ.get("APIFY_BACKUP_KEYS", "")
        if csv_pool:
            for item in csv_pool.split(","):
                clean = item.strip()
                if clean and clean not in tokens:
                    tokens.append(clean)
        return tokens

    @property
    def apify_api_token(self) -> str:
        tokens = self.apify_api_tokens
        return tokens[0] if tokens else ""

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
