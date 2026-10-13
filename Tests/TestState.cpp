#include "IronTest.h"

#include "Sim/IronLocale.h"
#include "Sim/IronState.h"

using namespace IronSim;

namespace StateTests
{
	bool LoadScenario(FGameState& OutState)
	{
		std::string Text;
		if (!IronTest::ReadFile(IronTest::DataDir() + "/Scenarios/BrokenMandate.json", Text))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "missing BrokenMandate.json");
			return false;
		}
		FJson Root;
		std::string Error;
		if (!FJson::Parse(Text, Root, Error))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "parse: " + Error);
			return false;
		}
		if (!LoadGameState(Root, OutState, Error))
		{
			IronTest::ReportFailure(__FILE__, __LINE__, "load: " + Error);
			return false;
		}
		return true;
	}
}

IRON_TEST(StateLoadsScenario)
{
	FGameState State;
	if (!StateTests::LoadScenario(State))
	{
		return;
	}
	IRON_EXPECT(State.Cities.size() >= 20);
	IRON_EXPECT(State.Factions.size() == 6);
	IRON_EXPECT(State.Roads.size() >= 30);
	IRON_EXPECT(State.Relations.size() == State.Factions.size() * State.Factions.size());
	const int Luojing = State.FindCity("luojing");
	IRON_EXPECT(Luojing >= 0);
	IRON_EXPECT(!State.Neighbors(Luojing).empty());
	for (size_t Road = 0; Road < State.Roads.size(); ++Road)
	{
		IRON_EXPECT(State.RoadBetween(State.Roads[Road].A, State.Roads[Road].B) == static_cast<int>(Road));
	}
	// Relations are symmetric through the accessor.
	const int Iron = State.FindFaction("iron_banner");
	const int Azure = State.FindFaction("azure_court");
	IRON_EXPECT(State.Relation(Iron, Azure).Trust == State.Relation(Azure, Iron).Trust);
	IRON_EXPECT(State.AreHostile(Iron, Azure));
	IRON_EXPECT(State.AreHostile(Iron, -1));
	IRON_EXPECT(!State.AreHostile(Iron, Iron));
}

IRON_TEST(StateSaveRoundTripIsStable)
{
	FGameState State;
	if (!StateTests::LoadScenario(State))
	{
		return;
	}
	State.PlayerFaction = 0;
	State.Rng.SetState(0x1234567890ABCDEFull);
	State.AddLog(0, true, "A message with \"quotes\" and 中文.");
	const std::string First = SaveGameState(State).Write(true);
	FJson Parsed;
	std::string Error;
	IRON_EXPECT_MSG(FJson::Parse(First, Parsed, Error), Error);
	FGameState Reloaded;
	IRON_EXPECT_MSG(LoadGameState(Parsed, Reloaded, Error), Error);
	IRON_EXPECT(Reloaded.Rng.GetState() == 0x1234567890ABCDEFull);
	IRON_EXPECT(Reloaded.PlayerFaction == 0);
	const std::string Second = SaveGameState(Reloaded).Write(true);
	IRON_EXPECT(First == Second);
}

IRON_TEST(StateArmyPositionFollowsRoad)
{
	FGameState State;
	if (!StateTests::LoadScenario(State))
	{
		return;
	}
	FArmy Army;
	Army.Node = State.Roads[0].A;
	Army.Next = State.Roads[0].B;
	Army.Road = 0;
	Army.Progress = State.RoadLength(0) / 2;
	Army.Units.push_back(FArmyUnit{-1, 1000, ETroopType::Infantry});
	const FPoint Mid = State.ArmyPosition(Army);
	const FPoint A = State.Cities[static_cast<size_t>(Army.Node)].Position;
	const FPoint B = State.Cities[static_cast<size_t>(Army.Next)].Position;
	IRON_EXPECT(std::abs(Mid.X - (A.X + B.X) / 2.0f) < 1.0f);
	IRON_EXPECT(std::abs(Mid.Y - (A.Y + B.Y) / 2.0f) < 1.0f);
	IRON_EXPECT(State.ArmySpeed(Army) == 10);
}

IRON_TEST(LocaleLooksUpAndFormats)
{
	FLocale& Locale = FLocale::Active();
	Locale.Reset("zh-Hans");
	Locale.SetString("test.greeting", "{name}，你好！共{count}人。");
	IRON_EXPECT(LocF("test.greeting", "Hello {name}! {count} people.", {{"name", "燕铁山"}, {"count", ToText(3)}}) == "燕铁山，你好！共3人。");
	IRON_EXPECT(Loc("test.missing", "Fallback") == "Fallback");
	IRON_EXPECT(DisplayName(EStat::Martial) == "Martial");
	Locale.SetString("stat.martial", "武力");
	IRON_EXPECT(DisplayName(EStat::Martial) == "武力");
	Locale.Reset("en");
	IRON_EXPECT(DisplayName(EStat::Martial) == "Martial");
}
