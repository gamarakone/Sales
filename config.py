import os
from dotenv import load_dotenv

load_dotenv()

APIFY_API_KEY = os.getenv("APIFY_API_KEY")
if not APIFY_API_KEY:
    raise EnvironmentError("APIFY_API_KEY is not set. Copy .env.example to .env and fill in your key.")

DB_PATH = os.getenv("DB_PATH", "leads.db")
