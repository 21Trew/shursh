# Шурш! — рабочий локальный MVP

**«Дарить приятно. Угадывать необязательно».** Вишлисты и Тайный Санта с авторскими SVG-иллюстрациями и отзывчивым интерфейсом.

## Самый быстрый просмотр

Открой `shursh-preview.html` в браузере — это **автономная интерактивная демоверсия**. Она запускается без Python, Node.js, регистрации и интернета (для надёжной офлайн-работы используется системный шрифт). Примерные данные уже есть. Работают создание и редактирование списков, желания, локальная имитация бронирований, создание игр, добавление участников, исключения, жеребьёвка и раскрытие.

**Важно:** автономная HTML-демоверсия сохраняет данные в `localStorage`. Данные не синхронизируются между людьми, а результаты жеребьёвки не защищены от пользователя с доступом к devtools. Ссылки работают только в рамках этого файла и того же браузера. Для реальных сценариев с гостевым доступом используй серверную версию.

## Локальный запуск с настоящим сервером и SQLite

**Требование:** Python 3.10+ (проверялось на Python 3.13). Никакие пакеты для запуска не нужны.

**Windows:** дважды кликни `start-windows.bat` (при установленном Python). Откроется браузер, а консоль с сервером должна оставаться запущенной.

**macOS / Linux:**

```bash
python3 server.py
```

Открой [http://127.0.0.1:8787](http://127.0.0.1:8787).

Вход в тестовый аккаунт: открой **Войти → Войти в демонстрационный аккаунт**, либо используй `demo@shursh.local` / `demo12345`. Можешь зарегистрировать отдельный аккаунт с собственным паролем.

Данные автоматически сохраняются в `data/shursh.sqlite3`; изображения — в `uploads/`. Перезапуск сервера данные не удаляет. Демоданные создаются только при первом запуске на пустой базе. Перед работой с настоящими пользователями установи `SHURSH_DEMO=0` и используй новую чистую БД. В таком режиме автоматический демовход отключён, существующему демо-адресу тоже запрещён вход. **Эта версия не предназначена для публичного доступа в интернет.**

## Что можно проверить

1. Войти → создать вишлист → добавить подарок/идею, ссылку, стоимость, приоритет, необязательную фотографию → скопировать ссылку.
2. Открыть ссылку в **другом браузере / инкогнито** → забронировать подарок → сохранить приватную ссылку управления бронью → отменить. У владельца информация о брони отсутствует в серверном ответе личного API.
3. Создать Тайного Санту → скопировать приглашение → присоединить гостей из отдельных браузерных сессий → добавить пожелания → создать ограничения для пар → запустить жеребьёвку → открыть персональные конверты из приватных ссылок.

### Ключевое о приватности

- Владелец, работающий в авторизованной сессии, не получает флаг бронирования даже в публичном API списка. Однако **владелец, открывший свою публичную ссылку как анонимный гость, технически увидит занятость** — универсально предотвратить это без обязательной идентификации всех гостей невозможно.
- Бронь создаётся атомарно; активных броней для одного желания не может быть более одной благодаря частичному уникальному индексу SQLite.
- Гость управляет своей бронью через непредсказуемый приватный токен. Токен в БД хранится только в виде SHA-256.
- Личный токен участника игры не раскрывает данные других назначений. Полную таблицу жеребьёвки API не отдаёт даже организатору.
- В локальной серверной версии аккаунты защищаются паролями (scrypt), а не отправляемыми по email magic links: email-провайдер не подключён.

## Автоматические проверки

В `.github/workflows/ci.yml` настроены GitHub Actions: Python 3.11/3.13 (API-тесты) и Node 22 (проверка синтаксиса JS). Их результат на GitHub станет известен только после первой загрузки репозитория.

## Тесты

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q tests/test_api.py
```

`tests/test_api.py` поднимает сервер во временной базе и проверяет API, алгоритм жеребьёвки, исключения, приватность, двойные и одновременные бронирования. См. `TEST_REPORT.md`.

## Организация проекта

```
server.py                 HTTP API + SQLite + авторизация + распределение
public/index.html         Браузерная оболочка
public/styles.css         Дизайн-система и адаптивность
public/app.js             Основные экраны и сценарии
public/preview-store.js   Только для автономного HTML-превью
public/shursh-preview.html Самодостаточная копия демоверсии
start-windows.bat         Запуск для Windows
start.sh                  Запуск для macOS/Linux
PRODUCT.md               Концепция и границы
DESIGN.md                Дизайн-система
ARCHITECTURE.md          Архитектура, схема БД и права
TEST_REPORT.md           Отчёт о проверках
```

## Что остаётся перед публичным запуском

Нужны HTTPS и домен, подтверждение email или полноценные passwordless-ссылки с доставкой по почте, восстановление гостевого доступа, постоянный rate limiting, защита от спама и мониторинг, PostgreSQL/Supabase RLS при переходе на соответствующий стек, резервное копирование и продакшен-тесты. SQLite и встроенный сервер Python выбраны сознательно ради воспроизводимого локального MVP без ключей и инфраструктуры.

## Облачный MVP (ветка feat/supabase-mvp)

`app.py` — Flask WSGI для Vercel, `cloud/` — адаптер PostgreSQL и Supabase Auth.
Облачный режим использует те же API и дизайн, но работает с постоянной БД; демовход и
автономный симулятор в этом режиме отключены. SQLite-сервер остаётся только для
локальной разработки и регрессионных тестов.

1. Применить миграции из `supabase/migrations/` к отдельному проекту Supabase.
   Не повторять уже зарегистрированные миграции.
2. В серверном окружении настроить `SHURSH_DATABASE_URL` (PostgreSQL pooler,
   SSL required, роль с возможностью SET ROLE shursh_backend), `SUPABASE_URL`,
   `SUPABASE_PUBLISHABLE_KEY` и независимый `SHURSH_RATE_SECRET`. Не помещать
   пароль базы или токены в GitHub, браузерный bundle или публичные логи.
3. Настроить Auth: подтверждение email и разрешённые redirect URLs; настроить
   SMTP для регистрации пользователей вне команды. Сессия приложения живёт 24 часа,
   выход удаляет её на сервере. Немедленная синхронизация отзыва сессий Supabase
   требует отдельной реализации; удаление аккаунта удаляет сессии каскадно.
4. `pip install -r requirements.txt`, затем `python app.py` для локального smoke test.
   Cookie в облачном режиме Secure; браузерный тест нужен по HTTPS.
5. Для будущего Vercel Preview использовать корень репозитория, Flask,
   `app.py`, без прежней команды копирования статического демо. Не менять
   production-настройки до разрешения и зелёных проверок.

CI поднимает одноразовый PostgreSQL 17, применяет обе миграции, выполняет
`tests/test_cloud.py` с реальной СУБД. Внешний Auth transport в CI подменяется
контролируемым ответом провайдера; реальная отправка почты и авторизация
проверяются отдельно в staging. Тесты специально отказываются работать с
удалённой БД. Вложения хранятся в PostgreSQL под лимитами 12 МБ на пользователя
и 100 МБ на проект, доступны только в контексте открытого списка или владельца.
До публичного релиза нужны политика хранения, очистка rate-limit записей,
внешний тест email, изолированный DB login вместо общего postgres,
проверка Preview и тестирование браузером. Не подключать платные ресурсы.

### Аудит облачного API

Проверены прямые SPA-маршруты приглашений, брони, желаний и участников. Тесты охватывают ротацию и истечение сессии, ошибочные ссылки и отклонение некорректного JSON-содержимого. `SHURSH_RATE_SECRET` обязателен; пароль базы не используется как запасной секрет. Ссылки гостевого доступа являются bearer-capabilities: перед релизом необходимо проверить настройки логов платформы, исключить запись токенов и определить механизм отзыва/перевыпуска ссылок. Зелёный CI не подтверждает живой Supabase Auth, SMTP или браузерный E2E.

## Browser E2E (CI)

The `browser-e2e` job starts the **real Flask WSGI application** against an **ephemeral PostgreSQL 17 service** and uses Playwright Chromium with multiple isolated browser contexts (desktop and mobile). It covers the register confirmation UI (mock provider), sign-in, wishlist creation, wishlist sharing and guest reservation, cancellation, owner/other-user data isolation, private lists, invitation joins, participant wishes, Secret Santa draws, and private reveals. External Supabase Auth transport is mocked; this does **not** prove live Supabase registration, email delivery, or login in the hosted Preview. The hosted protected Preview is checked separately via Vercel smoke tests. The job uses no hosted secrets, screenshots or auth-state artifacts.

### Supabase confirmation emails (Preview)

Configure `SHURSH_AUTH_REDIRECT_URL` only on the isolated Vercel Preview project. Set it to the trusted stable Preview origin, with a trailing slash. Add the **exact same URL** under Supabase **Authentication → URL Configuration → Redirect URLs**; otherwise Supabase may fall back to an unrelated Site URL (often localhost). Do not add wildcard redirects broader than the isolated Preview project. The app intentionally discards provider access/refresh tokens in the URL fragment and asks the user to sign in via the password flow, which establishes the application's HttpOnly session. Confirmation-email delivery and actual provider verification still require a real inbox and are not covered by the mocked CI tests.


## Public beta release gates (2026-11-18)

Do not merge or deploy to Production until the owner separately approves.
The protected Preview is not a public launch. CI mocks the Supabase Auth
transport and cannot prove SMTP delivery.

### Supabase Auth: project Shursh

- Authentication > Providers > Email: leave email confirmation REQUIRED.
- Authentication > URL Configuration: set Site URL to
  https://shursh.vercel.app/ and allow the exact redirect URLs
  https://shursh.vercel.app/ and
  https://shursh-preview-git-feat-supabase-mvp-21trews-projects.vercel.app/
  (for continued staging). Never use broad wildcards.
- Authentication > SMTP Settings: enable Custom SMTP after selecting a
  provider. Set host, port, username and password/API credential using
  that provider's account (NOT repository secrets); sender must be a
  verified domain address. Configure SPF/DKIM and validate sending quotas.
- Authentication > Email Templates > Confirm signup: retain
  the Supabase ConfirmationURL template variable for verification links.
- Authentication > Rate Limits: verify email quota before inviting users.
- Register using a NEW EXTERNAL inbox, confirm email delivery (including
  spam folder), follow the link and log in with a password. Do not send
  tokens, session cookies, SMTP credentials or email contents to logs.

Docs: https://supabase.com/docs/guides/auth/auth-smtp
https://supabase.com/docs/guides/auth/redirect-urls
https://supabase.com/docs/guides/auth/auth-email-templates

### Vercel project: shursh (production, currently old main)

- Configure Flask (app.py), not the old static/demo production target.
- Production env variable NAMES: SHURSH_DATABASE_URL, SUPABASE_URL,
  SUPABASE_PUBLISHABLE_KEY, SHURSH_RATE_SECRET,
  SHURSH_AUTH_REDIRECT_URL = https://shursh.vercel.app/
- Set credentials in Vercel secrets only. Check database role privileges
  and plan a dedicated least-privilege login. Do not expose values.
- Check runtime logs for capability URLs or sensitive request data;
  establish backup/rollback plan before public invitations.
- Only after owner approval, deploy the reviewed commit to Production
  and validate the public origin without Vercel SSO.

### Live user acceptance checklist

1. Fresh external user registers; email arrives and confirmation returns
   to the public origin; confirmed user signs in.
2. User creates/edits wishlist and wishes; data survives reload.
3. Guest opens public link in incognito, reserves a gift and saves
   cancellation link. Owner cannot see booking details; guest cancels.
4. Organizer creates Secret Santa, invites at least two guests, records
   wishes, sets restrictions and draws. Separate guest contexts reveal
   only their own assignments.
5. Repeat critical paths on mobile; verify sign-out, private lists,
   invalid links and meaningful user-facing errors.

Stop public onboarding if confirmation fails, cross-user access is
possible or secrets appear in logs. Deferred: password recovery,
lost capability-link recovery, reminders, retention/backup policy.
