from db.connection import get_pool
import datetime

async def create_all_tables():
    await create_users_table()
    await create_level_rewards_table()
    await create_cards_idol_table()
    await create_cards_item_table()
    await create_cards_performance_table()
    await create_redeemables_table()
    await create_badges_table()
    await create_inventory_idol_cards_table()
    await create_inventory_item_cards_table()
    await create_inventory_performance_cards_table()
    await create_inventory_redeemables_table()
    await create_inventory_badges_table()
    await create_packs_table()
    await create_players_packs_table()
    await create_idol_group_table()
    await create_idol_base_table()
    await create_skills_table()
    await create_effects_table()
    await create_groups_table()
    await create_groups_members_table()
    await create_songs_table()
    await create_song_sections_table()
    await create_effects_table()
    await create_presentation_table()
    await create_presentation_members_table()
    await create_presentation_sections_table()
    #await create_idol_usage_table()
    await create_loop_events_table()

async def create_users_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                agency_name TEXT,
                level INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                influence_temp INTEGER DEFAULT 0,
                credits INTEGER DEFAULT 0,
                last_sponsor TIMESTAMPTZ DEFAULT now(),
                bank INTEGER DEFAULT 0,
                register_date TIMESTAMPTZ DEFAULT now(),
                language TEXT DEFAULT 'en',
                notifications BOOLEAN DEFAULT FALSE,
                can_FCR BOOLEAN DEFAULT TRUE
            );
        """)

async def create_level_rewards_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS level_rewards (
                level INTEGER PRIMARY KEY,
                xp_needed INTEGER NOT NULL,
                credits INTEGER DEFAULT 0,
                pack TEXT,
                redeemable TEXT,
                badge TEXT
            );
        """)

async def create_cards_idol_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cards_idol (
                card_id TEXT PRIMARY KEY,
                idol_id TEXT NOT NULL,
                set_id TEXT NOT NULL,
                rarity_id TEXT NOT NULL,
                idol_name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                set_name TEXT NOT NULL,
                rarity TEXT NOT NULL,
                theme TEXT,
                vocal INTEGER DEFAULT 0,
                rap INTEGER DEFAULT 0,
                dance INTEGER DEFAULT 0,
                visual INTEGER DEFAULT 0,
                energy INTEGER DEFAULT 0,
                p_skill TEXT,
                a_skill TEXT,
                s_skill TEXT,
                u_skill TEXT,
                weight INTEGER DEFAULT 0,
                value INTEGER DEFAULT 0
            );
        """)
        
async def create_cards_item_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cards_item (
                item_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                plus_vocal INTEGER DEFAULT 0,
                plus_rap INTEGER DEFAULT 0,
                plus_dance INTEGER DEFAULT 0,
                plus_visual INTEGER DEFAULT 0,
                plus_energy INTEGER DEFAULT 0,
                max_durability INTEGER DEFAULT 1,
                weight INTEGER DEFAULT 0,
                value INTEGER DEFAULT 0
            );
        """)
        
async def create_cards_performance_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS cards_performance (
                pcard_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                effect TEXT,
                duration INTEGER DEFAULT 0,
                cooldown INTEGER DEFAULT 0,
                match TEXT,
                match_value TEXT,
                weight INTEGER DEFAULT 0,
                value INTEGER DEFAULT 0
            );
        """)
        
async def create_redeemables_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS redeemables (
                redeemable_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                weight INTEGER DEFAULT 0
            );
        """)
        
async def create_badges_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS badges (
                badge_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                set_id TEXT,
                idol_id TEXT
            );
        """)

async def create_packs_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS packs (
                pack_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                card_amount INTEGER NOT NULL,
                can_idol BOOLEAN NOT NULL,
                can_group BOOLEAN NOT NULL,
                set_id TEXT,
                theme TEXT,
                can_gift BOOLEAN NOT NULL,
                price INTEGER NOT NULL,
                w_idol INTEGER NOT NULL,
                w_regular INTEGER NOT NULL,
                w_limited INTEGER NOT NULL,
                w_fcr INTEGER NOT NULL,
                w_pob INTEGER NOT NULL,
                w_legacy INTEGER NOT NULL,
                w_item INTEGER NOT NULL,
                w_performance INTEGER NOT NULL,
                w_redeemable INTEGER NOT NULL,
                base_price INTEGER NOT NULL
            );
        """)
  
async def create_players_packs_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players_packs (
                unique_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                pack_id TEXT NOT NULL,
                buy_date TIMESTAMPTZ NOT NULL,
                idol_id TEXT,
                group_name TEXT,
                set_id TEXT,
                theme TEXT
            );
        """)

async def create_inventory_idol_cards_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_idol_cards (
                unique_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                card_id TEXT NOT NULL,
                idol_id TEXT,
                set_id TEXT,
                rarity_id TEXT,
                status TEXT DEFAULT 'available',
                is_locked BOOLEAN DEFAULT FALSE,
                date_obtained TIMESTAMPTZ DEFAULT now()
            );
        """)

async def create_inventory_item_cards_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_item_cards (
                unique_id TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                item_id TEXT NOT NULL,
                durability INTEGER,
                status TEXT DEFAULT 'available',
                date_obtained TIMESTAMPTZ DEFAULT now()
            );
        """)

async def create_inventory_performance_cards_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_performance_cards (
                user_id BIGINT NOT NULL,
                pcard_id TEXT NOT NULL,
                quantity INTEGER DEFAULT 0,
                last_updated TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (user_id, pcard_id)
            );
        """)

async def create_inventory_redeemables_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_redeemables (
                user_id BIGINT NOT NULL,
                redeemable_id TEXT NOT NULL,
                quantity INTEGER DEFAULT 0,
                last_updated TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (user_id, redeemable_id)
            );
        """)

async def create_inventory_badges_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_badges (
                user_id BIGINT NOT NULL,
                badge_id TEXT NOT NULL,
                date_obtained TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (user_id, badge_id)
            );
        """)



async def create_idol_group_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS idol_group (
                idol_id TEXT,
                idol_name TEXT NOT NULL,
                group_name TEXT NOT NULL,
                PRIMARY KEY (idol_id, group_name)
            );
        """)

async def create_idol_base_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS idol_base (
                idol_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                vocal INTEGER DEFAULT 0,
                rap INTEGER DEFAULT 0,
                dance INTEGER DEFAULT 0,
                visual INTEGER DEFAULT 0
            );
        """)

async def create_skills_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                skill_name TEXT PRIMARY KEY,
                skill_type TEXT NOT NULL,
                condition TEXT,
                condition_values JSONB,
                condition_effect TEXT,
                condition_params JSONB,
                effect_id TEXT,
                duration INTEGER DEFAULT 0,
                energy_cost FLOAT DEFAULT 0,
                cost_type TEXT,
                effect TEXT,
                params JSONB,
                tags TEXT
            );
        """)


async def create_groups_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS groups (
                group_id TEXT PRIMARY KEY,
                user_id BIGINT,
                name TEXT,
                popularity INT DEFAULT 0,
                permanent_popularity INT DEFAULT 0,
                status TEXT,
                weekly_payment INT DEFAULT 100,
                unpaid_weeks INT DEFAULT 0,
                creation_date TIMESTAMPTZ DEFAULT now(),
                comeback_motion INT DEFAULT 0
            );
        """)

async def create_groups_members_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS groups_members (
                group_id TEXT NOT NULL,
                user_id BIGINT,
                idol_id TEXT NOT NULL,
                card_id TEXT DEFAULT NULL,
                mic_id TEXT DEFAULT NULL,
                outfit_id TEXT DEFAULT NULL,
                accessory_id TEXT DEFAULT NULL,
                consumable_id TEXT DEFAULT NULL,
                weekly_payment INT DEFAULT 50,
                PRIMARY KEY (group_id, idol_id)
            );
        """)

#-----
async def create_songs_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS songs (
                song_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                original_artist TEXT NOT NULL,
                owner TEXT,
                total_duration INTEGER NOT NULL,
                total_sections INTEGER NOT NULL,
                released_date TIMESTAMPTZ DEFAULT now(),
                average_score FLOAT NOT NULL
            );
        """)

async def create_song_sections_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS song_sections (
                section_id TEXT PRIMARY KEY,
                song_id TEXT NOT NULL,
                section_number INTEGER NOT NULL,
                section_type TEXT NOT NULL,
                duration INTEGER NOT NULL,
                lyrics TEXT NOT NULL,
                vocal INTEGER DEFAULT 0,
                rap INTEGER DEFAULT 0,
                dance INTEGER DEFAULT 0,
                visual INTEGER DEFAULT 0,
                change_rule TEXT DEFAULT 'optional',
                type_plus TEXT,
                plus_vocal INTEGER DEFAULT 0,
                plus_rap INTEGER DEFAULT 0,
                plus_dance INTEGER DEFAULT 0,
                plus_visual INTEGER DEFAULT 0,
                average_score FLOAT NOT NULL
            );
        """)
"""
ALTER TABLE song_sections
ADD COLUMN lyrics TEXT NOT NULL DEFAULT '';
"""


async def create_effects_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS performance_effects (
                effect_id TEXT PRIMARY KEY,
                effect_name TEXT NOT NULL,
                effect_type TEXT NOT NULL,
                highest_stat_mod INTEGER DEFAULT 0,
                lowest_stat_mod INTEGER DEFAULT 0,
                plus_vocal INTEGER DEFAULT 0,
                plus_rap INTEGER DEFAULT 0,
                plus_dance INTEGER DEFAULT 0,
                plus_visual INTEGER DEFAULT 0,
                hype_mod FLOAT DEFAULT 1.0,
                score_mod FLOAT DEFAULT 1.0,
                extra_cost INTEGER DEFAULT 0,
                relative_cost FLOAT DEFAULT 1.0
            );
        """)

async def create_presentation_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS presentations (
                presentation_id TEXT PRIMARY KEY,
                owner_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                group_id TEXT,
                song_id TEXT,
                can_select_song BOOLEAN DEFAULT TRUE,
                current_section INTEGER DEFAULT 1,
                stage_effect TEXT,
                stage_effect_duration INTEGER DEFAULT 0,
                support_effect TEXT,
                support_effect_duration INTEGER DEFAULT 0,
                free_switches INTEGER DEFAULT 0,
                status TEXT DEFAULT 'preparation',
                presentation_type TEXT,
                presentation_date TIMESTAMPTZ DEFAULT now(),
                start_date TIMESTAMPTZ,
                last_action TIMESTAMPTZ DEFAULT now(),
                total_hype FLOAT DEFAULT 40,
                total_score INTEGER DEFAULT 0,
                total_popularity INTEGER DEFAULT 0,
                performance_card_uses INTEGER DEFAULT 0,
                used_reinforcement BOOLEAN DEFAULT FALSE,
                used_stage BOOLEAN DEFAULT FALSE,
                min_energy FLOAT DEFAULT 100
            );
        """)

async def create_presentation_members_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS presentation_members (
                id SERIAL PRIMARY KEY,
                presentation_id TEXT NOT NULL,
                idol_id TEXT NOT NULL,
                card_id TEXT,
                unique_id TEXT,
                user_id BIGINT NOT NULL,
                vocal INTEGER NOT NULL,
                rap INTEGER NOT NULL,
                dance INTEGER NOT NULL,
                visual INTEGER NOT NULL,
                max_energy INTEGER NOT NULL,
                used_energy FLOAT DEFAULT 0,
                can_ult BOOLEAN DEFAULT TRUE,
                p_type TEXT,
                current_position TEXT DEFAULT 'back',
                last_position TEXT,
                individual_score INTEGER DEFAULT 0
            );
        """)

async def create_presentation_sections_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS presentation_sections (
                id SERIAL PRIMARY KEY,
                presentation_id TEXT NOT NULL,
                section INTEGER NOT NULL,
                score_got INTEGER DEFAULT 0,
                hype_got FLOAT DEFAULT 0,
                active_card_id TEXT,
                plus_vocal INTEGER DEFAULT 0,
                plus_rap INTEGER DEFAULT 0,
                plus_dance INTEGER DEFAULT 0,
                plus_visual INTEGER DEFAULT 0
            );
        """)


async def create_idol_usage_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS user_idol_usage (
                user_id BIGINT NOT NULL,
                idol_id TEXT NOT NULL,
                month TEXT NOT NULL,
                total_score INTEGER DEFAULT 0,
                times_used INTEGER DEFAULT 0,
                UNIQUE (user_id, idol_id, month)
            );
        """)


# - Loops table

async def create_loop_events_table():
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS loop_events (
                event TEXT PRIMARY KEY,
                last_applied TIMESTAMPTZ DEFAULT '1970-01-01',
                frecuencia_tipo TEXT,
                dia_semana INTEGER,  -- 0=lunes, 6=domingo
                dia_mes INTEGER      -- 1 al 31
            );
        """)

        # Insertar eventos predefinidos
        eventos = [
            ('reset_fcr',        'semanal', 0, None),
            ('reduce_popularity','semanal',  0, None),
            ('reduce_influence', 'semanal', 0, None),
            ('change_limited_set','mensual', None, 1),
            ('cancel_presentation','frecuente', None, None),
            ('increase_payment','semanal', 0, None),
        ]

        for event_name, tipo, dia_semana, dia_mes in eventos:
            await conn.execute("""
                INSERT INTO loop_events (event, frecuencia_tipo, dia_semana, dia_mes)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (event) DO UPDATE 
                SET frecuencia_tipo = EXCLUDED.frecuencia_tipo,
                    dia_semana = EXCLUDED.dia_semana,
                    dia_mes = EXCLUDED.dia_mes;
            """, event_name, tipo, dia_semana, dia_mes)

















