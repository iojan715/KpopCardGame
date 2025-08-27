import discord, random, string
from datetime import timezone, datetime
from discord.ext import commands
from discord import app_commands
from utils.language import get_user_language
from utils.localization import get_translation
from db.connection import get_pool
from commands.starter import version

class ModGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="mod", description="Comandos para moderación")

    @app_commands.command(name="bug_reward", description="Entregar recompensa a un jugador por reporte de error")
    @app_commands.describe(
        user="Jugador que reportó el error",
        level="Nivel del error",
        tier="Grado del impacto dentro del nivel (1-3)",
        message ="Descripcion del error resuelto"
    )
    @app_commands.choices(
        level=[
            app_commands.Choice(name="🟢 Menor", value="minor"),
            app_commands.Choice(name="🟡 Moderado", value="moderate"),
            app_commands.Choice(name="🔴 Importante", value="important"),
            app_commands.Choice(name="🔥 Crítico", value="critical"),
        ],
        tier=[
            app_commands.Choice(name="Tier 1", value=1),
            app_commands.Choice(name="Tier 2", value=2),
            app_commands.Choice(name="Tier 3", value=3),
        ]
    )
    async def bug_reward(self, interaction: discord.Interaction, user: discord.User, level: app_commands.Choice[str], tier: app_commands.Choice[int], message:str):
        language = await get_user_language(interaction.user.id)

        # Créditos base por nivel
        base_credits = {
            "minor": 1000,
            "moderate": 3000,
            "important": 6000,
            "critical": 10000
        }
        
        credit_mult = {
            "minor": 1,
            "moderate": 2,
            "important": 3,
            "critical": 5
        }
        
        packs = {
            "minor": "GFT",
            "moderate": "SPP",
            "important": "HLV",
            "critical": "STR"
        }
        packs_names = {
            "minor": "Gift Pack",
            "moderate": "Support Pack",
            "important": "High Level Pack",
            "critical": "Star Pack"
        }
        
        redeemables = {
            "minor": "DISCN",
            "moderate": "RECRT",
            "important": "TCONT",
            "critical": "CONTR"
        }
        redeemables_names = {
            "minor": "Discount",
            "moderate": "Recruitment",
            "important": "Tactical Contract",
            "critical": "Contract"
        }

        # Bonus por tier
        tier_bonus = {
            1: 0,
            2: 1000,
            3: 2000
        }
        pack_id = packs[level.value]
        reward_credits = base_credits[level.value] + tier_bonus[tier.value] * credit_mult[level.value]

        redeemable_id = redeemables[level.value]
        
        now = datetime.now(timezone.utc)
        
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO reported_bugs
                (user_id, report_date, level, tier, message, resolved_by)
                VALUES ($1, $2, $3, $4, $5, $6)""",
                user.id, now, level.value, tier.value, message, interaction.user.id
            )
            
            await conn.execute(
                "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                reward_credits, user.id
            )
            
            while True:
                new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                exists = await conn.fetchval("SELECT 1 FROM players_packs WHERE unique_id = $1", new_id)
                if not exists:
                    break
            await conn.execute(
                """
                INSERT INTO players_packs (pack_id, unique_id, user_id, buy_date)
                VALUES ($1, $2, $3, $4)""",
                pack_id, new_id, user.id, now 
            )
            
            await conn.execute("""
                INSERT INTO user_redeemables (user_id, redeemable_id, quantity)
                VALUES ($1, $2, 1)
                ON CONFLICT (user_id, redeemable_id)
                DO UPDATE SET quantity = user_redeemables.quantity + 1
            """, user.id, redeemable_id)
            
            

        embed = discord.Embed(
            title="🎁 Recompensa por reporte de error",
            description=f"**Arreglado:** _{message}_",
            color=discord.Color.orange()
        )
        embed.add_field(name="💵 Dinero otorgado", value=f"{reward_credits:,}", inline=False)
        embed.add_field(name="📦 Pack entregado", value=packs_names[level.value], inline=True)
        embed.add_field(name="🎫 Cupón recibido", value=redeemables_names[level.value], inline=True)
        embed.set_footer(text="¡Tu ayuda mejora el juego para todos!")

        await interaction.response.send_message(
            content=f"## Gracias a {user.mention} por reportar un error de nivel **{level.name}**:",
            embed=embed, ephemeral=False)

    @app_commands.command(name="give_idol_card", description="Entregar manualmente una carta de idol a un jugador")
    @app_commands.describe(
        user="Usuario que recibirá la carta",
        card_id="ID base de la carta a entregar"
    )
    async def give_idol_card(self, interaction: discord.Interaction, user: discord.User, card_id: str):
        pool = get_pool()

        async with pool.acquire() as conn:
            
            card_row = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", card_id)
            if not card_row:
                await interaction.response.send_message(f"❌ La carta `{card_id}` no existe.", ephemeral=True)
                return
            
            unique_id = ""
            while True:
                caracteres = string.ascii_lowercase + string.digits
                new_id = ''.join(random.choice(caracteres) for _ in range(5))
                
                row = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", new_id)
                if not row:
                    unique_id = new_id
                    break
            idol_id = card_row['idol_id']
            set_id = card_row['set_id']
            rarity_id = card_row['rarity_id']
            
            p_skill = a_skill = s_skill = u_skill = None
            
            # Asignar habilidades dependiendo rareza
            if card_row["rarity"] == "Regular":
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
                        
            elif card_row["rarity"] == "Special":
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
            
            elif card_row["rarity"] == "Limited":
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
                        
            elif card_row["rarity"] == "FCR":
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
            
            elif card_row["rarity"] == "POB":
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
            
            values = (unique_id,
                    user.id,
                    card_id,
                    idol_id,
                    set_id,
                    rarity_id,
                    p_skill,
                    a_skill,
                    s_skill,
                    u_skill
                )
            

            await conn.execute("""
                INSERT INTO user_idol_cards (
                    unique_id,
                    user_id,
                    card_id,
                    idol_id,
                    set_id,
                    rarity_id,
                    p_skill,
                    a_skill,
                    s_skill,
                    u_skill
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10);
            """, *values)

        await interaction.response.send_message(f"✅ Se entregó {card_id} a {user.mention}.", ephemeral=False)



    @app_commands.command(name="give_pack", description="Entregar manualmente un pack a un jugador")
    @app_commands.describe(
        agency="Usuario que recibirá el pack",
        pack_id="ID del tipo de pack a entregar",
        idol_id="Idol para el que se limita el pack (opcional)",
        group_name="Grupo para el que se limita el pack (opcional)",
        set_id="Set para el que se limita el pack (opcional)",
        theme="Tema para el que se limita el pack (opcional)"
    )
    async def give_pack(
        self,
        interaction: discord.Interaction,
        agency: str,
        pack_id: str,
        idol_id: str = None,
        group_name: str = None,
        set_id: str = None,
        theme: str = None
    ):
        pool = get_pool()
        
        
        
        async with pool.acquire() as conn:
            agency_r = await conn.fetchrow("SELECT user_id FROM users WHERE agency_name = $1", agency)
            user = await interaction.client.fetch_user(agency_r["user_id"])

            pack_row = await conn.fetchrow("SELECT * FROM packs WHERE pack_id = $1", pack_id)
            if not pack_row:
                await interaction.response.send_message(f"❌ El pack `{pack_id}` no existe.", ephemeral=True)
                return

            unique_id = ""
            while True:
                new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                row = await conn.fetchrow("SELECT 1 FROM players_packs WHERE unique_id = $1", new_id)
                if not row:
                    unique_id = new_id
                    break

            values = (
                unique_id,
                user.id,
                pack_id,
                datetime.now(timezone.utc),
                idol_id,
                group_name,
                set_id,
                theme
            )

            pack_name = pack_row["name"]
            
            await conn.execute("""
                INSERT INTO players_packs (
                    unique_id,
                    user_id,
                    pack_id,
                    buy_date,
                    idol_id,
                    group_name,
                    set_id,
                    theme
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8);
            """, *values)

        await interaction.response.send_message(f"✅ Se entregó **{pack_name}** a la Agencia *{agency}*\n> Dirigida por: {user.mention}.", ephemeral=False)

    @give_pack.autocomplete("agency")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name, user_id FROM users")
        return [
            app_commands.Choice(name=row["agency_name"], value=row["agency_name"])
            for row in rows if current.lower() in row["agency_name"].lower()
        ][:25]

    @give_pack.autocomplete("pack_id")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT pack_id, name FROM packs ORDER BY name ASC")
        return [
            app_commands.Choice(name=row["name"], value=row["pack_id"])
            for row in rows if current.lower() in row["name"].lower()
        ][:25]

    @give_pack.autocomplete("set_id")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT set_id, set_name FROM cards_idol ORDER BY set_name ASC")
        return [
            app_commands.Choice(name=row["set_name"], value=row["set_id"])
            for row in rows if current.lower() in row["set_name"].lower()
        ][:25]

    @give_pack.autocomplete("group_name")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM cards_idol ORDER BY group_name ASC")
        return [
            app_commands.Choice(name=row["group_name"], value=row["group_name"])
            for row in rows if current.lower() in row["group_name"].lower()
        ][:25]   
    

    @app_commands.command(name="birthday", description="Entregar recompensa a un jugador por su cumpleaños")
    @app_commands.describe(
        user="Jugador",
        card_id="Id de carta a otorgar"
    )
    async def birthday(self, interaction: discord.Interaction, user: discord.User, card_id: str):
        language = await get_user_language(interaction.user.id)
        
        now = datetime.now(timezone.utc)
        pool = get_pool()
        year = now.year
        
        async with pool.acquire() as conn:
            card_row = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", card_id)
            if not card_row:
                await interaction.response.send_message(f"❌ La carta `{card_id}` no existe.", ephemeral=True)
                return
            
            unique_id = ""
            while True:
                caracteres = string.ascii_lowercase + string.digits
                new_id = ''.join(random.choice(caracteres) for _ in range(5))
                
                row = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", new_id)
                if not row:
                    unique_id = new_id
                    break
            idol_id = card_row['idol_id']
            set_id = card_row['set_id']
            rarity_id = card_row['rarity_id']
            
            p_skill = a_skill = s_skill = u_skill = None
            
            # Asignar habilidades dependiendo rareza
            if card_row["rarity"] == "Regular":
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
                        
            elif card_row["rarity"] == "Special":
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
            
            elif card_row["rarity"] == "Limited":
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
                        
            elif card_row["rarity"] == "FCR":
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
            
            elif card_row["rarity"] == "POB":
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
            
            values = (unique_id,
                    user.id,
                    card_id,
                    idol_id,
                    set_id,
                    rarity_id,
                    p_skill,
                    a_skill,
                    s_skill,
                    u_skill
                )
            

            await conn.execute("""
                INSERT INTO user_idol_cards (
                    unique_id,
                    user_id,
                    card_id,
                    idol_id,
                    set_id,
                    rarity_id,
                    p_skill,
                    a_skill,
                    s_skill,
                    u_skill
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, *values)
            
            await conn.execute("""
                INSERT INTO user_badges (
                    user_id,
                    badge_id,
                    date_obtained
                    ) VALUES ($1, $2, $3)""",
                user.id, f"BDGBRTH{year}", now)
            
            await conn.execute(
                "UPDATE users SET credits = credits + 10000 WHERE user_id = $1",
                user.id)
            
            await conn.execute("""
                INSERT INTO user_redeemables (user_id, redeemable_id, quantity, last_updated)
                VALUES ($1, $2, 1, now())
                ON CONFLICT (user_id, redeemable_id) DO UPDATE SET
                quantity = user_redeemables.quantity + 1,
                last_updated = now()
            """, user.id, "UPGRD")

        embed = discord.Embed(
            title="🎁 Te hemos dejado un regalito:",
            description=f"Carta _{card_row['rarity']}_ de: {card_row['idol_name']} del set `{card_row['set_name']}`",
            color=discord.Color.blue()
        )
        embed.add_field(name="💵 Dinero otorgado", value=format(10000,','), inline=False)
        embed.add_field(name="🎫 Cupón recibido", value=f"Upgrade Card", inline=True)
        embed.set_footer(text="¡Que la pases muy bien en este día!")

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}"
        embed.set_image(url=image_url)
        
        await interaction.response.send_message(
            content=f"## 🎉🎊 Muchas felicidades a {user.mention} por su cumpleaños 🎊🎉",
            embed=embed, ephemeral=False)

    @birthday.autocomplete("card_id")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT card_id FROM cards_idol ORDER BY card_id ASC")
        return [
            app_commands.Choice(name=row["card_id"], value=row["card_id"])
            for row in rows if current.lower() in row["card_id"].lower()
        ][:25]   



async def setup(bot):
    bot.tree.add_command(ModGroup())