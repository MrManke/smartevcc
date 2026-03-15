---
trigger: always_on
---

---
trigger: always_on
---

# Antigravity Rules: SmartEVCC (Custom Component)
*Version: 1.0 | Context: Local Load Balancing & Price Optimization*

## 1. CORE ARCHITECTURE (Dual Loop System)
SmartEVCC måste byggas med två separata asynkrona loopar för att separera prisplanering (långsam) från säkringsskydd (blixtsnabb).

### Loop 1: The Fast Loop (Fuse Protection & Load Balancing)
- **Intervall:** Körs var 10:e sekund.
- **Inputs:** `sensor.p1_meter_strom_fas_1`, `_2`, `_3`.
- **Constraint 1 (Max):** Huvudsäkring är 16A. Sätt en hård gräns på 15.5A för ingripande.
- **Constraint 2 (Min):** Bilar kan inte ladda på mindre än 6A (standard). 
- **Logik vid överlast (>15.5A på någon fas):**
  1. Minska laddström på Zaptec Go via lokalt OCPP-kommando ned till minimum 6A.
  2. Om laddaren redan är på 6A och fasen fortfarande är över 15.5A -> Initiera **Load Shedding**.
  3. Om Load Shedding är utmaxat och fasen >15.5A -> Pausa laddningen (`switch.zaptec_go_laddar` = off / OCPP StopTransaction).

### Loop 2: The Slow Loop (Price & Capacity Planner)
- **Intervall:** Körs varje timme, eller vid state-change på Nordpool-entiteten.
- **Inputs:** `sensor.nordpool_kwh_se2_sek_3_10_025`, `sensor.id4_gtx_battery_level`, `sensor.id4_gtx_hv_battery_min_temperature`.
- **Logik:** Skapa en array av de billigaste timmarna fram till önskad avfärdstid för att nå målet (t.ex. 80%).
- **Cold Weather Override:** Om `id4_gtx_hv_battery_min_temperature` < -4.0, begränsa förväntad maxeffekt i kalkylen till 4 kW (ca 6A på 3-fas). Planeraren MÅSTE schemalägga fler timmar eftersom laddhastigheten är strypt av bilen.

## 2. LOAD SHEDDING HIERARCHY (The Drop List)
När Fast Loop behöver sänka husets förbrukning, stäng av/sänk enheter i exakt denna ordning. Återställ i omvänd ordning med 3 minuters hysteres.

**Nivå 1: Varmvattenberedare (Reläer)**
- `switch.varmvattenberedare_outlet`
- `switch.smart_switch_24091105541627510802c4e7ae0b7c12_outlet`
- ny entiteter kommer till sommaren för att tex reglera värmepump till pool
**Nivå 3: Tunga Element (Relä)**
- `switch.smart_switch_24091110714336510802c4e7ae0b7c26_outlet` (Stora element)

**Nivå 2: Golvvärme (Ebeco Climate - Sänk target temp med 3 grader)**
- `climate.vardagsrum`
- `climate.matrum`
- `climate.tvattstuga`
- `climate.badrum`
- `climate.master_bedroom`
- `climate.sovrum_litet`
- `climate.koket`

## 3. HOME ASSISTANT STANDARDER & SÄKERHET
- **Inga synkrona anrop:** Använd enbart `aiohttp` och `asyncio`. Inga blockerande sleep-kommandon.
- **State Machine:** Komponenten måste exponera en sensor (t.ex. `sensor.smartevcc_status`) med tydliga states: `Idle`, `Price_Wait`, `Charging`, `Shedding`, `Fuse_Protect_Paused`.
- **Fall-back:** Om komponenten tappar kontakten med `sensor.p1_meter_strom_fas_1` i mer än 30 sekunder MÅSTE den dra ner Zaptec till 6A som en säkerhetsåtgärd.

## 4. FILSYSTEM & DEBUG
- Vid varje aktivering av Load Shedding, skriv en loggpost med aktuell fasbelastning till en JSON-fil i `export/smartevcc_shedding_[date].json`. Använd `os.makedirs` för att garantera att mappen finns.