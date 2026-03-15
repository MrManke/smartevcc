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

## Interactive UI Control

När komponenten ligger i drift skapar den tre stycken reglage som du sätter i ditt grafiska Lovelace-gränssnitt för att styra beteendet "på the fly" utan att öppna konfiguratorn:

* **[Number] Smartevcc Max Price Limit**
  Styr en absolut smärtgräns i kronor. Skjuter priset över denna gräns laddas inte bilen oavsett hur tom den är. 
* **[Number] Smartevcc Low Price Charging Limit**
  Om timpriset dippar under detta värde kastas alla "scheman" och "hink-kalkyler" i papperskorgen – ladda för fullt, strömmen är så billig att det inte spelar någon roll.
* **[Switch] Smartevcc Force Charge**
  Override-knappen. Tryck in denna för att tvinga bilen att ladda nu. *Notera att systemet givetvis fortfarande är skyddat av Fast Loop och P1-mätaren även när du vrider på denna.*

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
| **Nordpool Entity** | Nuvarande timpris-entitet från t.ex. HACS-Nordpool. | *`sensor.nordpool_kwh_se3`* |
| **EV Battery Level** | Sensor som visar bilens nuvarande SoC (State of Charge). | *`sensor.id4_battery_level`* |
| **EV Min SoC** | Nödladdning! %-gräns där bilen alltid laddar oavsett om elen är dyr. | *`20`* |
| **EV Target Level** | Din önskade målnivå på morgonen. | *`80`* |
| **EV Temp Sensor** | En `weather`- eller `sensor`-entitet för utetemperatur. | *`weather.smhi_home`* |
| **Load Shedding** | Slå av/på smart relä-kontroll, och välj entiteter ur flervalslistor. | *Välj WWB för Nivå 1* |
