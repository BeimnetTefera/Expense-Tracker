from pathlib import Path
import os

from dotenv import load_dotenv

# backend/ folder (this file is backend/app/config.py). Every relative path below
# is resolved from here, so it doesn't matter which folder you start the app from.
BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def _from_base(path: str) -> str:
    # "expenses.db" -> backend/expenses.db; absolute paths (e.g. a host's disk) stay as-is.
    p = Path(path)
    return str(p if p.is_absolute() else BASE_DIR / p)


DB_PATH = _from_base(os.getenv("DB_PATH", "expenses.db"))
LOG_DIR = Path(_from_base(os.getenv("LOG_DIR", "logs")))
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MAX_STEPS = int(os.getenv("MAX_STEPS", "5"))

# Websites allowed to call the API from a browser (CORS). Comma-separated in .env.
# Defaults = common local dev servers. Add your Vercel URL when you deploy.
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5500,http://127.0.0.1:5500,http://localhost:3000",
    ).split(",")
    if origin.strip()
]


if __name__ == "__main__":
    print(DB_PATH)
