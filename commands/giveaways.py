import discord, random, asyncio, string, json
from discord.ext import commands
from discord import app_commands
import csv
import os
from utils.localization import get_translation
from utils.language import get_user_language
from utils.emojis import get_emoji
from db.connection import get_pool
from datetime import timezone, datetime, timedelta
from commands.starter import version
from commands.starter import base, mult, reduct


# --- /giveaway
class GiveawaysGroup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="giveaway", description="Inicia un sorteo")
    @app_commands.describe(prize="ID de la carta a sortear", duration="Duración en horas")
    async def giveaway(self, interaction: discord.Interaction, prize: str, duration: int):
        try:
            c_id, u_id = prize.split(".")
        except Exception:
            return await interaction.response.send_message(content="## ❌ El ID ingresado no es válido.", ephemeral=True)
        pool = await get_pool()
        if duration == 0:
            duration = 1
        elif duration > 12:
            duration = 12

        async with pool.acquire() as conn:
            # buscar carta en inventario de usuario que lo inicia
            ucard_data = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1 AND user_id = $2", u_id, interaction.user.id)
            if not ucard_data:
                return await interaction.response.send_message(content="## ❌ Esta carta no se encuentra en tu inventario.", ephemeral=True)
            
            # generar ID y tiempo de finalización
            while True:
                giveaway_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
                exist_id = await conn.fetchval("SELECT 1 FROM giveaways WHERE giveaway_id = $1", giveaway_id)
                if not exist_id:
                    break
                
            end_time = datetime.now(timezone.utc) + timedelta(minutes=duration)

            embed = discord.Embed(
                title="🎉 Nuevo sorteo",
                description=f"**Premio:** {prize}\n\nPulsa el botón para participar.",
                color=discord.Color.gold()
            )
            embed.add_field(name="Host", value=interaction.user.mention)
            embed.add_field(name="Duración", value=f"{duration} minutos")
            embed.set_footer(text=f"{giveaway_id}")
            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{c_id}.webp{version}"
            embed.set_thumbnail(url=image_url)

            view = GiveawayButton(giveaway_id, pool)
            message = await interaction.channel.send(content="@everyone", embed=embed, view=view)
            
            await conn.execute("UPDATE user_idol_cards SET status = 'giveaway' WHERE unique_id = $1", u_id)

            # guardar en DB
            await conn.execute(
                """INSERT INTO giveaways (giveaway_id, guild_id, channel_id, message_id, host_id, card_id, end_time)
                   VALUES ($1,$2,$3,$4,$5,$6,$7)""",
                giveaway_id,
                interaction.guild.id,
                interaction.channel.id,
                message.id,
                interaction.user.id,
                u_id,
                end_time
            )

        await interaction.response.send_message("## ✅ Sorteo creado exitosamente.", ephemeral=True)

class GiveawayButton(discord.ui.View):
    def __init__(self, giveaway_id: str, pool):
        super().__init__(timeout=None)  # sin timeout para que siga activo después de reinicios
        self.giveaway_id = giveaway_id
        self.pool = pool

    @discord.ui.button(label="🎉 Participar", style=discord.ButtonStyle.primary, custom_id="giveaway:join")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        async with self.pool.acquire() as conn:
            # Verificar si ya está registrado
            exists = await conn.fetchrow(
                "SELECT 1 FROM giveaway_entries WHERE giveaway_id=$1 AND user_id=$2",
                self.giveaway_id, user_id
            )
            if exists:
                return await interaction.response.send_message(
                    "⚠️ Ya estás participando en este sorteo.", ephemeral=True
                )

            # Insertar nueva entrada
            await conn.execute(
                "INSERT INTO giveaway_entries (giveaway_id, user_id, winner) VALUES ($1, $2, FALSE)",
                self.giveaway_id, user_id
            )
            await interaction.response.send_message("✅ Te uniste al sorteo. ¡Mucha suerte! 🎉", ephemeral=True)








async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GiveawaysGroup(bot))
