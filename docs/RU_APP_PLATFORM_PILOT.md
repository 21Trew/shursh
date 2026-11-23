# Шурш: российский Staging-пилот на Timeweb Cloud App Platform

Дата: 23 ноября 2026. Основа: Production SHA `f8360a65c33d16a10b96864fc55436f4d45945f0`.

## Цель и границы

Проверить, сможет ли российский origin с тем же Flask-кодом обслуживать Шурш стабильнее Vercel из российских домашних и мобильных сетей. Сравниваются **две разные точки входа**, а не две базы данных. Пилот использует исключительно Supabase Staging (`vwhzhbsaspbelkvnjjho`, eu-central-1).

Никаких изменений Production DNS, Supabase Auth, Production DB и merge. Никаких копий данных пользователей Production. Тестировать только на синтетических аккаунтах и подарках. Перенос основного хостинга пока не решён.

## Подготовлено в репозитории

- Корневой `Dockerfile`: Python 3.13 + существующие Flask/psycopg зависимости + фиксированная версия Gunicorn, один процесс и четыре потока, HTTP на 8080.
- `.dockerignore` и явный `COPY`: исключает Git history, .env, тесты, данные и временные загрузки из образа.
- `tools/ru_pilot_preflight.py`: перед Gunicorn проверяет точную Staging-схему Supabase, отдельную роль, Supavisor TLS, отсутствие Vercel production markers, HTTPS cookies и секрет rate-limit.
- `tests/test_ru_pilot_preflight.py`: регрессии fail-closed и запрет Production DSN/URL.
- `tools/compare-ru-hosts.mjs`: анонимные HTTP-измерения сразу двух сайтов без cookies и личных данных.

Все изменения изолированы в `feat/ru-app-platform-pilot-20261123`. Vercel Production продолжает использовать свой `vercel.json`, а не этот Dockerfile.

## Запуск в Timeweb Cloud (только после согласования расходов)

1. В панели Timeweb Cloud → **App Platform → Добавить → Dockerfile**. Подключить GitHub `21Trew/shursh` с доступом только к этому репозиторию. Выбрать **ветку `feat/ru-app-platform-pilot-20261123`** и зафиксировать проверенный SHA. Отключить автодеплой, чтобы тестовый сервер не менялся при последующих коммитах.
2. Выбрать **регион Москва** (для проверки приоритетных российских сетей), самый небольшой подходящий backend-план с достаточной памятью. Перед созданием изучить финальную цену и условия списания в панели. Не считать «от 1 ₽» ценой backend-проекта.
3. Технический HTTPS-домен выдаётся платформой автоматически; **не** привязывать `shursh.fun`. В Dockerfile задан `EXPOSE 8080`.
4. Внести переменные **только в секреты среды Timeweb**, не в GitHub, Issues или этот чат:

| Переменная | Значение/ограничение |
|---|---|
| `SHURSH_DATABASE_URL` | Действительный Staging Supavisor transaction DSN: `shursh_preview_login.vwhzhbsaspbelkvnjjho`, `aws-N-eu-central-1.pooler.supabase.com:6543/postgres`, `sslmode=require` |
| `SUPABASE_URL` | `https://vwhzhbsaspbelkvnjjho.supabase.co` |
| `SUPABASE_PUBLISHABLE_KEY` | Publishable key **из Staging** |
| `SHURSH_RATE_SECRET` | Новый случайный секрет длиной минимум 24 символа; **не** копировать Production |
| `SHURSH_AUTH_REDIRECT_URL` | Добавить **после получения технического HTTPS-домена**: `https://<technical-host>/` |
| `PORT` | `8080` (уже по умолчанию в образе) |

`SHURSH_PILOT=1`, `SHURSH_ENV=staging`, `SHURSH_HTTPS=1` и `SHURSH_EXPECTED_SUPABASE_REF=vwhzhbsaspbelkvnjjho` уже зафиксированы в образе и проверяются при запуске. Не задавать `VERCEL`, `VERCEL_ENV`, `SUPABASE_SERVICE_ROLE_KEY` и `SHURSH_ADMIN_EMAILS`.

Если секреты Staging не заданы, контейнер **не стартует**; это ожидаемый fail-closed режим. При первом создании можно не задавать `SHURSH_AUTH_REDIRECT_URL` для анонимной проверки, но регистрация будет закрыта, пока redirect не настроен.

5. После выдачи технического домена настроить **только Staging Supabase Auth** → Redirect URLs: точный `https://<technical-host>/`. Не менять Production Site URL или Production Redirect URLs. Указать `SHURSH_AUTH_REDIRECT_URL` в Timeweb и повторить Staging deploy.
6. Проверить анонимные `/`, `/app.js`, `/styles.css`, `/fonts.css`, `/api/me`, `/api/dashboard`; они должны отдавать HTTP 200. Неавторизованные API должны возвращать пустой пользовательский контекст. Проверить CSP, secure cookie при входе, вход/выход и регистрацию с тестовой почтой. Для реальной проверки БД создать **только Staging** вишлист/игру.
7. С российского подключения **без VPN** выполнить:

```bash
node tools/compare-ru-hosts.mjs https://<technical-host>
```

Скрипт делает 3 GET-запроса на каждый из 6 маршрутов каждого origin, чередуя Vercel и Timeweb, считает успешность и медианный TTFB. Никаких паролей, cookie и содержимого ответов. Повторить с домашнего интернета и хотя бы двух мобильных операторов, желательно в разные часы. Затем дополнительно проверить мобильный Safari и Android непосредственно.

## Критерий выбора

Считать пилот перспективным, если в тех же проблемных сетях он стабильно отдаёт HTML, JS, CSS и анонимный API без ошибок TCP/TLS, а время загрузки и авторизованные сценарии не хуже исходного сайта. Один успешный запрос из дата-центра или 3 запроса сами по себе не являются гарантией доступности.

Дополнительно измерить `Server-Timing` авторизованного API: более дальний маршрут Timeweb → Supabase eu-central-1 может ухудшить время ответа, даже если загрузка HTML из РФ станет надёжнее.

## Что проверено до запуска

- Supabase Staging `ACTIVE_HEALTHY`; роль `shursh_preview_login`, роль `shursh_backend` и маркер `shursh_env.environment_identity` существуют. Выполнялся только SELECT.
- Существующий код `cloud/environment.py` отклоняет Production Supabase DSN/URL при включённом Staging.
- Правила Dockerfile-сборки и выдача технического HTTPS-домена описаны Timeweb: https://timeweb.cloud/docs/apps/deploying-with-dockerfile и https://timeweb.cloud/docs/apps/how-it-works.

## Безопасный откат

До какого-либо изменения Production достаточно удалить тестовое приложение в панели Timeweb Cloud; `shursh.fun` продолжит работать на Vercel без изменений. При удалении убрать Staging redirect из allowlist. Не менять Production DNS/SSL/cookies. Если тестовые Staging-учётные данные или токены утекли — отозвать/ротировать только Staging credentials.

## Блокеры настоящего RU-деплоя

Требуется доступ к аккаунту Timeweb Cloud, согласование стоимости выбранного backend-тарифа и технический URL, который появится только после создания приложения. Автоматизированного подключённого управления Timeweb Cloud в текущем чате нет. Пока этого нет, реальный RU endpoint и его измерения не могут считаться выполненными.
