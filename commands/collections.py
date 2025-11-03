import discord, logging, asyncio, random, string, datetime
from discord.ext import commands
from discord import app_commands
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool
from collections import defaultdict
from typing import List

RARITY_LIST = ["Regular", "Special", "Limited", "FCR", "POB", "Legacy"]  # Puedes ajustar si usas otras

class CollectionPaginator(discord.ui.View):
    def __init__(self, embeds: List[discord.Embed], user_id: int):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.user_id = user_id
        self.current_page = 0

        self.prev_button = discord.ui.Button(emoji="◀️", style=discord.ButtonStyle.secondary)
        self.next_button = discord.ui.Button(emoji="▶️", style=discord.ButtonStyle.secondary)

        self.prev_button.callback = self.go_prev
        self.next_button.callback = self.go_next

        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user_id

    async def go_prev(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    async def go_next(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % len(self.embeds)
        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

RARITY_CHOICES = [
        app_commands.Choice(name="Regular", value="Regular"),
        app_commands.Choice(name="Special", value="Special"),
        app_commands.Choice(name="Limited", value="Limited"),
        app_commands.Choice(name="FCR", value="FCR"),
        app_commands.Choice(name="POB", value="POB"),
    ]


class CollectionCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="collections", description="Consulta el progreso de tus cartas por set, rareza o idol.")
    @app_commands.describe(group="Nombre del grupo")
    async def collections(self, interaction: discord.Interaction, group: str = None):
        if interaction.guild is None:
            return await interaction.response.send_message(
                "❌ Este comando solo está disponible en servidores.", 
                ephemeral=True
            )
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()
        
        hidden = True

        
        
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE user_missions um
                SET obtained = um.obtained + 1,
                    last_updated = now()
                FROM missions_base mb
                WHERE um.mission_id = mb.mission_id
                AND um.user_id = $1
                AND um.status = 'active'
                AND mb.mission_type = 'view_collections'
                """, interaction.user.id)
            
            query = "SELECT * FROM cards_idol WHERE vocal > 1"
            params = []
            idx = 1
            
            if group:
                query += f" AND group_name = ${idx}"
                params.append(group)
                idx += 1
            
            query += " ORDER BY card_id"
        
        embeds, sorted_sets = await generate_sets_embeds(query, params, pool, interaction)  
        
        paginator = CollectionSetsPaginator(embeds,
                                        rows=sorted_sets,
                                        interaction=interaction,
                                        base_query=query,
                                        query_params=params)
        await paginator.start()

    @collections.autocomplete("group")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT group_name FROM cards_idol ORDER BY group_name ASC")
        return [
            app_commands.Choice(name=row["group_name"], value=row["group_name"])
            for row in rows if current.lower() in row["group_name"].lower()
        ][:25]

async def generate_sets_embeds(query, params, pool, interaction: discord.Interaction):
    async with pool.acquire() as conn:
        cards = await conn.fetch(query, *params)
        user_cards = await conn.fetch("SELECT card_id FROM user_idol_cards WHERE user_id = $1 AND is_locked = True", interaction.user.id)

    user_card_ids = {uc["card_id"] for uc in user_cards}
    user_regular_models = set()
    user_non_regular_ids = set()

    for card_id in user_card_ids:
        rarity_id = card_id[-3:]
        if rarity_id.startswith("R"):
            model_key = card_id[:7] + rarity_id[:2]
            user_regular_models.add(model_key)
        else:
            user_non_regular_ids.add(card_id)
    
    
    
    idol = None
    """
    # Combinaciones múltiples permitidas
    if set_name and rarity and idol:
        # 1. SET + RAREZA + IDOL
        filtered_cards = [c for c in cards if c["set_name"].lower() == set_name.lower() and c["rarity"] == rarity and c["idol_id"].lower() == idol.lower()]
        if not filtered_cards:
            await interaction.response.send_message("❌ No hay cartas con esos filtros.", ephemeral=True)
            return
        description = ""
        if rarity == "Regular":
            for model in ["R1", "R2", "R3"]:
                model_card = next((c for c in filtered_cards if c["rarity_id"].startswith(model)), None)
                if model_card:
                    model_key = model_card["idol_id"] + model_card["set_id"] + model
                    owned = model_key in user_regular_models
                    description += f"{'✅' if owned else '❌'} {model_card['rarity']} {model[-1]}\n"
        else:
            for c in filtered_cards:
                owned = c["card_id"] in user_non_regular_ids
                description += f"{'✅' if owned else '❌'} {c['rarity']}\n"

        embed = discord.Embed(
            title=f"{idol} - {set_name} ({rarity})",
            description=description,
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=hidden)
        return

    elif set_name and rarity and not idol:
        # 2. SET + RAREZA
        filtered_cards = [c for c in cards if c["set_name"].lower() == set_name.lower() and c["rarity"] == rarity]
        if not filtered_cards:
            await interaction.response.send_message("❌ No hay cartas con esos filtros.", ephemeral=True)
            return

        idols = defaultdict(lambda: {"owned": 0, "total": 0, "_counted": set()})
        for card in filtered_cards:
            idol_key = f"{card['idol_name']}|{card['idol_id']}"
            if rarity == "Regular":
                model_key = card["rarity_id"][:2]
                unique_model_id = card["idol_id"] + card["set_id"] + model_key
                if model_key not in idols[idol_key]["_counted"]:
                    idols[idol_key]["_counted"].add(model_key)
                    idols[idol_key]["total"] += 1
                    if unique_model_id in user_regular_models:
                        idols[idol_key]["owned"] += 1
            else:
                idols[idol_key]["total"] += 1
                if card["card_id"] in user_non_regular_ids:
                    idols[idol_key]["owned"] += 1

        description = ""
        for idol_key, data in sorted(idols.items()):
            name = idol_key.split("|")[0]
            percent = round(data["owned"] / data["total"] * 100, 2) if data["total"] else 0
            description += f"**{name}** - ({data['owned']}/{data['total']})\n"

        embed = discord.Embed(
            title=f"{rarity} - {set_name}",
            description=description,
            color=discord.Color.purple()
        )
        await interaction.response.send_message(embed=embed, ephemeral=hidden)
        return

    elif set_name and idol and not rarity:
        # 3. SET + IDOL
        filtered_cards = [c for c in cards if c["set_name"].lower() == set_name.lower() and c["idol_id"].lower() == idol.lower()]
        if not filtered_cards:
            await interaction.response.send_message("❌ Ese idol no tiene cartas en ese set.", ephemeral=True)
            return

        grouped = defaultdict(list)
        for card in filtered_cards:
            grouped[card["rarity"]].append(card)

        description = ""
        completed = True
        for rarity in RARITY_LIST:
            if rarity not in grouped:
                continue
            if rarity == "Regular":
                for model in ["R1", "R2", "R3"]:
                    card = next((c for c in grouped[rarity] if c["rarity_id"].startswith(model)), None)
                    if card:
                        model_key = card["idol_id"] + card["set_id"] + model
                        owned = model_key in user_regular_models
                        description += f"`{card['card_id']}` - {'✅' if owned else '❌'} {rarity} {model[-1]}\n"
                        if not owned:
                            completed = False
            else:
                card = grouped[rarity][0]
                owned = card["card_id"] in user_non_regular_ids
                description += f"`{card['card_id']}` - {'✅' if owned else '❌'} {rarity}\n"
                if not owned:
                    completed = False
        async with pool.acquire() as conn:
            idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", idol)
        embed = discord.Embed(
            title=f"{idol_name} ({idol}) - {set_name}",
            description=description,
            color=discord.Color.teal()
        )
        badge_id = have_it = None
        if completed:
            async with pool.acquire() as conn:
                set_id = await conn.fetchval("SELECT set_id FROM cards_idol WHERE set_name = $1", set_name)
                badge_id = await conn.fetchval(
                    "SELECT badge_id FROM badges WHERE set_id = $1 AND idol_id = $2",
                    set_id, idol
                )
                if badge_id:
                    have_it = await conn.fetch("SELECT 1 FROM user_badges WHERE badge_id = $1 AND user_id = $2",
                                            badge_id, interaction.user.id)
                    embed.set_footer(text="✅ Idol completo en este set")
                else:
                    have_it = True
                    embed.set_footer(text="Este set no tiene recompensas individuales")
                
                
                await interaction.response.send_message(embed=embed, ephemeral=hidden)
                
                if not have_it:
                    await conn.execute("INSERT INTO user_badges (user_id, badge_id) VALUES ($1, $2)",
                                    interaction.user.id, badge_id)
                    await conn.execute("UPDATE users SET credits = credits + 5000, xp = xp + 50")
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    await conn.execute(
                        "INSERT INTO players_packs (pack_id, user_id, unique_id, buy_date) VALUES ('MST', $1, $2, $3)",
                        interaction.user.id, new_id, now)
                
                    await interaction.followup.send(
                        content=f"## ⭐ Has completado todas las cartas de _{idol_name} ({idol})_ del set _{set_name}_\n_Has recibido 💵5,000 y 50 XP y un **Mini Star Pack**_",
                        ephemeral=True)
        else:
            embed.set_footer(text="❌ Aún te faltan cartas de este idol en el set")
            await interaction.response.send_message(embed=embed, ephemeral=hidden)
            
        
        return

    elif rarity and idol and not set_name:
        # 4. RAREZA + IDOL
        filtered_cards = [c for c in cards if c["rarity"] == rarity and c["idol_id"].lower() == idol.lower()]
        if not filtered_cards:
            await interaction.response.send_message("❌ Ese idol no tiene cartas de esa rareza.", ephemeral=True)
            return

        by_set = defaultdict(lambda: {"owned": 0, "total": 0, "_counted": set()})
        for card in filtered_cards:
            set_key = card["set_name"]
            if rarity == "Regular":
                model_key = card["rarity_id"][:2]
                unique_model_id = card["idol_id"] + card["set_id"] + model_key
                if model_key not in by_set[set_key]["_counted"]:
                    by_set[set_key]["_counted"].add(model_key)
                    by_set[set_key]["total"] += 1
                    if unique_model_id in user_regular_models:
                        by_set[set_key]["owned"] += 1
            else:
                by_set[set_key]["total"] += 1
                if card["card_id"] in user_non_regular_ids:
                    by_set[set_key]["owned"] += 1

        description = ""
        for set_name, data in sorted(by_set.items()):
            percent = round(data["owned"] / data["total"] * 100, 2) if data["total"] else 0
            description += f"**{set_name}** - ({data['owned']}/{data['total']})\n"

        embed = discord.Embed(
            title=f"{idol} - Rareza: {rarity}",
            description=description,
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=hidden)
        return

    elif idol and not set_name and not rarity:
        filtered_cards = [c for c in cards if c["idol_id"].lower() == idol.lower()]
        if not filtered_cards:
            await interaction.response.send_message("❌ Ese idol no tiene cartas registradas.", ephemeral=True)
            return

        sets = defaultdict(lambda: {"owned": 0, "total": 0, "_counted": set()})

        for card in filtered_cards:
            set_key = (card["set_id"], card["set_name"])
            is_regular = card["rarity"] == "Regular"

            if is_regular:
                model_key = card["idol_id"] + card["set_id"] + card["rarity_id"][:2]
                if model_key not in sets[set_key]["_counted"]:
                    sets[set_key]["_counted"].add(model_key)
                    sets[set_key]["total"] += 1
                    if model_key in user_regular_models:
                        sets[set_key]["owned"] += 1
            else:
                sets[set_key]["total"] += 1
                if card["card_id"] in user_non_regular_ids:
                    sets[set_key]["owned"] += 1

        sorted_sets = sorted(sets.items(), key=lambda x: x[0][1])
        embeds = []
        chunk_size = 10

        for i in range(0, len(sorted_sets), chunk_size):
            i_desc = ""
            for (set_id, set_name), data in sorted_sets[i:i + chunk_size]:
                percent = round(data["owned"] / data["total"] * 100, 2) if data["total"] else 0
                i_desc += f"\n[`{percent}%`] **{set_name}** - ({data['owned']}/{data['total']})"
            embed = discord.Embed(
                title=f"📘 Colecciones de {idol}",
                description=i_desc,
                color=discord.Color.dark_teal()
            )
            embed.set_footer(text=f"Página {i//chunk_size + 1} / {(len(sorted_sets)-1)//chunk_size + 1}")
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.response.send_message(embed=embeds[0], ephemeral=hidden)
        else:
            view = CollectionPaginator(embeds, user_id)
            await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=hidden)
        return

    # === CASO: Solo se indica set ===
    elif set_name and not rarity and not idol:
        idols_in_set = defaultdict(lambda: {"owned": 0, "total": 0, "_counted": set(), "_owned": set()})
        total_in_set = set()
        owned_in_set = set()

        for card in cards:
            if card["set_name"].lower() != set_name.lower():
                continue

            idol_key = f"{card['idol_name']}|{card['idol_id']}"
            is_regular = card["rarity"] == "Regular"
            key = card["card_id"]

            if is_regular:
                model_key = card["rarity_id"][:2]  # Rm
                unique_model_id = f"{card['idol_id']}{card['set_id']}{model_key}"
                total_in_set.add(unique_model_id)

                if model_key not in idols_in_set[idol_key]["_counted"]:
                    idols_in_set[idol_key]["_counted"].add(model_key)
                    idols_in_set[idol_key]["total"] += 1

                if unique_model_id in user_regular_models and model_key not in idols_in_set[idol_key]["_owned"]:
                    idols_in_set[idol_key]["owned"] += 1
                    idols_in_set[idol_key]["_owned"].add(model_key)
                    owned_in_set.add(unique_model_id)
            else:
                total_in_set.add(key)
                idols_in_set[idol_key]["total"] += 1
                if key in user_non_regular_ids:
                    idols_in_set[idol_key]["owned"] += 1
                    owned_in_set.add(key)

        # ✅ Verificación del set completo
        set_completed = total_in_set == owned_in_set
        members_amount = int(len(total_in_set)/7)


        s_desc = ""
        for idol_key, data in sorted(idols_in_set.items(), key=lambda x: x[0]):
            idol_name = idol_key.split("|")[0]
            s_desc += f"\n[`{round(int(data['owned'])/int(data['total'])*100,2)}%`] **{idol_name}** - ({data['owned']}/{data['total']})"

        embed = discord.Embed(
            title=f"📦 Cartas en el set: {set_name}",
            description=s_desc,
            color=discord.Color.green()
        )
        
        if set_completed:
            async with pool.acquire() as conn:
                set_id = await conn.fetchval("SELECT set_id FROM cards_idol WHERE set_name = $1", set_name)
                badge_id = await conn.fetchval("SELECT badge_id FROM badges WHERE set_id = $1 AND idol_id = ''",
                                                set_id)
                if badge_id:
                    have_it = await conn.fetch("SELECT 1 FROM user_badges WHERE badge_id = $1 AND user_id = $2",
                                            badge_id, interaction.user.id)
                    embed.set_footer(text="✅ ¡Set completo!")
                else:
                    have_it = True
                    embed.set_footer(text="Este set no tiene recompensa grupal")
                
                
                await interaction.response.send_message(embed=embed, ephemeral=hidden)
                
                if not have_it:
                    await conn.execute("INSERT INTO user_badges (user_id, badge_id) VALUES ($1, $2)",
                                    interaction.user.id, badge_id)
                    
                    credits_given = 3000 * members_amount
                    xp = 25 * members_amount
                    
                    if credits_given > 50000:
                        credits_given = 50000
                    
                    await conn.execute("UPDATE users SET credits = credits + $1, xp = xp + $2", credits_given, xp)
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    await conn.execute(
                        "INSERT INTO players_packs (pack_id, user_id, unique_id, buy_date) VALUES ('STR', $1, $2, $3)",
                        interaction.user.id, new_id, now)
                
                    await interaction.followup.send(
                        content=f"## ⭐ Has completado todas las cartas del set _{set_name}_\n_Has recibido 💵{format(credits_given,',')} y {xp} XP y un **Star Pack**_",
                        ephemeral=True)
            
        else:
            embed.set_footer(text="❌ Aún no tienes todas las cartas del set.")
            await interaction.response.send_message(embed=embed, ephemeral=hidden)
        return
    
    elif rarity and not set_name and not idol:
        # 1) Filtramos por rareza
        filtered = [c for c in cards if c["rarity"] == rarity]

        # 2) Contamos owned / total por set
        by_set = defaultdict(lambda: {"owned": 0, "total": 0})
        for c in filtered:
            key = (c["set_id"], c["set_name"])
            by_set[key]["total"] += 1

            if c["rarity"] != "Regular":
                if c["card_id"] in user_non_regular_ids:
                    by_set[key]["owned"] += 1
            else:
                model_key = c["idol_id"] + c["set_id"] + c["rarity_id"][:2]
                if model_key in user_regular_models:
                    by_set[key]["owned"] += 1

        # 3) Creamos los embeds paginados igual que en el default
        embeds = []
        sorted_sets = sorted(by_set.items(), key=lambda x: x[0][1])
        chunk_size = 10

        for i in range(0, len(sorted_sets), chunk_size):
            desc = ""
            for (set_id, set_name), data in sorted_sets[i:i + chunk_size]:
                pct = round(data["owned"] / data["total"] * 100, 2) if data["total"] else 0
                desc += f"[`{pct}%`] **{set_name}** - ({data['owned']}/{data['total']})\n"

            embed = discord.Embed(
                title=f"🎴 Rareza: {rarity}",
                description=desc,
                color=discord.Color.green()
            )
            total_pages = (len(sorted_sets) - 1) // chunk_size + 1
            embed.set_footer(text=f"Página {i//chunk_size + 1} / {total_pages}")
            embeds.append(embed)

        # 4) Enviamos embed o paginador
        if len(embeds) == 1:
            await interaction.response.send_message(embed=embeds[0], ephemeral=hidden)
        else:
            view = CollectionPaginator(embeds, user_id)
            await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=hidden)

        return
    """
    
    # === CASO: Sin parámetros ===
    sets = defaultdict(lambda: {"total": 0, "owned": 0})
    seen_regular_models = set()
    
    for card in cards:
        set_key = (card["set_id"], card["set_name"])
        is_regular = card["rarity"] == "Regular"

        if is_regular:
            model_key = card["idol_id"] + card["set_id"] + card["rarity_id"][:2]
            if model_key in seen_regular_models:
                continue
            seen_regular_models.add(model_key)
            sets[set_key]["total"] += 1
            if model_key in user_regular_models:
                sets[set_key]["owned"] += 1
        else:
            sets[set_key]["total"] += 1
            if card["card_id"] in user_non_regular_ids:
                sets[set_key]["owned"] += 1

    embeds = []
    sorted_sets = sorted(sets.items(), key=lambda x: x[0][1])
    chunk_size = 1
    for i in range(0, len(sorted_sets)):
        i_desc = ""
        for (set_id, set_name), info in sorted_sets[i:i + 1]:
            i_desc += f"\n[`{round(int(info['owned'])/int(info['total'])*100,2)}%`] - ({info['owned']}/{info['total']})"
        async with pool.acquire() as conn:
            group_name = await conn.fetchval("SELECT group_name FROM cards_idol WHERE set_name = $1", set_name)
        embed = discord.Embed(
            title=f"{group_name} - {set_name}",
            description=i_desc,
            color=discord.Color.green()
        )
        embeds.append(embed)
    
    return embeds, sorted_sets
        

class CollectionSetsPaginator:
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
        self.base_query = base_query
        self.query_params = query_params

    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        footer = discord.Embed(
            description=f"Página {self.current_page+1}/{self.total_pages} • Total: {len(self.all_embeds)}",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        for row in self.all_rows[start:end]:
            view.add_item(SetButton(set_id=row[0][0], set_name=row[0][1], base_query=self.base_query, query_params=self.query_params))
        view.add_item(PreviousSetPageButton(self))
        view.add_item(NextSetPageButton(self))
        return view

    async def start(self):
        await self.interaction.response.send_message(
            content="",
            embeds=self.get_page_embeds(),
            view=self.get_view(),
            ephemeral=True
        )

    async def restart(self):
        self.current_page = 0
        await self.interaction.response.edit_message(
            embeds=self.get_page_embeds(),
            view=self.get_view()
        )

    async def update(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embeds=self.get_page_embeds(),
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)

class PreviousSetPageButton(discord.ui.Button):
    def __init__(self, paginator: CollectionSetsPaginator):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.previous_page(interaction)

class NextSetPageButton(discord.ui.Button):
    def __init__(self, paginator: CollectionSetsPaginator):
        super().__init__(label="➡️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.next_page(interaction)


class SetButton(discord.ui.Button):
    def __init__(self, set_id: str, set_name: str, base_query, query_params):
        super().__init__(label=f"{set_name}", style=discord.ButtonStyle.primary)
        self.set_id = set_id
        self.set_name = set_name
        self.base_query = base_query
        self.query_params = query_params

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pool = get_pool()
        embed = already_active = None
        
        async with pool.acquire() as conn:
            query = "SELECT * FROM cards_idol WHERE set_id = $1 ORDER BY idol_id"
            params = [self.set_id]
            cards = await conn.fetch(query, *params)
            user_cards = await conn.fetch("SELECT card_id FROM user_idol_cards WHERE user_id = $1 AND is_locked = True", user_id)
            
        idols_in_set = defaultdict(lambda: {"owned": 0, "total": 0, "_counted": set(), "_owned": set()})
        total_in_set = set()
        owned_in_set = set()
        
        

        user_card_ids = {uc["card_id"] for uc in user_cards}
        user_regular_models = set()
        user_non_regular_ids = set()

        for card_id in user_card_ids:
            rarity_id = card_id[-3:]
            if rarity_id.startswith("R"):
                model_key = card_id[:7] + rarity_id[:2]
                user_regular_models.add(model_key)
            else:
                user_non_regular_ids.add(card_id)
        
        for card in cards:

            idol_key = f"{card['idol_name']}|{card['idol_id']}"
            is_regular = card["rarity"] == "Regular"
            key = card["card_id"]

            if is_regular:
                model_key = card["rarity_id"][:2]  # Rm
                unique_model_id = f"{card['idol_id']}{card['set_id']}{model_key}"
                total_in_set.add(unique_model_id)

                if model_key not in idols_in_set[idol_key]["_counted"]:
                    idols_in_set[idol_key]["_counted"].add(model_key)
                    idols_in_set[idol_key]["total"] += 1

                if unique_model_id in user_regular_models and model_key not in idols_in_set[idol_key]["_owned"]:
                    idols_in_set[idol_key]["owned"] += 1
                    idols_in_set[idol_key]["_owned"].add(model_key)
                    owned_in_set.add(unique_model_id)
            else:
                total_in_set.add(key)
                idols_in_set[idol_key]["total"] += 1
                if key in user_non_regular_ids:
                    idols_in_set[idol_key]["owned"] += 1
                    owned_in_set.add(key)

        # ✅ Verificación del set completo
        set_completed = total_in_set == owned_in_set
        members_amount = int(len(total_in_set)/7)

        embeds = []
        
        idols = []
        for idol_key, data in sorted(idols_in_set.items(), key=lambda x: x[0]):
            idol_name, idol_id = idol_key.split("|")
            
            idol_data = f"{idol_name} ({idol_id})"
            idols.append((idol_data,idol_id))

            embed = discord.Embed(
                title=idol_data,
                description=f"[`{round(int(data['owned'])/int(data['total'])*100,2)}%`] - ({data['owned']}/{data['total']})",
                color=discord.Color.green()
            )
            embeds.append(embed)
            
        
        
        embed1 = discord.Embed(
            title=f"📦 Cartas en el set: {self.set_name}",
            description="",
            color=discord.Color.green()
        )
        if set_completed and False:
            async with pool.acquire() as conn:
                set_id = self.set_id
                badge_id = await conn.fetchval("SELECT badge_id FROM badges WHERE set_id = $1 AND idol_id = ''",
                                                set_id)
                if badge_id:
                    have_it = await conn.fetch("SELECT 1 FROM user_badges WHERE badge_id = $1 AND user_id = $2",
                                            badge_id, interaction.user.id)
                    embed1.set_footer(text="✅ ¡Set completo!")
                else:
                    have_it = True
                    embed1.set_footer(text="Este set no tiene recompensa grupal")
                
                
                await interaction.response.send_message(embed=embed1, ephemeral=True)
                
                if not have_it:
                    await conn.execute("INSERT INTO user_badges (user_id, badge_id) VALUES ($1, $2)",
                                    interaction.user.id, badge_id)
                    
                    credits_given = 3000 * members_amount
                    xp = 25 * members_amount
                    
                    if credits_given > 50000:
                        credits_given = 50000
                    
                    await conn.execute("UPDATE users SET credits = credits + $1, xp = xp + $2", credits_given, xp)
                    new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
                    now = datetime.datetime.now(datetime.timezone.utc)
                    await conn.execute(
                        "INSERT INTO players_packs (pack_id, user_id, unique_id, buy_date) VALUES ('STR', $1, $2, $3)",
                        interaction.user.id, new_id, now)
                
                    await interaction.followup.send(
                        content=f"## ⭐ Has completado todas las cartas del set _{self.set_name}_\n_Has recibido 💵{format(credits_given,',')} y {xp} XP y un **Star Pack**_",
                        ephemeral=True)
            


        
        paginator = CollectionIdolsPaginator(
            embeds=embeds,
            rows=idols,
            interaction=interaction,
            base_query=self.base_query,
            set_name=self.set_name,
            query_params=self.query_params
        )
        
        await paginator.restart()


class CollectionIdolsPaginator:
    def __init__(
        self,
        embeds: list[discord.Embed],
        rows: list[dict],
        interaction: discord.Interaction,
        base_query: str,
        query_params: tuple,
        set_name: str,
        embeds_per_page: int = 4
    ):
        self.all_embeds = embeds
        self.all_rows = rows
        self.set_name = set_name
        self.interaction = interaction
        self.embeds_per_page = embeds_per_page
        self.current_page = 0
        self.total_pages = (len(embeds) + embeds_per_page - 1) // embeds_per_page
        self.base_query = base_query
        self.query_params = query_params

    def get_page_embeds(self):
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        page = self.all_embeds[start:end]
        footer = discord.Embed(
            description=f"Página {self.current_page+1}/{self.total_pages} • Total: {len(self.all_embeds)}\n**Set: `{self.set_name}`**",
            color=discord.Color.dark_gray()
        )
        return [footer] + page

    def get_view(self):
        view = discord.ui.View(timeout=120)
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        for row in self.all_rows[start:end]:
            view.add_item(IdolButton(idol_id=row[1], idol_name=row[0], set_name=self.set_name, base_query=self.base_query, query_params=self.query_params))
        view.add_item(PreviousIdolPageButton(self))
        view.add_item(NextIdolPageButton(self))
        view.add_item(BackToSetsButton(query=self.base_query, params=self.query_params))
        return view

    async def start(self):
        await self.interaction.response.send_message(
            content="",
            embeds=self.get_page_embeds(),
            view=self.get_view(),
            ephemeral=True
        )

    async def restart(self):
        self.current_page = 0
        await self.interaction.response.edit_message(
            content = "",
            embeds=self.get_page_embeds(),
            view=self.get_view()
        )

    async def update(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embeds=self.get_page_embeds(),
            view=self.get_view()
        )

    async def previous_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page - 1) % self.total_pages
        await self.update(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page = (self.current_page + 1) % self.total_pages
        await self.update(interaction)

class BackToSetsButton(discord.ui.Button):
    def __init__(self, query: str, params: str):
        super().__init__(label=f"Volver", style=discord.ButtonStyle.secondary, row=2)
        self.query = query
        self.params = params
        

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pool = get_pool()
        embed = already_active = None
        
        embeds, sorted_sets = await generate_sets_embeds(self.query, self.params, pool, interaction)  
        
        paginator = CollectionSetsPaginator(embeds,
                                        rows=sorted_sets,
                                        interaction=interaction,
                                        base_query=self.query,
                                        query_params=self.params)
        await paginator.restart()

class PreviousIdolPageButton(discord.ui.Button):
    def __init__(self, paginator: CollectionSetsPaginator):
        super().__init__(label="⬅️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.previous_page(interaction)

class NextIdolPageButton(discord.ui.Button):
    def __init__(self, paginator: CollectionSetsPaginator):
        super().__init__(label="➡️", style=discord.ButtonStyle.secondary, row=2)
        self.paginator = paginator

    async def callback(self, interaction: discord.Interaction):
        await self.paginator.next_page(interaction)

class IdolButton(discord.ui.Button):
    def __init__(self, idol_id: str, idol_name: str, set_name: str, base_query: str, query_params: str):
        super().__init__(label=f"{idol_name}", style=discord.ButtonStyle.primary)
        self.idol_id = idol_id
        self.idol_name = idol_name
        self.set_name = set_name
        self.base_query = base_query
        self.query_params = query_params

    async def callback(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        pool = get_pool()
        
        description = ""
        completed = True
        cards = []
        cards_rows = []
        
        async with pool.acquire() as conn:
            set_id = await conn.fetchval("SELECT set_id FROM cards_idol WHERE set_name = $1", self.set_name)
            
            for rarity in RARITY_LIST:
                if rarity == "Regular":
                    card = await conn.fetchval("SELECT card_id FROM cards_idol WHERE set_name = $1 AND rarity_id = 'R13' AND idol_id = $2",
                                            self.set_name, self.idol_id)
                    cards.append(card)
                    card = await conn.fetchval("SELECT card_id FROM cards_idol WHERE set_name = $1 AND rarity_id = 'R23' AND idol_id = $2",
                                            self.set_name, self.idol_id)
                    cards.append(card)
                    card = await conn.fetchval("SELECT card_id FROM cards_idol WHERE set_name = $1 AND rarity_id = 'R33' AND idol_id = $2",
                                            self.set_name, self.idol_id)
                    cards.append(card)
                else:
                    card = await conn.fetchval("SELECT card_id FROM cards_idol WHERE set_name = $1 AND rarity = $2 AND idol_id = $3",
                                            self.set_name, rarity, self.idol_id)
                    cards.append(card)
            
            for card in cards:
                if card:
                    collected = await conn.fetchrow("SELECT 1 FROM user_idol_cards WHERE card_id = $1 AND is_locked = True AND user_id = $2",
                                                    card, user_id)
                    description += f"`{card}` - {"✅" if collected else "❌"}\n"
                    if not collected:
                        completed = False
                    rarity: str = await conn.fetchval("SELECT rarity FROM cards_idol WHERE card_id = $1", card)
                    
                    if rarity == "Regular":
                        rarity += f" {card[8]}"
                    
                    cards_rows.append((card,collected,rarity))
            
        embed = discord.Embed(
            title=f"{self.idol_name} - {self.set_name}",
            description=description,
            color=discord.Color.teal()
        )
        
        badge_id = have_it = None
        
        if completed:
            async with pool.acquire() as conn:
                set_id = await conn.fetchval("SELECT set_id FROM cards_idol WHERE set_name = $1", self.set_name)
                badge_id = await conn.fetchval(
                    "SELECT badge_id FROM badges WHERE set_id = $1 AND idol_id = $2",
                    set_id, self.idol_id
                )
                if badge_id:
                    have_it = await conn.fetch("SELECT 1 FROM user_badges WHERE badge_id = $1 AND user_id = $2",
                                            badge_id, interaction.user.id)
                    embed.set_footer(text="✅ Idol completo en este set")
                else:
                    have_it = True
                    embed.set_footer(text="Este set no tiene recompensas")
                
                
        else:
            embed.set_footer(text="❌ Aún te faltan cartas de este idol en el set")

            
        view = IdolCardsView(cards_rows, user_id, self.base_query, self.query_params, set_id, self.set_name, completed, have_it)

        await interaction.response.edit_message(
            content="",
            embed=embed,
            view=view
        )

class IdolCardsView(discord.ui.View):
    def __init__(self, cards_rows: list, user_id, base_query, query_params, set_id, set_name, completed:bool, have_it:bool):
        super().__init__(timeout=180)
        self.user_id = user_id
        self.cards_rows = cards_rows
        self.base_query = base_query
        self.query_params = query_params
        self.set_id = set_id
        self.set_name = set_name
        self.completed = completed
        self.have_it = have_it

        for card_id, collected, rarity in cards_rows:
            if not card_id:
                continue
            self.add_card_button(card_id, collected, rarity, self.completed, self.have_it)


        complete_button = discord.ui.Button(
            label="✔️ Completar",
            style=discord.ButtonStyle.success,
            row=4,
            disabled = True if have_it else (False if completed else True)
        )
        complete_button.callback = self.complete_button
        self.add_item(complete_button)


        back_button = discord.ui.Button(
            label="⬅️ Volver",
            style=discord.ButtonStyle.secondary,
            row=4
        )
        back_button.callback = self.back_button
        self.add_item(back_button)
        
        
    def add_card_button(self, card_id: str, collected: bool, rarity: str, completed: bool, have_it: bool):
        button = discord.ui.Button(
            label=f"{rarity}",
            style=(discord.ButtonStyle.success if have_it else discord.ButtonStyle.primary) if collected else discord.ButtonStyle.secondary,
        )
        async def card_callback(interaction: discord.Interaction, cid=card_id, coll=collected):
            await interaction.response.defer(
                ephemeral=True
            )
            user_id = interaction.user.id
            pool = get_pool()
            is_duplicated = False

            idol_query = """
                SELECT uc.*, ci.* FROM user_idol_cards uc
                JOIN cards_idol ci ON uc.card_id = ci.card_id
                WHERE uc.user_id = $1 AND uc.card_id = $2
            """
            idol_params = [user_id, card_id]
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(idol_query, *idol_params)    
            
            language = await get_user_language(user_id=user_id)  
                
            if not rows:
                await interaction.edit_original_response(content="## ❌No hay cartas para mostrar.")
                return

            embeds = await generate_idol_card_embeds(rows, pool, interaction.guild)

            paginator = InventoryEmbedPaginator(embeds, rows, interaction, self.base_query, self.query_params, is_duplicated, True, self.set_id, self.set_name, have_it)
            await paginator.restart(interaction)
            

        button.callback = card_callback
        self.add_item(button)
    
    async def complete_button(self, interaction: discord.Interaction):
        pool = get_pool()
        card_id, collected, rarity = self.cards_rows[0]
        
        async with pool.acquire() as conn:
            badge_id = await conn.fetchval("SELECT badge_id FROM badges WHERE set_id = $1 AND idol_id = $2",
                                           self.set_id, card_id[:3])
            idol_name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", card_id[:3])
            
            
            await conn.execute("INSERT INTO user_badges (user_id, badge_id) VALUES ($1, $2)",
                            interaction.user.id, badge_id)
            
            await conn.execute("UPDATE users SET credits = credits + 10000, xp = xp + 150")
            new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            now = datetime.datetime.now(datetime.timezone.utc)
            await conn.execute(
                "INSERT INTO players_packs (pack_id, user_id, unique_id, buy_date) VALUES ('STR', $1, $2, $3)",
                interaction.user.id, new_id, now)
    
        
        await SetButton(self.set_id, self.set_name, self.base_query, self.query_params).callback(interaction)
        await interaction.followup.send(
            content=f"## ⭐ {interaction.user.mention} ha completado todas las cartas de _{idol_name} ({card_id[:3]})_ del set _{self.set_name}_\n**Recompensas:**\n> 💵10,000\n> 150 XP\n> 📦 **Star Pack**",
            ephemeral=False)
    
    async def back_button(self, interaction: discord.Interaction):
        await SetButton(self.set_id, self.set_name, self.base_query, self.query_params).callback(interaction)

async def generate_idol_card_embeds(rows: list, pool, guild: discord.Guild, is_detailed:bool = True) -> list[discord.Embed]:
    from collections import Counter
    from utils.emojis import get_emoji
    from commands.starter import version
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
        set_id: str,
        set_name: str,
        have_it: bool,
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
        self.set_id = set_id
        self.set_name = set_name
        self.have_it = have_it
    
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
        start = self.current_page * self.embeds_per_page
        end = start + self.embeds_per_page
        rows_this_page = self.all_rows[start:end]

        for row_data in rows_this_page:
            view.add_item(LockCardButton(row_data, self.set_id, self.set_name, self.base_query, self.query_params))

        # navegación
        view.add_item(PreviousPageButton(self))
        view.add_item(NextPageButton(self))
        
        view.add_item(UnlockButton(rows_this_page[0], self.set_id, self.set_name, self.base_query, self.query_params, self.have_it))
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

class LockCardButton(discord.ui.Button):
    def __init__(self, row_data:dict, set_id, set_name, base_query, query_params):
        super().__init__(label=f"{row_data['unique_id']}", style=discord.ButtonStyle.primary)
        self.row_data = row_data

        self.base_query = base_query
        self.query_params = query_params
        self.set_id = set_id
        self.set_name = set_name

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        guild = interaction.guild
        
        async with pool.acquire() as conn:
            await conn.execute("UPDATE user_idol_cards SET is_locked = $1 WHERE card_id = $2 AND user_id = $3",
                               False, self.row_data['card_id'], interaction.user.id)
            await conn.execute("UPDATE user_idol_cards SET is_locked = $1 WHERE unique_id = $2", True, self.row_data['unique_id'])
            name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", self.row_data['idol_id'])
        
        idol_name = f"{name} ({self.row_data['idol_id']})"
        
        await IdolButton(self.row_data['idol_id'], idol_name, self.set_name, self.base_query, self.query_params).callback(interaction)

class UnlockButton(discord.ui.Button):
    def __init__(self, row_data:dict, set_id, set_name, base_query, query_params, have_it):
        super().__init__(label=f"Remove", style=discord.ButtonStyle.danger, disabled=have_it!=None, row=2)
        self.row_data = row_data

        self.base_query = base_query
        self.query_params = query_params
        self.set_id = set_id
        self.set_name = set_name

    async def callback(self, interaction: discord.Interaction):
        pool = get_pool()
        language = await get_user_language(interaction.user.id)
        guild = interaction.guild
        
        async with pool.acquire() as conn:
            await conn.execute("UPDATE user_idol_cards SET is_locked = $1 WHERE card_id = $2 AND user_id = $3",
                               False, self.row_data['card_id'], interaction.user.id)
            name = await conn.fetchval("SELECT name FROM idol_base WHERE idol_id = $1", self.row_data['idol_id'])
        
        idol_name = f"{name} ({self.row_data['idol_id']})"
        
        await IdolButton(self.row_data['idol_id'], idol_name, self.set_name, self.base_query, self.query_params).callback(interaction)


async def setup(bot):
    await bot.add_cog(CollectionCommand(bot))
