import discord, random, asyncio, string
from discord.ext import commands
from discord import app_commands
import csv
import os
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import datetime
from utils.paginator import Paginator
from collections import Counter, defaultdict
from commands.starter import version as v

version = v

class RedeemGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="redeem", description="Canjea cartas o ítems usando tus redeemables")

    @app_commands.command(name="card", description="Canjea una carta idol o ítem usando un redeemable")
    @app_commands.describe(card_id="ID de la carta (idol o ítem) que deseas canjear")
    async def redeem_card(self, interaction: discord.Interaction, card_id: str):
        pool = get_pool()

        # Validación de ID
        if not (len(card_id) == 10 or (len(card_id) == 6 and card_id[:3].isalpha())):
            return await interaction.response.send_message(content="❌ El ID ingresado no es válido.", ephemeral=True)

        user_id = interaction.user.id

        # Buscar si es idol card
        async with pool.acquire() as conn:
            card_data = await conn.fetchrow(
                "SELECT * FROM cards_idol WHERE card_id = $1", card_id
            )
            item_data = None
            if not card_data:
                item_data = await conn.fetchrow(
                    "SELECT * FROM cards_item WHERE item_id = $1", card_id
                )
                if not item_data:
                    return await interaction.response.send_message(content="❌ El ID ingresado no corresponde a ninguna carta o ítem.", ephemeral=True)

            is_idol_card = card_data is not None
            rarity = card_data["rarity_id"] if is_idol_card else item_data["item_id"][:3]
            print(rarity)
            effect_code = ""
            if rarity[0] in "R":
                effect_code += "R"
                if rarity[-1] == "1":
                    effect_code += "G1"
            elif rarity in ["LMT","POB","FCR","ACC", "CON", "MIC", "FIT", "SPC"]:
                effect_code = rarity

            # Buscar redeemables disponibles del usuario
            redeemables = await conn.fetch("""
                SELECT r.redeemable_id, r.name, r.effect
                FROM user_redeemables ur
                JOIN redeemables r ON r.redeemable_id = ur.redeemable_id
                WHERE ur.user_id = $1
                AND ur.quantity > 0
                ORDER BY r.redeemable_id ASC
            """, user_id)
            
            a_red = await conn.fetch(
                "SELECT * FROM redeemables ORDER BY redeemable_id ASC"
            )

        matching = []
        all_redeemables =[]
        if is_idol_card:
            for r in redeemables:
                if r["effect"] == "ALL" or r["effect"] == effect_code:
                    matching.append({
                        "redeemable_id": r["redeemable_id"],
                        "name": r["name"],
                        "effect": r["effect"]
                    })
            for ar in a_red:
                if ar["effect"] == "ALL" or ar["effect"] == effect_code:
                    all_redeemables.append({
                        "redeemable_id": ar["redeemable_id"],
                        "name": ar["name"],
                        "effect": ar["effect"]
                    })
        else:
            for r in redeemables:
                if r["effect"] == "item":
                    matching.append({
                        "redeemable_id": r["redeemable_id"],
                        "name": r["name"],
                        "effect": r["effect"]
                    })
            for ar in a_red:
                if ar["effect"] == "item":
                    all_redeemables.append({
                        "redeemable_id": ar["redeemable_id"],
                        "name": ar["name"],
                        "effect": ar["effect"]
                    })

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp"

        embed = discord.Embed(
            title="🎁 Canjear carta",
            description=f"Selecciona un redeemable para canjear **{card_id}**.",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=image_url)
        for r in all_redeemables:
            cantidad=0
            for m in matching:
                if r['redeemable_id'] == m['redeemable_id']:
                    async with pool.acquire() as conn:
                        q = await conn.fetchrow("""
                            SELECT quantity FROM user_redeemables
                            WHERE user_id = $1 AND redeemable_id = $2
                        """, user_id, m["redeemable_id"])
                        if q:
                            cantidad = q['quantity']
            embed.add_field(name=r["name"], value=f"Tienes: **{cantidad}**", inline=True)
        view=discord.ui.View()
        if matching:
            view = RedeemableView(card_id, is_idol_card, matching)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class RedeemableView(discord.ui.View):
    def __init__(self, card_id: str, is_idol_card: bool, redeemables: list[dict]):
        super().__init__(timeout=60)
        self.card_id = card_id
        self.is_idol_card = is_idol_card

        for r in redeemables:
            button = RedeemableButton(
                label=r["name"],
                redeemable_id=r["redeemable_id"],
                card_id=self.card_id,
                is_idol_card=self.is_idol_card
            )
            self.add_item(button)

class RedeemableButton(discord.ui.Button):
    def __init__(self, label: str, redeemable_id: str, card_id: str, is_idol_card: bool):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.redeemable_id = redeemable_id
        self.card_id = card_id
        self.is_idol_card = is_idol_card

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id

        # Verificar si el usuario aún tiene ese redeemable
        async with pool.acquire() as conn:
            row = await conn.execute(
                "UPDATE user_redeemables SET quantity = quantity - 1 WHERE user_id = $1 AND redeemable_id = $2 AND quantity > 0 ",
                user_id, self.redeemable_id)

            if row == "UPDATE 0":
                return await interaction.response.edit_message(content="❌ Ya no tienes este redeemable disponible.", embed=None, view=None)

            # Insertar carta al inventario del usuario
            if self.is_idol_card:
                while True:
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    exists = await conn.fetchrow("SELECT 1 FROM user_idol_cards WHERE unique_id = $1", new_id)
                    if not exists:
                        break
                card = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", self.card_id)
                await conn.execute("""
                    INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id)
                        VALUES ($1, $2, $3, $4, $5, $6)
                    """, new_id, user_id, card["card_id"], card["idol_id"], card["set_id"], card["rarity_id"])
            else:
                while True:
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    exists = await conn.fetchrow("SELECT 1 FROM user_item_cards WHERE unique_id = $1", new_id)
                    if not exists:
                        break
                card = await conn.fetchrow("SELECT * FROM cards_item WHERE item_id = $1", self.card_id)
                await conn.execute("""
                        INSERT INTO user_item_cards (unique_id, user_id, item_id, durability)
                        VALUES ($1, $2, $3, $4)
                    """, new_id, user_id, card["item_id"], card["max_durability"])

        await interaction.response.edit_message(
            content=f"✅ ¡Has canjeado exitosamente la carta `{self.card_id}` usando el redeemable **{self.label}**!",
            embed=None,
            view=None
        )

# Registro del grupo en el bot
async def setup(bot: commands.Bot):
    bot.tree.add_command(RedeemGroup())