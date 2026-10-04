# Piano di Implementazione: Ottimizzazione Cache Web-Ready (MP4 / GPU / CPU)

## 🎯 Obiettivo
Evolvere il task di post-processing della cache (`OptimizeMediaTask`) affinché i file multimediali salvati in cache locale vengano resi **Web-Ready** (contenitore MP4, video H.264, audio AAC stereo, `-movflags +faststart`) in modo rapido, intelligente e configurabile via variabili d'ambiente, sfruttando l'accelerazione hardware della GPU (Intel VA-API / QuickSync) se presente, con fallback sicuro su CPU.

---

## 🏗️ Architettura e Requisiti

### 1. Controllo del livello di ottimizzazione via Environment Variables
Aggiunta delle nuove variabili d'ambiente in `stremio_http_proxy/container/default_container.py` e documentazione in `.env.example`:

* **`OPTIMIZE_MEDIA_ENABLED`** (default: `true`):
  * Se `false`: disabilita completamente qualsiasi elaborazione post-download. Il file viene marcato direttamente come `ready` nello stato originario.
* **`OPTIMIZE_MEDIA_TARGET`** (default: `web_ready_mp4`, opzioni: `web_ready_mp4`, `mkv`, `disabled`):
  * `web_ready_mp4`: converte/remuxa in MP4 web-ready (H.264 + AAC stereo + faststart).
  * `mkv`: comportamento legacy (garantisce solo che il file sia un contenitore MKV/MP4, per compatibilità base).
* **`OPTIMIZE_MEDIA_GPU_ENABLED`** (default: `true`):
  * Abilita il tentativo di utilizzo della GPU per la transcodifica video se necessaria.
* **`OPTIMIZE_MEDIA_VAAPI_DEVICE`** (default: `/dev/dri/renderD128`):
  * Percorso del device VA-API per la GPU (es. Intel QuickSync).
* **`OPTIMIZE_MEDIA_PRESET`** (default: `ultrafast` per CPU / `7` per VA-API):
  * Livello di velocità vs qualità.

---

### 2. Gestione Docker e Passthrough GPU
I server di produzione possono avere o meno una GPU Intel/AMD/NVIDIA. La configurazione deve essere opzionale e resiliente:

* **Dockerfile**:
  * Installare i driver e gli strumenti VA-API di base per Debian/Ubuntu nel container:
    ```dockerfile
    RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        intel-media-va-driver \
        va-driver-all \
        vainfo \
        && rm -rf /var/lib/apt/lists/*
    ```
* **docker-compose.yml / docker-compose.override.yml**:
  * Nel `docker-compose.yml` del repository git, la direttiva `devices:` per il worker va lasciata **commentata** (con esempio chiaro), per evitare errori di avvio (`device not found`) su ambienti di sviluppo privi di GPU Linux (come macOS o VPS cloud generiche).
  * La mappatura effettiva dei device (`/dev/dri:/dev/dri`) viene delegata al template **`docker-compose.override.yml.j2`** nel repository Ansible (`capimichi-home`), condizionata alla presenza della GPU o controllata da variabile Ansible dedicata (es. `stremio_http_proxy_gpu_devices: ["/dev/dri:/dev/dri"]`).
* **Controllo dinamico a runtime**:
  * Nel codice Python (`OptimizeMediaTask`), prima di lanciare FFmpeg via GPU:
    * Verificare che il percorso indicato in `OPTIMIZE_MEDIA_VAAPI_DEVICE` esista fisicamente (`os.path.exists`) e che il processo abbia i permessi di lettura/scrittura (`os.access(..., os.R_OK | os.W_OK)`).
    * Se il device non è accessibile o non risponde, effettuare automaticamente il fallback su CPU senza far fallire il task.

---

### 3. Logica di Ispezione Intelligente degli Stream (`ffprobe`)
Non tutti i video necessitano di ricodifica. La ricodifica video completa è l'operazione più costosa. Il task eseguirà una scansione preliminare tramite `ffprobe` (formato JSON) per decidere la strategia per ciascun flusso:

#### 🔹 Flusso Video:
* **Caso A: Già H.264 (AVC) Web-Compatible**
  * Il video ha codec `h264`, profilo standard (High, Main, Baseline) e pixel format a 8-bit (`yuv420p`).
  * **Azione**: **`-c:v copy`** (nessuna ricodifica!).
  * **Velocità**: fino a 50x–100x (limitata solo dall'I/O del disco). Qualità 100% inalterata.
* **Caso B: Non Web-Ready (HEVC/H.265, DivX/MPEG-4, VC-1, VP9, AV1, ecc.)**
  * **Azione**: Transcodifica verso H.264.
  * **Scelta encoder**:
    * Se GPU disponibile e funzionante: `-c:v h264_vaapi -low_power 1 -quality 7 -qp 28`.
    * Se GPU assente/errore: `-c:v libx264 -preset ultrafast -crf 28 -pix_fmt yuv420p`.

#### 🔹 Flussi Audio:
* I browser desktop/mobile non supportano AC3, E-AC3, DTS o TrueHD in HTML5 puro, e spesso ammutoliscono l'audio multicanale 5.1.
* **Verifica per ogni traccia audio**:
  * Se una traccia è già `aac` o `mp3` in stereo (2 canali) -> `-c:a copy`.
  * Se una traccia è `ac3`, `dts`, `flac`, o multicanale (>2 canali) -> transcodifica in **AAC Stereo** (`-c:a aac -ac 2 -b:a 128k`).
* Mantenere tutte le tracce audio essenziali mappando con `-map 0:a?` per preservare le varie lingue (es. ITA + ENG).

#### 🔹 Flussi Sottotitoli:
* I sottotitoli bitmap BluRay (PGS `hdmv_pgs_subtitle` o VobSub) **non sono supportati** dal contenitore MP4 e fanno fallire FFmpeg.
* **Azione**:
  * Scartare i sottotitoli bitmap incompatibili.
  * Includere solo sottotitoli testuali compatibili (es. `subrip` / `mov_text`) se richiesto, oppure dare priorità all'affidabilità del flusso AV principale.

#### 🔹 Struttura MP4 Web-Ready:
* Applicare sempre `-movflags +faststart` per posizionare l'indice all'inizio del file (avvio streaming immediato e seek rapido).

---

### 4. Aggiornamento del Proxy e NotWebReady
* Una volta che il file in cache è un MP4 Web-Ready:
  * In `StreamRewriteService._mark_cached_if_ready()`:
    * Se il file associato alla cache entry è pronto (`READY`) ed è in formato `.mp4` (o marcato come ottimizzato), aggiornare esplicitamente:
      ```python
      if "behaviorHints" in stream and isinstance(stream["behaviorHints"], dict):
          stream["behaviorHints"]["notWebReady"] = False
      ```
    * Garantire la coerenza sia per gli stream iniettati sinteticamente sia per quelli provenienti dall'upstream.

---

## 📋 Fasi di Implementazione e Roadmap

1. **Fase 1: Configurazione & Dependency Injection**
   - Aggiungere le variabili di configurazione in `default_container.py` e passarle al costruttore di `OptimizeMediaTask`.
   - Aggiornare `.env.example`.

2. **Fase 2: Refactoring di `OptimizeMediaTask`**
   - Implementare l'ispezione con `ffprobe` asincrono (`asyncio.create_subprocess_exec`).
   - Implementare la matrice decisionale: `copy` vs `vaapi` vs `libx264`.
   - Implementare il controllo dinamico di accessibilità del device `/dev/dri/renderD128`.
   - Gestire la sostituzione atomica del file (`temp.mp4` -> `1.media`) e l'aggiornamento dei metadati nel database.

3. **Fase 3: Integrazione Stream Web-Ready (`StreamRewriteService`)**
   - Modificare `_mark_cached_if_ready` per impostare `notWebReady: false` quando il file in cache è pronto.

4. **Fase 4: Aggiornamento Docker & Ansible**
   - Aggiungere `intel-media-va-driver` e `vainfo` nel `Dockerfile`.
   - Lasciare commentata la sezione `devices:` per `/dev/dri` in `docker-compose.yml` (come template/esempio).
   - Aggiungere la mappatura `devices:` nel template Ansible `docker-compose.override.yml.j2` (ruolo `stremio_http_proxy`).

5. **Fase 5: Testing e Validazione**
   - Unit test su `OptimizeMediaTask` con mock di `ffprobe` e `ffmpeg`.
   - Verifica su un file di test con video H.264 (copia istantanea a 50x-90x).
   - Verifica su un file con codec non web (HEVC/DivX) con transcodifica GPU e fallback CPU.
