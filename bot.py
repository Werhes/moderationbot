import asyncio
import re
import aiohttp
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, BaseFilter
from aiogram.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import BaseMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# === НАСТРОЙКИ БОТА ===
BOT_TOKEN = "ТОКЕН"
ADMINS = ["makrotos", "pulsesyncdev"]
BAD_WORDS = ["блять", "хуй", "пидорас", "пидор", "пиздишь", "пиздюк", "заебал", "гандон", "мудак", "пиздабол"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === БАЗА ДАННЫХ ===
db = {}
global_usernames = {}

def get_chat_db(chat_id: int):
    if chat_id not in db:
        db[chat_id] = {
            "welcome_msg": "Привет, {name} Добро пожаловать в чат VK M! Здесь можно пообсуждать баги, фичи и просто поболтать.",
            "rules": None,
            "warnings": {},
            "mafia_status": "idle",
            "mafia_players": set()
        }
    return db[chat_id]

def resolve_user_id(username_str: str) -> int:
    clean_username = username_str.replace("@", "").lower()
    return global_usernames.get(clean_username)

# === ФИЛЬТРЫ И MIDDLEWARE ===

class IsGroup(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        return message.chat.type in ["group", "supergroup"]

class IsPrivateAndAdmin(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        if message.chat.type == "private":
            username = message.from_user.username
            return bool(username and username.lower() in ADMINS)
        return False

class IsBotAdmin(BaseFilter):
    async def __call__(self, message: types.Message) -> bool:
        username = message.from_user.username
        return bool(username and username.lower() in ADMINS)

class UsernameCacheMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: types.Message, data: dict):
        if event.from_user and event.from_user.username:
            global_usernames[event.from_user.username.lower()] = event.from_user.id
            
        if event.chat and event.chat.type in ["group", "supergroup"]:
            get_chat_db(event.chat.id)
            
        return await handler(event, data)

dp.message.middleware(UsernameCacheMiddleware())

# === РАСПИСАНИЕ И АВТОМАТИЧЕСКИЙ МУТ ЧАТА ===

DEFAULT_PERMISSIONS = ChatPermissions(
    can_send_messages=True, can_send_audios=True, can_send_documents=True,
    can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
    can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
    can_add_web_page_previews=True, can_invite_users=True
)

async def morning_routine(bot: Bot):
    for chat_id in list(db.keys()):
        try:
            await bot.set_chat_permissions(chat_id, DEFAULT_PERMISSIONS)
            await bot.send_message(chat_id, "Сейчас - 7:00 по московскому времени! Пора вставать, всем доброе утро!")
        except Exception:
            pass

async def evening_warning(bot: Bot):
    for chat_id in list(db.keys()):
        try:
            await bot.send_message(chat_id, "Сейчас по московскому времени 21:45, а значит пора ложится спать. Всем спокойной ночи, через 15 минут возможность писать сообщения в чат останется только у админов, чат будет замучен до 7:00 по московскому времени. Добрых снов!")
        except Exception:
            pass

async def night_mute(bot: Bot):
    for chat_id in list(db.keys()):
        try:
            await bot.set_chat_permissions(chat_id, ChatPermissions(can_send_messages=False))
            await bot.send_message(chat_id, "🔒 Чат переведен в ночной режим (писать могут только администраторы).")
        except Exception:
            pass

# === ОБЩИЕ КОМАНДЫ (ДЛЯ ВСЕХ) ===

@dp.message(Command("pravila"), IsGroup())
async def show_rules(message: types.Message):
    chat_db = get_chat_db(message.chat.id)
    if chat_db["rules"]:
        await message.reply(f"📜 Правила группы:\n\n{chat_db['rules']}")
    else:
        await message.reply("В этой группе пока не установлены правила.")

@dp.message(Command("getrelease"))
async def get_latest_release(message: types.Message):
    url = "https://api.github.com/repos/MaKrotos/Music-M/releases/latest"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    name = data.get("name", "Без названия")
                    version = data.get("tag_name", "Неизвестно")
                    body = data.get("body", "Нет описания")
                    html_url = data.get("html_url", "https://github.com/MaKrotos/Music-M/releases")
                    
                    # Ограничиваем длину описания, если оно очень длинное
                    if len(body) > 500:
                        body = body[:500] + "...\n(читайте продолжение по ссылке)"
                        
                    text = (
                        f"⚡️ последний релиз: {name}\n"
                        f"📦 Версия: {version}\n"
                        f"📝 Описание: {body}\n"
                        f"🔗 <a href='{html_url}'>Ссылка на релиз</a>"
                    )
                    await message.reply(text, parse_mode="HTML", disable_web_page_preview=True)
                else:
                    await message.reply("❌ Не удалось получить релиз. Возможно, репозиторий приватный или релизов еще нет.")
    except Exception as e:
        await message.reply(f"❌ Ошибка при запросе к GitHub: {e}")

# === УДАЛЕНИЕ СООБЩЕНИЙ И РУЧНОЙ МАТ ===

@dp.message(Command("del"), IsGroup(), IsBotAdmin())
async def delete_msg(message: types.Message):
    if not message.reply_to_message:
        return await message.reply("Эту команду нужно использовать ответом на сообщение, которое нужно удалить.")
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
        await message.delete() 
    except Exception as e:
        error_text = (
            f"❌ Ошибка удаления.\n"
            f"Возможные причины:\n"
            f"1. Бот не администратор или у него нет прав удалять сообщения.\n"
            f"2. Сообщение старше 48 часов.\n"
            f"3. Вы пытаетесь удалить сообщение создателя группы.\n\n"
            f"Техническая ошибка: {e}"
        )
        await message.reply(error_text)

@dp.message(Command("mat"), IsGroup(), IsBotAdmin())
async def manual_warn(message: types.Message):
    chat_db = get_chat_db(message.chat.id)
    target_user_id = None
    target_username = ""

    if message.reply_to_message:
        target_user_id = message.reply_to_message.from_user.id
        target_username = f"@{message.reply_to_message.from_user.username}" if message.reply_to_message.from_user.username else message.reply_to_message.from_user.first_name
    else:
        parts = message.text.split()
        if len(parts) > 1 and parts[1].startswith("@"):
            target_user_id = resolve_user_id(parts[1])
            target_username = parts[1]
            
    if not target_user_id:
        return await message.reply("Ответь этой командой на сообщение нарушителя или напиши /mat @юзернейм")
        
    now = datetime.now()
    if target_user_id not in chat_db["warnings"]:
        chat_db["warnings"][target_user_id] = []
        
    chat_db["warnings"][target_user_id] = [w for w in chat_db["warnings"][target_user_id] if now - w < timedelta(days=7)]
    chat_db["warnings"][target_user_id].append(now)
    warn_count = len(chat_db["warnings"][target_user_id])
    
    if warn_count >= 3:
        await bot.ban_chat_member(chat_id=message.chat.id, user_id=target_user_id)
        await message.reply(f"Участник {target_username} был удален из группы за 3 предупреждения (выдано админом).")
        chat_db["warnings"][target_user_id] = []
    else:
        await message.reply(f"Администратор выдал предупреждение участнику {target_username}! Предупреждение {warn_count}/3.")

# === ИГРА "МАФИЯ" ===

@dp.message(Command("startgame"), IsGroup(), IsBotAdmin())
async def start_game(message: types.Message):
    chat_db = get_chat_db(message.chat.id)
    if chat_db.get("mafia_status") == "recruiting":
        return await message.reply("Набор уже открыт!")
        
    chat_db["mafia_status"] = "recruiting"
    chat_db["mafia_players"] = set()
    
    bot_info = await bot.get_me()
    safe_chat_id = str(message.chat.id).replace("-", "m")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Играть 🕵️‍♂️", url=f"https://t.me/{bot_info.username}?start=mafia_{safe_chat_id}")]
    ])
    
    await message.answer("🕵️‍♂️ **Объявляется набор в Мафию!**\n\nНужно 5 игроков. Нажми кнопку ниже, чтобы присоединиться.", reply_markup=keyboard)

@dp.message(Command("stopgame"), IsGroup(), IsBotAdmin())
async def stop_game(message: types.Message):
    chat_db = get_chat_db(message.chat.id)
    chat_db["mafia_status"] = "idle"
    chat_db["mafia_players"] = set()
    await message.answer("🛑 Набор в Мафию закрыт админом.")

@dp.message(Command("start"), F.chat.type == "private")
async def private_start(message: types.Message):
    parts = message.text.split(maxsplit=1)
    
    if len(parts) == 1:
        return await message.answer("Привет! Я бот для управления группой.")
        
    if len(parts) > 1 and parts[1].startswith("mafia_"):
        safe_chat_id = parts[1].replace("mafia_", "")
        chat_id_str = safe_chat_id.replace("m", "-")
        
        try:
            chat_id = int(chat_id_str)
        except ValueError:
            return await message.answer("❌ Ошибка: неверный код группы.")
            
        chat_db = get_chat_db(chat_id)
        if chat_db.get("mafia_status") != "recruiting":
            return await message.answer("❌ Набор в игру в этой группе сейчас закрыт.")
            
        players = chat_db.get("mafia_players", set())
        
        if len(players) >= 5:
            return await message.answer("❌ Мест нет! Уже набрано 5 игроков.")
            
        if message.from_user.id in players:
            return await message.answer("Ты уже участвуешь в игре!")
            
        players.add(message.from_user.id)
        chat_db["mafia_players"] = players
        
        await message.answer("✅ Ты теперь участвуешь в Мафии! Возвращайся в группу и жди начала.")
        
        user_display = f"@{message.from_user.username}" if message.from_user.username else message.from_user.first_name
        await bot.send_message(chat_id, f"Участник {user_display} присоединился к Мафии! ({len(players)}/5)")
        
        if len(players) == 5:
            chat_db["mafia_status"] = "idle"
            await bot.send_message(chat_id, "🎉 **Набрано 5 игроков! Набор автоматически закрыт.**")

# === ОТПРАВКА СООБЩЕНИЙ В ЛС ===

@dp.message(Command("chat"), IsPrivateAndAdmin())
async def send_msg_on_behalf(message: types.Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        return await message.reply("Использование: /chat @юзернейм текст сообщения")
    
    target_username = parts[1]
    msg_text = parts[2]
    user_id = resolve_user_id(target_username)
    
    if not user_id:
        return await message.reply(f"❌ Не могу найти пользователя {target_username}.")
    
    try:
        await bot.send_message(chat_id=user_id, text=msg_text)
        await message.reply(f"✅ Сообщение отправлено {target_username}.")
    except Exception as e:
        await message.reply(f"❌ Ошибка отправки: {e}")

# === ВХОД И ВЫХОД УЧАСТНИКОВ ===

@dp.message(IsGroup(), F.new_chat_members)
async def welcome_new_member(message: types.Message):
    chat_db = get_chat_db(message.chat.id)
    for new_user in message.new_chat_members:
        user_name = new_user.first_name if new_user.first_name else new_user.username
        welcome_text = chat_db["welcome_msg"].replace("{name}", user_name)
        await message.answer(welcome_text)
        if chat_db["rules"]:
            await message.answer(f"📜 Правила группы:\n\n{chat_db['rules']}")

@dp.message(IsGroup(), F.left_chat_member)
async def goodbye_member(message: types.Message):
    left_user = message.left_chat_member
    user_name = left_user.first_name if left_user.first_name else left_user.username
    await message.answer(f"Пока, {user_name}, ты, это, если что возвращайся, мы будем тебе рады.")

# === КОМАНДЫ НАСТРОЙКИ ===

@dp.message(Command("newprivet"), IsGroup(), IsBotAdmin())
async def set_welcome_msg(message: types.Message):
    new_text = message.text.replace("/newprivet", "").strip()
    if not new_text:
        return await message.reply("Напиши текст после команды.")
    chat_db = get_chat_db(message.chat.id)
    chat_db["welcome_msg"] = new_text
    await message.reply("✅ Приветственное сообщение обновлено!")

@dp.message(Command("newpravila"), IsGroup(), IsBotAdmin())
async def set_rules(message: types.Message):
    new_rules = message.text.replace("/newpravila", "").strip()
    if not new_rules:
        return await message.reply("Напиши текст правил после команды.")
    chat_db = get_chat_db(message.chat.id)
    chat_db["rules"] = new_rules
    await message.reply("✅ Правила добавлены!")

@dp.message(Command("devpravila"), IsGroup(), IsBotAdmin())
async def del_rules(message: types.Message):
    chat_db = get_chat_db(message.chat.id)
    chat_db["rules"] = None
    await message.reply("🗑 Правила удалены.")

# === КОМАНДЫ МОДЕРАЦИИ ===

@dp.message(Command("unmute"), IsGroup(), IsBotAdmin())
async def unmute_chat(message: types.Message):
    try:
        await bot.set_chat_permissions(message.chat.id, DEFAULT_PERMISSIONS)
        await message.reply("✅ Мут с чата снят! Все участники снова могут писать сообщения.")
    except Exception as e:
        await message.reply(f"❌ Ошибка при снятии мута: {e}")

@dp.message(Command("ban"), IsGroup(), IsBotAdmin())
async def ban_user(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        return await message.reply("Использование: /ban @юзернейм")
    target_username = parts[1]
    user_id = resolve_user_id(target_username)
    
    if not user_id:
        return await message.reply("❌ Не могу найти этого пользователя.")
    await bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
    await message.reply(f"🔨 Участник {target_username} удален из группы.")

@dp.message(Command("mute"), IsGroup(), IsBotAdmin())
async def mute_user(message: types.Message):
    parts = message.text.split(maxsplit=3)
    if len(parts) < 3:
        return await message.reply("Использование: /mute 10m @юзернейм причина")
    
    time_str = parts[1]
    target_username = parts[2]
    reason = parts[3] if len(parts) > 3 else "Без причины"
    
    match = re.match(r"(\d+)([mhd])", time_str)
    if not match:
        return await message.reply("❌ Неверный формат времени.")
    
    amount, unit = int(match.group(1)), match.group(2)
    delta = timedelta(minutes=amount) if unit == 'm' else timedelta(hours=amount) if unit == 'h' else timedelta(days=amount)
        
    until_date = datetime.now() + delta
    user_id = resolve_user_id(target_username)
    
    if not user_id:
        return await message.reply("❌ Не могу найти этого пользователя.")
    
    await bot.restrict_chat_member(message.chat.id, user_id, ChatPermissions(can_send_messages=False), until_date=until_date)
    await message.answer(f"🤐 Участник {target_username} заглушен на {time_str}.\nПричина: {reason}")

# === АВТОМОДЕРАЦИЯ (МАТ) ===

@dp.message(IsGroup())
async def auto_moderator(message: types.Message):
    if not message.text or message.text.startswith('/'):
        return

    text_lower = message.text.lower()
    chat_db = get_chat_db(message.chat.id)
    
    for word in BAD_WORDS:
        if word in text_lower:
            user_id = message.from_user.id
            now = datetime.now()
            
            if user_id not in chat_db["warnings"]:
                chat_db["warnings"][user_id] = []
                
            chat_db["warnings"][user_id] = [w for w in chat_db["warnings"][user_id] if now - w < timedelta(days=7)]
            chat_db["warnings"][user_id].append(now)
            warn_count = len(chat_db["warnings"][user_id])
            
            if warn_count >= 3:
                await bot.ban_chat_member(chat_id=message.chat.id, user_id=user_id)
                await message.reply(f"Участник @{message.from_user.username or message.from_user.first_name} был удален из группы за 3 предупреждения.")
                chat_db["warnings"][user_id] = []
            else:
                await message.reply(f"В чате запрещен мат! Предупреждение {warn_count}/3. (Сгорит через 7 дней).")
            break

async def main():
    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
    scheduler.add_job(morning_routine, trigger='cron', hour=7, minute=0, kwargs={'bot': bot})
    scheduler.add_job(evening_warning, trigger='cron', hour=21, minute=45, kwargs={'bot': bot})
    scheduler.add_job(night_mute, trigger='cron', hour=22, minute=0, kwargs={'bot': bot})
    scheduler.start()

    print("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())