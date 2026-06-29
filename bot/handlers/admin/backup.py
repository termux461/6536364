from pathlib import Path

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from bot.keyboards.admin import admin_back_menu, admin_restore_confirm_menu
from bot.services.backup import BackupError, create_backup, restore_backup
from bot.utils.helpers import admin_filter
from bot.utils.states import AdminRestore

router = Router(name="admin_backup")
router.message.filter(admin_filter)
router.callback_query.filter(admin_filter)


@router.callback_query(F.data == "admin:backup")
async def cb_admin_backup(callback: CallbackQuery) -> None:
    await callback.message.edit_text("Создаю бэкап базы данных...")
    try:
        zip_path = await create_backup()
    except BackupError as exc:
        await callback.message.edit_text(f"Ошибка бэкапа: {exc}", reply_markup=admin_back_menu())
        await callback.answer()
        return

    await callback.message.answer_document(FSInputFile(zip_path), caption="Бэкап базы данных МАМОНТ ВПН")
    await callback.message.answer("Готово.", reply_markup=admin_back_menu())
    await callback.answer()


@router.callback_query(F.data == "admin:restore")
async def cb_admin_restore(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminRestore.waiting_file)
    await callback.message.edit_text(
        "Отправьте .zip файл с бэкапом базы данных для восстановления.",
        reply_markup=admin_back_menu(),
    )
    await callback.answer()


@router.message(AdminRestore.waiting_file, F.document)
async def msg_admin_restore_file(message: Message, state: FSMContext) -> None:
    if not message.document.file_name.endswith(".zip"):
        await message.answer("Нужен .zip файл. Попробуйте снова.")
        return

    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)
    file_path = backup_dir / message.document.file_name
    await message.bot.download(message.document, destination=file_path)

    await state.update_data(restore_path=str(file_path))
    await message.answer(
        "⚠️ Внимание! Восстановление полностью заменит текущие данные в базе. Продолжить?",
        reply_markup=admin_restore_confirm_menu(),
    )


@router.callback_query(F.data == "admin:restore:confirm")
async def cb_admin_restore_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    restore_path = data.get("restore_path")
    await state.clear()
    if not restore_path:
        await callback.answer("Файл бэкапа не найден, начните заново.", show_alert=True)
        return

    await callback.message.edit_text("Восстанавливаю базу данных...")
    try:
        await restore_backup(Path(restore_path))
    except BackupError as exc:
        await callback.message.edit_text(f"Ошибка восстановления: {exc}", reply_markup=admin_back_menu())
        await callback.answer()
        return

    await callback.message.edit_text("База данных успешно восстановлена.", reply_markup=admin_back_menu())
    await callback.answer()
