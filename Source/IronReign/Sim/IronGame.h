#pragma once

#include "Sim/IronBattle.h"
#include "Sim/IronState.h"

#include <string>
#include <vector>

namespace IronSim
{
	/** Validation and preview for an order before it is issued. */
	struct FOrderCheck
	{
		bool bAllowed = false;
		/** Why the order is not allowed (empty when allowed). */
		std::string Reason;
		/** Gold cost paid when issued. */
		int Cost = 0;
		/** Expected result for the UI, e.g. "Farmland +12" or "Success 64%". */
		std::string Preview;
		/** 0..100 for chance-based orders (recruit, search, diplomacy), -1 otherwise. */
		int SuccessChance = -1;
	};

	/** Parameters for marching an army out of a city. */
	struct FArmyPlan
	{
		int City = -1;
		/** Officers[0] commands. Up to MaxArmyUnits. */
		std::vector<int> Officers;
		int Troops = 0;
		int Food = 0;
		int Target = -1;
	};

	enum class EStepResult : uint8_t
	{
		Idle,          // Not in the execution phase.
		DayAdvanced,   // One day passed; call Step() again.
		PlayerBattle,  // A battle involving the player is waiting: see PendingPlayerBattle().
		MonthEnded,    // Day 30 finished; a new planning phase began (check events/prisoners).
		GameOver       // Victory or defeat; see State.Outcome.
	};

	/**
	 * Rules engine for the strategic layer: a Romance of the Three Kingdoms IX style monthly loop.
	 *
	 * Planning: the player assigns officers to orders, forms armies, trades, rewards, answers events.
	 * Execution: EndPlanning() runs domestic orders, then Step() plays days 1..30 one at a time while
	 * armies march along roads. Battles involving the player pause the loop (EStepResult::PlayerBattle)
	 * so the UI can run the tactical battle; all other battles are resolved by FBattle's AI.
	 * After day 30 the month ends: income, harvest, upkeep, loyalty, events and AI planning.
	 */
	class FGame
	{
	public:
		FGameState State;

		// ----- Session -----
		bool NewGame(const FJson& Scenario, int PlayerFaction, EDifficulty Difficulty, uint64_t Seed, std::string& OutError);
		bool LoadGame(const FJson& Save, std::string& OutError);
		FJson SaveGame() const;

		// ----- Planning phase: queries -----
		bool IsPlanning() const;
		bool IsPlayerCity(int City) const;
		/** Serving player officers in City without an order this month and not marching. */
		std::vector<int> IdleOfficers(int City) const;
		FOrderCheck CheckOrder(const FOrder& Order) const;
		/** Orders issued by the player's faction this month. */
		std::vector<FOrder> PlayerOrders() const;
		/** Free officers in or next to City, and enemy officers in adjacent cities. */
		std::vector<int> RecruitTargets(int City) const;
		/** Other cities owned by the player. */
		std::vector<int> MoveDestinations(int City) const;
		/** Living factions other than the player. */
		std::vector<int> DiplomacyTargets() const;
		/** Sects reachable from City (same or adjacent city). */
		std::vector<int> SectsNear(int City) const;
		int DraftCapacity(int City) const;
		int DraftCost(int Troops) const;
		int RecruitChance(int Recruiter, int Target) const;

		// ----- Planning phase: orders -----
		bool IssueOrder(const FOrder& Order, std::string& OutError);
		/** Cancels the officer's order this month and refunds its cost. */
		bool CancelOrder(int Officer);

		// ----- Planning phase: military -----
		int MaxUnitTroops(int Officer) const;
		/** Cities an army from City may target (neighbors and cities reachable through own territory). */
		std::vector<int> MarchTargets(int City) const;
		/** Estimated march time in days from City to Target, -1 if unreachable. */
		int MarchDays(int City, int Target) const;
		int ArmyDailyFood(int Troops) const;
		FOrderCheck CheckArmy(const FArmyPlan& Plan) const;
		bool FormArmy(const FArmyPlan& Plan, std::string& OutError);
		/** Only armies formed this planning phase can be disbanded; everything is refunded. */
		bool DisbandArmy(int ArmyId);

		// ----- Planning phase: immediate actions -----
		/** Gold per 100 food. Prices follow the harvest cycle. */
		int FoodBuyPrice() const;
		int FoodSellPrice() const;
		/** Positive FoodDelta buys food, negative sells it. */
		bool TradeFood(int City, int FoodDelta, std::string& OutError);
		bool RewardOfficer(int Officer, int Gold, std::string& OutError);
		bool DonateToSect(int City, int Sect, int Gold, std::string& OutError);
		void SetDelegated(int City, bool bDelegated);
		int PrisonerRecruitChance(int Prisoner) const;
		/** Returns false if the decision could not be applied; a failed recruit keeps the prisoner imprisoned. */
		bool DecidePrisoner(int Prisoner, EPrisonerDecision Decision, std::string& OutMessage);
		/** Hints about hidden officers and the realm, for the tavern. */
		std::string TavernRumor(int City) const;

		// ----- Events -----
		const FPendingEvent* CurrentEvent() const;
		bool CanChoose(int ChoiceIndex) const;
		void ChooseEventOption(int ChoiceIndex);

		// ----- Execution phase -----
		/** Runs all queued orders and starts day 1. */
		void EndPlanning();
		EStepResult Step();
		const FPendingBattle* PendingPlayerBattle() const;
		/** True if the player's faction is the attacking side of the battle. */
		bool IsPlayerAttacker(const FPendingBattle& Battle) const;
		FBattleSetup MakeBattleSetup(const FPendingBattle& Battle) const;
		/** Applies a battle the player fought in the tactical screen. */
		void ResolvePlayerBattle(const FBattleResult& Result);
		/** Lets the AI fight the pending player battle. */
		void AutoResolvePlayerBattle();

		// ----- Info -----
		/** "Year 212, Month 3 (Spring)" or with the day during execution. */
		std::string DateText() const;
		int CityCount(int Faction) const;

		// ----- Additions (rules engineer) -----
		/** Expected gold income of City at the end of this month (difficulty scaling included). */
		int GoldIncome(int City) const;
		/** Expected food from City's next harvest (month 9). */
		int HarvestYield(int City) const;
		/** Food City's garrison eats per month. */
		int FoodConsumption(int City) const;
		/** Gold City pays its officers (including those marching from it) per month. */
		int OfficerUpkeep(int City) const;
		/** Loyalty an officer gains from a reward of Gold (for the reward dialog preview). */
		int RewardLoyaltyGain(int Gold) const;
		/** True if Prisoner is held by the player and DecidePrisoner can be called for them. */
		bool CanDecidePrisoner(int Prisoner) const;
	};
}
