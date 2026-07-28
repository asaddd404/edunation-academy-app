# Edunation Academy

Онлайн-платформа учебного центра. Текущий этап: вертикальный срез
регистрация → каталог категорий → заявка → одобрение учителем.

## Стек
FastAPI (async) · Vue 3 + Tailwind · PostgreSQL + Redis · Docker Compose + Nginx.

## Запуск (локально, через Docker)

```bash
cp .env.example .env
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

Frontend: http://localhost/
API: http://localhost/api/v1/
Прямой доступ к backend (для отладки): http://localhost:8000

## Роли
- **student** — регистрируется сам, подаёт заявки на категории.
- **teacher** — назначается администратором на категории, одобряет заявки.
- **admin** — создаёт категории, назначает учителей, управляет пользователями.

Первый администратор создаётся регистрацией обычного пользователя с
последующим ручным изменением роли в БД (самообслуживание для admin/teacher
не предусмотрено):

```sql
UPDATE users SET role = 'admin' WHERE phone = '+7XXXXXXXXXX';
```
