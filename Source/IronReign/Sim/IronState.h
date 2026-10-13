#pragma once

#include "Sim/IronJson.h"
#include "Sim/IronRandom.h"
#include "Sim/IronTypes.h"

#include <string>
#include <vector>

namespace IronSim
{
	// ---------------------------------------------------------------------------------------------
	// Strategic map geometry. Units are pixels of the painted world map image (default 2400x1500).
	// ---------------------------------------------------------------------------------------------

	struct FPoint
	{
		float X = 0.0f;
		float Y = 0.0f;
	};

	struct FMapStroke
	{
		std::vector<FPoint> Points;
		float Width = 0.0f;
	};

	struct FMapCircle
	{
		FPoint Center;
		float Radius = 0.0f;
	};

	struct FMapLabel
	{
		std::string Text;
		FPoint Position;
		float Size = 1.0f;
	};

	struct FMapDef
	{
		int Width = 2400;
		int Height = 1500;
		/** Painted map image, relative to Content/Data. */
		std::string Image;
		std::vector<std::vector<FPoint>> Land;
		std::vector<std::vector<FPoint>> Lakes;
		std::vector<FMapStroke> Mountains;
		std::vector<FMapStroke> Hills;
		std::vector<FMapStroke> Rivers;
		std::vector<FMapCircle> Forests;
		std::vector<FMapCircle> Deserts;
		std::vector<FMapLabel> Labels;
	};

	// ---------------------------------------------------------------------------------------------
	// Entities. Cross references are indices into the FGameState arrays (-1 = none).
	// The JSON format uses string keys instead; see IronState.cpp.
	// ---------------------------------------------------------------------------------------------

	struct FOfficer
	{
		std::string Key;
		std::string Name;
		std::string NameZh;
		std::string Epithet;
		std::string Bio;
		/** Tavern hint shown while the officer is hidden or free. */
		std::string Rumor;
		/** Portrait asset id, e.g. "m_warrior_03" -> Content/Data/Art/Portraits/m_warrior_03.png. */
		std::string Portrait;
		EGender Gender = EGender::Male;
		int Stats[StatCount] = {50, 50, 50, 50, 50};
		/** Experience toward the next +1 of each stat; 100 exp = +1. */
		int StatExp[StatCount] = {0, 0, 0, 0, 0};
		int BirthYear = 180;
		/** Year an Unborn officer becomes Free (0 = from the start). */
		int AppearYear = 0;
		/** Compatibility ring 0..149 (as in classic Koei titles). Close values get along. */
		int Affinity = 75;
		int Ambition = 50;
		int Bravery = 50;
		ETroopType Specialty = ETroopType::Infantry;
		EOfficerStatus Status = EOfficerStatus::Free;
		/** Allegiance. For prisoners this is the faction they served before capture (-1 if none). */
		int Faction = -1;
		/** Faction holding the officer while Status == Prisoner. */
		int Captor = -1;
		/** City where the officer is located; -1 while marching with an army. */
		int City = -1;
		/** Army id while marching, otherwise -1. */
		int Army = -1;
		int Loyalty = 70;
		int Merit = 0;
		/** Martial sect membership (sect masters and disciples), -1 if none. */
		int Sect = -1;
		/** Indices into FGameState::Techniques. */
		std::vector<int> Techniques;

		int GetStat(EStat Stat) const { return Stats[StatIndex(Stat)]; }
	};

	struct FCity
	{
		std::string Key;
		std::string Name;
		std::string NameZh;
		std::string Description;
		FPoint Position;
		/** 1 = town, 2 = city, 3 = great city (icon size, battle map size). */
		int Size = 2;
		ETerrain Terrain = ETerrain::Plains;
		/** Owning faction or -1 for an independent city. */
		int Owner = -1;
		int Population = 50000;
		int PopulationMax = 150000;
		int Farm = 300;
		int FarmMax = 800;
		int Commerce = 300;
		int CommerceMax = 800;
		int Defense = 300;
		int DefenseMax = 800;
		/** Public order 0..100. */
		int Order = 60;
		int Troops = 5000;
		/** Training 0..100. */
		int Training = 50;
		int Gold = 1000;
		int Food = 10000;
		/** When true the AI governor issues domestic orders for this player city. */
		bool bDelegated = false;
	};

	struct FRoad
	{
		int A = -1;
		int B = -1;
		/** Travel time in days for an infantry army. */
		int Days = 10;
		ERoadKind Kind = ERoadKind::Road;
		/** Optional intermediate points (map units) from A to B for drawing and army placement. */
		std::vector<FPoint> Points;
	};

	struct FFaction
	{
		std::string Key;
		std::string Name;
		std::string NameZh;
		/** Single character painted on the faction's banners, e.g. a clan surname. */
		std::string Glyph;
		/** 0xRRGGBB. */
		uint32_t Color = 0x808080;
		int Ruler = -1;
		int Capital = -1;
		bool bAlive = true;
	};

	struct FRelation
	{
		/** 0..100. Drives diplomacy acceptance. */
		int Trust = 50;
		int AllianceMonths = 0;
		int TruceMonths = 0;
	};

	struct FTechnique
	{
		std::string Key;
		std::string Name;
		std::string NameZh;
		std::string Description;
		/** The duel move this technique enhances; it wins ties against the same move. */
		EDuelMove Kind = EDuelMove::Strike;
		/** Damage multiplier in percent (e.g. 160 = 1.6x). */
		int Power = 150;
		int MinMartial = 60;
	};

	struct FSect
	{
		std::string Key;
		std::string Name;
		std::string NameZh;
		std::string Description;
		int City = -1;
		int Master = -1;
		std::vector<int> Techniques;
		/** Favor 0..100 toward each faction (indexed by faction). */
		std::vector<int> Favor;
	};

	struct FArmyUnit
	{
		int Officer = -1;
		int Troops = 0;
		ETroopType Type = ETroopType::Infantry;
	};

	struct FArmy
	{
		int Id = 0;
		int Faction = -1;
		/** Units[0] is the commander. */
		std::vector<FArmyUnit> Units;
		int Food = 0;
		int Training = 50;
		int Morale = 70;
		/** City the army set out from; retreats go back here (or the nearest own city). */
		int Home = -1;
		int Target = -1;
		EArmyState State = EArmyState::Marching;
		/** Last city passed. */
		int Node = -1;
		/** City being travelled to along Road, or -1 while waiting at Node. */
		int Next = -1;
		int Road = -1;
		/** Distance travelled along Road from Node toward Next, in tenths of a day. */
		int Progress = 0;
		/** Remaining cities after Next. */
		std::vector<int> Route;
		/** Formed during the current planning phase; can still be disbanded for a full refund. */
		bool bNew = true;

		int TotalTroops() const
		{
			int Total = 0;
			for (const FArmyUnit& Unit : Units)
			{
				Total += Unit.Troops;
			}
			return Total;
		}
	};

	struct FOrder
	{
		EOrderType Type = EOrderType::Farm;
		int Officer = -1;
		/** City the order is issued from (pays the cost). */
		int City = -1;
		int TargetCity = -1;
		int TargetOfficer = -1;
		int TargetFaction = -1;
		int TargetSect = -1;
		/** Draft: troops requested. */
		int Amount = 0;
		/** Transport / Gift payload. */
		int Gold = 0;
		int Food = 0;
		int Troops = 0;
		/** Gold deducted when the order was issued; refunded on cancel. */
		int Cost = 0;
	};

	struct FEffect
	{
		EEffectType Type = EEffectType::Message;
		int Amount = 0;
		/** City index, RefContext or RefCapital. */
		int City = RefNone;
		/** Officer index, RefContext or RefRuler. */
		int Officer = RefNone;
		/** Faction index, RefContext or RefPlayer. */
		int Faction = RefNone;
		int Sect = RefNone;
		int Technique = RefNone;
		EStat Stat = EStat::Martial;
		std::string Text;
	};

	struct FEventChoice
	{
		std::string Label;
		/** Gold the context city must hold for the choice to be selectable. */
		int RequireGold = 0;
		std::vector<FEffect> Effects;
	};

	struct FEventCondition
	{
		int MinYear = 0;
		int MaxYear = 99999;
		/** Empty = any month. */
		std::vector<int> Months;
		/** Percent chance per eligible month. */
		int Chance = 100;
		/** Player must own this city. */
		int OwnsCity = -1;
		/** This officer must serve the player. */
		int HasOfficer = -1;
		/** Player must be this faction. */
		int Faction = -1;
		int MinCities = 0;
		int MaxCities = 9999;
	};

	enum class EEventContext : uint8_t
	{
		RandomPlayerCity,
		Capital,
		RandomCity,
		FixedCity
	};

	struct FEventDef
	{
		std::string Key;
		std::string Title;
		/** May contain {city}, {ruler}, {faction}, {officer} placeholders. */
		std::string Text;
		/** Officer index, or -1 for the player's advisor (best strategist). */
		int Speaker = -1;
		/** Illustration asset relative to Content/Data/Art, e.g. "Events/Harvest.png". */
		std::string Image;
		/** World events apply Effects automatically (to any faction's city) and are only logged. */
		bool bWorld = false;
		bool bOnce = true;
		int TimesFired = 0;
		EEventContext Context = EEventContext::RandomPlayerCity;
		int ContextCity = -1;
		FEventCondition Condition;
		std::vector<FEffect> Effects;
		std::vector<FEventChoice> Choices;
	};

	/** An event waiting for the player's decision. Choice effects are already resolved (no Ref* values). */
	struct FPendingEvent
	{
		int Def = -1;
		std::string Title;
		std::string Text;
		std::string Image;
		int Speaker = -1;
		int City = -1;
		int Faction = -1;
		int Officer = -1;
		std::vector<FEventChoice> Choices;
	};

	struct FPendingBattle
	{
		EBattleKind Kind = EBattleKind::Siege;
		/** Attacking army id. */
		int Attacker = 0;
		/** Defending army id for field battles, 0 for sieges. */
		int Defender = 0;
		/** Besieged city for sieges, -1 otherwise. */
		int City = -1;
	};

	struct FLogEntry
	{
		int Year = 0;
		int Month = 0;
		int Day = 0;
		/** Faction the message concerns, -1 for world news. */
		int Faction = -1;
		bool bImportant = false;
		std::string Text;
	};

	// ---------------------------------------------------------------------------------------------
	// Whole-game state. Plain data plus read-only helpers; rules live in FGame (IronGame.h).
	// ---------------------------------------------------------------------------------------------

	struct FGameState
	{
		// Scenario definition.
		std::string ScenarioKey;
		std::string ScenarioName;
		std::string ScenarioDescription;
		int StartYear = 212;
		FMapDef Map;
		std::vector<FTechnique> Techniques;
		std::vector<FFaction> Factions;
		std::vector<FCity> Cities;
		std::vector<FRoad> Roads;
		std::vector<FOfficer> Officers;
		std::vector<FSect> Sects;
		std::vector<FEventDef> Events;

		// Session.
		int Year = 212;
		int Month = 1;
		/** 0 during planning, 1..30 during execution. */
		int Day = 0;
		EPhase Phase = EPhase::Planning;
		EOutcome Outcome = EOutcome::None;
		EDifficulty Difficulty = EDifficulty::Normal;
		int PlayerFaction = -1;
		/** Factions.size() squared, symmetric. Use Relation(). */
		std::vector<FRelation> Relations;
		std::vector<FArmy> Armies;
		int NextArmyId = 1;
		std::vector<FOrder> Orders;
		std::vector<FPendingEvent> PendingEvents;
		/** Officers captured by the player awaiting a decision. */
		std::vector<int> PendingPrisoners;
		std::vector<FPendingBattle> BattleQueue;
		/** True while a day's battles are still being resolved. */
		bool bDayInProgress = false;
		std::vector<FLogEntry> Log;
		FRng Rng;

		// Lookup by key; -1 when missing.
		int FindTechnique(const std::string& Key) const;
		int FindFaction(const std::string& Key) const;
		int FindCity(const std::string& Key) const;
		int FindOfficer(const std::string& Key) const;
		int FindSect(const std::string& Key) const;
		int FindEvent(const std::string& Key) const;

		FRelation& Relation(int FactionA, int FactionB);
		const FRelation& Relation(int FactionA, int FactionB) const;
		bool AreAllied(int FactionA, int FactionB) const;
		bool HaveTruce(int FactionA, int FactionB) const;
		/** Independent cities (-1) are hostile to everyone. A faction is never hostile to itself. */
		bool AreHostile(int FactionA, int FactionB) const;

		/** Serving officers of the city owner stationed in City (not marching). */
		std::vector<int> CityOfficers(int City) const;
		std::vector<int> FreeOfficersInCity(int City) const;
		std::vector<int> PrisonersInCity(int City) const;
		std::vector<int> FactionCities(int Faction) const;
		std::vector<int> FactionOfficers(int Faction) const;
		std::vector<int> Neighbors(int City) const;
		int RoadBetween(int CityA, int CityB) const;
		int SectInCity(int City) const;

		FArmy* FindArmy(int ArmyId);
		const FArmy* FindArmy(int ArmyId) const;
		const FOrder* OfficerOrder(int Officer) const;
		/** Serving, stationed in a city, not marching and without an order this month. */
		bool IsOfficerIdle(int Officer) const;
		bool IsRuler(int Officer) const;
		int OfficerAge(int Officer) const;

		/** Point along a road (including its waypoints), T in 0..1 measured from FromCity. */
		FPoint RoadPoint(int Road, int FromCity, float T) const;
		/** Current map position of an army; FractionalDay (0..1) interpolates the next day's march for animation. */
		FPoint ArmyPosition(const FArmy& Army, float FractionalDay = 0.0f) const;
		/** Length of a road in tenths of a day (Days x 10). */
		int RoadLength(int Road) const;
		/** Tenths of a day an army advances per day: 10, or 13 when at least 60% of its troops are cavalry. */
		int ArmySpeed(const FArmy& Army) const;

		int FactionTotalTroops(int Faction) const;
		int FactionTotalGold(int Faction) const;
		int FactionTotalFood(int Faction) const;

		void AddLog(int Faction, bool bImportant, const std::string& Text);
	};

	/** Parses either a scenario file or a save game (a save is a scenario plus session fields). */
	bool LoadGameState(const FJson& Root, FGameState& OutState, std::string& OutError);
	/** Serializes the complete state; the result can be loaded with LoadGameState. */
	FJson SaveGameState(const FGameState& State);
	/** Cheap scenario header read for menus. */
	struct FScenarioInfo
	{
		std::string Key;
		std::string Name;
		std::string Description;
		int StartYear = 0;
		struct FFactionInfo
		{
			std::string Key;
			std::string Name;
			std::string NameZh;
			std::string Glyph;
			uint32_t Color = 0;
			std::string RulerName;
			std::string RulerPortrait;
			int Cities = 0;
			int Officers = 0;
			int Troops = 0;
		};
		std::vector<FFactionInfo> Factions;
	};
	bool ReadScenarioInfo(const FJson& Root, FScenarioInfo& OutInfo);

	std::string ColorToHex(uint32_t Color);
	uint32_t ColorFromHex(const std::string& Text, uint32_t Default);
}
