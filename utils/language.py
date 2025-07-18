from db.connection import get_pool

async def get_user_language(user_id: int) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT language FROM users WHERE user_id = $1", user_id)
        if row and row["language"]:
            return row["language"]
    return "en"  # idioma por defecto