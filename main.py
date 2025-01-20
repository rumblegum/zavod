# main.py
import logging
import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils import executor

from config import (
    BOT_TOKEN, SUPER_ADMIN_TG_ID, DEPARTMENTS, 
    ROLE_ADMIN, ROLE_LEADER, ROLE_WORKER
)
from states import RegistrationFSM, TransferFSM
import database as db

logging.basicConfig(level=logging.INFO)

# ИНИЦИАЛИЗАЦИЯ БОТА И БАЗЫ
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())
conn = db.init_db("factory.db")

# ---- ХЕЛПЕРЫ РОЛЕЙ ----

def user_is_admin_or_leader(user_role: str) -> bool:
    return user_role in [ROLE_ADMIN, ROLE_LEADER]

def user_is_admin(user_role: str) -> bool:
    return user_role == ROLE_ADMIN

# ---- МИДДЛВЭР: ПРОВЕРКА "ПОДТВЕРЖДЁН ЛИ ПОЛЬЗОВАТЕЛЬ" ----
@dp.message_handler()
async def check_approved(message: types.Message):
    """
    Этот хендлер будет проверять, не является ли команда
    системной (уже отловленной другими хендлерами).
    Если пользователь не подтверждён и пытается что-то писать —
    отправляем уведомление. 
    """
    # Если команда /start, /admin, /menu и т.п. — их отлавливают другие хендлеры
    # Но если это что-то "левое", проверим статус подтверждения
    user = db.get_user_by_telegram_id(conn, message.from_user.id)
    if not user:
        return  # Пусть идёт регистрация
    if user[5] == 0:  # approved=0
        await message.answer("Ваш аккаунт ещё не подтверждён администратором. Ожидайте.")
    else:
        # Просто игнорируем, если нет подходящего хендлера
        pass


# --- START: РЕГИСТРАЦИЯ ---

@dp.message_handler(commands=["start"], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    user = db.get_user_by_telegram_id(conn, message.from_user.id)

    # Если SUPER_ADMIN_TG_ID задали, и этот человек впервые запускает бота —
    # делаем его админом сразу, без подтверждения
    if user is None and SUPER_ADMIN_TG_ID is not None:
        try:
            if int(SUPER_ADMIN_TG_ID) == message.from_user.id:
                # Создаём запись пользователя как админа
                db.create_user(conn, message.from_user.id, "SuperAdmin", ROLE_ADMIN, "АдминОтдел", approved=1)
                await message.answer("Вы являетесь супер-админом. Учётная запись создана и подтверждена.")
                return
        except:
            pass

    if not user:
        # Начинаем процесс регистрации
        await message.answer("Здравствуйте! Похоже, вы здесь впервые. Введите ваше ФИО:")
        await RegistrationFSM.waiting_for_name.set()
    else:
        # Если пользователь есть
        user_id, tg_id, full_name, role, department, approved = user
        if approved == 0:
            await message.answer("Ваша учётная запись ещё не подтверждена администратором.")
        else:
            # Утверждённый пользователь
            await message.answer(
                f"С возвращением, {full_name}!\n"
                f"Отдел: {department}, Роль: {role}\n\n"
                f"Для выбора действий используйте /menu",
                reply_markup=ReplyKeyboardRemove()
            )

# --- FSM Регистрация ---
@dp.message_handler(state=RegistrationFSM.waiting_for_name, content_types=types.ContentTypes.TEXT)
async def reg_full_name(message: types.Message, state: FSMContext):
    await state.update_data(full_name=message.text)
    # Выбираем роль
    buttons = [
        InlineKeyboardButton("Работник", callback_data="role_worker"),
        InlineKeyboardButton("Руководитель", callback_data="role_leader")
    ]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("Выберите вашу роль:", reply_markup=markup)
    await RegistrationFSM.waiting_for_role.set()

@dp.callback_query_handler(Text(startswith="role_"), state=RegistrationFSM.waiting_for_role)
async def reg_role(callback_query: types.CallbackQuery, state: FSMContext):
    if callback_query.data not in ["role_worker", "role_leader"]:
        await callback_query.answer("Некорректный выбор.")
        return
    role = ROLE_WORKER if callback_query.data == "role_worker" else ROLE_LEADER
    await state.update_data(role=role)

    # Спрашиваем цех
    markup = InlineKeyboardMarkup(row_width=2)
    for dep in DEPARTMENTS:
        markup.add(InlineKeyboardButton(dep, callback_data=f"dep_{dep}"))

    await callback_query.message.edit_text("Выберите ваш отдел:", reply_markup=markup)
    await RegistrationFSM.waiting_for_department.set()

@dp.callback_query_handler(Text(startswith="dep_"), state=RegistrationFSM.waiting_for_department)
async def reg_department(callback_query: types.CallbackQuery, state: FSMContext):
    department = callback_query.data.split("_", 1)[1]
    data = await state.get_data()
    full_name = data.get("full_name")
    role = data.get("role")

    try:
        db.create_user(conn, callback_query.from_user.id, full_name, role, department, approved=0)
        await callback_query.message.edit_text(
            "Спасибо за регистрацию!\n"
            "Пожалуйста, дождитесь подтверждения вашего аккаунта администратором."
        )
    except:
        await callback_query.message.edit_text(
            "Ошибка при регистрации. Возможно, вы уже зарегистрированы. Обратитесь к администратору."
        )
    await state.finish()

# --- /admin панель ---

@dp.message_handler(commands=["admin"])
async def cmd_admin(message: types.Message):
    user = db.get_user_by_telegram_id(conn, message.from_user.id)
    if not user:
        return
    # (id, tg_id, full_name, role, department, approved)
    role = user[3]
    if role != ROLE_ADMIN:
        await message.answer("Вы не администратор.")
        return

    # Меню администратора
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Список неподтверждённых", callback_data="admin_list_pending"))
    markup.add(InlineKeyboardButton("Добавить блюдо", callback_data="admin_add_dish"))
    markup.add(InlineKeyboardButton("Очистка старых данных", callback_data="admin_cleanup"))
    await message.answer("Панель администратора:", reply_markup=markup)

@dp.callback_query_handler(Text(startswith="admin_"))
async def admin_callbacks(callback_query: types.CallbackQuery):
    user = db.get_user_by_telegram_id(conn, callback_query.from_user.id)
    if not user or user[3] != ROLE_ADMIN:
        await callback_query.answer("Нет прав администратора.")
        return

    data = callback_query.data
    if data == "admin_list_pending":
        rows = db.get_all_pending_users(conn)
        if not rows:
            await callback_query.message.edit_text("Нет неподтверждённых пользователей.")
        else:
            lines = []
            markup = InlineKeyboardMarkup()
            for (uid, fname, r, dep) in rows:
                lines.append(f"{uid} — {fname} ({r}, {dep})")
                markup.add(InlineKeyboardButton(f"Подтвердить {uid}", callback_data=f"admin_approve_{uid}"))
            await callback_query.message.edit_text("\n".join(lines), reply_markup=markup)

    elif data.startswith("admin_approve_"):
        uid_str = data.split("_")[-1]
        try:
            uid = int(uid_str)
            db.approve_user(conn, uid)
            await callback_query.answer("Пользователь подтверждён!", show_alert=True)
            await callback_query.message.delete()
        except:
            await callback_query.answer("Ошибка ID.")

    elif data == "admin_add_dish":
        await callback_query.message.edit_text("Введите новое блюдо в формате: <b>Название, Категория</b>")

        @dp.message_handler(content_types=types.ContentTypes.TEXT, state="*")
        async def add_dish_handler(msg: types.Message):
            if "," not in msg.text:
                await msg.answer("Неверный формат. Нужно: Название, Категория.")
                return
            name, category = msg.text.split(",", 1)
            name, category = name.strip(), category.strip()
            db.add_dish(conn, name, category)
            # Удаляем этот хендлер (чтобы не срабатывал каждый раз). 
            # В реальном проекте лучше FSM, но для примера — так.
            dp.message_handlers.unregister(add_dish_handler)
            await msg.answer(f"Блюдо '{name}' добавлено с категорией '{category}'.")

    elif data == "admin_cleanup":
        db.cleanup_old_data(conn)
        await callback_query.message.edit_text("Очистка старых данных выполнена.")

# --- /menu ---

@dp.message_handler(commands=["menu"])
async def cmd_menu(message: types.Message):
    user = db.get_user_by_telegram_id(conn, message.from_user.id)
    if not user:
        return
    role = user[3]
    approved = user[5]
    if approved == 0:
        await message.answer("Аккаунт не подтверждён админом.")
        return

    # Главное меню
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Передать товар", callback_data="menu_transfer"))
    if role in [ROLE_LEADER, ROLE_ADMIN]:
        markup.add(InlineKeyboardButton("Отчёты", callback_data="menu_reports"))
    markup.add(InlineKeyboardButton("Мои входящие", callback_data="menu_incoming"))
    await message.answer("Выберите действие:", reply_markup=markup)

# --- Обработка кнопок меню ---
@dp.callback_query_handler(Text(startswith="menu_"))
async def menu_callbacks(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    user = db.get_user_by_telegram_id(conn, callback_query.from_user.id)
    if not user:
        await callback_query.answer("Нет пользователя.")
        return
    role = user[3]
    user_id = user[0]
    department = user[4]
    approved = user[5]

    if approved == 0:
        await callback_query.answer("Аккаунт не подтверждён.")
        return

    if data == "menu_transfer":
        # Начинаем FSM передачи
        await callback_query.answer()
        buttons = []
        for dep in DEPARTMENTS:
            buttons.append(InlineKeyboardButton(dep, callback_data=f"to_dep_{dep}"))
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(*buttons)
        await callback_query.message.edit_text("Выберите цех (или покупателя) для передачи:", reply_markup=markup)
        await TransferFSM.waiting_for_to_department.set()

    elif data == "menu_reports":
        # Меню отчётов
        if not user_is_admin_or_leader(role):
            await callback_query.answer("Нет прав для отчётов.")
            return
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Отчёт за сегодня", callback_data="report_today"))
        markup.add(InlineKeyboardButton("Отчёт за всё время", callback_data="report_all"))
        await callback_query.message.edit_text("Выберите отчёт:", reply_markup=markup)

    elif data == "menu_incoming":
        # Показать входящие транзакции
        pending = db.get_pending_transactions_for_department(conn, department)
        if not pending:
            await callback_query.message.edit_text("Нет ожидающих приёмки товаров.")
        else:
            lines = ["<b>Ожидающие приёмки:</b>"]
            markup = InlineKeyboardMarkup()
            for (tid, dish_name, qty, from_dep, lbl_date) in pending:
                label_info = f" (дата: {lbl_date})" if lbl_date else ""
                lines.append(f"#{tid} | {dish_name} x {qty} | из {from_dep}{label_info}")
                btn_a = InlineKeyboardButton(f"Принять #{tid}", callback_data=f"accept_{tid}")
                btn_r = InlineKeyboardButton(f"Отклонить #{tid}", callback_data=f"reject_{tid}")
                markup.row(btn_a, btn_r)
            await callback_query.message.edit_text("\n".join(lines), reply_markup=markup)

# --- FSM ПЕРЕДАЧА ---

@dp.callback_query_handler(Text(startswith="to_dep_"), state=TransferFSM.waiting_for_to_department)
async def select_to_department(callback_query: types.CallbackQuery, state: FSMContext):
    to_dep = callback_query.data.split("_", 1)[1]
    await callback_query.answer()

    await state.update_data(to_department=to_dep)
    dishes = db.get_all_dishes(conn)
    if not dishes:
        await callback_query.message.edit_text("Нет доступных блюд. Добавьте блюдо через админа.")
        await state.finish()
        return
    markup = InlineKeyboardMarkup(row_width=2)
    for (dish_id, name, cat) in dishes:
        markup.add(InlineKeyboardButton(f"{name} ({cat})", callback_data=f"dish_{dish_id}"))
    await callback_query.message.edit_text("Выберите блюдо:", reply_markup=markup)

    await TransferFSM.waiting_for_dish.set()

@dp.callback_query_handler(Text(startswith="dish_"), state=TransferFSM.waiting_for_dish)
async def select_dish(callback_query: types.CallbackQuery, state: FSMContext):
    dish_id_str = callback_query.data.split("_")[1]
    await callback_query.answer()
    await state.update_data(dish_id=dish_id_str)
    await callback_query.message.edit_text("Введите количество (число):")
    await TransferFSM.waiting_for_quantity.set()

@dp.message_handler(state=TransferFSM.waiting_for_quantity)
async def set_quantity(message: types.Message, state: FSMContext):
    try:
        qty = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число.")
        return

    await state.update_data(quantity=qty)

    user = db.get_user_by_telegram_id(conn, message.from_user.id)
    from_dep = user[4]
    data = await state.get_data()
    to_dep = data["to_department"]

    # Проверяем, нужна ли дата этикетки
    need_label_date = False
    if (from_dep == "Упаковка" and to_dep == "Холодильник") or (from_dep == "Холодильник" and to_dep == "Покупатель"):
        need_label_date = True

    if need_label_date:
        await message.answer("Введите дату на этикетке (например, 20.01.2025):")
        await TransferFSM.waiting_for_label_date.set()
    else:
        # Сразу завершаем транзакцию
        await finalize_transfer(message, state, label_date=None)

@dp.message_handler(state=TransferFSM.waiting_for_label_date)
async def set_label_date(message: types.Message, state: FSMContext):
    label_date = message.text.strip()
    await finalize_transfer(message, state, label_date)

async def finalize_transfer(message: types.Message, state: FSMContext, label_date):
    user = db.get_user_by_telegram_id(conn, message.from_user.id)
    if not user:
        await message.answer("Ошибка пользователя.")
        await state.finish()
        return
    user_id = user[0]
    from_dep = user[4]
    data = await state.get_data()
    to_dep = data["to_department"]
    dish_id = data["dish_id"]
    qty = data["quantity"]

    # Определяем статус (pending / auto_done)
    auto_departments = [("Упаковка", "Холодильник"), ("Холодильник", "Покупатель")]
    if (from_dep, to_dep) in auto_departments:
        status = "auto_done"
    else:
        status = "pending"

    trans_id = db.create_transaction(conn, user_id, from_dep, to_dep, dish_id, qty, label_date, status)
    db.log_action(conn, user_id, f"Create transaction #{trans_id}")

    # Уведомляем отправителя
    if status == "auto_done":
        await message.answer(
            f"Товар передан без подтверждения (auto_done).\n"
            f"Цех: {to_dep}, Кол-во: {qty}, label={label_date}"
        )
        # Уведомим админов
        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM users WHERE role='admin' AND approved=1")
        admins = cursor.fetchall()
        for (adm_tg,) in admins:
            await bot.send_message(
                adm_tg,
                f"[AUTO] {from_dep} -> {to_dep}, кол-во={qty}, label={label_date}, trans_id={trans_id}"
            )
    else:
        await message.answer(
            f"Транзакция #{trans_id} создана. Ожидаем приёмку.\n"
            f"{from_dep} -> {to_dep}, кол-во={qty}"
        )
        # Уведомить получателей (если не Холодильник/Покупатель)
        if to_dep not in ["Холодильник", "Покупатель"]:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT telegram_id FROM users
                WHERE department=? AND approved=1
            """, (to_dep,))
            rows = cursor.fetchall()
            for (tg_id,) in rows:
                try:
                    await bot.send_message(
                        tg_id,
                        f"Вам поступил товар из {from_dep} (trans_id={trans_id}). "
                        "Подтвердите приёмку через /menu -> 'Мои входящие'."
                    )
                except:
                    pass

    await state.finish()

# --- Принятие / Отклонение транзакций ---

@dp.callback_query_handler(Text(startswith=("accept_", "reject_")))
async def handle_accept_reject(callback_query: types.CallbackQuery):
    user = db.get_user_by_telegram_id(conn, callback_query.from_user.id)
    if not user:
        await callback_query.answer("Ошибка пользователя.")
        return
    user_id = user[0]
    department = user[4]
    data = callback_query.data.split("_", 1)
    action = data[0]  # "accept" или "reject"
    trans_id_str = data[1]

    try:
        trans_id = int(trans_id_str)
    except:
        await callback_query.answer("Некорректный ID транзакции.")
        return

    # Проверим, действительно ли эта транзакция 'pending' и принадлежит department
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM transactions
        WHERE id=? AND to_department=? AND status='pending'
    """, (trans_id, department))
    row = cursor.fetchone()
    if not row:
        await callback_query.answer("Транзакция не найдена или уже не в статусе 'pending'.")
        return

    if action == "accept":
        db.accept_transaction(conn, trans_id)
        db.log_action(conn, user_id, f"Accepted transaction #{trans_id}")
        await callback_query.answer("Товар принят!", show_alert=True)
        await callback_query.message.delete()
    else:
        db.reject_transaction(conn, trans_id)
        db.log_action(conn, user_id, f"Rejected transaction #{trans_id}")
        await callback_query.answer("Транзакция отклонена!", show_alert=True)
        await callback_query.message.delete()

# --- REPORTS ---

@dp.callback_query_handler(Text(startswith="report_"))
async def handle_reports(callback_query: types.CallbackQuery):
    data = callback_query.data
    report_type = data.split("_", 1)[1]  # "today" or "all"
    now = datetime.datetime.now()
    if report_type == "today":
        date_str = now.date().isoformat()
        rows = db.get_transactions_by_date(conn, date_str)
        if not rows:
            await callback_query.message.edit_text("Сегодня транзакций не было.")
        else:
            lines = [f"<b>Отчёт за {date_str}:</b>"]
            for (tid, fdep, tdep, dname, qty, lbl, created, accepted, st) in rows:
                lines.append(f"#{tid} | {fdep} -> {tdep} | {dname} x {qty} | {st}")
            await callback_query.message.edit_text("\n".join(lines))
    elif report_type == "all":
        rows = db.get_transactions_by_date(conn, None)
        if not rows:
            await callback_query.message.edit_text("Транзакций нет.")
        else:
            lines = ["<b>Все транзакции:</b>"]
            for (tid, fdep, tdep, dname, qty, lbl, created, accepted, st) in rows:
                lines.append(f"#{tid} | {fdep} -> {tdep} | {dname} x {qty} | {st}")
            await callback_query.message.edit_text("\n".join(lines))

    await callback_query.answer()

# --- Запуск ---

if __name__ == "__main__":
    logging.info("Starting bot...")
    executor.start_polling(dp, skip_updates=True)
