# Design Doc: Ottimizzazione Media 'compatible' e Ripristino Seek Cache

**Data**: 2026-10-18  
**Stato**: Approvato  
**Ambito**: `stremio-http-proxy` (Celery Tasks, Servizi di Streaming, Configurazione Contenitore)

---

## 1. Obiettivo e Contesto

Gli stream video salvati nella cache locale e serviti a Stremio presentavano l'impossibilità di avanzare o retrocedere velocemente (seek/fast-forward). 
Le cause individuate erano due:
1. **Assenza o collocazione a fine file (EOF) della tabella `Cues` nei file MKV**: i file scaricati da rete torrent hanno spesso l'indice di seek collocato alla fine o del tutto assente. La precedente modalità di ottimizzazione saltava qualsiasi file già in formato `.mkv`, lasciandolo non indicizzato per lo streaming HTTP.
2. **Flag `notWebReady: true` inviato a Stremio**: `StreamRewriteService` marcava come non pronte per il web tutte le voci MKV in cache, portando i client Stremio a limitare o bloccare la gestione del seek temporale via HTTP range requests.

L'obiettivo è introdurre la nuova modalità di ottimizzazione **`compatible`** che uniforma qualsiasi file scaricato in un contenitore MKV universale con indici `Cues` a inizio file (`-cues_to_front true`), preservando il 100% dei flussi e delle tracce senza perdita di qualità, e abilitando il seek nei client Stremio.

---

## 2. Decisioni Architetturali

1. **Nuovo Target `compatible`**:
   - `OPTIMIZE_MEDIA_TARGET` supporterà:
     - `compatible` (valore predefinito): remux in MKV con indici all'inizio, preservando tutte le tracce.
     - `web_ready_mp4`: transcodifica/remux completo per browser HTML5 (H.264/AAC).
     - `disabled` / `none` / `false`: nessuna ottimizzazione, marcatura immediata del file grezzo come `ready`.
   - Il vecchio valore `mkv` viene eliminato senza retrocompatibilità.
2. **Iniezione Dipendenze e Configurazione**:
   - `OPTIMIZE_MEDIA_TARGET` viene letto da variabile d'ambiente esclusivamente in `stremio_http_proxy/container/default_container.py`.
   - Nessun file o classe di configurazione esterna, rispettando le linee guida del progetto (`AGENTS.md`).
3. **Preservazione Integrale di Tracce e Stream**:
   - L'operazione di remux utilizza sempre `-map 0` per copiare ogni flusso presente nel file sorgente (tutti i flussi video, tracce audio multilingua, tracce di sottotitoli e capitoli).
   - Non viene scartato alcun flusso; se uno stream non è compatibile col muxer Matroska, viene convertito tramite fallback mirato.

---

## 3. Dettaglio Componenti

### 3.1 `OptimizeMediaTask` (`stremio_http_proxy/task/optimize_media_task.py`)
- Sostituzione di `_run_legacy_mkv_optimization()` con `_run_compatible_optimization(cache_key, media_path, orig_size)`:
  1. **Fase 1: Fast Remux (Stream Copy)**:
     ```bash
     ffmpeg -y -i <src> -map 0 -c copy -cues_to_front true -f matroska <dest.tmp.mkv>
     ```
     - Durata: pochi secondi (CPU ~0%, I/O sequenziale a 50x-100x).
     - Sposta la tabella `Cues` all'offset `0` per consentire seek immediato.
  2. **Fase 2: Fallback Audio/Sottotitoli**:
     Se il remux diretto fallisce (es. codec audio o sottotitoli non supportati nativamente da MKV):
     ```bash
     ffmpeg -y -i <src> -map 0 -c:v copy -c:a aac -c:s copy -cues_to_front true -f matroska <dest.tmp.mkv>
     ```
  3. **Fase 3: Fallback Video Completo**:
     Se anche il video presenta codec incompatibili (es. vecchi formati AVI/DivX obsoleti):
     ```bash
     ffmpeg -y -i <src> -map 0 -c:v libx264 -preset ultrafast -crf 22 -c:a aac -c:s copy -cues_to_front true -f matroska <dest.tmp.mkv>
     ```
  4. **Finalizzazione Atomica**:
     - `temp_mkv_path.replace(media_path)`
     - Assegnazione permessi `0o666`
     - Aggiornamento `size_bytes` sul database tramite `self.cache_manager.mark_ready(cache_key, new_size)`.
     - In caso di errore irreversibile in tutte le fasi di fallback, il file originale viene conservato e marcato `ready` per non interrompere il servizio.

### 3.2 `StreamRewriteService` (`stremio_http_proxy/service/stream_rewrite_service.py`)
- Aggiornamento della logica `_is_web_ready()`:
  - Per target `compatible`: se la voce in cache è presente ed è in stato `READY`, restituisce `True`.
  - Nei payload degli stream riscritti e nei flussi sintetici iniettati per la cache locale (`[Cache Locale]`):
    - `behaviorHints: {"notWebReady": False}` quando il file in cache è pronto.
    - `behaviorHints: {"notWebReady": True}` solo se il file non è in cache o è ancora in download/elaborazione.

### 3.3 Container e Dependency Injection (`stremio_http_proxy/container/default_container.py`)
- Lettura di `OPTIMIZE_MEDIA_TARGET = os.getenv("OPTIMIZE_MEDIA_TARGET", "compatible")`.
- Binding dei costruttori di `OptimizeMediaTask` e `StreamRewriteService` con il nuovo parametro.

---

## 4. Gestione Errori e Casi Limite

| Scenario | Gestione |
|---|---|
| File torrent già MKV ma senza Cues | Viene processato dal Fast Remux (`-c copy -cues_to_front true`) e dotato di indice all'inizio |
| File contenente tracce audio multiple o sottotitoli complessi | `-map 0` garantisce il mantenimento integrale di tutte le tracce |
| File con permessi restrittivi o concorrenza I/O | Sostituzione atomica del file (`Path.replace`) con ripristino permessi di lettura/scrittura |
| FFmpeg non disponibile o errore irreversibile | Log dettagliato dell'errore, file sorgente preservato e marcato `ready` senza bloccare la riproduzione |

---

## 5. Piano di Collaudo e Verifica

1. **Test Unitari**:
   - Test del comando generato da `OptimizeMediaTask` in modalità `compatible`.
   - Test del comportamento di fallback (copy -> audio transcode -> full transcode).
   - Test di `StreamRewriteService._is_web_ready` e generazione `behaviorHints` per elementi `READY`.
2. **Test di Integrazione**:
   - Esecuzione remux su campioni MKV e verifica binaria dello spostamento dell'EBML element `Cues` (`0x1C53BB6B`) nei primi byte del file.
   - Verifica delle risposte HTTP range (`HTTP 206 Partial Content`) da `CacheController`.
