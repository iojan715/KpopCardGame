import discord, asyncio, random, string
from discord.ext import commands
from discord import app_commands
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from datetime import timezone, datetime
from utils.paginator import Paginator, PreviousButton, NextButton
from commands.starter import version as v

version = v

class PacksGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="packs", description="Comandos relacionados con sobres de cartas")


    @app_commands.command(name="fcr", description="Recibe tu pack semanal de tipo FCR")
    @app_commands.describe(group="El grupo que deseas asignar al pack")
    async def fcr(self, interaction: discord.Interaction, group: str):
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()

        async with pool.acquire() as conn:
            user_data = await conn.fetchrow("SELECT can_fcr, agency_name FROM users WHERE user_id = $1", user_id)
            if not user_data or not user_data["can_fcr"]:
                await interaction.response.send_message("❌ Ya reclamaste tu pack FCR semanal o no estás autorizado para ello.", ephemeral=True)
                return

            pack_data = await conn.fetchrow("SELECT * FROM packs WHERE pack_id = 'FCR'")
            if not pack_data:
                await interaction.response.send_message("❌ No se encontró el pack FCR.", ephemeral=True)
                return

            embed = discord.Embed(
                title="🎁 Pack FCR - Confirmar entrega",
                description=f"🎴 Cartas: {pack_data['card_amount']}",
                color=discord.Color.teal()
            )
            embed.add_field(name="Grupo elegido", value=group, inline=True)
            if pack_data['set_id']:
                set_data = await conn.fetchrow("SELECT DISTINCT set_name FROM cards_idol WHERE set_id = $1", pack_data['set_id'])
                embed.add_field(name="Set", value=set_data['set_name'], inline=True)

            embed.set_footer(text=f"Agencia: {user_data['agency_name']}")
            
            view = ConfirmFCRView(user_id, group, pack_data)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @fcr.autocomplete("group")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM cards_idol WHERE rarity_id = 'FCR' ORDER BY group_name ASC")
        return [
            app_commands.Choice(name=row["group_name"], value=row["group_name"])
            for row in rows if current.lower() in row["group_name"].lower()
        ][:25]   


    @app_commands.command(name="open", description="Abrir uno de tus packs disponibles")
    async def open_pack(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pool = await get_pool()

        async with pool.acquire() as conn:
            # Obtener todos los packs del usuario con info del pack
            player_packs = await conn.fetch("""
                SELECT pp.*, p.name, p.card_amount 
                FROM players_packs pp
                JOIN packs p ON pp.pack_id = p.pack_id
                WHERE pp.user_id = $1
                ORDER BY pp.buy_date ASC
            """, user_id)

        if not player_packs:
            await interaction.response.send_message("No tienes packs disponibles para abrir.", ephemeral=True)
            return

        embeds = []
        pack_ids = []  # Lista de unique_ids por embed (1:1 con embeds)

        for pack in player_packs:
            desc = f"**Cartas:** {pack['card_amount']}"
            if pack['group_name']:
                desc += f"\n**Grupo:** {pack['group_name']}"
            if pack['set_id']:
                async with pool.acquire() as conn:
                    pack_set = await conn.fetchrow("SELECT DISTINCT set_name FROM cards_idol WHERE set_id = $1", pack['set_id'])
                desc += f"\n**Set:** {pack_set['set_name']}"
            desc += f"\n> **Obtenido:** <t:{int(pack['buy_date'].timestamp())}:d>"
            embed = discord.Embed(
                title=f"🎁 {pack['name']}",
                description=desc,
                color=discord.Color.gold()
            )
            
            embed.set_footer(text="Usa los botones para abrir el pack.")
            embeds.append(embed)
            pack_ids.append(pack["unique_id"])
        
        class OpenPackButton(discord.ui.Button):
            def __init__(self, label, unique_id, paginator=None):
                super().__init__(label=label, style=discord.ButtonStyle.green)
                self.unique_id = unique_id
                self.paginator = paginator

            async def callback(self, interaction: discord.Interaction):
                await interaction.response.edit_message(content="## 📦 Abriendo el pack...", embed=None, view=None)

                # Abrir el pack y obtener resultado
                result, pack_name = await open_pack(self.unique_id, interaction.user.id)

                if isinstance(result, str):  # Error (ej. pack ya abierto)
                    await interaction.followup.send(result, ephemeral=True)
                    return

                # Mapa de emojis para animación
                emoji_map = {
                    "item": "🎒",
                    "performance": "🎬",
                    "redeemable": "🎟️",
                    "idol": "👤",
                    "error": "❌"
                }

                message = await interaction.original_response()
                content = ""

                # Mostrar "animación" de apertura
                for tipo, _, id, u_id in result:
                    content += "\n" + emoji_map.get(tipo, "❓")
                    await message.edit(content=f"## 📦 Abriendo el pack...\n{content}")
                    await asyncio.sleep(0.6)

                await asyncio.sleep(1)

                RARITY_COLORS = {
                    "Regular": discord.Color.light_gray(),
                    "Special": discord.Color.purple(),
                    "Limited": discord.Color.yellow(),
                    "FCR": discord.Color.orange(),
                    "POB": discord.Color.blue(),
                    "Legacy": discord.Color.dark_purple(),
                }
                TYPE_COLORS = {
                    "item": discord.Color.teal(),
                    "performance": discord.Color.green(),
                    "redeemable": discord.Color.orange(),
                    "error": discord.Color.red()
                }
                RARITY_EMOJIS = {
                    "Regular": "⚪",
                    "Special": "🟣",
                    "Limited": "🟡",
                    "FCR": "🔴",
                    "POB": "🔵",
                    "Legacy": "⚫",
                }
                    
                final_embeds = []
                for i, (tipo, descripcion, id, u_id) in enumerate(result, start=1):
                    color = TYPE_COLORS.get(tipo, discord.Color.random())

                    if tipo == "idol":
                        emoji = "👤"
                        for nombre_r, color_r in RARITY_COLORS.items():
                            if nombre_r in descripcion:
                                color = color_r
                                emoji = RARITY_EMOJIS.get(nombre_r, emoji)
                                break
                    else:
                        emoji = ""

                    tipo_carta = tipo.capitalize()
                    
                    if tipo == "redeemable":
                        descr = f"{tipo_carta} obtenido!"
                    else:
                        descr = f"Carta {tipo_carta} obtenida"
                    embed = discord.Embed(
                        title=f"{emoji}{descripcion}",
                        description=descr,
                        color=color
                    )
                    if tipo != "redeemable" and tipo != "performance":
                        embed.set_footer(text=f"{id}.{u_id}")
                        
                    image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/d_no_image.jpg/{id}.webp{version}"
                    embed.set_thumbnail(url=image_url)
                    final_embeds.append(embed)

                await interaction.followup.send(
                    content=f"## {interaction.user.mention} ha abierto `{pack_name}` y obtuvo:",
                    embeds=final_embeds,
                    ephemeral=False
                )
                await interaction.followup.send(
                    content="✅ Pack abierto. Puedes volver a seleccionar otro pack:",
                    embed=None,
                    view=ReturnToPacksView(interaction.user.id),
                    ephemeral=True
                )

        class OpenPackView(discord.ui.View):
            def __init__(self, paginator: Paginator):
                super().__init__(timeout=120)
                self.paginator = paginator
                self.update_buttons()

            def update_buttons(self):
                self.clear_items()
                
                start = self.paginator.current_page * self.paginator.embeds_per_page
                end = start + self.paginator.embeds_per_page
                for i, pack_id in enumerate(self.paginator.pack_ids[start:end], start=1):
                    self.add_item(OpenPackButton(f"Open {i}", pack_id, paginator=self.paginator))

                
                self.add_item(PreviousButton(self.paginator))
                self.add_item(NextButton(self.paginator))

            async def interaction_check(self, interaction: discord.Interaction) -> bool:
                
                return interaction.user.id == user_id
        
        class CustomPaginator(Paginator):
            def __init__(self, embeds, embeds_per_page=3):
                super().__init__(embeds, embeds_per_page)
                self.pack_ids = []  # ✅ Esto lo evita el error

            def get_view(self):
                return OpenPackView(self)

            def current_embed(self):
                return self.embeds[self.current_page]

        
        # Crear paginador
        paginator = CustomPaginator(embeds, embeds_per_page=3)
        paginator.pack_ids = pack_ids
        await paginator.start(interaction)

        class ReturnToPacksButton(discord.ui.Button):
            def __init__(self, user_id):
                super().__init__(label="🔙 Volver a Packs", style=discord.ButtonStyle.secondary)
                self.user_id = user_id

            async def callback(self, interaction: discord.Interaction):
                pool = await get_pool()

                async with pool.acquire() as conn:
                    player_packs = await conn.fetch("""
                        SELECT pp.*, p.name, p.card_amount 
                        FROM players_packs pp
                        JOIN packs p ON pp.pack_id = p.pack_id
                        WHERE pp.user_id = $1
                        ORDER BY pp.buy_date ASC
                    """, self.user_id)

                if not player_packs:
                    await interaction.response.edit_message(content="❌ Ya no tienes packs disponibles.", embed=None, view=None)
                    return

                embeds = []
                new_pack_ids = []

                for pack in player_packs:
                    desc = f"**Cartas:** {pack['card_amount']}"
                    if pack['group_name']:
                        desc += f"\n**Grupo:** {pack['group_name']}"
                    if pack['set_id']:
                        async with pool.acquire() as conn:
                            pack_set = await conn.fetchrow("SELECT DISTINCT set_name FROM cards_idol WHERE set_id = $1", pack['set_id'])
                        desc += f"\n**Set:** {pack_set['set_name']}"
                    desc += f"\n> **Obtenido:** <t:{int(pack['buy_date'].timestamp())}:d>"

                    embed = discord.Embed(
                        title=f"🎁 {pack['name']}",
                        description=desc,
                        color=discord.Color.gold()
                    )
                    embed.set_footer(text="Usa los botones para abrir el pack.")
                    embeds.append(embed)
                    new_pack_ids.append(pack["unique_id"])

                # Crear nuevo paginador
                class RefreshedPaginator(Paginator):
                    def get_view(self):
                        return OpenPackView(self)

                    def current_embed(self):
                        return self.embeds[self.current_page]

                new_paginator = RefreshedPaginator(embeds, embeds_per_page=3)
                new_paginator.pack_ids = new_pack_ids

                # Sobrescribir variables globales del view actual (para que los botones se actualicen correctamente)
                view = new_paginator.get_view()

                await interaction.response.edit_message(embeds=new_paginator.get_current_embeds(), view=view)

        class ReturnToPacksView(discord.ui.View):
            def __init__(self, user_id):
                super().__init__(timeout=60)
                self.add_item(ReturnToPacksButton(user_id))

    @app_commands.command(name="buy", description="Comprar un sobre de cartas")
    @app_commands.describe(
        pack="Elige un pack para comprar",
        amount="Cantidad a comprar",
        group="(opcional) Elige un grupo, si el pack lo permite",
        gift_to="(opcional) Regala este pack a otro jugador"
    )
    async def buy(self, interaction: discord.Interaction, pack: str, amount:int = None, group: str = None, gift_to: str = None):
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()

        async with pool.acquire() as conn:
            if gift_to:
                agency = gift_to
            else:
                data = await conn.fetchrow("SELECT agency_name FROM users WHERE user_id = $1", user_id)
                agency = data['agency_name']
            agency_r = await conn.fetchrow("SELECT user_id FROM users WHERE agency_name = $1", agency)
            gift_to = await interaction.client.fetch_user(agency_r["user_id"])
            
            pack_data = await conn.fetchrow("SELECT * FROM packs WHERE pack_id = $1 AND price > 0", pack)
            if not pack_data:
                await interaction.response.send_message("❌ Pack inválido o no disponible para la venta.", ephemeral=True)
                return

            group_name = None
            if group:
                if pack_data["can_group"]:
                    group_name = group
                else:
                    await interaction.response.send_message("❌ Este pack no permite elegir grupo.", ephemeral=True)
                    return
                
            

            final_receiver_id = user_id
            total_price = pack_data["price"]
            if gift_to and gift_to.id != user_id:
                if not pack_data["can_gift"]:
                    await interaction.response.send_message("❌ Este pack no puede ser regalado.", ephemeral=True)
                    return
                final_receiver_id = gift_to.id
                total_price += pack_data["base_price"]

            t_cant = ""
            if amount:
                t_cant = f" x{amount}"
            else:
                amount = 1
            
            embed = discord.Embed(
                title=f"{pack_data['name']}{t_cant} - Confirmar compra",
                description=f"🎴 Cartas: {pack_data['card_amount']}\n💸 Precio total: {format(total_price*amount,',')}",
                color=discord.Color.gold()
            )
            if group_name:
                embed.add_field(name="Grupo elegido", value=group_name, inline=True)
            if pack_data['set_id']:
                set_data = await conn.fetchrow("SELECT DISTINCT set_name FROM cards_idol WHERE set_id = $1", pack_data['set_id'])
                embed.add_field(name="Set", value=set_data['set_name'], inline=True)
            if gift_to and gift_to.id != user_id:
                embed.add_field(name="Será entregado a", value=f"{agency} (Dirigida por: {gift_to.mention})", inline=False)

            user_c = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", user_id)
            user_credit = user_c['credits']
            embed.set_footer(text=f"Saldo actual: 💵{user_credit}")
            
            view = ConfirmPurchaseView(user_id, pack_data, total_price, final_receiver_id, group_name, agency, amount)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @buy.autocomplete("gift_to")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users")
        return [
            app_commands.Choice(name=f"{row["agency_name"]}", value=row["agency_name"])
            for row in rows if current.lower() in row["agency_name"].lower()
        ][:25] 
      
    @buy.autocomplete("pack")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM packs WHERE price > 0")
        return [
            app_commands.Choice(name=f"{row["name"]} (💵{row['price']}{" 👥" if row['can_group'] else ""}{" 🎁" if row['can_gift'] else ""}{" 🧩" if row['set_id'] else ""})",
                                value=row["pack_id"])
            for row in rows if current.lower() in f"{row["name"]} (💵{row['price']}{" 👥" if row['can_group'] else ""}{" 🎁" if row['can_gift'] else ""}{" 🧩" if row['set_id'] else ""})".lower()
        ][:25] 
    
    @buy.autocomplete("group")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM cards_idol ORDER BY group_name ASC")
        return [
            app_commands.Choice(name=row["group_name"], value=row["group_name"])
            for row in rows if current.lower() in row["group_name"].lower()
        ][:25]   

    @app_commands.command(name="list", description="Ver todos los packs disponibles para compra")
    async def list_packs(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM packs
            """)

        if not rows:
            await interaction.response.send_message("No hay packs disponibles actualmente.", ephemeral=True)
            return

        embeds = []
        for pack in rows:
            price = pack['price']
            if price > 0:
                price_text = f" | 💸 **Precio:** {price}"
            else:
                price_text = ""
            
            current_set = ""
            if pack["set_id"]:
                async with pool.acquire() as conn:
                    set_row = await conn.fetchrow("SELECT DISTINCT set_name FROM cards_idol WHERE set_id = $1", pack["set_id"])
                current_set = f"{set_row["set_name"]}"
            
            embed = discord.Embed(
                title=f"{pack['name']} - `{pack['pack_id']}`",
                description=f"🎴 **Cartas**: {pack['card_amount']}{price_text}",
                color=discord.Color.blue()
            )
            
            details = []
            theme = pack['theme']
            base_price = pack['base_price']
            w_idol = pack['w_idol']
            w_item = pack["w_item"]
            w_performance = pack["w_performance"]
            w_redeemable = pack["w_redeemable"]
            w_regular = pack['w_regular']
            w_limited = pack['w_limited']
            w_fcr = pack['w_fcr']
            w_pob = pack['w_pob']
            w_legacy = pack['w_legacy']
            if pack["theme"]:
                details.append(f"> 🎨 Temática: {theme}")
            if pack["set_id"]:
                details.append(f"> 🧩 Set: `{current_set}`")
            if pack["can_group"]:
                details.append("> 👥 Permite elegir grupo")
            if pack["can_gift"]:
                details.append(f"> 🎁 Se puede enviar (💵{base_price})")
            if pack["can_idol"]:
                details.append("> 👤 Permite elegir idol")
            if w_idol > 0:
                details.append(f"> 🃏 Puede incluir idol cards ({w_idol}%)")
            if w_regular > 0:
                details.append(f"> - Regular {w_regular}%")
            if w_limited > 0:
                details.append(f"> - Limited {w_limited}%")
            if w_fcr > 0:
                details.append(f"> - FCR {w_fcr}%")
            if w_pob > 0:
                details.append(f"> - POB {w_pob}%")
            if w_legacy > 0:
                details.append(f"> - Legacy {w_legacy}%")
            if w_item > 0:
                details.append(f"> 🧰 Puede incluir item cards ({w_item}%)")
            if w_performance > 0:
                details.append(f"> 🎤 Puede incluir performance cards ({w_performance}%)")
            if w_redeemable > 0:
                details.append(f"> 🎟️ Puede incluir canjeables ({w_redeemable}%)")

            
            embed.add_field(name="Detalles", value="\n".join(details) or "Sin detalles", inline=False)
            embeds.append(embed)

        paginator = Paginator(embeds, embeds_per_page=3)
        await paginator.start(interaction)

async def open_pack(unique_id: str, user_id: int):
    pool = await get_pool()
    results = []
    
    async with pool.acquire() as conn:
        async with conn.transaction():  # Asegura que todo se ejecute de forma atómica
            # Verificar existencia y obtener detalles
            pack_row = await conn.fetchrow("""
                SELECT pp.pack_id, pp.group_name, pp.set_id, p.name, p.card_amount, 
                       p.w_idol, p.w_item, p.w_performance, p.w_redeemable,
                       p.w_regular, p.w_limited, p.w_fcr, p.w_pob, p.w_legacy
                FROM players_packs pp
                JOIN packs p ON pp.pack_id = p.pack_id
                WHERE pp.unique_id = $1 AND pp.user_id = $2
            """, unique_id, user_id)

            if not pack_row:
                results = f"❌ Este pack ya fue abierto o no existe."
                return results

            # Eliminar el pack
            await conn.execute("DELETE FROM players_packs WHERE unique_id = $1", unique_id)

            amount = pack_row["card_amount"]

            tipo_weights = {
                "idol": pack_row["w_idol"],
                "item": pack_row["w_item"],
                "performance": pack_row["w_performance"],
                "redeemable": pack_row["w_redeemable"]
            }

            rarity_weights = {
                "R_": pack_row["w_regular"],
                "LMT": pack_row["w_limited"],
                "FCR": pack_row["w_fcr"],
                "POB": pack_row["w_pob"],
                "LEG": pack_row["w_legacy"]
            }

            for _ in range(amount):
                tipo = random.choices(list(tipo_weights.keys()), weights=tipo_weights.values())[0]

                if tipo == "item":
                    cards = await conn.fetch("SELECT * FROM cards_item")
                    if not cards:
                        results.append("❌ No hay items disponibles.")
                        continue

                    card = random.choices(cards, weights=[c["weight"] for c in cards])[0]

                    while True:
                        new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                        exists = await conn.fetchrow("SELECT 1 FROM user_item_cards WHERE unique_id = $1", new_id)
                        if not exists:
                            break

                    await conn.execute("""
                        INSERT INTO user_item_cards (unique_id, user_id, item_id, durability)
                        VALUES ($1, $2, $3, $4)
                    """, new_id, user_id, card["item_id"], card["max_durability"])
                    
                    item_desc = ""
                    if card['type'] == "mic":
                        item_desc = "🎤"
                    if card['type'] == "outfit":
                        item_desc = "👗"
                    if card['type'] == "accessory":
                        item_desc = "🎀"
                    if card['type'] == "consumable":
                        item_desc = "🧃"
                    item_desc += f" {card['name']}"
                    
                    results.append(("item", item_desc, card["item_id"], new_id))

                elif tipo == "performance":
                    cards = await conn.fetch("SELECT * FROM cards_performance")
                    if not cards:
                        results.append("❌ No hay performance cards disponibles.")
                        continue

                    card = random.choices(cards, weights=[c["weight"] for c in cards])[0]

                    await conn.execute("""
                        INSERT INTO user_performance_cards (user_id, pcard_id, quantity, last_updated)
                        VALUES ($1, $2, 1, now())
                        ON CONFLICT (user_id, pcard_id) DO UPDATE SET
                        quantity = user_performance_cards.quantity + 1,
                        last_updated = now()
                    """, user_id, card["pcard_id"])
                    
                    perf_desc = ""
                    if card['type'] == "reinforcement":
                        perf_desc = "🎭"
                    if card['type'] == "stage":
                        perf_desc = "🪩"
                    perf_desc += f" {card['name']}"
                    results.append(("performance", perf_desc, card["pcard_id"], None))

                elif tipo == "redeemable":
                    cards = await conn.fetch("SELECT * FROM redeemables")
                    if not cards:
                        results.append("❌ No hay redeemables disponibles.")
                        continue

                    card = random.choices(cards, weights=[c["weight"] for c in cards])[0]

                    await conn.execute("""
                        INSERT INTO user_redeemables (user_id, redeemable_id, quantity, last_updated)
                        VALUES ($1, $2, 1, now())
                        ON CONFLICT (user_id, redeemable_id) DO UPDATE SET
                        quantity = user_redeemables.quantity + 1,
                        last_updated = now()
                    """, user_id, card["redeemable_id"])
                    results.append(("redeemable", f"🎟️ {card['name']}", card["redeemable_id"], None))

                elif tipo == "idol":
                    while True:
                        rareza = random.choices(list(rarity_weights.keys()), weights=rarity_weights.values())[0]

                        if rareza == "R_":
                            query = "SELECT * FROM cards_idol WHERE rarity_id LIKE 'R_1'"
                            params = []

                            idx = 1
                            
                            if pack_row['group_name']:
                                query += f" AND group_name = ${idx}"
                                idx += 1
                                params.append(pack_row['group_name'])
                            if pack_row['set_id']:
                                query += f" AND set_id = ${idx}"
                                idx += 1
                                params.append(pack_row['set_id'])

                        else:
                            query = "SELECT * FROM cards_idol WHERE rarity_id = $1"
                            params = [rareza]
                            idx = 2
                            if pack_row['group_name']:
                                query += f" AND group_name = ${idx}"
                                idx += 1
                                params.append(pack_row['group_name'])
                            if pack_row['set_id']:
                                query += f" AND set_id = ${idx}"
                                idx += 1
                                params.append(pack_row['set_id'])

                        cards = await conn.fetch(query, *params)
                        if cards:
                            break

                    card = random.choices(cards, weights=[c["weight"] for c in cards])[0]

                    while True:
                        new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                        exists = await conn.fetchrow("SELECT 1 FROM user_idol_cards WHERE unique_id = $1", new_id)
                        if not exists:
                            break
                    
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
                    
                    # Agregar carta al inventario
                    await conn.execute("""
                        INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id, p_skill, a_skill, s_skill, u_skill)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, new_id, user_id, card["card_id"], card["idol_id"], card["set_id"], card["rarity_id"], p_skill, a_skill, s_skill, u_skill)
                    if card["rarity"] == "Regular" and card["rarity_id"].startswith("R") and len(card["rarity_id"]) == 3:
                        modelo = card["rarity_id"][1]
                        results.append(("idol", f"👤 {card['idol_name']} `{card['set_name']}`\n(Regular {modelo})", card["card_id"], new_id))
                    else:
                        results.append(("idol", f"👤 {card['idol_name']} `{card['set_name']}`\n({card['rarity']})", card["card_id"], new_id))

    return results, pack_row['name']

class ConfirmPurchaseView(discord.ui.View):
    def __init__(self, user_id, pack_data, total_price, final_receiver_id, group_name, agency, amount):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.pack_data = pack_data
        self.total_price = total_price
        self.final_receiver_id = final_receiver_id
        self.group_name = group_name
        self.agency = agency
        self.amount = amount
        self.pool = get_pool()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Solo quien usó el comando puede confirmar esta compra.", ephemeral=True)
            return
        quantity = self.amount
        async with self.pool.acquire() as conn:
            credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", self.user_id)
            if credits is None or credits < self.total_price * quantity:
                await interaction.response.send_message("❌ No tienes créditos suficientes.", ephemeral=True)
                return
            
            await conn.execute("UPDATE users SET credits = credits - $1 WHERE user_id = $2", self.total_price*quantity, self.user_id)

            q_gave = 0
            total_xp = 0
            while q_gave < quantity:
                while True:
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                    exists = await conn.fetchval("SELECT 1 FROM players_packs WHERE unique_id = $1", new_id)
                    if not exists:
                        break

                now = datetime.now(timezone.utc)
            
                await conn.execute("""
                    INSERT INTO players_packs (
                        unique_id, user_id, pack_id, buy_date,
                        group_name, set_id, theme
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, new_id, self.final_receiver_id, self.pack_data['pack_id'], now,
                    self.group_name, self.pack_data['set_id'], self.pack_data['theme'])
                
                pack_data = await conn.fetchrow(
                    "SELECT card_amount, base_price FROM packs WHERE pack_id = $1",
                    self.pack_data['pack_id']
                )

                xp_got = pack_data['card_amount'] * 10
                
                if self.final_receiver_id != self.user_id:
                    xtra_xp = pack_data['base_price'] // 100
                    xp_got += xtra_xp
                    
                q_gave += 1
                total_xp += xp_got
                
            await conn.execute(
                "UPDATE users SET xp = xp + $1 WHERE user_id = $2",
                total_xp, self.user_id
            )
        
        t_quantity = ""
        if quantity > 1:
            t_quantity = f" x{quantity}"
        
        await interaction.response.edit_message(
            content=f"✅ ¡Compra completada con éxito!\n## Has obtenido {total_xp} XP por tu compra",
            embed=None, view=None)
        

        if self.final_receiver_id != self.user_id:
            gifted_user = await interaction.client.fetch_user(self.final_receiver_id)
            print(gifted_user)
            await interaction.followup.send(
                content=f"🎁 Agencia **{self.agency}** (Dirigida por: {gifted_user.mention}) ha recibido **{self.pack_data['name']}{t_quantity}** como regalo de {interaction.user.mention}!"
            )
        

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Solo quien usó el comando puede cancelar esta compra.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Compra cancelada.", embeds=[], view=None)

# fcr
class ConfirmFCRView(discord.ui.View):
    def __init__(self, user_id, group_name, pack_data):
        super().__init__()
        self.user_id = user_id
        self.group_name = group_name
        self.pack_data = pack_data

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.green)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No puedes confirmar esto.", ephemeral=True)
            return

        pool = get_pool()
        unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))

        async with pool.acquire() as conn:
            # Verificar que el usuario aún pueda recibirlo
            user_data = await conn.fetchrow("SELECT can_fcr FROM users WHERE user_id = $1", self.user_id)
            if not user_data or not user_data["can_fcr"]:
                await interaction.response.send_message("❌ Ya reclamaste este pack.", ephemeral=True)
                return

            # Marcar como ya recibido
            await conn.execute("UPDATE users SET can_fcr = FALSE WHERE user_id = $1", self.user_id)

            user_data = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", self.user_id)
            
            # Insertar en tabla players_packs
            await conn.execute("""
                INSERT INTO players_packs (unique_id, user_id, pack_id, buy_date, group_name, set_id, theme)
                VALUES ($1, $2, $3, NOW(), $4, $5, $6)
            """, unique_id, self.user_id, self.pack_data['pack_id'], self.group_name, self.pack_data['set_id'], self.pack_data['theme'])

        await interaction.response.edit_message(content="## ✅ Pack FCR entregado correctamente!",view=None, embed=None)
        await interaction.followup.send(f"🎉 {user_data['agency_name']} ha recibido un **FCR Pack** de **{self.group_name}**", ephemeral=False)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ No puedes cancelar esto.", ephemeral=True)
            return
        await interaction.response.edit_message(content="❌ Entrega cancelada.", embed=None, view=None)


async def setup(bot):
    bot.tree.add_command(PacksGroup())