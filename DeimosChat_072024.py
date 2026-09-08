import asyncio
from datetime import datetime, timedelta
import json
import logging
import os
import random
import sys
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# Настройка логирования
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

TOKEN = "8994039104:AAEgHnwwv97G0TUzTbAcGYQoGPAQa93wo7A"

bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

DB_FILE = "nevada_database.json"

USER_DIRECTORY = {}  # username -> telegram_id
USER_DATA = {}       # user_id -> {...}

# Магазин аксессуаров для дуэлей с игроками
ACCESSORIES_SHOP = {
    "очки_хэнка": {"name": "😎 Культовые очки Хэнка", "price": 150, "bonus_power": 5},
    "сигарета_деймоса": {"name": "🚬 Сигарета Деймоса", "price": 100, "bonus_power": 3},
    "маска_трикки": {"name": "🤡 Маска Трикки", "price": 300, "bonus_power": 12},
    "бита_санфорда": {"name": "🏏 Бита Санфорда", "price": 200, "bonus_power": 8},
}

# Отдельный магазин аксессуаров для битв с ботами (покупаются за валюту ботов)
BOT_ACCESSORIES_SHOP = {
    "бот_бронежилет": {"name": "🛡 Бронежилет Агента", "price": 50, "bot_bonus": 5},
    "бот_клинок": {"name": "🗡 Тактический нож", "price": 100, "bot_bonus": 12},
    "бот_пулемет": {"name": "🔫 Портативный пулемет", "price": 250, "bot_bonus": 30},
}

def load_data():
    global USER_DATA
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                USER_DATA = {int(k): v for k, v in data.get("users", {}).items()}
        except Exception as e:
            logging.error(f"Ошибка загрузки базы данных: {e}")

def save_data():
    try:
        data = {"users": USER_DATA}
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Ошибка сохранения базы данных: {e}")

# Фоновая задача: начисление ежедневных монет с проверкой активности (3 дня без дуэлей = стоп)
async def daily_coins_distributor():
    while True:
        await asyncio.sleep(86400)  # Каждые 24 часа
        now = datetime.now()
        now_str = now.strftime("%Y-%m-%d")
        
        for uid, udata in USER_DATA.items():
            last_duel_str = udata.get("last_duel_date")
            
            # Проверка: если за последние 3 дня не было дуэлей, монеты не капают
            if last_duel_str:
                last_duel_date = datetime.strptime(last_duel_str, "%Y-%m-%d")
                if (now - last_duel_date).days > 3:
                    continue

            if udata.get("last_daily") != now_str:
                streak = udata.get("duel_streak", 0)
                daily_amount = 10 + min(streak * 2, 20)
                
                udata["coins"] += daily_amount
                udata["last_daily"] = now_str
                
        save_data()

class MissionStates(StatesGroup):
    waiting_for_mission_text = State()

class AnnouncementStates(StatesGroup):
    waiting_for_announcement_text = State()

class PollStates(StatesGroup):
    waiting_for_question = State()
    waiting_for_options = State()

class ProfileStates(StatesGroup):
    waiting_for_name = State()
    waiting_for_avatar = State()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    now_str = datetime.now().strftime("%Y-%m-%d")

    if username:
        USER_DIRECTORY[username.lower()] = user_id

    if user_id not in USER_DATA:
        USER_DATA[user_id] = {
            "coins": 100, 
            "bot_coins": 50,  # Отдельная валюта для ботов
            "username": username or message.from_user.first_name,
            "custom_name": None,
            "custom_avatar": None,
            "inventory": [],
            "bot_inventory": [],
            "last_daily": now_str,
            "last_duel_date": now_str,
            "duel_streak": 0,
            "wins": 0
        }
        save_data()
    else:
        if "wins" not in USER_DATA[user_id]:
            USER_DATA[user_id]["wins"] = 0
        if "bot_coins" not in USER_DATA[user_id]:
            USER_DATA[user_id]["bot_coins"] = 50
        if "bot_inventory" not in USER_DATA[user_id]:
            USER_DATA[user_id]["bot_inventory"] = []

        if USER_DATA[user_id].get("last_daily") != now_str:
            last_duel_str = USER_DATA[user_id].get("last_duel_date")
            can_get = True
            if last_duel_str:
                if (datetime.now() - datetime.strptime(last_duel_str, "%Y-%m-%d")).days > 3:
                    can_get = False
            
            if can_get:
                streak = USER_DATA[user_id].get("duel_streak", 0)
                daily_amount = 10 + min(streak * 2, 20)
                USER_DATA[user_id]["coins"] += daily_amount
                USER_DATA[user_id]["last_daily"] = now_str
                save_data()

    welcome_text = (
        "⚔️ **Добро пожаловать в Неваду, боец!**\n\n"
        "📅 Каждый день капают монеты за дуэли с игроками. За победы над ботами вы получаете отдельную валюту (монеты ботов) и прокачиваетесь в боях с ними.\n\n"
        "📜 **Доступные команды:**\n"
        "• `/duel @username [ставка]` — бросить вызов игроку (влияет на топ денег и топ побед).\n"
        "• `/fight [ставка]` — сразиться с ботом (дает валюту ботов и прокачку против ботов).\n"
        "• `/shop` — магазин аксессуаров за обычные монеты (для дуэлей с игроками).\n"
        "• `/botshop` — магазин аксессуаров за валюту ботов (только для ботов).\n"
        "• `/inventory` — ваш арсенал.\n"
        "• `/p [текст]` — отправить скрытую карточку в группе.\n"
        "• `/balance` — проверить балансы (монеты дуэлей и валюту ботов).\n"
        "• `/poll` — создать опрос (в группе).\n"
        "• `.RP [текст]` — RP-действие в группе.\n"
        "• `.S @username [текст]` — секретное сообщение в ЛС через группу."
    )
    
    keyboard = None
    if message.chat.type == "private":
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Настроить профиль", callback_data="setup_profile")],
                [InlineKeyboardButton(text="🏆 Топы", callback_data="open_tops")]
            ]
        )

    await message.answer(welcome_text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "open_tops")
async def process_open_tops(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 Топ денег", callback_data="top_money")],
            [InlineKeyboardButton(text="⚔️ Топ побед", callback_data="top_wins")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_start")]
        ]
    )
    await callback.message.edit_text(
        "🏆 **ЗАЛ СЛАВЫ НЕВАДЫ**\n\nВыберите категорию рейтинга дуэлей:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data == "back_to_start")
async def process_back_to_start(callback: types.CallbackQuery):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Настроить профиль", callback_data="setup_profile")],
            [InlineKeyboardButton(text="🏆 Топы", callback_data="open_tops")]
        ]
    )
    await callback.message.edit_text(
        "⚔️ **Главное меню Невады**\nВыберите нужный пункт ниже:",
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query(F.data.in_(["top_money", "top_wins"]))
async def process_show_top(callback: types.CallbackQuery):
    is_money = callback.data == "top_money"
    user_id = callback.from_user.id

    if is_money:
        sorted_users = sorted(USER_DATA.items(), key=lambda x: x[1].get("coins", 0), reverse=True)
        title = "💰 **ТОП-10 БОГАТЕЙ НЕВАДЫ**"
        metric_name = "монет"
    else:
        sorted_users = sorted(USER_DATA.items(), key=lambda x: x[1].get("wins", 0), reverse=True)
        title = "⚔️ **ТОП-10 ПОБЕДИТЕЛЕЙ**"
        metric_name = "побед"

    text = f"{title}\n\n"
    
    top_10 = sorted_users[:10]
    for idx, (uid, udata) in enumerate(top_10, 1):
        name = udata.get("custom_name") or udata.get("username") or f"Боец {uid}"
        val = udata.get("coins", 0) if is_money else udata.get("wins", 0)
        text += f"{idx}. **{name}** — {val} {metric_name}\n"

    user_rank = None
    user_val = 0
    for idx, (uid, udata) in enumerate(sorted_users, 1):
        if uid == user_id:
            user_rank = idx
            user_val = udata.get("coins", 0) if is_money else udata.get("wins", 0)
            break

    if user_rank and user_rank > 10:
        name = USER_DATA.get(user_id, {}).get("custom_name") or USER_DATA.get(user_id, {}).get("username") or "Вы"
        text += f"\n...\n{user_rank}. **{name}** (Вы) — {user_val} {metric_name}"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад к топам", callback_data="open_tops")]]
    )

    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "setup_profile")
async def process_setup_profile(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Введите новое **имя** (никнейм) для вашего кастомного профиля в Неваде:")
    await state.set_state(ProfileStates.waiting_for_name)
    await callback.answer()

@dp.message(ProfileStates.waiting_for_name)
async def process_custom_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("⚠️ Имя не может быть пустым. Введите никнейм еще раз:")
        return
    
    await state.update_data(custom_name=name)
    await message.answer(
        "🖼 Отправьте **аватарку** (картинку) для вашего профиля.\n"
        "⚠️ Она должна быть **приблизительно квадратной** (отклонение до 25%)."
    )
    await state.set_state(ProfileStates.waiting_for_avatar)

@dp.message(ProfileStates.waiting_for_avatar, F.photo)
async def process_custom_avatar(message: Message, state: FSMContext):
    photo = message.photo[-1]  
    width = photo.width
    height = photo.height

    max_side = max(width, height)
    min_side = min(width, height)
    
    if min_side < max_side * 0.75:
        await message.answer(
            f"❌ Картинка слишком сильно вытянута! Ее пропорции: {width}x{height} пикселей.\n"
            "Отправьте картинку ближе к квадрату:"
        )
        return

    data = await state.get_data()
    custom_name = data.get("custom_name")
    file_id = photo.file_id
    
    user_id = message.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"coins": 100, "bot_coins": 50, "username": message.from_user.username or message.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    USER_DATA[user_id]["custom_name"] = custom_name
    USER_DATA[user_id]["custom_avatar"] = file_id
    save_data()
    await state.clear()

    await message.answer(
        f"✅ **Профиль успешно сохранен!**\n\n"
        f"👤 Имя: **{custom_name}**\n"
        f"Теперь в группе используйте `/p [текст]` для публикации карточки от вашего лица.",
        parse_mode="Markdown"
    )

@dp.message(Command("p"))
async def cmd_custom_profile_post(message: Message):
    if message.chat.type == "private":
        await message.answer("Команда /p предназначена только для групповых чатов!")
        return

    user_id = message.from_user.id
    if user_id not in USER_DATA or not USER_DATA[user_id].get("custom_name") or not USER_DATA[user_id].get("custom_avatar"):
        await message.answer("⚠️ У вас не настроен кастомный профиль! Настройте его в ЛС бота.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Вы не указали текст сообщения! Пример: `/p Привет, сектор.`", parse_mode="Markdown")
        return

    post_text = args[1]
    profile = USER_DATA[user_id]
    c_name = profile["custom_name"]
    c_avatar = profile["custom_avatar"]

    try:
        await message.delete()
    except Exception:
        pass

    caption = f"👤 **{c_name}**: {post_text}"

    try:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=c_avatar,
            caption=caption,
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.error(f"Ошибка отправки /p: {e}")

# МАГАЗИН АКСЕССУАРОВ (ДЛЯ ДУЭЛЕЙ С ИГРОКАМИ)
@dp.message(Command("shop"))
async def cmd_shop(message: Message):
    shop_text = "🛍 **МАГАЗИН АКСЕССУАРОВ (ДУЭЛИ С ИГРОКАМИ)**\n\n"
    keyboard_buttons = []
    
    for key, item in ACCESSORIES_SHOP.items():
        shop_text += f"• **{item['name']}** — 💰 {item['price']} монет (+{item['bonus_power']} к силе)\n"
        keyboard_buttons.append([InlineKeyboardButton(text=f"Купить: {item['name']} ({item['price']} 💰)", callback_data=f"buy_{key}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(shop_text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("buy_"))
async def process_buy_accessory(callback: types.CallbackQuery):
    item_key = callback.data.split("_", 1)[1]
    if item_key not in ACCESSORIES_SHOP:
        await callback.answer("❌ Такого аксессуара нет в продаже!", show_alert=True)
        return

    user_id = callback.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"coins": 100, "bot_coins": 50, "username": callback.from_user.username or callback.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    item = ACCESSORIES_SHOP[item_key]
    user_inv = USER_DATA[user_id].setdefault("inventory", [])

    if item_key in user_inv:
        await callback.answer("⚠️ У вас уже куплен этот аксессуар!", show_alert=True)
        return

    if USER_DATA[user_id]["coins"] < item["price"]:
        await callback.answer(f"❌ Недостаточно монет! Нужно {item['price']}, а у вас {USER_DATA[user_id]['coins']}.", show_alert=True)
        return

    USER_DATA[user_id]["coins"] -= item["price"]
    user_inv.append(item_key)
    save_data()

    await callback.answer(f"🎉 Вы успешно приобрели {item['name']}!", show_alert=True)
    await callback.message.edit_text(f"✅ Покупка совершена! Вы приобрели: **{item['name']}**.\n💰 Остаток монет: {USER_DATA[user_id]['coins']}.", parse_mode="Markdown")

# МАГАЗИН АКСЕССУАРОВ ДЛЯ БИТВ С БОТАМИ
@dp.message(Command("botshop"))
async def cmd_botshop(message: Message):
    shop_text = "🤖 **МАГАЗИН АРСЕНАЛА ПРОТИВ БОТОВ**\n\n"
    keyboard_buttons = []
    
    for key, item in BOT_ACCESSORIES_SHOP.items():
        shop_text += f"• **{item['name']}** — ⚙️ {item['price']} валюты ботов (+{item['bot_bonus']}% к победе)\n"
        keyboard_buttons.append([InlineKeyboardButton(text=f"Купить: {item['name']} ({item['price']} ⚙️)", callback_data=f"botbuy_{key}")])

    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    await message.answer(shop_text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("botbuy_"))
async def process_buy_bot_accessory(callback: types.CallbackQuery):
    item_key = callback.data.split("_", 1)[1]
    if item_key not in BOT_ACCESSORIES_SHOP:
        await callback.answer("❌ Такого снаряжения нет в продаже!", show_alert=True)
        return

    user_id = callback.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"coins": 100, "bot_coins": 50, "username": callback.from_user.username or callback.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    item = BOT_ACCESSORIES_SHOP[item_key]
    bot_inv = USER_DATA[user_id].setdefault("bot_inventory", [])

    if item_key in bot_inv:
        await callback.answer("⚠️ У вас уже куплено это снаряжение!", show_alert=True)
        return

    if USER_DATA[user_id]["bot_coins"] < item["price"]:
        await callback.answer(f"❌ Недостаточно валюты ботов! Нужно {item['price']}, а у вас {USER_DATA[user_id]['bot_coins']}.", show_alert=True)
        return

    USER_DATA[user_id]["bot_coins"] -= item["price"]
    bot_inv.append(item_key)
    save_data()

    await callback.answer(f"🎉 Вы успешно приобрели {item['name']}!", show_alert=True)
    await callback.message.edit_text(f"✅ Покупка совершена! Снаряжение: **{item['name']}**.\n⚙️ Остаток валюты ботов: {USER_DATA[user_id]['bot_coins']}.", parse_mode="Markdown")

@dp.message(Command("inventory"))
async def cmd_inventory(message: Message):
    user_id = message.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"coins": 100, "bot_coins": 50, "username": message.from_user.username or message.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    user_inv = USER_DATA[user_id].get("inventory", [])
    bot_inv = USER_DATA[user_id].get("bot_inventory", [])

    inv_text = "🎒 **ВАШ АРСЕНАЛ СНАРЯЖЕНИЯ**\n\n"
    
    inv_text += "👤 **Для дуэлей с игроками:**\n"
    if not user_inv:
        inv_text += "• Пусто (посетите `/shop`)\n"
    else:
        total_bonus = 0
        for key in user_inv:
            item = ACCESSORIES_SHOP[key]
            inv_text += f"• {item['name']} (+{item['bonus_power']} к силе)\n"
            total_bonus += item['bonus_power']
        inv_text += f"💪 Бонус к силе: **+{total_bonus}**\n"

    inv_text += "\n🤖 **Для битв с ботами:**\n"
    if not bot_inv:
        inv_text += "• Пусто (посетите `/botshop`)\n"
    else:
        total_bot_bonus = 0
        for key in bot_inv:
            item = BOT_ACCESSORIES_SHOP[key]
            inv_text += f"• {item['name']} (+{item['bot_bonus']}% к победе)\n"
            total_bot_bonus += item['bot_bonus']
        inv_text += f"⚡ Бонус к шансу победы бота: **+{total_bot_bonus}%**\n"

    await message.answer(inv_text, parse_mode="Markdown")

# ДУЭЛИ МЕЖДУ ИГРОКАМИ
@dp.message(Command("duel"))
async def cmd_duel(message: Message):
    if message.chat.type == "private":
        await message.answer("Дуэли между бойцами проводятся только в групповых чатах!")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3 or not parts[2].isdigit():
        await message.answer("⚠️ Неверный формат! Используйте: `/duel @username ставка` (например, `/duel @hank 50`)", parse_mode="Markdown")
        return

    target_mention = parts[1]
    bet = int(parts[2])

    if bet <= 0:
        await message.answer("⚠️ Ставка должна быть больше 0 монет.")
        return

    challenger_id = message.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if challenger_id not in USER_DATA:
        USER_DATA[challenger_id] = {"coins": 100, "bot_coins": 50, "username": message.from_user.username or message.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    if USER_DATA[challenger_id]["coins"] < bet:
        await message.answer(f"❌ У вас недостаточно монет для такой ставки! Ваш баланс: {USER_DATA[challenger_id]['coins']} монет.")
        return

    target_username = target_mention.lstrip("@").lower()
    target_id = USER_DIRECTORY.get(target_username)

    if not target_id:
        await message.answer(f"❌ Боец {target_mention} не зарегистрирован в базе данных бота (не запускал его в ЛС).")
        return

    if target_id == challenger_id:
        await message.answer("⚠️ Нельзя бросить вызов самому себе!")
        return

    if target_id not in USER_DATA:
        USER_DATA[target_id] = {"coins": 100, "bot_coins": 50, "username": target_username, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    if USER_DATA[target_id]["coins"] < bet:
        await message.answer(f"❌ У противника {target_mention} недостаточно монет для такой ставки (баланс: {USER_DATA[target_id]['coins']}).")
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⚔️ Принять дуэль", callback_data=f"duel_accept_{challenger_id}_{target_id}_{bet}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"duel_decline_{challenger_id}_{target_id}")
            ]
        ]
    )

    await message.answer(
        f"🎯 **ВНИМАНИЕ, СЕКТОР! ВЫЗОВ НА ДУЭЛЬ!**\n\n"
        f"👤 Инициатор: {message.from_user.full_name}\n"
        f"🎯 Соперник: {target_mention}\n"
        f"💰 Ставка: **{bet} монет**\n\n"
        f"{target_mention}, у вас есть выбор: принять вызов на арене или отклонить его.",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@dp.callback_query(F.data.startswith("duel_"))
async def process_duel_callback(callback: types.CallbackQuery):
    data_parts = callback.data.split("_")
    action = data_parts[1]
    challenger_id = int(data_parts[2])
    target_id = int(data_parts[3])

    if callback.from_user.id != target_id:
        await callback.answer("⚠️ Этот вызов брошен не вам!", show_alert=True)
        return

    if action == "decline":
        await callback.message.edit_text("❌ **Дуэль отклонена.** Трусость — тоже выбор в Неваде.", parse_mode="Markdown")
        await callback.answer()
        return

    if action == "accept":
        bet = int(data_parts[4])

        if USER_DATA.get(challenger_id, {}).get("coins", 0) < bet:
            await callback.message.edit_text("❌ У инициатора дуэли больше нет нужного количества монет!")
            await callback.answer()
            return
        if USER_DATA.get(target_id, {}).get("coins", 0) < bet:
            await callback.message.edit_text("❌ У вас недостаточно монет для принятия этой ставки!")
            await callback.answer()
            return

        now_str = datetime.now().strftime("%Y-%m-%d")
        for uid in [challenger_id, target_id]:
            USER_DATA[uid]["last_duel_date"] = now_str
            USER_DATA[uid]["duel_streak"] = USER_DATA[uid].get("duel_streak", 0) + 1

        def get_total_power(uid):
            base = random.randint(1, 50)
            inv = USER_DATA.get(uid, {}).get("inventory", [])
            bonus = sum(ACCESSORIES_SHOP[k]["bonus_power"] for k in inv if k in ACCESSORIES_SHOP)
            return base + bonus

        p1_power = get_total_power(challenger_id)
        p2_power = get_total_power(target_id)

        if p1_power == p2_power:
            winner_id = random.choice([challenger_id, target_id])
        else:
            winner_id = challenger_id if p1_power > p2_power else target_id

        loser_id = target_id if winner_id == challenger_id else challenger_id

        USER_DATA[winner_id]["coins"] += bet
        USER_DATA[loser_id]["coins"] -= bet
        
        if "wins" not in USER_DATA[winner_id]:
            USER_DATA[winner_id]["wins"] = 0
        USER_DATA[winner_id]["wins"] += 1

        save_data()

        winner_name = (await bot.get_chat(winner_id)).full_name
        loser_name = (await bot.get_chat(loser_id)).full_name

        await callback.message.edit_text(
            f"⚔️ **ДУЭЛЬ ЗАВЕРШЕНА!** ⚔️\n\n"
            f"🔥 Сила инициатора: {p1_power}\n"
            f"🔥 Сила соперника: {p2_power}\n\n"
            f"🏆 **Победитель:** {winner_name} забирает весь куш (**+{bet} монет**)!\n"
            f"💀 **Проигравший:** {loser_name} теряет {bet} монет.\n\n"
            f"💰 Балансы: Инициатор — {USER_DATA[challenger_id]['coins']} | Соперник — {USER_DATA[target_id]['coins']}",
            parse_mode="Markdown"
        )
        await callback.answer()

# СРАЖЕНИЕ С БОТОМ (Шанс 75% на 25%, выигрыш +50% в валюте ботов, победы НЕ идут в топ)
@dp.message(Command("fight"))
async def cmd_fight(message: Message):
    if message.chat.type == "private":
        await message.answer("Битвы на арене Невады проводятся только в групповых чатах!")
        return

    user_id = message.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"coins": 100, "bot_coins": 50, "username": message.from_user.username or message.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}

    args = message.text.split()
    bet = 10
    if len(args) > 1 and args[1].isdigit():
        bet = int(args[1])

    if USER_DATA[user_id]["bot_coins"] < bet:
        await message.answer(f"❌ У вас недостаточно валюты ботов для такой ставки! Ваш баланс: {USER_DATA[user_id]['bot_coins']} ⚙️.")
        return

    enemies = ["Агент AAHW", "Зомби с трубой", "Сложный киборг", "Трикки Клоун"]
    enemy_name = random.choice(enemies)

    # Просчет бонусов от снаряжения против ботов
    bot_inv = USER_DATA[user_id].get("bot_inventory", [])
    bot_bonus = sum(BOT_ACCESSORIES_SHOP[k]["bot_bonus"] for k in bot_inv if k in BOT_ACCESSORIES_SHOP)
    
    roll = random.randint(1, 100)
    win_chance = 75 + bot_bonus  # Базовые 75% + бонус от снаряжения против ботов

    profit = int(bet * 0.5)  # Выигрыш +50% от ставки

    if roll <= win_chance:
        USER_DATA[user_id]["bot_coins"] += profit
        save_data()
        await message.answer(
            f"⚔️ **АРЕНА НЕВАДЫ: БИТВА С БОТОМ!**\n\n"
            f"Противник: **{enemy_name}**\n"
            f"🎉 **ПОБЕДА НАД БОТОМ!**\n"
            f"⚙️ Выигрыш в валюте ботов (+50%): **+{profit}**\n"
            f"⚙️ Баланс валюты ботов: {USER_DATA[user_id]['bot_coins']}",
            parse_mode="Markdown"
        )
    else:
        USER_DATA[user_id]["bot_coins"] -= bet
        save_data()
        await message.answer(
            f"⚔️ **АРЕНА НЕВАДЫ: БИТВА С БОТОМ!**\n\n"
            f"Противник: **{enemy_name}**\n"
            f"💀 **ПОРАЖЕНИЕ!** (Удача была на стороне бота)\n"
            f"💸 Потеряно валюты ботов: -{bet}. Баланс: {USER_DATA[user_id]['bot_coins']}",
            parse_mode="Markdown"
        )

@dp.message(Command("balance"))
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    now_str = datetime.now().strftime("%Y-%m-%d")
    if user_id not in USER_DATA:
        USER_DATA[user_id] = {"coins": 100, "bot_coins": 50, "username": message.from_user.username or message.from_user.first_name, "inventory": [], "bot_inventory": [], "last_daily": now_str, "last_duel_date": now_str, "duel_streak": 0, "wins": 0}
        save_data()
    
    coins = USER_DATA[user_id]["coins"]
    bot_coins = USER_DATA[user_id].get("bot_coins", 50)
    streak = USER_DATA[user_id].get("duel_streak", 0)
    wins = USER_DATA[user_id].get("wins", 0)
    
    await message.answer(
        f"💰 Баланс монетизированных дуэлей: **{coins} монет**\n"
        f"⚙️ Валюта для битв с ботами: **{bot_coins} ед.**\n"
        f"⚔️ Побед в дуэлях с игроками: **{wins}**\n"
        f"🔥 Стрик активности в дуэлях: **{streak}**",
        parse_mode="Markdown"
    )

@dp.message(Command("poll"))
async def cmd_poll_start(message: Message, state: FSMContext):
    if message.chat.type == "private":
        await message.answer("Опросы можно создавать только в групповых чатах!")
        return

    await message.answer("📊 Введите **вопрос** для будущего опроса:")
    await state.set_state(PollStates.waiting_for_question)

@dp.message(PollStates.waiting_for_question)
async def process_poll_question(message: Message, state: FSMContext):
    await state.update_data(question=message.text)
    await message.answer("📝 Теперь отправьте **варианты ответа** каждый с новой строки (от 2 до 10 вариантов).")
    await state.set_state(PollStates.waiting_for_options)

@dp.message(PollStates.waiting_for_options)
async def process_poll_options(message: Message, state: FSMContext):
    options = [line.strip() for line in message.text.split("\n") if line.strip()]
    
    if len(options) < 2:
        await message.answer("⚠️ Нужно указать как минимум 2 варианта ответа!")
        return
    if len(options) > 10:
        await message.answer("⚠️ Максимальное количество вариантов — 10.")
        return

    data = await state.get_data()
    question = data.get("question")
    await state.clear()

    await message.answer_poll(
        question=question,
        options=options,
        is_anonymous=False
    )

@dp.message(F.chat.type == "private")
async def private_message_handler(message: Message):
    if message.from_user.username:
        USER_DIRECTORY[message.from_user.username.lower()] = message.from_user.id

    text = message.text
    if not text:
        return

    words = text.split(" ", 1)
    target_candidate = words[0].lstrip("@").lower()

    if target_candidate in USER_DIRECTORY:
        target_id = USER_DIRECTORY[target_candidate]
        actual_message = words[1] if len(words) > 1 else "[пустое сообщение]"
        sender_name = message.from_user.username or message.from_user.first_name

        try:
            await bot.send_message(
                target_id,
                f"📡 **Сообщение от агента @{sender_name} через терминал:**\n\n{actual_message}",
                parse_mode="Markdown"
            )
            await message.answer("✅ Сообщение успешно доставлено в другой сектор Невады!")
        except Exception:
            await message.answer("❌ Не удалось доставить сообщение.")
    else:
        await message.answer("⚠️ Получатель не найден в базе данных терминала. Убедитесь, что он запускал бота.")

@dp.message(F.text.startswith(".RP") | F.text.startswith(".рп"))
async def group_rp_handler(message: Message):
    if message.chat.type == "private":
        await message.answer("Команда .RP работает только в групповых чатах!")
        return

    action_text = message.text[3:].strip()
    if not action_text:
        await message.answer("⚠️ Вы не указали действие для RP!")
        return

    user_name = message.from_user.full_name
    await message.answer(f"🛡 *[RP]* **{user_name}** *{action_text}*", parse_mode="Markdown")

@dp.message(F.text.startswith(".S") | F.text.startswith(".с"))
async def group_secret_message_handler(message: Message):
    if message.chat.type == "private":
        await message.answer("Команда .S работает только в групповых чатах!")
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("⚠️ Неверный формат! Используйте: `.S @username сообщение`")
        return

    target_mention = parts[1]
    secret_text = parts[2]

    target_username = target_mention.lstrip("@").lower()
    target_id = USER_DIRECTORY.get(target_username)

    if not target_id:
        await message.answer(f"❌ Пользователь {target_mention} не зарегистрирован.")
        return

    sender_name = message.from_user.full_name
    try:
        await bot.send_message(
            target_id,
            f"🔒 **Секретное сообщение от {sender_name} из группы:**\n\n{secret_text}",
            parse_mode="Markdown"
        )
        await message.answer(f"✉️ Секретное сообщение отправлено пользователю {target_mention} в ЛС.")
    except Exception:
        await message.answer("❌ Ошибка отправки в ЛС.")

async def is_admin_or_owner(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    member = await message.chat.get_member(message.from_user.id)
    return member.status in ["creator", "administrator"]

@dp.message(Command("mission"))
async def cmd_mission(message: Message, state: FSMContext):
    if message.chat.type == "private":
        await message.answer("Эта команда предназначена для групп.")
        return

    if not await is_admin_or_owner(message):
        await message.answer("⛔ Доступ запрещен!")
        return

    await message.answer("🎯 Введите текст миссии:")
    await state.set_state(MissionStates.waiting_for_mission_text)

@dp.message(MissionStates.waiting_for_mission_text)
async def process_mission_text(message: Message, state: FSMContext):
    mission_text = message.text
    await state.clear()
    await message.answer(f"🚨 **НОВАЯ МИССИЯ АГЕНТСТВА** 🚨\n\n{mission_text}", parse_mode="Markdown")

@dp.message(Command("announce"))
async def cmd_announce(message: Message, state: FSMContext):
    if message.chat.type == "private":
        await message.answer("Эта команда предназначена для групп.")
        return

    if not await is_admin_or_owner(message):
        await message.answer("⛔ Доступ запрещен!")
        return

    await message.answer("📢 Введите текст объявления:")
    await state.set_state(AnnouncementStates.waiting_for_announcement_text)

@dp.message(AnnouncementStates.waiting_for_announcement_text)
async def process_announcement_text(message: Message, state: FSMContext):
    announcement_text = message.text
    await state.clear()
    await message.answer(f"📢 **ВНИМАНИЕ ВСЕМ СЕКТОРАМ!** 📢\n\n{announcement_text}", parse_mode="Markdown")

async def main():
    load_data()
    asyncio.create_task(daily_coins_distributor())
    print("Бот вселенной Madness Combat запущен и готов к работе в Неваде...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
