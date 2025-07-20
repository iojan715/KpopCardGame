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

# --- /inventory
class InventoryGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="inventory", description="Ver tu inventario de cartas y objetos")
    
    RARITY_CHOICES = [
        app_commands.Choice(name="Regular", value="Regular"),
        app_commands.Choice(name="Special", value="SPC"),
        app_commands.Choice(name="Limited", value="LMT"),
        app_commands.Choice(name="FCR", value="FCR"),
        app_commands.Choice(name="POB", value="POB"),
    ]

    STATUS_CHOICES = [
        app_commands.Choice(name="Available", value="available"),
        app_commands.Choice(name="Equipped", value="equipped"),
        app_commands.Choice(name="On sale", value="on_sale"),
        app_commands.Choice(name="Trading", value="trading"),
    ]

    IS_LOCKED_CHOICES = [
        app_commands.Choice(name="✅", value="✅"),
        app_commands.Choice(name="❌", value="❌"),
    ]

    ORDER_BY_CHOICES = [
        app_commands.Choice(name="Fecha de obtención", value="date_obtained"),
        app_commands.Choice(name="ID de idol", value="idol_id"),
        app_commands.Choice(name="ID de set", value="set_id"),
        app_commands.Choice(name="Rareza", value="rarity_id"),
        app_commands.Choice(name="Estado", value="status"),
        app_commands.Choice(name="Bloqueada", value="is_locked"),
    ]

    ORDER_CHOICES = [
        app_commands.Choice(name="⏫", value="ASC"),
        app_commands.Choice(name="⏬", value="DESC"),
    ]
    
    PUBLIC_CHOICES = [
        app_commands.Choice(name="✅", value="✅"),
        app_commands.Choice(name="❌", value="❌"),
    ]
    
    @app_commands.command(name="idol_cards", description="Ver tus cartas de idol")
    @app_commands.describe(
        user="Target user's inventory",
        idol="Filter by idol",
        set_name="Filter by set",
        group="Filter by group",
        rarity="Filter by rarity",
        nivel="Filter by level (1-3)",
        status="Filter by status",
        is_locked="(✅/❌)",
        order_by="Sort by parameter",
        order="Sort direction (⏫/⏬)",
        duplicated="only duplicated")
    @app_commands.choices(
        rarity=RARITY_CHOICES,
        status=STATUS_CHOICES,
        is_locked=IS_LOCKED_CHOICES,
        order_by=ORDER_BY_CHOICES,
        order=ORDER_CHOICES,
        duplicated=PUBLIC_CHOICES
    )
    async def idol_cards(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        idol: str = None,
        set_name: str = None,
        group: str = None,
        rarity: app_commands.Choice[str] = None,
        nivel: int = None,
        status: app_commands.Choice[str] = None,
        is_locked: app_commands.Choice[str] = None,
        order_by: app_commands.Choice[str] = None,
        order: app_commands.Choice[str] = None,
        duplicated: app_commands.Choice[str] = None,
    ):
        user_id = user.id if user else interaction.user.id
        pool = get_pool()

        
        base_query = """
            SELECT uc.* FROM user_idol_cards uc
            JOIN cards_idol ci ON uc.card_id = ci.card_id
            WHERE uc.user_id = $1
        """
        params = [user_id]
        idx = 2
        
        if idol:
            base_query += f" AND uc.idol_id = ${idx}"
            params.append(idol)
            idx += 1

        if set_name:
            base_query += f" AND uc.set_id = ${idx}"
            params.append(set_name)
            idx += 1

        if group:
            base_query += f" AND ci.group_name = ${idx}"
            params.append(group)
            idx += 1
        
        if rarity:
            if rarity.value == "Regular":
                base_query += f" AND uc.rarity_id LIKE 'R__'"
            else:
                base_query += f" AND uc.rarity_id = ${idx}"
                params.append(rarity.value.upper())
                idx += 1

        if nivel and (not rarity or rarity == "Regular"):
            base_query += f" AND RIGHT(uc.rarity_id, 1) = ${idx}"
            params.append(str(nivel))
            idx += 1

        if status:
            base_query += f" AND uc.status = ${idx}"
            params.append(status.value.lower())
            idx += 1

        if is_locked:
            boolean_value = is_locked.value == "✅"
            base_query += f" AND uc.is_locked = ${idx}"
            params.append(boolean_value)
            idx += 1
        
        valid_order_by = ["idol_id", "set_id", "rarity_id", "status", "is_locked"]
        order_column = "date_obtained"
        if order_by:
            if order_by.value in valid_order_by:
                order_column = order_by.value
        order_dir = "ASC"
        if order:
            order_dir = order.values
        if not order and not order_by:
            order_dir = "DESC"
        base_query += f" ORDER BY {order_column} {order_dir}"
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(base_query, *params)
            if duplicated:
                card_counts = Counter([row['card_id'] for row in rows])
                if duplicated.value == "✅":
                    rows = [row for row in rows if card_counts[row['card_id']] >= 2]
                else:
                    rows = [row for row in rows if card_counts[row['card_id']] == 1]

        
        language = await get_user_language(user_id=user_id)  
            
        if not rows:
            await interaction.response.send_message("No tienes cartas de idol por ahora.", ephemeral=True)
            return

        card_counts = Counter([row['card_id'] for row in rows])
        embeds = []
        for row in rows:
            async with pool.acquire() as conn:
                idol_row = await conn.fetchrow("""
                    SELECT idol_name, set_name, rarity, group_name, rarity_id
                    FROM cards_idol WHERE card_id = $1
                """, row["card_id"])
                
                name = idol_row['idol_name']
                card_set = idol_row['set_name']
                rarity = idol_row['rarity']
                group_name = idol_row['group_name']
                
                c_rarity = rarity
                
                if rarity == "Regular":
                    model = idol_row['rarity_id'][1]
                    level = idol_row['rarity_id'][2]
                    rarity += f" {model} - Lvl.{level}"
                
            blocked = "🔐" if row["is_locked"] else ""
            c_status = ""
            if row['status'] == 'equipped':
                c_status = "👥"
            elif row['status'] == "trading":
                c_status = "🔄"
            elif row['status'] == "on_sale":
                c_status = "💲"
            
            RARITY_COLORS = {
                "Regular": discord.Color.light_gray(),
                "Special": discord.Color.purple(),
                "Limited": discord.Color.yellow(),
                "FCR": discord.Color.fuchsia(),
                "POB": discord.Color.blue(),
                "Legacy": discord.Color.dark_purple(),
            }
            embed_color = RARITY_COLORS.get(c_rarity, discord.Color.default())

            embed = discord.Embed(
                title=f"{name} - *{group_name}* {blocked}{c_status}",
                description=f"{card_set} `{rarity}`",
                color=embed_color
            )
            
            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['card_id']}.webp{version}"
            embed.set_thumbnail(url=image_url)
            
            cantidad_copias = ""
            if card_counts[row['card_id']] > 1:
                cantidad_copias = f" `x{card_counts[row['card_id']]} copias`"
            
            embed.add_field(name=cantidad_copias, value="", inline=False)
            embed.set_footer(text=f"{row['card_id']}.{row['unique_id']}")
            #{row['date_obtained'].strftime('%Y-%m-%d %H:%M:%S')}
            embeds.append(embed)

        paginator = Paginator(embeds)
        await paginator.start(interaction)

    
    @idol_cards.autocomplete("idol")
    async def idol_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT idol_id, name FROM idol_base ORDER BY name ASC")
        return [
            app_commands.Choice(name=f"{row['name']} ({row['idol_id']})", value=row['idol_id'])
            for row in rows if current.lower() in f"{row['name'].lower()} ({row['idol_id'].lower()})"
        ][:25]

    @idol_cards.autocomplete("set_name")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT set_id, set_name FROM cards_idol ORDER BY set_name ASC")
        return [
            app_commands.Choice(name=row["set_name"], value=row["set_id"])
            for row in rows if current.lower() in row["set_name"].lower()
        ][:25]
    
    @idol_cards.autocomplete("group")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM cards_idol ORDER BY group_name ASC")
        return [
            app_commands.Choice(name=row["group_name"], value=row["group_name"])
            for row in rows if current.lower() in row["group_name"].lower()
        ][:25]


    ITEM_TYPE_CHOICES = [
        app_commands.Choice(name="Accessory", value="accessory"),
        app_commands.Choice(name="Outfit", value="outfit"),
        app_commands.Choice(name="Mic", value="mic"),
        app_commands.Choice(name="Consumable", value="consumable"),
    ]

    STATUS_CHOICES = [
        app_commands.Choice(name="Available", value="available"),
        app_commands.Choice(name="Equipped", value="equipped"),
        app_commands.Choice(name="On sale", value="on_sale"),
        app_commands.Choice(name="Trading", value="trading"),
    ]

    STAT_CHOICES = [
        app_commands.Choice(name="Vocal", value="plus_vocal"),
        app_commands.Choice(name="Rap", value="plus_rap"),
        app_commands.Choice(name="Dance", value="plus_dance"),
        app_commands.Choice(name="Visual", value="plus_visual"),
        app_commands.Choice(name="Energy", value="plus_energy"),
    ]

    ORDER_BY_CHOICES = [
        app_commands.Choice(name="Durability", value="durability"),
        app_commands.Choice(name="Name", value="name"),
        app_commands.Choice(name="Date obtained", value="date_obtained"),
    ]

    ORDER_CHOICES = [
        app_commands.Choice(name="⏫", value="ASC"),
        app_commands.Choice(name="⏬", value="DESC"),
    ]
    
    @app_commands.command(name="item_cards", description="Ver tus item cards")
    @app_commands.describe(
        user="User",
        type="Filtra por tipo de item",
        status="Filtra por estado",
        stat="Filtra por stat con bonus",
        order_by="Ordenar por",
        order="Dirección de orden"
    )
    @app_commands.choices(
        type=ITEM_TYPE_CHOICES,
        status=STATUS_CHOICES,
        stat=STAT_CHOICES,
        order_by=ORDER_BY_CHOICES,
        order=ORDER_CHOICES
    )
    async def item_cards(
        self,
        interaction: discord.Interaction,
        user: discord.User = None,
        type: app_commands.Choice[str] = None,
        status: app_commands.Choice[str] = None,
        stat: app_commands.Choice[str] = None,
        order_by: app_commands.Choice[str] = None,
        order: app_commands.Choice[str] = None
    ):
        user_id = interaction.user.id
        pool = get_pool()

        if user:
            user_id = user.id
        
        # Construcción dinámica del query
        query = """
            SELECT u.*, c.name, c.type, c.plus_vocal, c.plus_rap, c.plus_dance,
                c.plus_visual, c.plus_energy
            FROM user_item_cards u
            JOIN cards_item c ON u.item_id = c.item_id
            WHERE u.user_id = $1
        """
        params = [user_id]
        idx = 2

        if type:
            query += f" AND c.type = ${idx}"
            params.append(type.value)
            idx += 1

        if status:
            query += f" AND u.status = ${idx}"
            params.append(status.value)
            idx += 1

        if stat:
            query += f" AND c.{stat.value} != 0"

        order_column = order_by.value if order_by else "u.date_obtained"
        order_direction = order.value if order else "DESC"

        # Validar que no se pueda hacer ORDER BY por un stat inválido (por seguridad)
        valid_columns = {"durability": "u.durability", "name": "c.name", "date_obtained": "u.date_obtained"}
        order_clause = f" ORDER BY {valid_columns.get(order_column, 'u.date_obtained')} {order_direction}"
        query += order_clause

        async with pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        language = await get_user_language(user_id=user_id)
        durability = get_translation(language, "inventory.durability")

        if not rows:
            await interaction.response.send_message("No tienes item cards por ahora.", ephemeral=True)
            return

        embeds = []
        for row in rows:
            embed = discord.Embed(
                title=f"{"✅" if row['status'] == "available" else ""} {row['name']} ⌛{row['durability']}",
                description=f"`{row['type'].capitalize()}`",
                color=discord.Color.teal()
            )

            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['item_id']}.webp{version}"
            embed.set_thumbnail(url=image_url)

            stats = [
                ("Vocal", row["plus_vocal"]),
                ("Rap", row["plus_rap"]),
                ("Dance", row["plus_dance"]),
                ("Visual", row["plus_visual"]),
                ("Energy", row["plus_energy"]),
            ]
            bonus_str = "\n".join(f"**{f'+{v}' if v > 0 else v}** {k}" for k, v in stats if v != 0)
            if bonus_str:
                embed.add_field(name="Bonos:", value=bonus_str, inline=False)

            embed.set_footer(text=f"{row['item_id']}.{row['unique_id']}")
            embeds.append(embed)

        paginator = Paginator(embeds, embeds_per_page=3)
        await paginator.start(interaction)


    @app_commands.command(name="performance_cards", description="Ver tus performance cards")
    @app_commands.describe(user="User")
    async def performance_cards(self, interaction: discord.Interaction, user:discord.User = None):
        await self.display_simple_inventory(
            interaction,
            user=user,
            table="user_performance_cards",
            id_field="pcard_id",
            quantity_field="quantity",
            order_by="pcard_id"
        )

    @app_commands.command(name="redeemables", description="Ver tus objetos canjeables")
    @app_commands.describe(user="User")
    async def redeemables(self, interaction: discord.Interaction, user:discord.User = None):
        await self.display_simple_inventory(
            interaction,
            user = user,
            table="user_redeemables",
            id_field="redeemable_id",
            quantity_field="quantity",
            order_by="redeemable_id"
        )

    @app_commands.command(name="badges", description="Ver tus insignias")
    @app_commands.describe(user="User")
    async def badges(self, interaction: discord.Interaction, user:discord.User = None):
        await self.display_simple_inventory(
            interaction,
            user = user,
            table="user_badges",
            id_field="badge_id",
            quantity_field=None,
            order_by="date_obtained"
        )

    async def display_simple_inventory(self, interaction: discord.Interaction, user, table, id_field, quantity_field, order_by):
        user_id = interaction.user.id
        if user:
            user_id = user.id
        
        pool = get_pool()
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            if quantity_field:
                query = f"SELECT {id_field}, {quantity_field} FROM {table} WHERE user_id = $1 ORDER BY {order_by} ASC"
            else:
                query = f"SELECT {id_field}, date_obtained FROM {table} WHERE user_id = $1 ORDER BY {order_by} ASC"

            rows = await conn.fetch(query, user_id)

        if not rows:
            await interaction.response.send_message("No tienes objetos de este tipo por ahora.", ephemeral=True)
            return

        # Crear páginas de hasta 10 elementos
        items_per_page = 5
        pages = [
            rows[i:i+items_per_page]
            for i in range(0, len(rows), items_per_page)
        ]

        current_page = 0
        embeds = []
        
        if table == "user_performance_cards":
            table_base = "cards_performance"
            id_type = "pcard_id"
        elif table == "user_redeemables":
            table_base = "redeemables"
            id_type = "redeemable_id"
        elif table == "user_badges":
            table_base = "badges"
            id_type = "badge_id"

        for page_rows in pages:
            embed = discord.Embed(
                title=f"📦 {table.replace('user_', '').replace('_', ' ').title()}",
                color=discord.Color.teal()
            )
            for row in page_rows:
                item_id = row[id_field]
                
                async with pool.acquire() as conn:
                    p_name = await conn.fetchrow(f"SELECT name FROM {table_base} WHERE {id_type} = $1", item_id)
                    
                    vocal = rap = dance = visual = hype = score = extra_cost = relative_cost = duration = None
                    if table_base == "cards_performance":
                        pe_card = await conn.fetchrow("SELECT type, effect, duration FROM cards_performance WHERE pcard_id = $1", item_id)
                        if pe_card['type'] == "stage":
                            eff_stats = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", pe_card['effect'])
                            vocal = eff_stats['plus_vocal']
                            rap = eff_stats['plus_rap']
                            dance = eff_stats['plus_dance']
                            visual = eff_stats['plus_visual']
                            hype = int((eff_stats['hype_mod']-1)*100)
                            score = int((eff_stats['score_mod']-1)*100)
                            extra_cost = eff_stats['extra_cost']
                            relative_cost = int((eff_stats['relative_cost']-1)*100)
                            duration = pe_card['duration']
                
                if quantity_field:
                    quantity = row[quantity_field]
                    embed.add_field(name=f"**{p_name['name']}:** {quantity}",
                                    value=f"> {get_translation(language,f"inventory_description.{item_id}",vocal=vocal, rap=rap, dance=dance, visual=visual, hype=hype, score=score, extra_cost=extra_cost, relative_cost=relative_cost, duration=duration)}",
                                    inline=False)
                else:
                    embed.add_field(name=f"**{p_name['name']}**", value="Aqui va la descripción del objeto", inline=False)
            embeds.append(embed)

        paginator = SimplePaginator(embeds)
        await paginator.start(interaction)

# paginator
class SimplePaginator:
    def __init__(self, embeds: list):
        self.embeds = embeds
        self.current_page = 0
        self.total_pages = len(embeds)

    async def start(self, interaction: discord.Interaction):
        embed = self.get_current_embed()
        await interaction.response.send_message(embed=embed, view=self.get_view(), ephemeral=True)

    def get_view(self):
        view = discord.ui.View()
        view.add_item(PreviousSimpleButton(self))
        view.add_item(NextSimpleButton(self))
        return view

    def get_current_embed(self):
        embed = self.embeds[self.current_page]
        embed.set_footer(text=f"Página {self.current_page + 1} / {self.total_pages}")
        return embed

    async def update(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.get_current_embed(), view=self.get_view())

class PreviousSimpleButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="◀️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page - 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

class NextSimpleButton(discord.ui.Button):
    def __init__(self, paginator):
        super().__init__(label="▶️", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        self.paginator.current_page = (self.paginator.current_page + 1) % self.paginator.total_pages
        await self.paginator.update(interaction)

# --- /cards
class CardGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="cards", description="Manage idol and item cards")

    PUBLIC_CHOICES = [
        app_commands.Choice(name="✅", value="T"),
        app_commands.Choice(name="❌", value="F")
    ]
    
    @app_commands.command(name="view", description="Ver información de cualquier carta (idol o ítem)")
    @app_commands.describe(
        card_id="ID de la carta o ítem en formato card_id.unique_id",
        public="¿Quieres que el mensaje sea público?"
    )
    @app_commands.choices(public=PUBLIC_CHOICES)
    async def view_card(
        self,
        interaction: discord.Interaction,
        card_id: str,
        public: str = None
    ):
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()

        try:
            code, unique_id = card_id.split(".")
        except ValueError:
            return await interaction.response.send_message("❌ Formato inválido. Usa `id.unique_id`", ephemeral=True)

        async with pool.acquire() as conn:
            # Buscar primero como carta idol
            row = await conn.fetchrow("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = $1 AND user_id = $2
            """, unique_id, user_id)

            if row:
                card_type = "idol"
                base_data = await conn.fetchrow("""
                    SELECT idol_name, set_name, rarity, group_name, rarity_id
                    FROM cards_idol WHERE card_id = $1
                """, row["card_id"])

                if not base_data:
                    return await interaction.response.send_message("❌ No se encontró la información de la carta.", ephemeral=True)

                name = base_data['idol_name']
                card_set = base_data['set_name']
                rarity = base_data['rarity']
                group_name = base_data['group_name']
                rarity_id = base_data['rarity_id']

                c_rarity = rarity
                if rarity == "Regular":
                    model = rarity_id[1]
                    level = rarity_id[2]
                    rarity += f" {model} - Lvl.{level}"

                blocked = "🔐" if row["is_locked"] else ""

                RARITY_COLORS = {
                    "Regular": discord.Color.light_gray(),
                    "Special": discord.Color.purple(),
                    "Limited": discord.Color.yellow(),
                    "FCR": discord.Color.fuchsia(),
                    "POB": discord.Color.blue(),
                    "Legacy": discord.Color.dark_purple(),
                }
                embed_color = RARITY_COLORS.get(c_rarity, discord.Color.default())

                embed = discord.Embed(
                    title=f"{name} - *{group_name}* {blocked}",
                    description=f"{card_set} `{rarity}`",
                    color=embed_color
                )

                user_row = await conn.fetchrow("SELECT agency_name FROM users WHERE user_id = $1", row['user_id'])
                embed.add_field(name=f"Agencia: {user_row['agency_name']}", value=f"> Dirigida por: <@{row['user_id']}>")

                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['card_id']}.webp{version}"
                embed.set_image(url=image_url)

                embed.add_field(name=row["status"].capitalize(), value="", inline=False)
                embed.set_footer(text=f"{row['card_id']}.{row['unique_id']}")

            else:
                # Buscar como ítem
                row = await conn.fetchrow("""
                    SELECT * FROM user_item_cards
                    WHERE unique_id = $1 AND user_id = $2
                """, unique_id, user_id)

                if not row:
                    return await interaction.response.send_message("❌ No se encontró la carta o ítem especificado.", ephemeral=True)

                card_type = "item"
                item_data = await conn.fetchrow("""
                    SELECT * FROM cards_item WHERE item_id = $1
                """, row["item_id"])

                if not item_data:
                    return await interaction.response.send_message("❌ No se encontró información del ítem base.", ephemeral=True)

                user_row = await conn.fetchrow("SELECT agency_name FROM users WHERE user_id = $1", row['user_id'])

                embed = discord.Embed(
                    title=f"{item_data['name']} ({item_data['type']})",
                    description=(f"🎯 Durabilidad: `{row['durability']} / {item_data['max_durability']}`\n"
                                f"📦 Estado: `{row['status'].capitalize()}`"),
                    color=discord.Color.orange()
                )

                embed.add_field(
                    name=f"Agencia: {user_row['agency_name']}",
                    value=f"> Propietario: <@{row['user_id']}>",
                    inline=False
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

                embed.set_footer(text=f"{item_data['item_id']}.{row['unique_id']}")
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{item_data['item_id']}.webp{version}"
                embed.set_image(url=image_url)

        # Mostrar mensaje
        if not public:
            public = "F"
        publicc = public == "T"
        await interaction.response.send_message(embed=embed, ephemeral=not publicc)

    @app_commands.command(name="equip", description="Equipar una carta de idol o de ítem")
    @app_commands.describe(card_id="ID único de la carta o ítem (formato: id.unique_id)")
    async def equip_card(self, interaction: discord.Interaction, card_id: str):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        try:
            base_id, unique_id = card_id.split(".")
        except ValueError:
            return await interaction.response.send_message("❌ Formato inválido. Usa el formato `id.unique_id`.", ephemeral=True)

        async with pool.acquire() as conn:
            # Primero buscar como idol card
            card = await conn.fetchrow("""
                SELECT uic.*, ci.idol_name, ci.set_name, ci.group_name, ci.idol_id, ci.rarity, ci.rarity_id
                FROM user_idol_cards uic
                JOIN cards_idol ci ON uic.card_id = ci.card_id
                WHERE uic.unique_id = $1 AND uic.user_id = $2
            """, unique_id, user_id)

            if card:
                if card["status"] not in ("available", "equipped"):
                    return await interaction.response.send_message(
                        get_translation(language, "equip_idol.unavailable"), ephemeral=True)

                # Buscar grupos que contengan al idol
                groups = await conn.fetch("""
                    SELECT g.group_id, g.name
                    FROM groups g
                    JOIN groups_members gm ON g.group_id = gm.group_id
                    WHERE g.user_id = $1 AND gm.idol_id = $2 AND g.status = 'active'
                """, user_id, card["idol_id"])

                if not groups:
                    return await interaction.response.send_message(
                        get_translation(language, "equip_idol.no_valid_groups"), ephemeral=True)

                embed = discord.Embed(
                    title=get_translation(language, "equip_idol.select_group_title"),
                    description=get_translation(language, "equip_idol.select_group_desc",
                                                card_name=f"{card['idol_name']} `{card['set_name']}` ({card['rarity']}{f' {card['rarity_id'][1]} Lv.{card['rarity_id'][2]}' if card['set_name'] == 'Regular' else ''})"),
                    color=discord.Color.blue()
                )
                view = SelectGroupToEquipView(card)
                for group in groups:
                    view.add_item(SelectGroupButton(card, group))

                return await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

            # Si no es idol, intentar como ítem
            item = await conn.fetchrow("""
                SELECT uic.*, ci.name, ci.type FROM user_item_cards uic
                JOIN cards_item ci ON uic.item_id = ci.item_id
                WHERE uic.user_id = $1 AND uic.unique_id = $2
            """, user_id, unique_id)

            if not item:
                return await interaction.response.send_message("❌ No se encontró ninguna carta o ítem con ese ID.", ephemeral=True)

            if item["status"] not in ("available", "equipped"):
                return await interaction.response.send_message("❌ Esa carta no se puede equipar en este momento.", ephemeral=True)

            groups = await conn.fetch("""
                SELECT group_id, name FROM groups WHERE user_id = $1
            """, user_id)

            view = SelectGroupForItemView(item)
            for g in groups:
                view.add_item(SelectGroupItemButton(user_id, item, g))

            await interaction.response.send_message(
                f"Selecciona el grupo al que deseas equipar **{item['name']}** (`{card_id}`):",
                view=view,
                ephemeral=True
            )

    @app_commands.command(name="unequip", description="Desequipar una carta de idol o ítem")
    @app_commands.describe(card_id="ID único de la carta (formato: id.unique_id)")
    async def unequip_card(self, interaction: discord.Interaction, card_id: str):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        try:
            base_id, unique_id = card_id.split(".")
        except ValueError:
            return await interaction.response.send_message("❌ Formato inválido. Usa el formato `id.unique_id`.", ephemeral=True)

        async with pool.acquire() as conn:
            # Intentar como carta de idol
            idol_card = await conn.fetchrow("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = $1 AND user_id = $2
            """, unique_id, user_id)

            if idol_card:
                if idol_card["status"] != "equipped":
                    return await interaction.response.send_message(
                        get_translation(language, "unequip_idol.not_equipped"), ephemeral=True)

                await conn.execute("""
                    UPDATE groups_members SET card_id = NULL
                    WHERE user_id = $1 AND card_id = $2
                """, user_id, idol_card["card_id"])

                await conn.execute("""
                    UPDATE user_idol_cards SET status = 'available'
                    WHERE unique_id = $1
                """, unique_id)

                return await interaction.response.send_message(
                    get_translation(language, "unequip_idol.success", card_id=idol_card["card_id"]), ephemeral=True)

            # Intentar como ítem
            item_card = await conn.fetchrow("""
                SELECT * FROM user_item_cards
                WHERE unique_id = $1 AND user_id = $2
            """, unique_id, user_id)

            if not item_card:
                return await interaction.response.send_message("❌ No se encontró esa carta.", ephemeral=True)

            if item_card["status"] != "equipped":
                return await interaction.response.send_message("⚠️ Esa carta no está equipada.", ephemeral=True)

            # Detectar slot (mic_id, outfit_id, accessory_id, consumable_id)
            slot_columns = ["mic_id", "outfit_id", "accessory_id", "consumable_id"]
            found_slot = None

            for slot in slot_columns:
                result = await conn.fetchrow(f"""
                    SELECT group_id, idol_id FROM groups_members
                    WHERE user_id = $1 AND {slot} = $2
                """, user_id, card_id)
                if result:
                    found_slot = slot
                    break

            if not found_slot:
                return await interaction.response.send_message(
                    "⚠️ No se encontró en qué idol está equipada esta carta de ítem.", ephemeral=True)

            await conn.execute(f"""
                UPDATE groups_members SET {found_slot} = NULL
                WHERE user_id = $1 AND {found_slot} = $2
            """, user_id, card_id)

            await conn.execute("""
                UPDATE user_item_cards SET status = 'available'
                WHERE unique_id = $1
            """, unique_id)

            return await interaction.response.send_message(
                f"✅ Carta de ítem `{card_id}` ha sido desequipada correctamente.", ephemeral=True)


    @app_commands.command(name="level_up", description="Combina dos cartas Regulares iguales para subir de nivel")
    @app_commands.describe(card_1="ej: IDLSETTR12.unique", card_2="ej: IDLSETTR12.unique")
    async def level_up(self, interaction: discord.Interaction, card_1: str, card_2: str):
        user_id = interaction.user.id

        if card_1 == card_2:
            return await interaction.response.send_message("❌ Las cartas deben ser diferentes.", ephemeral=True)

        uid_1 = card_1.split(".")[1]
        uid_2 = card_2.split(".")[1]

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, [uid_1, uid_2], user_id)

        if len(rows) != 2:
            return await interaction.response.send_message("❌ No se encontraron ambas cartas o no te pertenecen.", ephemeral=True)

        row_1, row_2 = rows
        if row_1["card_id"] != row_2["card_id"]:
            return await interaction.response.send_message("❌ Las cartas deben ser del mismo idol, set y rareza.", ephemeral=True)

        if row_1["status"] != "available" or row_2["status"] != "available":
            return await interaction.response.send_message("❌ Ambas cartas deben estar disponibles.", ephemeral=True)

        rarity_id = row_1["rarity_id"]
        if not rarity_id.startswith("R") or rarity_id.endswith("3"):
            return await interaction.response.send_message("❌ Solo se pueden subir de nivel cartas Regulares menores a nivel 3.", ephemeral=True)

        # Obtener nuevo rarity_id
        nivel_actual = int(rarity_id[-1])
        nuevo_nivel = nivel_actual + 1
        nuevo_rarity_id = rarity_id[:-1] + str(nuevo_nivel)
        nuevo_card_id = f"{row_1['idol_id']}{row_1['set_id']}{nuevo_rarity_id}"

        stars = "⭐" * nuevo_nivel
        cost = 1000 * nivel_actual
        # Mostrar preview
        preview_embed = discord.Embed(
            title=f"{stars} Confirmar mejora!",
            description=f"### Obtendrás una carta nivel {nuevo_nivel}.\n### > Costo de mejora: {format(cost, ',')}💵",
            color=discord.Color.light_gray()
        )
        preview_embed.set_thumbnail(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{nuevo_card_id}.webp{version}")
        preview_embed.set_footer(text="Presiona Confirmar para continuar o Cancelar para detener el proceso.")

        view = ConfirmLevelUpView(
            user_id=user_id,
            uid_1=uid_1,
            uid_2=uid_2,
            nuevo_card_id=nuevo_card_id,
            idol_id=row_1['idol_id'],
            set_id=row_1['set_id'],
            rarity_id=nuevo_rarity_id,
            cost=cost
        )
        await interaction.response.send_message(embed=preview_embed, view=view, ephemeral=True)

    @app_commands.command(name="fusion_check", description="Ver posibles fusiones que puedes hacer con tus cartas Regulares")
    @app_commands.describe(level="Nivel que quieres priorizar (1, 2 o 3)")
    async def fusion_check(self, interaction: discord.Interaction, level: int = None):
        user_id = interaction.user.id
        pool = await get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT uc.unique_id, uc.card_id, uc.idol_id, uc.set_id, uc.rarity_id,
                    ci.idol_name, ci.set_name
                FROM user_idol_cards uc
                JOIN cards_idol ci ON uc.card_id = ci.card_id
                WHERE uc.user_id = $1
                AND uc.status = 'available'
                AND uc.rarity_id LIKE 'R__'
            """, user_id)

        if not rows:
            return await interaction.response.send_message("❌ No tienes cartas Regulares disponibles para fusión.", ephemeral=True)

        # Agrupar por (idol_id, set_id)
        combinaciones = defaultdict(lambda: defaultdict(list))
        for row in rows:
            model = row["rarity_id"][1]
            nivel = int(row["rarity_id"][2])
            key = (row["idol_id"], row["set_id"], row["idol_name"], row["set_name"])
            combinaciones[key][model].append((nivel, row["card_id"], row["unique_id"]))

        posibles = []
        for (idol_id, set_id, idol_name, set_name), modelos in combinaciones.items():
            if len(modelos) < 3:
                continue

            # Necesitamos al menos un modelo de cada tipo: 1, 2, 3
            if not all(m in modelos for m in ["1", "2", "3"]):
                continue

            seleccionadas = []
            for m in ["1", "2", "3"]:
                cartas = modelos[m]
                # Ordenar por cercanía al nivel deseado si se indicó
                if level:
                    cartas.sort(key=lambda x: abs(x[0] - level))
                else:
                    cartas.sort(key=lambda x: x[0])  # más bajo primero por defecto

                seleccionadas.append(cartas[0])  # (nivel, card_id, unique_id)

            # Preparar comando
            cmd = f"/cards fusion card_1:{seleccionadas[0][1]}.{seleccionadas[0][2]} card_2:{seleccionadas[1][1]}.{seleccionadas[1][2]} card_3:{seleccionadas[2][1]}.{seleccionadas[2][2]}"

            success = sum(carta[0] for carta in seleccionadas) * 10
            embed = discord.Embed(
                title=f"{idol_name} - {set_name}",
                description=f"{cmd}",
                color=discord.Color.teal()
            )
            embed.set_footer(text=f"Probabilidad de éxito: {success}%")
            posibles.append(embed)

        if not posibles:
            return await interaction.response.send_message("❌ No tienes combinaciones válidas para fusión.", ephemeral=True)

        paginator = Paginator(posibles)
        await paginator.start(interaction)

    @app_commands.command(name="fusion", description="Fusiona 3 cartas Regulares diferentes del mismo idol y set")
    @app_commands.describe(card_1="ej: IDLSETTR11.unique", card_2="ej: IDLSETTR21.unique", card_3="ej: IDLSETTR31.unique")
    async def fusion(self, interaction: discord.Interaction, card_1: str, card_2: str, card_3: str):
        user_id = interaction.user.id
        input_cards = [card_1, card_2, card_3]
        
        if len(set(input_cards)) != 3:
            return await interaction.response.send_message("❌ Las cartas deben ser diferentes.", ephemeral=True)

        uids = [c.split(".")[1] for c in input_cards]
        pool = await get_pool()

        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, uids, user_id)

        if len(rows) != 3:
            return await interaction.response.send_message("❌ No se encontraron las tres cartas o no te pertenecen.", ephemeral=True)

        if any(row["status"] != "available" for row in rows):
            return await interaction.response.send_message("❌ Todas las cartas deben estar disponibles.", ephemeral=True)

        if any(not row["rarity_id"].startswith("R") for row in rows):
            return await interaction.response.send_message("❌ Solo se pueden usar cartas Regulares.", ephemeral=True)

        idol_ids = {r["idol_id"] for r in rows}
        set_ids = {r["set_id"] for r in rows}
        modelos = {r["rarity_id"][1] for r in rows}

        if len(idol_ids) != 1 or len(set_ids) != 1 or len(modelos) != 3:
            return await interaction.response.send_message("❌ Las cartas deben ser del mismo idol, set, y de modelos distintos.", ephemeral=True)

        idol_id = idol_ids.pop()
        set_id = set_ids.pop()
        rarity_id = "SPC"
        card_id = f"{idol_id}{set_id}{rarity_id}"
        success = 0
        for row in rows:
            success += int(row['rarity_id'][-1]) * 10
        
        preview = discord.Embed(
            title="✨ Confirmar fusión",
            description=f"### Fusionarás 3 cartas regulares para obtener una carta **Special**.\n> Costo: 5,000 💵\nProbabilidad de éxito: {success}%",
            color=discord.Color.purple()
        )
        preview.set_thumbnail(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}")
        preview.set_footer(text="Presiona Confirmar para continuar o Cancelar para detener el proceso.")

        view = ConfirmFusionView(user_id, uids, card_id, idol_id, set_id, rarity_id)
        await interaction.response.send_message(embed=preview, view=view, ephemeral=True)

    @app_commands.command(name="refund", description="Solicita un reembolso por una carta u objeto")
    @app_commands.describe(
        card="ID de la carta/objeto con formato ID.unique"
    )
    async def refund(self, interaction: discord.Interaction, card: str):
        user_id = interaction.user.id
        try:
            uid = card.split(".")[1]
        except IndexError:
            return await interaction.response.send_message("❌ El formato del ID es incorrecto.", ephemeral=True)

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM user_idol_cards WHERE unique_id = $1 AND user_id = $2
            """, uid, user_id)

            item_type = "idol"
            if not row:
                row = await conn.fetchrow("""
                    SELECT * FROM user_item_cards WHERE unique_id = $1 AND user_id = $2
                """, uid, user_id)
                item_type = "item"

            if not row or row["status"] != "available":
                return await interaction.response.send_message("❌ No se encontró el ítem o no está disponible.", ephemeral=True)

            if item_type == "idol":
                ref_data = await conn.fetchrow("SELECT idol_name, set_name, rarity, value FROM cards_idol WHERE card_id = $1", row["card_id"])
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['card_id']}.webp{version}"
            else:
                ref_data = await conn.fetchrow("SELECT name, value FROM cards_item WHERE item_id = $1", row["item_id"])
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['item_id']}.webp{version}"

            if not ref_data:
                return await interaction.response.send_message("❌ No se encontró la información del ítem.", ephemeral=True)

            value = ref_data["value"]
            refund = value * 2
            xp = value // 100

            name = ref_data.get("idol_name", ref_data.get("name"))
            desc = f"{ref_data['set_name']} - {ref_data['rarity']}" if item_type == "idol" else "Objeto de soporte"

            embed = discord.Embed(
                title=f"🔁 Reembolso",
                description=f"## **{name}**\n### {desc}\n\nObtendrás:\n> **{format(refund,',')} 💵**",
                color=discord.Color.gold()
            )
            embed.set_image(url=image_url)
            embed.set_footer(text="Presiona Confirmar para realizar el reembolso o Cancelar para abortar.")
            view = ConfirmRefundView(user_id=user_id, unique_id=uid, refund=refund, xp=xp, item_type=item_type)

            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# refund
class ConfirmRefundView(discord.ui.View):
    def __init__(self, user_id, unique_id, refund, xp, item_type):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.unique_id = unique_id
        self.refund = refund
        self.xp = xp
        self.item_type = item_type

    @discord.ui.button(label="✅", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        pool = await get_pool()
        async with pool.acquire() as conn:
            tabla = "user_idol_cards" if self.item_type == "idol" else "user_item_cards"
            row = await conn.fetchrow(f"""
                SELECT * FROM {tabla}
                WHERE unique_id = $1 AND user_id = $2 AND status = 'available'
            """, self.unique_id, self.user_id)

            if not row:
                return await interaction.response.edit_message(content="❌ El ítem ya no está disponible.", embed=None, view=None)

            await conn.execute(f"""
                DELETE FROM {tabla}
                WHERE unique_id = $1 AND user_id = $2
            """, self.unique_id, self.user_id)

            await conn.execute("""
                UPDATE users SET credits = credits + $1, xp = xp + $2
                WHERE user_id = $3
            """, self.refund, self.xp, self.user_id)

        await interaction.response.edit_message(content=f"## ✅ Reembolso completado.\n### Has recibido **{self.refund}💵** y **{self.xp} XP**.",
                                                embed=None,
                                                view=None)

    @discord.ui.button(label="✖", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)
        await interaction.response.edit_message(content="❌ Reembolso cancelado.", embed=None, view=None)


# fusion
class ConfirmFusionView(discord.ui.View):
    def __init__(self, user_id, uids, new_card_id, idol_id, set_id, rarity_id):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.uids = uids
        self.new_card_id = new_card_id
        self.idol_id = idol_id
        self.set_id = set_id
        self.rarity_id = rarity_id
        self.cost = 5000

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2 AND status = 'available'
            """, self.uids, self.user_id)

            if len(rows) != 3:
                return await interaction.response.edit_message(
                    content="❌ Las cartas ya fueron usadas o no están disponibles.",
                    embed=None, view=None
                )

            user_data = await conn.fetchrow("SELECT credits FROM users WHERE user_id = $1", self.user_id)
            if not user_data or user_data["credits"] < self.cost:
                return await interaction.response.edit_message(
                    content="❌ No tienes suficientes créditos para realizar la fusión.",
                    embed=None, view=None
                )

            msg = await interaction.response.edit_message(
                content="## 🔮 Realizando fusión...\n",
                embed=None,
                view=None
            )
            await asyncio.sleep(0.5)

            success = True
            result = "## 🔮 Resultados:\n"
            for row in rows:
                level = int(row["rarity_id"][-1])
                chance = 0
                if level == 3:
                    chance = 96
                elif level == 2:
                    chance = 84
                else:
                    chance = 67
                roll = random.randint(1, 100)
                emoji = "\n✅" if roll <= chance else "\n❌"
                result += f"{emoji} "
                if emoji == "\n❌":
                    success = False
                await interaction.edit_original_response(content=result)
                await asyncio.sleep(0.6)

            if not success:
                await conn.execute("""
                    UPDATE users SET credits = credits - $1 WHERE user_id = $2
                """, self.cost, self.user_id)

                embed_fail = discord.Embed(
                    title="❌ Fusión fallida",
                    description="La fusión ha fallado.\nPuedes intentar nuevamente si deseas.",
                    color=discord.Color.red()
                )
                retry_view = RetryFusionView(self.user_id, self.uids, self.new_card_id, self.idol_id, self.set_id, self.rarity_id)

                await interaction.followup.send(embed=embed_fail, view=retry_view, ephemeral=True)
                return


            await conn.execute("""
                DELETE FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, self.uids, self.user_id)

            await conn.execute("""
                UPDATE users SET credits = credits - $1 WHERE user_id = $2
            """, self.cost, self.user_id)

            new_uid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            await conn.execute("""
                INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, new_uid, self.user_id, self.new_card_id, self.idol_id, self.set_id, self.rarity_id)

        embed = discord.Embed(
            title="✨ Fusión completada con éxito!",
            description="Has obtenido una nueva carta **Special** 🎉",
            color=discord.Color.purple()
        )
        embed.set_image(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{self.new_card_id}.webp{version}")

        await interaction.followup.send(embed=embed, ephemeral=False)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        await interaction.response.edit_message(content="❌ Fusión cancelada.", embed=None, view=None)

class RetryFusionView(discord.ui.View):
    def __init__(self, user_id, uids, card_id, idol_id, set_id, rarity_id):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.uids = uids
        self.card_id = card_id
        self.idol_id = idol_id
        self.set_id = set_id
        self.rarity_id = rarity_id

    @discord.ui.button(label="🔁 Intentar de nuevo", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        # reconstruir el mensaje inicial
        preview = discord.Embed(
            title="✨ Confirmar fusión",
            description=f"### Fusionarás 3 cartas regulares para obtener una carta **Special**.\n> Costo: 5,000 💵\nProbabilidad de éxito: calculada dinámicamente",
            color=discord.Color.purple()
        )
        preview.set_thumbnail(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{self.card_id}.webp{version}")
        preview.set_footer(text="Presiona Confirmar para continuar o Cancelar para detener el proceso.")

        view = ConfirmFusionView(self.user_id, self.uids, self.card_id, self.idol_id, self.set_id, self.rarity_id)
        await interaction.response.edit_message(content=None, embed=preview, view=view)


# level up
class ConfirmLevelUpView(discord.ui.View):
    def __init__(self, user_id, uid_1, uid_2, nuevo_card_id, idol_id, set_id, rarity_id, cost):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.uid_1 = uid_1
        self.uid_2 = uid_2
        self.nuevo_card_id = nuevo_card_id
        self.idol_id = idol_id
        self.set_id = set_id
        self.rarity_id = rarity_id
        self.cost = cost

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Verificar que ambas cartas aún estén disponibles
            rows = await conn.fetch("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2 AND status = 'available'
            """, [self.uid_1, self.uid_2], self.user_id)

            if len(rows) != 2:
                return await interaction.response.edit_message(
                    content="❌ Las cartas ya fueron usadas o no están disponibles.",
                    embed=None,
                    view=None
                )

            # Eliminar las cartas originales
            await conn.execute("""
                DELETE FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, [self.uid_1, self.uid_2], self.user_id)
            
            xp = (15*self.cost)//1000
            # Aplicar costo
            await conn.execute("""
                UPDATE users SET credits = credits - $1, xp = xp + $2
                WHERE user_id = $3
            """, self.cost, xp, self.user_id)

            # Insertar nueva carta
            new_unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            await conn.execute("""
                INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, new_unique_id, self.user_id, self.nuevo_card_id, self.idol_id, self.set_id, self.rarity_id)

        # Mostrar resultado final
        final_embed = discord.Embed(
            title="✅ Carta mejorada con éxito",
            description=f"Has obtenido una nueva carta de nivel {self.rarity_id[-1]}.",
            color=discord.Color.light_gray()
        )
        final_embed.set_image(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{self.nuevo_card_id}.webp{version}")

        await interaction.response.edit_message(content=f"## ✅ Carta obtenida con éxito!\nHas obtenido **{xp} XP**", embed=None, view=None)
        await interaction.followup.send(embed=final_embed, ephemeral=False)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        await interaction.response.edit_message(content="❌ Mejora cancelada.", embed=None, view=None)

# equip idol
class SelectGroupToEquipView(discord.ui.View):
    def __init__(self, card):
        super().__init__(timeout=120)
        self.card = card

class SelectGroupButton(discord.ui.Button):
    def __init__(self, card, group):
        super().__init__(label=group["name"], style=discord.ButtonStyle.primary)
        self.card = card
        self.group = group

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            member = await conn.fetchrow("""
                SELECT * FROM groups_members
                WHERE group_id = $1 AND user_id = $2 AND idol_id = $3
            """, self.group["group_id"], user_id, self.card["idol_id"])

        if not member:
            await interaction.response.send_message(get_translation(language, "equip_idol.no_matching_members"), ephemeral=True)
            return

        embed = discord.Embed(
            title=get_translation(language, "equip_idol.confirm_title"),
            description=get_translation(language, "equip_idol.confirm_desc",
                card_name=f"{self.card['idol_name']} ({self.card['unique_id']})",
                group_name=self.group["name"]
            ),
            color=discord.Color.orange()
        )

        view = ConfirmEquipIdolView(card=self.card, group_id=self.group["group_id"], idol_id=self.card["idol_id"])
        await interaction.response.edit_message(embed=embed, view=view)

class ConfirmEquipIdolView(discord.ui.View):
    def __init__(self, card, group_id, idol_id):
        super().__init__(timeout=60)
        self.card = card
        self.group_id = group_id
        self.idol_id = idol_id
        self.add_item(ConfirmEquipIdolButton(self))
        self.add_item(CancelEquipIdolButton(self))

class ConfirmEquipIdolButton(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            # Desequipar si está en otro 
            card_id = f"{self.parent.card['card_id']}.{self.parent.card["unique_id"]}"
            
            name = await conn.fetchrow("SELECT idol_name FROM cards_idol WHERE card_id = $1", self.parent.card['card_id'])
            
            await conn.execute("""
                UPDATE groups_members SET card_id = NULL
                WHERE user_id = $1 AND card_id = $2
            """, user_id, card_id)

            # Equipar en el idol actual
            await conn.execute("""
                UPDATE groups_members SET card_id = $1
                WHERE user_id = $2 AND group_id = $3 AND idol_id = $4
            """, card_id, user_id, self.parent.group_id, self.parent.idol_id)

            # Cambiar estado de la carta
            await conn.execute("""
                UPDATE user_idol_cards SET status = 'equipped'
                WHERE unique_id = $1
            """, self.parent.card["unique_id"])

        await interaction.response.edit_message(
            content=get_translation(language, "equip_idol.success", card_id=card_id, idol_id=name['idol_name']),
            embed=None, view=None
        )

class CancelEquipIdolButton(discord.ui.Button):
    def __init__(self, parent):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        language = await get_user_language(interaction.user.id)
        await interaction.response.edit_message(
            content=get_translation(language, "equip_idol.cancelled"),
            embed=None, view=None
        )

# equip item
class EquipItemCommand(app_commands.Command):
    def __init__(self):
        super().__init__(
            name="equip_item",
            description="Equipa una carta de ítem a uno de tus idols",
            callback=self.callback
        )

    async def callback(self, interaction: discord.Interaction, item_id: str):
        pool = get_pool()
        user_id = interaction.user.id

        async with pool.acquire() as conn:
            item = await conn.fetchrow("""
                SELECT uic.*, ci.name, ci.type FROM user_item_cards uic
                JOIN cards_item ci ON uic.item_id = ci.item_id
                WHERE uic.user_id = $1 AND uic.unique_id = $2
            """, user_id, item_id)

            if not item:
                await interaction.response.send_message("❌ No tienes esa carta de ítem.", ephemeral=True)
                return

            if item["status"] not in ("available", "equipped"):
                await interaction.response.send_message("❌ Esa carta no se puede equipar en este momento.", ephemeral=True)
                return

            groups = await conn.fetch("""
                SELECT group_id, name FROM groups WHERE user_id = $1
            """, user_id)

        view = SelectGroupForItemView(item)
        for g in groups:
            view.add_item(SelectGroupItemButton(item, g["group_id"], g["name"]))
        await interaction.response.send_message(
            f"Selecciona el grupo al que deseas equipar **{item['name']} ({item['unique_id']})**:",
            view=view,
            ephemeral=True
        )

class SelectGroupForItemView(discord.ui.View):
    def __init__(self, item):
        super().__init__(timeout=60)
        self.item = item

class SelectMemberItemView(discord.ui.View):
    def __init__(self, item, group_id):
        super().__init__(timeout=60)
        self.item = item
        self.group_id = group_id

class BackToItemGroupSelectButton(discord.ui.Button):
    def __init__(self, item):
        super().__init__(label="🔙 Volver", style=discord.ButtonStyle.secondary)
        self.item = item

    async def callback(self, interaction: discord.Interaction):
        await EquipItemCommand().callback(interaction, self.item["unique_id"])

class SelectGroupItemButton(discord.ui.Button):
    def __init__(self, user_id, item_row, group):
        super().__init__(label=group["name"], style=discord.ButtonStyle.secondary)
        self.user_id = user_id
        self.item_row = item_row
        self.group = group

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            members = await conn.fetch("""
                SELECT gm.*, ig.idol_name
                FROM groups_members gm
                JOIN idol_group ig ON gm.idol_id = ig.idol_id
                WHERE gm.group_id = $1
            """, self.group["group_id"])

        view = discord.ui.View(timeout=60)
        for member in members:
            label = f"{member['idol_name']} ({member['idol_id']})"
            view.add_item(SelectMemberItemButton(self.item_row, self.group, member, label))

        view.add_item(CancelButtonItemEquip())
        await interaction.response.edit_message(
            content="Selecciona al idol que deseas equipar el ítem:",
            embed=None,
            view=view
        )

class SelectMemberItemButton(discord.ui.Button):
    def __init__(self, item_row, group, member, label):
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.item_row = item_row
        self.group = group
        self.member = member

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            type_slot_map = {
                "mic": "mic_id",
                "outfit": "outfit_id",
                "accessory": "accessory_id",
                "consumable": "consumable_id"
            }
            slot = type_slot_map.get(self.item_row["type"])
            if not slot:
                await interaction.response.edit_message(content="❌ Tipo de ítem inválido.", view=None)
                return

            # Desequipar item anterior si existe
            previous_item_id = self.member[slot]
            if previous_item_id:
                await conn.execute("""
                    UPDATE user_item_cards SET status = 'available'
                    WHERE unique_id = $1
                """, previous_item_id)

            await conn.execute(f"""
                UPDATE groups_members SET {slot} = $1
                WHERE {slot} = $2
            """, None, f"{self.item_row["item_id"]}.{self.item_row["unique_id"]}")

            # Actualizar grupo y carta
            await conn.execute(f"""
                UPDATE groups_members SET {slot} = $1
                WHERE group_id = $2 AND idol_id = $3
            """, f"{self.item_row["item_id"]}.{self.item_row["unique_id"]}", self.group["group_id"], self.member["idol_id"])

            print(self.item_row["unique_id"])
            await conn.execute("""
                UPDATE user_item_cards SET status = 'equipped'
                WHERE unique_id = $1
            """, self.item_row["unique_id"])

        await interaction.response.edit_message(
            content=f"✅ Ítem equipado correctamente a **{self.member['idol_name']}**.",
            view=None
        )

class CancelButtonItemEquip(discord.ui.Button):
    def __init__(self):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="❌ Operación cancelada.", view=None)

async def setup(bot):
    bot.tree.add_command(InventoryGroup())
    bot.tree.add_command(CardGroup())
