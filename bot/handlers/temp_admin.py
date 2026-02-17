
@admin_router.message(StateFilter(AdminStates.fraud_check_date))
async def fraud_check_date_process(message: types.Message, state: FSMContext):
    """Process date input for fraud check"""
    try:
        # Parse date. format is DD.MM
        date_str = message.text.strip()
        parts = date_str.split('.')
        if len(parts) != 2:
            raise ValueError("Wrong format")
            
        day = int(parts[0])
        month = int(parts[1])
        year = get_now().year
        
        # Create date object
        from datetime import datetime
        start_date = datetime(year, month, day, 0, 0, 0)
        
        # Save to state
        await state.update_data(fraud_check_start_date=start_date.isoformat())
        
        await message.answer(
            f"✅ Дата начала установлена: <b>{day:02d}.{month:02d}.{year}</b>\n\n"
            "Теперь отправьте файл выписки Kaspi (Excel .xlsx или .csv).",
            parse_mode="HTML"
        )
        await state.set_state(AdminStates.fraud_check_file)
        
    except Exception:
        await message.answer(
            "❌ <b>Неверный формат даты!</b>\n"
            "Используйте формат <code>ДД.ММ</code> (например: <code>01.02</code>).\n"
            "Попробуйте снова."
        )