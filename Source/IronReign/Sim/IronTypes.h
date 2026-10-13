#pragma once

#include <cstdint>
#include <string>

/**
 * Shared enums and constants for the Iron Reign rules engine.
 *
 * The Sim/ folder is engine-agnostic C++20 so the rules can be unit tested outside Unreal.
 * It is compiled as part of the IronReign module, so it must follow Unreal's build constraints:
 * no exceptions, no RTTI, no identifiers that collide with Unreal macros (check, verify, PI, IN, OUT, TEXT...),
 * no variable shadowing, and no file-local helpers with generic names (unity builds merge .cpp files).
 */
namespace IronSim
{
	constexpr int StatCount = 5;
	constexpr int MaxStatValue = 100;
	constexpr int DaysPerMonth = 30;
	constexpr int MaxArmyUnits = 5;
	constexpr int MaxLogEntries = 400;

	/** Order matches FIronCharacterAttributes: Martial, Command, Strategy, Politics, Charm. */
	enum class EStat : uint8_t
	{
		Martial,
		Command,
		Strategy,
		Politics,
		Charm
	};

	enum class ETroopType : uint8_t
	{
		Infantry,
		Cavalry,
		Archer
	};

	enum class EGender : uint8_t
	{
		Male,
		Female
	};

	enum class EOfficerStatus : uint8_t
	{
		Serving,   // Belongs to a faction and is stationed in a city or marching with an army.
		Free,      // Wandering hero visible in a city tavern; can be recruited.
		Hidden,    // Present in a city but must be discovered with the Search order.
		Prisoner,  // Held in a city by another faction.
		Dead,
		Unborn     // Appears as a Free officer when the calendar reaches AppearYear.
	};

	/** Surroundings of a city or road. Drives tactical battle map generation. */
	enum class ETerrain : uint8_t
	{
		Plains,
		Forest,
		Hills,
		River,
		Mountains,
		Coast
	};

	enum class ERoadKind : uint8_t
	{
		Road,
		Pass,
		River
	};

	enum class EPhase : uint8_t
	{
		Planning,   // Player issues orders for the month.
		Execution,  // Days 1..30 play out: armies march, battles happen.
		GameOver
	};

	enum class EOutcome : uint8_t
	{
		None,
		Victory,
		Defeat
	};

	enum class EDifficulty : uint8_t
	{
		Easy,
		Normal,
		Hard
	};

	/** Monthly officer assignments. Each serving officer may carry one order per month. */
	enum class EOrderType : uint8_t
	{
		Farm,          // Develop farmland (Politics).
		Commerce,      // Develop markets (Politics).
		Walls,         // Repair and raise city defense (Politics/Command).
		Patrol,        // Raise public order (Martial/Command).
		Draft,         // Conscript troops (Charm). Amount = troops requested.
		Train,         // Drill the garrison (Command).
		Search,        // Look for hidden talent, gold or supplies (Charm/Strategy).
		Recruit,       // Persuade a free officer or enemy officer (Charm). TargetOfficer.
		Move,          // Relocate the officer to another own city. TargetCity.
		Transport,     // Escort gold/food/troops to another own city. TargetCity + Gold/Food/Troops.
		SectTraining,  // Train with a martial sect (Martial exp, may learn a technique). TargetSect.
		Alliance,      // Envoy proposes an alliance. TargetFaction.
		Truce,         // Envoy proposes a ceasefire. TargetFaction.
		Gift,          // Envoy delivers gold to raise trust. TargetFaction + Gold.
		Count
	};

	/** Duel moves: Strike beats Feint, Feint beats Guard, Guard beats Strike. */
	enum class EDuelMove : uint8_t
	{
		Strike,
		Guard,
		Feint
	};

	enum class EArmyState : uint8_t
	{
		Marching,   // Heading to Target.
		Returning   // Retreating or returning to an own city.
	};

	enum class EBattleKind : uint8_t
	{
		Field,  // Two armies meet on a road.
		Siege   // An army assaults a city.
	};

	enum class EPrisonerDecision : uint8_t
	{
		Recruit,
		Release,
		Execute,
		Imprison
	};

	enum class EEffectType : uint8_t
	{
		Gold,            // Amount to City.
		Food,            // Amount to City.
		Troops,          // Amount to City.
		Order,           // Amount to City public order.
		Farm,
		Commerce,
		Defense,
		Population,
		Training,
		Loyalty,         // Amount to Officer.
		LoyaltyAll,      // Amount to every officer of Faction.
		Stat,            // Amount to Officer stat Stat.
		JoinOfficer,     // Officer joins Faction at City.
		RevealOfficer,   // Hidden/unborn Officer becomes Free at City.
		Trust,           // Amount to trust between Faction and the player.
		Alliance,        // Faction and player become allies for Amount months.
		Truce,           // Faction and player sign a truce for Amount months.
		SectFavor,       // Amount to Sect favor toward the player.
		LearnTechnique,  // Officer learns Technique.
		Message          // Adds Text to the log.
	};

	/** Special reference values used by event effects; resolved when the event fires. */
	constexpr int RefNone = -1;
	constexpr int RefContext = -2;  // The event's context city / faction / officer.
	constexpr int RefCapital = -3;  // City: the player's capital.
	constexpr int RefPlayer = -3;   // Faction: the player's faction.
	constexpr int RefRuler = -3;    // Officer: the player's ruler.

	const char* EnumName(EStat Value);
	const char* EnumName(ETroopType Value);
	const char* EnumName(EGender Value);
	const char* EnumName(EOfficerStatus Value);
	const char* EnumName(ETerrain Value);
	const char* EnumName(ERoadKind Value);
	const char* EnumName(EPhase Value);
	const char* EnumName(EOutcome Value);
	const char* EnumName(EDifficulty Value);
	const char* EnumName(EOrderType Value);
	const char* EnumName(EDuelMove Value);
	const char* EnumName(EArmyState Value);
	const char* EnumName(EBattleKind Value);
	const char* EnumName(EPrisonerDecision Value);
	const char* EnumName(EEffectType Value);

	bool EnumParse(const std::string& Text, EStat& Out);
	bool EnumParse(const std::string& Text, ETroopType& Out);
	bool EnumParse(const std::string& Text, EGender& Out);
	bool EnumParse(const std::string& Text, EOfficerStatus& Out);
	bool EnumParse(const std::string& Text, ETerrain& Out);
	bool EnumParse(const std::string& Text, ERoadKind& Out);
	bool EnumParse(const std::string& Text, EPhase& Out);
	bool EnumParse(const std::string& Text, EOutcome& Out);
	bool EnumParse(const std::string& Text, EDifficulty& Out);
	bool EnumParse(const std::string& Text, EOrderType& Out);
	bool EnumParse(const std::string& Text, EDuelMove& Out);
	bool EnumParse(const std::string& Text, EArmyState& Out);
	bool EnumParse(const std::string& Text, EBattleKind& Out);
	bool EnumParse(const std::string& Text, EPrisonerDecision& Out);
	bool EnumParse(const std::string& Text, EEffectType& Out);

	/** Player-facing names ("Develop Farmland", "Martial"...), translated through the active FLocale (IronLocale.h). */
	std::string DisplayName(EStat Value);
	std::string ShortName(EStat Value);
	std::string DisplayName(ETroopType Value);
	std::string DisplayName(EOrderType Value);
	std::string DisplayName(ETerrain Value);
	std::string DisplayName(EDuelMove Value);
	std::string DisplayName(EDifficulty Value);

	inline int ClampInt(int Value, int Low, int High)
	{
		return Value < Low ? Low : (Value > High ? High : Value);
	}

	inline int StatIndex(EStat Stat)
	{
		return static_cast<int>(Stat);
	}

	/** Seasons follow the lunar-style calendar used by the UI: 1-3 spring, 4-6 summer, 7-9 autumn, 10-12 winter. Translated. */
	std::string SeasonName(int Month);
}
