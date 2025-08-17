import asyncpg
from config import DATABASE_URL

# Pool global
db_pool = None

# Crear el pool (una vez)
async def create_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)

# Obtener el pool desde otros archivos
def get_pool():
    return db_pool