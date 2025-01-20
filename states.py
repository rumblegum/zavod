# states.py
from aiogram.dispatcher.filters.state import State, StatesGroup

class RegistrationFSM(StatesGroup):
    waiting_for_name = State()
    waiting_for_role = State()
    waiting_for_department = State()

class TransferFSM(StatesGroup):
    waiting_for_to_department = State()
    waiting_for_dish = State()
    waiting_for_quantity = State()
    waiting_for_label_date = State()
