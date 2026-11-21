# Шурш! UI-kit v1

## Назначение и границы

Единый визуальный язык для текущего Flask + vanilla JavaScript приложения
Без внедрения React, UI-библиотеки, CSS-in-JS или нового runtime-запроса
Примитивы уже существуют в `public/styles.css` и JS-генераторах `public/app.js`,
`public/social-ui.js` и `public/santa-ui.js`. Этот документ закрепляет контракт
Порядок: сохранить visual identity → общие токены → компоненты → состояния → регрессии

Источник стиля: `DESIGN.md`. Фирменное направление: playful editorial,
воздух, авторские SVG, кнопки-пилюли, эмодзи только для аватаров
Запрещено стирать характер страницы под видом унификации
Текстовый стандарт: без завершающей точки и без длинного тире в пользовательском UI
Пользовательские тексты и адреса не изменяем

## Токены

Все токены находятся внутри **существующего** `public/styles.css`, не в импортируемом CSS
Это сохраняет одну CSS-загрузку и исключает дополнительный запрос при навигации

| Категория | CSS variable | Значение / назначение |
|---|---|---|
| Фон | `--paper` | `#f9f7ef` |
| Светлая поверхность | `--paper2` | `#fffdf7` |
| Поверхность карточки | `--surface-card` | `#fffdf8` |
| Основной текст | `--ink` | `#27272b` |
| Вторичный текст | `--muted` | `#797675` |
| Границы | `--border` | `#e9e5da` |
| Акценты | `--peach`, `--lilac`, `--mint`, `--yellow` | Цветовая палитра DESIGN.md |
| Вторичный акцент | `--orange` | `#f4a465` |
| Радиус поля | `--radius-control` | `13px` |
| Радиус панели | `--radius-panel` | `24px` |
| Радиус модалки | `--radius-modal` | `27px` |
| Радиус пилюли | `--radius-pill` | `100px` |
| Отступ панели | `--space-panel` | `28px` на desktop, responsive overrides сохраняются |
| Focus outline | `--focus-color`, `--focus-width`, `--focus-offset` | `#7760b9`, `3px`, `4px` |
| Целевая зона касания | `--touch-target` | `44px` (допуск для очень плотных контролов анализируется отдельно) |
| Поле | `--control-height` | `48px` |
| Основная кнопка | `--button-height` | `49px` |
| Микроанимации | `--duration-interactive` | `.19s` |
| Тень hover кнопки | `--shadow-button-hover` | `0 5px 0 rgba(42,42,42,.12)` |
| Типографика | `--heading`, `--body` | Unbounded + Onest с системными fallback |

Семантические токены не вводят новых визуальных значений, только ссылки на уже принятые
В остальных декларациях остаются исторические значения: переносить их нужно по мере
тестирования конкретного компонента, а не массовой заменой HEX или px

## Контракт компонентов

| Primitive | CSS / JS | Варианты | Состояния и поведение |
|---|---|---|---|
| Button | `.btn` | `.btn-dark`, `.btn-peach`, `.btn-lilac`, `.btn-soft`, `.btn-ghost`, `.btn-danger` | hover, active, disabled, focus-visible; события без полной перерисовки |
| Button sizing | `.btn-small`, `.btn-square` | compact, icon | Проверять область касания на мобильных, не уменьшать текст до нечитаемого |
| Icon action | `.header-bell`, `.text-link` | иконка, текстовая ссылка | SVG, доступный label, без декоративной рамки колокольчика |
| Tag | `.chip` | `.chip-peach`, `.chip-lilac`, `.chip-green` | Не использовать цвета как единственный индикатор статуса |
| Panel | `.panel` | стандартная поверхность | Единый фон/радиус/граница; вложенность и отступы адаптируются |
| Card | `.list-card`, `.wish-card`, `.santa-list-card` | вишлист, желание, игра | Специализированная композиция и artwork остаются самостоятельными |
| Input | `.field`, `.input`, `selectField()` | input, select, textarea | label/required/error/focus/disabled, нативный select на touch |
| Dialog | `modal()`, `.modal`, `.modal-backdrop` | стандартная, длинная форма | desktop центр; mobile bottom sheet; scrollable body, safe area, Escape |
| Navigation | `.nav`, `[data-nav]` | primary, active | активная вкладка с «фломастером», DOM-cache без перерендера shell |
| Chat tabs | `[data-chat-room]` | общий, личный | scroll внутри родителя, мгновенное переключение кешированного чата |
| Status | `.alert`, `.toast`, `.note` | success/error/neutral | не скрывать смысл за цветом, не блокировать навигацию |
| Loading | `.route-skeleton`, `.skeleton-*` | первая загрузка | только когда нет контента; warm navigation без skeleton |
| Empty state | `emptyState()` | текст + основное действие | одна понятная следующая операция |
| Identity | `.emoji-avatar`, `socialAvatar()` | emoji allowlist | не загружать изображения, fallback при отсутствии эмодзи |
| Artwork | `ico()`, `fallbackArt()`, SVG | декор/контент | авторские SVG; системные декоративные emoji не использовать |

Интерфейсы в Gallery демонстрируют **существующую разметку и CSS-классы**,
но это не экспортируемая библиотека компонентов и не копия бизнес-логики

## Границы адаптивности

Проверять минимально: **375, 390, 768, 1024, 1440 px**
Существующая CSS поддерживает несколько исторических media queries. Целевая схема для
**новых** правил: small mobile до `420px`, mobile/tablet до `760px`,
intermediate до `1100px`, desktop выше. Не объединять старые breakpoint
без полноценных визуальных сравнений: есть зависимости композиции и скролла

- Модалки на мобильных появляются от нижнего края без боковых полей
- Большие формы прокручиваются внутри; кнопки не выпадают за viewport
- Длинные чаты и слайдеры скроллятся внутри своих контейнеров
- Элементы остаются пригодными для touch и клавиатуры
- Изображения не должны подменяться цветными системными глифами Safari
- `prefers-reduced-motion: reduce` отключает несущественное движение

## UX и производительность — неизменяемый контракт

- `nav()`, `ownerTabViews` и stale-while-revalidate не переписывать ради UI-kit
- Разделы сохраняют DOM между переходами; базовые CSS-изменения не должны создавать
  новые сетевые зависимости или принудительные rerender
- На warm обходе 6 вкладок после предзагрузки: 0 дополнительных HTTP/API запросов,
  0 новых DOM-элементов, если данные не изменились
- Публичные bearer-ссылки и приватные данные никогда не помещаются в owner DOM-cache
- На ошибки API показывается существующий контент либо локальное состояние ошибки
- Результаты браузерных проверок на CI с локальной тестовой PostgreSQL
  не приравнивать к замерам авторизованного Production или iPhone Safari

## Как открыть и проверить

1. Открыть `tools/ui-gallery.html` локально в браузере (file://), без сборки и сервера
2. Галерея использует `../public/styles.css`, не обращается к API и не включается в Flask
3. Проверить кнопки, checkbox, select, чаты, Escape и мобильную модалку
4. Playwright запускает проверку на пяти ширинах и сохраняет скриншоты как CI artifact
5. Генерируемый реестр `docs/UI_RULE_REGISTRY.md` обновить командой
   `python tools/ui_audit.py` после каждого изменения CSS

## Следующие этапы без массовой переписи

1. В текущем PR: закрепить токены, реестр, локальную Gallery, browser UI contracts
2. После визуального review: убрать одинаковые base overrides у `.header-bell`,
   `.modal`, `.game-chat-tabs`, при сохранении computed styles
3. После отдельного согласования: унифицировать редкие формы и повторяющиеся карточки
   без переписывания route renderers и без CSS-фреймворка
4. Сохранить документацию в актуальном состоянии и не допускать
   новых неконтролируемых override (CI registry check)

Production deploy требует отдельной явной команды пользователя


## CSS consolidation gate (PR #4)

The audit identified 54 same-selector/same-context value differences.
This pass removed 55 historically shadowed declarations from 54 conflict groups,
then removed empty rules. 2705 final declaration winners retain the exact
pre-change values and importance per at-rule context and selector, independently
checked by `tools/css_effective_check.py` and its anchored SHA-256 reference.

The visual gate samples accepted flat interiors of real buttons, both alternating Santa card variants and fields
in both Chromium and WebKit across five viewports, plus radius/border assertions.
Complex imagery and text are screenshot artifacts for human review, not silently
approved new full-component goldens. Do not merge or publish Production without
explicit permission.
