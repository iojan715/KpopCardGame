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
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
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

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}"

        embed = discord.Embed(
            title="🎁 Canjear carta",
            description=f"Selecciona un redeemable para canjear **{card_id}**.",
            color=discord.Color.purple()
        )
        if not item_data:
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

    @redeem_card.autocomplete("card_id")
    async def redeem_card_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM cards_idol ORDER BY card_id ASC")
        return [
            app_commands.Choice(name=f"{row['card_id']}", value=row['card_id'])
            for row in rows if current.lower() in f"{row['card_id'].lower()}"
        ][:25]

    @app_commands.command(name="item", description="Canjea una carta idol o ítem usando un redeemable")
    @app_commands.describe(item="Item que deseas canjear")
    async def redeem_item(self, interaction: discord.Interaction, item: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        pool = get_pool()
        item_id = item
        user_id = interaction.user.id

        # Buscar si es idol card
        async with pool.acquire() as conn:
            
            item_data = await conn.fetchrow(
                "SELECT * FROM cards_item WHERE item_id = $1", item_id
            )
            if not item_data:
                return await interaction.response.send_message(content="❌ El ID ingresado no corresponde a ninguna carta o ítem.", ephemeral=True)

            is_idol_card = False


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

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{item_id}.webp{version}"

        embed = discord.Embed(
            title="🎁 Canjear carta",
            description=f"Selecciona un redeemable para canjear **{item_data['name']}**.",
            color=discord.Color.purple()
        )
        stats = [
            ("Vocal", item_data["plus_vocal"]),
            ("Rap", item_data["plus_rap"]),
            ("Dance", item_data["plus_dance"]),
            ("Visual", item_data["plus_visual"]),
            ("Energy", item_data["plus_energy"]),
        ]
        bonus_str = "\n".join(f"**{f'+{v}' if v > 0 else v}** {k}" for k, v in stats if v != 0)

        if bonus_str:
            embed.add_field(name="Bonos:", value=bonus_str, inline=False)

            
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
            view = RedeemableView(item_id, is_idol_card, matching)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @redeem_item.autocomplete("item")
    async def item_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT name, item_id FROM cards_item ORDER BY name ASC")
        return [
            app_commands.Choice(name=f"{row['name']}", value=row['item_id'])
            for row in rows if current.lower() in f"{row['name'].lower()}"
        ][:25]


    @app_commands.command(name="p_card", description="Canjea una Performance Card usando un redeemable")
    @app_commands.describe(card="Nombre de la carta que deseas canjear",)
    async def redeem_p_card(self, interaction: discord.Interaction, card:str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        pool = get_pool()
        user_id = interaction.user.id

        # Buscar si es idol card
        async with pool.acquire() as conn:
            card_data = await conn.fetchrow(
                "SELECT * FROM cards_performance WHERE name = $1", card
            )
            

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
        
        for r in redeemables:
            if r["effect"] == "p_card":
                matching.append({
                    "redeemable_id": r["redeemable_id"],
                    "name": r["name"],
                    "effect": r["effect"]
                })
        for ar in a_red:
            if ar["effect"] == "p_card":
                all_redeemables.append({
                    "redeemable_id": ar["redeemable_id"],
                    "name": ar["name"],
                    "effect": ar["effect"]
                })

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card}.webp{version}"

        embed = discord.Embed(
            title="🎁 Canjear carta",
            description=f"Selecciona un redeemable para canjear **{card}**.",
            color=discord.Color.purple()
        )
        #embed.set_thumbnail(url=image_url)
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
            view = PcardRedeemableView(card, matching)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @redeem_p_card.autocomplete("card")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT name FROM cards_performance ORDER BY name ASC")
        return [
            app_commands.Choice(name=f"{row['name']}", value=row['name'])
            for row in rows if current.lower() in f"{row['name'].lower()}"
        ][:25]

    @app_commands.command(name="skill_reroll", description="Regenera las habilidades de una carta idol")
    @app_commands.describe(card_id="ID de la carta (idol) que deseas regenerar habilidades")
    async def redeem_skill(self, interaction: discord.Interaction, card_id: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        pool = get_pool()

        try:
            c_id, u_id = card_id.split(".")
        except Exception:
            return await interaction.response.send_message(content="❌ El ID ingresado no es válido.", ephemeral=True)
        
        user_id = interaction.user.id

        # Buscar si es idol card
        async with pool.acquire() as conn:
            card_data = await conn.fetchrow(
                "SELECT * FROM user_idol_cards WHERE unique_id = $1", u_id
            )
            if not card_data:
                return await interaction.response.send_message(content="❌ El ID ingresado no corresponde a ninguna carta.", ephemeral=True)

            rarity = card_data["rarity_id"]
            effect_code = ""
            if rarity[0] in "R":
                effect_code += "REG"
            elif rarity in ["LMT","POB","FCR","SPC"]:
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
                "SELECT * FROM redeemables ORDER BY redeemable_id ASC")

        matching = []
        all_redeemables =[]
        for r in redeemables:
            if r["effect"] == "skills":
                matching.append({
                    "redeemable_id": r["redeemable_id"],
                    "name": r["name"],
                    "effect": r["effect"]
                })
        for ar in a_red:
            if ar["effect"] == "skills":
                all_redeemables.append({
                    "redeemable_id": ar["redeemable_id"],
                    "name": ar["name"],
                    "effect": ar["effect"]
                })


        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{c_id}.webp{version}"

        embed = discord.Embed(
            title="🎁 Regenerar habilidades",
            description=f"Selecciona un redeemable para regenerar las habilidades de **{c_id}.{u_id}**.",
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
            view = SkillRedeemableView(u_id, matching)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="upgrade", description="Sube de nivel una carta Regular (max. Lv. 3)")
    @app_commands.describe(card_id="ID de la carta (idol) que deseas mejorar")
    async def redeem_upgrade(self, interaction: discord.Interaction, card_id: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        pool = get_pool()

        try:
            c_id, u_id = card_id.split(".")
        except Exception:
            return await interaction.response.send_message(content="❌ El ID ingresado no es válido.", ephemeral=True)
        
        user_id = interaction.user.id

        # Buscar si es idol card
        async with pool.acquire() as conn:
            card_data = await conn.fetchrow(
                "SELECT * FROM user_idol_cards WHERE unique_id = $1", u_id
            )
            if not card_data:
                return await interaction.response.send_message(content="❌ El ID ingresado no corresponde a ninguna carta.", ephemeral=True)

            rarity = card_data["rarity_id"]
            if rarity[0] not in "R":
                return await interaction.response.send_message(content="❌ Solo se puede subir de nivel cartas Regulares.", ephemeral=True)
            
            if rarity[-1] in "3":
                return await interaction.response.send_message(content="❌ Esta carta es nivel 3 y no puede subir más.", ephemeral=True)

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
                "SELECT * FROM redeemables ORDER BY redeemable_id ASC")

        matching = []
        all_redeemables =[]
        for r in redeemables:
            if r["effect"] == "upgrade":
                matching.append({
                    "redeemable_id": r["redeemable_id"],
                    "name": r["name"],
                    "effect": r["effect"]
                })
        for ar in a_red:
            if ar["effect"] == "upgrade":
                all_redeemables.append({
                    "redeemable_id": ar["redeemable_id"],
                    "name": ar["name"],
                    "effect": ar["effect"]
                })


        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_data['card_id']}.webp{version}"

        embed = discord.Embed(
            title="🎁 Subir de nivel",
            description=f"Selecciona un redeemable para subir de nivel la carta **{card_data['card_id']}.{u_id}**.",
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
            view = UpgradeRedeemableView(u_id, matching)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


# - card idol/item
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

            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'redeem_coupon'
                """, interaction.user.id)
            
            # Insertar carta al inventario del usuario
            if self.is_idol_card:
                while True:
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    exists = await conn.fetchrow("SELECT 1 FROM user_idol_cards WHERE unique_id = $1", new_id)
                    if not exists:
                        break
                card = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", self.card_id)
                
                p_skill = a_skill = s_skill = u_skill = None
                # Asignar habilidades dependiendo rareza
                if card["rarity"] == "Regular":
                    tipo_habilidad = random.choice(["passive", "active", "support"])

                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                    """, tipo_habilidad)

                    if skill_row:
                        if tipo_habilidad == "passive":
                            p_skill = skill_row["skill_name"]
                        elif tipo_habilidad == "active":
                            a_skill = skill_row["skill_name"]
                        elif tipo_habilidad == "support":
                            s_skill = skill_row["skill_name"]
                            
                elif card["rarity"] == "Special":
                    available_types = ["passive", "active", "support"]
                    chosen_types = random.sample(available_types, 2)

                    for skill_type in chosen_types:
                        skill_row = await conn.fetchrow("""
                            SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                        """, skill_type)

                        if skill_row:
                            if skill_type == "passive":
                                p_skill = skill_row["skill_name"]
                            elif skill_type == "active":
                                a_skill = skill_row["skill_name"]
                            elif skill_type == "support":
                                s_skill = skill_row["skill_name"]
                            elif skill_type == "ultimate":
                                u_skill = skill_row["skill_name"]
                
                elif card["rarity"] == "Limited":
                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = 'ultimate' ORDER BY RANDOM() LIMIT 1
                    """)
                    if skill_row:
                        u_skill = skill_row["skill_name"]

                    extra_type = random.choice(["passive", "active", "support"])
                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                    """, extra_type)
                    if skill_row:
                        if extra_type == "passive":
                            p_skill = skill_row["skill_name"]
                        elif extra_type == "active":
                            a_skill = skill_row["skill_name"]
                        elif extra_type == "support":
                            s_skill = skill_row["skill_name"]
                            
                elif card["rarity"] == "FCR":
                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = 'support' ORDER BY RANDOM() LIMIT 1
                    """)
                    if skill_row:
                        s_skill = skill_row["skill_name"]

                    extra_type = random.choice(["passive", "active", "ultimate"])
                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                    """, extra_type)
                    if skill_row:
                        if extra_type == "passive":
                            p_skill = skill_row["skill_name"]
                        elif extra_type == "active":
                            a_skill = skill_row["skill_name"]
                        elif extra_type == "ultimate":
                            u_skill = skill_row["skill_name"]
                
                elif card["rarity"] == "POB":
                    available_types = ["passive", "active", "support", "ultimate"]
                    chosen_types = random.sample(available_types, 3)

                    for skill_type in chosen_types:
                        skill_row = await conn.fetchrow("""
                            SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                        """, skill_type)

                        if skill_row:
                            if skill_type == "passive":
                                p_skill = skill_row["skill_name"]
                            elif skill_type == "active":
                                a_skill = skill_row["skill_name"]
                            elif skill_type == "support":
                                s_skill = skill_row["skill_name"]
                            elif skill_type == "ultimate":
                                u_skill = skill_row["skill_name"]
                
                await conn.execute("""
                    INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id, p_skill, a_skill, s_skill, u_skill)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, new_id, user_id, card["card_id"], card["idol_id"], card["set_id"], card["rarity_id"], p_skill, a_skill, s_skill, u_skill)
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

# - pcard
class PcardRedeemableView(discord.ui.View):
    def __init__(self, card: str, redeemables: list[dict]):
        super().__init__(timeout=60)
        self.card = card

        for r in redeemables:
            button = PcardRedeemableButton(
                label=r["name"],
                redeemable_id=r["redeemable_id"],
                card=self.card
            )
            self.add_item(button)

class PcardRedeemableButton(discord.ui.Button):
    def __init__(self, label: str, redeemable_id: str, card: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.redeemable_id = redeemable_id
        self.card = card

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

            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'redeem_coupon'
                """, interaction.user.id)
            
            card_id = await conn.fetchval(
                "SELECT pcard_id FROM cards_performance WHERE name = $1",
                self.card
            )
            
            await conn.execute("""
                INSERT INTO user_performance_cards (user_id, pcard_id, quantity, last_updated)
                VALUES ($1, $2, 1, now())
                ON CONFLICT (user_id, pcard_id) DO UPDATE SET
                quantity = user_performance_cards.quantity + 1,
                last_updated = now()
                """, user_id, card_id)

        await interaction.response.edit_message(
            content=f"✅ ¡Has canjeado exitosamente la carta `{self.card}` usando el redeemable **{self.label}**!",
            embed=None,
            view=None
        )

# - skill reroll
class SkillRedeemableView(discord.ui.View):
    def __init__(self, unique_id: str, redeemables: list[dict]):
        super().__init__(timeout=60)
        self.unique_id = unique_id

        for r in redeemables:
            button = SkillRedeemableButton(
                label=r["name"],
                redeemable_id=r["redeemable_id"],
                unique_id=self.unique_id
            )
            self.add_item(button)

class SkillRedeemableButton(discord.ui.Button):
    def __init__(self, label: str, redeemable_id: str, unique_id: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.redeemable_id = redeemable_id
        self.unique_id = unique_id
        self.is_idol_card = True

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

            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'redeem_coupon'
                """, interaction.user.id)
            
            card_id = await conn.fetchval(
                "SELECT card_id FROM user_idol_cards WHERE unique_id = $1",
                self.unique_id)
            card = await conn.fetchrow(
                "SELECT * FROM cards_idol WHERE card_id = $1",
                card_id)
            
            
            await conn.execute("""UPDATE user_idol_cards
                               SET p_skill = NULL, a_skill = NULL,
                               s_skill = NULL, u_skill = NULL
                               WHERE unique_id = $1""", self.unique_id)
            
            p_skill = a_skill = s_skill = u_skill = None
            # Asignar habilidades dependiendo rareza
            if card["rarity"] == "Regular":
                tipo_habilidad = random.choice(["passive", "active", "support"])

                skill_row = await conn.fetchrow("""
                    SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                """, tipo_habilidad)

                if skill_row:
                    if tipo_habilidad == "passive":
                        p_skill = skill_row["skill_name"]
                    elif tipo_habilidad == "active":
                        a_skill = skill_row["skill_name"]
                    elif tipo_habilidad == "support":
                        s_skill = skill_row["skill_name"]
                        
            elif card["rarity"] == "Special":
                available_types = ["passive", "active", "support"]
                chosen_types = random.sample(available_types, 2)

                for skill_type in chosen_types:
                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                    """, skill_type)

                    if skill_row:
                        if skill_type == "passive":
                            p_skill = skill_row["skill_name"]
                        elif skill_type == "active":
                            a_skill = skill_row["skill_name"]
                        elif skill_type == "support":
                            s_skill = skill_row["skill_name"]
                        elif skill_type == "ultimate":
                            u_skill = skill_row["skill_name"]
            
            elif card["rarity"] == "Limited":
                skill_row = await conn.fetchrow("""
                    SELECT skill_name FROM skills WHERE skill_type = 'ultimate' ORDER BY RANDOM() LIMIT 1
                """)
                if skill_row:
                    u_skill = skill_row["skill_name"]

                extra_type = random.choice(["passive", "active", "support"])
                skill_row = await conn.fetchrow("""
                    SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                """, extra_type)
                if skill_row:
                    if extra_type == "passive":
                        p_skill = skill_row["skill_name"]
                    elif extra_type == "active":
                        a_skill = skill_row["skill_name"]
                    elif extra_type == "support":
                        s_skill = skill_row["skill_name"]
                        
            elif card["rarity"] == "FCR":
                skill_row = await conn.fetchrow("""
                    SELECT skill_name FROM skills WHERE skill_type = 'support' ORDER BY RANDOM() LIMIT 1
                """)
                if skill_row:
                    s_skill = skill_row["skill_name"]

                extra_type = random.choice(["passive", "active", "ultimate"])
                skill_row = await conn.fetchrow("""
                    SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                """, extra_type)
                if skill_row:
                    if extra_type == "passive":
                        p_skill = skill_row["skill_name"]
                    elif extra_type == "active":
                        a_skill = skill_row["skill_name"]
                    elif extra_type == "ultimate":
                        u_skill = skill_row["skill_name"]
            
            elif card["rarity"] == "POB":
                available_types = ["passive", "active", "support", "ultimate"]
                chosen_types = random.sample(available_types, 3)

                for skill_type in chosen_types:
                    skill_row = await conn.fetchrow("""
                        SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                    """, skill_type)

                    if skill_row:
                        if skill_type == "passive":
                            p_skill = skill_row["skill_name"]
                        elif skill_type == "active":
                            a_skill = skill_row["skill_name"]
                        elif skill_type == "support":
                            s_skill = skill_row["skill_name"]
                        elif skill_type == "ultimate":
                            u_skill = skill_row["skill_name"]
            
            await conn.execute("""UPDATE user_idol_cards
                               SET p_skill = $1, a_skill = $2,
                               s_skill = $3, u_skill = $4
                               WHERE unique_id = $5""",
                               p_skill, a_skill, s_skill, u_skill, self.unique_id)

        await interaction.response.edit_message(
            content=f"✅ ¡Se han generado exitosamente las nuevas habilidades de la carta `{card_id}.{self.unique_id}` usando el redeemable **{self.label}**!",
            embed=None,
            view=None
        )

# - upgrade
class UpgradeRedeemableView(discord.ui.View):
    def __init__(self, unique_id: str, redeemables: list[dict]):
        super().__init__(timeout=60)
        self.unique_id = unique_id

        for r in redeemables:
            button = UpgradeRedeemableButton(
                label=r["name"],
                redeemable_id=r["redeemable_id"],
                unique_id=self.unique_id
            )
            self.add_item(button)

class UpgradeRedeemableButton(discord.ui.Button):
    def __init__(self, label: str, redeemable_id: str, unique_id: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.redeemable_id = redeemable_id
        self.unique_id = unique_id
        self.is_idol_card = True

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

            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'redeem_coupon'
                """, interaction.user.id)
            
            card = await conn.fetchrow(
                "SELECT * FROM user_idol_cards WHERE unique_id = $1",
                self.unique_id)
            
            level = int(card['rarity_id'][-1])
            level += 1
            rarity = card['rarity_id'][0] + str(card['rarity_id'][1]) + str(level)
            
            card_id = card['idol_id'] + card['set_id'] + rarity
            
            await conn.execute(
                "UPDATE user_idol_cards SET card_id = $1, rarity_id = $2 WHERE unique_id = $3",
                card_id, rarity, self.unique_id
            )
            
            
            

        await interaction.response.edit_message(
            content=f"✅ ¡La carta `{card_id}.{self.unique_id}` ha subido de nivel exitosamente usando el redeemable **{self.label}**!",
            embed=None,
            view=None
        )


# Registro del grupo en el bot
async def setup(bot: commands.Bot):
    bot.tree.add_command(RedeemGroup())