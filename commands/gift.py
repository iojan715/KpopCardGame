import discord, random, string, asyncio, logging
from discord.ext import commands
from discord import app_commands
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import datetime, timezone
import uuid
from commands.starter import version

class GiftGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="gift", description="Comandos para el sistema de intercambio")

    @app_commands.command(name="card", description="Proponer un intercambio a otro jugador")
    @app_commands.describe(
        user="Jugador al que quieres regalar una carta",
        card="IDs de la carta para regalar",
        message="Mensaje opcional para el otro jugador"
    )
    async def gift_card(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        card: str,
        message: str = ""
    ):
        language = await get_user_language(interaction.user.id)
        user_id = interaction.user.id
        

        if user.id == interaction.user.id:
            return await interaction.response.send_message("## ❌ No te puedes regalar algo a ti mismo.", ephemeral=True)

        try:
            card_id, unique_id = card.split(".")
        except (AttributeError,ValueError):
            return await interaction.response.send_message(
                "## ⚠️ Formato de carta no valido.",
                ephemeral=True
            )

        pool = get_pool()
        async with pool.acquire() as conn:
            card_data = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1 AND user_id = $2", unique_id, user_id)
            card_type = "idol"
            if not card_data:
                card_type = "item"
                card_data = await conn.fetchrow("SELECT * FROM user_item_cards WHERE unique_id = $1 AND user_id = $2", unique_id, user_id)
                if not card_data:
                    return await interaction.response.send_message(
                        "## ❌ No tienes esta carta en tu inventario.",
                        ephemeral=True
                    )
            
            if card_data['status'] != 'available':
                return await interaction.response.send_message(
                    "## ❌ No se puede enviar esta carta porque no está disponible.",
                    ephemeral=True
                )

            if card_type == "idol":
                if card_data['is_locked']:
                    return await interaction.response.send_message(
                        content="## 🔐 No se puede enviar esta carta porque está bloqueada.",
                        ephemeral=True
                    )
            
                card_base = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1",card_data['card_id'])
            else:
                card_base = await conn.fetchrow("SELECT * FROM cards_item WHERE item_id = $1",card_data['item_id'])
            
            if not card_base:
                return await interaction.response.send_message(
                    "## ⚠️ Ha ocurrido un error al buscar los datos de la carta.",
                    ephemeral=True
                )
            
            agency_name = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1", user.id)
            if not agency_name:
                return await interaction.response.send_message(
                    f"{user.mention} no está registrado en el juego.",
                    ephemeral=True
                )
            
                
        view = discord.ui.View()
        view.add_item(ConfirmGiftButton(to_user=user, card=card_data, message=message))
        
        embed = discord.Embed(
            title=f"¿Estás seguro de enviar esta carta a `{agency_name}`?",
            description=f"**CEO:** {user.mention}\n**Costo de envío:** 💸{card_base['value']}",
            color=discord.Color.dark_blue()
        )
        if card_type == "idol":
            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_data['card_id']}.webp{version}"
            embed.set_image(url=image_url)
        else:
            embed.add_field(
                name=f"{card_base['name']} ⏳{card_data['durability']}",
                value=f"{card_data['item_id']}.{card_data['unique_id']}")
        
        await interaction.response.send_message(
            embed=embed,
            view=view,
            ephemeral=True
        )
        
        # --- /trade propose
class ConfirmGiftButton(discord.ui.Button):
    def __init__(self, to_user: discord.User, card, message:str):
        super().__init__(label="Confirmar", emoji="✅", style=discord.ButtonStyle.primary)
        self.to_user = to_user
        self.card = card
        self.message = message

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        

        async with pool.acquire() as conn:
            card_data = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1 AND user_id = $2", self.card['unique_id'], self.card['user_id'])
            card_type = "idol"
            if not card_data:
                card_data = await conn.fetchrow("SELECT * FROM user_item_cards WHERE unique_id = $1 AND user_id = $2", self.card['unique_id'], self.card['user_id'])
                card_type = "item"
            
            if card_data['status'] != 'available':
                return await interaction.response.send_message(
                    "## ❌ No se puede enviar esta carta porque no está disponible.",
                    ephemeral=True
                )

            if card_type == "idol":
                if card_data['is_locked']:
                    return await interaction.response.send_message(
                        content="## 🔐 No se puede enviar esta carta porque está bloqueada.",
                        ephemeral=True
                    )
            
                card_base = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1",card_data['card_id'])
            else:
                card_base = await conn.fetchrow("SELECT * FROM cards_item WHERE item_id = $1",card_data['item_id'])
            
            send_agency = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1", interaction.user.id)
            agency_name = await conn.fetchval("SELECT agency_name FROM users WHERE user_id = $1", self.to_user.id)
            
            xp = int(card_base['value']/100)
            await conn.execute("UPDATE users SET credits = credits - $1, xp = xp + $2 WHERE user_id = $3", card_base['value'], xp, interaction.user.id)
            
            now = datetime.now(timezone.utc)
            if card_type == "idol":
                await conn.execute("UPDATE user_idol_cards SET user_id = $1, date_obtained = $2 WHERE unique_id = $3", self.to_user.id, now, card_data['unique_id'])
            else:
                await conn.execute("UPDATE user_item_cards SET user_id = $1, date_obtained = $2 WHERE unique_id = $3", self.to_user.id, now, card_data['unique_id'])
            
            dm_message=""
            if self.message:
                dm_message = f"_{self.message}_"
            
            dm_embed = discord.Embed(
                title=f"🎁 ¡Has recibido una carta de `{send_agency}`!",
                description=f"**CEO:** {interaction.user.mention}\n\n{dm_message}",
                color=discord.Color.dark_blue()
            )
            embed = discord.Embed(
                title=f"✅ Carta enviada exitosamente a `{agency_name}`",
                description=f"**CEO:** {self.to_user.mention}",
                color=discord.Color.dark_blue()
            )
            logging.info(f"✅ Carta {card_data['card_id']}.{self.card['unique_id']} enviada exitosamente a `{agency_name}`")
            
            if card_type == "idol":
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_data['card_id']}.webp{version}"
                embed.set_image(url=image_url)
                embed.set_footer(text=f"{card_data['card_id']}.{card_data['unique_id']}")
                embed.add_field(name=f"XP obtenida: {xp}", value="")
                
                dm_embed.set_image(url=image_url)
                dm_embed.set_footer(text=f"{card_data['card_id']}.{card_data['unique_id']}")
            else:
                embed.add_field(
                    name=f"{card_base['name']} ⏳{card_data['durability']}",
                    value=f"{card_data['item_id']}.{card_data['unique_id']}")
                embed.set_footer(text=f"XP obtenida: {xp}")
                dm_embed.add_field(
                    name=f"{card_base['name']} ⏳{card_data['durability']}",
                    value=f"{card_data['item_id']}.{card_data['unique_id']}")
            
            dm_row = await conn.fetchrow(
                "SELECT notifications FROM users WHERE user_id = $1",
                self.to_user.id
            )
            if dm_row and dm_row["notifications"]:
                try:
                    dm_channel = await self.to_user.create_dm()
                    await dm_channel.send(embed=dm_embed)
                except discord.Forbidden:
                    # El usuario tiene los MD desactivados o bloqueó al bot
                    pass
        
        await interaction.response.edit_message(
            embed=embed,
            view=None
        )




async def setup(bot):
    bot.tree.add_command(GiftGroup())