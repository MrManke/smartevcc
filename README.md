# SmartEVCC (Custom Component för Home Assistant)

En intelligent, lokal "dirigent" för hemmets elförbrukning som maximerar laddhastighet för elbil till lägsta pris, utan att riskera huvudsäkringen. 

Integrationen drar tung inspiration från de populära projekten [**evcc.io**](https://github.com/evcc-io/evcc) och [**EV Smart Charging**](https://github.com/jonasbkarlsson/ev_smart_charging), för att erbjuda en svårslagen kombination av lokalt blixtsnabbt fas-skydd och automatiserad nordpool-prissättning – byggt direkt i Home Assistant utan externa driftberoenden (som MQTT-servrar eller separata Docker-containrar).

## Huvudfunktioner

1. **Dual-Loop Arkitektur**
   * **Fast Loop (Säkringsskydd - 10 s):** Övervakar lokala mätvärden (t.ex. P1/Han-port) var 10:e sekund för omedelbart ingripande. Vid överlast reagerar systemet direkt för att undvika att husets huvudsäkring går. Den filtrerar "startspikar" (ex. från kylskåp) för att undvika onödiga avbrott (Anti-Flapping).
   * **Slow Loop (Prisplanerare - 1 h):** Vaknar varje timme och bygger en "hink" av energi som behöver fyllas innan avfärd. Letar upp morgondagens Nordpool-priser och schemalägger laddningen på de absolut billigaste timmarna.

2. **Smart Köldkompensation (Proaktiv Throttling)**
   Kalla elbilsbatterier (särskilt de från MEB-plattformen, som ID.4) tar inte emot laddning lika fort.
   Integrationen analyserar nästa dygns **väderprognos** (`weather`-entiteter) eller en specifik **temperatursensor**. Dippar värdet för de kommande timmarna under en viss angiven kyla, beräknar Slow Loop proaktivt med att ladda på "lägre effekt" (t.ex 4 kW istället för 11 kW) och tillsätter automatiskt fler billiga timmar under natten. Resultatet är att bilen *alltid* är full när du ska åka, även om det var 10 minusgrader och bilen inte tog emot ström lika fort som på sommaren.

3. **Hierarkisk Load Shedding (Dropp-lista)**
   När Zaptec dragits ner till sin absoluta minimumnivå (6A) och säkringen fortfarande hotas, släcker komponenten metodiskt ner utvald last i en kaskad, och startar sedan upp den igen mjukt när faran är över:
   * **Nivå 1:** Mindre/enklare switchar (t.ex. Varmvattenberedare)
   * **Nivå 2:** Tyngre laster (t.ex. stora elelement)
   * **Nivå 3:** Golvvärme sänks intelligent! (3 graders offset)

4. **Säker & Responsiv Fail-Safe**
   * **Ingen kommunikation** med P1-mätare? Systemet ställer omedelbart ner laddboxen till max 6A som säkerhetsåtgärd.
   * **Dyr tjuvladdning stoppas:** Ligger bilen på faser där priset är högt blockerar komponenten minsta strömmen genom en ren *avstängning* (`switch.turn_off` på laddaren). Det förhindrar den där konstanta, dryga 4 kW-förlusten ("tjuvladdning") som annars kan ske.

5. **Avancerade "Nice-To-Have" Funktioner [Nytt]**
   * **Zaptec 1-fas Fallback:** Om en fas (L2/L3) oavsiktligt blir snedbelastad tvingar komponenten automatiskt Zaptec till att byta till "1-fas" istället för att stänga av helt. När strömmen blir tillgänglig igen byter den tillbaka till "3-fas".
   * **"Sista Minuten" (Prisspik Override):** Om priset stiger extremt mycket inför *nästa* dag, prioriterar komponenten automatiskt att ladda till *100%* under den innevarande billiga natten för att säkra upp budgeten!

## Interactive UI Control

När komponenten ligger i drift är alla dina viktiga parameterar samlade som fysiska reglage (Numbers) och Brytare (Switches) på din "SmartEVCC Controller" i ditt enhetskort i Home Assistant. Du slipper gå in i tilläggsmenyer – all interaktion görs "on the fly":

### Reglage (Number)
* **Max Price Limit & Low Price Limit:** Ställ in extrema prisgränser för när bilen *aldrig* eller *alltid* ska ladda.
* **Main Fuse (A):** Din konfigurerade huvudsäkring.
* **Recovery Duration (s):** Hur länge systemet måste ha legat "på den säkra sidan" innan Zaptecs Ampere höjs igen.
* **EV Min SoC & Target Level:** Styr din nödladdning och din målnivå (%).
* **EV Battery Capacity & Max Charge Rate:** De fysiska parametrarna systemet använder för schemaläggning.
* **Cold Temp Threshold & Cold Charge Rate:** Automatisk throttlings-logik på vinterhalvåret. 

### Sensorer
* **[Ny] Lägsta prognostiserade temperatur:** Visar kalkylen från vädersensorn du angett, som systemet baserar "Cold Temp"-throttling på.
* **[Ny] Planerad laddning:** En dynamisk text-sensor som exakt talar om vilka tider under dygnet SmartEVCC planerar att låta strömmen flöda till din EV. 

### Brytare (Switch)
* **Force Charge (Override):** Tvingar laddning att starta omedelbart (men du är fortfarande skyddad av Fast Loop och P1-mätaren).
* **Load Shedding:** Slå av/på funktionen för att tillfälligt stänga av husets element och varmvatten vid lasttoppar.
* **Prisspik-Override (100%):** Om du vill låta systemet maxa till 100% (och strunta i ditt målvärde) om elen imorgon blir extremdyr ("Sista Minuten"-funktionen). 
* **1-fas Fallback:** Aktivera den automatiska räddningen för snedbelastning. Tvingar Zaptec in i 1-fas tills headroom återvänder.
* **Debug Mode:** Skapar detaljerade JSON-dumpar i mappen `/config/custom_components/smartevcc/debug_logs/` vid alla ingripanden från Fast Loop, så du kan se i detalj varför systemet reagerade.

## EVCC-Matematik för Återhämtning
När tunga storförbrukare i huset (ex. ugnen) stängs av räknar systemet direkt fram exakt hur stort utrymme ("headroom") som finns kvar upp till huvudsäkringen, och tilldelar laddboxen all tillgänglig kapacitet i ett enda responsivt kommando! En omedelbar maximering av den ström som faktiskt  är ledig.

## Installation & Konfiguration
Inga yaml-filer behövs - komponenten stöder fullständig Home Assistant Config Flow.
1. Kopiera foldern `smartevcc` till din `custom_components`-mapp i Home Assistant.
2. Starta om Home Assistant.
3. Gå till **Inställningar -> Enheter och tjänster -> Lägg till integration**.
4. Sök fram "SmartEVCC" och klicka!

*I guiden som dyker upp mappar du enkelt vilka entiteter (P1, Nordpool, Bil) din Home Assistant har.*

| Meny / Tabb | Vad gör den? | Example Entities |
| :--- | :--- | :--- |
| **Huvudsäkring** | Siffra på hur mycket ditt tak är per fas. Fritext: T.ex. 16, 20 eller 17.5A. | *`16`* |
| **P1 Fas 1-3** | Sensorer som visar strömförbrukningen i realtid. | *`sensor.p1_fas_1_current`* |
| **Zaptec Ladd-Amp** | The number-entity som ställer amp på boxen. | *`number.zaptec_id_max_laddstrom`* |
| **Charger Status** | Valfri sensor som visar om bilen är inkopplad för att stoppa onödiga anrop. | *`sensor.zaptec_id_laddstatus`* |
| **Zaptec Fas-läge** | Valfri sensor/select för att bestämma 1-fas eler 3-fasläge för fallback funktionen | *`select.zaptec_id_operating_mode`* |
| **Nordpool Entity** | Nuvarande timpris-entitet från t.ex. HACS-Nordpool. | *`sensor.nordpool_kwh_se3`* |
| **EV Battery Level** | Sensor som visar bilens nuvarande SoC (State of Charge). | *`sensor.id4_battery_level`* |
| **EV Min SoC** | Nödladdning! %-gräns där bilen alltid laddar oavsett om elen är dyr. | *`20`* |
| **EV Target Level** | Din önskade målnivå på morgonen. | *`80`* |
| **EV Temp Sensor** | En `weather`- eller `sensor`-entitet för utetemperatur. | *`weather.smhi_home`* |
| **Load Shedding** | Slå av/på smart relä-kontroll, och välj entiteter ur flervalslistor. | *Välj WWB för Nivå 1* |
