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
class GiveawaysGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="giveaway", description="Inicia un sorteo")

    @app_commands.command(name="card", description="Sortea una carta idol")
    @app_commands.describe(prize="ID de la carta a sortear", duration="Duración en horas")
    async def giveaway_card(self, interaction: discord.Interaction, prize: str, duration: int):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        try:
            c_id, u_id = prize.split(".")
        except Exception:
            return await interaction.response.send_message(content="## ❌ El ID ingresado no es válido.", ephemeral=True)
        pool = await get_pool()
        if duration == 0:
            duration = 1
        elif duration > 72:
            duration = 72

        async with pool.acquire() as conn:
            # buscar carta en inventario de usuario que lo inicia
            ucard_data = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1 AND user_id = $2", u_id, interaction.user.id)
            if not ucard_data:
                return await interaction.response.send_message(content="## ❌ Esta carta no se encuentra en tu inventario.", ephemeral=True)
            
            if ucard_data['status'] != 'available':
                return await interaction.response.send_message(content="## ❌ Esta carta no está disponible para ser enviada.", ephemeral=True)
            
            # generar ID y tiempo de finalización
            while True:
                giveaway_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
                exist_id = await conn.fetchval("SELECT 1 FROM giveaways WHERE giveaway_id = $1", giveaway_id)
                if not exist_id:
                    break
                
            end_time = datetime.now(timezone.utc) + timedelta(hours=duration)
            
            embed = discord.Embed(
                title="🎉 Nuevo sorteo",
                description=f"",
                color=discord.Color.gold()
            )
            embed.add_field(name=f"**Premio:**", value=prize, inline=False)
            embed.add_field(name="Host", value=interaction.user.mention, inline=False)
            embed.add_field(name="Finalización", value=f"<t:{int(end_time.timestamp())}:f> (±5 min)", inline=False)
            embed.set_footer(text=f"Pulsa el botón para participar\nID: {giveaway_id}")
            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{c_id}.webp{version}"
            embed.set_thumbnail(url=image_url)

            view = GiveawayButton(giveaway_id, pool)
            message = await interaction.channel.send(content="@CEO", embed=embed, view=view)
            
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

    @app_commands.command(name="item", description="Sortea un objeto")
    @app_commands.describe(prize="ID del objeto a sortear", duration="Duración en horas")
    async def giveaway_item(self, interaction: discord.Interaction, prize: str, duration: int):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        try:
            c_id, u_id = prize.split(".")
        except Exception:
            return await interaction.response.send_message(content="## ❌ El ID ingresado no es válido.", ephemeral=True)
        pool = await get_pool()
        if duration == 0:
            duration = 1
        elif duration > 72:
            duration = 72

        async with pool.acquire() as conn:
            # buscar carta en inventario de usuario que lo inicia
            ucard_data = await conn.fetchrow("SELECT * FROM user_item_cards WHERE unique_id = $1 AND user_id = $2", u_id, interaction.user.id)
            if not ucard_data:
                return await interaction.response.send_message(content="## ❌ Esta carta no se encuentra en tu inventario.", ephemeral=True)
            
            if ucard_data['status'] != 'available':
                return await interaction.response.send_message(content="## ❌ Esta carta no está disponible para ser enviada.", ephemeral=True)
            
            # generar ID y tiempo de finalización
            while True:
                giveaway_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
                exist_id = await conn.fetchval("SELECT 1 FROM giveaways WHERE giveaway_id = $1", giveaway_id)
                if not exist_id:
                    break
                
            end_time = datetime.now(timezone.utc) + timedelta(hours=duration)
            item_name = await conn.fetchval("SELECT name FROM cards_item WHERE item_id = $1", ucard_data['item_id'])
            
            embed = discord.Embed(
                title="🎉 Nuevo sorteo",
                description=f"",
                color=discord.Color.gold()
            )
            embed.add_field(name=f"**Premio: {item_name}**", value=prize, inline=False)
            embed.add_field(name="Host", value=interaction.user.mention, inline=False)
            embed.add_field(name="Finalización", value=f"<t:{int(end_time.timestamp())}:f> (±5 min)", inline=False)
            embed.set_footer(text=f"Pulsa el botón para participar\nID: {giveaway_id}")
            #image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{c_id}.webp{version}"
            #embed.set_thumbnail(url=image_url)

            view = GiveawayButton(giveaway_id, pool)
            message = await interaction.channel.send(content="@CEO", embed=embed, view=view)
            
            await conn.execute("UPDATE user_item_cards SET status = 'giveaway' WHERE unique_id = $1", u_id)

            # guardar en DB
            await conn.execute(
                """INSERT INTO giveaways (giveaway_id, guild_id, channel_id, message_id, host_id, card_id, end_time, type)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                giveaway_id,
                interaction.guild.id,
                interaction.channel.id,
                message.id,
                interaction.user.id,
                u_id,
                end_time,
                'item'
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
            registered = await conn.fetchrow("SELECT 1 FROM users WHERE user_id = $1", user_id)
            if not registered:
                return await interaction.response.send_message(
                        "❌ No estas registrado aún. Usa `/start` para crear tu agencia.", ephemeral=True
                    )
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








async def setup(bot):
    bot.tree.add_command(GiveawaysGroup())
