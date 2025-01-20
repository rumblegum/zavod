# config.py
import os
from dotenv import load_dotenv

load_dotenv()  # Читаем файл .env, если он есть

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "7735698208:AAHC7w-UJ69p45Jx7OnzS2yG7HgyFTGV9ls")

# ID пользователя, который будет иметь права "суперадмина" по умолчанию.
# Например, чтобы не плодить "ручные" SQL-запросы, можно задать себя как "первого администратора".
SUPER_ADMIN_TG_ID = os.getenv("SUPER_ADMIN_TG_ID", None)

# Период (в днях), по истечении которого старые данные будут удаляться
OLD_DATA_RETENTION_DAYS = int(os.getenv("OLD_DATA_RETENTION_DAYS", "30"))

# Список доступных цехов (для удобства)
DEPARTMENTS = [
    "Пекарня",
    "Кондитерка",
    "Кухня",
    "Упаковка",
    "Склад",
    "Холодильник",
    "Покупатель"  # "Покупатель" будет условным "виртуальным цехом"
]

# Для удобства можно завести словарь переводов названий ролей, но не обязательно
ROLE_WORKER = "worker"
ROLE_LEADER = "leader"
ROLE_ADMIN = "admin"
