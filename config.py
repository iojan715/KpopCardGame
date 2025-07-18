import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env (solo en local)
load_dotenv()

# Esto funcionará en Render porque usa variables de entorno del sistema
TOKEN = os.getenv("DISCORD_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise ValueError("⚠️ No se encontró el DISCORD_TOKEN.")