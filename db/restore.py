from commands.giveaways import GiveawayButton
from db.connection import get_pool
import logging

async def restore_giveaways(bot):
    pool = await get_pool()
    async with pool.acquire() as conn:
        active_giveaways = await conn.fetch(
            "SELECT giveaway_id, channel_id, message_id FROM giveaways WHERE active=TRUE"
        )
    if not active_giveaways:
        return

    for g in active_giveaways:
        giveaway_id = g["giveaway_id"]
        message_id = g["message_id"]

        view = GiveawayButton(giveaway_id, pool)
        try:
            bot.add_view(view, message_id=message_id)
            logging.info(f"✅ View restaurada para sorteo {giveaway_id} (msg {message_id})")
        except Exception as e:
            logging.error(f"❌ No se pudo restaurar sorteo {giveaway_id}: {e}")