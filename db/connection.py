import asyncpg
import ssl
from config import DATABASE_URL

# Pool global
db_pool = None

async def create_pool():
    global db_pool
    
    # Detectar si es enlace externo o interno
    # (generalmente los internos no llevan ".render.com", ".supabase.co", etc.)
    use_ssl = any(x in DATABASE_URL for x in ["render.com", "supabase.co", "neon.tech", "railway.app"])
    
    ssl_ctx = None
    if use_ssl:
        ssl_ctx = ssl.create_default_context()
    
    db_pool = await asyncpg.create_pool(DATABASE_URL, ssl=ssl_ctx)

def get_pool():
    return db_pool