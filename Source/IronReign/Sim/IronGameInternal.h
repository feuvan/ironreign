#pragma once

// Private helpers shared by the IronGame*.cpp files (the strategic rules engine). Not part of the public API.

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"

#include <string>
#include <vector>

namespace IronSim
{
	namespace GameRules
	{
		// -----------------------------------------------------------------------------------------
		// Balance numbers (DESIGN.md section 3). Tuned with Tests/TestCampaign.cpp.
		// -----------------------------------------------------------------------------------------
		namespace Balance
		{
			// Economy.
			constexpr int OfficerUpkeep = 10;
			/** Garrisons eat Troops / GarrisonFoodDivisor food per month. */
			constexpr int GarrisonFoodDivisor = 15;
			/** Harvest = Farm x HarvestPerFarm x OrderFactor. */
			constexpr int HarvestPerFarm = 30;
			constexpr int HarvestMonth = 9;
			constexpr int ShortageDesertionPercent = 10;
			constexpr int ShortageOrderLoss = 5;
			constexpr int OrderDecayAbove = 40;
			/** AI gold/harvest multiplier in percent by difficulty (Easy, Normal, Hard). */
			constexpr int AIIncomePercent[3] = {80, 100, 125};

			// Orders.
			constexpr int DevelopCost = 50;
			constexpr int WallsCost = 50;
			constexpr int PatrolCost = 30;
			constexpr int TrainCost = 30;
			constexpr int SearchCost = 20;
			constexpr int RecruitCost = 30;
			constexpr int SectTrainingCost = 50;
			constexpr int AllianceCost = 100;
			constexpr int TruceCost = 50;
			constexpr int DraftBase = 300;
			constexpr int DraftPerCharm = 15;
			constexpr int DraftCostDivisor = 5;
			constexpr int DraftOrderLoss = 3;
			/** Recruits arrive with this training and dilute the garrison's training. */
			constexpr int RecruitTraining = 30;
			/** At most Population / DraftPopulationDivisor recruits per city per month. */
			constexpr int DraftPopulationDivisor = 25;
			constexpr int SectTrainingExp = 60;
			constexpr int SectTechniqueFavor = 50;
			constexpr int ExpPerStatPoint = 100;

			// Market: gold per 100 food in an average month.
			constexpr int FoodBasePrice = 12;

			// Armies.
			constexpr int UnitBaseTroops = 2000;
			constexpr int UnitTroopsPerCommand = 60;
			constexpr int MinUnitTroops = 100;
			constexpr int GarrisonUnitStat = 40;
			constexpr int MaxDefenderOfficers = 5;
			constexpr int MaxGarrisonUnits = 5;
			constexpr int SurrenderPercent = 30;
			constexpr int LootKeepPercent = 50;
			constexpr int FleeChance = 50;
			constexpr int ConquestOrderLoss = 10;

			// Officers, prisoners, diplomacy.
			constexpr int PrisonerEscapeChance = 5;
			constexpr int AllianceMonths = 36;
			constexpr int TruceMonths = 12;
			constexpr int ExecuteTrustLoss = 10;
			constexpr int ReleaseTrustGain = 10;
			/** Monthly chance an AI captor releases a prisoner it failed to recruit. */
			constexpr int AIReleaseChance = 10;

			// AI: attack when local strength exceeds the defender's by this ratio (percent; Easy, Normal, Hard).
			constexpr int AIAttackRatioPercent[3] = {190, 160, 140};
			/** Months over which the AI's appetite for attacking other factions ramps up (independents are fair game at once). */
			constexpr int AIWarmupMonths = 24;
			/** Share of an adjacent same-owner garrison the AI expects to come to a besieged city's aid. */
			constexpr int AISupportPercent = 20;
		}

		constexpr int Unreachable = 1 << 29;

		// -----------------------------------------------------------------------------------------
		// IronGame.cpp: common helpers
		// -----------------------------------------------------------------------------------------

		template <typename ElementType>
		ElementType& At(std::vector<ElementType>& Vector, int Index)
		{
			return Vector[static_cast<size_t>(Index)];
		}

		template <typename ElementType>
		const ElementType& At(const std::vector<ElementType>& Vector, int Index)
		{
			return Vector[static_cast<size_t>(Index)];
		}

		template <typename ElementType>
		int CountOf(const std::vector<ElementType>& Vector)
		{
			return static_cast<int>(Vector.size());
		}

		bool ValidCity(const FGameState& State, int City);
		bool ValidOfficer(const FGameState& State, int Officer);
		bool ValidFaction(const FGameState& State, int Faction);
		bool ValidSect(const FGameState& State, int Sect);
		bool ValidTechnique(const FGameState& State, int Technique);
		bool IsAliveFaction(const FGameState& State, int Faction);
		bool IsPlayerFaction(const FGameState& State, int Faction);
		/** Owner is an AI faction, or the player delegated the city. */
		bool IsAIControlledCity(const FGameState& State, int City);

		/** Returns Check marked as not allowed with Reason. */
		FOrderCheck DenyCheck(FOrderCheck Check, const std::string& Reason);
		int AffinityDistance(int AffinityA, int AffinityB);
		int StatOf(const FOfficer& Officer, EStat Stat);
		void GainExp(FOfficer& Officer, EStat Stat, int Amount);
		/** Monthly cost of food for a garrison. */
		int GarrisonFood(int Troops);
		int ArmyFoodPerDay(int Troops);
		int IncomePercentFor(const FGameState& State, int Faction);
		int CityGoldIncome(const FGameState& State, int City);
		int CityHarvest(const FGameState& State, int City);

		std::string CityLabel(const FGameState& State, int City);
		std::string OfficerLabel(const FGameState& State, int Officer);
		std::string FactionLabel(const FGameState& State, int Faction);

		void LogPlayer(FGameState& State, const std::string& Text, bool bImportant = false);
		void LogWorld(FGameState& State, const std::string& Text, bool bImportant = false);
		/** Logs for the player when Faction is the player's, otherwise as world news. */
		void LogFaction(FGameState& State, int Faction, const std::string& Text, bool bImportant);
		/** Logs for the player when either faction is the player's, otherwise as world news. */
		void LogBetween(FGameState& State, int FactionA, int FactionB, const std::string& Text, bool bImportant);

		std::vector<int> ServingOfficers(const FGameState& State, int Faction);
		std::vector<int> OfficersInCity(const FGameState& State, int City, int Faction);
		int RulerOf(const FGameState& State, int Faction);

		void RemoveFromArmy(FGameState& State, int Officer);
		void PlaceInCity(FGameState& State, int Officer, int City);
		void SetFree(FGameState& State, int Officer, int City);
		void JoinFaction(FGameState& State, int Officer, int Faction, int City, int Loyalty);
		/** Takes Officer prisoner. Falls back to SendOfficerHome when Captor cannot hold prisoners. */
		void CaptureOfficer(FGameState& State, int Officer, int Captor, int City);
		void KillOfficer(FGameState& State, int Officer);
		/** A serving officer escapes to the nearest city of their faction (free if there is none). */
		void SendOfficerHome(FGameState& State, int Officer, int FromCity);
		/** A prisoner returns to their faction, or becomes free. */
		void ReleasePrisoner(FGameState& State, int Prisoner);
		void RemovePendingPrisoner(FGameState& State, int Officer);

		/** Shortest road distances in tenths of a day. With bOwnTerritory only Faction's cities can be passed through. */
		void ShortestPaths(const FGameState& State, int From, int Faction, bool bOwnTerritory, bool bExpandStart, std::vector<int>& OutDist, std::vector<int>& OutPrev);
		/** Route through own territory: OutPath excludes From and ends with Target. */
		bool FindRoute(const FGameState& State, int Faction, int From, int Target, std::vector<int>& OutPath, int& OutTenths);
		/** Nearest city owned by Faction along any roads (FromCity itself when owned), -1 if none. */
		int NearestOwnedCity(const FGameState& State, int Faction, int FromCity);

		void EnsureRuler(FGameState& State, int Faction, bool bAllowDestroy);
		void FixCapital(FGameState& State, int Faction);
		void DestroyFaction(FGameState& State, int Faction);
		/** Eliminates factions without cities and armies and checks victory/defeat. */
		void UpdateFactions(FGameState& State);
		void CheckGameOver(FGameState& State);
		/** Repairs inconsistent references (content errors, old saves). */
		void SanitizeState(FGameState& State);
		void RevealDueOfficers(FGameState& State);

		// -----------------------------------------------------------------------------------------
		// IronGameOrders.cpp
		// -----------------------------------------------------------------------------------------

		int DevelopGain(const FOfficer& Officer);
		int WallsGain(const FOfficer& Officer);
		int PatrolGain(const FOfficer& Officer);
		int TrainGain(const FOfficer& Officer);
		int DraftLimit(const FOfficer& Officer);
		int SearchChance(const FOfficer& Officer);
		int DraftCapacityOf(const FGameState& State, int City);
		int DraftCostOf(int Troops);
		int RecruitChanceOf(const FGameState& State, int Recruiter, int Target);
		int PrisonerRecruitChanceOf(const FGameState& State, int Prisoner, int Captor);
		int AllianceChanceOf(const FGameState& State, int Envoy, int From, int To);
		int TruceChanceOf(const FGameState& State, int Envoy, int From, int To);
		int GiftTrustGain(const FOfficer& Envoy, int Gold);
		std::vector<int> RecruitTargetsOf(const FGameState& State, int City, int Faction);
		std::vector<int> SectsNearOf(const FGameState& State, int City);
		bool IsRecruitTargeted(const FGameState& State, int Target);
		int FoodBuyPriceOf(const FGameState& State);
		int FoodSellPriceOf(const FGameState& State);
		bool TradeFoodRules(FGameState& State, int City, int FoodDelta, std::string& OutError);
		int RewardLoyaltyGain(int Gold);

		FOrderCheck CheckOrderRules(const FGameState& State, const FOrder& Order);
		bool IssueOrderRules(FGameState& State, const FOrder& Order, std::string& OutError);
		bool CancelOrderRules(FGameState& State, int Officer);
		void ExecuteOrders(FGameState& State);

		// -----------------------------------------------------------------------------------------
		// IronGameMilitary.cpp
		// -----------------------------------------------------------------------------------------

		int MaxUnitTroopsOf(const FGameState& State, int Officer);
		std::vector<int> SplitTroops(const FGameState& State, const std::vector<int>& Officers, int Troops);
		std::vector<int> MarchTargetsOf(const FGameState& State, int City, int Faction);
		FOrderCheck CheckArmyRules(const FGameState& State, const FArmyPlan& Plan);
		/** Returns the new army id, or 0 on failure. */
		int FormArmyRules(FGameState& State, const FArmyPlan& Plan, std::string& OutError);
		void BeginExecution(FGameState& State);
		EStepResult StepRules(FGameState& State);
		bool IsPlayerBattle(const FGameState& State, const FPendingBattle& Battle);
		FBattleSetup MakeBattleSetupRules(const FGameState& State, const FPendingBattle& Battle);
		/** Applies Result to the front of the battle queue (which must be Battle) and pops it. */
		void ApplyBattleResult(FGameState& State, const FPendingBattle& Battle, const FBattleResult& Result);
		void MergeArmy(FGameState& State, int ArmyId, int City);
		void StartReturn(FGameState& State, int ArmyId);
		/** Total troops of hostile armies marching on City. */
		int IncomingHostileTroops(const FGameState& State, int City, int Faction);

		// -----------------------------------------------------------------------------------------
		// IronGameMonth.cpp
		// -----------------------------------------------------------------------------------------

		void EndMonthRules(FGameState& State);
		/** Starts a planning phase: events, then AI planning. */
		void BeginPlanning(FGameState& State);
		int MonthsUntilHarvest(int Month);

		// -----------------------------------------------------------------------------------------
		// IronGameEvents.cpp
		// -----------------------------------------------------------------------------------------

		void CheckEventsRules(FGameState& State);
		bool CanChooseRules(const FGameState& State, int ChoiceIndex);
		void ChooseRules(FGameState& State, int ChoiceIndex);
		/** An AI faction proposes an alliance (or a truce) to the player through a pending event. */
		void QueueProposal(FGameState& State, int FromFaction, bool bAlliance);
		/** Best strategist serving the faction (the player's advisor), -1 if none. */
		int AdvisorOf(const FGameState& State, int Faction);

		// -----------------------------------------------------------------------------------------
		// IronGameAI.cpp
		// -----------------------------------------------------------------------------------------

		/** Plans every AI faction and the player's delegated cities. */
		void PlanAllAI(FGameState& State);
		/** Plans one player city that was just delegated. */
		void PlanDelegatedCity(FGameState& State, int City);
		/** Month end: AI captors recruit or release their prisoners. */
		void DecideAIPrisoners(FGameState& State);
	}
}
