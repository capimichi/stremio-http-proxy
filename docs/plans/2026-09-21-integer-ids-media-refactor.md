# Piano di Refactoring: ID Numerici Incrementali e Riferimenti Esterni per Media & MediaItem

## 🎯 Obiettivo del Refactoring
Ristrutturare il database e il modello dati di `stremio-http-proxy` per:
1. Utilizzare **chiavi primarie numeriche auto-incrementali** (`id: int`) per le tabelle `media` e `media_items`.
2. Aggiungere riferimenti esterni espliciti (`imdb_id`, `tmdb_id`) sulla tabella `media`.
3. Mantenere su `media_items`:
   - `id`: Intero incrementale (`PK`)
   - `media_id`: Chiave esterna intera verso `media.id` (`FK`)
   - `season`: Intero (nullable per i film)
   - `episode`: Intero (nullable per i film)
   - `title`: Titolo dell'episodio o opera
   - `UniqueConstraint("media_id", "season", "episode")`
4. Aggiornare le chiavi esterne in `cache_entries` e `playback_history` (`media_item_id: int | None`).
5. Modificare direttamente le migration Alembic esistenti (tabula rasa del database, senza legacy fallback).

---

## 🗺️ Mappa di Tutti i File Interessati e Punti di Modifica

### 1. Entità SQLAlchemy (`stremio_http_proxy/entity/`)
- [`stremio_http_proxy/entity/media.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/entity/media.py)
  - `id`: da `String(128)` a `Integer, primary_key=True, autoincrement=True`
  - Aggiunti campi: `imdb_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)`, `tmdb_id: Mapped[str | None] = mapped_column(String(64), index=True)`
- [`stremio_http_proxy/entity/media_item.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/entity/media_item.py)
  - `id`: da `String(128)` a `Integer, primary_key=True, autoincrement=True`
  - `media_id`: da `String(128)` a `Integer, ForeignKey("media.id", ondelete="CASCADE")`
- [`stremio_http_proxy/entity/cache_entry.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/entity/cache_entry.py)
  - `media_item_id`: da `String(128)` a `Integer, ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True`
- [`stremio_http_proxy/entity/playback_history.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/entity/playback_history.py)
  - `media_item_id`: da `String(128)` a `Integer, ForeignKey("media_items.id", ondelete="CASCADE"), nullable=True`

---

### 2. Modelli Pydantic / DTO (`stremio_http_proxy/model/`)
- [`stremio_http_proxy/model/cache_entry.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/model/cache_entry.py)
  - `media_item_id: int | None = None`
  - `content_id: str | None = None` (usato per il payload Stremio `tt...:1:12`)
- [`stremio_http_proxy/model/download_job.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/model/download_job.py)
  - `media_item_id: int | None = None`
  - `content_id: str | None = None`

---

### 3. Migrazioni Alembic (`alembic/versions/`)
- [`alembic/versions/001_create_media_table.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/alembic/versions/001_create_media_table.py)
  - `id`: `sa.Integer(), primary_key=True, autoincrement=True`
  - `imdb_id`: `sa.String(64), nullable=True, unique=True, index=True`
  - `tmdb_id`: `sa.String(64), nullable=True, index=True`
- [`alembic/versions/002_create_media_items_table.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/alembic/versions/002_create_media_items_table.py)
  - `id`: `sa.Integer(), primary_key=True, autoincrement=True`
  - `media_id`: `sa.Integer(), sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False`
- [`alembic/versions/003_create_cache_entries_table.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/alembic/versions/003_create_cache_entries_table.py)
  - `media_item_id`: `sa.Integer(), sa.ForeignKey("media_items.id", ondelete="SET NULL"), nullable=True`
- [`alembic/versions/004_create_playback_history_table.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/alembic/versions/004_create_playback_history_table.py)
  - `media_item_id`: `sa.Integer(), sa.ForeignKey("media_items.id", ondelete="CASCADE"), nullable=True`

---

### 4. Repository (`stremio_http_proxy/repository/`)
- [`stremio_http_proxy/repository/media_repository.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/repository/media_repository.py)
  - `get_media(self, media_id: int) -> Media | None`
  - `get_by_imdb_id(self, imdb_id: str) -> Media | None`
  - `get_by_tmdb_id(self, tmdb_id: str) -> Media | None`
  - `upsert_media(self, imdb_id: str | None, media_type: str, title: str, tmdb_id: str | None = None, ...)`: cerca per `imdb_id` (o `tmdb_id`), crea con ID incrementale se non esiste o aggiorna.
  - `delete_media(self, media_id: int) -> bool`
- [`stremio_http_proxy/repository/media_item_repository.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/repository/media_item_repository.py)
  - `get_media_item(self, item_id: int) -> MediaItem | None`
  - `get_by_media_season_episode(self, media_id: int, season: int | None, episode: int | None) -> MediaItem | None`
  - `get_by_content_id(self, content_id: str, content_type: str | None = None) -> MediaItem | None`: risolve tramite `media_repository.get_by_imdb_id(imdb_id)` ➔ `MediaItem(media_id, season, episode)`
  - `get_items_for_media(self, media_id: int) -> list[MediaItem]`
  - `upsert_media_item(self, media_id: int, season: int | None, episode: int | None, title: str | None = None) -> MediaItem`
- [`stremio_http_proxy/repository/playback_history_repository.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/repository/playback_history_repository.py)
  - `media_item_id`: tipo `int | None`

---

### 5. Service & Manager Layer
- [`stremio_http_proxy/service/media_metadata_service.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/service/media_metadata_service.py)
  - `ensure_media_and_item(content_id: str, ...)`:
    - Scompone `content_id` in `imdb_id = "tt3749900"`, `season = 1`, `episode = 13`.
    - Esegue `media = media_repo.upsert_media(imdb_id=imdb_id, ...)` (restituisce `Media` con `id: int`).
    - Esegue `item = media_item_repo.upsert_media_item(media_id=media.id, season=season, episode=episode, ...)` (restituisce `MediaItem` con `id: int`).
    - Ritorna `(media, item)`.
- [`stremio_http_proxy/manager/cache_manager.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/manager/cache_manager.py)
  - `count_ready_for_item(self, media_item_id: int) -> int`
  - `count_active_or_ready_for_item(self, media_item_id: int) -> int`
  - `_to_job(record)`: passa `media_item_id = record.media_item_id` (`int`) e popola `content_id` se disponibile.
  - `_to_model(record)`: mappa `media_item_id: int | None`.
- [`stremio_http_proxy/service/download_queue_service.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/service/download_queue_service.py)
  - `media_item_id: int | None`
  - Chiama `media_metadata_service.ensure_media_and_item(...)` per ottenere l'ID numerico `media_item.id`.
- [`stremio_http_proxy/service/hub_service.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/service/hub_service.py)
  - Query e join aggiornati per usare `media.id` intero e `media_items.media_id` intero.
  - Ricerca `MediaItem` tramite ID numerico o `(media_id, season, episode)`.
- [`stremio_http_proxy/service/dashboard_service.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/service/dashboard_service.py)
  - Visualizzazione metadati e mapping arricchito dai record `Media` e `MediaItem`.
- [`stremio_http_proxy/service/next_episode_prefetch_service.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/service/next_episode_prefetch_service.py)
  - Verifica stato attivo/pronto tramite lookup di `MediaItem` per `content_id` ("tt3749900:1:13").
- [`stremio_http_proxy/service/download_worker_service.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/service/download_worker_service.py)
  - Su fallback (`on_download_failed`), recupera `content_id` ("tt3749900:1:13") associato al job/media_item.

---

### 6. Controller & Web API
- [`stremio_http_proxy/controller/playback_controller.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/controller/playback_controller.py)
  - Registrazione riproduzione con `media_item_id: int`.
- [`stremio_http_proxy/controller/hub_controller.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/controller/hub_controller.py)
  - API endpoint recenti, libreria e streams.
- [`stremio_http_proxy/controller/browser_controller.py`](file:///Users/michele/PycharmProjects/stremio-http-proxy/stremio_http_proxy/controller/browser_controller.py)
  - Gestione cache stagione/episodio con identificazione media.

---

### 7. Suite di Test Unitari e di Integrazione
- `tests/test_media_repository.py`
- `tests/test_hub_service.py`
- `tests/test_dashboard_service.py`
- `tests/test_cache_manager.py`
- `tests/test_cache_service.py`
- `tests/test_next_episode_prefetch_service.py`
- `tests/test_download_worker_service.py`
- `tests/test_playback_controller.py`
- `tests/test_default_container.py`

---

## 📋 Piano di Esecuzione Task per Task

1. **Task 1 - Schema Database & Entità**:
   - Aggiornamento di `entity/media.py`, `entity/media_item.py`, `entity/cache_entry.py`, `entity/playback_history.py`.
   - Aggiornamento delle 4 migrazioni in `alembic/versions/001...` a `004...`.
2. **Task 2 - Repository Layer**:
   - Aggiornamento `MediaRepository` (ricerca per `imdb_id`/`tmdb_id`, ID autoincrement).
   - Aggiornamento `MediaItemRepository` (lookup con `media_id` intero e `(media_id, season, episode)`).
   - Aggiornamento `PlaybackHistoryRepository`.
3. **Task 3 - Metadata & Prefetch Services**:
   - Aggiornamento `MediaMetadataService.ensure_media_and_item()`.
   - Aggiornamento `DownloadQueueService` e `NextEpisodePrefetchService`.
4. **Task 4 - Cache Manager & Hub Service**:
   - Aggiornamento `CacheManager` e modelli `CacheEntryModel`, `DownloadJob`.
   - Aggiornamento `HubService` e `DashboardService`.
5. **Task 5 - Test Suite & Validazione**:
   - Aggiornamento di tutti i mock e fixture dei test.
   - Esecuzione `pytest` fino a 100% test passing.

---

## ✅ Stato del Refactoring: COMPLETATO

Tutti i task e tutti i test (158/158) sono stati completati con successo:
- Schema DB & Alembic (001 - 004) allineati con chiavi primarie e foreign keys intere.
- Entity e Repository (`Media`, `MediaItem`, `CacheEntry`, `PlaybackHistory`) aggiornati.
- Servizi e Controller (`MediaMetadataService`, `CacheManager`, `HubService`, `DashboardService`, `DownloadQueueService`, `PlaybackController`, `BrowserController`) allineati.
- Tutti i test unitari e di integrazione passano al 100%.
