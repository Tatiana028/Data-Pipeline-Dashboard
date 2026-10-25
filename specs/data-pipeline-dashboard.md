# Data Pipeline Dashboard

## Objective
Портфолио-проект для поиска работы в data engineering / банковской автоматизации.
ETL-пайплайн по расписанию забирает почасовую погоду из открытого REST API Open-Meteo
для 5–10 городов, сохраняет сырые ответы и очищенные данные в PostgreSQL, считает
дневные агрегаты; FastAPI отдаёт данные, Streamlit визуализирует погоду и здоровье
пайплайна. Всё поднимается одной командой `docker compose up` без API-ключей и
регистраций — рекрутер может запустить проект сам. Акцент — на DE-паттернах: слои
raw → clean → aggregate, идемпотентный upsert, лог запусков, миграции, retry.

## Requirements
### Must have

**Источник и конфиг**
1. Источник — Open-Meteo Forecast API (`https://api.open-meteo.com/v1/forecast`), без ключа.
2. Список городов (name, country, latitude, longitude, timezone) хранится в конфиге
   `config/cities.yaml`; по умолчанию 6 городов: Moscow, Berlin, London, New York, Tokyo, Sydney.
   Добавление города = новая строка в YAML, без изменения кода.
3. Собираемые почасовые метрики: `temperature_2m`, `apparent_temperature`,
   `relative_humidity_2m`, `precipitation`, `wind_speed_10m`, `surface_pressure`, `weather_code`.
4. Настройки (DSN БД, URL API, интервал, число дней бэкфилла, таймауты) — через
   переменные окружения (`pydantic-settings`), с `.env.example` в репозитории.

**ETL (`src/etl/`)**
5. Extract: один HTTP-запрос на город (`httpx`), таймаут 10 с, до 3 попыток с
   экспоненциальной паузой (`tenacity`) на сетевые ошибки и HTTP 5xx/429.
6. Каждый успешный HTTP-ответ сохраняется в `raw_responses` как JSONB до парсинга.
7. Transform: JSON валидируется Pydantic-моделью; массивы `hourly.time[]` + метрики
   разворачиваются в строки (одна строка = город + час); время приводится к UTC.
8. В `weather_hourly` пишутся только часы `<= текущего часа UTC` (наблюдения, не прогноз).
9. Load: `INSERT ... ON CONFLICT (city_id, ts) DO UPDATE` — повторный запуск за тот же
   период не создаёт дублей и обновляет значения (Open-Meteo может уточнять данные).
10. После загрузки пересчитываются `weather_daily` для затронутых дат этого города
    одним SQL `INSERT ... SELECT ... GROUP BY ... ON CONFLICT DO UPDATE`
    (min/max/avg температуры, сумма осадков, max ветра, avg влажности, `hours_count`).
    Дата агрегата — локальная дата города (по его timezone).
11. Изоляция по городу: ошибка одного города не прерывает остальные; каждый город —
    своя транзакция для clean+daily.
12. Каждый запуск пишет строку в `etl_runs`: `started_at`, `finished_at`,
    `status` (`success` / `partial` / `failed`), `cities_ok`, `cities_failed`,
    `rows_upserted`, `error` (текст ошибок по городам).
13. Бэкфилл: при запуске, если у города нет данных в `weather_hourly`, запрос идёт
    с `past_days=30` (значение из конфига); иначе — `past_days=2` (перекрытие окна,
    чтобы закрыть пропуски после простоя).
14. Планировщик: APScheduler (`BlockingScheduler`) в отдельном сервисе `etl`;
    один запуск сразу при старте, далее каждый час в `HH:05` UTC;
    `max_instances=1`, `coalesce=True` (запуски не наслаиваются).
15. ETL можно запустить вручную одной командой: `python -m src.etl.run_once`.
16. Логирование в stdout в структурированном виде (уровень, город, число строк, длительность).

**БД**
17. PostgreSQL 16. Таблицы:
    - `cities` (id, name, country, latitude, longitude, timezone; UNIQUE(name, country)) —
      синхронизируется из YAML upsert-ом при старте ETL;
    - `raw_responses` (id, city_id FK, run_id FK, fetched_at, http_status, payload JSONB);
    - `weather_hourly` (city_id FK, ts TIMESTAMPTZ, 7 метрик, ingested_at; PK(city_id, ts));
    - `weather_daily` (city_id FK, date, temp_min, temp_max, temp_avg, precipitation_sum,
      wind_speed_max, humidity_avg, hours_count, updated_at; PK(city_id, date));
    - `etl_runs` (поля из п. 12).
    Индекс на `weather_hourly(ts)` и `etl_runs(started_at DESC)`.
18. Слой доступа — SQLAlchemy 2.x **Core** (таблицы в `src/db/tables.py`), без ORM.
19. Схема создаётся только миграциями Alembic; в compose отдельный одноразовый сервис
    `migrate` (`alembic upgrade head`), от успешного завершения которого зависят `etl` и `api`.

**API (`src/api/`)**
20. FastAPI, только чтение, ответы через Pydantic-схемы, Swagger на `/docs`:
    - `GET /health` — `{"status": "ok", "db": "ok"}`, 503 если БД недоступна;
    - `GET /cities`;
    - `GET /weather/latest` — последний час по каждому городу;
    - `GET /weather/hourly?city_id=&date_from=&date_to=&limit=&offset=`;
    - `GET /weather/daily?city_id=&date_from=&date_to=`;
    - `GET /etl/runs?limit=` — последние запуски, новые сверху.
21. По умолчанию `/weather/hourly` отдаёт последние 7 дней; `limit` по умолчанию 1000, максимум 5000.
22. Несуществующий `city_id` → 404; `date_from > date_to` или неверный формат → 422.

**Дашборд (`src/dashboard/`)**
23. Streamlit, данные берёт **только** через FastAPI (не ходит в БД напрямую); URL API из env.
24. Страница «Overview»: KPI-плитки текущей погоды по каждому городу
    (температура, ощущается как, ветер, осадки, время последнего обновления).
25. Страница «Trends»: мультивыбор городов и диапазон дат; линейный график почасовой
    температуры; график дневных min/max (диапазон) и столбцы суммы осадков.
26. Страница «Pipeline health»: таблица последних 50 запусков со статусами (цветом),
    «data freshness» (сколько минут назад последний успешный запуск; предупреждение,
    если > 90 мин), число строк в `weather_hourly`.
27. Ответы API кешируются в дашборде на 60 с (`st.cache_data(ttl=60)`).
28. Все пользовательские тексты дашборда — на английском.

**Инфраструктура**
29. `docker-compose.yml` с сервисами: `db` (postgres:16 + volume + healthcheck),
    `migrate`, `etl`, `api` (порт 8000), `dashboard` (порт 8501).
    `docker compose up --build` с чистой машины → через ≤ 2 мин дашборд показывает
    данные за ~30 дней по всем городам.
30. Один `Dockerfile` (Python 3.12-slim) для всех Python-сервисов, разные `command`.
31. Зависимости — `pyproject.toml`; линт — `ruff`.

**Тесты и CI**
32. Unit-тесты (без сети и БД): парсинг/валидация JSON на фикстурах из `tests/fixtures/`,
    разворот массивов, отсечение будущих часов, перевод в UTC, расчёт локальной даты,
    логика статуса запуска (success/partial/failed).
33. HTTP мокается `respx`: тест retry (2 ошибки 503 → успех), тест исчерпания попыток.
34. Интеграционные тесты на реальном Postgres: идемпотентность (двойной запуск →
    то же число строк, обновлённые значения), пересчёт `weather_daily`, изоляция
    по городу (1 город падает → остальные загружены, статус `partial`),
    эндпоинты API через `TestClient` (200/404/422).
35. GitHub Actions `.github/workflows/ci.yml` на push и PR: `ruff check` → миграции →
    `pytest` с Postgres в `services:`. CI зелёный.

**README (английский)**
36. Одна строка о проекте, архитектурная схема (Mermaid), список технологий,
    «Run in one command», описание слоёв данных и схемы БД, примеры запросов к API,
    скриншоты трёх страниц дашборда, раздел «Design decisions» (почему отдельный
    scheduler, почему Core, почему raw-слой, почему Postgres в тестах).

### Nice to have
- Второй источник: Open-Meteo Air Quality API (PM2.5, PM10) — показать мульти-источниковый ETL.
- Добавление города через API с геокодингом (Open-Meteo Geocoding).
- Data quality-проверки (диапазоны значений, пропуски часов) с записью в отдельную таблицу.
- Retention для `raw_responses` (удалять старше N дней).
- GIF работающего дашборда в README.
- Pre-commit хуки (ruff).

## Constraints
- Python 3.12; `httpx`, `tenacity`, `pydantic` v2, `pydantic-settings`, SQLAlchemy 2.x Core,
  `psycopg` 3, Alembic, APScheduler 3.x, FastAPI + uvicorn, Streamlit, `pandas`, `plotly`,
  `pytest`, `respx`, `ruff`.
- Никаких API-ключей и секретов; пароль БД только для локального compose, в `.env.example`.
- Структура репозитория: `src/etl/`, `src/api/`, `src/dashboard/`, `src/db/` (таблицы + подключение),
  `migrations/` (Alembic), `config/cities.yaml`, `tests/`, `docker-compose.yml`,
  `Dockerfile`, `.github/workflows/ci.yml`, `README.md`.
- Лимиты Open-Meteo (бесплатно, ~10k запросов/сутки) не превышаются: 6–10 городов × 24 ≈ 240/сутки.
- Отдельный репозиторий `~/Data-Pipeline-Dashboard`, никак не связан с `~/Transaction-Monitoring`.
- Комментарии в коде — на русском; README и тексты дашборда — на английском.

## Edge cases
- Open-Meteo недоступен / таймаут / 5xx / 429 → 3 попытки с паузой; если все неудачны —
  город в `cities_failed`, ошибка в `etl_runs.error`, остальные города грузятся.
- Все города упали → статус `failed`, процесс планировщика продолжает работать и ждёт следующего часа.
- Ответ 200, но JSON не проходит валидацию (нет поля, длины массивов не совпадают) →
  payload сохранён в `raw_responses`, в `weather_hourly` ничего не пишется, город считается failed.
- Отдельное значение метрики `null` → строка сохраняется, поле NULL (не отбрасываем час).
- Повторный запуск за тот же час → дублей нет, значения обновлены, `updated_at` обновлён.
- Неполный текущий день → `weather_daily` содержит частичный агрегат, `hours_count < 24`;
  дашборд это показывает как есть.
- ETL был выключен несколько часов → следующий запуск с `past_days=2` закрывает пропуск;
  простой > 2 дней не досасывается автоматически (см. Open questions).
- Город удалён из YAML → остаётся в `cities` и данных, но больше не собирается.
- БД ещё не готова при старте → `migrate`/`etl`/`api` ждут healthcheck `db`.
- API недоступен для дашборда → на странице сообщение «API is unavailable», без трейсбека.
- Пустая БД (до первого запуска) → эндпоинты возвращают `[]`, дашборд — «No data yet».
- Переход на летнее/зимнее время → все `ts` хранятся в UTC, локальная дата считается
  через timezone города, поэтому дубль/пропуск локального часа не ломает PK.

## Out of scope
- Аутентификация, пользователи, роли в API и дашборде.
- Запись через API (POST/PUT/DELETE), ручной запуск ETL из дашборда.
- Прогноз погоды (будущие часы) и ML-прогнозирование.
- Kafka, Airflow, dbt, облачный деплой, Kubernetes.
- Мониторинг Prometheus/Grafana, алерты в мессенджеры.
- Бэкфилл больше 30 дней / исторический archive-API.
- Нагрузочное тестирование, горизонтальное масштабирование API.

## Definition of done
- [ ] `git clone` + `docker compose up --build` на чистой машине без `.env` и ключей →
      все 5 сервисов healthy/работают, `migrate` завершился с кодом 0.
- [ ] Через ≤ 2 мин в `weather_hourly` есть данные за ~30 дней по всем городам из YAML
      (проверка: `GET /cities` и `GET /weather/hourly`).
- [ ] `GET /etl/runs` показывает стартовый запуск со статусом `success`; через час — второй.
- [ ] `python -m src.etl.run_once` дважды подряд → число строк в `weather_hourly` не меняется.
- [ ] Отключение сети у контейнера `etl` → запуск со статусом `failed`, после восстановления
      следующий запуск `success`, пропуск закрыт.
- [ ] Все 6 эндпоинтов работают, Swagger `/docs` открывается, 404/422 отдаются как описано.
- [ ] Дашборд: три страницы (Overview, Trends, Pipeline health) показывают данные;
      фильтры городов/дат работают.
- [ ] `ruff check` без ошибок; `pytest` зелёный локально и в GitHub Actions.
- [ ] README на английском: схема, запуск, API-примеры, скриншоты всех трёх страниц, Design decisions.
- [ ] Каждое требование 1–36 выполнено (проверка через `/review` против этого спека).

## Open questions / Assumptions
- **Язык спека** — русский (внутренний документ); если `specs/` будет публичным на GitHub,
  можно перевести на английский перед публикацией.
- **Города по умолчанию** — Moscow, Berlin, London, New York, Tokyo, Sydney (разные пояса
  и полушария → интереснее графики). Легко поменять в YAML.
- **Только наблюдения, без прогноза** — решено самостоятельно, чтобы не смешивать
  факт и прогноз в одной таблице.
- **Расписание `HH:05` UTC** — небольшой сдвиг после начала часа, чтобы данные за час уже были.
- **`past_days=2` для регулярных запусков** — перекрытие окна вместо отслеживания
  «последнего загруженного часа»; долгий простой (> 2 дней) не догружается автоматически.
- **Один запрос на город** (а не batch из всех координат) — ради изоляции ошибок.
- **Порты**: api 8000, dashboard 8501, db 5432 (наружу db можно не пробрасывать).
- **Графики** — Plotly (интерактивность в Streamlit).
- **Порядок работы** (стиль «маленькие шаги»): скелет + compose с db → миграции →
  extract/transform с тестами на фикстурах → load + upsert → scheduler → API → дашборд →
  CI → README. Каждый шаг — своя ветка и PR.
- Git-репозиторий ещё не инициализирован и на GitHub не создан — сделаем на первом шаге вместе.
