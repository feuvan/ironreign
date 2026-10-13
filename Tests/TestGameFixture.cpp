// Shared fixture for the strategic rules tests (TestGame*.cpp): a small synthetic scenario and helpers.
// The other test files forward-declare the functions in namespace GameTestFixture.

#include "IronTest.h"

#include "Sim/IronGame.h"

#include <algorithm>
#include <string>

namespace GameTestFixture
{
	/**
	 * Map (days):
	 *   red_b --5-- red_a --6-- free_town --7-- green_a
	 *     |                                      |
	 *     8                                      10
	 *     |                                      |
	 *   blue_a ----------------------------------+
	 */
	const char* ScenarioText()
	{
		return R"JSON({
  "format": "ironreign", "version": 1, "key": "test", "name": "Test Scenario", "startYear": 212, "startMonth": 1,
  "map": {"width": 1000, "height": 1000},
  "techniques": [
    {"key": "tiger_claw", "name": "Tiger Claw", "kind": "strike", "power": 160, "minMartial": 60}
  ],
  "factions": [
    {"key": "red", "name": "Red Banner", "glyph": "R", "color": "#B3282D", "ruler": "r_ruler", "capital": "red_a"},
    {"key": "blue", "name": "Blue Court", "glyph": "B", "color": "#2F6DB5", "ruler": "b_ruler", "capital": "blue_a"},
    {"key": "green", "name": "Green Lotus", "glyph": "G", "color": "#4C9A3C", "ruler": "g_ruler", "capital": "green_a"}
  ],
  "cities": [
    {"key": "red_a", "name": "Redhold", "x": 100, "y": 100, "size": 3, "terrain": "plains", "owner": "red",
     "population": 200000, "populationMax": 300000, "farm": 500, "farmMax": 900, "commerce": 500, "commerceMax": 900,
     "defense": 500, "defenseMax": 900, "order": 70, "troops": 10000, "training": 60, "gold": 3000, "food": 30000},
    {"key": "red_b", "name": "Redford", "x": 100, "y": 300, "size": 2, "terrain": "river", "owner": "red",
     "population": 100000, "populationMax": 200000, "farm": 300, "farmMax": 600, "commerce": 300, "commerceMax": 600,
     "defense": 300, "defenseMax": 600, "order": 60, "troops": 5000, "training": 50, "gold": 1000, "food": 10000},
    {"key": "blue_a", "name": "Bluegate", "x": 300, "y": 400, "size": 2, "terrain": "hills", "owner": "blue",
     "population": 150000, "populationMax": 250000, "farm": 400, "farmMax": 800, "commerce": 400, "commerceMax": 800,
     "defense": 400, "defenseMax": 800, "order": 65, "troops": 8000, "training": 55, "gold": 1500, "food": 20000},
    {"key": "green_a", "name": "Greenvale", "x": 500, "y": 100, "size": 2, "terrain": "forest", "owner": "green",
     "population": 150000, "populationMax": 250000, "farm": 400, "farmMax": 800, "commerce": 400, "commerceMax": 800,
     "defense": 400, "defenseMax": 800, "order": 65, "troops": 8000, "training": 55, "gold": 1500, "food": 20000},
    {"key": "free_town", "name": "Freeport", "x": 300, "y": 100, "size": 1, "terrain": "coast",
     "population": 60000, "populationMax": 120000, "farm": 200, "farmMax": 500, "commerce": 200, "commerceMax": 500,
     "defense": 200, "defenseMax": 500, "order": 50, "troops": 2000, "training": 30, "gold": 800, "food": 8000}
  ],
  "roads": [
    {"a": "red_a", "b": "red_b", "days": 5, "kind": "road"},
    {"a": "red_a", "b": "free_town", "days": 6, "kind": "road"},
    {"a": "red_b", "b": "blue_a", "days": 8, "kind": "pass"},
    {"a": "free_town", "b": "green_a", "days": 7, "kind": "road"},
    {"a": "blue_a", "b": "green_a", "days": 10, "kind": "river"}
  ],
  "officers": [
    {"key": "r_ruler", "name": "Red Lord", "status": "serving", "faction": "red", "city": "red_a", "birth": 180,
     "martial": 70, "command": 80, "strategy": 60, "politics": 60, "charm": 85, "affinity": 10, "ambition": 80, "bravery": 60, "specialty": "cavalry", "loyalty": 100},
    {"key": "r_gen", "name": "Red General", "status": "serving", "faction": "red", "city": "red_a", "birth": 185,
     "martial": 85, "command": 75, "strategy": 50, "politics": 30, "charm": 50, "affinity": 12, "ambition": 40, "bravery": 80, "specialty": "infantry", "loyalty": 90},
    {"key": "r_admin", "name": "Red Steward", "status": "serving", "faction": "red", "city": "red_a", "birth": 182,
     "martial": 30, "command": 40, "strategy": 70, "politics": 88, "charm": 70, "affinity": 15, "ambition": 30, "bravery": 30, "specialty": "archer", "loyalty": 85},
    {"key": "r_b", "name": "Red Captain", "status": "serving", "faction": "red", "city": "red_b", "birth": 190,
     "martial": 65, "command": 60, "strategy": 40, "politics": 50, "charm": 55, "affinity": 20, "ambition": 50, "bravery": 60, "specialty": "infantry", "loyalty": 80},
    {"key": "b_ruler", "name": "Blue Lord", "status": "serving", "faction": "blue", "city": "blue_a", "birth": 175,
     "martial": 50, "command": 70, "strategy": 75, "politics": 80, "charm": 80, "affinity": 70, "ambition": 70, "bravery": 50, "specialty": "archer", "loyalty": 100},
    {"key": "b_gen", "name": "Blue General", "status": "serving", "faction": "blue", "city": "blue_a", "birth": 186,
     "martial": 75, "command": 82, "strategy": 55, "politics": 40, "charm": 45, "affinity": 72, "ambition": 50, "bravery": 70, "specialty": "cavalry", "loyalty": 70},
    {"key": "g_ruler", "name": "Green Lord", "status": "serving", "faction": "green", "city": "green_a", "birth": 178,
     "martial": 60, "command": 65, "strategy": 80, "politics": 75, "charm": 78, "affinity": 120, "ambition": 60, "bravery": 50, "specialty": "archer", "loyalty": 100},
    {"key": "f_wander", "name": "Free Wanderer", "status": "free", "city": "free_town", "birth": 192,
     "martial": 72, "command": 60, "strategy": 50, "politics": 40, "charm": 50, "affinity": 11, "ambition": 20, "bravery": 70, "specialty": "cavalry"},
    {"key": "h_sage", "name": "Hidden Sage", "status": "hidden", "city": "red_a", "birth": 170, "rumor": "An old sage tends plum trees outside Redhold.",
     "martial": 20, "command": 50, "strategy": 92, "politics": 80, "charm": 60, "affinity": 10, "ambition": 10, "bravery": 30, "specialty": "archer"},
    {"key": "u_kid", "name": "Young Prodigy", "status": "unborn", "appear": 214, "city": "red_b", "birth": 200,
     "martial": 80, "command": 70, "strategy": 60, "politics": 40, "charm": 60, "affinity": 30, "ambition": 50, "bravery": 80, "specialty": "cavalry"}
  ],
  "sects": [
    {"key": "iron_fist", "name": "Iron Fist School", "city": "red_b", "techniques": ["tiger_claw"], "favor": {"red": 60}}
  ],
  "relations": [
    {"a": "red", "b": "blue", "trust": 30},
    {"a": "red", "b": "green", "trust": 50}
  ],
  "events": [
    {"key": "bandits", "title": "Bandits near {city}", "text": "Bandits plague {city}, my lord {ruler}.", "world": false, "once": true,
     "context": "capital", "when": {"minYear": 212, "months": [2], "chance": 100},
     "choices": [
       {"label": "Send troops", "effects": [{"type": "troops", "amount": -500, "city": "context"}, {"type": "order", "amount": 10, "city": "context"}]},
       {"label": "Pay them off", "gold": 5000, "effects": [{"type": "gold", "amount": -5000, "city": "context"}]},
       {"label": "Ignore them", "effects": [{"type": "order", "amount": -5, "city": "context"}, {"type": "message", "text": "The people of {city} grumble."}]}
     ]},
    {"key": "good_rains", "title": "Good Rains", "text": "Rain blesses the fields of {city}.", "world": true, "once": false,
     "context": "green_a", "when": {"months": [3], "chance": 100},
     "effects": [{"type": "farm", "amount": 25, "city": "context"}]}
  ]
})JSON";
	}

	IronSim::FJson ScenarioJson()
	{
		IronSim::FJson Root;
		std::string Error;
		if (!IronSim::FJson::Parse(ScenarioText(), Root, Error))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "fixture parse: " + Error);
		}
		return Root;
	}

	bool StartGame(IronSim::FGame& Game, uint64_t Seed)
	{
		std::string Error;
		const bool bOk = Game.NewGame(ScenarioJson(), 0, IronSim::EDifficulty::Normal, Seed, Error);
		if (!bOk)
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "NewGame: " + Error);
		}
		return bOk;
	}

	/** Like StartGame, but AI factions are kept from acting: their officers are given away. */
	bool StartQuietGame(IronSim::FGame& Game, uint64_t Seed)
	{
		IronSim::FJson Root = ScenarioJson();
		std::string Error;
		if (!Game.NewGame(Root, 0, IronSim::EDifficulty::Normal, Seed, Error))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "NewGame: " + Error);
			return false;
		}
		// Clear AI orders/armies made during initial planning and prevent further AI activity in tests that need a quiet world.
		IronSim::FGameState& State = Game.State;
		State.Orders.erase(std::remove_if(State.Orders.begin(), State.Orders.end(), [&State](const IronSim::FOrder& Order) {
			return State.Officers[static_cast<size_t>(Order.Officer)].Faction != State.PlayerFaction;
		}), State.Orders.end());
		for (const IronSim::FArmy& Army : State.Armies)
		{
			for (const IronSim::FArmyUnit& Unit : Army.Units)
			{
				State.Officers[static_cast<size_t>(Unit.Officer)].Army = -1;
				State.Officers[static_cast<size_t>(Unit.Officer)].City = Army.Home;
			}
			State.Cities[static_cast<size_t>(Army.Home)].Troops += Army.TotalTroops();
			State.Cities[static_cast<size_t>(Army.Home)].Food += Army.Food;
		}
		State.Armies.clear();
		State.PendingEvents.clear();
		return true;
	}

	int City(const IronSim::FGame& Game, const char* Key)
	{
		const int Index = Game.State.FindCity(Key);
		if (Index < 0)
		{
			IronTest::ReportFailure(__FILE__, __LINE__, std::string("missing city ") + Key);
		}
		return Index;
	}

	int Officer(const IronSim::FGame& Game, const char* Key)
	{
		const int Index = Game.State.FindOfficer(Key);
		if (Index < 0)
		{
			IronTest::ReportFailure(__FILE__, __LINE__, std::string("missing officer ") + Key);
		}
		return Index;
	}

	int Faction(const IronSim::FGame& Game, const char* Key)
	{
		return Game.State.FindFaction(Key);
	}

	/** Steps through execution until the month ends (auto-resolving player battles). Returns the last result. */
	IronSim::EStepResult FinishMonth(IronSim::FGame& Game)
	{
		IronSim::EStepResult Result = IronSim::EStepResult::Idle;
		for (int Guard = 0; Guard < 400; ++Guard)
		{
			Result = Game.Step();
			if (Result == IronSim::EStepResult::PlayerBattle)
			{
				Game.AutoResolvePlayerBattle();
				continue;
			}
			if (Result != IronSim::EStepResult::DayAdvanced)
			{
				return Result;
			}
		}
		IronTest::ReportFailure(__FILE__, __LINE__, "month did not end");
		return Result;
	}

	/** Answers all pending events with their first selectable choice and imprisons pending prisoners. */
	void ClearPlanningPrompts(IronSim::FGame& Game)
	{
		for (int Guard = 0; Guard < 32 && Game.CurrentEvent(); ++Guard)
		{
			int Choice = 0;
			while (Choice < static_cast<int>(Game.CurrentEvent()->Choices.size()) && !Game.CanChoose(Choice))
			{
				++Choice;
			}
			Game.ChooseEventOption(Choice);
		}
		const std::vector<int> Prisoners = Game.State.PendingPrisoners;
		for (const int Prisoner : Prisoners)
		{
			std::string Message;
			Game.DecidePrisoner(Prisoner, IronSim::EPrisonerDecision::Imprison, Message);
		}
	}

	/** Puts the player's officer into a new army that is already standing on the road next to Target. */
	int PlaceArmy(IronSim::FGame& Game, int Faction, const std::vector<int>& Officers, int Troops, int From, int Target, int Progress)
	{
		IronSim::FGameState& State = Game.State;
		IronSim::FArmy Army;
		Army.Id = State.NextArmyId++;
		Army.Faction = Faction;
		const int Each = Troops / static_cast<int>(Officers.size());
		for (const int Officer : Officers)
		{
			IronSim::FOfficer& Data = State.Officers[static_cast<size_t>(Officer)];
			Army.Units.push_back(IronSim::FArmyUnit{Officer, Each, Data.Specialty});
			Data.City = -1;
			Data.Army = Army.Id;
		}
		Army.Food = 5000;
		Army.Training = 60;
		Army.Morale = 70;
		Army.Home = From;
		Army.Target = Target;
		Army.State = IronSim::EArmyState::Marching;
		Army.Node = From;
		Army.Next = Target;
		Army.Road = State.RoadBetween(From, Target);
		Army.Progress = Progress;
		Army.bNew = false;
		State.Armies.push_back(Army);
		return Army.Id;
	}
}
