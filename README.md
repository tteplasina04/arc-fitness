# ARC.FITNESS

Веб-сайт фитнес-клуба на Python (FastAPI) + PostgreSQL

## Запуск

### Docker
```bash
docker compose up --build
```

### Локально
```bash
# Создать БД
psql postgres -c "CREATE DATABASE arc_fitness OWNER arc_user;"
psql -U arc_user -d arc_fitness -f app/schema.sql

# Установить зависимости
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Запустить сервер
uvicorn app.main:app --reload
```

Откройте http://localhost:8000

## Админ-панель

- **URL:** http://localhost:8000/admin
- **Email:** admin@arc.fitness
- **Пароль:** admin123

## Настройка

Скопируйте `.env.example` в `.env` и настройте параметры.
