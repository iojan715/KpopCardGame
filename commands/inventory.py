import discord, random, asyncio, string, json
from discord.ext import commands
from discord import app_commands
import csv
import os
from utils.localization import get_translation
from utils.language import get_user_language
from utils.emojis import get_emoji
from db.connection import get_pool
from datetime import datetime
from utils.paginator import Paginator, NextButton, PreviousButton
from collections import Counter, defaultdict
from commands.starter import version
from commands.starter import base, mult, reduct


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
    app_commands.Choice(name="Fecha de obtención", value="uc.date_obtained"),
    app_commands.Choice(name="Nombre", value="ci.idol_name"),
    app_commands.Choice(name="Idol ID", value="uc.idol_id"),
    app_commands.Choice(name="Set ID", value="uc.set_id"),
    app_commands.Choice(name="Rareza", value="uc.rarity_id"),
    app_commands.Choice(name="Estado", value="uc.status"),
    app_commands.Choice(name="Bloqueada", value="uc.is_locked"),
]

ORDER_CHOICES = [
    app_commands.Choice(name="⏫", value="ASC"),
    app_commands.Choice(name="⏬", value="DESC"),
]

PUBLIC_CHOICES = [
    app_commands.Choice(name="✅", value="✅"),
    app_commands.Choice(name="❌", value="❌"),
]

DETAIL_CHOICES = [
    app_commands.Choice(name="❌", value="❌"),
    app_commands.Choice(name="✅", value="✅"),
]
    

# --- /inventory
class InventoryGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="inventory", description="Ver tu inventario de cartas y objetos")
    

    @app_commands.command(name="idol_cards", description="Ver tus cartas de idol")
    @app_commands.describe(
        agency="Target agency's inventory",
        idol="Filter by idol",
        set_name="Filter by set",
        group="Filter by group",
        rarity="Filter by rarity",
        nivel="Filter by level (1-3)",
        status="Filter by status",
        is_locked="(✅/❌)",
        order_by="Sort by parameter",
        order="Sort direction (⏫/⏬)",
        duplicated="only duplicated",
        details="Show or not card stats and skills")
    @app_commands.choices(
        rarity=RARITY_CHOICES,
        status=STATUS_CHOICES,
        is_locked=IS_LOCKED_CHOICES,
        order_by=ORDER_BY_CHOICES,
        order=ORDER_CHOICES,
        duplicated=PUBLIC_CHOICES,
        details=DETAIL_CHOICES
    )
    async def idol_cards(
        self,
        interaction: discord.Interaction,
        agency: str = None,
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
        details: app_commands.Choice[str] = None,
    ):
        await interaction.response.defer(
            ephemeral=True
        )
        if interaction.guild is None:
            return await interaction.edit_original_response(
                content="❌ Este comando solo está disponible en servidores."
            )
        user_id = interaction.user.id
        pool = get_pool()
        is_duplicated = False
        if duplicated:
            if duplicated.value == "✅":
                is_duplicated = True

        if agency:
            async with pool.acquire() as conn:
                user_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
        
        base_query = """
            SELECT uc.*, ci.* FROM user_idol_cards uc
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
        
        valid_order_by = ["uc.idol_id", "ci.idol_name", "uc.set_id", "uc.rarity_id", "uc.status", "uc.is_locked"]
        order_column = "uc.date_obtained"
        if order_by:
            if order_by.value in valid_order_by:
                order_column = order_by.value
        order_dir = "ASC"
        if order:
            order_dir = order.value
        if not order and not order_by:
            order_dir = "DESC"
        base_query += f" ORDER BY {order_column} {order_dir}"
        
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'view_inventory'
                """, interaction.user.id)
            rows = await conn.fetch(base_query, *params)
            if duplicated:
                card_counts = Counter([row['card_id'] for row in rows])
                if duplicated.value == "✅":
                    rows = [row for row in rows if card_counts[row['card_id']] >= 2]
                else:
                    rows = [row for row in rows if card_counts[row['card_id']] >= 1]
        is_detailed = True
        if details:
            if details.value == "✅":
                pass
            else:
                is_detailed = False
                
        
        language = await get_user_language(user_id=user_id)  
            
        if not rows:
            await interaction.edit_original_response(content="## ❌No hay cartas para mostrar.")
            return

        card_counts = Counter([row['card_id'] for row in rows])
        embeds = await generate_idol_card_embeds(rows, pool, interaction.guild, is_detailed)

        paginator = InventoryEmbedPaginator(embeds, rows, interaction, base_query, params, is_duplicated, is_detailed, embeds_per_page=3)
        await paginator.start()

    
    @idol_cards.autocomplete("idol")
    async def idol_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT idol_id, name FROM idol_base ORDER BY name ASC")
        return [
            app_commands.Choice(name=f"{row['name']} ({row['idol_id']})", value=row['idol_id'])
            for row in rows if current.lower() in f"{row['name'].lower()} ({row['idol_id'].lower()})"
        ][:25]
        
    @idol_cards.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
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
        agency="Agency",
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
        agency: str = None,
        type: app_commands.Choice[str] = None,
        status: app_commands.Choice[str] = None,
        stat: app_commands.Choice[str] = None,
        order_by: app_commands.Choice[str] = None,
        order: app_commands.Choice[str] = None
    ):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return await interaction.edit_original_response(
                content="❌ Este comando solo está disponible en servidores."
            )
        user_id = interaction.user.id
        pool = get_pool()

        if agency:
            async with pool.acquire() as conn:
                user_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
        
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
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'view_items'
                """, interaction.user.id)
            rows = await conn.fetch(query, *params)

        language = await get_user_language(user_id=user_id)

        if not rows:
            await interaction.edit_original_response(content="## ❌No tienes item cards por ahora.")
            return

        embeds = await generate_item_card_embeds(rows, pool)
        
        paginator = ItemInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=query,
            query_params=tuple(params),
            embeds_per_page=3
        )
        await paginator.start()
    
    @item_cards.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
        ][:25]

    @app_commands.command(name="performance_cards", description="Ver tus performance cards")
    @app_commands.describe(agency="Agency")
    async def performance_cards(self, interaction: discord.Interaction, agency:str = None):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild is None:
            return await interaction.edit_original_response(
                content="❌ Este comando solo está disponible en servidores."
            )
        pool = get_pool()
        
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'view_pcards'
                """, interaction.user.id)
        
        await self.display_simple_inventory(
            interaction,
            agency=agency,
            table="user_performance_cards",
            id_field="pcard_id",
            quantity_field="quantity",
            order_by="pcard_id"
        )

    @performance_cards.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
        ][:25]

    ORDER_BY_CHOICES_REDEEM = [
        #app_commands.Choice(name="Type", value="r.type"),
        app_commands.Choice(name="Name", value="r.name"),
        app_commands.Choice(name="Last obtained", value="u.last_updated"),
    ]

    ORDER_CHOICES_REDEEM = [
        app_commands.Choice(name="⏫", value="DESC"),
        app_commands.Choice(name="⏬", value="ASC"),
    ]
    
    @app_commands.command(name="redeemables", description="Ver tus objetos canjeables")
    @app_commands.describe(agency="Agency", order_by="Ordenar por", order="Orden")
    @app_commands.choices(order_by=ORDER_BY_CHOICES_REDEEM, order=ORDER_CHOICES_REDEEM)
    async def redeemables(
        self,
        interaction: discord.Interaction,
        agency:str = None,
        order_by: app_commands.Choice[str] = None,
        order: app_commands.Choice[str] = None
        ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = get_pool()
        language = await get_user_language(user_id)

        if agency:
            async with pool.acquire() as conn:
                user_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
        
        # Construcción dinámica del query
        query = """
            SELECT u.*, r.*
            FROM user_redeemables u
            JOIN redeemables r ON u.redeemable_id = r.redeemable_id
            WHERE u.user_id = $1
        """
        params = [user_id]
        idx = 2
        
        order_column = order_by.value if order_by else "u.last_updated"
        order_direction = order.value if order else None
        
        if order_column:
            if order_column == "r.name" and not order_direction:
                order_direction = "ASC"
        
        if not order_direction:
            order_direction = "DESC"
        
        valid_columns = {"u.last_updated": "u.last_updated", "r.type": "r.type", "r.name": "r.name"}
        order_clause = f" ORDER BY {valid_columns.get(order_column, 'u.last_updated')} {order_direction}"
        query += order_clause
        
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'view_redeemables'
                """, interaction.user.id)
            rows = await conn.fetch(query, *params)
            
        if not rows:
            await interaction.response.send_message("No tienes cupones por ahora.", ephemeral=True)
            return
        
        embeds = await generate_redeemables_embeds(rows, pool, interaction)
        
        paginator = RedeemablesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=query,
            query_params=tuple(params),
            embeds_per_page=5
        )
        await paginator.start()

    @redeemables.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
        ][:25]

    @app_commands.command(name="badges", description="Ver tus insignias")
    @app_commands.describe(agency="Agency")
    async def badges(self, interaction: discord.Interaction, agency:str = None):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = get_pool()
        language = await get_user_language(user_id)

        if agency:
            async with pool.acquire() as conn:
                user_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
        
        # Construcción dinámica del query
        query = """
            SELECT u.*, b.*
            FROM user_badges u
            JOIN badges b ON u.badge_id = b.badge_id
            WHERE u.user_id = $1
        """
        params = [user_id]
        idx = 2
        
        order_column = "u.date_obtained"
        order_direction = None
        
        if order_column:
            if order_column == "b.name" and not order_direction:
                order_direction = "ASC"
        
        if not order_direction:
            order_direction = "DESC"
        
        valid_columns = {"u.date_obtained": "u.date_obtained"}
        order_clause = f" ORDER BY {valid_columns.get(order_column, 'u.date_obtained')} {order_direction}"
        query += order_clause
        
        async with pool.acquire() as conn:
            
            rows = await conn.fetch(query, *params)
            
        if not rows:
            await interaction.response.send_message("## No tienes insignias por ahora.", ephemeral=True)
            return
        
        embeds = await generate_badges_embeds(rows, pool, interaction)
        
        paginator = BadgesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=query,
            query_params=tuple(params),
            embeds_per_page=5
        )
        await paginator.start()

    @badges.autocomplete("agency")
    async def agency_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT agency_name FROM users ORDER BY register_date DESC")
        return [
            app_commands.Choice(name=f"{row['agency_name']}", value=row['agency_name'])
            for row in rows if current.lower() in f"{row['agency_name'].lower()}"
        ][:25]

    async def display_simple_inventory(self, interaction: discord.Interaction, agency, table, id_field, quantity_field, order_by):
        user_id = interaction.user.id
        
        pool = get_pool()
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            if agency:
                user_id = await conn.fetchval("SELECT user_id FROM users WHERE agency_name = $1", agency)
            
            if quantity_field:
                query = f"SELECT {id_field}, {quantity_field} FROM {table} WHERE user_id = $1 ORDER BY {order_by} ASC"
            else:
                query = f"SELECT {id_field}, date_obtained FROM {table} WHERE user_id = $1 ORDER BY {order_by} ASC"

            rows = await conn.fetch(query, user_id)

        if not rows:
            await interaction.edit_original_response(content="No tienes objetos de este tipo por ahora.")
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
                title=f"{table.replace('user_', '').replace('_', ' ').title()}",
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
                                    value=f"- {get_translation(language,f"inventory_description.{item_id}",vocal=vocal, rap=rap, dance=dance, visual=visual, hype=hype, score=score, extra_cost=extra_cost, relative_cost=relative_cost, duration=duration)}",
                                    inline=False)
                else:
                    embed.add_field(name=f"**{p_name['name']}**", value="", inline=False)
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
        await interaction.edit_original_response(embed=embed, view=self.get_view())

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

# redeemables
async def generate_redeemables_embeds(rows: list[dict], pool, interaction) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    language = await get_user_language(interaction.user.id)
    
    for row in rows:
        
        embed = discord.Embed(
            title=f"{row['name']}: {row['quantity']}",
            description=f"{get_translation(language,f"inventory_description.{row['redeemable_id']}")}",
            color=discord.Color.teal()
        )

        image_url = (
            f"https://res.cloudinary.com/dyvgkntvd/image/upload/"
            f"f_webp,d_no_image.jpg/{row['redeemable_id']}.webp{version}"
        )
        #embed.set_thumbnail(url=image_url)

        embeds.append(embed)

    return embeds

class RedeemablesInventoryEmbedPaginator:
    def __init__(
        self,
        embeds: list[discord.Embed],
        rows: list[dict],
        interaction: discord.Interaction,
        base_query: str,
        query_params: tuple,
        embeds_per_page: int = 5
    ):
        self.all_embeds = embeds
        self.all_rows = rows
        self.interaction = interaction
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(embeds) + embeds_per_page - 1) // embeds_per_page
        self.current_page_embeds: list[discord.Embed] = []

        self.base_query = base_query
        self.query_params = query_params

    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        footer = discord.Embed(
            description=f"**Página** {self.current_page+1}/{self.total_pages}",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        rows_this_page = self.all_rows[start:end]

        for row in rows_this_page:
            if row['user_id'] == self.interaction.user.id:
                view.add_item(RedeemButton(row, self))

        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))
        return view

    async def start(self):
        self.current_page_embeds = self.get_page_embeds()
        await self.interaction.response.send_message(
            embeds=self.current_page_embeds,
            view=self.get_view(),
            ephemeral=True
        )

    async def restart(self, interaction: discord.Interaction, restart:bool):
        self.current_page = 0
        self.current_page_embeds = self.get_page_embeds()
        if restart:
            await interaction.followup.send(
                embeds=self.current_page_embeds,
                view=self.get_view(),
                ephemeral=True
            )
        else:
            await interaction.response.edit_message(
                embeds=self.current_page_embeds,
                view=self.get_view()
            )

    async def update(self, interaction: discord.Interaction):
        self.current_page_embeds = self.get_page_embeds()
        await interaction.response.edit_message(
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)

class RedeemButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "RedeemablesInventoryEmbedPaginator"):
        self.row_data = row_data
        self.paginator = paginator
        super().__init__(label=row_data['name'], style=discord.ButtonStyle.primary, disabled=row_data['type']=="redeem" or row_data['quantity']==0)
        
    async def callback(self, interaction: discord.Interaction):
        row = self.row_data
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
        
        need_group = ["EXCNT", "MDCNT"]
        
        if row['redeemable_id'] in need_group:
            async with pool.acquire() as conn:
                groups = await conn.fetch("SELECT * FROM groups WHERE user_id = $1 AND status = 'active'", interaction.user.id)
            
            desc = ""
            for g in groups:
                desc += f"- **{g['name']}**\n> ⭐: `{g['popularity']}` - 🏆: `{g['permanent_popularity']}`\n\n"
                
            
            embed = discord.Embed(
                title=f"Selecciona un grupo para usar el cupón:",
                description="",
                color=discord.Color.teal()
                )
            
            view = discord.ui.View()
            for group in groups:
                view.add_item(RedeemableGroupButton(row, self.paginator, group))
            
            view.add_item(BackToRedeemablesInventoryButton(self.paginator.base_query, self.paginator.query_params,self.paginator))
            
            await interaction.response.edit_message(
                embed=embed, view=view
            )
            return
            
        
        embed = discord.Embed(
            title=f"¿Deseas canjear el siguiente cupón?",
            description=f"{row['name']}: {row['quantity']}\n> {get_translation(language,f"inventory_description.{row['redeemable_id']}")}",
            color=discord.Color.teal()
        )
        
        view = discord.ui.View()
        view.add_item(ConfirmRedeemableButton(self.row_data, self.paginator))
        view.add_item(BackToRedeemablesInventoryButton(self.paginator.base_query, self.paginator.query_params,self.paginator))
        
        await interaction.response.edit_message(
            embed=embed, view=view
        )

class ConfirmRedeemableButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "RedeemablesInventoryEmbedPaginator"):
        self.row_data = row_data
        self.paginator = paginator
        super().__init__(label="Confirm", emoji="✅", style=discord.ButtonStyle.primary, disabled=row_data['type']=="redeem", row=2)
    async def callback(self, interaction: discord.Interaction):
        row = self.row_data
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
        
        if row['type'] == "boost" and row['redeemable_id'] not in ["ORGAN"]:
            async with pool.acquire() as conn:
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
                
                await conn.execute(
                    """INSERT INTO user_boosts (user_id, boost, amount)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (user_id, boost) DO UPDATE 
                    SET amount = user_boosts.amount + 1;
                    """, row['user_id'], row['redeemable_id'], 1)
                
                await conn.execute(
                    "UPDATE user_redeemables SET quantity = quantity-1 WHERE user_id = $1 AND redeemable_id = $2",
                    row['user_id'], row['redeemable_id'])
                
            embed = discord.Embed(
            title=f"✅ Effecto del cupón _{row['name']}_ canjeado!",
            description=f"",
            color=discord.Color.green()
            )
            await interaction.response.edit_message(embed=embed, view=None)
        
        elif row['type'] == "effect":
            if row['redeemable_id'] == "TCONT":
                async with pool.acquire() as conn:
                    while True:
                        new_card_id = await conn.fetchval("SELECT card_id FROM cards_idol ORDER BY RANDOM() LIMIT 1")
                        exists = await conn.fetchval("SELECT 1 FROM user_idol_cards WHERE card_id = $1",new_card_id)
                        if not exists:
                            break
                    

                    card = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", new_card_id)

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
                    
                    # Agregar carta al inventario
                    await conn.execute("""
                        INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id, p_skill, a_skill, s_skill, u_skill)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """, new_id, interaction.user.id, card["card_id"], card["idol_id"], card["set_id"], card["rarity_id"], p_skill, a_skill, s_skill, u_skill)
                    
                    await conn.execute(
                    "UPDATE user_redeemables SET quantity = quantity-1 WHERE user_id = $1 AND redeemable_id = $2",
                    row['user_id'], row['redeemable_id'])
                
                embed = discord.Embed(
                title=f"✅ Nueva carta obtenida!",
                description=f"**{card['idol_name']}** _{card['group_name']}_\n`{card['set_name']}`",
                color=discord.Color.green()
                )
                embed.set_footer(text=f"{card['card_id']}.{new_id}")
                c_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/d_no_image.jpg/{card['card_id']}.webp{version}"
                embed.set_image(url=c_url)
                await interaction.response.edit_message(embed=embed, view=None)
        
        else:
            embed = discord.Embed(
            title=f"❌ No se ha podido canjear el cupón",
            description=f"",
            color=discord.Color.light_gray()
            )
            await interaction.response.edit_message(embed=embed, view=None)
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                self.paginator.base_query,
                *self.paginator.query_params
            )
        embeds = await generate_redeemables_embeds(rows, pool, interaction)
        new_paginator = RedeemablesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_paginator.restart(interaction, True)   
        
class RedeemableGroupButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "RedeemablesInventoryEmbedPaginator", group):
        self.row_data = row_data
        self.paginator = paginator
        self.group = group
        super().__init__(label=group['name'], style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction):
        row = self.row_data
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
        
        embed = discord.Embed(
            title=f"¿Deseas usar tu cupón _{row['name']}_ en tu grupo *{self.group['name']}*?",
            description=f"{row['name']}: {row['quantity']}\n> {get_translation(language,f"inventory_description.{row['redeemable_id']}")}",
            color=discord.Color.teal()
            )
        
        view = discord.ui.View()
        
        view.add_item(ConfirmRedeemableGroupButton(self.row_data, self.paginator, self.group))
        
        view.add_item(BackToRedeemablesInventoryButton(self.paginator.base_query, self.paginator.query_params,self.paginator))
        
        await interaction.response.edit_message(
            embed=embed, view=view
        )
        return
        

class ConfirmRedeemableGroupButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "RedeemablesInventoryEmbedPaginator", group):
        self.row_data = row_data
        self.paginator = paginator
        self.group = group
        super().__init__(label="Confirmar", emoji="✅", style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        row = self.row_data
        
        async with pool.acquire() as conn:
            
            
            embed = discord.Embed(
                title="✅ Cupón canjeado correctamente",
                description="",
                color=discord.Color.dark_grey()
            )
            await interaction.response.edit_message(
                embed=embed, view=None
            )
            
            if row["redeemable_id"] == "MDCNT":
                extra_pop = random.randint(1,15)
                event_num = random.randint(1,14)
                
                idol_id = await conn.fetchval("SELECT idol_id FROM groups_members WHERE group_id = $1 ORDER BY RANDOM() LIMIT 1", self.group['group_id'])
                idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", idol_id)
                
                desc_response = get_translation(language, f"media_content.response_{extra_pop}", extra_pop=extra_pop)
                desc_event = get_translation(language, f"media_content.event_{event_num}", idol_name=idol_name, group_name=self.group['name'])
                
                await conn.execute(
                    "UPDATE groups SET permanent_popularity = permanent_popularity + $1 WHERE group_id = $2",
                    extra_pop, self.group['group_id']
                )
                
                desc = f"{desc_event}{desc_response}"
                await interaction.followup.send(
                    content=desc, ephemeral=False
                )
            
            elif row["redeemable_id"] == "EXCNT":
                
                popularity = int(self.group['popularity']) + int(self.group['permanent_popularity'])
                
                sponsor = base + mult*(popularity/(popularity+reduct))
                sponsor = int(sponsor*24)
                
                await conn.execute(
                    "UPDATE users SET credits = credits + $1 WHERE user_id = $2",
                    sponsor, self.group['user_id']
                )
                
                desc = f"## Has obtenido 💵 {format(sponsor,',')}"
                await interaction.followup.send(
                    content=desc, ephemeral=True
                )
                
                
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
            
            await conn.execute(
                "UPDATE user_redeemables SET quantity = quantity-1 WHERE user_id = $1 AND redeemable_id = $2",
                row['user_id'], row['redeemable_id'])
            rows = await conn.fetch(
                self.paginator.base_query,
                *self.paginator.query_params
            )

        embeds = await generate_redeemables_embeds(rows, pool, interaction)
        new_paginator = RedeemablesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_paginator.restart(interaction, True)
        
class BackToRedeemablesInventoryButton(discord.ui.Button):
    def __init__(
        self,
        base_query: str,
        query_params: list,
        paginator: "RedeemablesInventoryEmbedPaginator"
    ):
        super().__init__(label="Volver", style=discord.ButtonStyle.secondary, row=2)
        self.base_query = base_query
        self.query_params = query_params
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                self.paginator.base_query,
                *self.paginator.query_params
            )

        if not rows:
            return await interaction.response.edit_message(
                content="⚠️ No se encontraron cupones con estos filtros.",
                embed=None,
                view=None
            )

        embeds = await generate_redeemables_embeds(rows, pool, interaction)
        new_paginator = RedeemablesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        
        await new_paginator.restart(interaction, False)


# badges
async def generate_badges_embeds(rows: list[dict], pool, interaction) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    language = await get_user_language(interaction.user.id)
    
    for row in rows:
        is_selected = ""
        if row['is_selected']:
            is_selected = "✅ "
        
        embed = discord.Embed(
            title=f"{is_selected}{row['name']}",
            description=f"",
            color=discord.Color.teal()
        )

        image_url = (
            f"https://res.cloudinary.com/dyvgkntvd/image/upload/"
            f"f_webp,d_no_image.jpg/{row['badge_id']}.webp{version}"
        )
        #embed.set_thumbnail(url=image_url)

        embeds.append(embed)

    return embeds

class BadgesInventoryEmbedPaginator:
    def __init__(
        self,
        embeds: list[discord.Embed],
        rows: list[dict],
        interaction: discord.Interaction,
        base_query: str,
        query_params: tuple,
        embeds_per_page: int = 5
    ):
        self.all_embeds = embeds
        self.all_rows = rows
        self.interaction = interaction
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(embeds) + embeds_per_page - 1) // embeds_per_page
        self.current_page_embeds: list[discord.Embed] = []

        self.base_query = base_query
        self.query_params = query_params

    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        footer = discord.Embed(
            description=f"**Página** {self.current_page+1}/{self.total_pages}",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        rows_this_page = self.all_rows[start:end]

        for row in rows_this_page:
            if row['user_id'] == self.interaction.user.id:
                view.add_item(BadgeButton(row, self))

        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))
        return view

    async def start(self):
        self.current_page_embeds = self.get_page_embeds()
        await self.interaction.response.send_message(
            embeds=self.current_page_embeds,
            view=self.get_view(),
            ephemeral=True
        )

    async def restart(self, interaction: discord.Interaction, restart:bool):
        self.current_page = 0
        self.current_page_embeds = self.get_page_embeds()
        if restart:
            await interaction.followup.send(
                embeds=self.current_page_embeds,
                view=self.get_view(),
                ephemeral=True
            )
        else:
            await interaction.response.edit_message(
                embeds=self.current_page_embeds,
                view=self.get_view()
            )

    async def update(self, interaction: discord.Interaction):
        self.current_page_embeds = self.get_page_embeds()
        await interaction.response.edit_message(
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)

class BadgeButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "BadgesInventoryEmbedPaginator"):
        self.row_data = row_data
        self.paginator = paginator
        super().__init__(label=row_data['name'], style=discord.ButtonStyle.primary)
        
    async def callback(self, interaction: discord.Interaction):
        row = self.row_data
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
            
        embed = discord.Embed(
            title=f"¿Deseas mostrar esta insignia en tu perfil?",
            description=f"{row['name']}",
            color=discord.Color.teal()
        )
        
        view = discord.ui.View()
        view.add_item(ConfirmBadgeButton(self.row_data, self.paginator))
        view.add_item(BackToBadgesInventoryButton(self.paginator.base_query, self.paginator.query_params,self.paginator))
        
        await interaction.response.edit_message(
            embed=embed, view=view
        )

class ConfirmBadgeButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "BadgesInventoryEmbedPaginator"):
        self.row_data = row_data
        self.paginator = paginator
        super().__init__(label="Confirm", emoji="✅", style=discord.ButtonStyle.primary)
    async def callback(self, interaction: discord.Interaction):
        row = self.row_data
        language = await get_user_language(interaction.user.id)
        pool = get_pool()
        
        async with pool.acquire() as conn:
            #await conn.execute("""
            #    UPDATE user_missions um
            #    SET obtained = um.obtained + 1,
            #        last_updated = now()
            #    FROM missions_base mb
            #    WHERE um.mission_id = mb.mission_id
            #    AND um.user_id = $1
            #    AND um.status = 'active'
            #    AND mb.mission_type = 'redeem_coupon'
            #    """, interaction.user.id)
            
            await conn.execute("UPDATE user_badges SET is_selected = $1 WHERE user_id = $2",
                               False, interaction.user.id)
            
            await conn.execute(
                "UPDATE user_badges SET is_selected = $1 WHERE user_id = $2 AND badge_id = $3",
                True, interaction.user.id, row['badge_id'])
            
        embed = discord.Embed(
        title=f"✅ Insignia _{row['name']}_ asignada correctamente!",
        description=f"",
        color=discord.Color.dark_gray()
        )
        await interaction.response.edit_message(embed=embed, view=None)
        
        
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                self.paginator.base_query,
                *self.paginator.query_params
            )
        embeds = await generate_badges_embeds(rows, pool, interaction)
        new_paginator = BadgesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_paginator.restart(interaction, True)   
              
class BackToBadgesInventoryButton(discord.ui.Button):
    def __init__(
        self,
        base_query: str,
        query_params: list,
        paginator: "BadgesInventoryEmbedPaginator"
    ):
        super().__init__(label="Volver", style=discord.ButtonStyle.secondary, row=2)
        self.base_query = base_query
        self.query_params = query_params
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                self.paginator.base_query,
                *self.paginator.query_params
            )

        if not rows:
            return await interaction.response.edit_message(
                content="⚠️ No se encontraron cupones con estos filtros.",
                embed=None,
                view=None
            )

        embeds = await generate_badges_embeds(rows, pool, interaction)
        new_paginator = BadgesInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        
        await new_paginator.restart(interaction, False)

# - item_cards
async def generate_item_card_embeds(rows: list[dict], pool) -> list[discord.Embed]:
    embeds: list[discord.Embed] = []
    for row in rows:
        equipped_desc = ""
        async with pool.acquire() as conn:
            eq_data = await conn.fetchrow(
                f"SELECT * FROM groups_members WHERE {row['type']}_id = $1",
                f"{row['item_id']}.{row['unique_id']}"
            )
            if eq_data:
                group_name = await conn.fetchval(
                    "SELECT name FROM groups WHERE group_id = $1",
                    eq_data["group_id"]
                )
                idol_name = await conn.fetchval(
                    "SELECT name FROM idol_base WHERE idol_id = $1",
                    eq_data["idol_id"]
                )
                equipped_desc = f"\n> Equipped to: {idol_name} - {group_name}"

        title_prefix = "✅ " if row["status"] == "available" else ""
        embed = discord.Embed(
            title=f"{title_prefix}{row['name']} ⌛{row['durability']}",
            description=f"`{row['type'].capitalize()}`{equipped_desc}",
            color=discord.Color.teal()
        )

        image_url = (
            f"https://res.cloudinary.com/dyvgkntvd/image/upload/"
            f"f_webp,d_no_image.jpg/{row['item_id']}.webp{version}"
        )
        #embed.set_thumbnail(url=image_url)

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

    return embeds


class ItemInventoryEmbedPaginator:
    def __init__(
        self,
        embeds: list[discord.Embed],
        rows: list[dict],
        interaction: discord.Interaction,
        base_query: str,
        query_params: tuple,
        embeds_per_page: int = 3
    ):
        self.all_embeds = embeds
        self.all_rows = rows
        self.interaction = interaction
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(embeds) + embeds_per_page - 1) // embeds_per_page
        self.current_page_embeds: list[discord.Embed] = []

        self.base_query = base_query
        self.query_params = query_params

    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        footer = discord.Embed(
            description=f"### Total: {len(self.all_embeds)}\n**Página** {self.current_page+1}/{self.total_pages}",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        rows_this_page = self.all_rows[start:end]

        for row in rows_this_page:
            view.add_item(ItemCardDetailButton(row, self))

        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))
        return view

    async def start(self):
        self.current_page_embeds = self.get_page_embeds()
        await self.interaction.edit_original_response(
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def restart(self, interaction: discord.Interaction):
        self.current_page = 0
        self.current_page_embeds = self.get_page_embeds()
        await interaction.edit_original_response(
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def update(self, interaction: discord.Interaction):
        self.current_page_embeds = self.get_page_embeds()
        await interaction.response.edit_message(
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)

class ItemCardDetailButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "ItemInventoryEmbedPaginator"):
        self.row_data = row_data
        self.paginator = paginator
        self.item_id = row_data["item_id"]
        self.unique_id = row_data["unique_id"]
        label = f"{self.item_id}.{self.unique_id}"
        super().__init__(label=label, style=discord.ButtonStyle.primary)

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title=f"Detalles de {self.row_data['name']}",
            description=f"ID: `{self.item_id}.{self.unique_id}`\nTipo: `{self.row_data['type']}`\nDurabilidad: ⌛{self.row_data['durability']}",
            color=discord.Color.teal()
        )

        stats = [
            ("Vocal", self.row_data["plus_vocal"]),
            ("Rap", self.row_data["plus_rap"]),
            ("Dance", self.row_data["plus_dance"]),
            ("Visual", self.row_data["plus_visual"]),
            ("Energy", self.row_data["plus_energy"]),
        ]
        bonus_str = "\n".join(f"**{f'+{v}' if v > 0 else v}** {k}" for k, v in stats if v != 0)
        if bonus_str:
            embed.add_field(name="Bonos:", value=bonus_str, inline=False)

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{self.item_id}.webp{version}"
        #embed.set_thumbnail(url=image_url)

        view = ItemCardDetailView(
            row_data=self.row_data,
            query=self.paginator.base_query,
            params=self.paginator.query_params,
            paginator=self.paginator,
            status=self.row_data["status"]
        )

        await interaction.response.edit_message(embed=embed, view=view)


class ItemCardDetailView(discord.ui.View):
    def __init__(self, row_data: dict, query: str, params: list, paginator, status: str):
        super().__init__(timeout=120)

        self.add_item(EquipItemButton(row_data, paginator))
        self.add_item(UnequipItemButton(row_data, paginator))
        self.add_item(RefundItemButton(row_data, query, params, paginator))
        
        self.add_item(BackToItemInventoryButton(query, params, paginator))

class BackToItemInventoryButton(discord.ui.Button):
    def __init__(
        self,
        base_query: str,
        query_params: list,
        paginator: "ItemInventoryEmbedPaginator"
    ):
        super().__init__(label="Volver", style=discord.ButtonStyle.secondary, row=2)
        self.base_query = base_query
        self.query_params = query_params
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        # Volvemos a ejecutar la consulta original
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                self.paginator.base_query,
                *self.paginator.query_params
            )

        if not rows:
            return await interaction.response.edit_message(
                content="⚠️ No se encontraron ítems con estos filtros.",
                embed=None,
                view=None
            )

        embeds = await generate_item_card_embeds(rows, pool)
        new_paginator = ItemInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        # Reinciamos la paginación
        await new_paginator.restart(interaction)


class EquipItemButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "ItemInventoryEmbedPaginator"):
        super().__init__(label="Equipar", style=discord.ButtonStyle.primary)
        self.row_data = row_data
        self.paginator = paginator
        self.base_query = paginator.base_query
        self.query_params = paginator.query_params

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        # 1. Validar estado
        if self.row_data["status"] not in ("available", "equipped"):
            return await interaction.response.send_message(
                get_translation(language, "equip_idol.unavailable"),
                ephemeral=True
            )

        # 2. Buscar grupos activos
        async with pool.acquire() as conn:
            groups = await conn.fetch(
                """
                SELECT group_id, name
                FROM groups
                WHERE user_id = $1 AND status = 'active'
                """,
                user_id
            )

        # 3. Si no hay grupos, volvemos al inventario
        if not groups:
            view = discord.ui.View()
            view.add_item(BackToItemInventoryButton(self.paginator))
            return await interaction.response.edit_message(
                content=get_translation(language, "equip_item.no_groups"),
                embed=None,
                view=view
            )

        # 4. Mostrar selección de grupo
        embed = discord.Embed(
            title=get_translation(language, "equip_item.select_group_title"),
            description=get_translation(
                language, "equip_item.select_group_desc",
                item_name=self.row_data["name"],
                item_id=f"{self.row_data['item_id']}.{self.row_data['unique_id']}"
            ),
            color=discord.Color.blue()
        )
        view = SelectGroupForItemView(self.row_data, self.paginator)
        for g in groups:
            view.add_item(SelectGroupItemButton(self.row_data, g, self.paginator))

        # botón volver
        view.add_item(BackToItemInventoryButton(self.base_query, self.query_params, self.paginator))

        await interaction.response.edit_message(embed=embed, view=view)

class SelectGroupForItemView(discord.ui.View):
    def __init__(self, row_data: dict, paginator: "ItemInventoryEmbedPaginator"):
        super().__init__(timeout=120)
        self.row_data = row_data
        self.paginator = paginator


class SelectGroupItemButton(discord.ui.Button):
    def __init__(self, row_data: dict, group: dict, paginator: "ItemInventoryEmbedPaginator"):
        super().__init__(label=group["name"], style=discord.ButtonStyle.primary)
        self.row_data = row_data
        self.group = group
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)

        # Fetch miembros del grupo
        async with pool.acquire() as conn:
            members = await conn.fetch(
                """
                SELECT gm.idol_id, ib.name AS idol_name, gm.*
                FROM groups_members gm
                JOIN idol_base ib ON ib.idol_id = gm.idol_id
                WHERE gm.group_id = $1 AND gm.user_id = $2 ORDER BY gm.idol_id
                """,
                self.group["group_id"], interaction.user.id
            )

        slot_name = get_translation(language, f"equip_item.type_{self.row_data['type']}")
        # Construir vista de selección de idol
        embed = discord.Embed(
            title=get_translation(language, "equip_item.select_idol_title"),
            description=get_translation(language, "equip_item.select_idol_desc",
                                       slot_name=slot_name),
            color=discord.Color.blue()
        )
        view = discord.ui.View(timeout=120)
        for m in members:
            label = f"{m['idol_name']} ({m['idol_id']})"
            view.add_item(SelectMemberItemButton(self.row_data, self.group, m, self.paginator))
        # volver & cancelar
        view.add_item(BackToItemInventoryButton(self.paginator.base_query,self.paginator.query_params,self.paginator))

        await interaction.response.edit_message(embed=embed, view=view)

class SelectMemberItemButton(discord.ui.Button):
    def __init__(
        self,
        row_data: dict,
        group: dict,
        member: dict,
        paginator: "ItemInventoryEmbedPaginator"
    ):
        label = f"{member['idol_name']} ({member['idol_id']})"
        super().__init__(label=label, style=discord.ButtonStyle.success)
        self.row_data = row_data
        self.group = group
        self.member = member
        self.paginator = paginator
        self.base_query = paginator.base_query
        self.query_params = paginator.query_params

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()

        # Determinar slot según tipo
        slot_map = {
            "mic": "mic_id",
            "outfit": "outfit_id",
            "accessory": "accessory_id",
            "consumable": "consumable_id"
        }
        slot = slot_map.get(self.row_data["type"])
        if not slot:
            return await interaction.response.edit_message(
                content="❌ Tipo de ítem inválido.",
                view=None
            )

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'equip_card'
                """, interaction.user.id)
            # 1) Desequipar antiguo si existe
            old = await conn.fetchval(
                f"SELECT {slot} FROM groups_members WHERE group_id = $1 AND idol_id = $2",
                self.group["group_id"], self.member["idol_id"]
            )
            if old:
                await conn.execute(
                    "UPDATE user_item_cards SET status = 'available' WHERE unique_id = $1",
                    old.split(".")[1]
                )

            # 2) Equipar nuevo: limpiar en todo el grupo y poner en este miembro
            full_id = f"{self.row_data['item_id']}.{self.row_data['unique_id']}"
            await conn.execute(
                f"UPDATE groups_members SET {slot} = NULL WHERE {slot} = $1",
                full_id
            )
            await conn.execute(
                f"UPDATE groups_members SET {slot} = $1 WHERE group_id = $2 AND idol_id = $3",
                full_id, self.group["group_id"], self.member["idol_id"]
            )

            # 3) Marcar ítem como equipado
            await conn.execute(
                "UPDATE user_item_cards SET status = 'equipped' WHERE unique_id = $1",
                self.row_data["unique_id"]
            )

            rows = await conn.fetch(self.base_query, *self.query_params)
        embeds = await generate_item_card_embeds(rows, pool)
        new_p = ItemInventoryEmbedPaginator(
            embeds, rows, interaction,
            base_query=self.base_query,
            query_params=self.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_p.restart(interaction)

class CancelItemEquipButton(discord.ui.Button):
    def __init__(self, paginator: "ItemInventoryEmbedPaginator"):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.danger)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.paginator.restart(interaction)


class UnequipItemButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "ItemInventoryEmbedPaginator"):
        super().__init__(
            label="Desequipar",
            style=discord.ButtonStyle.danger,
            disabled=(row_data.get("status") != "equipped")
        )
        self.row_data = row_data
        self.paginator = paginator
        self.base_query = paginator.base_query
        self.query_params = paginator.query_params

    async def callback(self, interaction: discord.Interaction):
        # Vista de confirmación
        view = ConfirmUnequipItemView(self.row_data, self.paginator)
        embed = discord.Embed(
            title="⚠️ Confirmar Desequipar",
            description=(
                f"¿Seguro que quieres desequipar "
                f"`{self.row_data['item_id']}.{self.row_data['unique_id']}`?"
            ),
            color=discord.Color.orange()
        )
        await interaction.response.edit_message(embed=embed, view=view)


class ConfirmUnequipItemView(discord.ui.View):
    def __init__(self, row_data: dict, paginator: "ItemInventoryEmbedPaginator"):
        super().__init__(timeout=60)
        self.row_data = row_data
        self.paginator = paginator
        # Botones de confirmar y cancelar
        self.add_item(ConfirmUnequipItemButton(self))
        self.add_item(CancelUnequipItemButton(self))


class ConfirmUnequipItemButton(discord.ui.Button):
    def __init__(self, parent: ConfirmUnequipItemView):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        row = self.parent.row_data
        paginator = self.parent.paginator
        pool = get_pool()
        user_id = interaction.user.id

        # Determinar slot por tipo
        slot_map = {
            "mic": "mic_id",
            "outfit": "outfit_id",
            "accessory": "accessory_id",
            "consumable": "consumable_id",
        }
        slot = slot_map.get(row["type"])
        full_id = f"{row['item_id']}.{row['unique_id']}"

        async with pool.acquire() as conn:
            # 1) Quitar del grupo
            print(slot)
            print(full_id)
            await conn.execute(
                f"UPDATE groups_members SET {slot} = NULL WHERE user_id = $1 AND {slot} = $2",
                user_id, full_id
            )
            # 2) Marcar ítem como disponible
            await conn.execute(
                "UPDATE user_item_cards SET status = 'available' WHERE unique_id = $1",
                row["unique_id"]
            )
            # 3) Releer filas filtradas
            rows = await conn.fetch(paginator.base_query, *paginator.query_params)

        # 4) Regenerar inventario
        embeds = await generate_item_card_embeds(rows, pool)
        new_paginator = ItemInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=paginator.base_query,
            query_params=paginator.query_params,
            embeds_per_page=paginator.embeds_per_page
        )
        await new_paginator.restart(interaction)


class CancelUnequipItemButton(discord.ui.Button):
    def __init__(self, parent: ConfirmUnequipItemView):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        # Volver a la vista de detalles original
        row = self.parent.row_data
        paginator = self.parent.paginator

        embed = discord.Embed(
            title=f"Detalles de {row['name']}",
            description=(
                f"ID: `{row['item_id']}.{row['unique_id']}`\n"
                f"Tipo: `{row['type']}`\n"
                f"Durabilidad: ⌛{row['durability']}"
            ),
            color=discord.Color.teal()
        )
        stats = [
            ("Vocal", row["plus_vocal"]),
            ("Rap", row["plus_rap"]),
            ("Dance", row["plus_dance"]),
            ("Visual", row["plus_visual"]),
            ("Energy", row["plus_energy"]),
        ]
        bonus = "\n".join(f"**+{v}** {k}" for k, v in stats if v)
        if bonus:
            embed.add_field(name="Bonos:", value=bonus, inline=False)
        embed.set_thumbnail(
            url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/"
                f"f_webp,d_no_image.jpg/{row['item_id']}.webp{version}"
        )

        # Vista con los tres botones + volver
        view = discord.ui.View(timeout=120)
        view.add_item(BackToItemInventoryButton(paginator))
        view.add_item(EquipItemButton(row, paginator.base_query, paginator.query_params))
        view.add_item(
            UnequipItemButton(row, paginator),
        )
        view.add_item(
            RefundItemButton(row, paginator.base_query, paginator.query_params)
        )

        await interaction.response.edit_message(embed=embed, view=view)


class RefundItemButton(discord.ui.Button):
    def __init__(
        self,
        row_data: dict,
        base_query: str,
        query_params: list,
        paginator: "ItemInventoryEmbedPaginator"
    ):
        super().__init__(
            label="Refund",
            style=discord.ButtonStyle.secondary,
            custom_id="refund_item",
            disabled=(row_data.get("status") != "available")
        )
        self.row_data = row_data
        self.query = base_query
        self.params = query_params
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        uid = self.row_data["unique_id"]
        pool = get_pool()

        # 1) Verificar que el ítem sigue disponible
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_item_cards WHERE unique_id = $1 AND user_id = $2",
                uid, user_id
            )
        if not row or row["status"] != "available":
            return await interaction.response.edit_message(
                content="❌ Este ítem ya no está disponible.",
                embed=None,
                view=None
            )

        # 2) Obtener datos del ítem base para calcular refund
        async with pool.acquire() as conn:
            ref_data = await conn.fetchrow(
                "SELECT name, value, max_durability FROM cards_item WHERE item_id = $1",
                self.row_data["item_id"]
            )
        if not ref_data:
            return await interaction.response.edit_message(
                content="❌ No se encontró la información del ítem.",
                embed=None,
                view=None
            )

        # 3) Calcular refund y XP
        durability_ratio = row["durability"] / ref_data["max_durability"]
        base_value = ref_data["value"]
        refund_amount = int(base_value * durability_ratio * 2.5)
        xp_amount = max(base_value // 100, 1)

        # 4) Mostrar embed de confirmación
        name = ref_data["name"]
        embed = discord.Embed(
            title="🔁 Reembolso de ítem",
            description=(
                f"**{name}**\n"
                f"ID: `{self.row_data['item_id']}.{uid}`\n\n"
                f"Obtendrás:\n> **{format(refund_amount, ',')} 💵**\n"
                f"> **{xp_amount} XP**"
            ),
            color=discord.Color.gold()
        )
        view = ConfirmItemRefundView(
            user_id=user_id,
            unique_id=uid,
            refund=refund_amount,
            xp=xp_amount,
            base_query=self.query,
            query_params=self.params,
            paginator=self.paginator
        )
        return await interaction.response.edit_message(embed=embed, view=view)

class ConfirmItemRefundView(discord.ui.View):
    def __init__(
        self,
        user_id: int,
        unique_id: str,
        refund: int,
        xp: int,
        base_query: str,
        query_params: list,
        paginator: "ItemInventoryEmbedPaginator"
    ):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.unique_id = unique_id
        self.refund = refund
        self.xp = xp
        self.base_query = base_query
        self.query_params = query_params
        self.paginator = paginator

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        pool = get_pool()

        # 1) Verificar nuevamente disponibilidad
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM user_item_cards WHERE unique_id = $1 AND user_id = $2 AND status = 'available'",
                self.unique_id, self.user_id
            )
            if not row:
                return await interaction.response.edit_message(
                    content="❌ El ítem ya no está disponible.",
                    embed=None, view=None
                )
            # 2) Borrar de user_item_cards
            await conn.execute(
                "DELETE FROM user_item_cards WHERE unique_id = $1 AND user_id = $2",
                self.unique_id, self.user_id
            )
            # 3) Sumar créditos y XP al usuario
            await conn.execute(
                "UPDATE users SET credits = credits + $1, xp = xp + $2 WHERE user_id = $3",
                self.refund, self.xp, self.user_id
            )

        # 4) Regenerar inventario actualizado
        async with pool.acquire() as conn:
            rows = await conn.fetch(self.base_query, *self.query_params)
        embeds = await generate_item_card_embeds(rows, pool)
        new_paginator = ItemInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.base_query,
            query_params=self.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        return await new_paginator.restart(interaction)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        # Volver al inventario sin cambios
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(self.base_query, *self.query_params)
        embeds = await generate_item_card_embeds(rows, pool)
        new_paginator = ItemInventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.base_query,
            query_params=self.query_params,
            embeds_per_page=self.paginator.embeds_per_page
        )
        return await new_paginator.restart(interaction)



# - idol_cards
async def generate_idol_card_embeds(rows: list, pool, guild: discord.Guild, is_detailed:bool) -> list[discord.Embed]:
    """Genera una lista de embeds para cartas de idols."""
    card_counts = Counter([row['card_id'] for row in rows])
    embeds = []

    for row in rows:
        async with pool.acquire() as conn:
            idol_row = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", row["card_id"])
            idol_base_row = await conn.fetchrow("SELECT * FROM idol_base WHERE idol_id = $1", row["idol_id"])
            user_card_row = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", row['unique_id'])
            
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
        elif row['status'] == "giveaway":
            c_status = "🎁"

        RARITY_COLORS = {
            "Regular": discord.Color.light_gray(),
            "Special": discord.Color.purple(),
            "Limited": discord.Color.yellow(),
            "FCR": discord.Color.orange(),
            "POB": discord.Color.blue(),
            "Legacy": discord.Color.dark_purple(),
        }
        embed_color = RARITY_COLORS.get(c_rarity, discord.Color.default())

        cantidad_copias = ""
        if card_counts[row['card_id']] > 1:
            cantidad_copias = f" `x{card_counts[row['card_id']]} copias`"

        embed = discord.Embed(
            title=f"{name} - *{group_name}*{cantidad_copias} {blocked}{c_status}",
            description=f"{card_set} `{rarity}`",
            color=embed_color
        )

        image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['card_id']}.webp{version}"
        embed.set_thumbnail(url=image_url)

        skills = ""
        if user_card_row['p_skill']:
            skills += get_emoji(guild, "PassiveSkill")
        if user_card_row['a_skill']:
            skills += get_emoji(guild, "ActiveSkill")
        if user_card_row['s_skill']:
            skills += get_emoji(guild, "SupportSkill")
        if user_card_row['u_skill']:
            skills += get_emoji(guild, "UltimateSkill")

        vocal = idol_row['vocal'] - idol_base_row['vocal']
        rap = idol_row['rap'] - idol_base_row['rap']
        dance = idol_row['dance'] - idol_base_row['dance']
        visual = idol_row['visual'] - idol_base_row['visual']
        energy = idol_row['energy'] - 50

        if is_detailed:
            embed.add_field(name=f"**🎤 Vocal: {idol_base_row['vocal']} (+{vocal})**", value=f"**🎶 Rap: {idol_base_row['rap']} (+{rap})**", inline=True)
            embed.add_field(name=f"**💃 Dance: {idol_base_row['dance']} (+{dance})**", value=f"**✨ Visual: {idol_base_row['visual']} (+{visual})**", inline=True)
            embed.add_field(name=f"**⚡ Energy: 50 (+{energy})**", value=f"**Skills: {skills}**", inline=True)

        embed.set_footer(text=f"{row['card_id']}.{row['unique_id']}")
        embeds.append(embed)

    return embeds

class CardDetailButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "InventoryEmbedPaginator"):
        self.row_data = row_data
        self.card_id = row_data["card_id"]
        self.unique_id = row_data["unique_id"]
        label = f"{self.card_id}.{self.unique_id}"
        super().__init__(label=label, style=discord.ButtonStyle.primary)

        self.paginator = paginator
        self.base_query = paginator.base_query
        self.query_params = paginator.query_params

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        guild = interaction.guild
        
        async with pool.acquire() as conn:
            card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", self.unique_id)
            base_card_data = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", self.card_id)
            idol_base_row = await conn.fetchrow("SELECT * FROM idol_base WHERE idol_id = $1", base_card_data['idol_id'])
            
            rarity=""
            if base_card_data['rarity'] == "Regular":
                rarity = f"{base_card_data['rarity']} {base_card_data['rarity_id'][1]} - Lvl.{base_card_data['rarity_id'][2]}"
            else:
                rarity = f"{base_card_data['rarity']}"

        status = ""
        if card:
            if card['status'] == 'equipped':
                status = "👥"
            elif card['status'] == "trading":
                status = "🔄"
            elif card['status'] == "on_sale":
                status = "💲"
            elif card['status'] == "giveaway":
                status = "🎁"
            
            RARITY_COLORS = {
                "Regular": discord.Color.light_gray(),
                "Special": discord.Color.purple(),
                "Limited": discord.Color.yellow(),
                "FCR": discord.Color.orange(),
                "POB": discord.Color.blue(),
                "Legacy": discord.Color.dark_purple(),
            }
            embed_color = RARITY_COLORS.get(base_card_data['rarity'], discord.Color.default())
            
            embed = discord.Embed(
                title=f"{idol_base_row['name']} - _{base_card_data['group_name']}_ {status}",
                description=f"{base_card_data['set_name']} `{rarity}`",
                color=embed_color
            )
            
            vocal = base_card_data['vocal'] - idol_base_row['vocal']
            rap = base_card_data['rap'] - idol_base_row['rap']
            dance = base_card_data['dance'] - idol_base_row['dance']
            visual = base_card_data['visual'] - idol_base_row['visual']
            energy = base_card_data['energy'] - 50
            
            embed.add_field(name=f"**🎤 Vocal: {idol_base_row['vocal']} (+{vocal})**", value=f"**🎶 Rap: {idol_base_row['rap']} (+{rap})**", inline=True)
            embed.add_field(name=f"**💃 Dance: {idol_base_row['dance']} (+{dance})**", value=f"**✨ Visual: {idol_base_row['visual']} (+{visual})**", inline=True)
            embed.add_field(name=f"**⚡ Energy: 50 (+{energy})**", value=f"", inline=True)
            
            async with pool.acquire() as conn:
                if card['p_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['p_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    cond_energy=condition_values.get("energy")
                    cond_energy = int((cond_energy)*100) if cond_energy else None
                    pcond_extra_cost = condition_params.get("energy")
                    pcond_relative_cost = condition_params.get("energy")
                    pcond_relative_cost = int(round(pcond_relative_cost-1,2)*100) if pcond_relative_cost else None
                    
                    embed.add_field(name=f"**{get_emoji(guild, "PassiveSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            cond_vocal = condition_values.get("vocal"),
                                                            cond_rap = condition_values.get("rap"),
                                                            cond_dance = condition_values.get("dance"),
                                                            cond_visual = condition_values.get("visual"),
                                                            cond_energy = cond_energy,
                                                            cond_stat = condition_values.get("stat"),
                                                            cond_hype = condition_values.get("hype"),
                                                            cond_duration = condition_values.get("duration"),
                                                            pcond_vocal = condition_params.get("vocal"),
                                                            pcond_rap = condition_params.get("rap"),
                                                            pcond_dance = condition_params.get("dance"),
                                                            pcond_visual = condition_params.get("visual"),
                                                            pcond_hype = pcond_hype,
                                                            pcond_score = pcond_score,
                                                            pcond_extra_cost = pcond_extra_cost,
                                                            pcond_relative_cost = pcond_relative_cost,
                                                            pcond_value = condition_params.get("value")
                                                            ))
                if card['a_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['a_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    eff_params = json.loads(skill_data['params'])
                    eff = skill_data['effect']
                    cost_type = skill_data['cost_type']
                    lower = higher = relative_cost = extra_cost = ""
                    
                    pcond_energy = condition_params.get("energy")
                    if pcond_energy:
                        pcond_energy *= -1
                    
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = int(round(hype-1,2)*100) if hype else None
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    cond_energy=condition_values.get("energy")
                    cond_energy = int((cond_energy)*100) if cond_energy else None
                    
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = skill_data['energy_cost']
                    if eff == "boost_lower_stat":
                        lower = eff_params.get("value")
                    if eff == "boost_higher_stat":
                        higher = eff_params.get("value")
                    embed.add_field(name=f"**{get_emoji(guild, "ActiveSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            cond_vocal = condition_values.get("vocal"),
                                                            cond_rap = condition_values.get("rap"),
                                                            cond_dance = condition_values.get("dance"),
                                                            cond_visual = condition_values.get("visual"),
                                                            cond_energy = cond_energy,
                                                            cond_stat = condition_values.get("stat"),
                                                            cond_hype = condition_values.get("hype"),
                                                            cond_duration = condition_values.get("duration"),
                                                            pcond_vocal = condition_params.get("vocal"),
                                                            pcond_rap = condition_params.get("rap"),
                                                            pcond_dance = condition_params.get("dance"),
                                                            pcond_visual = condition_params.get("visual"),
                                                            pcond_energy = pcond_energy,
                                                            pcond_hype = pcond_hype,
                                                            pcond_score = pcond_score,
                                                            pcond_extra_cost = condition_params.get("energy"),
                                                            pcond_value = condition_params.get("value"),
                                                            higher=higher, lower=lower,
                                                            vocal=eff_params.get("vocal"),
                                                            rap=eff_params.get("rap"),
                                                            dance=eff_params.get('dance'),
                                                            visual=eff_params.get('visual'),
                                                            score=score,
                                                            hype=hype,
                                                            relative_cost=relative_cost,
                                                            extra_cost=extra_cost,
                                                            ))
                if card['s_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['s_skill'])
                    effect_data = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", skill_data['effect_id'])
                    if effect_data['hype_mod']:
                        hype = int(round(effect_data['hype_mod']-1,2)*100)
                    if effect_data['score_mod']:
                        score = int(round(effect_data['score_mod']-1,2)*100)
                    if effect_data['relative_cost']:
                        relative = int(round(effect_data['relative_cost']-1,2)*100)
                    embed.add_field(name=f"**{get_emoji(guild, "SupportSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            duration=skill_data['duration'], energy_cost=int(skill_data['energy_cost']),
                                                            highest = effect_data['highest_stat_mod'], lowest = effect_data['lowest_stat_mod'],
                                                            vocal = effect_data['plus_vocal'], rap = effect_data['plus_rap'],
                                                            dance = effect_data['plus_dance'], visual = effect_data['plus_visual'],
                                                            hype = hype, score = score,
                                                            extra_cost = effect_data['extra_cost'], relative_coost = relative
                                                            ))
                if card['u_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['u_skill'])
                    cost_type = skill_data['cost_type']
                    eff_params = json.loads(skill_data['params'])
                    lower = higher = relative_cost = extra_cost = ""
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = int(skill_data['energy_cost'] * -1)
                        
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = (int(round(hype-1,2)*100)) if hype else None
                    
                    embed.add_field(name=f"**{get_emoji(guild, "UltimateSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            higher=higher, lower=lower,
                                                            vocal=eff_params.get("vocal"),
                                                            rap=eff_params.get("rap"),
                                                            dance=eff_params.get('dance'),
                                                            visual=eff_params.get('visual'),
                                                            score=score,
                                                            hype=hype,
                                                            value=eff_params.get('value'),
                                                            relative_cost=relative_cost,
                                                            extra_cost=extra_cost,
                                                            ))
            
            
            image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{base_card_data['card_id']}.webp{version}"
            embed.set_image(url=image_url)
            embed.set_footer(text=f"{self.card_id}.{self.unique_id}")
            
            view = discord.ui.View()
            if card['user_id'] == interaction.user.id:
                view.add_item(EquipButton(self.row_data, self.paginator))
                view.add_item(DesequipButton(self.row_data, self.paginator))

            view.add_item(BackToInventoryButton(self.paginator))

            await interaction.response.edit_message(
                embed=embed,
                view=view
            )
        return

class BackToInventoryButton(discord.ui.Button):
    def __init__(self, paginator: "InventoryEmbedPaginator"):
        super().__init__(label="Volver", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(self.paginator.base_query, *self.paginator.query_params)

        if not rows:
            await interaction.response.edit_message(
                content="⚠️ No se encontraron cartas con esta búsqueda.",
                embed=None,
                view=None
            )
            return
        card_counts = Counter([row['card_id'] for row in rows])
        if self.paginator.is_duplicated:
            rows = [row for row in rows if card_counts[row['card_id']] >= 2]
        else:
            rows = [row for row in rows if card_counts[row['card_id']] >= 1]
            

        embeds = await generate_idol_card_embeds(rows, pool, interaction.guild, self.paginator.is_detailed)
        new_paginator = InventoryEmbedPaginator(
            embeds,
            rows,
            interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            is_duplicated=self.paginator.is_duplicated,
            is_detailed=self.paginator.is_detailed,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_paginator.restart(interaction)


class EquipButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "InventoryEmbedPaginator"):
        super().__init__(label="Equipar", style=discord.ButtonStyle.success)
        self.row_data = row_data
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        # Usamos exactamente la misma "card" que el comando:
        user_card = self.row_data

        # --- Inicia flujo de selección de grupo ---
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        # Validar estado
        if user_card["status"] not in ("available", "equipped"):
            return await interaction.response.send_message(
                get_translation(language, "equip_idol.unavailable"),
                ephemeral=True
            )

        # Buscar grupos donde este idol
        async with pool.acquire() as conn:
            groups = await conn.fetch(
                """
                SELECT g.group_id, g.name
                FROM groups g
                JOIN groups_members gm ON g.group_id = gm.group_id
                WHERE g.user_id = $1 AND gm.idol_id = $2 AND g.status = 'active'
                ORDER BY g.creation_date DESC
                """,
                user_id, user_card["idol_id"]
            )
            
            card = await conn.fetchrow(
                "SELECT * FROM cards_idol WHERE card_id = $1", user_card['card_id']
            )

        if not groups:
            view = discord.ui.View()
            view.add_item(BackToInventoryButton(self.paginator))
            return await interaction.response.edit_message(
                content=get_translation(language, "equip_idol.no_valid_groups"),
                embed=None,
                view=view
            )

        # Construir embed y vista de selección
        embed = discord.Embed(
            title=get_translation(language, "equip_idol.select_group_title"),
            description=get_translation(
                language, "equip_idol.select_group_desc",
                card_name=f"{card['idol_name']} `{card['set_name']}`"
            ),
            color=discord.Color.blue()
        )
        view = SelectGroupToEquipView(card, self.paginator)
        for g in groups:
            view.add_item(SelectGroupButton(user_card, g, self.paginator))
        view.add_item(BackToInventoryButton(self.paginator))

        # Editamos el mensaje original del inventario
        await interaction.response.edit_message(embed=embed, view=view)

class SelectGroupToEquipView(discord.ui.View):
    def __init__(self, card: dict, paginator: "InventoryEmbedPaginator"):
        super().__init__(timeout=120)
        self.card = card
        self.paginator = paginator

class SelectGroupButton(discord.ui.Button):
    def __init__(self, card: dict, group: dict, paginator: "InventoryEmbedPaginator"):
        super().__init__(label=group["name"], style=discord.ButtonStyle.primary)
        self.card = card
        self.group = group
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            member = await conn.fetchrow(
                "SELECT * FROM groups_members WHERE group_id = $1 AND user_id = $2 AND idol_id = $3",
                self.group["group_id"], user_id, self.card["idol_id"]
            )
            card_base = await conn.fetchrow(
                "SELECT * FROM cards_idol WHERE card_id = $1", self.card['card_id']
            )

        if not member:
            return await interaction.response.send_message(
                get_translation(language, "equip_idol.no_matching_members"),
                ephemeral=True
            )

        # Confirmación
        embed = discord.Embed(
            title=get_translation(language, "equip_idol.confirm_title"),
            description=get_translation(
                language, "equip_idol.confirm_desc",
                card_name=f"{card_base['idol_name']} ({self.card['unique_id']})",
                group_name=self.group["name"]
            ),
            color=discord.Color.orange()
        )
        view = ConfirmEquipIdolView(self.card, self.group["group_id"], self.card["idol_id"], self.paginator)
        await interaction.response.edit_message(embed=embed, view=view)

class ConfirmEquipIdolView(discord.ui.View):
    def __init__(self, card: dict, group_id: str, idol_id: str, paginator: "InventoryEmbedPaginator"):
        super().__init__(timeout=60)
        self.card = card
        self.group_id = group_id
        self.idol_id = idol_id
        self.paginator = paginator
        self.add_item(ConfirmEquipIdolButton(self))
        self.add_item(BackToInventoryButton(self.paginator))

class ConfirmEquipIdolButton(discord.ui.Button):
    def __init__(self, parent: ConfirmEquipIdolView):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        pool = get_pool()
        user_id = interaction.user.id
        language = await get_user_language(user_id)

        card_full_id = f"{self.parent.card['card_id']}.{self.parent.card['unique_id']}"
        # Obtener nombre para el mensaje final
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'equip_card'
                """, interaction.user.id)
            
            name_row = await conn.fetchrow(
                "SELECT idol_name FROM cards_idol WHERE card_id = $1", 
                self.parent.card["card_id"]
            )
            idol_name = name_row["idol_name"]

            # 1) Desequipar carta anterior
            old_card = await conn.fetchrow(
                "SELECT card_id FROM groups_members WHERE user_id = $1 AND idol_id = $2 AND group_id = $3",
                user_id, self.parent.idol_id, self.parent.group_id
            )
            if old_card['card_id']:
                old_id, old_u = old_card['card_id'].split(".")
                await conn.execute(
                    "UPDATE user_idol_cards SET status = 'available' WHERE unique_id = $1",
                    old_u
                )
                print("carta anterior desequipada")
            # 1.1) Desequipar de donde estuviera
            await conn.execute(
                "UPDATE groups_members SET card_id = NULL WHERE card_id = $1",
                card_full_id
            )
            # 2) Equipar en el grupo elegido
            await conn.execute(
                "UPDATE groups_members SET card_id = $1 WHERE user_id = $2 AND group_id = $3 AND idol_id = $4",
                card_full_id, user_id, self.parent.group_id, self.parent.idol_id
            )
            print("carta equipada")
            # 3) Marcar la carta como equipada
            await conn.execute(
                "UPDATE user_idol_cards SET status = 'equipped' WHERE unique_id = $1",
                self.parent.card["unique_id"]
            )
            print("status cambiado a: equipada")
            
            rows = await conn.fetch(
                self.parent.paginator.base_query,
                *self.parent.paginator.query_params
            )

        embeds = await generate_idol_card_embeds(rows, pool, interaction.guild, self.parent.paginator.is_detailed)

        new_paginator = InventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.parent.paginator.base_query,
            query_params=self.parent.paginator.query_params,
            embeds_per_page=self.parent.paginator.embeds_per_page,
            is_duplicated=self.parent.paginator.is_duplicated,
            is_detailed=self.parent.paginator.is_detailed
        )

        await new_paginator.restart(interaction)


class DesequipButton(discord.ui.Button):
    def __init__(self, row_data: dict, paginator: "InventoryEmbedPaginator"):
        super().__init__(
            label="Desequipar",
            style=discord.ButtonStyle.danger,
            disabled=row_data.get("status") != "equipped"
        )
        self.row_data = row_data
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        # Vista de confirmación
        embed = discord.Embed(
            title="⚠️ Confirmar desequipar",
            description=(
                f"¿Deseas desequipar la carta "
                f"`{self.row_data['card_id']}.{self.row_data['unique_id']}`?"
            ),
            color=discord.Color.orange()
        )
        view = ConfirmUnequipView(self.row_data, self.paginator)
        await interaction.response.edit_message(embed=embed, view=view)

class ConfirmUnequipView(discord.ui.View):
    def __init__(self, row_data: dict, paginator: "InventoryEmbedPaginator"):
        super().__init__(timeout=60)
        self.row_data = row_data
        self.paginator = paginator
        # Botones
        self.add_item(ConfirmUnequipButton(self))
        self.add_item(CancelUnequipButton(self.paginator))
        
class ConfirmUnequipView(discord.ui.View):
    def __init__(self, row_data: dict, paginator: "InventoryEmbedPaginator"):
        super().__init__(timeout=60)
        self.row_data = row_data
        self.paginator = paginator
        # Botones
        self.add_item(ConfirmUnequipButton(self))
        self.add_item(CancelUnequipButton(self.paginator))

class ConfirmUnequipButton(discord.ui.Button):
    def __init__(self, parent: ConfirmUnequipView):
        super().__init__(label="✅ Confirmar", style=discord.ButtonStyle.success)
        self.parent = parent  # tipo: ConfirmUnequipView

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        row = self.parent.row_data
        pool = get_pool()
        user_id = interaction.user.id
        unique_id = row["unique_id"]
        full_card_id = f"{row['card_id']}.{unique_id}"
        # idioma
        language = await get_user_language(user_id)

        async with pool.acquire() as conn:
            # 1) Quitar de groups_members
            await conn.execute(
                """
                UPDATE groups_members
                   SET card_id = NULL
                 WHERE user_id = $1
                   AND card_id = $2
                """,
                user_id, full_card_id
            )
            # 2) Marcar disponible en user_idol_cards
            await conn.execute(
                """
                UPDATE user_idol_cards
                   SET status = 'available'
                 WHERE unique_id = $1
                """,
                unique_id
            )
            # 3) Re-consultar las rows originales
            rows = await conn.fetch(self.parent.paginator.base_query,
                                    *self.parent.paginator.query_params)

        # 4) Regenerar embeds
        embeds = await generate_idol_card_embeds(rows, pool, interaction.guild, self.parent.paginator.is_detailed)
        new_pag = InventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.parent.paginator.base_query,
            query_params=self.parent.paginator.query_params,
            is_duplicated=self.parent.paginator.is_duplicated,
            is_detailed=self.parent.paginator.is_detailed,
            embeds_per_page=self.parent.paginator.embeds_per_page
        )
        # 5) Reiniciar el paginador
        await new_pag.restart(interaction)

class CancelUnequipButton(discord.ui.Button):
    def __init__(self, paginator: "InventoryEmbedPaginator"):
        super().__init__(label="❌ Cancelar", style=discord.ButtonStyle.secondary)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        # simplemente regenerar inventario
        pool = get_pool()
        rows = await pool.acquire().__aenter__()  # para simplificar…
        async with pool.acquire() as conn:
            rows = await conn.fetch(self.paginator.base_query,
                                    *self.paginator.query_params)
        embeds = await generate_idol_card_embeds(rows, pool, interaction.guild, self.paginator.is_detailed)
        new_pag = InventoryEmbedPaginator(
            embeds=embeds,
            rows=rows,
            interaction=interaction,
            base_query=self.paginator.base_query,
            query_params=self.paginator.query_params,
            is_duplicated=self.paginator.is_duplicated,
            is_detailed=self.paginator.is_detailed,
            embeds_per_page=self.paginator.embeds_per_page
        )
        await new_pag.restart(interaction)
        

class PreviousPageButton(discord.ui.Button):
    def __init__(self, paginator: "InventoryEmbedPaginator"):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.previous_page(interaction)

class NextPageButton(discord.ui.Button):
    def __init__(self, paginator: "InventoryEmbedPaginator"):
        super().__init__(label="➡️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.next_page(interaction)

class InventoryEmbedPaginator:
    def __init__(
        self,
        embeds: list[discord.Embed],
        rows: list[dict],
        interaction: discord.Interaction,
        base_query: str,
        query_params: tuple,
        is_duplicated: bool,
        is_detailed: bool,
        embeds_per_page: int = 3
    ):
        self.all_embeds = embeds
        self.all_rows = rows
        self.interaction = interaction
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(embeds) + embeds_per_page - 1) // embeds_per_page
        self.current_page_embeds: list[discord.Embed] = []

        self.base_query = base_query
        self.query_params = query_params
        self.is_duplicated = is_duplicated
        self.is_detailed = is_detailed
    
    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        # al final, pie de página con info de paginación
        footer = discord.Embed(
            description=f"### Total: {len(self.all_embeds)}\n**Página** {self.current_page+1}/{self.total_pages}",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        # botones de detalles para cada embed de carta (sin contar el footer)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        rows_this_page = self.all_rows[start:end]

        for row in rows_this_page:
            view.add_item(CardDetailButton(row, self))

        # navegación
        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))
        return view

    async def start(self):
        self.current_page_embeds = self.get_page_embeds()
        await self.interaction.edit_original_response(
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def restart(self, interaction: discord.Interaction):
        self.current_page = 0  # Reiniciar la página
        self.current_page_embeds = self.get_page_embeds()
        await interaction.edit_original_response(
            content="",
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def update(self, interaction: discord.Interaction):
        self.current_page_embeds = self.get_page_embeds()
        await interaction.response.edit_message(
            content="",
            embeds=self.current_page_embeds,
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)


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
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()
        guild = interaction.guild

        try:
            card_id, unique_id = card_id.split(".")
        except ValueError:
            return await interaction.response.send_message("❌ Formato inválido. Usa `id.unique_id`", ephemeral=True)

        async with pool.acquire() as conn:
            # Buscar primero como carta idol
            row = await conn.fetchrow("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = $1
            """, unique_id)

            if row:
                card_type = "idol"
                base_data = await conn.fetchrow("""
                    SELECT idol_name, set_name, rarity, group_name, rarity_id
                    FROM cards_idol WHERE card_id = $1
                """, row["card_id"])

                if not base_data:
                    return await interaction.response.send_message("❌ No se encontró la información de la carta.", ephemeral=True)

                
                card = await conn.fetchrow("SELECT * FROM user_idol_cards WHERE unique_id = $1", unique_id)
                base_card_data = await conn.fetchrow("SELECT * FROM cards_idol WHERE card_id = $1", row["card_id"])
                idol_base_row = await conn.fetchrow("SELECT * FROM idol_base WHERE idol_id = $1", base_card_data['idol_id'])
                
                rarity=""
                if base_card_data['rarity'] == "Regular":
                    rarity = f"{base_card_data['rarity']} {base_card_data['rarity_id'][1]} - Lvl.{base_card_data['rarity_id'][2]}"
                else:
                    rarity = f"{base_card_data['rarity']}"

                status = ""
                if card['status'] == 'equipped':
                    status = "👥"
                elif card['status'] == "trading":
                    status = "🔄"
                elif card['status'] == "on_sale":
                    status = "💲"
                elif card['status'] == "giveaway":
                    status = "🎁"
            
                
                user_row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", card['user_id'])    
                propietario = f"\nAgencia: **{user_row['agency_name']}**\n> CEO: <@{card['user_id']}>"
                
                RARITY_COLORS = {
                    "Regular": discord.Color.light_gray(),
                    "Special": discord.Color.purple(),
                    "Limited": discord.Color.yellow(),
                    "FCR": discord.Color.orange(),
                    "POB": discord.Color.blue(),
                    "Legacy": discord.Color.dark_purple(),
                }
                embed_color = RARITY_COLORS.get(base_card_data['rarity'], discord.Color.default())
                
                
                embed = discord.Embed(
                    title=f"{idol_base_row['name']} - _{base_card_data['group_name']}_ {status}",
                    description=f"{base_card_data['set_name']} `{rarity}`{propietario}",
                    color=embed_color
                )
                
                vocal = base_card_data['vocal'] - idol_base_row['vocal']
                rap = base_card_data['rap'] - idol_base_row['rap']
                dance = base_card_data['dance'] - idol_base_row['dance']
                visual = base_card_data['visual'] - idol_base_row['visual']
                energy = base_card_data['energy'] - 50
                
                embed.add_field(name=f"**🎤 Vocal: {idol_base_row['vocal']} (+{vocal})**", value=f"**🎶 Rap: {idol_base_row['rap']} (+{rap})**", inline=True)
                embed.add_field(name=f"**💃 Dance: {idol_base_row['dance']} (+{dance})**", value=f"**✨ Visual: {idol_base_row['visual']} (+{visual})**", inline=True)
                embed.add_field(name=f"**⚡ Energy: 50 (+{energy})**", value=f"", inline=True)
                
                
                if card['p_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['p_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    cond_energy=condition_values.get("energy")
                    cond_energy = int((cond_energy)*100) if cond_energy else None
                    pcond_extra_cost = condition_params.get("energy")
                    pcond_relative_cost = condition_params.get("energy")
                    pcond_relative_cost = int(round(pcond_relative_cost-1,2)*100) if pcond_relative_cost else None
                    
                    embed.add_field(name=f"**{get_emoji(guild, "PassiveSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            cond_vocal = condition_values.get("vocal"),
                                                            cond_rap = condition_values.get("rap"),
                                                            cond_dance = condition_values.get("dance"),
                                                            cond_visual = condition_values.get("visual"),
                                                            cond_energy = cond_energy,
                                                            cond_stat = condition_values.get("stat"),
                                                            cond_hype = condition_values.get("hype"),
                                                            cond_duration = condition_values.get("duration"),
                                                            pcond_vocal = condition_params.get("vocal"),
                                                            pcond_rap = condition_params.get("rap"),
                                                            pcond_dance = condition_params.get("dance"),
                                                            pcond_visual = condition_params.get("visual"),
                                                            pcond_hype = pcond_hype,
                                                            pcond_score = pcond_score,
                                                            pcond_extra_cost = pcond_extra_cost,
                                                            pcond_relative_cost = pcond_relative_cost,
                                                            pcond_value = condition_params.get("value")
                                                            ))
                if card['a_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['a_skill'])
                    condition_values = json.loads(skill_data['condition_values'])
                    condition_params = json.loads(skill_data['condition_params'])
                    eff_params = json.loads(skill_data['params'])
                    eff = skill_data['effect']
                    cost_type = skill_data['cost_type']
                    lower = higher = relative_cost = extra_cost = ""
                    
                    pcond_energy = condition_params.get("energy")
                    if pcond_energy:
                        pcond_energy *= -1
                    
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = int(round(hype-1,2)*100) if hype else None
                    
                    pcond_score=condition_params.get('score')
                    pcond_score = int(round(pcond_score-1,2)*100) if pcond_score else None
                    pcond_hype=condition_params.get('hype')
                    pcond_hype = int(round(pcond_hype-1,2)*100) if pcond_hype else None
                    cond_energy=condition_values.get("energy")
                    cond_energy = int((cond_energy)*100) if cond_energy else None
                    
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = skill_data['energy_cost']
                    if eff == "boost_lower_stat":
                        lower = eff_params.get("value")
                    if eff == "boost_higher_stat":
                        higher = eff_params.get("value")
                    embed.add_field(name=f"**{get_emoji(guild, "ActiveSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            cond_vocal = condition_values.get("vocal"),
                                                            cond_rap = condition_values.get("rap"),
                                                            cond_dance = condition_values.get("dance"),
                                                            cond_visual = condition_values.get("visual"),
                                                            cond_energy = cond_energy,
                                                            cond_stat = condition_values.get("stat"),
                                                            cond_hype = condition_values.get("hype"),
                                                            cond_duration = condition_values.get("duration"),
                                                            pcond_vocal = condition_params.get("vocal"),
                                                            pcond_rap = condition_params.get("rap"),
                                                            pcond_dance = condition_params.get("dance"),
                                                            pcond_visual = condition_params.get("visual"),
                                                            pcond_energy = pcond_energy,
                                                            pcond_hype = pcond_hype,
                                                            pcond_score = pcond_score,
                                                            pcond_extra_cost = condition_params.get("energy"),
                                                            pcond_value = condition_params.get("value"),
                                                            higher=higher, lower=lower,
                                                            vocal=eff_params.get("vocal"),
                                                            rap=eff_params.get("rap"),
                                                            dance=eff_params.get('dance'),
                                                            visual=eff_params.get('visual'),
                                                            score=score,
                                                            hype=hype,
                                                            relative_cost=relative_cost,
                                                            extra_cost=extra_cost,
                                                            ))
                if card['s_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['s_skill'])
                    effect_data = await conn.fetchrow("SELECT * FROM performance_effects WHERE effect_id = $1", skill_data['effect_id'])
                    if effect_data['hype_mod']:
                        hype = int(round(effect_data['hype_mod']-1,2)*100)
                    if effect_data['score_mod']:
                        score = int(round(effect_data['score_mod']-1,2)*100)
                    if effect_data['relative_cost']:
                        relative = int(round(effect_data['relative_cost']-1,2)*100) 
                    embed.add_field(name=f"**{get_emoji(guild, "SupportSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            duration=skill_data['duration'], energy_cost=int(skill_data['energy_cost']),
                                                            highest = effect_data['highest_stat_mod'], lowest = effect_data['lowest_stat_mod'],
                                                            vocal = effect_data['plus_vocal'], rap = effect_data['plus_rap'],
                                                            dance = effect_data['plus_dance'], visual = effect_data['plus_visual'],
                                                            hype = hype, score = score,
                                                            extra_cost = effect_data['extra_cost'], relative_coost = relative
                                                            ))
                if card['u_skill']:
                    skill_data = await conn.fetchrow("SELECT * FROM skills WHERE skill_name = $1", card['u_skill'])
                    cost_type = skill_data['cost_type']
                    eff_params = json.loads(skill_data['params'])
                    lower = higher = relative_cost = extra_cost = ""
                    if cost_type == "relative":
                        relative_cost = skill_data['energy_cost']
                        relative_cost = int((relative_cost)*100)
                    if cost_type == "fixed":
                        extra_cost = int(skill_data['energy_cost'] * -1)
                        
                    score=eff_params.get('score')
                    score = int(round(score-1,2)*100) if score else None
                    hype=eff_params.get('hype')
                    hype = (int(round(hype-1,2)*100)) if hype else None
                    
                    embed.add_field(name=f"**{get_emoji(guild, "UltimateSkill")} {skill_data['skill_name']}**",
                                    value=get_translation(language,
                                                            f"skills.{skill_data['skill_name']}",
                                                            higher=higher, lower=lower,
                                                            vocal=eff_params.get("vocal"),
                                                            rap=eff_params.get("rap"),
                                                            dance=eff_params.get('dance'),
                                                            visual=eff_params.get('visual'),
                                                            score=score,
                                                            hype=hype,
                                                            value=eff_params.get('value'),
                                                            relative_cost=relative_cost,
                                                            extra_cost=extra_cost,
                                                            ))
                
                
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{base_card_data['card_id']}.webp{version}"
                embed.set_image(url=image_url)
                embed.set_footer(text=f"{row["card_id"]}.{unique_id}")

            else:
                # Buscar como ítem
                row = await conn.fetchrow("""
                    SELECT * FROM user_item_cards
                    WHERE unique_id = $1
                """, unique_id)

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
                    value=f"> CEO: <@{row['user_id']}>",
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
                #embed.set_image(url=image_url)

        # Mostrar mensaje
        if not public:
            public = "F"
        publicc = public == "T"
        await interaction.response.send_message(embed=embed, ephemeral=not publicc)

    @app_commands.command(name="level_up", description="Combina dos cartas Regulares iguales para subir de nivel")
    @app_commands.describe(card_1="ej: IDLSETTR12.unique", card_2="ej: IDLSETTR12.unique")
    async def level_up(self, interaction: discord.Interaction, card_1: str, card_2: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
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
        cost = 1500 * nivel_actual
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
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        pool = await get_pool()

        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'view_fusion'
                """, interaction.user.id)
            
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

            success = sum(int((carta[0]*(carta[0]+1))/2) for carta in seleccionadas) * 5
            embed = discord.Embed(
                title=f"{idol_name} - {set_name}",
                description=f"{cmd}",
                color=discord.Color.teal()
            )
            posibles.append(embed)

        if not posibles:
            return await interaction.response.send_message("❌ No tienes combinaciones válidas para fusión.", ephemeral=True)

        paginator = Paginator(posibles)
        await paginator.start(interaction)

    @app_commands.command(name="fusion", description="Fusiona 3 cartas Regulares diferentes del mismo idol y set")
    @app_commands.describe(card_1="ej: IDLSETTR11.unique", card_2="ej: IDLSETTR21.unique", card_3="ej: IDLSETTR31.unique")
    async def fusion(self, interaction: discord.Interaction, card_1: str, card_2: str, card_3: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
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
            
            btfsn = await conn.fetchval("SELECT amount FROM user_boosts WHERE user_id = $1 AND boost = 'BTFSN'", user_id)

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
        
        success = 0.0
        for row in rows:
            nivel = int(row['rarity_id'][-1])
            if nivel == 3:
                chance = 0.95
            elif nivel == 2:
                chance = 0.75
            else:
                chance = 0.55
                
            if success == 0:
                success += chance
            else:
                success *= chance
        
        extra_success = 0.0
        plus_success = ""
        active_btfsn = False
        if btfsn:
            if btfsn >= 1:
                for row in rows:
                    nivel = int(row['rarity_id'][-1])
                    if nivel == 3:
                        chance = 1.00
                    elif nivel == 2:
                        chance = 0.85
                    else:
                        chance = 0.65
                    
                    if extra_success == 0:
                        extra_success += chance
                    else:
                        extra_success *= chance
                    
                extra_success -= success
                extra_success = int(extra_success*100)
                plus_success = f" (+{extra_success}%)"
                active_btfsn = True
                
        success = int(success*100)
        
        preview = discord.Embed(
            title="✨ Confirmar fusión",
            description=f"### Fusionarás 3 cartas regulares para obtener una carta **Special**.\n> Costo: 7,000 💵\nProbabilidad de éxito: {success}%{plus_success}",
            color=discord.Color.purple()
        )
        preview.set_thumbnail(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card_id}.webp{version}")
        preview.set_footer(text="Presiona Confirmar para continuar o Cancelar para detener el proceso.")

        view = ConfirmFusionView(user_id, uids, card_id, idol_id, set_id, rarity_id, success, active_btfsn)
        await interaction.response.send_message(embed=preview, view=view, ephemeral=True)

    @app_commands.command(name="refund", description="Solicita un reembolso por una carta u objeto")
    @app_commands.describe(card="ID de la carta/objeto con formato ID.unique")
    async def refund(self, interaction: discord.Interaction, card: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
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
                ref_data = await conn.fetchrow("SELECT name, value, max_durability FROM cards_item WHERE item_id = $1", row["item_id"])
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{row['item_id']}.webp{version}"

            if not ref_data:
                return await interaction.response.send_message("❌ No se encontró la información del ítem.", ephemeral=True)

            value = ref_data["value"]
            
            if item_type != "idol":
                durability = row['durability']/ref_data['max_durability']
                print(durability)
                value = int(value*durability)
            
            refund = int(value * 2.5)
            xp = max(value // 100,1)

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

    @app_commands.command(name="search", description="Buscar agencias que tengan una carta específica")
    @app_commands.describe(
        idol="Filter by idol",
        set_name="Filter by set",
        group="Filter by group",
        rarity="Filter by rarity",
        nivel="Filter by level (1-3)",
        status="Filter by status",
        is_locked="(✅/❌)",
        order_by="Sort by parameter",
        order="Sort direction (⏫/⏬)")
    @app_commands.choices(
        rarity=RARITY_CHOICES,
        status=STATUS_CHOICES,
        is_locked=IS_LOCKED_CHOICES,
        order_by=ORDER_BY_CHOICES,
        order=ORDER_CHOICES
    )
    async def search_card(
        self,
        interaction: discord.Interaction,
        idol: str = None,
        set_name: str = None,
        group: str = None,
        rarity: app_commands.Choice[str] = None,
        nivel: int = None,
        status: app_commands.Choice[str] = None,
        is_locked: app_commands.Choice[str] = None,
        order_by: app_commands.Choice[str] = None,
        order: app_commands.Choice[str] = None,
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()
        guild = interaction.guild

        base_query = """
            SELECT uc.*, ci.* FROM user_idol_cards uc
            JOIN cards_idol ci ON uc.card_id = ci.card_id
        """
        params = []
        idx = 1
        
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
        
        valid_order_by = ["uc.idol_id", "ci.idol_name", "uc.set_id", "uc.rarity_id", "uc.status", "uc.is_locked"]
        order_column = "uc.date_obtained"
        if order_by:
            if order_by.value in valid_order_by:
                order_column = order_by.value
        order_dir = "ASC"
        if order:
            order_dir = order.value
        if not order and not order_by:
            order_dir = "DESC"
        base_query += f" ORDER BY {order_column} {order_dir}"
        
        
        
        
        async with pool.acquire() as conn:
            rows = await conn.fetch(base_query, *params)


            if not rows:
                return await interaction.response.send_message("❌ No se encontró ninguna carta de este tipo", ephemeral=True)

            embeds = []
            for card in rows:
                c_rarity=""
                if card['rarity'] == "Regular":
                    c_rarity = f"{card['rarity']} {card['rarity_id'][1]} - Lvl.{card['rarity_id'][2]}"
                else:
                    c_rarity = f"{card['rarity']}"
                    
                status = ""
                if card['status'] == 'equipped':
                    status = "👥"
                elif card['status'] == "trading":
                    status = "🔄"
                elif card['status'] == "on_sale":
                    status = "💲"
                elif card['status'] == "giveaway":
                    status = "🎁"
                
                if card['is_locked']:
                    status += "🔐"
            
                
                user_row = await conn.fetchrow("SELECT * FROM users WHERE user_id = $1", card['user_id'])    
                propietario = f"\nAgencia: **{user_row['agency_name']}**\nCEO: <@{user_row['user_id']}>"
                
                RARITY_COLORS = {
                    "Regular": discord.Color.light_gray(),
                    "Special": discord.Color.purple(),
                    "Limited": discord.Color.yellow(),
                    "FCR": discord.Color.orange(),
                    "POB": discord.Color.blue(),
                    "Legacy": discord.Color.dark_purple(),
                }
                embed_color = RARITY_COLORS.get(card['rarity'], discord.Color.default())
                
                skills = ""
                if card['p_skill']:
                    skills += f"{get_emoji(guild, "PassiveSkill")}"
                if card['a_skill']:
                    skills += f"{get_emoji(guild, "ActiveSkill")}"
                if card['s_skill']:
                    skills += f"{get_emoji(guild, "SupportSkill")}"
                if card['u_skill']:
                    skills += f"{get_emoji(guild, "UltimateSkill")}"
                    
                embed = discord.Embed(
                    title=f"{skills} {card['idol_name']} - _{card['group_name']}_ {status}",
                    description=f"{card['set_name']} `{c_rarity}`{propietario}",
                    color=embed_color
                )
                
                
                image_url = f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{card['card_id']}.webp{version}"
                embed.set_thumbnail(url=image_url)
                
                
                embed.set_footer(text=f"{card["card_id"]}.{card['unique_id']}")
                embeds.append(embed)

        paginator = Paginator(embeds)
        await paginator.start(interaction)

    @search_card.autocomplete("idol")
    async def idol_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT idol_id, name FROM idol_base ORDER BY name ASC")
        return [
            app_commands.Choice(name=f"{row['name']} ({row['idol_id']})", value=row['idol_id'])
            for row in rows if current.lower() in f"{row['name'].lower()} ({row['idol_id'].lower()})"
        ][:25]

    @search_card.autocomplete("set_name")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT set_id, set_name FROM cards_idol ORDER BY set_name ASC")
        return [
            app_commands.Choice(name=row["set_name"], value=row["set_id"])
            for row in rows if current.lower() in row["set_name"].lower()
        ][:25]
    
    @search_card.autocomplete("group")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM cards_idol ORDER BY group_name ASC")
        return [
            app_commands.Choice(name=row["group_name"], value=row["group_name"])
            for row in rows if current.lower() in row["group_name"].lower()
        ][:25]


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
    def __init__(self, user_id, uids, new_card_id, idol_id, set_id, rarity_id, success, active_btfsn):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.uids = uids
        self.new_card_id = new_card_id
        self.idol_id = idol_id
        self.set_id = set_id
        self.rarity_id = rarity_id
        self.success = success
        self.active_btfsn = active_btfsn
        self.cost = 7000

    @discord.ui.button(label="✅ Confirmar", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        pool = await get_pool()
        xp = 150
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
            
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'try_fusion'
                """, interaction.user.id)

            msg = await interaction.response.edit_message(
                content="## 🔮 Realizando fusión...\n",
                embed=None,
                view=None
            )
            await asyncio.sleep(0.5)
            active_btfsn = False
            if self.active_btfsn:
                btfsn = await conn.fetchval("SELECT amount FROM user_boosts WHERE user_id = $1 AND boost = 'BTFSN'", self.user_id)
                
                if btfsn:
                    if btfsn >= 1:
                        active_btfsn = True
                        await conn.execute("UPDATE user_boosts SET amount = amount - 1 WHERE user_id = $1 AND boost = 'BTFSN'", self.user_id)
            
            success = True
            result = "## 🔮 Resultados:\n"
            for row in rows:
                level = int(row["rarity_id"][-1])
                chance = 0
                
                if level == 3:
                    chance = 95 if not active_btfsn else 100
                elif level == 2:
                    chance = 75 if not active_btfsn else 85
                else:
                    chance = 55 if not active_btfsn else 65
                    
                roll = random.randint(1, 100)
                print(chance,roll)
                emoji = f"\n✅ `{roll}/{chance}`" if roll <= chance else f"\n❌ `{roll}/{chance}`"
                result += f"{emoji} "
                
                if "❌" in emoji:
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
                retry_view = RetryFusionView(self.user_id, self.uids, self.new_card_id, self.idol_id, self.set_id, self.rarity_id, self.success)

                await interaction.followup.send(embed=embed_fail, view=retry_view, ephemeral=True)
                return


            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'fusion'
                """, interaction.user.id)
            
            await conn.execute("""
                DELETE FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, self.uids, self.user_id)

            await conn.execute("""
                UPDATE users SET credits = credits - $1, xp = xp + $2 WHERE user_id = $3
            """, self.cost, xp, self.user_id)

            skill_map = {"p_skill": "passive", "a_skill": "active", "s_skill": "support"}
            found_skills = []
            
            for row in rows:
                for column, skill_type in skill_map.items():
                    skill_name = row.get(column)
                    if skill_name:
                        found_skills.append((skill_type, skill_name))
                        break
            
            grouped = {}
            for skill_type, skill_name in found_skills:
                if skill_type not in grouped:
                    grouped[skill_type] = []
                grouped[skill_type].append(skill_name)
            
            chosen_types = list(grouped.keys())
            
            if len(chosen_types) >= 2:
                final_types = random.sample(chosen_types, 2)
                final_skills = {
                    "passive": random.choice(grouped["passive"]) if "passive" in final_types else None,
                    "active": random.choice(grouped["active"]) if "active" in final_types else None,
                    "support": random.choice(grouped["support"]) if "support" in final_types else None,
                }
                
            else:
                only_type = chosen_types[0]
                available_new = [t for t in ["passive", "active", "support"] if t != only_type]
                second_type = random.choice(available_new)
                
                final_skills = {
                    "passive": random.choice(grouped["passive"]) if only_type == "passive" else None,
                    "active": random.choice(grouped["active"]) if only_type == "active" else None,
                    "support": random.choice(grouped["support"]) if only_type == "support" else None,
                }
                
                skill_row = await conn.fetchrow("""
                    SELECT skill_name FROM skills WHERE skill_type = $1 ORDER BY RANDOM() LIMIT 1
                """, second_type)

                if skill_row:
                    final_skills[second_type] = skill_row["skill_name"]
                
            
            new_uid = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            await conn.execute("""
                INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id, p_skill, a_skill, s_skill)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, new_uid, self.user_id, self.new_card_id, self.idol_id, self.set_id, self.rarity_id, final_skills["passive"], final_skills["active"], final_skills["support"])
            
            idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", self.idol_id)
            set_name = await conn.fetchval("SELECT set_name FROM cards_idol WHERE set_id = $1", self.set_id)

        embed = discord.Embed(
            title="✨ Fusión completada con éxito!",
            description="🎉 Has obtenido una nueva carta **Special**",
            color=discord.Color.purple()
        )
        embed.add_field(name=f"**{idol_name}** _{set_name}_",value=f"`{self.new_card_id}.{new_uid}`", inline=False)
        embed.set_footer(text=f"✨ Has obtenido {xp} XP")
        embed.set_image(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{self.new_card_id}.webp{version}")

        await interaction.followup.send(embed=embed, ephemeral=False)

    @discord.ui.button(label="❌ Cancelar", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        await interaction.response.edit_message(content="❌ Fusión cancelada.", embed=None, view=None)

class RetryFusionView(discord.ui.View):
    def __init__(self, user_id, uids, card_id, idol_id, set_id, rarity_id, success):
        super().__init__(timeout=60)
        self.user_id = user_id
        self.uids = uids
        self.card_id = card_id
        self.idol_id = idol_id
        self.set_id = set_id
        self.rarity_id = rarity_id
        self.success = success

    @discord.ui.button(label="🔁 Intentar de nuevo", style=discord.ButtonStyle.primary)
    async def retry(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ No puedes usar este botón.", ephemeral=True)

        pool = get_pool()
        async with pool.acquire() as conn:
            btfsn = await conn.fetchval("SELECT amount FROM user_boosts WHERE user_id = $1 AND boost = 'BTFSN'", self.user_id)
            rows = await conn.fetch("""
                SELECT * FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, self.uids, self.user_id)
        temp_success = self.success/100
        
        extra_success = 0.0
        plus_success = ""
        active_btfsn = False
        if btfsn:
            if btfsn >= 1:
                for row in rows:
                    nivel = int(row['rarity_id'][-1])
                    if nivel == 3:
                        chance = 1.00
                    elif nivel == 2:
                        chance = 0.85
                    else:
                        chance = 0.65
                    
                    if extra_success == 0:
                        extra_success += chance
                    else:
                        extra_success *= chance
                    
                extra_success -= temp_success
                extra_success = int(extra_success*100)
                plus_success = f" (+{extra_success}%)"
                active_btfsn = True
                
        
        # reconstruir el mensaje inicial
        preview = discord.Embed(
            title="✨ Confirmar fusión",
            description=f"### Fusionarás 3 cartas regulares para obtener una carta **Special**.\n> Costo: 7,000 💵\nProbabilidad de éxito: {self.success}%{plus_success}",
            color=discord.Color.purple()
        )
        preview.set_thumbnail(url=f"https://res.cloudinary.com/dyvgkntvd/image/upload/f_webp,d_no_image.jpg/{self.card_id}.webp{version}")
        preview.set_footer(text="Presiona Confirmar para continuar o Cancelar para detener el proceso.")

        view = ConfirmFusionView(self.user_id, self.uids, self.card_id, self.idol_id, self.set_id, self.rarity_id, self.success, active_btfsn)
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
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'level_up'
                """, interaction.user.id)
            
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
                
            card_1 = rows[0]
            card_2 = rows[1]
            
            user_credits = await conn.fetchval("SELECT credits FROM users WHERE user_id = $1", interaction.user.id)
            
            if self.cost > user_credits:
                return await interaction.response.edit_message(
                    content=f"## ❌ No tienes créditos suificientes para realizar esta acción.",
                    embed=None,
                    view=None
                )
            
            def get_skill(card):
                for skill_type in ["p_skill", "a_skill", "s_skill"]:
                    if card[skill_type] is not None:
                        return skill_type, card[skill_type]
                return None, None

            skill1_type, skill1_value = get_skill(card_1)
            skill2_type, skill2_value = get_skill(card_2)
            
            if random.random() < 0.5:
                chosen_type, chosen_value = skill1_type, skill1_value
            else:
                chosen_type, chosen_value = skill2_type, skill2_value
            
            p_skill = a_skill = s_skill = None
            if chosen_type == "p_skill":
                p_skill = chosen_value
            elif chosen_type == "a_skill":
                a_skill = chosen_value
            elif chosen_type == "s_skill":
                s_skill = chosen_value
            
            # Eliminar las cartas originales
            await conn.execute("""
                DELETE FROM user_idol_cards
                WHERE unique_id = ANY($1::TEXT[]) AND user_id = $2
            """, [self.uid_1, self.uid_2], self.user_id)
            
            xp = 20 * (int(self.nuevo_card_id[-1]) - 1)
            # Aplicar costo
            await conn.execute("""
                UPDATE users SET credits = credits - $1, xp = xp + $2
                WHERE user_id = $3
            """, self.cost, xp, self.user_id)

            # Insertar nueva carta
            new_unique_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
            await conn.execute("""
                INSERT INTO user_idol_cards (unique_id, user_id, card_id, idol_id, set_id, rarity_id, p_skill, a_skill, s_skill)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """, new_unique_id, self.user_id, self.nuevo_card_id, self.idol_id, self.set_id, self.rarity_id, p_skill, a_skill, s_skill)

        # Mostrar resultado final
        final_embed = discord.Embed(
            title="✅ Carta mejorada con éxito",
            description=f"### {interaction.user.mention} ha obtenido una nueva carta de nivel {self.rarity_id[-1]}.",
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

async def setup(bot):
    bot.tree.add_command(InventoryGroup())
    bot.tree.add_command(CardGroup())
