# SmartEVCC - Custom Home Assistant Component

SmartEVCC är ett lokalt energihanteringssystem (EMS) för Home Assistant, speciellt utformat för att balansera och optimera elbilsladdning i kombination med hemmets övriga förbrukning.

Komponenten är byggd med en unik **Dual Loop-arkitektur** för att separera snabbt överlastskydd från långsammare prisoptimering.

## Funktioner

### Snabba Loopen (Säkringsskydd & Lastbalansering - Fas 1-3)
- **Körs var 10:e sekund** för att läsa av fasströmmar (t.ex. från P1-mätare).
- **Hysteres och Anti-Flapping:** Mindre överlaster tolereras i 60 sekunder, medan allvarliga överlaster triggar åtgärd på 10 sekunder. Systemet har en 3 minuters minnes-hysteres vid återställning.
- **Fail-safe:** Om komponenten tappar kontakt med P1-mätaren i mer än 30 sekunder faller Zaptec-laddaren tillbaka till minimum (6A) automatiskt.
- **Level 1 Defense (Zaptec API):** Drar stegvis ned Zaptec-laddarens ström till minimum (6A).
- **Level 2 Defense (Load Shedding - Valbart):** Om huset fortfarande är överbelastat trots att be bilen laddar på 6A, börjar systemet automatiskt stänga av prioriterade laster i lager:
  1. **Nivå 1 Switchar:** Slår av reläer (t.ex. mindre Varmvattenberedare).
  2. **Nivå 2 Switchar:** Slår av tyngre laster (t.ex. element).
  3. **Klimat / Värmepumpar (Automatisk logik):** Sänker värmen eller höjer kylan med 3°C för att spara ström, utan att stänga av maskinen helt. Sparar det ursprungliga läget och återställer dynamiskt (LIFO) när strömmen är säker igen.
- **Zaptec Pause (Level 3 Defense):** Om inga laster finns kvar att stänga av, pausas Zaptec-laddaren helt. 

### Långsamma Loopen (Pris- & Kapacitetsplaneraren - Fas 4)
- **Körs varje timme** för att beräkna framtida laddbehov fram till din angivna avfärdstid.
- **Köldpåverkan (Climate Throttle):** Om utomhus/batteritemperaturen understiger valt gränsvärde (t.ex. -4°C) ställer systemet om kalkylen till en lägre förväntad maxeffekt (t.ex. 4 kW) och bokar in *fler* timmar än vanligt för att hinna nå målet.
- **Price Optimization:** Hämtar och pusslar ihop de billigaste timmarna från Nordpool. Om nuvarande timme ligger utanför listan tvingas Zaptecen ned i viloläge/minimiström.

### Status-Sensor (State Machine - Fas 5)
- Integrerad `sensor.smartevcc_status` uppdateras i realtid (Idle, Charging, Shedding, Fuse_Protect_Paused, Price_Wait) för att visualisera vad systemet gör direkt i dina dashboards.

## Konfiguration (UI)
Ingen YAML krävs! Hela systemet konfigureras direkt via Home Assistants gränssnitt med dynamiska selectors. Ändra valda switchar, värmepumpar, P1-sensorer eller Nordpool-entiteter i farten genom "Integrationer -> SmartEVCC -> Konfigurera".

## Installation

1. Kopiera foldern `smartevcc` till din `custom_components`-mapp i Home Assistant.
2. Starta om Home Assistant.
3. Gå till **Inställningar -> Enheter och tjänster -> Lägg till integration**.
4. Sök efter "SmartEVCC" och följ installationsguiden.
