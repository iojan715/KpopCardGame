import discord
from discord.ext import commands
from discord import app_commands
import csv
import os
import string
import random
from datetime import timezone, datetime
from utils.localization import get_translation
from utils.language import get_user_language
from db.connection import get_pool


class AdminGroup(app_commands.Group):
    def __init__(self):
        super().__init__(name="admin", description="Comandos administrativos")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Evita repetir el chequeo de permisos en cada subcomando"""
        admin_role = discord.utils.get(interaction.user.roles, name="Admin")
        if not admin_role:
            language = await get_user_language(interaction.user.id)
            not_permission = get_translation(language, "error.not_permission")
            await interaction.response.send_message(not_permission, ephemeral=True)
            return False
        return True

    CONTENT_CHOICES = [
        app_commands.Choice(name="All", value="all"),
        app_commands.Choice(name="Packs", value="packs"),
        app_commands.Choice(name="Level rewards", value="levels"),
        app_commands.Choice(name="Idol Cards", value="idols"),
        app_commands.Choice(name="Performance cards", value="performance"),
        app_commands.Choice(name="Item cards", value="items"),
        app_commands.Choice(name="Redeemables", value="redeemables"),
        app_commands.Choice(name="Badges", value="badges"),
        app_commands.Choice(name="Idol base stats", value="idol_base"),
        app_commands.Choice(name="Skills", value="skills"),
        app_commands.Choice(name="Effects", value="effects"),
        app_commands.Choice(name="Groups", value="idol_group"),
        app_commands.Choice(name="songs", value="songs"),
        app_commands.Choice(name="Song sections", value="song_sections")
    ]

    @app_commands.command(name="upload_content", description="Sube datos desde un archivo CSV")
    @app_commands.describe(content_type="Tipo de contenido que deseas subir (ej. packs)")
    @app_commands.choices(content_type = CONTENT_CHOICES)
    async def upload_content(self, interaction: discord.Interaction, content_type: str):
        await interaction.response.defer(ephemeral=True, thinking=True)
        language = await get_user_language(interaction.user.id)
        ALLOWED_CONTENT_TYPES = ["packs",
                                 "levels",
                                 "idols",
                                 "performance",
                                 "items",
                                 "redeemables",
                                 "badges",
                                 "idol_base",
                                 "skills",
                                 "effects",
                                 "idol_group",
                                 "songs",
                                 "song_sections"
                                 ]
        if content_type != "all" and content_type not in ALLOWED_CONTENT_TYPES:
            contenido = ', '.join(ALLOWED_CONTENT_TYPES)
            content_type_not_found = get_translation(language,"upload_content.content_type_not_found",contenido=contenido)
            await interaction.edit_original_response(content=content_type_not_found)
            return
        file_path = f"data_upload/{content_type}.csv"
        if content_type != "all" and not os.path.exists(file_path):
            file_not_found = get_translation(language, "upload_content.file_not_found", file_path=file_path)
            await interaction.edit_original_response(content=file_not_found)
            return

        pool = await get_pool()
        inserted = 0

        
        async with pool.acquire() as conn:
            inserted_total = 0
            types_to_process = ALLOWED_CONTENT_TYPES if content_type == "all" else [content_type]

            for ct in types_to_process:
                print(ct)
                file_path = f"data_upload/{ct}.csv"
                if not os.path.exists(file_path):
                    if content_type == "all":
                        continue
                    file_not_found = get_translation(language, "upload_content.file_not_found", file_path=file_path)
                    await interaction.edit_original_response(content=file_not_found)
                    return

                
                if ct == "packs":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO packs (
                                    pack_id, name, card_amount, can_idol, can_group, set_id, theme,
                                    can_gift, price, w_idol, w_regular, w_limited, w_fcr, w_pob,
                                    w_legacy, w_item, w_performance, w_redeemable, base_price
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6, $7,
                                    $8, $9, $10, $11, $12, $13, $14,
                                    $15, $16, $17, $18, $19
                                )
                                ON CONFLICT (pack_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    card_amount = EXCLUDED.card_amount,
                                    can_idol = EXCLUDED.can_idol,
                                    can_group = EXCLUDED.can_group,
                                    set_id = EXCLUDED.set_id,
                                    theme = EXCLUDED.theme,
                                    can_gift = EXCLUDED.can_gift,
                                    price = EXCLUDED.price,
                                    w_idol = EXCLUDED.w_idol,
                                    w_regular = EXCLUDED.w_regular,
                                    w_limited = EXCLUDED.w_limited,
                                    w_fcr = EXCLUDED.w_fcr,
                                    w_pob = EXCLUDED.w_pob,
                                    w_legacy = EXCLUDED.w_legacy,
                                    w_item = EXCLUDED.w_item,
                                    w_performance = EXCLUDED.w_performance,
                                    w_redeemable = EXCLUDED.w_redeemable,
                                    base_price = EXCLUDED.base_price;
                            """, 
                            row["pack_id"], row["name"], int(row["card_amount"]),
                            row["can_idol"].lower() == "true",
                            row["can_group"].lower() == "true",
                            row.get("set_id"), row.get("theme"),
                            row["can_gift"].lower() == "true", int(row["price"]),
                            int(row["w_idol"]), int(row["w_regular"]), int(row["w_limited"]),
                            int(row["w_fcr"]), int(row["w_pob"]), int(row["w_legacy"]),
                            int(row["w_item"]), int(row["w_performance"]), int(row["w_redeemable"]), int(row["base_price"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                
                elif ct == "idols":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO cards_idol (
                                    card_id, idol_id, set_id, rarity_id, idol_name, group_name, set_name,
                                    rarity, theme, vocal, rap, dance, visual, energy, p_skill,
                                    a_skill, s_skill, u_skill, weight, value
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6, $7,
                                    $8, $9, $10, $11, $12, $13, $14,
                                    $15, $16, $17, $18, $19, $20
                                )
                                ON CONFLICT (card_id) DO UPDATE SET
                                    idol_id = EXCLUDED.idol_id,
                                    set_id = EXCLUDED.set_id,
                                    rarity_id = EXCLUDED.rarity_id,
                                    idol_name = EXCLUDED.idol_name,
                                    group_name = EXCLUDED.group_name,
                                    set_name = EXCLUDED.set_name,
                                    rarity = EXCLUDED.rarity,
                                    theme = EXCLUDED.theme,
                                    vocal = EXCLUDED.vocal,
                                    rap = EXCLUDED.rap,
                                    dance = EXCLUDED.dance,
                                    visual = EXCLUDED.visual,
                                    energy = EXCLUDED.energy,
                                    p_skill = EXCLUDED.p_skill,
                                    a_skill = EXCLUDED.a_skill,
                                    s_skill = EXCLUDED.s_skill,
                                    u_skill = EXCLUDED.u_skill,
                                    weight = EXCLUDED.weight,
                                    value = EXCLUDED.value;
                            """, 
                            row["card_id"], row["idol_id"], row["set_id"], row["rarity_id"],
                            row["idol_name"], row["group_name"], row["set_name"], row["rarity"], row.get("theme"),
                            int(row["vocal"]), int(row["rap"]), int(row["dance"]), int(row["visual"]),
                            int(row["energy"]), row.get("p_skill"), row.get("a_skill"),row.get("s_skill"),
                            row.get("u_skill"), int(row["weight"]), int(row["value"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                
                elif ct == "redeemables":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO redeemables (
                                    redeemable_id, name, type, effect, weight
                                ) VALUES (
                                    $1, $2, $3, $4, $5
                                )
                                ON CONFLICT (redeemable_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    type = EXCLUDED.type,
                                    effect = EXCLUDED.effect,
                                    weight = EXCLUDED.weight;
                            """, 
                            row["redeemable_id"], row["name"], row["type"], row.get("effect"), int(row["weight"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                
                elif ct == "badges":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO badges (
                                    badge_id, name, category, set_id, idol_id
                                ) VALUES (
                                    $1, $2, $3, $4, $5
                                )
                                ON CONFLICT (badge_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    category = EXCLUDED.category,
                                    set_id = EXCLUDED.set_id,
                                    idol_id = EXCLUDED.idol_id;
                            """,
                            row["badge_id"], row["name"], row["category"],
                            row.get("set_id"), row.get("idol_id"))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "performance":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO cards_performance (
                                    pcard_id, name, type, effect, duration,
                                    cooldown, match, match_value, weight, value
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6, $7, $8, $9, $10
                                )
                                ON CONFLICT (pcard_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    type = EXCLUDED.type,
                                    effect = EXCLUDED.effect,
                                    duration = EXCLUDED.duration,
                                    cooldown = EXCLUDED.cooldown,
                                    match = EXCLUDED.match,
                                    match_value = EXCLUDED.match_value,
                                    weight = EXCLUDED.weight,
                                    value = EXCLUDED.value;
                            """,
                            row["pcard_id"], row["name"], row["type"],
                            row.get("effect"),
                            int(row["duration"]) if row.get("duration") else 0,
                            int(row["cooldown"]) if row.get("cooldown") else 0,
                            row.get("match"),
                            row.get("match_value"),
                            int(row["weight"]) if row.get("weight") else 0,
                            int(row["value"]) if row.get("value") else 0)
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "items":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO cards_item (
                                    item_id, name, type,
                                    plus_vocal, plus_rap, plus_dance, plus_visual, plus_energy,
                                    max_durability, weight, value
                                ) VALUES (
                                    $1, $2, $3,
                                    $4, $5, $6, $7, $8,
                                    $9, $10, $11
                                )
                                ON CONFLICT (item_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    type = EXCLUDED.type,
                                    plus_vocal = EXCLUDED.plus_vocal,
                                    plus_rap = EXCLUDED.plus_rap,
                                    plus_dance = EXCLUDED.plus_dance,
                                    plus_visual = EXCLUDED.plus_visual,
                                    plus_energy = EXCLUDED.plus_energy,
                                    max_durability = EXCLUDED.max_durability,
                                    weight = EXCLUDED.weight,
                                    value = EXCLUDED.value;
                            """,
                            row["item_id"], row["name"], row["type"],
                            int(row["plus_vocal"]) if row.get("plus_vocal") else 0,
                            int(row["plus_rap"]) if row.get("plus_rap") else 0,
                            int(row["plus_dance"]) if row.get("plus_dance") else 0,
                            int(row["plus_visual"]) if row.get("plus_visual") else 0,
                            int(row["plus_energy"]) if row.get("plus_energy") else 0,
                            int(row["max_durability"]) if row.get("max_durability") else 1,
                            int(row["weight"]) if row.get("weight") else 0,
                            int(row["value"]) if row.get("value") else 0)
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "levels":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO level_rewards (
                                    level, xp_needed, credits, pack, redeemable, badge
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6
                                )
                                ON CONFLICT (level) DO UPDATE SET
                                    xp_needed = EXCLUDED.xp_needed,
                                    credits = EXCLUDED.credits,
                                    pack = EXCLUDED.pack,
                                    redeemable = EXCLUDED.redeemable,
                                    badge = EXCLUDED.badge;
                            """,
                            int(row["level"]),
                            int(row["xp_needed"]),
                            int(row["credits"]) if row.get("credits") else 0,
                            row.get("pack_id"),
                            row.get("redeemable_id"),
                            row.get("badge_id"))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "idol_base":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO idol_base (
                                    idol_id, name, vocal, rap, dance, visual
                                ) VALUES (
                                    $1, $2, $3, $4, $5, $6
                                )
                                ON CONFLICT (idol_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    vocal = EXCLUDED.vocal,
                                    rap = EXCLUDED.rap,
                                    dance = EXCLUDED.dance,
                                    visual = EXCLUDED.visual;
                            """,
                            row["idol_id"], row["name"],
                            int(row["vocal"]), int(row["rap"]),
                            int(row["dance"]), int(row["visual"]))
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
                            
                elif ct == "idol_group":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute("""
                                INSERT INTO idol_group (
                                    idol_id, idol_name, group_name
                                ) VALUES (
                                    $1, $2, $3
                                )
                                ON CONFLICT (idol_id, group_name) DO UPDATE SET
                                    idol_name = EXCLUDED.idol_name,
                                    group_name = EXCLUDED.group_name;
                            """,
                            row["idol_id"], row["idol_name"], row["group_name"])
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "skills":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO skills (
                                    skill_name, skill_type, condition, condition_values, condition_effect,
                                    condition_params, effect_id, duration, energy_cost,
                                    cost_type, effect, params, tags
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6, $7, $8, $9,
                                    $10, $11, $12, $13
                                )
                                ON CONFLICT (skill_name) DO UPDATE SET
                                    skill_type = EXCLUDED.skill_type,
                                    condition = EXCLUDED.condition,
                                    condition_values = EXCLUDED.condition_values,
                                    condition_effect = EXCLUDED.condition_effect,
                                    condition_params = EXCLUDED.condition_params,
                                    effect_id = EXCLUDED.effect_id,
                                    duration = EXCLUDED.duration,
                                    energy_cost = EXCLUDED.energy_cost,
                                    cost_type = EXCLUDED.cost_type,
                                    effect = EXCLUDED.effect,
                                    params = EXCLUDED.params,
                                    tags = EXCLUDED.tags;
                                """,
                                row["skill_name"],
                                row["skill_type"],
                                row.get("condition"),
                                json.dumps(json.loads(row["condition_values"])) if row.get("condition_values") else None,
                                row.get("condition_effect"),
                                json.dumps(json.loads(row["condition_params"])) if row.get("condition_params") else None,
                                row.get("effect_id"),
                                int(row["duration"]) if row.get("duration") else 0,
                                float(row["energy_cost"]) if row.get("energy_cost") else 0,
                                row.get("cost_type"),
                                row.get("effect"),
                                json.dumps(json.loads(row["params"])) if row.get("params") else None,
                                row.get("tags")
                            )
                            
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "effects":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO performance_effects (
                                    effect_id, effect_name, effect_type,
                                    highest_stat_mod, lowest_stat_mod,
                                    plus_vocal, plus_rap, plus_dance, plus_visual,
                                    hype_mod, score_mod,
                                    extra_cost, relative_cost
                                ) VALUES (
                                    $1, $2, $3,
                                    $4, $5,
                                    $6, $7, $8, $9,
                                    $10, $11,
                                    $12, $13
                                )
                                ON CONFLICT (effect_id) DO UPDATE SET
                                    effect_name = EXCLUDED.effect_name,
                                    effect_type = EXCLUDED.effect_type,
                                    highest_stat_mod = EXCLUDED.highest_stat_mod,
                                    lowest_stat_mod = EXCLUDED.lowest_stat_mod,
                                    plus_vocal = EXCLUDED.plus_vocal,
                                    plus_rap = EXCLUDED.plus_rap,
                                    plus_dance = EXCLUDED.plus_dance,
                                    plus_visual = EXCLUDED.plus_visual,
                                    hype_mod = EXCLUDED.hype_mod,
                                    score_mod = EXCLUDED.score_mod,
                                    extra_cost = EXCLUDED.extra_cost,
                                    relative_cost = EXCLUDED.relative_cost;
                                """,
                                row["effect_id"],
                                row["name"],
                                row["type"],
                                int(row.get("plus_highest") or 0),
                                int(row.get("plus_lowest") or 0),
                                int(row.get("plus_vocal") or 0),
                                int(row.get("plus_rap") or 0),
                                int(row.get("plus_dance") or 0),
                                int(row.get("plus_visual") or 0),
                                float(row.get("hype_mod") or 1.0),
                                float(row.get("score_mod") or 1.0),
                                int(row.get("extra_cost") or 0),
                                float(row.get("relative_cost") or 1.0)
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "songs":
                    import json
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO songs (
                                    song_id, name, original_artist, total_duration,
                                    total_sections, average_score
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6
                                )
                                ON CONFLICT (song_id) DO UPDATE SET
                                    name = EXCLUDED.name,
                                    original_artist = EXCLUDED.original_artist,
                                    total_duration = EXCLUDED.total_duration,
                                    total_sections = EXCLUDED.total_sections,
                                    average_score = EXCLUDED.average_score;
                                """,
                                row["song_id"],
                                row["name"],
                                row["original_artist"],
                                int(row["total_duration"]),
                                int(row["total_sections"]),
                                round(float(row["average_score"]),2)
                            )
                            
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0

                elif ct == "song_sections":
                    with open(file_path, newline='', encoding='utf-8') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            await conn.execute(
                                """
                                INSERT INTO song_sections (
                                    section_id, song_id, section_number, section_type, duration,
                                    lyrics, vocal, rap, dance, visual, change_rule, type_plus,
                                    plus_vocal, plus_rap, plus_dance, plus_visual, average_score
                                ) VALUES (
                                    $1, $2, $3, $4, $5,
                                    $6, $7, $8, $9, $10, $11,
                                    $12, $13, $14, $15, $16, $17
                                )
                                ON CONFLICT (section_id) DO UPDATE SET
                                    song_id = EXCLUDED.song_id,
                                    section_number = EXCLUDED.section_number,
                                    section_type = EXCLUDED.section_type,
                                    duration = EXCLUDED.duration,
                                    lyrics = EXCLUDED.lyrics,
                                    vocal = EXCLUDED.vocal,
                                    rap = EXCLUDED.rap,
                                    dance = EXCLUDED.dance,
                                    visual = EXCLUDED.visual,
                                    change_rule = EXCLUDED.change_rule,
                                    type_plus = EXCLUDED.type_plus,
                                    plus_vocal = EXCLUDED.plus_vocal,
                                    plus_rap = EXCLUDED.plus_rap,
                                    plus_dance = EXCLUDED.plus_dance,
                                    plus_visual = EXCLUDED.plus_visual,
                                    average_score = EXCLUDED.average_score;
                                """,
                                row["section_id"],
                                row["song_id"],
                                int(row["section_number"]),
                                row["section_type"],
                                int(row["duration"]),
                                row['lyrics'],
                                int(row["vocal"]),
                                int(row["rap"]),
                                int(row["dance"]),
                                int(row["visual"]),
                                row.get("change_rule", "optional"),
                                row.get("type_plus") or None,
                                int(row["plus_vocal"]) if row["plus_vocal"] else 0,
                                int(row["plus_rap"]) if row["plus_rap"] else 0,
                                int(row["plus_dance"]) if row["plus_dance"] else 0,
                                int(row["plus_visual"]) if row["plus_visual"] else 0,
                                round(float(row["average_score"]),2)
                            )
                            inserted += 1
                    inserted_total += inserted
                    inserted = 0
        
        
        if content_type == "all":
            succesfull = get_translation(language, "upload_content.succesfull_all", inserted=inserted_total)
        else:
            succesfull = get_translation(language, "upload_content.succesfull", inserted=inserted_total, content_type=content_type)

        await interaction.edit_original_response(
            content= succesfull
        )


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


    @app_commands.command(name="give_item_card", description="Entregar manualmente una item card a un jugador")
    @app_commands.describe(
        user="Usuario que recibirá la carta",
        item_id="ID base del ítem a entregar"
    )
    async def give_item_card(self, interaction: discord.Interaction, user: discord.User, item_id: str):
        pool = get_pool()

        async with pool.acquire() as conn:
            
            item_row = await conn.fetchrow("SELECT * FROM cards_item WHERE item_id = $1", item_id)
            if not item_row:
                await interaction.response.send_message(f"❌ El item `{item_id}` no existe.", ephemeral=True)
                return
            durability = item_row['max_durability']
            item_name = item_row['name']
            
            unique_id = ""
            while True:
                new_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
                row = await conn.fetchrow("SELECT 1 FROM user_item_cards WHERE unique_id = $1", new_id)
                if not row:
                    unique_id = new_id
                    break

            
            values = (
                unique_id,
                user.id,
                item_id,
                durability,
                None,
                datetime.now(timezone.utc)
            )

            await conn.execute("""
                INSERT INTO user_item_cards (
                    unique_id,
                    user_id,
                    item_id,
                    durability,
                    equipped_idol_card_id,
                    date_obtained
                ) VALUES ($1, $2, $3, $4, $5, $6);
            """, *values)

        await interaction.response.send_message(f"✅ Se entregó `{item_name}` a {user.mention}.", ephemeral=False)



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
    
async def setup(bot):
    bot.tree.add_command(AdminGroup())