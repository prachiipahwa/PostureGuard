"""
config.py — Central configuration loader
=========================================
Reads from .env file or environment variables.
Copy .env.example to .env and fill in your Groq API key.

Groq is free — get a key at https://console.groq.com/
No billing setup required.
"""
import os
from pathlib import Path

# Load .env file if present
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
SECRET_KEY   = os.environ.get("SECRET_KEY", "postureguard-dev-secret-change-this")
PORT         = int(os.environ.get("PORT", 5000))
DEBUG        = os.environ.get("DEBUG", "false").lower() == "true"

# Groq model to use — llama-3.3-70b-versatile is fast, free, and excellent
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")

# Groq API endpoint (OpenAI-compatible)
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

def has_api_key() -> bool:
    return bool(GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"))
