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
  that provider's account (NOT repository secrets); sender must be permitted
  by the SMTP account (a confirmed mailbox is sufficient for Yandex SMTP).
  For custom domains, configure SPF/DKIM and validate sending quotas.
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


## Release candidate preflight (2026-11-18)

### Current verified state

- GitHub PR #1 is Draft, tested branch is feat/supabase-mvp
- CI covers Python 3.11/3.13, PostgreSQL integration, frontend syntax and
  Playwright Chromium, including signup confirmation UI with mocked provider,
  login, wishes, public reservations, Secret Santa invitations/draw and mobile
- Supabase project is ACTIVE_HEALTHY, all 3 migrations are registered,
  RLS is enabled on all 12 public tables
- Hosted Supabase Auth logs contain successful /signup and /token requests
  after external Yandex SMTP delivery was confirmed by a user inbox screenshot
  This does not by itself prove every step of one complete live signup journey
- shursh-preview is a separate Flask project on the feature commit; SSO enabled
- shursh.vercel.app still serves old main (28afd5f), not the cloud MVP
- The distinct Vercel project shursh has framework=null and ZERO Production
  env variable keys; the Preview project has five Preview-only keys
- Supabase security advisor warns that leaked password protection is disabled

### Production configuration gate (requires separate approval)

The following settings are **not configured** in Production yet

1. Vercel -> team 21trews-projects -> project shursh -> Settings
   Set Framework Preset to Flask and Root Directory to repository root
   Ensure the Git repo is 21Trew/shursh and the production source is the
   exact reviewed SHA, NOT an unrelated static demo
2. Environment Variables -> Production (server-side only)
   - SUPABASE_URL: the existing Shursh Supabase HTTPS project origin
   - SUPABASE_PUBLISHABLE_KEY: publishable key, never a service-role key
   - SHURSH_DATABASE_URL: TLS PostgreSQL pooler URI for a dedicated limited
     production login that can SET ROLE shursh_backend
   - SHURSH_RATE_SECRET: strong independent random secret, different from Preview
   - SHURSH_AUTH_REDIRECT_URL: https://shursh.vercel.app/
   Store values in Vercel secure environment settings, not in GitHub, logs,
   scripts or chat. Avoid reusing the privileged postgres login
3. Supabase Authentication -> URL Configuration
   - Site URL: https://shursh.vercel.app/
   - Exact redirect allowlist includes https://shursh.vercel.app/
     and the stable protected Preview origin
   - No wildcard redirect destinations
   - Confirm signup email template retains the Supabase ConfirmationURL
   - Email confirmation remains required
4. Set operational email sending quota appropriate for the first-user pilot
   Review provider restrictions and Supabase Authentication -> Rate Limits
5. Decide rollback procedure before inviting users. The old production
   deployment is a static/demo version, so switching back temporarily hides
   cloud functionality even though PostgreSQL data remains stored

### After explicitly authorized Production deployment (no automatic release)

Run the **read-only anonymous smoke** from this repository on Node.js 22+

    node tools/release-smoke.mjs

This always checks only https://shursh.vercel.app and uses **no cookies,
credentials, account creation, or modification requests**. It validates:
homepage and security headers, JS/CSS assets, no-session /api/me and
/api/dashboard with no private data, no-store policies and 404 behavior.
The tool does NOT prove that a logged-in user can register or draw names

Then perform this **separate live acceptance** in fresh browser contexts:

1. Register one fresh external inbox, receive confirmation, follow redirect
   back to https://shursh.vercel.app/ and sign in by password
2. Create and edit a wishlist and wishes, reload, verify persistent data
3. Share the guest link in incognito, reserve and cancel a gift using only
   the guest's private management URL; confirm owner privacy isolation
4. Create a Secret Santa for at least three participants and check invite,
   participant-specific private links, exclusions and recipient reveal
5. Verify mobile layout, sign-out, invalid links, access denial and error copy
6. Check Vercel runtime logs without printing capability URLs or tokens

Stop the public rollout and do not send invitations if authentication, data
isolation, critical flows or privacy checks fail. Merge or Production deploy
requires explicit owner authorization; note that merging into a Git-connected
Production branch can trigger a deployment automatically


## Автозаполнение подарка по ссылке

В форме добавления или редактирования желания поле ссылки на магазин находится
перед названием. При вставке HTTPS-ссылки приложение пытается заполнить название,
цену в рублях и фотографию. Кнопка "Заполнить по ссылке" повторяет запрос вручную
Поля остаются редактируемыми. Выбранное пользователем изображение имеет приоритет
над автоматически полученным. Фото копируется в стандартное хранилище пожеланий,
поэтому карточка не зависит от внешней картинки после сохранения

Поддерживаемые домены: ozon.ru, wildberries.ru, market.yandex.ru, bookvoed.ru,
chitai-gorod.ru, labirint.ru, detmir.ru, dns-shop.ru, mvideo.ru,
eldorado.ru, sportmaster.ru и их разрешённые поддомены

Источники: публичный HTML, Open Graph и JSON-LD Product/Offer.
Это best-effort интеграция: магазины могут не отдавать цену и фото без
авторизации, блокировать серверные запросы или отдавать региональную цену.
Сервис не обходит CAPTCHA, ограничения доступа и антибот-защиту.
При неуспешном чтении данных пользователь добавляет желание вручную.
Для официальных гарантий полноты нужны разрешённые API или партнёрские доступы

Безопасность: сервер принимает ссылки только на перечисленные HTTPS-домены,
запрещает порты и credentials в URL, проверяет публичность DNS-адресов и
подключается к проверенному IP с TLS-проверкой имени. Редиректы снова проходят
валидацию, размеры HTML и изображения ограничены, запрос доступен только
авторизованному пользователю и имеет отдельный rate limit. URL и ответ магазина
не записываются в логи. В автономной HTML-демоверсии внешняя загрузка отключена

CI содержит unit-тесты URL-проверки, DNS-защиты, разбора цены и изображений,
API-тест контроля доступа и Browser E2E автозаполнения на mock-ответе.
Реальную доступность конкретных карточек маркетплейсов нужно проверять
по пользовательским ссылкам в защищённом Preview


### Free source adapters and licensed book feeds (November 2026)

Product identifiers are recognized without network access for Ozon,
Wildberries (nmID), Yandex Market, Bookvoed, Chitai-gorod and Labirint.
This does not imply public access to seller or marketplace JSON endpoints.
For all other supported stores the existing JSON-LD/Open Graph HTML reader
remains the fallback. A store's 307 redirect loop or access challenge is not
bypassed; users can add the original link and complete their wish manually

For book-store pages that publicly include a valid ISBN, missing title or
image metadata can be supplemented from Open Library's official read-only
`/isbn/<ISBN>.json` edition API and Covers API. A checksum is required for
ISBN-10 or ISBN-13 and we only accept identifiers labelled ISBN in the
page. Open Library offers **bibliographic information only** - not a price
for Bookvoed or any other seller. Do not populate a merchant price from an
unrelated book source. Images are downloaded only from the pinned/validated
allowlist, size-capped and then stored in existing user-controlled image data

Optional partner catalogs:
- `cloud/product_sources.py` parses a compact YML/XML catalog with
  `<offer>`, `<url>`, `<name>`, `<price>`, `<currencyId>`,
  `<picture>` and optional `<isbn>`
- Installation requires **explicit, documented rights** for the use,
  caching and redistribution of the catalog, prices and pictures
- A trusted operator may install a small (at most 4 MB) approved XML file
  in the deployment artifact and set the server-side environment variable
  `SHURSH_APPROVED_BOOK_CATALOG_FILE` to its local path
- Without a file and permission this adapter is **disabled**; no partner
  URLs are requested and no credentials are used
- Large XML feeds should be filtered **offline** into a permitted subset
  rather than fetched on every wishlist import
- The source URL embedded in each offer must resolve to an allowlisted
  bookstore and a recognizable product ID; images are validated separately
- No pricing is supplied from bibliographic APIs or made up by Shursh

Live diagnostics (GitHub-hosted runner, November 19, 2026):

| Source | Title | Price | Image | Observed |
| --- | --- | --- | --- | --- |
| Ozon public page | No | No | No | Repeated 307 |
| Wildberries public page | No | No | No | Store data unavailable |
| Yandex Market public page | No | No | No | Generic landing page rejected |
| Chitai-gorod public page | No | No | No | Store data unavailable |
| Bookvoed public page | Yes | No | Yes | Partial HTML import |
| Open Library official API | Yes | No | Cover ID | Official JSON success |
| Google Books public query | No | No | No | HTTP error on runner |

Use `PYTHONPATH=. python tools/free-source-probe.py` only for a deliberate
new live test. It is not part of CI, preventing repeated network probes.
CI unit tests mock network inputs; they do not assert that blocked marketplaces
must suddenly provide unrestricted API access
