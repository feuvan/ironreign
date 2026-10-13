// Headless AI campaign on the real scenario: every faction is played by the AI (the player's cities are delegated and
// player battles are auto-resolved) for 20 years. Checks state invariants every month and that the map changes hands.

#include "IronTest.h"

#include "Sim/IronGame.h"

#include <algorithm>
#include <cstdio>
#include <string>
#include <vector>

using namespace IronSim;

namespace CampaignTests
{
	struct FStats
	{
		int Months = 0;
		int Conquests = 0;
		int ConquestsAfterYear5 = 0;
		int FirstElimination = -1;
		int Eliminated = 0;
		int StarvingCityMonths = 0;
		int BrokeCityMonths = 0;
		int CityMonths = 0;
		int Battles = 0;
		int PlayerBattles = 0;
		int MaxArmies = 0;
		int PlayerDefeatMonth = -1;
		std::vector<int> Owners;
	};

	bool LoadScenario(FJson& OutRoot)
	{
		std::string Text;
		if (!IronTest::ReadFile(IronTest::DataDir() + "/Scenarios/BrokenMandate.json", Text))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "missing BrokenMandate.json");
			return false;
		}
		std::string Error;
		if (!FJson::Parse(Text, OutRoot, Error))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "parse: " + Error);
			return false;
		}
		if (OutRoot.Get("officers").Size() == 0)
		{
			std::printf("  NOTE: BrokenMandate.json has no officers yet; campaign test skipped.\n");
			return false;
		}
		return true;
	}

	/** Returns an empty string when every invariant holds, otherwise a description of the first violation. */
	std::string CheckInvariants(const FGameState& State)
	{
		const int CityCount = static_cast<int>(State.Cities.size());
		for (const FCity& City : State.Cities)
		{
			if (City.Gold < 0 || City.Food < 0 || City.Troops < 0)
			{
				return "negative resources in " + City.Key;
			}
			if (City.Order < 0 || City.Order > 100 || City.Training < 0 || City.Training > 100 || City.Population < 0)
			{
				return "city stat out of range in " + City.Key;
			}
			if (City.Owner >= 0 && !State.Factions[static_cast<size_t>(City.Owner)].bAlive)
			{
				return City.Key + " is owned by a dead faction";
			}
		}
		std::vector<int> Seen;
		for (const FArmy& Army : State.Armies)
		{
			if (Army.Units.empty() || Army.Food < 0 || Army.TotalTroops() < 0)
			{
				return "broken army " + std::to_string(Army.Id);
			}
			if (Army.Faction < 0 || !State.Factions[static_cast<size_t>(Army.Faction)].bAlive)
			{
				return "army of a dead faction " + std::to_string(Army.Id);
			}
			if (Army.Node < 0 || Army.Node >= CityCount || Army.Road < 0 || Army.Next < 0 || Army.Progress < 0 || Army.Progress > State.RoadLength(Army.Road))
			{
				return "army off the road " + std::to_string(Army.Id);
			}
			for (const FArmyUnit& Unit : Army.Units)
			{
				if (Unit.Officer < 0 || Unit.Officer >= static_cast<int>(State.Officers.size()) || Unit.Troops < 0)
				{
					return "bad unit in army " + std::to_string(Army.Id);
				}
				const FOfficer& Officer = State.Officers[static_cast<size_t>(Unit.Officer)];
				if (Officer.Army != Army.Id || Officer.Status != EOfficerStatus::Serving || Officer.Faction != Army.Faction || Officer.City != -1)
				{
					return Officer.Key + " is listed in army " + std::to_string(Army.Id) + " but is not marching with it";
				}
				if (std::find(Seen.begin(), Seen.end(), Unit.Officer) != Seen.end())
				{
					return Officer.Key + " appears in two army units";
				}
				Seen.push_back(Unit.Officer);
			}
		}
		for (const FOfficer& Officer : State.Officers)
		{
			switch (Officer.Status)
			{
			case EOfficerStatus::Serving:
			{
				if (Officer.Faction < 0 || !State.Factions[static_cast<size_t>(Officer.Faction)].bAlive)
				{
					return Officer.Key + " serves a dead faction";
				}
				const bool bInCity = Officer.City >= 0 && Officer.Army < 0 && State.Cities[static_cast<size_t>(Officer.City)].Owner == Officer.Faction;
				const FArmy* Army = Officer.Army >= 0 ? State.FindArmy(Officer.Army) : nullptr;
				bool bInArmy = Officer.City < 0 && Army && Army->Faction == Officer.Faction;
				if (bInArmy)
				{
					bool bListed = false;
					for (const FArmyUnit& Unit : Army->Units)
					{
						bListed = bListed || State.Officers[static_cast<size_t>(Unit.Officer)].Key == Officer.Key;
					}
					bInArmy = bListed;
				}
				if (bInCity == bInArmy)
				{
					return Officer.Key + " is neither in an own city nor in an army (city " + std::to_string(Officer.City) + ", army " + std::to_string(Officer.Army) + ")";
				}
				if (Officer.Loyalty < 0 || Officer.Loyalty > 100)
				{
					return Officer.Key + " has loyalty out of range";
				}
				break;
			}
			case EOfficerStatus::Prisoner:
				if (Officer.Captor < 0 || !State.Factions[static_cast<size_t>(Officer.Captor)].bAlive || Officer.City < 0
					|| State.Cities[static_cast<size_t>(Officer.City)].Owner != Officer.Captor || Officer.Army >= 0)
				{
					return Officer.Key + " is held in an invalid prison";
				}
				break;
			case EOfficerStatus::Free:
			case EOfficerStatus::Hidden:
			case EOfficerStatus::Unborn:
				if (Officer.City < 0 || Officer.City >= CityCount || Officer.Army >= 0 || Officer.Faction >= 0)
				{
					return Officer.Key + " (unaffiliated) has an invalid location";
				}
				break;
			case EOfficerStatus::Dead:
				if (Officer.Army >= 0)
				{
					return Officer.Key + " is dead but marching";
				}
				break;
			}
			for (int Stat = 0; Stat < StatCount; ++Stat)
			{
				if (Officer.Stats[Stat] < 1 || Officer.Stats[Stat] > MaxStatValue || Officer.StatExp[Stat] < 0 || Officer.StatExp[Stat] >= 100)
				{
					return Officer.Key + " has a stat out of range";
				}
			}
		}
		const int FactionCount = static_cast<int>(State.Factions.size());
		for (int Faction = 0; Faction < FactionCount; ++Faction)
		{
			const FFaction& Data = State.Factions[static_cast<size_t>(Faction)];
			bool bHasCity = false;
			for (const FCity& City : State.Cities)
			{
				bHasCity = bHasCity || City.Owner == Faction;
			}
			bool bHasArmy = false;
			for (const FArmy& Army : State.Armies)
			{
				bHasArmy = bHasArmy || Army.Faction == Faction;
			}
			if (Data.bAlive && !bHasCity && !bHasArmy)
			{
				return Data.Key + " has no cities or armies but is alive";
			}
			if (Data.bAlive)
			{
				if (Data.Ruler < 0 || State.Officers[static_cast<size_t>(Data.Ruler)].Status != EOfficerStatus::Serving || State.Officers[static_cast<size_t>(Data.Ruler)].Faction != Faction)
				{
					return Data.Key + " has no serving ruler";
				}
				if (bHasCity && (Data.Capital < 0 || State.Cities[static_cast<size_t>(Data.Capital)].Owner != Faction))
				{
					return Data.Key + " has a capital it does not own";
				}
			}
			for (int Other = 0; Other < FactionCount; ++Other)
			{
				const FRelation& Forward = State.Relation(Faction, Other);
				const FRelation& Backward = State.Relation(Other, Faction);
				if (Forward.Trust != Backward.Trust || Forward.AllianceMonths != Backward.AllianceMonths || Forward.TruceMonths != Backward.TruceMonths)
				{
					return "asymmetric relation " + Data.Key;
				}
				if (Forward.Trust < 0 || Forward.Trust > 100 || Forward.AllianceMonths < 0 || Forward.TruceMonths < 0)
				{
					return "relation out of range " + Data.Key;
				}
			}
		}
		for (const int Prisoner : State.PendingPrisoners)
		{
			if (State.Officers[static_cast<size_t>(Prisoner)].Status != EOfficerStatus::Prisoner)
			{
				return "pending prisoner who is not a prisoner";
			}
		}
		return std::string();
	}

	void PrintSummary(const FGame& Game, const FStats& Stats)
	{
		const FGameState& State = Game.State;
		std::string Line = "  Year " + std::to_string(State.Year) + ":";
		for (size_t Faction = 0; Faction < State.Factions.size(); ++Faction)
		{
			const FFaction& Data = State.Factions[Faction];
			const int Cities = Game.CityCount(static_cast<int>(Faction));
			Line += " " + Data.Key + " " + (Data.bAlive ? std::to_string(Cities) + "c/" + std::to_string(State.FactionTotalTroops(static_cast<int>(Faction)) / 1000) + "k" : std::string("dead"));
		}
		int Independent = 0;
		for (const FCity& City : State.Cities)
		{
			Independent += City.Owner < 0 ? 1 : 0;
		}
		Line += " | indep " + std::to_string(Independent) + " | conquests " + std::to_string(Stats.Conquests) + " | armies " + std::to_string(State.Armies.size());
		Line += " | starving " + std::to_string(Stats.StarvingCityMonths) + " broke " + std::to_string(Stats.BrokeCityMonths);
		std::printf("%s\n", Line.c_str());
	}

	/** Answers events and prisoners like a (random) player would. */
	void AnswerPrompts(FGame& Game, FRng& Choices)
	{
		for (int Guard = 0; Guard < 32 && Game.CurrentEvent(); ++Guard)
		{
			std::vector<int> Options;
			for (int Index = 0; Index < static_cast<int>(Game.CurrentEvent()->Choices.size()); ++Index)
			{
				if (Game.CanChoose(Index))
				{
					Options.push_back(Index);
				}
			}
			Game.ChooseEventOption(Options.empty() ? 0 : Options[static_cast<size_t>(Choices.Range(0, static_cast<int>(Options.size()) - 1))]);
		}
		const std::vector<int> Prisoners = Game.State.PendingPrisoners;
		for (const int Prisoner : Prisoners)
		{
			std::string Message;
			static const EPrisonerDecision Decisions[] = {EPrisonerDecision::Recruit, EPrisonerDecision::Recruit, EPrisonerDecision::Release, EPrisonerDecision::Imprison};
			Game.DecidePrisoner(Prisoner, Decisions[Choices.Range(0, 3)], Message);
		}
	}

	void CountCityHealth(const FGameState& State, FStats& Stats)
	{
		for (const FCity& City : State.Cities)
		{
			if (City.Owner < 0)
			{
				continue;
			}
			++Stats.CityMonths;
			Stats.StarvingCityMonths += (City.Food == 0 && City.Troops > 0) ? 1 : 0;
			Stats.BrokeCityMonths += City.Gold == 0 ? 1 : 0;
		}
	}

	/** Steps until the month ends or the game is over, auto-resolving player battles. Returns Idle if it never ends. */
	EStepResult FinishMonth(FGame& Game, FStats& Stats)
	{
		for (int Guard = 0; Guard < 2000; ++Guard)
		{
			const EStepResult Result = Game.Step();
			if (Result == EStepResult::PlayerBattle)
			{
				++Stats.PlayerBattles;
				Game.AutoResolvePlayerBattle();
			}
			Stats.MaxArmies = std::max(Stats.MaxArmies, static_cast<int>(Game.State.Armies.size()));
			if (Result == EStepResult::MonthEnded || Result == EStepResult::GameOver)
			{
				return Result;
			}
		}
		return EStepResult::Idle;
	}

	/** Plays Years years; returns false if the run had to stop because of an invariant failure. */
	bool RunCampaign(FGame& Game, int Years, uint64_t ChoiceSeed, FStats& Stats, bool bVerbose = true)
	{
		FGameState& State = Game.State;
		FRng Choices(ChoiceSeed);
		Stats.Owners.clear();
		for (const FCity& City : State.Cities)
		{
			Stats.Owners.push_back(City.Owner);
		}
		const int StartYear = State.Year;
		const int EndYear = StartYear + Years;
		int ReportedYear = State.Year;
		while (State.Year < EndYear)
		{
			if (State.Phase == EPhase::GameOver)
			{
				if (State.Outcome != EOutcome::Defeat)
				{
					break;
				}
				// The player's faction fell: keep watching the AI-only world (spectator rules) until the end.
				if (bVerbose)
				{
					PrintSummary(Game, Stats);
					std::printf("  The player's faction fell in year %d after %d months; the campaign continues without a player.\n", State.Year, Stats.Months);
				}
				Stats.PlayerDefeatMonth = Stats.Months;
				State.PlayerFaction = -1;
				State.Outcome = EOutcome::None;
				State.Phase = EPhase::Execution;
				State.bDayInProgress = false;
				const EStepResult Resume = FinishMonth(Game, Stats);
				if (Resume == EStepResult::GameOver || Resume == EStepResult::Idle)
				{
					break;
				}
				continue;
			}
			if (State.PlayerFaction >= 0)
			{
				for (int City = 0; City < static_cast<int>(State.Cities.size()); ++City)
				{
					if (Game.IsPlayerCity(City) && !State.Cities[static_cast<size_t>(City)].bDelegated)
					{
						Game.SetDelegated(City, true);
					}
				}
			}
			AnswerPrompts(Game, Choices);
			Game.EndPlanning();
			if (FinishMonth(Game, Stats) == EStepResult::Idle)
			{
				IronTest::ReportFailure(__FILE__, __LINE__, "the month never ended");
				return false;
			}
			++Stats.Months;
			const std::string Problem = CheckInvariants(State);
			if (!Problem.empty())
			{
				IronTest::ReportFailure(__FILE__, __LINE__, "Year " + std::to_string(State.Year) + " month " + std::to_string(State.Month) + ": " + Problem);
				return false;
			}
			for (size_t City = 0; City < State.Cities.size(); ++City)
			{
				if (State.Cities[City].Owner != Stats.Owners[City])
				{
					if (State.Cities[City].Owner >= 0)
					{
						++Stats.Conquests;
						Stats.ConquestsAfterYear5 += State.Year >= StartYear + 5 ? 1 : 0;
					}
					Stats.Owners[City] = State.Cities[City].Owner;
				}
			}
			int Dead = 0;
			for (const FFaction& Faction : State.Factions)
			{
				Dead += Faction.bAlive ? 0 : 1;
			}
			if (Dead > Stats.Eliminated)
			{
				if (Stats.FirstElimination < 0)
				{
					Stats.FirstElimination = Stats.Months;
				}
				Stats.Eliminated = Dead;
			}
			CountCityHealth(State, Stats);
			if (State.Year != ReportedYear)
			{
				ReportedYear = State.Year;
				if (bVerbose)
				{
					PrintSummary(Game, Stats);
				}
			}
		}
		if (!bVerbose)
		{
			return true;
		}
		if (State.Phase == EPhase::GameOver)
		{
			PrintSummary(Game, Stats);
			std::printf("  Game over in year %d (%s).\n", State.Year, EnumName(State.Outcome));
		}
		std::printf("  %d months, %d conquests (%d after year 5), %d factions eliminated (first after %d months), %d player battles, max %d armies\n",
			Stats.Months, Stats.Conquests, Stats.ConquestsAfterYear5, Stats.Eliminated, Stats.FirstElimination, Stats.PlayerBattles, Stats.MaxArmies);
		std::printf("  starving city-months %d, broke city-months %d of %d\n", Stats.StarvingCityMonths, Stats.BrokeCityMonths, Stats.CityMonths);
		return true;
	}

	void ExpectLively(const FStats& Stats, bool bCompleted)
	{
		IRON_EXPECT_MSG(Stats.Conquests >= 10, "the map should change hands: " + std::to_string(Stats.Conquests) + " conquests");
		IRON_EXPECT_MSG(Stats.FirstElimination < 0 || Stats.FirstElimination > 24, "no faction should fall in the first two years (first after " + std::to_string(Stats.FirstElimination) + " months)");
		IRON_EXPECT_MSG(Stats.PlayerDefeatMonth < 0 || Stats.PlayerDefeatMonth > 24, "the player's faction should not fall in the first two years");
		if (bCompleted)
		{
			IRON_EXPECT_MSG(Stats.Eliminated >= 1, "at least one faction should be eliminated within 20 years");
			IRON_EXPECT_MSG(Stats.ConquestsAfterYear5 >= 2, "the war should not stall after year 5");
		}
		IRON_EXPECT_MSG(Stats.StarvingCityMonths * 100 <= Stats.CityMonths * 3, "the AI should not starve its cities");
		IRON_EXPECT_MSG(Stats.BrokeCityMonths * 100 <= Stats.CityMonths * 5, "the AI should not go broke");
	}
}

IRON_TEST(CampaignBrokenMandateTwentyYears)
{
	FJson Root;
	if (!CampaignTests::LoadScenario(Root))
	{
		return;
	}
	FGame Game;
	std::string Error;
	// A representative seed (see CampaignBrokenMandateSweep for the spread across seeds).
	if (!Game.NewGame(Root, 0, EDifficulty::Normal, 16554ull, Error))
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "NewGame: " + Error);
		return;
	}
	IRON_EXPECT_MSG(CampaignTests::CheckInvariants(Game.State).empty(), CampaignTests::CheckInvariants(Game.State));
	CampaignTests::FStats Stats;
	std::printf("  Player faction %s (all cities delegated), Normal difficulty\n", Game.State.Factions[0].Key.c_str());
	if (!CampaignTests::RunCampaign(Game, 20, 513181ull, Stats))
	{
		return;
	}
	const bool bCompleted = Game.State.Phase != EPhase::GameOver;
	IRON_EXPECT_MSG(Stats.Months >= 60, "the campaign should last at least five years");
	IRON_EXPECT_MSG(Stats.PlayerBattles > 0, "the player's delegated armies should fight");
	CampaignTests::ExpectLively(Stats, bCompleted);

	// The finished campaign still saves and loads.
	FGame Loaded;
	IRON_EXPECT_MSG(Loaded.LoadGame(Game.SaveGame(), Error), Error);
	IRON_EXPECT(Loaded.SaveGame().Write(false) == Game.SaveGame().Write(false));
}

IRON_TEST(CampaignBrokenMandateSpectatorHard)
{
	FJson Root;
	if (!CampaignTests::LoadScenario(Root))
	{
		return;
	}
	FGame Game;
	std::string Error;
	if (!Game.NewGame(Root, -1, EDifficulty::Hard, 20260413ull, Error))
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "NewGame: " + Error);
		return;
	}
	CampaignTests::FStats Stats;
	std::printf("  Spectator game (no player), Hard difficulty\n");
	if (!CampaignTests::RunCampaign(Game, 20, 7, Stats))
	{
		return;
	}
	CampaignTests::ExpectLively(Stats, Game.State.Phase != EPhase::GameOver);
}

IRON_TEST(CampaignBrokenMandateSweep)
{
	// Several Normal campaigns with the player's faction delegated: one line each, so balance can be compared across seeds.
	FJson Root;
	if (!CampaignTests::LoadScenario(Root))
	{
		return;
	}
	for (int Run = 1; Run <= 6; ++Run)
	{
		const uint64_t Seed = 1000 + static_cast<uint64_t>(Run) * 7777;
		FGame Game;
		std::string Error;
		if (!Game.NewGame(Root, 0, EDifficulty::Normal, Seed, Error))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "NewGame: " + Error);
			return;
		}
		CampaignTests::FStats Stats;
		if (!CampaignTests::RunCampaign(Game, 20, Seed * 31 + 7, Stats, false))
		{
			return;
		}
		int Alive = 0;
		int Largest = 0;
		for (int Faction = 0; Faction < static_cast<int>(Game.State.Factions.size()); ++Faction)
		{
			Alive += Game.State.Factions[static_cast<size_t>(Faction)].bAlive ? 1 : 0;
			Largest = std::max(Largest, Game.CityCount(Faction));
		}
		std::printf("  seed %5llu: %3d months, %2d conquests (%2d after year 5), first elimination after %3d months, %d factions left (largest %2d cities), player fell after %3d months, starving %d, broke %d of %d city-months\n",
			static_cast<unsigned long long>(Seed), Stats.Months, Stats.Conquests, Stats.ConquestsAfterYear5, Stats.FirstElimination, Alive, Largest, Stats.PlayerDefeatMonth,
			Stats.StarvingCityMonths, Stats.BrokeCityMonths, Stats.CityMonths);
		IRON_EXPECT_MSG(Stats.Conquests >= 10, "the map should change hands (seed " + std::to_string(Seed) + ")");
		IRON_EXPECT_MSG(Stats.FirstElimination < 0 || Stats.FirstElimination > 24, "no faction should fall in the first two years (seed " + std::to_string(Seed) + ")");
		IRON_EXPECT_MSG(Stats.StarvingCityMonths * 100 <= Stats.CityMonths * 3, "the AI should not starve its cities (seed " + std::to_string(Seed) + ")");
		IRON_EXPECT_MSG(Stats.BrokeCityMonths * 100 <= Stats.CityMonths * 5, "the AI should not go broke (seed " + std::to_string(Seed) + ")");
	}
}
