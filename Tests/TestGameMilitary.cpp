// Unit tests for armies, marching, field battles, sieges, prisoners, succession, victory/defeat and save/load mid-game.

#include "IronTest.h"

#include "Sim/IronGame.h"

#include <algorithm>
#include <string>

using namespace IronSim;

namespace GameTestFixture
{
	FJson ScenarioJson();
	bool StartGame(FGame& Game, uint64_t Seed);
	bool StartQuietGame(FGame& Game, uint64_t Seed);
	int City(const FGame& Game, const char* Key);
	int Officer(const FGame& Game, const char* Key);
	int Faction(const FGame& Game, const char* Key);
	EStepResult FinishMonth(FGame& Game);
	void ClearPlanningPrompts(FGame& Game);
	int PlaceArmy(FGame& Game, int Faction, const std::vector<int>& Officers, int Troops, int From, int Target, int Progress);
}

namespace GameMilitaryTests
{
	/** A finished battle where every unit keeps Percent of its troops; Statuses override per officer. */
	FBattleResult MakeResult(const FBattleSetup& Setup, int Winner, int AttackerPercent, int DefenderPercent, const std::vector<std::pair<int, EUnitStatus>>& Statuses = {})
	{
		FBattleResult Result;
		Result.bFinished = true;
		Result.Winner = Winner;
		Result.Days = 3;
		for (int Side = 0; Side < 2; ++Side)
		{
			for (const FBattleUnitSetup& Unit : Setup.Sides[Side].Units)
			{
				FUnitOutcome Outcome;
				Outcome.Side = Side;
				Outcome.Officer = Unit.Officer;
				Outcome.Troops = Unit.Troops * (Side == 0 ? AttackerPercent : DefenderPercent) / 100;
				Outcome.Status = Side == Winner ? EUnitStatus::Active : EUnitStatus::Routed;
				Outcome.DamageDealt = 1500;
				for (const std::pair<int, EUnitStatus>& Override : Statuses)
				{
					if (Override.first == Unit.Officer && Unit.Officer >= 0)
					{
						Outcome.Status = Override.second;
						if (Override.second == EUnitStatus::Captured || Override.second == EUnitStatus::Killed)
						{
							Outcome.Troops = 0;
						}
					}
				}
				Result.Units.push_back(Outcome);
			}
		}
		return Result;
	}

	/** Steps until a player battle is pending or the month ends. */
	EStepResult StepToBattle(FGame& Game)
	{
		EStepResult Result = EStepResult::Idle;
		for (int Guard = 0; Guard < 40; ++Guard)
		{
			Result = Game.Step();
			if (Result != EStepResult::DayAdvanced)
			{
				return Result;
			}
		}
		return Result;
	}

	int TotalUnitTroops(const FBattleSideSetup& Side)
	{
		int Total = 0;
		for (const FBattleUnitSetup& Unit : Side.Units)
		{
			Total += Unit.Troops;
		}
		return Total;
	}

	bool LogContains(const FGame& Game, const std::string& Text)
	{
		for (const FLogEntry& Entry : Game.State.Log)
		{
			if (Entry.Text.find(Text) != std::string::npos)
			{
				return true;
			}
		}
		return false;
	}
}

IRON_TEST(GameArmyFormationValidatesSplitsAndDisbands)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 21))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int Town = GameTestFixture::City(Game, "free_town");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	const int GreenA = GameTestFixture::City(Game, "green_a");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int Admin = GameTestFixture::Officer(Game, "r_admin");

	IRON_EXPECT_EQ(Game.MaxUnitTroops(General), 2000 + 75 * 60);
	IRON_EXPECT_EQ(Game.ArmyDailyFood(8000), 27);
	const std::vector<int> Targets = Game.MarchTargets(RedA);
	IRON_EXPECT(std::find(Targets.begin(), Targets.end(), RedB) != Targets.end());
	IRON_EXPECT(std::find(Targets.begin(), Targets.end(), Town) != Targets.end());
	IRON_EXPECT(std::find(Targets.begin(), Targets.end(), BlueA) != Targets.end());
	IRON_EXPECT(std::find(Targets.begin(), Targets.end(), GreenA) == Targets.end());
	IRON_EXPECT_EQ(Game.MarchDays(RedA, Town), 6);
	IRON_EXPECT_EQ(Game.MarchDays(RedA, BlueA), 13);
	IRON_EXPECT_EQ(Game.MarchDays(RedA, GreenA), -1);

	FArmyPlan Plan;
	Plan.City = RedA;
	Plan.Officers = {General, Admin};
	Plan.Troops = 8000;
	Plan.Food = 3000;
	Plan.Target = Town;
	const FOrderCheck Check = Game.CheckArmy(Plan);
	IRON_EXPECT_MSG(Check.bAllowed, Check.Reason);
	IRON_EXPECT_MSG(Check.Preview == "8000 troops reach Freeport in 6 days, with food for 111 days.", Check.Preview);

	FArmyPlan Bad = Plan;
	Bad.Officers.clear();
	IRON_EXPECT(Game.CheckArmy(Bad).Reason == "Choose a commander.");
	Bad = Plan;
	Bad.Officers = {General, General};
	IRON_EXPECT(Game.CheckArmy(Bad).Reason == "Red General was chosen twice.");
	Bad = Plan;
	Bad.Troops = 12000;
	IRON_EXPECT_MSG(Game.CheckArmy(Bad).Reason == "Redhold has only 10000 troops.", Game.CheckArmy(Bad).Reason);
	Bad = Plan;
	Bad.Officers = {Admin};
	Bad.Troops = 5000;
	IRON_EXPECT_MSG(Game.CheckArmy(Bad).Reason == "These officers can lead at most 4400 troops.", Game.CheckArmy(Bad).Reason);
	Bad = Plan;
	Bad.Food = 10;
	IRON_EXPECT_MSG(Game.CheckArmy(Bad).Reason == "The army needs at least 162 food to reach Freeport.", Game.CheckArmy(Bad).Reason);
	Bad = Plan;
	Bad.Target = GreenA;
	IRON_EXPECT_MSG(Game.CheckArmy(Bad).Reason == "Greenvale cannot be reached through your territory.", Game.CheckArmy(Bad).Reason);
	Bad = Plan;
	Bad.Target = RedA;
	IRON_EXPECT(!Game.CheckArmy(Bad).bAllowed);
	Bad = Plan;
	Bad.City = BlueA;
	IRON_EXPECT(!Game.CheckArmy(Bad).bAllowed);

	std::string Error;
	IRON_EXPECT_MSG(Game.FormArmy(Plan, Error), Error);
	IRON_EXPECT_EQ(State.Armies.size(), static_cast<size_t>(1));
	const FArmy Army = State.Armies.front();
	IRON_EXPECT_EQ(Army.TotalTroops(), 8000);
	IRON_EXPECT_EQ(Army.Units.size(), static_cast<size_t>(2));
	IRON_EXPECT_EQ(Army.Units[0].Officer, General);
	IRON_EXPECT(Army.Units[0].Troops <= Game.MaxUnitTroops(General));
	IRON_EXPECT(Army.Units[1].Troops <= Game.MaxUnitTroops(Admin));
	IRON_EXPECT(Army.Units[1].Type == ETroopType::Archer);
	IRON_EXPECT(Army.bNew);
	IRON_EXPECT_EQ(Army.Next, Town);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Troops, 2000);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Food, 27000);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].Army, Army.Id);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].City, -1);
	IRON_EXPECT_EQ(Game.IdleOfficers(RedA).size(), static_cast<size_t>(1));
	IRON_EXPECT_EQ(Game.OfficerUpkeep(RedA), 30);

	IRON_EXPECT(Game.DisbandArmy(Army.Id));
	IRON_EXPECT(State.Armies.empty());
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Troops, 10000);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Food, 30000);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].City, RedA);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].Army, -1);

	IRON_EXPECT_MSG(Game.FormArmy(Plan, Error), Error);
	const int Id = State.Armies.front().Id;
	Game.EndPlanning();
	IRON_EXPECT(!State.Armies.front().bNew);
	IRON_EXPECT(!Game.DisbandArmy(Id));
}

IRON_TEST(GameArmyMarchesHomeAndMerges)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 22))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	FArmyPlan Plan;
	Plan.City = RedA;
	Plan.Officers = {General};
	Plan.Troops = 3000;
	Plan.Food = 500;
	Plan.Target = RedB;
	std::string Error;
	IRON_EXPECT_MSG(Game.FormArmy(Plan, Error), Error);
	const int Before = State.Cities[static_cast<size_t>(RedB)].Troops;
	const int FoodBefore = State.Cities[static_cast<size_t>(RedB)].Food;
	Game.EndPlanning();
	int Days = 0;
	while (!State.Armies.empty() && Days < 20)
	{
		IRON_EXPECT(Game.Step() == EStepResult::DayAdvanced);
		++Days;
		if (!State.Armies.empty())
		{
			const FPoint Position = State.ArmyPosition(State.Armies.front(), 0.5f);
			IRON_EXPECT(Position.Y >= 100.0f && Position.Y <= 300.0f);
		}
	}
	IRON_EXPECT_EQ(Days, 5);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedB)].Troops, Before + 3000);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedB)].Food, FoodBefore + 500 - 5 * Game.ArmyDailyFood(3000));
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].City, RedB);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].Army, -1);
	IRON_EXPECT(GameMilitaryTests::LogContains(Game, "has arrived in Redford"));
}

IRON_TEST(GameSiegeOfIndependentTownPausesForThePlayer)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 23))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int Town = GameTestFixture::City(Game, "free_town");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int Admin = GameTestFixture::Officer(Game, "r_admin");
	FArmyPlan Plan;
	Plan.City = RedA;
	Plan.Officers = {General, Admin};
	Plan.Troops = 8000;
	Plan.Food = 3000;
	Plan.Target = Town;
	std::string Error;
	IRON_EXPECT_MSG(Game.FormArmy(Plan, Error), Error);
	Game.EndPlanning();
	IRON_EXPECT(GameMilitaryTests::StepToBattle(Game) == EStepResult::PlayerBattle);
	IRON_EXPECT_EQ(State.Day, 6);
	IRON_EXPECT_MSG(Game.DateText() == "Year 212, Month 1, Day 6", Game.DateText());
	const FPendingBattle* Pending = Game.PendingPlayerBattle();
	IRON_EXPECT(Pending != nullptr);
	if (!Pending)
	{
		return;
	}
	IRON_EXPECT(Pending->Kind == EBattleKind::Siege);
	IRON_EXPECT_EQ(Pending->City, Town);
	IRON_EXPECT(Game.IsPlayerAttacker(*Pending));
	// Asking again keeps the same battle waiting.
	IRON_EXPECT(Game.Step() == EStepResult::PlayerBattle);

	const FBattleSetup Setup = Game.MakeBattleSetup(*Pending);
	IRON_EXPECT(Setup.Kind == EBattleKind::Siege);
	IRON_EXPECT(Setup.Terrain == ETerrain::Coast);
	IRON_EXPECT_MSG(Setup.Location == "Siege of Freeport", Setup.Location);
	IRON_EXPECT_EQ(Setup.CitySize, 1);
	IRON_EXPECT_EQ(Setup.GateHp, 300 + 200 * 2);
	IRON_EXPECT_EQ(Setup.WallBonus, 15 + 200 / 30);
	IRON_EXPECT(Setup.Sides[0].bPlayer);
	IRON_EXPECT(!Setup.Sides[1].bPlayer);
	IRON_EXPECT_EQ(Setup.Sides[0].Faction, 0);
	IRON_EXPECT_EQ(Setup.Sides[1].Faction, -1);
	IRON_EXPECT(Setup.Sides[0].Name == "Red Banner");
	IRON_EXPECT(Setup.Sides[1].Name == "Independents");
	IRON_EXPECT_EQ(Setup.Sides[0].Units.size(), static_cast<size_t>(2));
	IRON_EXPECT(Setup.Sides[0].Units[0].Name == "Red General");
	IRON_EXPECT_EQ(Setup.Sides[0].Units[0].Stats[StatIndex(EStat::Command)], 75);
	IRON_EXPECT_EQ(GameMilitaryTests::TotalUnitTroops(Setup.Sides[0]), 8000);
	IRON_EXPECT_EQ(Setup.Sides[1].Units.size(), static_cast<size_t>(1));
	IRON_EXPECT(Setup.Sides[1].Units[0].Officer == -1);
	IRON_EXPECT(Setup.Sides[1].Units[0].Name == "Garrison Captain");
	IRON_EXPECT_EQ(Setup.Sides[1].Units[0].Stats[0], 40);
	IRON_EXPECT_EQ(GameMilitaryTests::TotalUnitTroops(Setup.Sides[1]), 2000);
	IRON_EXPECT(Setup.Sides[0].FoodDays > 50);
	IRON_EXPECT_EQ(Setup.Techniques.size(), State.Techniques.size());
	IRON_EXPECT(Setup.Seed == Game.MakeBattleSetup(*Pending).Seed);

	const int Gold = State.Cities[static_cast<size_t>(Town)].Gold;
	Game.ResolvePlayerBattle(GameMilitaryTests::MakeResult(Setup, 0, 90, 50));
	IRON_EXPECT(Game.PendingPlayerBattle() == nullptr);
	const FCity& Taken = State.Cities[static_cast<size_t>(Town)];
	IRON_EXPECT_EQ(Taken.Owner, 0);
	IRON_EXPECT_EQ(Taken.Gold, Gold / 2);
	const int Survivors = Setup.Sides[0].Units[0].Troops * 90 / 100 + Setup.Sides[0].Units[1].Troops * 90 / 100;
	IRON_EXPECT_EQ(Taken.Troops, Survivors + 1000 * 30 / 100);
	IRON_EXPECT(State.Armies.empty());
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].City, Town);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(Admin)].City, Town);
	IRON_EXPECT(State.Officers[static_cast<size_t>(General)].StatExp[StatIndex(EStat::Command)] > 0);
	IRON_EXPECT(GameMilitaryTests::LogContains(Game, "Freeport has fallen to the Red Banner!"));
	IRON_EXPECT_EQ(Game.CityCount(0), 3);
	IRON_EXPECT(Game.Step() == EStepResult::DayAdvanced);
}

IRON_TEST(GameRepelledSiegeRetreatsAndEmptyCityFalls)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 24))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	const int Town = GameTestFixture::City(Game, "free_town");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int RedA = GameTestFixture::City(Game, "red_a");
	State.Cities[static_cast<size_t>(RedB)].Troops -= 3000;
	const int Id = GameTestFixture::PlaceArmy(Game, 0, {Captain}, 3000, RedB, BlueA, 70);
	Game.EndPlanning();
	IRON_EXPECT(GameMilitaryTests::StepToBattle(Game) == EStepResult::PlayerBattle);
	const FPendingBattle* Pending = Game.PendingPlayerBattle();
	if (!Pending)
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "expected a siege");
		return;
	}
	const FBattleSetup Setup = Game.MakeBattleSetup(*Pending);
	// Defenders: officers by Command (b_gen 82, b_ruler 70) split the garrison.
	IRON_EXPECT_EQ(Setup.Sides[1].Units.size(), static_cast<size_t>(2));
	IRON_EXPECT_EQ(Setup.Sides[1].Units[0].Officer, GameTestFixture::Officer(Game, "b_gen"));
	IRON_EXPECT_EQ(GameMilitaryTests::TotalUnitTroops(Setup.Sides[1]), 8000);
	IRON_EXPECT(Setup.Terrain == ETerrain::Hills);
	Game.ResolvePlayerBattle(GameMilitaryTests::MakeResult(Setup, 1, 40, 80));
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(BlueA)].Owner, 1);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(BlueA)].Troops, 6400);
	const FArmy* Army = State.FindArmy(Id);
	IRON_EXPECT(Army != nullptr);
	if (Army)
	{
		IRON_EXPECT(Army->State == EArmyState::Returning);
		IRON_EXPECT_EQ(Army->Next, RedB);
		IRON_EXPECT_EQ(Army->TotalTroops(), 1200);
	}
	const int Before = State.Cities[static_cast<size_t>(RedB)].Troops;
	for (int Day = 0; Day < 12 && State.FindArmy(Id); ++Day)
	{
		Game.Step();
	}
	IRON_EXPECT(State.FindArmy(Id) == nullptr);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedB)].Troops, Before + 1200);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(Captain)].City, RedB);

	// An undefended town opens its gates.
	State.Cities[static_cast<size_t>(Town)].Troops = 0;
	State.Cities[static_cast<size_t>(RedA)].Troops -= 1000;
	GameTestFixture::PlaceArmy(Game, 0, {General}, 1000, RedA, Town, 55);
	const EStepResult Result = Game.Step();
	IRON_EXPECT(Result == EStepResult::DayAdvanced);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(Town)].Owner, 0);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(Town)].Troops, 1000);
}

IRON_TEST(GameFieldBattleOnSharedRoad)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 25))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int BlueGeneral = GameTestFixture::Officer(Game, "b_gen");
	const int Blue = GameTestFixture::Faction(Game, "blue");
	State.Cities[static_cast<size_t>(RedB)].Troops -= 3000;
	State.Cities[static_cast<size_t>(BlueA)].Troops -= 4000;
	const int RedArmy = GameTestFixture::PlaceArmy(Game, 0, {Captain}, 3000, RedB, BlueA, 40);
	const int BlueArmy = GameTestFixture::PlaceArmy(Game, Blue, {BlueGeneral}, 4000, BlueA, RedB, 30);
	IRON_EXPECT_EQ(State.ArmySpeed(*State.FindArmy(BlueArmy)), 13);
	Game.EndPlanning();
	IRON_EXPECT(Game.Step() == EStepResult::PlayerBattle);
	const FPendingBattle* Pending = Game.PendingPlayerBattle();
	if (!Pending)
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "expected a field battle");
		return;
	}
	IRON_EXPECT(Pending->Kind == EBattleKind::Field);
	IRON_EXPECT_EQ(Pending->Attacker, RedArmy);
	IRON_EXPECT_EQ(Pending->Defender, BlueArmy);
	const FBattleSetup Setup = Game.MakeBattleSetup(*Pending);
	IRON_EXPECT(Setup.Kind == EBattleKind::Field);
	IRON_EXPECT(Setup.Terrain == ETerrain::Hills);
	IRON_EXPECT_MSG(Setup.Location == "Road to Bluegate", Setup.Location);
	IRON_EXPECT_EQ(Setup.GateHp, 0);
	IRON_EXPECT_EQ(Setup.Sides[1].Units.size(), static_cast<size_t>(1));
	IRON_EXPECT(Setup.Sides[1].Units[0].Type == ETroopType::Cavalry);
	Game.ResolvePlayerBattle(GameMilitaryTests::MakeResult(Setup, 0, 70, 30));
	const FArmy* Winner = State.FindArmy(RedArmy);
	const FArmy* Loser = State.FindArmy(BlueArmy);
	IRON_EXPECT(Winner && Winner->State == EArmyState::Marching);
	IRON_EXPECT(Loser && Loser->State == EArmyState::Returning);
	if (Loser)
	{
		IRON_EXPECT_EQ(Loser->Next, BlueA);
		IRON_EXPECT_EQ(Loser->TotalTroops(), 1200);
	}
	IRON_EXPECT(State.Relation(0, Blue).Trust < 30);
	IRON_EXPECT(GameMilitaryTests::LogContains(Game, "The Red Banner defeated the Blue Court in a battle on the road to Bluegate."));
}

IRON_TEST(GameConquestCapturesOfficersAndEndsFactions)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 26))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int BlueGeneral = GameTestFixture::Officer(Game, "b_gen");
	const int BlueRuler = GameTestFixture::Officer(Game, "b_ruler");
	const int Blue = GameTestFixture::Faction(Game, "blue");
	const int Green = GameTestFixture::Faction(Game, "green");
	// Green is already gone; Blue is the last rival.
	State.Factions[static_cast<size_t>(Green)].bAlive = false;
	State.Cities[static_cast<size_t>(GameTestFixture::City(Game, "green_a"))].Owner = -1;
	State.Officers[static_cast<size_t>(GameTestFixture::Officer(Game, "g_ruler"))].Status = EOfficerStatus::Free;
	State.Officers[static_cast<size_t>(GameTestFixture::Officer(Game, "g_ruler"))].Faction = -1;

	State.Cities[static_cast<size_t>(RedB)].Troops -= 4000;
	GameTestFixture::PlaceArmy(Game, 0, {Captain}, 4000, RedB, BlueA, 75);
	Game.EndPlanning();
	IRON_EXPECT(Game.Step() == EStepResult::PlayerBattle);
	const FPendingBattle* Pending = Game.PendingPlayerBattle();
	if (!Pending)
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "expected a siege");
		return;
	}
	const FBattleSetup Setup = Game.MakeBattleSetup(*Pending);
	Game.ResolvePlayerBattle(GameMilitaryTests::MakeResult(Setup, 0, 80, 40, {{BlueGeneral, EUnitStatus::Captured}, {BlueRuler, EUnitStatus::Captured}}));
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(BlueA)].Owner, 0);
	IRON_EXPECT(State.Officers[static_cast<size_t>(BlueGeneral)].Status == EOfficerStatus::Prisoner);
	IRON_EXPECT(State.Officers[static_cast<size_t>(BlueRuler)].Status == EOfficerStatus::Prisoner);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(BlueRuler)].Captor, 0);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(BlueRuler)].City, BlueA);
	IRON_EXPECT(std::find(State.PendingPrisoners.begin(), State.PendingPrisoners.end(), BlueGeneral) != State.PendingPrisoners.end());
	IRON_EXPECT(!State.Factions[static_cast<size_t>(Blue)].bAlive);
	IRON_EXPECT(State.Phase == EPhase::GameOver);
	IRON_EXPECT(State.Outcome == EOutcome::Victory);
	IRON_EXPECT(Game.Step() == EStepResult::GameOver);
	// The fallen faction's officers are now masterless prisoners, easy to win over.
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(BlueGeneral)].Faction, -1);
	IRON_EXPECT(GameMilitaryTests::LogContains(Game, "Victory!"));
}

IRON_TEST(GameDefeatWhenThePlayerFalls)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 27))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int Town = GameTestFixture::City(Game, "free_town");
	const int Blue = GameTestFixture::Faction(Game, "blue");
	const int BlueGeneral = GameTestFixture::Officer(Game, "b_gen");
	// Red keeps only Redhold; all its officers are there.
	State.Cities[static_cast<size_t>(RedB)].Owner = -1;
	State.Cities[static_cast<size_t>(Town)].Owner = Blue;
	State.Officers[static_cast<size_t>(GameTestFixture::Officer(Game, "r_b"))].City = RedA;
	State.Cities[static_cast<size_t>(Town)].Troops = 9000;
	GameTestFixture::PlaceArmy(Game, Blue, {BlueGeneral}, 9000, Town, RedA, 55);
	State.Cities[static_cast<size_t>(Town)].Troops = 0;
	Game.EndPlanning();
	IRON_EXPECT(Game.Step() == EStepResult::PlayerBattle);
	const FPendingBattle* Pending = Game.PendingPlayerBattle();
	if (!Pending)
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "expected a siege of Redhold");
		return;
	}
	IRON_EXPECT(!Game.IsPlayerAttacker(*Pending));
	const FBattleSetup Setup = Game.MakeBattleSetup(*Pending);
	IRON_EXPECT(Setup.Sides[1].bPlayer);
	IRON_EXPECT_EQ(Setup.Sides[1].Units.size(), static_cast<size_t>(4));
	// Ruler first by Command (r_ruler 80, r_gen 75, r_b 60, r_admin 40).
	IRON_EXPECT_EQ(Setup.Sides[1].Units[0].Officer, GameTestFixture::Officer(Game, "r_ruler"));
	std::vector<std::pair<int, EUnitStatus>> Captured;
	for (const FBattleUnitSetup& Unit : Setup.Sides[1].Units)
	{
		Captured.push_back({Unit.Officer, EUnitStatus::Captured});
	}
	Game.ResolvePlayerBattle(GameMilitaryTests::MakeResult(Setup, 0, 80, 0, Captured));
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Owner, Blue);
	IRON_EXPECT(!State.Factions[0].bAlive);
	IRON_EXPECT(State.Phase == EPhase::GameOver);
	IRON_EXPECT(State.Outcome == EOutcome::Defeat);
	IRON_EXPECT(Game.Step() == EStepResult::GameOver);
}

IRON_TEST(GameRulerSuccessionAfterDeathInBattle)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 28))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int Town = GameTestFixture::City(Game, "free_town");
	const int Ruler = GameTestFixture::Officer(Game, "r_ruler");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	State.Cities[static_cast<size_t>(RedA)].Troops -= 1000;
	GameTestFixture::PlaceArmy(Game, 0, {Ruler}, 1000, RedA, Town, 55);
	Game.EndPlanning();
	IRON_EXPECT(Game.Step() == EStepResult::PlayerBattle);
	const FPendingBattle* Pending = Game.PendingPlayerBattle();
	if (!Pending)
	{
		IronTest::ReportFailure(__FILE__, __LINE__, "expected a siege");
		return;
	}
	Game.ResolvePlayerBattle(GameMilitaryTests::MakeResult(Game.MakeBattleSetup(*Pending), 1, 0, 90, {{Ruler, EUnitStatus::Killed}}));
	IRON_EXPECT(State.Officers[static_cast<size_t>(Ruler)].Status == EOfficerStatus::Dead);
	IRON_EXPECT(State.Armies.empty());
	IRON_EXPECT_EQ(State.Factions[0].Ruler, General);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].Loyalty, 100);
	IRON_EXPECT(State.Factions[0].bAlive);
	IRON_EXPECT(GameMilitaryTests::LogContains(Game, "succeeds"));
}

IRON_TEST(GameStarvingArmyTurnsBack)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 29))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int Town = GameTestFixture::City(Game, "free_town");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	State.Cities[static_cast<size_t>(RedA)].Troops -= 2000;
	const int Id = GameTestFixture::PlaceArmy(Game, 0, {General}, 2000, RedA, Town, 20);
	State.FindArmy(Id)->Food = 0;
	Game.EndPlanning();
	IRON_EXPECT(Game.Step() == EStepResult::DayAdvanced);
	const FArmy* Army = State.FindArmy(Id);
	IRON_EXPECT(Army != nullptr);
	if (Army)
	{
		IRON_EXPECT(Army->State == EArmyState::Returning);
		IRON_EXPECT_EQ(Army->TotalTroops(), 1800);
		IRON_EXPECT_EQ(Army->Next, RedA);
	}
	for (int Day = 0; Day < 10 && State.FindArmy(Id); ++Day)
	{
		Game.Step();
	}
	IRON_EXPECT(State.FindArmy(Id) == nullptr);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].City, RedA);
}

IRON_TEST(GameSaveLoadMidBattleIsDeterministic)
{
	FGame Game;
	if (!GameTestFixture::StartGame(Game, 30))
	{
		return;
	}
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int Town = GameTestFixture::City(Game, "free_town");
	FArmyPlan Plan;
	Plan.City = RedA;
	Plan.Officers = {GameTestFixture::Officer(Game, "r_gen")};
	Plan.Troops = 6000;
	Plan.Food = 2000;
	Plan.Target = Town;
	std::string Error;
	IRON_EXPECT_MSG(Game.FormArmy(Plan, Error), Error);
	GameTestFixture::ClearPlanningPrompts(Game);
	Game.EndPlanning();
	IRON_EXPECT(GameMilitaryTests::StepToBattle(Game) == EStepResult::PlayerBattle);

	const std::string Saved = Game.SaveGame().Write(false);
	FJson Parsed;
	IRON_EXPECT_MSG(FJson::Parse(Saved, Parsed, Error), Error);
	FGame Loaded;
	IRON_EXPECT_MSG(Loaded.LoadGame(Parsed, Error), Error);
	IRON_EXPECT(Loaded.State.bDayInProgress);
	IRON_EXPECT(Loaded.PendingPlayerBattle() != nullptr);
	IRON_EXPECT(Loaded.DateText() == Game.DateText());
	IRON_EXPECT(Loaded.SaveGame().Write(false) == Saved);

	for (FGame* Copy : {&Game, &Loaded})
	{
		Copy->AutoResolvePlayerBattle();
		for (int Month = 0; Month < 3 && Copy->State.Phase != EPhase::GameOver; ++Month)
		{
			GameTestFixture::FinishMonth(*Copy);
			GameTestFixture::ClearPlanningPrompts(*Copy);
			Copy->EndPlanning();
		}
	}
	IRON_EXPECT(Game.SaveGame().Write(false) == Loaded.SaveGame().Write(false));
	IRON_EXPECT(Game.State.Month == Loaded.State.Month);
}
