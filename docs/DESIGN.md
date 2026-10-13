# Iron Reign: Game Design & Production Bible

Iron Reign is a single-player 2D grand-strategy/RPG in the tradition of Koei's *Romance of the Three
Kingdoms IX* (monthly command turns on a painted map, armies marching in real time across a month) and
*Taiko Risshiden IV* (personal growth of officers, duels, martial sects, town facilities, events).
The setting is a fictional wuxia-era realm, the **Nine Provinces**, after the collapse of the Mandate.

This document is the contract between everyone working on the game. If code and this document disagree,
fix one of them in the same change.

---

## 1. Pillars

1. **The map is the game.** One painted 2D world map with cities, roads, rivers and marching banners.
2. **Officers are characters.** Five stats (Martial, Command, Strategy, Politics, Charm), portraits,
   loyalty, affinity, growth through work, techniques learned from sects, duels on the battlefield.
3. **Every month matters.** Plan (assign orders), watch the month play out day by day, react to battles
   and events.
4. **Battles are personal.** Player battles open a hex tactical map; officers can challenge each other
   to duels resolved by a Strike/Guard/Feint minigame.

## 2. Core loop

```
Title -> New Game (choose scenario, faction, difficulty) -> Strategy screen
  Planning phase (month M, day 0)
    - select own city -> issue orders to idle officers (one per officer per month)
    - form armies (commander + up to 4 deputies, troops, food, target)
    - immediate actions: market, reward, sect donation, prisoners, delegate city
    - answer pending events (modal), then press "End Turn"
  Execution phase (days 1..30)
    - domestic orders resolve on day 1 (log shows results)
    - armies advance along roads each day (animated)
    - field battle when hostile armies meet on a road, siege when an army reaches a hostile city
    - player battles pause: "Command" (tactical screen) or "Delegate" (auto-resolve)
  Month end: income, harvest (month 9), upkeep, growth, loyalty, AI planning, events -> next month
Victory: every other faction eliminated. Defeat: player faction eliminated.
```

## 3. Rules summary (owned by the rules engine, `Sim/IronGame*.cpp`)

Numbers are starting points; tune with the headless simulation test (`Tests/`).

**City economy (per city).** Gold and food are stored per city (classic ROTK).
- Monthly gold income = Commerce x 0.5 x OrderFactor, OrderFactor = 0.5 + Order/200.
- Harvest in month 9: Food += Farm x 20 x OrderFactor.
- Upkeep: each serving officer costs 10 gold/month from the city they are in; garrison eats Troops/10 food
  per month. Food shortage -> 10% desertion and -5 order.
- Population grows with order toward PopulationMax; order decays by 1/month above 40.

**Orders** (cost paid at issue, results on execution day 1, stat exp to the governing stat):

| Order | Cost | Effect |
|---|---|---|
| Farm / Commerce | 50 | +4 + Politics/8 (capped by max) |
| Walls | 50 | Defense +4 + (Politics+Command)/20 |
| Patrol | 30 | Order +3 + (Martial+Command)/30 |
| Draft | Troops/5 gold | Troops +Amount (max 300 + Charm x 15, limited by population), order -3 |
| Train | 30 | Training +5 + Command/10 |
| Search | 20 | Find a hidden officer in the city (chance 25 + Charm/3 + Strategy/5) or some gold/food |
| Recruit | 30 | Chance from recruiter Charm, affinity distance to the ruler, target loyalty |
| Move | 0 | Officer relocates to another own city |
| Transport | 0 | Moves gold/food/troops to another own city |
| Sect Training | 50 | Martial exp +60; chance to learn a sect technique if favor >= 50 |
| Alliance / Truce / Gift | 100 / 50 / Gold | Diplomacy with Trust-based acceptance |

Stats grow with experience: 100 exp = +1 (max 100). Battles grant Command/Martial/Strategy exp.

**Loyalty.** Drifts monthly toward a target based on the ruler's Charm and affinity distance
(compatibility ring 0..149; distance = min(|a-b|, 150-|a-b|)). Reward (gold) raises it. Ambitious,
disloyal officers may leave. Rulers are always 100.

**Armies.** Each officer leads one unit of their Specialty troop type; max troops per unit =
2000 + Command x 60. Daily food = ceil(Troops/300). Speed 10 tenths/day (13 if mostly cavalry);
road length = Days x 10. Armies may pass only through own cities; the target may be any adjacent or
reachable city. Arriving at a hostile city -> siege. Opposite hostile armies on one road -> field battle.
Losers retreat to the nearest own city. Out of food -> morale loss, desertion, return.

**Sieges.** Defenders are the city's officers (best Command first, up to 5) splitting the garrison;
leftover troops form nameless garrison units (stats 40). A city with no troops falls immediately.
Capture: attacker moves in, keeps 50% of the city's gold/food; 30% of surviving defenders surrender and
join; enemy officers are captured or flee to their nearest own city.

**Prisoners.** The player decides: Recruit (chance), Release (+trust), Execute (-trust with everyone,
own loyalty -2), Imprison. Prisoners may escape (5%/month). AI captors recruit or release.

**Rulers.** If a ruler dies or is captured, the officer with the highest Charm+Command succeeds. No
successor -> faction destroyed: cities become independent, officers become free.

**Diplomacy.** Trust 0..100 per faction pair. Alliances (36 months) and truces (12 months) forbid
attacks. AI factions propose alliances/truces to the player through events.

**AI.** Per AI faction each month: recruit free officers, keep order >= 60, draft when troops are low
and gold allows, train, develop; attack a neighbor when local strength > 1.6x the defender's; reinforce
frontier cities from the interior. Difficulty scales AI income (Easy 0.8, Normal 1.0, Hard 1.25) and
aggression.

**Events.** Data-driven (see schema). Player events show a modal with choices; world events apply
effects automatically and are logged.

## 4. Tactical battle (owned by `Sim/IronBattle.cpp`, `Sim/IronDuel.cpp`)

- Flat-top hex grid, odd-q offset layout, 16x11 (sieges up to 18x12 for great cities).
- Field: attacker deploys in the 3 leftmost columns, defender in the 3 rightmost. Terrain is generated
  from `ETerrain` (forests, hills, a river with fords/bridge, mountain blocks) and the battle seed.
- Siege: a wall column with one gate (two for size-3 cities) about 2/3 across; defenders deploy inside;
  the castle hex sits near the right edge. Gate HP = 300 + Defense x 2.
- Movement points: infantry 4, archers 3, cavalry 6. Costs: plain/road/town/bridge/castle 1, forest/hill/
  rubble 2 (cavalry 3), ford 3. Entering a hex next to an enemy ends movement (zone of control).
- Attack: melee adjacent; archers range 2 (no counterattack against ranged). Melee defender counters
  at 50%. Damage ~ 0.7 x sqrt(Troops) x 10 x (attack/defense)^0.7 x type x terrain x morale x random.
  Type: cavalry > archers (+30%), infantry > cavalry (+20%), archers > infantry at range.
  Terrain defense: forest +20%, hill +25%, inside walls +WallBonus, ford -20%.
- Morale 0..100; taking losses lowers it; below 10 the unit routs.
- Tactics: Fire (range 2, damage + burning hex for 2 days), Confuse (range 2, lose next turn),
  Rally (self/adjacent ally, +morale, cures confusion). Chance from Strategy difference.
- Duels: challenge an adjacent enemy officer. AI accepts if brave enough or not outmatched. Declining
  costs morale. Loser's unit loses 30% troops and 30 morale; loser may be captured (25%) or rarely killed.
- End: commander unit destroyed/routed/captured -> that side loses; side wiped out; attacker on castle
  hex; attacker out of food; day > MaxDays -> defender wins.

## 5. Architecture

```
Source/IronReign/
  Sim/            Engine-agnostic rules engine (C++20, std only). Unit tested in Tests/.
    IronTypes     enums + names            (lead)
    IronJson      JSON DOM/parser/writer   (lead)
    IronRandom    deterministic RNG        (lead)
    IronState     data model + JSON load/save + read-only helpers (lead)
    IronGame*     strategic rules, AI, events, diplomacy (rules engineer)
    IronBattle    tactical hex battle + battle AI       (battle engineer)
    IronDuel      duel minigame                          (battle engineer)
  UI/             Slate presentation (all code, no Blueprint/uasset dependencies)
    IronSession   owns FGame, scenarios, save slots        (UE framework engineer)
    IronAssets    runtime PNG -> UTexture2D -> FSlateBrush (UE framework engineer)
    IronStyle     palette, fonts, button styles, widget factories (UE framework engineer)
    SIronRoot     screen stack + modal layer               (UE framework engineer)
    SIronTitleScreen / SIronNewGameScreen / SIronSaveLoadDialog (UE framework engineer)
    SIronStrategyScreen, SIronMapView, SIronCityPanel, SIronCommandPanel, SIronDialogs,
    SIronOfficerTable                                       (UE strategy engineer)
    SIronBattleScreen, SIronHexView, SIronDuelDialog        (UE battle engineer)
  IronReignGameMode / IronReignPlayerController / IronReignWorldStateSubsystem (UE framework engineer)
Content/Data/
  Scenarios/*.json   scenario files (content designer; geography by lead)
  Art/...            generated PNG art (art team), see section 8
  Fonts/*.ttf        OFL fonts (UI art)
Tools/ArtGen/        Python generators for every PNG in Content/Data/Art (art team)
Tests/               CMake project: Sim unit tests + headless AI campaign (everyone)
```

Runtime flow: `AIronReignGameMode` (no pawn) -> `AIronReignPlayerController::BeginPlay` creates
`SIronRoot` in the game viewport with UI-only input -> `UIronReignWorldStateSubsystem` owns the
`FIronSession` -> the session owns `IronSim::FGame`. The default map is the engine's `/Engine/Maps/Entry`
(world rendering disabled), so the game needs no project `.umap`.

Data files are loaded with `FFileHelper` from `FPaths::ProjectContentDir() / "Data"`; packaging stages
`Content/Data` via `DirectoriesToAlwaysStageAsUFS`.

## 6. Coding rules

**Sim/ (std C++):** compiled inside the Unreal module and by `Tests/` with
`-std=c++20 -fno-exceptions -fno-rtti -Wall -Wextra -Wshadow -Werror` (gcc and clang).
- No exceptions (`.at()`, `std::stoi`...), no RTTI, no `assert`.
- No identifiers that are Unreal macros: `check`, `verify`, `ensure`, `PI`, `IN`, `OUT`, `TEXT`,
  `INDEX_NONE`, `CONSTEXPR`, `ERROR`, `DELETE`, `TRANSPARENT`, `OPTIONAL`, `DrawText`, `GetObject`... Prefer
  CamelCase everywhere; never ALL_CAPS identifiers.
- Unity builds concatenate .cpp files: no `using namespace` at file scope and no generic helper names in
  anonymous namespaces. Put helpers in a file-specific namespace (`namespace IronSim { namespace BattleDetail { ... } }`).
- No shadowing (locals vs members/params/outer locals; Unreal turns it into an error).
- Unreal naming: PascalCase, `F` structs/classes, `E` enums, `b` booleans, tabs for indentation.
- Determinism: all randomness through `FRng` from the game state or battle seed.

**UI/ (Unreal):** Unreal Engine 5.8, C++20, Slate only. Linux builds use `-Wall -Werror`.
- Avoid deprecated APIs: use `FVector2f` arrays for `FSlateDrawElement::MakeLines`, the
  `ToPaintGeometry(Size, FSlateLayoutTransform(Offset))` overload, `GetPlatformData()` for textures.
- Text from the sim is UTF-8 `std::string`: convert with `IronUI::ToText` / `IronUI::ToFString`.
- Never block the game thread; the sim is cheap enough to run synchronously.
- Every widget gets its data from `FIronSession`; after mutating the game call `Session->NotifyChanged()`.

## 7. Scenario JSON schema

One file per scenario in `Content/Data/Scenarios/`. A save game uses the same format plus session fields
(a save is "a scenario in progress"). All cross references use string keys.

```jsonc
{
  "format": "ironreign", "version": 1,
  "key": "broken_mandate", "name": "The Broken Mandate", "description": "...",
  "startYear": 212, "startMonth": 1,
  "map": {
    "width": 2400, "height": 1500, "image": "Art/Map/WorldMap.png",
    "land":  [[[x,y], ...]],           // polygons, map units = map image pixels
    "lakes": [[[x,y], ...]],
    "mountains": [{"points": [[x,y],...], "width": 80}],
    "hills":     [{"points": [[x,y],...], "width": 60}],
    "rivers":    [{"points": [[x,y],...], "width": 10}],
    "forests":   [{"x": 0, "y": 0, "r": 60}],
    "deserts":   [{"x": 0, "y": 0, "r": 200}],
    "labels":    [{"text": "Central Plain", "x": 0, "y": 0, "size": 1.0}]
  },
  "techniques": [{"key","name","nameZh","description","kind":"strike|guard|feint","power":160,"minMartial":70}],
  "factions": [{"key","name","nameZh","glyph":"燕","color":"#B3282D","ruler":"officer_key","capital":"city_key"}],
  "cities": [{"key","name","nameZh","description","x","y","size":1-3,
              "terrain":"plains|forest|hills|river|mountains|coast","owner":"faction_key or omitted",
              "population","populationMax","farm","farmMax","commerce","commerceMax",
              "defense","defenseMax","order","troops","training","gold","food","delegated":false}],
  "roads": [{"a":"city","b":"city","days":9,"kind":"road|pass|river","points":[[x,y],...]}],
  "officers": [{"key","name","nameZh","epithet","bio","rumor","portrait":"m_warrior_01",
                "gender":"m|f","birth":180,"appear":0,
                "martial","command","strategy","politics","charm",
                "affinity":0-149,"ambition":0-100,"bravery":0-100,
                "specialty":"infantry|cavalry|archer",
                "status":"serving|free|hidden|unborn|prisoner|dead",
                "faction":"key (serving/prisoner)","captor":"key (prisoner)","city":"key","loyalty":80,
                "merit":0,"sect":"key","techniques":["key"],"exp":[0,0,0,0,0]}],
  "sects": [{"key","name","nameZh","description","city","master":"officer_key","techniques":["key"],
             "favor":{"faction_key": 20}}],
  "relations": [{"a":"faction","b":"faction","trust":60,"alliance":0,"truce":0}],
  "events": [{
    "key": "bandit_raid", "title": "Bandits on the Road", "image": "Events/Bandits.png",
    "text": "Bandits are raiding caravans near {city}, my lord {ruler}...",
    "speaker": "officer_key | advisor", "world": false, "once": true,
    "context": "random_player_city | capital | random_city | <city_key>",
    "when": {"minYear":212, "maxYear":240, "months":[3,4,5], "chance":25,
             "ownsCity":"key", "hasOfficer":"key", "faction":"key", "minCities":1, "maxCities":99},
    "effects": [ /* world events */ ],
    "choices": [{"label": "Send troops", "gold": 0,
                 "effects": [{"type":"troops","amount":-500,"city":"context"},
                             {"type":"order","amount":10,"city":"context"}]}]
  }],

  // ---- save games only ----
  "session": {"year","month","day","phase","outcome","difficulty","player":"faction_key",
              "rng":"hex string","nextArmyId","dayInProgress"},
  "armies": [...], "orders": [...], "pendingEvents": [...], "pendingPrisoners": [...],
  "battleQueue": [...], "log": [...]
}
```

Effect `type` values: `gold food troops order farm commerce defense population training loyalty
loyaltyAll stat joinOfficer revealOfficer trust alliance truce sectFavor learnTechnique message`.
Effect references: `"city": "context"|"capital"|key`, `"officer": "context"|"ruler"|key`,
`"faction": "player"|"context"|key`, `"sect": key`, `"technique": key`, `"stat": "martial"...`,
`"amount"`, `"text"`. Text placeholders: `{city} {ruler} {faction} {officer}`.

## 8. Art bible & asset manifest

**Style.** Painted parchment and ink, 1990s-2000s Koei: warm paper tones, ink outlines, muted earth
colours, vermilion lacquer and gold accents, dark lacquered wood/ink panels. Light from the top-left.
No photographic or neon colours. All art is generated by scripts in `Tools/ArtGen/` (Python 3 + numpy +
scipy + Pillow) so it can be regenerated; outputs are committed PNGs (sRGB, RGBA).

**Palette (sRGB):**

| Token | Hex | Use |
|---|---|---|
| Paper | `#E9DCC0` | panel fill, map land base |
| PaperDark | `#CDB990` | panel shading |
| Ink | `#2A2119` | text, outlines |
| InkSoft | `#5A4A3A` | secondary text |
| Lacquer | `#7E1F17` | headers, buttons |
| LacquerDark | `#4A120D` | pressed, borders |
| Gold | `#C9A24A` | trims, highlights |
| Jade | `#3F6E5A` | positive values |
| Indigo | `#2E3F5C` | water, info |
| Night | `#1B1712` | dark panels/background |

**Faction colours:** Iron Banner `#B3282D`, Wolf Riders `#B07A2A`, Azure Court `#2F6DB5`,
Sea League `#1F8F8A`, Southern Lotus `#4C9A3C`, Black Mountain `#4A4A55`, Independent `#8C8577`.

**Fonts** (`Content/Data/Fonts/`, OFL, downloaded from github.com/google/fonts):
`Body-Regular.ttf` + `Body-Bold.ttf` (Gentium Book Plus), `Heading.ttf` (Marcellus),
`Brush.ttf` (Ma Shan Zheng, used for CJK glyphs, faction banners and decorative titles).

**Manifest** (paths relative to `Content/Data/`; the UI must tolerate missing files with a fallback):

| Path | Size (px) | Notes |
|---|---|---|
| `Art/Map/WorldMap.png` | 2400x1500 | Painted world map from the scenario `map` block: sea, coast ink line, plains, steppe/desert, hills, mountain glyphs, forests, rivers, lakes. No city icons, no roads, no labels (drawn at runtime). |
| `Art/Map/City_1.png`, `City_2.png`, `City_3.png` | 96x96 | Town / walled city / great city with gate tower and curved roofs. Neutral stone and wood; no faction colour. Transparent background, bottom-center anchored. |
| `Art/Map/Banner.png` | 64x96 | Army banner on a pole, **white cloth** (tinted at runtime with the faction colour), dark pole; transparent. |
| `Art/Map/BannerGlyphArea.txt` | - | Optional: x y w h of the cloth area for the glyph. |
| `Art/Map/Sect.png` | 64x64 | Small pagoda/temple marker. |
| `Art/Map/Flag.png` | 32x48 | Small white pennant to tint, shown above city icons. |
| `Art/Battle/Hex_<Terrain>.png` | 128x111 | Flat-top hex (width 128 = 2r with r=64, height round(sqrt(3)x64)=111), transparent outside the hex. Terrains: Plain, Forest, Hill, Mountain, Water, Ford, Bridge, Road, Wall, Gate, Town, Castle, Rubble. |
| `Art/Battle/Hex_Fill.png` | 128x111 | Solid white hex (for tinted highlights). |
| `Art/Battle/Hex_Outline.png` | 128x111 | White hex outline ~3px (for tinted selection rings). |
| `Art/Battle/Unit_Infantry.png`, `Unit_Cavalry.png`, `Unit_Archer.png` | 96x96 | Unit figure icon, mostly neutral colours with **white** clothing/flag areas so runtime tint reads; transparent. |
| `Art/Battle/Unit_Base.png` | 96x96 | White disc/plinth to tint with faction colour under the figure. |
| `Art/Battle/Fx_Fire.png`, `Fx_Confuse.png`, `Fx_Rally.png`, `Fx_Hit.png` | 96x96 | Effect overlays. |
| `Art/Battle/Background.png` | 1920x1080 | Dark war-table / parchment surround behind the hex board. |
| `Art/Portraits/<id>.png` | 192x240 | Painted bust portraits, opaque background (neutral dark paper). Ids: `m_warrior_01..30`, `m_scholar_01..20`, `m_elder_01..12`, `m_monk_01..06`, `m_rogue_01..10`, `f_warrior_01..10`, `f_scholar_01..10`, `f_elder_01..04`. Plus `unknown.png` (silhouette). |
| `Art/UI/Panel.png` | 128x128 | 9-slice parchment panel, 24px border (ink line + gold inner trim). |
| `Art/UI/PanelDark.png` | 128x128 | 9-slice dark lacquer/ink panel, 24px border, gold trim. |
| `Art/UI/Button.png`, `Button_Hover.png`, `Button_Pressed.png`, `Button_Disabled.png` | 192x64 | 9-slice lacquer buttons, 20px horizontal / 16px vertical margins. |
| `Art/UI/Tab.png`, `Tab_Active.png` | 160x48 | 9-slice tabs. |
| `Art/UI/Frame_Portrait.png` | 212x260 | Ornamental frame for 192x240 portraits (transparent center). |
| `Art/UI/Title_Background.png` | 1920x1080 | Title screen painting: misty mountains, fortress, banners. |
| `Art/UI/Title_Logo.png` | 1200x400 | "IRON REIGN" logo + brush calligraphy 铁血王座, transparent. |
| `Art/UI/Seal.png` | 128x128 | Red square seal stamp, transparent. |
| `Art/UI/Scroll.png` | 1024x640 | Event dialog backdrop (unrolled scroll), 9-slice-able with 80px margins. |
| `Art/UI/Divider.png` | 512x16 | Ornamental horizontal divider. |
| `Art/UI/Icon_<Name>.png` | 64x64 | Ink-and-colour icons, transparent: Farm, Commerce, Walls, Patrol, Draft, Train, Search, Recruit, Move, Transport, SectTraining, Alliance, Truce, Gift, March, Market, Tavern, Officers, Factions, Save, Load, EndTurn, Gold, Food, Troops, Population, Order, Defense, Training, Loyalty, Settings, Delegate, Prisoner, Fire, Confuse, Rally, Duel, Attack, Wait, Undo. |
| `Art/Events/<Name>.png` | 640x360 | Event illustrations: Court, Battle, Harvest, Disaster, Wanderer, Sect, Bandits, Envoy, Festival, Plague, Flood, Omen. |
| `Art/Duel/Background.png` | 1280x720 | Duel arena: cliff/bamboo at dusk. |

**Portrait archetypes.** Warrior: armour, helmet or headband, strong jaw, beard variants. Scholar: robes,
guan hat, thin beard, fan. Elder: white hair/beard. Monk: shaved head, prayer beads. Rogue: scarf,
scar, messy hair. Female warrior: armour, hair bun with pins. Female scholar: elegant robes,
ornaments. Consistent 3/4 view, same lighting and framing (head + shoulders, eyes ~38% from the top).

## 9. UI specification

Target 1920x1080, scales with the engine DPI curve. Fonts: Body 14-16, headers 20-28.

**Title:** background painting, logo, buttons New Game / Load Game / Quit.

**New Game:** scenario list (left), faction cards (ruler portrait, banner glyph, cities, officers,
troops), difficulty selector, Start.

**Strategy screen:**
- Top bar: date & season, phase ("Planning" / "Day 12"), player faction banner, total gold/food/troops,
  buttons Officers, Factions, Save, Load, End Turn (Planning) or speed controls (Execution).
- Center: map view (pan by drag, zoom with wheel, clamp to map). Draws the painted map, roads
  (dashed ink, pass = dotted, river route = blue), city icons by size with faction pennant and name
  plaque, sect markers, army banners (faction tint + glyph, troop count) interpolated along roads, labels.
  Click a city to select; hover shows a tooltip.
- Left: city panel (name + Chinese name, owner, stats with bars, troops/training/gold/food, officers in
  the city with portrait thumbnails and current order).
- Right: command panel for player cities with tabs Domestic / Military / Personnel / Diplomacy / Town.
  Each command opens a dialog: officer picker (table with stats, highlights the relevant stat, shows
  preview/success chance), target picker, amount slider. Town tab: Market (buy/sell food), Tavern (free
  officers + rumor), Sect (donate, train).
- Bottom: message log (player news + important world news), newest first.
- Modals: event dialog (scroll background, illustration, speaker portrait, choices), prisoner decision,
  battle prompt (Command / Delegate), month report, game over/victory.
- Officers screen: sortable table of all faction officers. Factions screen: all factions with cities,
  troops, trust/alliance/truce.

**Battle screen:** hex board (terrain tiles, burning overlay, gate HP), units (base tinted by side colour,
type figure, troop bar, commander marker, status), selection highlights (reachable = blue, targets = red,
tactic = purple), right panel (selected unit portrait/stats/morale/troops, actions Attack / Fire /
Confuse / Rally / Duel / Wait / Undo), top bar (location, day X/30, sides with total troops, gate HP),
bottom log, buttons End Turn / Delegate. AI turns animate one action at a time (~0.35 s).

**Duel dialog:** two portraits, HP bars, round counter, buttons Strike / Guard / Feint plus technique
buttons, round history text.

## 10. Testing & CI

- `Tests/` (CMake): unit tests for JSON, state load/save round-trip, orders, execution, battle, duel,
  and a headless AI-only campaign (no crashes, invariants hold, conquests happen).
- GitHub Actions (`.github/workflows/ci.yml`): (1) Sim tests with gcc and clang; (2) Unreal build of
  `IronReignEditor` + automation tests + Linux package in Epic's `ghcr.io/epicgames/unreal-engine` 5.8
  container (requires GHCR credentials of an Epic-linked GitHub account, see README).

## 11. Localization

Supported cultures: **English (`en`), Simplified Chinese (`zh-Hans`), Traditional Chinese (`zh-Hant`),
Japanese (`ja`), Korean (`ko`)**. The language is chosen on the title screen / settings, defaults to the OS
culture, and is stored in `Saved/IronReign/Settings.json`. Switching language relabels everything live.

- One mechanism for all text: `IronSim::FLocale` string tables (`Sim/IronLocale.h`), used by the rules
  engine and the UI (`IronUI::Loc/LocF` return `FText`). Unreal's LOCTEXT/gather pipeline is not used.
- Code carries the English default inline: `Loc("key", "English")`, `LocF("key", "Hello {name}", {{"name", X}})`.
  Key and default must be string literals on one line. Whole sentences with named placeholders; never
  concatenate fragments (word order differs). Keys are dotted lowercase (`ui.title.newGame`, `log.city.captured`).
- Scenario data stays English in the game state (saves are language neutral). Display text comes from
  `NameOf/BioOf/TitleOf/...` which look up `officer.<key>.name`, `city.<key>.name`, `event.<key>.choice.<i>`...
- Files: `Content/Data/Localization/<culture>/Strings.json` (UI + rules text) and
  `Content/Data/Localization/<culture>/Scenario_<scenarioKey>.json` (scenario data). English tables are
  generated by `Tools/Localization/extract_strings.py` (scans sources for Loc/LocF) and
  `ExtractScenarioStrings`; translators fill the other cultures with the same keys.
- Fonts: `Body-*.ttf`/`Heading.ttf` (Latin) with CJK fallback fonts per culture:
  `Fonts/CJK-SC-Regular.ttf`/`-Bold.ttf` (Noto Serif SC), `CJK-TC-*` (Noto Serif TC), `CJK-JP-*`
  (Noto Serif JP), `CJK-KR-*` (Noto Serif KR), subset to the characters used by the game's text by
  `Tools/Localization/build_fonts.py` (re-run after text changes). The UI builds composite fonts: the
  culture's CJK font is the default typeface for CJK cultures and the fallback typeface for English.
- Naming conventions: Chinese names in Chinese characters (Traditional forms for zh-Hant), Japanese uses
  kanji names (Japanese shinjitai forms) as Koei's Japanese releases do, Korean uses Hangul readings of the
  Sino-Korean names (as in Korean releases). Faction banner glyphs are also localized (`faction.<key>.glyph`).
