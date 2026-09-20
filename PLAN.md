# Piano di Sviluppo: Trasformazione in Stremio Media Hub

## 1. Obiettivo del Progetto
Evolvere il proxy da semplice monitor tecnico dei download a **Personal Media Hub & Control Center** per Stremio.

### Requisiti Chiave Utente
1. **Verifica Immediata Stato Riproduzione (0 clic)**:
   - All'apertura dell'interfaccia, vedere subito se l'episodio/film appena riprodotto in Stremio è stato intercettato, se è pronto in cache o se è in download e a che velocità.
2. **Supporto Multi-Stream per Singolo Media**:
   - Uno stesso film o episodio può avere più flussi (es. 1080p ITA, 4K HDR, HLS).
   - *Livello Macro*: stato aggregato sintetico nella card o riga dell'episodio (es. "Pronto 1080p" con contatore di altri stream).
   - *Livello Micro*: visualizzazione dettagliata espandibile di tutti i flussi associati con i singoli stati (dimensione, velocità, pronto, errore, azioni di eliminazione o prioritizzazione).
3. **Messa in Cache Batch di un'Intera Stagione / Singolo Episodio**:
   - Dalla scheda della serie (o da azione rapida), pulsante *"📥 Metti in cache tutta la Stagione X"*.
   - Integrazione con l'infrastruttura di prefetch esistente (`NextEpisodePrefetchService` / `TaskService`), accodando in background tutti gli episodi della stagione. Il worker verifica automaticamente se ogni episodio è già presente o da scaricare.
4. **Esplorazione & Discovery Avanzata (TMDB / IMDb)**:
   - Ricerca titoli, schede arricchite con trama, rating, cast, selezione stagione/episodi e flussi disponibili.
5. **Nuovo Design Dark Moderno (Plex/Jellyfin style)**:
   - UI scura moderna con locandine visive, indicatori dinamici in tempo reale, navigazione intuitiva e responsive.

---

## 2. Baseline e Salvaguardia (Rollback Plan)
- **Git Tag di sicurezza**: `working` (punta al commit `3be8ff7`).
- Tutti i 137 test unitari/integrazione passano con successo prima di iniziare.
- Se necessario tornare indietro in qualsiasi momento:
  ```bash
  git checkout working
  # oppure
  git reset --hard working
  ```

---

## 3. Architettura delle Informazioni & Pagine

```
├── 🏠 Hub (Home / Dashboard)
│    ├── 🎬 In Riproduzione / Ultimo visto (Card principale con stato cache istantaneo)
│    ├── ⚡ Widget Stato Globale (Velocità complessiva, Storage occupato/libero, TorrServer online)
│    ├── 📥 Barra Download Attivi (Avanzamento in tempo reale)
│    └── 🕒 Continua a Guardare & Cronologia Recente (Card orizzontali con badge stato cache)
│
├── 🔍 Esplora & Cerca
│    ├── Barra di ricerca unificata (Titolo o IMDb ID)
│    ├── Griglia risultati con locandine e metadati
│    └── Scheda Dettaglio (Serie / Film):
│         ├── Header con poster grande, trama, voto IMDb, anno
│         ├── Selettore Stagione + Pulsante "Metti in cache tutta la Stagione"
│         └── Lista Episodi con stato sintetico + Accordion flussi multi-stream
│
├── 📥 Download & Archivio Cache
│    ├── Monitor coda di download (in corso, in attesa, falliti con possibilità di retry)
│    └── Archivio file su disco (elenco, dimensione, tasto Pin anti-pulizia, elimina)
│
├── 📜 Cronologia Riproduzioni
│    └── Storico completo delle sessioni riprodotte tramite il proxy
│
└── ⚙️ Whitelist & Impostazioni
     └── Gestione regole automatiche e whitelist flussi
```

---

## 4. Fasi di Implementazione & Strategia dei Commit

### Fase 1: Backend Watch History & API Media Hub
- **DB**: Creazione entità e tabella `playback_history` (o estensione sessioni) per memorizzare le riproduzioni avviate (`content_type`, `content_id`, `title`, `poster`, `category`, `source_link`, `infohash`, `played_at`).
- **Hook Riproduzione**: Registrazione automatica della riproduzione in `PlaybackController.play` e `play_manifest`.
- **API Endpoint**:
  - `GET /api/hub/recent`: Ritorna gli ultimi media riprodotti arricchiti con lo stato aggregato dei rispettivi flussi in cache.
  - `GET /api/hub/media-streams/{content_id}`: Ritorna tutti i flussi e le cache entries collegate a un determinato media/episodio.
  - `POST /api/browser/cache-season`: Accoda i task di prefetch per tutti gli episodi di una stagione.
  - `POST /api/browser/cache-episode`: Accoda il prefetch per un singolo episodio.
- **Commit**: `feat(hub): add playback history tracking and hub batch caching api`

### Fase 2: Redesign Layout Base & Componenti Comuni
- Palette moderna Dark Mode (stile Jellyfin/Netflix con Tailwind CSS).
- `header.html`: Nuova topbar con badge di stato server (TorrServer status, velocità totale download, storage cache).
- `sidebar.html`: Nuova navigazione pulita con icone e indicatori di stato.
- Componenti riutilizzabili per card multimediali, barre di progresso e badge di stato stream (Verde = Pronto, Blu = In download, Giallo = In coda, Grigio = Non in cache).
- **Commit**: `feat(ui): implement modern dark theme shell, sidebar and header`

### Fase 3: Home / Media Hub
- Riorganizzazione completa di `templates/dashboard/pages/index.html` e `static/dashboard.js`:
  - Sezione prominente "Ultimo riprodotto / In riproduzione" in alto a sinistra: mostra subito locandina, episodio, stato cache, progresso download o se è pronto.
  - Monitor download in tempo reale con polling/aggiornamento automatico leggero.
  - Sezione "Continua a guardare": card orizzontali dei titoli recenti con azione rapida per aprire la scheda o avviare in Stremio.
- **Commit**: `feat(ui): implement media hub homepage with instant playback cache status`

### Fase 4: Esplora & Scheda Titolo con Multi-Stream e Cache Stagione
- Aggiornamento di `browser_detail.html`:
  - Supporto al pulsante **"📥 Metti in cache tutta la Stagione X"** con feedback visivo immediato.
  - Riorganizzazione della lista episodi:
    - Badge aggregato di stato per episodio.
    - Sezione a comparsa/accordion per ogni episodio per visualizzare tutti gli stream disponibili e il loro stato indipendente.
    - Azione "Metti in cache questo stream specifico" o "Aggiungi a whitelist".
- **Commit**: `feat(ui): implement season batch caching and multi-stream episode view`

### Fase 5: Download & Archivio Cache Manager
- Refactoring della pagina `cache_items.html` per integrarsi armoniosamente nel tema scuro:
  - Tab o filtri rapidi: Tutti, In download, Pronti, Falliti.
  - Azioni rapide per rimuovere o prioritizzare i file.
- **Commit**: `feat(ui): refresh cache items and download manager view`

### Fase 6: Test, Verifica e Documentazione Finale
- Esecuzione completa della suite di test `pytest`.
- Aggiunta di nuovi test per i nuovi endpoint e il tracciamento della history.
- Verifica del funzionamento e documentazione aggiornata.
- **Commit**: `test(hub): add tests for playback history, hub api and season caching`

---

## 5. Deployment & Procedura di Verifica
Al termine delle fasi:
1. Verifica con `pytest` che tutti i test passino senza errori.
2. Riavvio dell'applicazione (`docker compose up --build -d` o avvio locale con cli serve).
3. Test end-to-end sui due scenari principali:
   - Apertura stream da Stremio ➔ Verifica immediata dell'episodio in Home con stato download cache.
   - Apertura scheda serie ➔ Clic su "Metti in cache tutta la Stagione" ➔ Verifica dell'accodamento corretto nella coda prefetch.
4. Se tutto è conforme e soddisfacente, rilascio definitivo; in alternativa, possibilità di ripristinare il tag `working`.
