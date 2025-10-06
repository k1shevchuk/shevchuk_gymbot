from aiogram.fsm.state import State, StatesGroup


class StartWorkout(StatesGroup):
    choosing_plan = State()
    selecting_exercise = State()
    in_progress = State()


class EnterSetData(StatesGroup):
    weight = State()
    reps = State()
    rir = State()
    confirm = State()


class WorkoutNavigation(StatesGroup):
    awaiting_action = State()


class SettingsState(StatesGroup):
    choosing_timezone = State()
    choosing_units = State()
    choosing_rir_format = State()
    editing_reminder = State()
    editing_reminder_weekday = State()
    editing_reminder_weekend = State()


class ImportState(StatesGroup):
    waiting_for_file = State()
