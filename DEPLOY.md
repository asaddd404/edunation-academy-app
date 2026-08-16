# Развёртывание Edunation Academy

Инструкция под сервер вида **hoster.kz Cloud, Ubuntu 24.04, 1 vCPU / 2 GB RAM / 50 GB**.

---

## 0. Что понадобится

- IP сервера и пароль root (из панели хостинга).
- Домен, у которого **A-запись уже указывает на этот IP**. Это обязательное
  условие: сертификат выдаётся после проверки, что домен ведёт на сервер.
  Проверить: `ping ваш-домен.kz` — должен отвечать IP сервера.

Смена DNS расходится по миру до нескольких часов. Сделайте это заранее.

---

## 1. Подключиться и подготовить сервер

```bash
ssh root@185.129.51.116
```

```bash
apt update && apt upgrade -y
```

**Своп — не пропускайте.** На 2 ГБ RAM сборка фронтенда и Postgres под
нагрузкой упираются в память, и ядро убивает процесс без внятной ошибки.
Полтора гигабайта свопа снимают этот класс проблем:

```bash
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

Docker:

```bash
curl -fsSL https://get.docker.com | sh
```

Файрвол — наружу нужны только SSH и веб:

```bash
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
```

---

## 2. Загрузить код

```bash
apt install -y git
git clone <адрес-репозитория> /opt/edunation
cd /opt/edunation
```

Если репозитория нет — скопируйте папку проекта с компьютера:

```bash
# выполнять НА СВОЁМ компьютере, не на сервере
scp -r "C:/Users/WEST/Desktop/Edunation Academy" root@185.129.51.116:/opt/edunation
```

---

## 3. Настроить переменные

```bash
cp .env.prod.example .env.prod
openssl rand -base64 32 | tr -d '/+=' | head -c 32; echo   # пароль БД
openssl rand -hex 48                                        # JWT_SECRET
nano .env.prod
```

Заполнить: `DOMAIN`, `ACME_EMAIL`, `POSTGRES_PASSWORD` (и тот же пароль внутри
`DATABASE_URL`), `JWT_SECRET`, `CORS_ORIGINS=https://ваш-домен.kz`.

> Пароль БД держите из букв, цифр, `-` и `_`. Символы `:` `@` `/` `#` внутри
> `DATABASE_URL` читаются как разделители URL и молча обрежут пароль —
> подключение будет падать с невнятной ошибкой авторизации.

---

## 4. Запустить

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Первая сборка занимает 5–15 минут (ffmpeg в бэкенде и npm-зависимости).

Применить миграции:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic upgrade head
```

Проверить:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod ps
curl -I https://ваш-домен.kz
```

Сертификат Caddy получает сам при первом обращении и обновляет автоматически —
никаких cron-задач. Если `curl` вернул ошибку сертификата, почти всегда причина
одна: A-запись ещё не разошлась. Посмотреть, что происходит:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod logs web --tail 50
```

---

## 5. Наполнить демо-данными

База стартует пустой — ни пользователей, ни предметов. Скрипт создаёт учителей,
админа, ~50 учеников, курсы с уроками, банк вопросов ЕНТ, заявки, домашние
работы и рейтинг:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend python -m app.seed_demo_data
```

> Данные вымышленные — показывать клиенту безопасно. **Но пароли демо-аккаунтов
> известны и лежат в коде**, а сайт после этого шага доступен всему интернету.
> Смените пароли демонстрационных учителя и админа сразу после сидирования
> (см. раздел ниже), иначе доступ к админ-панели получит любой, кто заглянет в
> репозиторий.

---

## 6. Сменить пароли демо-аккаунтов

Обязательный шаг перед отправкой ссылки клиенту. Скрипт спросит телефон и новый
пароль и обновит хеш:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T backend python - <<'PY'
import asyncio, getpass
from sqlalchemy import select
from app.database import async_session_factory
from app.models.user import User
from app.security import hash_password

async def main():
    phone = input("Телефон (например +77001112233): ").strip()
    password = getpass.getpass("Новый пароль: ")
    async with async_session_factory() as db:
        user = await db.scalar(select(User).where(User.phone == phone))
        if user is None:
            print("Пользователь не найден"); return
        user.password_hash = hash_password(password)
        await db.commit()
        print(f"Пароль обновлён: {user.last_name} {user.first_name} ({user.role})")

asyncio.run(main())
PY
```

> Хеш обязательно считать **внутри контейнера**, как здесь. Если сгенерировать
> его в шелле и подставить в SQL, оболочка съест `$` внутри argon2-хеша
> (`$argon2id$v=19$...`), в базу ляжет обрезанная строка, и вход начнёт падать
> с 500-й ошибкой.

Повторите для админа и учителя. Ученикам можно оставить как есть — они ничего
не ломают, зато клиенту видно живое наполнение.

---

## Обновление после правок

```bash
cd /opt/edunation && git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic upgrade head
```

Загруженные видео и картинки лежат в томе `uploads` и пересборку переживают.

## Бэкап базы

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres \
  pg_dump -U edunation edunation | gzip > ~/backup-$(date +%F).sql.gz
```

Раз в сутки автоматически:

```bash
(crontab -l 2>/dev/null; echo '0 3 * * * cd /opt/edunation && docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T postgres pg_dump -U edunation edunation | gzip > ~/backup-$(date +\%F).sql.gz') | crontab -
```

---

## Что учесть на этом тарифе

- **50 ГБ диска.** Видеоуроки конвертируются в HLS и занимают заметно больше
  исходника. Один курс с видео способен съесть диск целиком — следите за
  `df -h`, а под реальную нагрузку берите объём больше.
- **1 vCPU.** Конвертация видео (ffmpeg) загрузит его полностью и на это время
  подтормозит весь сайт. Для демонстрации клиенту это некритично.
- **Загрузка видео до 2 ГБ** уже разрешена в Caddy и в бэкенде.
