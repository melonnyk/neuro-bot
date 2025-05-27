# Dockerfile для запуска Telegram-бота как самостоятельного процесса
FROM python:3.10-slim

WORKDIR /app

# Сначала копируем файл зависимостей и устанавливаем
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем копируем весь код бота
COPY . .

# Запускаем бот
CMD ["python", "bot.py"]
