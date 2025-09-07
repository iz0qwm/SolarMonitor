# 📡 Space Weather Drone Monitor

Questo progetto raccoglie, registra e confronta parametri di **space weather** e di **qualità del segnale radio/GPS**, con particolare attenzione agli effetti sui **link di controllo/video dei droni** e sulla **posizione GPS**.

Monitoriamo e mettiamo in relazione:
- **Indice geomagnetico Kp** (tempeste geomagnetiche).
- **TEC – Total Electron Content** (stato ionosfera, impatto sul GPS).
- **Rumore radio** e **occupazione canale** sulle bande 2.4/5.8 GHz.
- **Qualità del fix GPS** (DOP, satelliti, C/N₀, alt, ecc.).

Obiettivo: **capire e documentare come le condizioni spaziali e ionosferiche influenzino GPS e link radio dei droni**, con log storici e grafici comparativi.

---

## 🧭 Diagramma di relazione (ASCII)

```text
             Disturbi Solari (flare, CME)
                         │
                         ▼
              Attività Geomagnetica (Kp)
                         │
                         ▼
              Ionosfera più variabile
                         │
                         ▼
               ↑ TEC (Total Electron Content)
                         │
        ┌────────────────┴────────────────┐
        ▼                                 ▼
  GPS degradato                     Canali ISM più
 (più iono-delay, jitter,          rumorosi/congestionati
   scintillazioni)                  (noise, busy_ratio)
        │                                 │
        ▼                                 ▼
  DOP ↑, C/N₀ ↓, fix instabile       SNR link ↓, packet loss ↑
        │                                 │
        └───────────────┬─────────────────┘
                        ▼
             Affidabilità link drone ↓
  (controllo/video meno robusti, rischio failsafe ↑)
```

---

## 📊 Parametri monitorati

| Parametro | Descrizione | Perché lo monitoriamo |
|-----------|-------------|------------------------|
| `ts_iso` | Timestamp ISO 8601 | Allineamento temporale di tutte le misure. |
| `kp` | Indice geomagnetico Kp (0–9) | Proxy dell’attività geomagnetica: eventi alti possono disturbare GPS/comunicazioni. |
| `kp_when` | Orario/slot di validità del Kp | Tracciabilità dell’intervallo ufficiale del valore Kp. |
| `gps_fix` | Stato del fix (`NO`, `2D`, `3D`) | Verifica della validità della posizione. |
| `lat`, `lon`, `alt` | Posizione stimata | Contestualizza gli effetti locali (ambiente, ostacoli). |
| `pdop`, `hdop`, `vdop` | Dilution of Precision | Qualità geometria satellitare (più basso = meglio). |
| `sv_used` | Satelliti usati | Affidabilità della soluzione. |
| `sv_tot` | Satelliti visibili | Confronto con `sv_used` (ambiente/ostacoli/filtri). |
| `cn0_mean` | C/N₀ medio dei satelliti (dB-Hz) | Qualità del segnale GPS ricevuto. |
| `mode` | Modalità (`SCAN`, ecc.) | Stato operativo del logger (es. scansione RF). |
| `freq` | Frequenza monitorata (MHz) | Canale/banda ISM (2.4 / 5.8 GHz) sotto test. |
| `noise_dbm` | Rumore medio (dBm) | Rumore di fondo che riduce margine SNR del link. |
| `busy_ratio` | % tempo canale occupato | Congestione/interferenze che impattano throughput/latency. |
| `scan_n` | Campioni nello scan | Robustezza statistica dei valori. |
| `scan_p50`, `scan_p10`, `scan_p90` | Percentili del segnale | Fotografano la distribuzione (tipico, coda bassa/alta). |
| `band` | Banda (`2.4G`, `5.8G`) | Bande tipiche droni per controllo/video. |
| `tec` | TEC (TECU) | Proxy della variabilità ionosferica che impatta il GPS. |
| `tec_source` | Fonte del TEC | Tracciabilità (ESWU/IGS/altro). |

---

## 🚀 Obiettivi del progetto

- Creare un **dataset continuo** di space weather e condizioni locali RF/GPS.
- Correlare picchi di **Kp/TEC** e **rumore/congestione RF** con degradazioni reali di **GPS** e **link drone**.
- Fornire **grafici e dashboard** utili a piloti, tecnici e ricercatori per la pianificazione e la consapevolezza del rischio.

---

## 📂 Struttura dei log

Ogni riga del CSV contiene:

```
ts_iso,kp,kp_when,
gps_fix,lat,lon,alt,pdop,hdop,vdop,sv_used,sv_tot,cn0_mean,
mode,freq,noise_dbm,busy_ratio,scan_n,scan_p50,scan_p10,scan_p90,band,
tec,tec_source
```

---

## 🔎 Interpretazione rapida (regole pratiche)

- **Kp alto (≥5)** + **TEC elevato** → aspettati **DOP↑, C/N₀↓**, fix più instabile.
- **noise_dbm più alto** (meno negativo) o **busy_ratio↑** → **SNR link↓**, bitrate ridotto, più ritrasmissioni.
- **sv_used ≪ sv_tot** con **DOP↑** → possibile mascheramento/ostacoli locali oltre agli effetti ionosferici.
- Usa **percentili (p10/p50/p90)** per capire se i problemi sono sporadici (solo coda) o sistematici (tutta la distribuzione si sposta).

---


## 🛠️ Hardware utilizzato

L’intero sistema è stato implementato su una **Raspberry Pi**, scelta per la sua compattezza ed efficienza energetica.

Sono collegati i seguenti dispositivi:

- 📍 **GPS esterno USB** → fornisce dati accurati di posizione, altitudine, DOP e qualità segnale satellitare (C/N₀).
- 📶 **Chiavetta WiFi USB** (chipset compatibile con modalità monitor) → consente di analizzare rumore di fondo, occupazione canali e distribuzione dei segnali nelle bande **2.4 GHz** e **5.8 GHz**.
- ⚡ Alimentazione stabile → necessaria per evitare undervoltage durante logging continuo.

Questa configurazione hardware permette di raccogliere in tempo reale sia i parametri GPS sia le condizioni RF locali, correlati con i dati di space weather (Kp, TEC).


### 🔌 Schema hardware & flusso dati

```text
   ┌────────────────┐      ┌──────────────────┐
   │   GPS USB      │      │  Chiavetta WiFi  │
   │  (posizione,   │      │  (scan 2.4/5.8G) │
   │  DOP, C/N₀)    │      │  noise, busy)    │
   └───────┬────────┘      └────────┬─────────┘
           │                         │
           ▼                         ▼
      ┌──────────────────────────────────────┐
      │          Raspberry Pi (logger)       │
      │  - raccoglie dati GPS + RF           │
      │  - integra Kp/TEC da API             │
      │  - scrive CSV e invia al DB          │
      └───────────────────┬──────────────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │   Dashboard Web     │
              │ (grafici Kp/TEC/RF) │
              └─────────────────────┘
```

## 🧱 Roadmap sintetica

- [ ] Dashboard comparativa Kp/TEC vs GPS/RF.
- [ ] Allerte soglia (es. Kp≥5, noise_dbm>-85 dBm, busy_ratio>60%).
- [ ] Esportazione dataset/plot per analisi esterne.

---
## 🖼️ Interfaccia

Esempio di visualizzazione dell'interfaccia web:

![Interfaccia](https://www.kwos.org/appoggio/droni/space_weather_qos/space_weather_QOS.png)
