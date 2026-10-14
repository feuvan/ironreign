// Unit tests for data-driven events, AI proposals and officer life-cycle rules at month end.

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
}

namespace GameEventTests
{
	void PlayQuietMonth(FGame& Game)
	{
		Game.State.Orders.clear();
		Game.EndPlanning();
		GameTestFixture::FinishMonth(Game);
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

IRON_TEST(GamePlayerEventOffersChoices)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 31))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	IRON_EXPECT(Game.CurrentEvent() == nullptr);
	GameEventTests::PlayQuietMonth(Game);
	const FPendingEvent* Event = Game.CurrentEvent();
	IRON_EXPECT(Event != nullptr);
	if (!Event)
	{
		return;
	}
	IRON_EXPECT_MSG(Event->Title == "Bandits near Redhold", Event->Title);
	IRON_EXPECT_MSG(Event->Text == "Bandits plague Redhold, my lord Red Lord.", Event->Text);
	IRON_EXPECT_EQ(Event->City, RedA);
	IRON_EXPECT_EQ(Event->Faction, 0);
	// The advisor is the best strategist besides the ruler.
	IRON_EXPECT_EQ(Event->Speaker, GameTestFixture::Officer(Game, "r_admin"));
	IRON_EXPECT_EQ(Event->Choices.size(), static_cast<size_t>(3));
	IRON_EXPECT(Game.CanChoose(0));
	IRON_EXPECT(!Game.CanChoose(1));
	IRON_EXPECT(Game.CanChoose(2));
	IRON_EXPECT(!Game.CanChoose(3));
	IRON_EXPECT(State.Events[0].TimesFired == 1);

	// Saving keeps the resolved event.
	std::string Error;
	FGame Loaded;
	IRON_EXPECT_MSG(Loaded.LoadGame(Game.SaveGame(), Error), Error);
	IRON_EXPECT(Loaded.CurrentEvent() && Loaded.CurrentEvent()->Choices.size() == 3);
	IRON_EXPECT(Loaded.CurrentEvent() && Loaded.CurrentEvent()->Title == Event->Title);

	const int Troops = State.Cities[static_cast<size_t>(RedA)].Troops;
	const int Order = State.Cities[static_cast<size_t>(RedA)].Order;
	Game.ChooseEventOption(0);
	IRON_EXPECT(Game.CurrentEvent() == nullptr);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Troops, Troops - 500);
	IRON_EXPECT_EQ(State.Cities[static_cast<size_t>(RedA)].Order, std::min(100, Order + 10));

	// The other copy picks the message option.
	Loaded.ChooseEventOption(2);
	IRON_EXPECT(GameEventTests::LogContains(Loaded, "The people of Redhold grumble."));
	IRON_EXPECT_EQ(Loaded.State.Cities[static_cast<size_t>(RedA)].Order, Order - 5);

	// A "once" event never returns.
	for (int Month = 0; Month < 12; ++Month)
	{
		GameEventTests::PlayQuietMonth(Game);
		GameTestFixture::ClearPlanningPrompts(Game);
	}
	IRON_EXPECT_EQ(State.Events[0].TimesFired, 1);
}

IRON_TEST(GameWorldEventAppliesAutomatically)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 32))
	{
		return;
	}
	FGameState& State = Game.State;
	const int GreenA = GameTestFixture::City(Game, "green_a");
	GameEventTests::PlayQuietMonth(Game);
	GameTestFixture::ClearPlanningPrompts(Game);
	const int Farm = State.Cities[static_cast<size_t>(GreenA)].Farm;
	GameEventTests::PlayQuietMonth(Game);
	IRON_EXPECT_EQ(State.Month, 3);
	IRON_EXPECT(State.Cities[static_cast<size_t>(GreenA)].Farm >= Farm + 25);
	IRON_EXPECT(GameEventTests::LogContains(Game, "Good Rains: Rain blesses the fields of Greenvale."));
	IRON_EXPECT_EQ(State.Events[1].TimesFired, 1);
	// World events never wait for the player.
	for (const FPendingEvent& Pending : State.PendingEvents)
	{
		IRON_EXPECT(Pending.Def != 1);
	}
}

IRON_TEST(GameAIProposalBecomesAnEvent)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 33))
	{
		return;
	}
	FGameState& State = Game.State;
	const int Blue = GameTestFixture::Faction(Game, "blue");
	State.Orders.clear();
	FOrder Envoy;
	Envoy.Type = EOrderType::Alliance;
	Envoy.Officer = GameTestFixture::Officer(Game, "b_ruler");
	Envoy.City = GameTestFixture::City(Game, "blue_a");
	Envoy.TargetFaction = 0;
	State.Orders.push_back(Envoy);
	Game.EndPlanning();
	const FPendingEvent* Event = Game.CurrentEvent();
	IRON_EXPECT(Event != nullptr);
	if (!Event)
	{
		return;
	}
	IRON_EXPECT_EQ(Event->Def, -1);
	IRON_EXPECT_EQ(Event->Faction, Blue);
	IRON_EXPECT_MSG(Event->Title == "Envoy from the Blue Court", Event->Title);
	IRON_EXPECT_EQ(Event->Choices.size(), static_cast<size_t>(2));
	IRON_EXPECT(!State.AreAllied(0, Blue));
	Game.ChooseEventOption(0);
	IRON_EXPECT(State.AreAllied(0, Blue));
	IRON_EXPECT_EQ(State.Relation(0, Blue).AllianceMonths, 36);
	IRON_EXPECT(GameEventTests::LogContains(Game, "have sealed an alliance"));
}

IRON_TEST(GameOfficersAppearDefectAndEscape)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 34))
	{
		return;
	}
	FGameState& State = Game.State;
	const int Kid = GameTestFixture::Officer(Game, "u_kid");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int BlueGeneral = GameTestFixture::Officer(Game, "b_gen");
	const int RedA = GameTestFixture::City(Game, "red_a");
	// A disloyal, ambitious officer is likely to leave; a prisoner may escape home.
	State.Officers[static_cast<size_t>(Captain)].Loyalty = 5;
	State.Officers[static_cast<size_t>(Captain)].Ambition = 100;
	State.Officers[static_cast<size_t>(Captain)].Affinity = 85;
	FOfficer& Captive = State.Officers[static_cast<size_t>(BlueGeneral)];
	Captive.Status = EOfficerStatus::Prisoner;
	Captive.Captor = 0;
	Captive.City = RedA;
	bool bLeft = false;
	for (int Month = 0; Month < 36; ++Month)
	{
		GameEventTests::PlayQuietMonth(Game);
		GameTestFixture::ClearPlanningPrompts(Game);
		bLeft = bLeft || State.Officers[static_cast<size_t>(Captain)].Status == EOfficerStatus::Free;
		if (State.Phase == EPhase::GameOver)
		{
			break;
		}
	}
	IRON_EXPECT_MSG(bLeft, "a disloyal officer should desert");
	IRON_EXPECT(State.Officers[static_cast<size_t>(Kid)].Status != EOfficerStatus::Unborn);
	IRON_EXPECT(State.Year >= 214);
	IRON_EXPECT(State.Officers[static_cast<size_t>(BlueGeneral)].Status != EOfficerStatus::Prisoner || State.Officers[static_cast<size_t>(BlueGeneral)].Captor == 0);
	IRON_EXPECT(GameEventTests::LogContains(Game, "has lost faith in your cause"));
}

IRON_TEST(GameEventWithoutChoicesCanBeAcknowledged)
{
	IronSim::FGame Game;
	IronSim::FPendingEvent Pending;
	Pending.Title = "Old save event";
	Game.State.PendingEvents.push_back(Pending);
	IRON_EXPECT(Game.CurrentEvent() != nullptr);
	IRON_EXPECT(!Game.CanChoose(1));
	IRON_EXPECT(Game.CanChoose(0));
	Game.ChooseEventOption(0);
	IRON_EXPECT(Game.CurrentEvent() == nullptr);
}
