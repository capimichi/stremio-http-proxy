# Stremio HTTP Proxy & Media Hub

Un proxy avanzato e intelligente per addon Stremio, integrato con **TorrServer** e **MediaFlow Proxy**, dotato di un motore di caching locale in background, smart prefetching degli episodi successivi e una **Web Dashboard (Media Hub)** moderna e responsive.

---

## 📑 Indice

- [Caratteristiche Principali](#-caratteristiche-principali)
- [Architettura del Sistema](#-architettura-del-sistema)
- [Web Dashboard (Media Hub)](#-web-dashboard-media-hub)
- [Variabili d'Ambiente](#-variabili-dambiente)
- [Sviluppo Locale](#-sviluppo-locale)
- [Deployment in Produzione con Ansible](#-deployment-in-produzione-con-ansible)
- [Integrazione con Stremio](#-integrazione-con-stremio)

---

## 🚀 Caratteristiche Principali

- **Proxy Addon Stremio Trasparente**: espone gli endpoint standard di Stremio (`/manifest.json`, `/catalog`, `/meta`, `/stream`, `/subtitles`) inoltrando le richieste all'addon upstream configurato.
- **Integrazione TorrServer & Stream Rewrite**:
  - Risolve automaticamente i file video corretti all'interno dei torrent multifile.
  - Registra il torrent su TorrServer e avvia il pre-buffering.
  - Riscrive gli stream verso il backend HTTP locale di TorrServer per un avvio immediato della riproduzione.
- **Supporto MediaFlow Proxy**:
  - Instrada e protegge flussi HTTP/HLS remoti che richiedono intestazioni personalizzate o autenticazione.
- **Engine di Caching Locale Asincrono**:
  - Coda di download gestita su SQLite in modalità WAL.
  - Worker separati in background per scaricare i file torrent/stream senza bloccare la riproduzione.
  - Deduplicazione e identificazione deterministica tramite infohash e indice file.
  - Servizio di file già scaricati tramite l'endpoint `/cache/{infohash}/{index}` con token firmati (HMAC-SHA256) a scadenza temporale.
  - Politica di retention automatica con limiti di dimensione massima su disco (es. 20 GB) e tempo di vita (LRU eviction).
- **Smart Prefetching dei Prossimi Episodi**:
  - Durante la visione di un episodio di una serie TV, il proxy programma automaticamente in background il prefetching e caching dell'episodio successivo per garantire una visione continuativa a zero attese.
- **Nessuna Whitelist**:
  - Accesso diretto e trasparente a tutti i flussi restituiti dagli addon e gestione rapida di play e cache con un click.

---

## 🏛 Architettura del Sistema

```text
               ┌───────────────────────┐
               │    Stremio Client     │
               └──────────┬────────────┘
                          │ (Manifest, Streams, Play)
                          ▼
            ┌─────────────────────────────┐
            │  stremio-http-proxy (API)   │◄────► TMDB API / Upstream Addon
            └──────┬───────────────┬──────┘
                   │               │
      (Torrent /   │               │ (HTTP/HLS Proxy)
      Playback)    │               │
                   ▼               ▼
            ┌─────────────┐ ┌──────────────┐
            │ TorrServer  │ │  MediaFlow   │
            └─────────────┘ └──────────────┘
                   ▲
                   │ (Background Cache Downloads)
                   │
            ┌─────────────────────────────┐
            │  stremio-http-proxy-worker  │
            └──────────────┬──────────────┘
                           │
             ┌─────────────┴─────────────┐
             ▼                           ▼
    ┌─────────────────┐         ┌─────────────────┐
    │  var/cache/     │         │ var/db/         │
    │  (Media Files)  │         │ (cache.sqlite)  │
    └─────────────────┘         └─────────────────┘
```

### Componenti:
1. **API Service (`stremio-http-proxy`)**: istanza FastAPI che gestisce il routing Stremio, il proxy verso l'addon upstream, l'autenticazione, la dashboard web e il serving dei file in cache.
2. **Worker Service (`stremio-http-proxy-worker`)**: processo asincrono (scalabile orizzontalmente con più repliche) che preleva i job dalla coda SQLite e scarica i file completi su disco locale.
3. **Database SQLite (`var/db/cache.sqlite`)**: gestisce gli ingressi in cache, lo stato dei download (queued, downloading, ready, failed), i job di prefetch e la cronologia delle riproduzioni.
4. **Volume di Storage (`var/cache/`)**: directory in cui risiedono i file multimediali scaricati pronti per la riproduzione istantanea.

---

## 🖥 Web Dashboard (Media Hub)

Accedendo con browser a `https://<tuo-dominio>/dashboard/index` (protetta da Basic Auth) è disponibile un'interfaccia completa:

1. **Control Center (`/dashboard/index`)**:
   - **Hero Card Ultima Riproduzione**: visualizza il titolo, stagione, episodio, poster e stato di caching del contenuto in riproduzione o riprodotto di recente, con tasti per aprirlo su Stremio o gestirne i flussi.
   - **Widget Storage & Sistema**: utilizzo dello spazio cache su disco rispetto al limite configurato, contatore download attivi e stato di connessione a TorrServer.
   - **Download Attivi in Corso**: tabella live che mostra i download in esecuzione con titolo dell'opera, tag stagione/episodio (es. `S01E02`), nome del file torrent, percentuale di avanzamento e velocità in KB/s o MB/s.
   - **Riprodotti di Recente**: carosello/griglia con i titoli visualizzati di recente.

2. **Libreria Titoli (`/dashboard/library`)**:
   - Catalogo delle serie TV e dei film visti o messi in cache.
   - Badge con numero di episodi pronti in cache locale e link diretto a Stremio.

3. **Esplora & Cerca (`/dashboard/browser`)**:
   - Ricerca universale basata su TMDB per qualsiasi film o serie TV.
   - **Scheda Dettaglio Serie**:
     - Selettore delle stagioni tramite menu a tendina dinamico (es. *Stagione 1 (10 episodi)*).
     - Lista ricca degli episodi contenente: miniatura 16:9 con skeleton loader, numero episodio (`E1`, `E2`), titolo dell'episodio, data di uscita e sinossi completa.
     - Indicatore in tempo reale dello stato in cache per ciascun episodio (`Pronto`, `In Download`, `In Coda`, `Non in cache`).
     - Pulsanti per caricare i flussi, avviare il caching del singolo episodio con un click, o mettere in cache l'intera stagione.

4. **Archivio Download & Cache (`/dashboard/cache-items`)**:
   - Elenco completo di tutti i file presenti in cache locale o in coda di download.
   - Mostra in evidenza il **Titolo del Media** e il relativo contrassegno **Stagione / Episodio** (con link rapido alla scheda dell'opera), oltre al nome della release torrent sottostante.
   - Filtri rapidi per stato (*Tutti i File*, *In Download / Coda*, *Pronti in Cache*, *Errori*).
   - Ricerca istantanea testuale per nome media, titolo release o infohash.
   - Possibilità di eliminare singoli file dalla cache per liberare spazio.

5. **Dettaglio Singolo Elemento Cache (`/dashboard/cache-entry/{infohash}/{index}`)**:
   - Scheda tecnica approfondita con infohash, file index, percorsi fisici, timestamp di creazione e completamento, dimensione totale e scaricata, e link diretto alla scheda del media.

---

## ⚙️ Variabili d'Ambiente

Le variabili possono essere impostate in un file `.env` o iniettate via container / Ansible:

| Variabile | Default | Descrizione |
|---|---|---|
| `UPSTREAM_BASE_URL` | *Richiesto* | URL base dell'addon Stremio originale da proxare (es. `https://torrentio.strem.fun`) |
| `PUBLIC_BASE_URL` | `http://localhost:8691` | URL pubblico raggiungibile da Stremio (es. `https://stremio-http-proxy.example.com`) |
| `CACHE_BASE_URL` | `$PUBLIC_BASE_URL` | URL base per il serving dei file in cache (può coincidere con `PUBLIC_BASE_URL` o essere un IP LAN) |
| `APP_SECRET` | *Richiesto* | Chiave segreta per la firma crittografica HMAC dei token di riproduzione della cache |
| `CACHE_TOKEN_TTL_SECONDS` | `259200` (72h) | Durata di validità dei link generati per i file in cache |
| `DASHBOARD_BASIC_AUTH_USER` | `admin` | Nome utente per l'accesso alla Dashboard Web |
| `DASHBOARD_BASIC_AUTH_PASSWORD` | - | Password per l'accesso alla Dashboard Web |
| `TMDB_API_KEY` | - | Chiave API di TheMovieDatabase (necessaria per la ricerca e le sinossi degli episodi) |
| `TORRSERVER_BASE_URL` | `http://localhost:8090` | URL pubblico/esterno di TorrServer |
| `TORRSERVER_INTERNAL_URL` | `$TORRSERVER_BASE_URL` | URL di rete interna Docker per raggiungere TorrServer (es. `http://torrserver:8090`) |
| `TORRSERVER_BASIC_AUTH_USER` | - | Utente autenticazione TorrServer (opzionale) |
| `TORRSERVER_BASIC_AUTH_PASSWORD` | - | Password autenticazione TorrServer (opzionale) |
| `MEDIAFLOW_ENABLED` | `true` | Abilita il supporto a MediaFlow Proxy per stream HLS/HTTP |
| `MEDIAFLOW_BASE_URL` | - | URL dell'istanza MediaFlow Proxy |
| `MEDIAFLOW_API_PASSWORD` | - | Password API di MediaFlow Proxy |
| `LOCAL_CACHE_DIR` | `var/cache` | Cartella in cui salvare i file scaricati |
| `SQLITE_PATH` | `var/db/cache.sqlite` | Percorso del database SQLite |
| `LOG_DIR` | `var/log` | Cartella per i file di log |
| `LOCAL_CACHE_MAX_SIZE_GB` | `20` | Dimensione massima della cache locale prima dell'eviction LRU |
| `LOCAL_CACHE_MAX_AGE_DAYS` | `7` | Giorni massimi di conservazione di un file non utilizzato |
| `DOWNLOAD_MAX_ATTEMPTS` | `3` | Tentativi massimi per il download di un flusso fallito |
| `NEXT_EPISODE_PREFETCH_ENABLED`| `true` | Abilita il prefetch automatico dell'episodio successivo |

---

## 💻 Sviluppo Locale

### 1. Prerequisiti
- Python 3.11 o 3.12
- Docker e Docker Compose (opzionale per TorrServer)

### 2. Installazione delle dipendenze
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
```

### 3. Esecuzione dei Test
Per eseguire l'intera suite di test unitari e di integrazione (oltre 140 test):
```bash
pytest
```

### 4. Avvio in Locale
Avvio del server API FastAPI:
```bash
python -m stremio_http_proxy.cli serve
```

Avvio del worker di download della cache (in un terminale separato):
```bash
python -m stremio_http_proxy.cli download-worker
```

### 5. Avvio con Docker Compose Locale
```bash
docker compose up --build
```
Per scalare il numero di download worker:
```bash
docker compose up --build -d --scale stremio-http-proxy-worker=2
```

---

## 📦 Deployment in Produzione con Ansible

Il deployment del proxy è completamente automatizzato tramite il repository **Ansible** (`capimichi-home`), all'interno del ruolo dedicato:
`roles/stremio_http_proxy/`

### Cosa fa il ruolo Ansible:
1. Crea le directory necessarie sul volume permanente del server (es. disco esterno WD):
   - `/mnt/wd/stremio_http_proxy/var/cache` (storage cache video)
   - `/mnt/wd/stremio_http_proxy/var/db` (database SQLite)
   - `/mnt/wd/stremio_http_proxy/var/log` (log di sistema)
2. Effettua il clone o il pull del repository Git dal branch `master`.
3. Compila e distribuisce i template:
   - `docker-compose.override.yml.j2`: monta i percorsi permanenti di cache e database e configura i container.
   - `.env.j2`: inietta i secret (password, API key TMDB, URL TorrServer e MediaFlow).
4. Avvia e ricrea lo stack Docker Compose tramite `community.docker.docker_compose_v2`, scalando automaticamente i worker in background in base alla variabile `stremio_http_proxy_worker_replicas`.

### Comando per il Deployment:
Dalla cartella del progetto Ansible (`capimichi-home`):

```bash
ansible-playbook playbooks/site.yml --tags stremio_http_proxy --vault-password-file ~/.vault_pass
```

L'esecuzione applicherà tutte le ultime modifiche del codice, ricompilerà le immagini Docker e riavvierà i servizi senza perdita di dati o interruzioni della cache preesistente.

---

## 📺 Integrazione con Stremio

1. **Ottenere il Link del Manifest**:
   - Apri la dashboard all'indirizzo pubblico configurato (es. `https://stremio-http-proxy.example.com/dashboard/index`).
   - Nella barra superiore, clicca sul pulsante **"Installa su Stremio"**, oppure copia direttamente l'URL del manifest:
     ```text
     https://stremio-http-proxy.example.com/manifest.json
     ```
2. **Aggiunta in Stremio**:
   - In Stremio (Desktop, Mobile o TV), vai nella sezione **Addon**.
   - Incolla l'URL nella barra di ricerca degli addon o premi il link con protocollo `stremio://` (`stremio://stremio-http-proxy.example.com/manifest.json`).
   - Clicca su **Installa**.
3. **Utilizzo**:
   - Seleziona qualsiasi serie TV o film.
   - I flussi già pronti in cache locale verranno mostrati prioritariamente con il prefisso **🔥**.
   - Gli stream avviati inizieranno istantaneamente attraverso TorrServer e, contemporaneamente, verranno messi in coda per il salvataggio in cache locale e per il prefetch degli episodi successivi.
