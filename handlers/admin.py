from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from keyboards.inline import (
    admin_kb, admin_plans_kb, admin_plan_edit_kb, back_kb
)
from services.database import Database
from config import Config

router = Router()

PROTO_NAMES = {"wg": "⚡ WireGuard", "awg": "🛡 AmneziaWG 2.0"}


def is_admin(user_id: int, config: Config) -> bool:
    return user_id in config.ADMIN_IDS


class AdminStates(StatesGroup):
    set_price      = State()
    add_plan_proto = State()
    add_plan_name  = State()
    add_plan_days  = State()
    add_plan_price = State()
    add_promo_code  = State()
    add_promo_bonus = State()
    add_promo_uses  = State()


# ── Main ──────────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, config: Config, state: FSMContext):
    if not is_admin(message.from_user.id, config):
        return
    await state.clear()
    await message.answer("🛠 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=admin_kb())


@router.callback_query(F.data == "adm:main")
async def adm_main(call: CallbackQuery, config: Config, state: FSMContext):
    if not is_admin(call.from_user.id, config):
        return
    await state.clear()
    await call.message.edit_text("🛠 <b>Панель администратора</b>", parse_mode="HTML", reply_markup=admin_kb())
    await call.answer()


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:stats")
async def adm_stats(call: CallbackQuery, db: Database, config: Config):
    if not is_admin(call.from_user.id, config):
        return
    users = await db.get_user_count()
    revenue = await db.get_total_revenue()
    await call.message.edit_text(
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"💰 Выручка: <b>{revenue}₽</b>",
        parse_mode="HTML",
        reply_markup=back_kb("adm:main")
    )
    await call.answer()


# ── Plans ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:plans:"))
async def adm_plans(call: CallbackQuery, db: Database, config: Config):
    if not is_admin(call.from_user.id, config):
        return
    protocol = call.data.split(":")[2]
    plans = await db.get_plans_by_protocol_all(protocol)
    proto_name = PROTO_NAMES.get(protocol, protocol)
    await call.message.edit_text(
        f"📦 <b>Тарифы — {proto_name}</b>",
        parse_mode="HTML",
        reply_markup=admin_plans_kb(plans, protocol)
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:plan_edit:"))
async def adm_plan_edit(call: CallbackQuery, db: Database, config: Config):
    if not is_admin(call.from_user.id, config):
        return
    plan_id = int(call.data.split(":")[2])
    plan = await db.get_plan(plan_id)
    status = "✅ Активен" if plan["active"] else "❌ Отключён"
    proto_name = PROTO_NAMES.get(plan["protocol"], plan["protocol"])
    await call.message.edit_text(
        f"📦 <b>{plan['name']}</b>  ·  {proto_name}\n\n"
        f"💰 Цена: <b>{plan['price']}₽</b>\n"
        f"📅 Дней: <b>{plan['duration_days']}</b>\n"
        f"Статус: {status}",
        parse_mode="HTML",
        reply_markup=admin_plan_edit_kb(plan_id, plan["active"], plan["protocol"])
    )
    await call.answer()


@router.callback_query(F.data.startswith("adm:plan_toggle:"))
async def adm_plan_toggle(call: CallbackQuery, db: Database, config: Config):
    if not is_admin(call.from_user.id, config):
        return
    plan_id = int(call.data.split(":")[2])
    await db.toggle_plan(plan_id)
    plan = await db.get_plan(plan_id)
    status = "✅ Активен" if plan["active"] else "❌ Отключён"
    proto_name = PROTO_NAMES.get(plan["protocol"], plan["protocol"])
    await call.message.edit_text(
        f"📦 <b>{plan['name']}</b>  ·  {proto_name}\n\n"
        f"💰 Цена: <b>{plan['price']}₽</b>\n"
        f"📅 Дней: <b>{plan['duration_days']}</b>\n"
        f"Статус: {status}",
        parse_mode="HTML",
        reply_markup=admin_plan_edit_kb(plan_id, plan["active"], plan["protocol"])
    )
    await call.answer("Статус изменён ✅")


@router.callback_query(F.data.startswith("adm:plan_price:"))
async def adm_plan_price_start(call: CallbackQuery, config: Config, state: FSMContext):
    if not is_admin(call.from_user.id, config):
        return
    plan_id = int(call.data.split(":")[2])
    await state.set_state(AdminStates.set_price)
    await state.update_data(plan_id=plan_id)
    await call.message.edit_text("✏️ Введите новую цену (только цифры):")
    await call.answer()


@router.message(AdminStates.set_price)
async def adm_set_price(message: Message, db: Database, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        price = int(message.text.strip())
        assert price > 0
    except (ValueError, AssertionError):
        await message.answer("❌ Введите корректное число")
        return
    data = await state.get_data()
    await db.update_plan_price(data["plan_id"], price)
    await state.clear()
    plan = await db.get_plan(data["plan_id"])
    plans = await db.get_plans_by_protocol_all(plan["protocol"])
    await message.answer("✅ Цена обновлена!", reply_markup=admin_plans_kb(plans, plan["protocol"]))


# ── Add plan ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:plan_add:"))
async def adm_plan_add_start(call: CallbackQuery, config: Config, state: FSMContext):
    if not is_admin(call.from_user.id, config):
        return
    protocol = call.data.split(":")[2]
    await state.set_state(AdminStates.add_plan_name)
    await state.update_data(protocol=protocol)
    proto_name = PROTO_NAMES.get(protocol, protocol)
    await call.message.edit_text(f"➕ Новый тариф для <b>{proto_name}</b>\n\nВведите название (напр. «2 месяца»):", parse_mode="HTML")
    await call.answer()


@router.message(AdminStates.add_plan_name)
async def adm_plan_name(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    await state.update_data(name=message.text.strip())
    await state.set_state(AdminStates.add_plan_days)
    await message.answer("📅 Количество дней:")


@router.message(AdminStates.add_plan_days)
async def adm_plan_days(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        days = int(message.text.strip())
        assert days > 0
    except (ValueError, AssertionError):
        await message.answer("❌ Введите число")
        return
    await state.update_data(days=days)
    await state.set_state(AdminStates.add_plan_price)
    await message.answer("💰 Цена в рублях:")


@router.message(AdminStates.add_plan_price)
async def adm_plan_price_new(message: Message, state: FSMContext, db: Database, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        price = int(message.text.strip())
        assert price > 0
    except (ValueError, AssertionError):
        await message.answer("❌ Введите число")
        return
    data = await state.get_data()
    await db.add_plan(data["protocol"], data["name"], data["days"], price)
    await state.clear()
    plans = await db.get_plans_by_protocol_all(data["protocol"])
    proto_name = PROTO_NAMES.get(data["protocol"], data["protocol"])
    await message.answer(
        f"✅ Тариф <b>{data['name']}</b> добавлен в {proto_name}!",
        parse_mode="HTML",
        reply_markup=admin_plans_kb(plans, data["protocol"])
    )


# ── Promos ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:promos")
async def adm_promos(call: CallbackQuery, db: Database, config: Config):
    if not is_admin(call.from_user.id, config):
        return
    promos = await db.get_all_promos()
    lines = ["🎟 <b>Промокоды:</b>\n"]
    for p in promos:
        status = "✅" if p["active"] and p["uses_left"] > 0 else "❌"
        uses = "∞" if p["uses_left"] >= 999999 else str(p["uses_left"])
        lines.append(f"{status} <code>{p['code']}</code> — {p['bonus']}₽, осталось: {uses}")

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Создать промокод", callback_data="adm:promo_add")],
        [InlineKeyboardButton(text="◀️ Назад",             callback_data="adm:main")],
    ])
    await call.message.edit_text(
        "\n".join(lines) if promos else "🎟 Промокодов нет.",
        parse_mode="HTML", reply_markup=kb
    )
    await call.answer()


@router.callback_query(F.data == "adm:promo_add")
async def adm_promo_add(call: CallbackQuery, config: Config, state: FSMContext):
    if not is_admin(call.from_user.id, config):
        return
    await state.set_state(AdminStates.add_promo_code)
    await call.message.edit_text("🎟 Введите код промокода (латиница):")
    await call.answer()


@router.message(AdminStates.add_promo_code)
async def adm_promo_code(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    await state.update_data(code=message.text.strip().upper())
    await state.set_state(AdminStates.add_promo_bonus)
    await message.answer("💰 Бонус в рублях:")


@router.message(AdminStates.add_promo_bonus)
async def adm_promo_bonus(message: Message, state: FSMContext, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        bonus = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Число")
        return
    await state.update_data(bonus=bonus)
    await state.set_state(AdminStates.add_promo_uses)
    await message.answer("🔢 Кол-во использований (0 = безлимит):")


@router.message(AdminStates.add_promo_uses)
async def adm_promo_uses(message: Message, state: FSMContext, db: Database, config: Config):
    if not is_admin(message.from_user.id, config):
        return
    try:
        uses = int(message.text.strip())
        if uses == 0:
            uses = 999999
    except ValueError:
        await message.answer("❌ Число")
        return
    data = await state.get_data()
    await db.create_promo(data["code"], data["bonus"], uses)
    await state.clear()
    label = "∞" if uses >= 999999 else str(uses)
    await message.answer(
        f"✅ Промокод <code>{data['code']}</code> создан!\n"
        f"Бонус: {data['bonus']}₽, использований: {label}",
        parse_mode="HTML"
    )
