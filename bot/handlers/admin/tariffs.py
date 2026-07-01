from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.states import AdminTariffFlow
from database.models import Host, Tariff

router = Router(name="admin_tariffs")


@router.message(lambda m: m.text == "📦 Тарифы")
async def list_tariffs(message: Message, session: AsyncSession, is_admin: bool) -> None:
    if not is_admin:
        return
    tariffs = (await session.execute(select(Tariff))).scalars().all()
    rows = [
        [InlineKeyboardButton(text=f"{t.name} {'✅' if t.is_active else '🚫'}", callback_data=f"admin_tariff_toggle:{t.id}")]
        for t in tariffs
    ]
    rows.append([InlineKeyboardButton(text="➕ Добавить тариф", callback_data="admin_tariff_add")])
    text = "Тарифы:\n" + "\n".join(f"• {t.name} — {t.price}₽ / {t.duration_days}д" for t in tariffs) if tariffs else "Тарифов пока нет."
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))


@router.callback_query(F.data == "admin_tariff_add")
async def add_tariff_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    hosts = (await session.execute(select(Host).where(Host.is_active.is_(True)))).scalars().all()
    if not hosts:
        await callback.message.answer("Сначала добавьте хост.")
        await callback.answer()
        return
    rows = [[InlineKeyboardButton(text=h.name, callback_data=f"admin_tariff_host:{h.id}")] for h in hosts]
    await state.set_state(AdminTariffFlow.choosing_host)
    await callback.message.answer("Выберите хост для тарифа:", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer()


@router.callback_query(AdminTariffFlow.choosing_host, F.data.startswith("admin_tariff_host:"))
async def add_tariff_host(callback: CallbackQuery, state: FSMContext) -> None:
    host_id = int(callback.data.split(":")[1])
    await state.update_data(host_id=host_id)
    await state.set_state(AdminTariffFlow.entering_name)
    await callback.message.answer("Введите название тарифа:")
    await callback.answer()


@router.message(AdminTariffFlow.entering_name)
async def add_tariff_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text)
    await state.set_state(AdminTariffFlow.entering_price)
    await message.answer("Введите цену в рублях (число):")


@router.message(AdminTariffFlow.entering_price)
async def add_tariff_price(message: Message, state: FSMContext) -> None:
    try:
        price = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число, например 199")
        return
    await state.update_data(price=price)
    await state.set_state(AdminTariffFlow.entering_duration)
    await message.answer("Введите длительность в днях (число):")


@router.message(AdminTariffFlow.entering_duration)
async def add_tariff_duration(message: Message, state: FSMContext) -> None:
    if not message.text.isdigit():
        await message.answer("Введите целое число дней.")
        return
    await state.update_data(duration_days=int(message.text))
    await state.set_state(AdminTariffFlow.entering_traffic)
    await message.answer("Введите лимит трафика в ГБ (0 = безлимит):")


@router.message(AdminTariffFlow.entering_traffic)
async def add_tariff_traffic(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if not message.text.isdigit():
        await message.answer("Введите целое число.")
        return
    data = await state.get_data()
    tariff = Tariff(
        host_id=data["host_id"], name=data["name"], price=data["price"],
        duration_days=data["duration_days"], traffic_limit_gb=int(message.text),
    )
    session.add(tariff)
    await session.commit()
    await state.clear()
    await message.answer(f"Тариф «{tariff.name}» создан.")


@router.callback_query(F.data.startswith("admin_tariff_toggle:"))
async def toggle_tariff(callback: CallbackQuery, session: AsyncSession) -> None:
    tariff_id = int(callback.data.split(":")[1])
    tariff = (await session.execute(select(Tariff).where(Tariff.id == tariff_id))).scalar_one_or_none()
    if tariff:
        tariff.is_active = not tariff.is_active
        await session.commit()
        await callback.message.answer(f"Тариф «{tariff.name}»: активен = {tariff.is_active}")
    await callback.answer()
