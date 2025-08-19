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

PUBLIC_CHOICES = [
    app_commands.Choice(name="✅", value="✅"),
    app_commands.Choice(name="❌", value="❌"),
]

class CollectionCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="collections", description="Consulta el progreso de tus cartas por set, rareza o idol.")
    @app_commands.describe(set_name="Nombre del set", rarity="Rareza de cartas", idol="Nombre del idol", public="Public message")
    @app_commands.choices(rarity=RARITY_CHOICES, public=PUBLIC_CHOICES)
    async def collections(self, interaction: discord.Interaction, set_name: str = None, rarity: str = None, idol: str = None, public: str = None):
        user_id = interaction.user.id
        language = await get_user_language(user_id)
        pool = get_pool()
        
        hidden = True
        if public:
            hidden = public == "❌"

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
            cards = await conn.fetch("SELECT * FROM cards_idol ORDER BY card_id")
            user_cards = await conn.fetch("SELECT card_id FROM user_idol_cards WHERE user_id = $1", user_id)

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
        
        # === CASO: Sin parámetros o solo rareza o solo idol ===
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
        chunk_size = 10
        for i in range(0, len(sorted_sets), chunk_size):
            i_desc = ""
            for (set_id, set_name), info in sorted_sets[i:i + chunk_size]:
                i_desc += f"\n[`{round(int(info['owned'])/int(info['total'])*100,2)}%`] **{set_name}** - ({info['owned']}/{info['total']})"
            embed = discord.Embed(
                title="📚 Colecciones de Cartas",
                description=i_desc,
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Página {i//chunk_size + 1} / {(len(sorted_sets)-1)//chunk_size + 1}")
            embeds.append(embed)

        if len(embeds) == 1:
            await interaction.response.send_message(embed=embeds[0], ephemeral=hidden)
        else:
            view = CollectionPaginator(embeds, user_id)
            await interaction.response.send_message(embed=embeds[0], view=view, ephemeral=hidden)

    @collections.autocomplete("set_name")
    async def set_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT set_name FROM cards_idol ORDER BY set_name ASC")
        return [
            app_commands.Choice(name=row["set_name"], value=row["set_name"])
            for row in rows if current.lower() in row["set_name"].lower()
        ][:25]

    @collections.autocomplete("idol")
    async def idol_autocomplete(self, interaction: discord.Interaction, current: str):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT idol_id, name FROM idol_base ORDER BY name ASC")
        return [
            app_commands.Choice(name=f"{row['name']} ({row['idol_id']})", value=row['idol_id'])
            for row in rows if current.lower() in f"{row['name'].lower()} ({row['idol_id'].lower()})"
        ][:25]

async def setup(bot):
    await bot.add_cog(CollectionCommand(bot))
