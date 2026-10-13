// Unit tests for the strategic rules: session, orders, immediate actions, prisoners and the monthly economy.

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

namespace GameOrderTests
{
	namespace F = GameTestFixture;

	FOrder MakeOrder(EOrderType Type, int Officer, int City)
	{
		FOrder Order;
		Order.Type = Type;
		Order.Officer = Officer;
		Order.City = City;
		return Order;
	}

	bool Contains(const std::vector<int>& Values, int Value)
	{
		return std::find(Values.begin(), Values.end(), Value) != Values.end();
	}

	/** Runs one whole month (end planning, play 30 days) and clears the next planning phase's prompts. */
	void PlayMonth(FGame& Game)
	{
		F::ClearPlanningPrompts(Game);
		Game.EndPlanning();
		F::FinishMonth(Game);
		F::ClearPlanningPrompts(Game);
	}
}

IRON_TEST(GameNewGameStartsInPlanning)
{
	FGame Game;
	if (!GameTestFixture::StartGame(Game, 7))
	{
		return;
	}
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	IRON_EXPECT(Game.IsPlanning());
	IRON_EXPECT_EQ(Game.State.PlayerFaction, 0);
	IRON_EXPECT_EQ(Game.State.Relations.size(), static_cast<size_t>(9));
	IRON_EXPECT(Game.DateText() == "Year 212, Month 1 (Spring)");
	IRON_EXPECT(Game.IsPlayerCity(RedA));
	IRON_EXPECT(!Game.IsPlayerCity(BlueA));
	IRON_EXPECT_EQ(Game.IdleOfficers(RedA).size(), static_cast<size_t>(3));
	IRON_EXPECT(Game.IdleOfficers(BlueA).empty());
	IRON_EXPECT_EQ(Game.CityCount(0), 2);
	IRON_EXPECT(Game.State.Officers[static_cast<size_t>(GameTestFixture::Officer(Game, "u_kid"))].Status == EOfficerStatus::Unborn);
	IRON_EXPECT(Game.PlayerOrders().empty());
	bool bAIOrders = false;
	for (const FOrder& Order : Game.State.Orders)
	{
		bAIOrders = bAIOrders || Game.State.Officers[static_cast<size_t>(Order.Officer)].Faction != 0;
	}
	IRON_EXPECT_MSG(bAIOrders, "AI factions plan their first month");
	IRON_EXPECT(Game.DiplomacyTargets().size() == 2);
	IRON_EXPECT(Game.MoveDestinations(RedA).size() == 1);
	IRON_EXPECT(!Game.State.Log.empty());

	FGame Bad;
	std::string Error;
	IRON_EXPECT(!Bad.NewGame(GameTestFixture::ScenarioJson(), 7, EDifficulty::Normal, 1, Error));
	IRON_EXPECT(!Error.empty());
}

IRON_TEST(GameFarmOrderDevelopsAndGrantsExperience)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 11))
	{
		return;
	}
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int Admin = GameTestFixture::Officer(Game, "r_admin");
	const FOrder Order = GameOrderTests::MakeOrder(EOrderType::Farm, Admin, RedA);
	const FOrderCheck Check = Game.CheckOrder(Order);
	IRON_EXPECT(Check.bAllowed);
	IRON_EXPECT_EQ(Check.Cost, 50);
	IRON_EXPECT_MSG(Check.Preview == "Farmland +15", Check.Preview);
	IRON_EXPECT_EQ(Check.SuccessChance, -1);
	const int Gold = Game.State.Cities[static_cast<size_t>(RedA)].Gold;
	std::string Error;
	IRON_EXPECT_MSG(Game.IssueOrder(Order, Error), Error);
	IRON_EXPECT_EQ(Game.State.Cities[static_cast<size_t>(RedA)].Gold, Gold - 50);
	IRON_EXPECT_EQ(Game.PlayerOrders().size(), static_cast<size_t>(1));
	IRON_EXPECT(!GameOrderTests::Contains(Game.IdleOfficers(RedA), Admin));
	const FOrderCheck Again = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Commerce, Admin, RedA));
	IRON_EXPECT(!Again.bAllowed);
	IRON_EXPECT_MSG(Again.Reason == "Red Steward already has orders this month.", Again.Reason);

	const int PoliticsExp = Game.State.Officers[static_cast<size_t>(Admin)].StatExp[StatIndex(EStat::Politics)];
	Game.EndPlanning();
	IRON_EXPECT(!Game.IsPlanning());
	IRON_EXPECT_MSG(Game.DateText() == "Year 212, Month 1, Day 1", Game.DateText());
	IRON_EXPECT_EQ(Game.State.Cities[static_cast<size_t>(RedA)].Farm, 515);
	IRON_EXPECT_EQ(Game.State.Officers[static_cast<size_t>(Admin)].StatExp[StatIndex(EStat::Politics)], PoliticsExp + 15);
	IRON_EXPECT(Game.Step() == EStepResult::DayAdvanced);
	IRON_EXPECT_MSG(Game.DateText() == "Year 212, Month 1, Day 2", Game.DateText());
}

IRON_TEST(GameOrderValidationExplainsRefusals)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 12))
	{
		return;
	}
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int Wanderer = GameTestFixture::Officer(Game, "f_wander");

	const FOrderCheck Foreign = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Farm, GameTestFixture::Officer(Game, "b_gen"), BlueA));
	IRON_EXPECT(!Foreign.bAllowed);
	IRON_EXPECT(Foreign.Reason == "This city is not under your control.");

	const FOrderCheck WrongCity = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Farm, Captain, RedA));
	IRON_EXPECT(!WrongCity.bAllowed);
	IRON_EXPECT_MSG(WrongCity.Reason == "Red Captain is not in Redhold.", WrongCity.Reason);

	FOrder Draft = GameOrderTests::MakeOrder(EOrderType::Draft, General, RedA);
	Draft.Amount = 2000;
	const FOrderCheck TooMany = Game.CheckOrder(Draft);
	IRON_EXPECT(!TooMany.bAllowed);
	IRON_EXPECT_MSG(TooMany.Reason == "Red General can raise at most 1050 troops in one month.", TooMany.Reason);
	Draft.Amount = 0;
	IRON_EXPECT(!Game.CheckOrder(Draft).bAllowed);

	Game.State.Cities[static_cast<size_t>(RedA)].Farm = Game.State.Cities[static_cast<size_t>(RedA)].FarmMax;
	const FOrderCheck Maxed = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Farm, General, RedA));
	IRON_EXPECT(!Maxed.bAllowed);
	IRON_EXPECT(Maxed.Reason == "The farmland is fully developed.");

	Game.State.Cities[static_cast<size_t>(RedA)].Gold = 10;
	const FOrderCheck Poor = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Commerce, General, RedA));
	IRON_EXPECT(!Poor.bAllowed);
	IRON_EXPECT_MSG(Poor.Reason == "Not enough gold: 50 needed, 10 in Redhold.", Poor.Reason);
	IRON_EXPECT_EQ(Poor.Cost, 50);
	Game.State.Cities[static_cast<size_t>(RedA)].Gold = 3000;

	const FOrderCheck Empty = Game.CheckOrder([&] {
		FOrder Order = GameOrderTests::MakeOrder(EOrderType::Transport, General, RedA);
		Order.TargetCity = RedB;
		return Order;
	}());
	IRON_EXPECT(!Empty.bAllowed);
	IRON_EXPECT(Empty.Reason == "Choose what to transport.");

	FOrder Recruit = GameOrderTests::MakeOrder(EOrderType::Recruit, Captain, RedB);
	Recruit.TargetOfficer = Wanderer;
	IRON_EXPECT(!Game.CheckOrder(Recruit).bAllowed);
	IRON_EXPECT(GameOrderTests::Contains(Game.RecruitTargets(RedA), Wanderer));
	IRON_EXPECT(!GameOrderTests::Contains(Game.RecruitTargets(RedB), Wanderer));

	FOrder SelfAlliance = GameOrderTests::MakeOrder(EOrderType::Alliance, General, RedA);
	SelfAlliance.TargetFaction = 0;
	IRON_EXPECT(!Game.CheckOrder(SelfAlliance).bAllowed);

	FOrder Move = GameOrderTests::MakeOrder(EOrderType::Move, General, RedA);
	Move.TargetCity = BlueA;
	IRON_EXPECT(!Game.CheckOrder(Move).bAllowed);

	std::string Error;
	IRON_EXPECT(!Game.IssueOrder(Recruit, Error));
	IRON_EXPECT(!Error.empty());
	IRON_EXPECT(Game.PlayerOrders().empty());

	Game.EndPlanning();
	const FOrderCheck Late = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Commerce, General, RedA));
	IRON_EXPECT(!Late.bAllowed);
	IRON_EXPECT(Late.Reason == "Orders can only be given during the planning phase.");
}

IRON_TEST(GameDraftTransportMoveAndCancel)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 13))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int Ruler = GameTestFixture::Officer(Game, "r_ruler");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int Admin = GameTestFixture::Officer(Game, "r_admin");
	FCity& Home = State.Cities[static_cast<size_t>(RedA)];
	FCity& Ford = State.Cities[static_cast<size_t>(RedB)];

	FOrder Draft = GameOrderTests::MakeOrder(EOrderType::Draft, Ruler, RedA);
	Draft.Amount = 1000;
	const FOrderCheck DraftCheck = Game.CheckOrder(Draft);
	IRON_EXPECT(DraftCheck.bAllowed);
	IRON_EXPECT_EQ(DraftCheck.Cost, 200);
	IRON_EXPECT_EQ(Game.DraftCost(1000), 200);
	IRON_EXPECT_EQ(Game.DraftCapacity(RedA), 200000 / 25);

	FOrder Transport = GameOrderTests::MakeOrder(EOrderType::Transport, General, RedA);
	Transport.TargetCity = RedB;
	Transport.Gold = 500;
	Transport.Food = 1000;
	Transport.Troops = 2000;
	FOrder Move = GameOrderTests::MakeOrder(EOrderType::Move, Admin, RedA);
	Move.TargetCity = RedB;

	std::string Error;
	const int Gold = Home.Gold;
	IRON_EXPECT_MSG(Game.IssueOrder(Draft, Error), Error);
	IRON_EXPECT_MSG(Game.IssueOrder(Transport, Error), Error);
	IRON_EXPECT_EQ(Home.Gold, Gold - 200 - 500);
	IRON_EXPECT_EQ(Home.Troops, 8000);
	IRON_EXPECT_EQ(Game.DraftCapacity(RedA), 200000 / 25 - 1000);
	// Cancelling refunds the cost and the convoy's cargo.
	IRON_EXPECT(Game.CancelOrder(General));
	IRON_EXPECT_EQ(Home.Gold, Gold - 200);
	IRON_EXPECT_EQ(Home.Troops, 10000);
	IRON_EXPECT(!Game.CancelOrder(General));
	IRON_EXPECT_MSG(Game.IssueOrder(Transport, Error), Error);
	IRON_EXPECT_MSG(Game.IssueOrder(Move, Error), Error);

	const int Population = Home.Population;
	Game.EndPlanning();
	IRON_EXPECT_EQ(Home.Troops, 8000 + 1000);
	IRON_EXPECT_EQ(Home.Population, Population - 1000);
	IRON_EXPECT_EQ(Home.Order, 67);
	IRON_EXPECT_EQ(Home.Training, (60 * 8000 + 30 * 1000) / 9000);
	IRON_EXPECT_EQ(Ford.Troops, 7000);
	IRON_EXPECT_EQ(Ford.Food, 11000);
	IRON_EXPECT_EQ(Ford.Gold, 1500);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(Admin)].City, RedB);
}

IRON_TEST(GameRecruitSearchAndSectTraining)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 14))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int Ruler = GameTestFixture::Officer(Game, "r_ruler");
	const int Admin = GameTestFixture::Officer(Game, "r_admin");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int Wanderer = GameTestFixture::Officer(Game, "f_wander");
	const int Sage = GameTestFixture::Officer(Game, "h_sage");
	const int Sect = State.FindSect("iron_fist");
	State.Officers[static_cast<size_t>(Wanderer)].City = RedA;

	IRON_EXPECT_EQ(Game.RecruitChance(Ruler, Wanderer), 83);
	IRON_EXPECT(GameOrderTests::Contains(Game.SectsNear(RedA), Sect));
	IRON_EXPECT(GameOrderTests::Contains(Game.SectsNear(RedB), Sect));

	bool bRecruited = false;
	bool bFoundSage = false;
	bool bLearned = false;
	for (int Month = 0; Month < 24 && !(bRecruited && bFoundSage && bLearned); ++Month)
	{
		std::string Error;
		const FOfficer& Target = State.Officers[static_cast<size_t>(Wanderer)];
		if (Target.Status == EOfficerStatus::Free && GameOrderTests::Contains(Game.RecruitTargets(RedA), Wanderer))
		{
			FOrder Recruit = GameOrderTests::MakeOrder(EOrderType::Recruit, Ruler, RedA);
			Recruit.TargetOfficer = Wanderer;
			const FOrderCheck Check = Game.CheckOrder(Recruit);
			IRON_EXPECT_EQ(Check.SuccessChance, Game.RecruitChance(Ruler, Wanderer));
			IRON_EXPECT_MSG(Game.IssueOrder(Recruit, Error), Error);
		}
		if (State.Officers[static_cast<size_t>(Sage)].Status == EOfficerStatus::Hidden && State.Officers[static_cast<size_t>(Admin)].City == RedA)
		{
			const FOrderCheck Check = Game.CheckOrder(GameOrderTests::MakeOrder(EOrderType::Search, Admin, RedA));
			IRON_EXPECT_EQ(Check.SuccessChance, 25 + 70 / 3 + 70 / 5);
			IRON_EXPECT_MSG(Game.IssueOrder(GameOrderTests::MakeOrder(EOrderType::Search, Admin, RedA), Error), Error);
		}
		if (!bLearned)
		{
			FOrder Training = GameOrderTests::MakeOrder(EOrderType::SectTraining, Captain, RedB);
			Training.TargetSect = Sect;
			const FOrderCheck Check = Game.CheckOrder(Training);
			IRON_EXPECT_MSG(Check.bAllowed, Check.Reason);
			IRON_EXPECT(Check.SuccessChance > 0);
			IRON_EXPECT_MSG(Game.IssueOrder(Training, Error), Error);
		}
		GameOrderTests::PlayMonth(Game);
		bRecruited = bRecruited || (Target.Status == EOfficerStatus::Serving && Target.Faction == 0);
		bFoundSage = bFoundSage || State.Officers[static_cast<size_t>(Sage)].Status != EOfficerStatus::Hidden;
		const FOfficer& Trainee = State.Officers[static_cast<size_t>(Captain)];
		bLearned = bLearned || !Trainee.Techniques.empty();
	}
	IRON_EXPECT_MSG(bRecruited, "the wanderer should join within a few months");
	IRON_EXPECT_MSG(bFoundSage, "the hidden sage should be found");
	IRON_EXPECT_MSG(bLearned, "sect training should teach a technique");
	const FOfficer& Trainee = State.Officers[static_cast<size_t>(Captain)];
	IRON_EXPECT(Trainee.Stats[StatIndex(EStat::Martial)] > 65);
	IRON_EXPECT_EQ(Trainee.Sect, Sect);
}

IRON_TEST(GameDiplomacyOrders)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 15))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int Admin = GameTestFixture::Officer(Game, "r_admin");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int Blue = GameTestFixture::Faction(Game, "blue");
	const int Green = GameTestFixture::Faction(Game, "green");
	State.Relation(0, Green).Trust = 100;

	FOrder Gift = GameOrderTests::MakeOrder(EOrderType::Gift, General, RedA);
	Gift.TargetFaction = Blue;
	Gift.Gold = 400;
	const FOrderCheck GiftCheck = Game.CheckOrder(Gift);
	IRON_EXPECT(GiftCheck.bAllowed);
	IRON_EXPECT_EQ(GiftCheck.Cost, 400);
	IRON_EXPECT_MSG(GiftCheck.Preview == "Trust +11", GiftCheck.Preview);
	std::string Error;
	IRON_EXPECT_MSG(Game.IssueOrder(Gift, Error), Error);
	FOrder Truce = GameOrderTests::MakeOrder(EOrderType::Truce, Admin, RedA);
	Truce.TargetFaction = Blue;
	IRON_EXPECT(!Game.CheckOrder(Truce).bAllowed);
	const int Trust = State.Relation(0, Blue).Trust;
	GameOrderTests::PlayMonth(Game);
	IRON_EXPECT(State.Relation(0, Blue).Trust >= Trust + 11 - 1);

	bool bAllied = false;
	for (int Month = 0; Month < 12 && !bAllied; ++Month)
	{
		FOrder Alliance = GameOrderTests::MakeOrder(EOrderType::Alliance, Admin, RedA);
		Alliance.TargetFaction = Green;
		const FOrderCheck Check = Game.CheckOrder(Alliance);
		IRON_EXPECT_MSG(Check.bAllowed, Check.Reason);
		IRON_EXPECT_EQ(Check.Cost, 100);
		IRON_EXPECT(Check.SuccessChance >= 80);
		IRON_EXPECT_MSG(Game.IssueOrder(Alliance, Error), Error);
		GameOrderTests::PlayMonth(Game);
		bAllied = State.AreAllied(0, Green);
	}
	IRON_EXPECT(bAllied);
	IRON_EXPECT(!State.AreHostile(0, Green));
	IRON_EXPECT(State.Relation(0, Green).AllianceMonths > 30);
	// Allies cannot be attacked.
	IRON_EXPECT(!GameOrderTests::Contains(Game.MarchTargets(RedA), GameTestFixture::City(Game, "green_a")));
}

IRON_TEST(GameMarketRewardDonateDelegate)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 16))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int RedB = GameTestFixture::City(Game, "red_b");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int Ruler = GameTestFixture::Officer(Game, "r_ruler");
	const int Captain = GameTestFixture::Officer(Game, "r_b");
	const int Sect = State.FindSect("iron_fist");
	FCity& Home = State.Cities[static_cast<size_t>(RedA)];

	IRON_EXPECT_EQ(Game.FoodBuyPrice(), 12);
	IRON_EXPECT_EQ(Game.FoodSellPrice(), 7);
	std::string Error;
	const int Gold = Home.Gold;
	const int Food = Home.Food;
	IRON_EXPECT_MSG(Game.TradeFood(RedA, 1000, Error), Error);
	IRON_EXPECT_EQ(Home.Gold, Gold - 120);
	IRON_EXPECT_EQ(Home.Food, Food + 1000);
	IRON_EXPECT_MSG(Game.TradeFood(RedA, -2000, Error), Error);
	IRON_EXPECT_EQ(Home.Gold, Gold - 120 + 140);
	IRON_EXPECT(!Game.TradeFood(RedA, -10000000, Error));
	IRON_EXPECT(!Game.TradeFood(GameTestFixture::City(Game, "blue_a"), 100, Error));
	State.Month = 9;
	IRON_EXPECT(Game.FoodBuyPrice() < 12);
	State.Month = 7;
	IRON_EXPECT(Game.FoodBuyPrice() > 12);
	State.Month = 1;

	IRON_EXPECT(!Game.RewardOfficer(Ruler, 100, Error));
	IRON_EXPECT(Error == "Your ruler needs no reward.");
	IRON_EXPECT(!Game.RewardOfficer(General, 5, Error));
	const int Loyalty = State.Officers[static_cast<size_t>(General)].Loyalty;
	IRON_EXPECT_MSG(Game.RewardOfficer(General, 100, Error), Error);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].Loyalty, std::min(100, Loyalty + 5));
	IRON_EXPECT_EQ(Game.RewardLoyaltyGain(100), 5);

	const int Favor = State.Sects[static_cast<size_t>(Sect)].Favor[0];
	IRON_EXPECT_MSG(Game.DonateToSect(RedA, Sect, 200, Error), Error);
	IRON_EXPECT_EQ(State.Sects[static_cast<size_t>(Sect)].Favor[0], Favor + 10);
	IRON_EXPECT(!Game.DonateToSect(RedA, -1, 200, Error));

	IRON_EXPECT(State.OfficerOrder(Captain) == nullptr);
	Game.SetDelegated(RedB, true);
	IRON_EXPECT(State.Cities[static_cast<size_t>(RedB)].bDelegated);
	IRON_EXPECT_MSG(State.OfficerOrder(Captain) != nullptr, "the governor plans as soon as the city is delegated");
	Game.SetDelegated(GameTestFixture::City(Game, "blue_a"), true);
	IRON_EXPECT(!State.Cities[static_cast<size_t>(GameTestFixture::City(Game, "blue_a"))].bDelegated);
	IRON_EXPECT(!Game.TavernRumor(RedA).empty());
}

IRON_TEST(GamePrisonerDecisions)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 17))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const int BlueA = GameTestFixture::City(Game, "blue_a");
	const int General = GameTestFixture::Officer(Game, "r_gen");
	const int BlueGeneral = GameTestFixture::Officer(Game, "b_gen");
	const int Blue = GameTestFixture::Faction(Game, "blue");
	const auto Imprison = [&State, RedA, Blue](int Officer) {
		FOfficer& Data = State.Officers[static_cast<size_t>(Officer)];
		Data.Status = EOfficerStatus::Prisoner;
		Data.Faction = Blue;
		Data.Captor = 0;
		Data.City = RedA;
		Data.Army = -1;
		State.PendingPrisoners.push_back(Officer);
	};
	Imprison(BlueGeneral);
	IRON_EXPECT(Game.CanDecidePrisoner(BlueGeneral));
	IRON_EXPECT(!Game.CanDecidePrisoner(General));
	IRON_EXPECT_EQ(Game.PrisonerRecruitChance(BlueGeneral), ClampInt(30 + 85 / 3 - 62 / 2 - 70 / 3, 0, 90));
	std::string Message;
	IRON_EXPECT(Game.DecidePrisoner(BlueGeneral, EPrisonerDecision::Imprison, Message));
	IRON_EXPECT(State.PendingPrisoners.empty());
	IRON_EXPECT(State.Officers[static_cast<size_t>(BlueGeneral)].Status == EOfficerStatus::Prisoner);
	const int Trust = State.Relation(0, Blue).Trust;
	IRON_EXPECT(Game.DecidePrisoner(BlueGeneral, EPrisonerDecision::Release, Message));
	IRON_EXPECT(!Message.empty());
	IRON_EXPECT(State.Officers[static_cast<size_t>(BlueGeneral)].Status == EOfficerStatus::Serving);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(BlueGeneral)].City, BlueA);
	IRON_EXPECT_EQ(State.Relation(0, Blue).Trust, Trust + 10);

	Imprison(BlueGeneral);
	const int Loyalty = State.Officers[static_cast<size_t>(General)].Loyalty;
	IRON_EXPECT(Game.DecidePrisoner(BlueGeneral, EPrisonerDecision::Execute, Message));
	IRON_EXPECT(State.Officers[static_cast<size_t>(BlueGeneral)].Status == EOfficerStatus::Dead);
	IRON_EXPECT_EQ(State.Relation(0, Blue).Trust, Trust);
	IRON_EXPECT_EQ(State.Officers[static_cast<size_t>(General)].Loyalty, Loyalty - 2);
	IRON_EXPECT(!Game.DecidePrisoner(BlueGeneral, EPrisonerDecision::Release, Message));

	// A prisoner whose faction is gone is easier to recruit; failed attempts keep the prisoner.
	const int Wanderer = GameTestFixture::Officer(Game, "f_wander");
	FOfficer& Captive = State.Officers[static_cast<size_t>(Wanderer)];
	Captive.Status = EOfficerStatus::Prisoner;
	Captive.Faction = -1;
	Captive.Captor = 0;
	Captive.City = RedA;
	IRON_EXPECT(Game.PrisonerRecruitChance(Wanderer) > 50);
	IRON_EXPECT(Game.DecidePrisoner(Wanderer, EPrisonerDecision::Recruit, Message));
	IRON_EXPECT(Captive.Status == EOfficerStatus::Serving || Captive.Status == EOfficerStatus::Prisoner);
	if (Captive.Status == EOfficerStatus::Serving)
	{
		IRON_EXPECT_EQ(Captive.Faction, 0);
		IRON_EXPECT_EQ(Captive.City, RedA);
	}
}

IRON_TEST(GameMonthEndEconomy)
{
	FGame Game;
	if (!GameTestFixture::StartQuietGame(Game, 18))
	{
		return;
	}
	FGameState& State = Game.State;
	const int RedA = GameTestFixture::City(Game, "red_a");
	const FCity Before = State.Cities[static_cast<size_t>(RedA)];
	IRON_EXPECT_EQ(Game.GoldIncome(RedA), 500 * 170 / 400);
	IRON_EXPECT_EQ(Game.FoodConsumption(RedA), 10000 / 15);
	IRON_EXPECT_EQ(Game.OfficerUpkeep(RedA), 30);
	IRON_EXPECT_EQ(Game.HarvestYield(RedA), 500 * 30 * 170 / 200);
	Game.EndPlanning();
	IRON_EXPECT(GameTestFixture::FinishMonth(Game) == EStepResult::MonthEnded);
	const FCity& After = State.Cities[static_cast<size_t>(RedA)];
	IRON_EXPECT(Game.IsPlanning());
	IRON_EXPECT_EQ(State.Month, 2);
	IRON_EXPECT_EQ(After.Gold, Before.Gold + 212 - 30);
	IRON_EXPECT_EQ(After.Food, Before.Food - 666);
	IRON_EXPECT_EQ(After.Order, Before.Order - 1);
	IRON_EXPECT_EQ(After.Population, Before.Population + (Before.PopulationMax - Before.Population) * 50 / 4000);
	IRON_EXPECT(State.Orders.size() == State.Orders.size());

	// The month 2 bandit event is waiting for the player.
	const FPendingEvent* Event = Game.CurrentEvent();
	IRON_EXPECT(Event != nullptr);

	// Harvest arrives at the start of month 9.
	GameTestFixture::ClearPlanningPrompts(Game);
	State.Month = 8;
	const int FoodBefore = State.Cities[static_cast<size_t>(RedA)].Food;
	const int Harvest = Game.HarvestYield(RedA);
	const int Eaten = Game.FoodConsumption(RedA);
	State.Orders.clear();
	Game.EndPlanning();
	GameTestFixture::FinishMonth(Game);
	IRON_EXPECT_EQ(State.Month, 9);
	IRON_EXPECT(State.Cities[static_cast<size_t>(RedA)].Food >= FoodBefore - Eaten + Harvest - 200);

	// Starvation: an empty granary costs troops and order.
	GameTestFixture::ClearPlanningPrompts(Game);
	State.Orders.clear();
	FCity& Hungry = State.Cities[static_cast<size_t>(RedA)];
	Hungry.Food = 0;
	const int Troops = Hungry.Troops;
	const int Order = Hungry.Order;
	Game.EndPlanning();
	GameTestFixture::FinishMonth(Game);
	IRON_EXPECT(Hungry.Troops <= Troops - Troops / 10 + 5);
	IRON_EXPECT(Hungry.Order < Order);
	IRON_EXPECT(Hungry.Food >= 0);
}
