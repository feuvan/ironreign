#include "Sim/IronGame.h"

#include "Sim/IronGameInternal.h"
#include "Sim/IronLocale.h"

#include <algorithm>
#include <cstdlib>

namespace IronSim
{
	// =============================================================================================
	// Shared helpers
	// =============================================================================================

	namespace GameRules
	{
		bool ValidCity(const FGameState& State, int City)
		{
			return City >= 0 && City < CountOf(State.Cities);
		}

		bool ValidOfficer(const FGameState& State, int Officer)
		{
			return Officer >= 0 && Officer < CountOf(State.Officers);
		}

		bool ValidFaction(const FGameState& State, int Faction)
		{
			return Faction >= 0 && Faction < CountOf(State.Factions);
		}

		bool ValidSect(const FGameState& State, int Sect)
		{
			return Sect >= 0 && Sect < CountOf(State.Sects);
		}

		bool ValidTechnique(const FGameState& State, int Technique)
		{
			return Technique >= 0 && Technique < CountOf(State.Techniques);
		}

		bool IsAliveFaction(const FGameState& State, int Faction)
		{
			return ValidFaction(State, Faction) && At(State.Factions, Faction).bAlive;
		}

		bool IsPlayerFaction(const FGameState& State, int Faction)
		{
			return Faction >= 0 && Faction == State.PlayerFaction;
		}

		FOrderCheck DenyCheck(FOrderCheck Check, const std::string& Reason)
		{
			Check.bAllowed = false;
			Check.Reason = Reason;
			return Check;
		}

		int AffinityDistance(int AffinityA, int AffinityB)
		{
			const int Delta = std::abs(AffinityA - AffinityB) % 150;
			return std::min(Delta, 150 - Delta);
		}

		int StatOf(const FOfficer& Officer, EStat Stat)
		{
			return Officer.Stats[StatIndex(Stat)];
		}

		void GainExp(FOfficer& Officer, EStat Stat, int Amount)
		{
			const int Index = StatIndex(Stat);
			if (Amount <= 0)
			{
				return;
			}
			if (Officer.Stats[Index] >= MaxStatValue)
			{
				Officer.StatExp[Index] = 0;
				return;
			}
			Officer.StatExp[Index] += Amount;
			while (Officer.StatExp[Index] >= Balance::ExpPerStatPoint && Officer.Stats[Index] < MaxStatValue)
			{
				Officer.StatExp[Index] -= Balance::ExpPerStatPoint;
				++Officer.Stats[Index];
			}
			if (Officer.Stats[Index] >= MaxStatValue)
			{
				Officer.StatExp[Index] = 0;
			}
		}

		int GarrisonFood(int Troops)
		{
			return std::max(0, Troops) / Balance::GarrisonFoodDivisor;
		}

		int ArmyFoodPerDay(int Troops)
		{
			return (std::max(0, Troops) + 299) / 300;
		}

		int IncomePercentFor(const FGameState& State, int Faction)
		{
			if (Faction < 0 || IsPlayerFaction(State, Faction))
			{
				return 100;
			}
			return Balance::AIIncomePercent[ClampInt(static_cast<int>(State.Difficulty), 0, 2)];
		}

		int CityGoldIncome(const FGameState& State, int City)
		{
			if (!ValidCity(State, City))
			{
				return 0;
			}
			const FCity& Data = At(State.Cities, City);
			if (Data.Owner < 0)
			{
				return 0;
			}
			// Commerce x 0.5 x OrderFactor, OrderFactor = 0.5 + Order / 200.
			const long long Base = static_cast<long long>(Data.Commerce) * (100 + Data.Order) / 400;
			return static_cast<int>(Base * IncomePercentFor(State, Data.Owner) / 100);
		}

		int CityHarvest(const FGameState& State, int City)
		{
			if (!ValidCity(State, City))
			{
				return 0;
			}
			const FCity& Data = At(State.Cities, City);
			const long long Base = static_cast<long long>(Data.Farm) * Balance::HarvestPerFarm * (100 + Data.Order) / 200;
			return static_cast<int>(Base * IncomePercentFor(State, Data.Owner) / 100);
		}

		std::string CityLabel(const FGameState& State, int City)
		{
			return ValidCity(State, City) ? NameOf(At(State.Cities, City)) : Loc("common.unknownCity", "an unknown city");
		}

		std::string OfficerLabel(const FGameState& State, int Officer)
		{
			return ValidOfficer(State, Officer) ? NameOf(At(State.Officers, Officer)) : Loc("common.unknownOfficer", "an unknown officer");
		}

		std::string FactionLabel(const FGameState& State, int Faction)
		{
			return ValidFaction(State, Faction) ? NameOf(At(State.Factions, Faction)) : Loc("faction.independent", "Independents");
		}

		void LogPlayer(FGameState& State, const std::string& Text, bool bImportant)
		{
			if (State.PlayerFaction >= 0)
			{
				State.AddLog(State.PlayerFaction, bImportant, Text);
			}
		}

		void LogWorld(FGameState& State, const std::string& Text, bool bImportant)
		{
			State.AddLog(-1, bImportant, Text);
		}

		void LogFaction(FGameState& State, int Faction, const std::string& Text, bool bImportant)
		{
			if (IsPlayerFaction(State, Faction))
			{
				State.AddLog(Faction, bImportant, Text);
			}
			else
			{
				State.AddLog(-1, bImportant, Text);
			}
		}

		void LogBetween(FGameState& State, int FactionA, int FactionB, const std::string& Text, bool bImportant)
		{
			if (IsPlayerFaction(State, FactionA) || IsPlayerFaction(State, FactionB))
			{
				State.AddLog(State.PlayerFaction, bImportant, Text);
			}
			else
			{
				State.AddLog(-1, bImportant, Text);
			}
		}

		std::vector<int> ServingOfficers(const FGameState& State, int Faction)
		{
			std::vector<int> Result;
			if (Faction < 0)
			{
				return Result;
			}
			for (int Index = 0; Index < CountOf(State.Officers); ++Index)
			{
				const FOfficer& Officer = At(State.Officers, Index);
				if (Officer.Status == EOfficerStatus::Serving && Officer.Faction == Faction)
				{
					Result.push_back(Index);
				}
			}
			return Result;
		}

		std::vector<int> OfficersInCity(const FGameState& State, int City, int Faction)
		{
			std::vector<int> Result;
			if (Faction < 0)
			{
				return Result;
			}
			for (int Index = 0; Index < CountOf(State.Officers); ++Index)
			{
				const FOfficer& Officer = At(State.Officers, Index);
				if (Officer.Status == EOfficerStatus::Serving && Officer.Faction == Faction && Officer.City == City && Officer.Army < 0)
				{
					Result.push_back(Index);
				}
			}
			return Result;
		}

		int RulerOf(const FGameState& State, int Faction)
		{
			if (!ValidFaction(State, Faction))
			{
				return -1;
			}
			const int Ruler = At(State.Factions, Faction).Ruler;
			return ValidOfficer(State, Ruler) ? Ruler : -1;
		}

		void RemovePendingPrisoner(FGameState& State, int Officer)
		{
			State.PendingPrisoners.erase(std::remove(State.PendingPrisoners.begin(), State.PendingPrisoners.end(), Officer), State.PendingPrisoners.end());
		}

		void RemoveFromArmy(FGameState& State, int Officer)
		{
			if (!ValidOfficer(State, Officer))
			{
				return;
			}
			FOfficer& Data = At(State.Officers, Officer);
			if (Data.Army >= 0)
			{
				if (FArmy* Army = State.FindArmy(Data.Army))
				{
					for (size_t Index = 0; Index < Army->Units.size(); ++Index)
					{
						if (Army->Units[Index].Officer == Officer)
						{
							Army->Units.erase(Army->Units.begin() + static_cast<std::ptrdiff_t>(Index));
							break;
						}
					}
				}
			}
			Data.Army = -1;
		}

		void PlaceInCity(FGameState& State, int Officer, int City)
		{
			RemoveFromArmy(State, Officer);
			At(State.Officers, Officer).City = City;
		}

		void SetFree(FGameState& State, int Officer, int City)
		{
			RemoveFromArmy(State, Officer);
			FOfficer& Data = At(State.Officers, Officer);
			Data.Status = EOfficerStatus::Free;
			Data.Faction = -1;
			Data.Captor = -1;
			Data.City = ValidCity(State, City) ? City : (ValidCity(State, Data.City) ? Data.City : 0);
			Data.Loyalty = 50;
			RemovePendingPrisoner(State, Officer);
		}

		void JoinFaction(FGameState& State, int Officer, int Faction, int City, int Loyalty)
		{
			RemoveFromArmy(State, Officer);
			FOfficer& Data = At(State.Officers, Officer);
			Data.Status = EOfficerStatus::Serving;
			Data.Faction = Faction;
			Data.Captor = -1;
			Data.City = City;
			Data.Loyalty = ClampInt(Loyalty, 0, 100);
			RemovePendingPrisoner(State, Officer);
		}

		void SendOfficerHome(FGameState& State, int Officer, int FromCity)
		{
			const FOfficer& Data = At(State.Officers, Officer);
			const int Start = ValidCity(State, FromCity) ? FromCity : Data.City;
			const int Refuge = NearestOwnedCity(State, Data.Faction, Start);
			if (Data.Status == EOfficerStatus::Serving && Refuge >= 0)
			{
				PlaceInCity(State, Officer, Refuge);
			}
			else
			{
				SetFree(State, Officer, Start);
			}
		}

		void CaptureOfficer(FGameState& State, int Officer, int Captor, int City)
		{
			if (!ValidOfficer(State, Officer))
			{
				return;
			}
			if (!IsAliveFaction(State, Captor) || !ValidCity(State, City) || At(State.Cities, City).Owner != Captor)
			{
				SendOfficerHome(State, Officer, City);
				return;
			}
			const bool bWasRuler = State.IsRuler(Officer);
			const int Former = At(State.Officers, Officer).Faction;
			RemoveFromArmy(State, Officer);
			FOfficer& Data = At(State.Officers, Officer);
			Data.Status = EOfficerStatus::Prisoner;
			Data.Captor = Captor;
			Data.City = City;
			Data.Faction = Former;
			if (IsPlayerFaction(State, Captor))
			{
				RemovePendingPrisoner(State, Officer);
				State.PendingPrisoners.push_back(Officer);
				LogPlayer(State, LocF("log.officer.weCaptured", "{officer} of the {faction} has been taken prisoner and awaits your judgement.", {{"officer", NameOf(Data)}, {"faction", FactionLabel(State, Former)}}), false);
			}
			if (IsPlayerFaction(State, Former))
			{
				LogPlayer(State, LocF("log.officer.captured", "{officer} has been captured by the {faction}.", {{"officer", NameOf(Data)}, {"faction", FactionLabel(State, Captor)}}), true);
			}
			if (bWasRuler)
			{
				LogBetween(State, Former, Captor, LocF("log.ruler.captured", "{officer}, ruler of the {faction}, has been taken prisoner!", {{"officer", NameOf(Data)}, {"faction", FactionLabel(State, Former)}}), true);
				EnsureRuler(State, Former, true);
			}
		}

		void KillOfficer(FGameState& State, int Officer)
		{
			if (!ValidOfficer(State, Officer))
			{
				return;
			}
			const bool bWasRuler = State.IsRuler(Officer);
			const int Former = At(State.Officers, Officer).Status == EOfficerStatus::Serving ? At(State.Officers, Officer).Faction : -1;
			RemoveFromArmy(State, Officer);
			FOfficer& Data = At(State.Officers, Officer);
			Data.Status = EOfficerStatus::Dead;
			Data.City = -1;
			Data.Army = -1;
			Data.Captor = -1;
			Data.Faction = -1;
			RemovePendingPrisoner(State, Officer);
			if (bWasRuler)
			{
				EnsureRuler(State, Former, true);
			}
		}

		void ReleasePrisoner(FGameState& State, int Prisoner)
		{
			FOfficer& Data = At(State.Officers, Prisoner);
			const int Home = Data.Faction;
			const int From = Data.City;
			if (IsAliveFaction(State, Home))
			{
				const int Destination = NearestOwnedCity(State, Home, From);
				if (Destination >= 0)
				{
					JoinFaction(State, Prisoner, Home, Destination, Data.Loyalty);
					return;
				}
			}
			SetFree(State, Prisoner, From);
		}

		void ShortestPaths(const FGameState& State, int From, int Faction, bool bOwnTerritory, bool bExpandStart, std::vector<int>& OutDist, std::vector<int>& OutPrev)
		{
			const int Count = CountOf(State.Cities);
			OutDist.assign(static_cast<size_t>(Count), Unreachable);
			OutPrev.assign(static_cast<size_t>(Count), -1);
			if (!ValidCity(State, From))
			{
				return;
			}
			std::vector<bool> Done(static_cast<size_t>(Count), false);
			At(OutDist, From) = 0;
			for (int Iteration = 0; Iteration < Count; ++Iteration)
			{
				int Best = -1;
				for (int City = 0; City < Count; ++City)
				{
					if (!Done[static_cast<size_t>(City)] && At(OutDist, City) < Unreachable && (Best < 0 || At(OutDist, City) < At(OutDist, Best)))
					{
						Best = City;
					}
				}
				if (Best < 0)
				{
					break;
				}
				Done[static_cast<size_t>(Best)] = true;
				const bool bExpand = Best == From ? (bExpandStart || !bOwnTerritory) : (!bOwnTerritory || At(State.Cities, Best).Owner == Faction);
				if (!bExpand)
				{
					continue;
				}
				for (const FRoad& Road : State.Roads)
				{
					int Other = -1;
					if (Road.A == Best)
					{
						Other = Road.B;
					}
					else if (Road.B == Best)
					{
						Other = Road.A;
					}
					if (!ValidCity(State, Other))
					{
						continue;
					}
					const int Candidate = At(OutDist, Best) + std::max(1, Road.Days) * 10;
					if (Candidate < At(OutDist, Other))
					{
						At(OutDist, Other) = Candidate;
						At(OutPrev, Other) = Best;
					}
				}
			}
		}

		bool FindRoute(const FGameState& State, int Faction, int From, int Target, std::vector<int>& OutPath, int& OutTenths)
		{
			OutPath.clear();
			OutTenths = 0;
			if (!ValidCity(State, From) || !ValidCity(State, Target) || From == Target)
			{
				return false;
			}
			std::vector<int> Dist;
			std::vector<int> Prev;
			ShortestPaths(State, From, Faction, true, true, Dist, Prev);
			if (At(Dist, Target) >= Unreachable)
			{
				return false;
			}
			for (int City = Target; City != From && City >= 0; City = At(Prev, City))
			{
				OutPath.push_back(City);
			}
			std::reverse(OutPath.begin(), OutPath.end());
			OutTenths = At(Dist, Target);
			return true;
		}

		int NearestOwnedCity(const FGameState& State, int Faction, int FromCity)
		{
			if (Faction < 0)
			{
				return -1;
			}
			if (!ValidCity(State, FromCity))
			{
				const int Capital = ValidFaction(State, Faction) ? At(State.Factions, Faction).Capital : -1;
				if (ValidCity(State, Capital) && At(State.Cities, Capital).Owner == Faction)
				{
					return Capital;
				}
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					if (At(State.Cities, City).Owner == Faction)
					{
						return City;
					}
				}
				return -1;
			}
			std::vector<int> Dist;
			std::vector<int> Prev;
			ShortestPaths(State, FromCity, Faction, false, true, Dist, Prev);
			int Best = -1;
			for (int City = 0; City < CountOf(State.Cities); ++City)
			{
				if (At(State.Cities, City).Owner == Faction && At(Dist, City) < Unreachable && (Best < 0 || At(Dist, City) < At(Dist, Best)))
				{
					Best = City;
				}
			}
			if (Best < 0)
			{
				// Disconnected map: any city of the faction.
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					if (At(State.Cities, City).Owner == Faction)
					{
						return City;
					}
				}
			}
			return Best;
		}

		void EnsureRuler(FGameState& State, int Faction, bool bAllowDestroy)
		{
			if (!IsAliveFaction(State, Faction))
			{
				return;
			}
			FFaction& Data = At(State.Factions, Faction);
			if (ValidOfficer(State, Data.Ruler))
			{
				FOfficer& Ruler = At(State.Officers, Data.Ruler);
				if (Ruler.Status == EOfficerStatus::Serving && Ruler.Faction == Faction)
				{
					Ruler.Loyalty = 100;
					return;
				}
			}
			int Best = -1;
			int BestScore = -1;
			for (const int Officer : ServingOfficers(State, Faction))
			{
				const FOfficer& Candidate = At(State.Officers, Officer);
				const int Score = StatOf(Candidate, EStat::Charm) + StatOf(Candidate, EStat::Command);
				if (Score > BestScore)
				{
					Best = Officer;
					BestScore = Score;
				}
			}
			const bool bHadRuler = ValidOfficer(State, Data.Ruler);
			if (Best >= 0)
			{
				const int Previous = Data.Ruler;
				Data.Ruler = Best;
				At(State.Officers, Best).Loyalty = 100;
				if (bHadRuler)
				{
					LogFaction(State, Faction, LocF("log.ruler.succession", "{officer} succeeds {previous} as ruler of the {faction}.", {{"officer", NameOf(At(State.Officers, Best))}, {"previous", OfficerLabel(State, Previous)}, {"faction", NameOf(Data)}}), true);
				}
				return;
			}
			if (bAllowDestroy)
			{
				DestroyFaction(State, Faction);
			}
		}

		void FixCapital(FGameState& State, int Faction)
		{
			if (!IsAliveFaction(State, Faction))
			{
				return;
			}
			FFaction& Data = At(State.Factions, Faction);
			if (ValidCity(State, Data.Capital) && At(State.Cities, Data.Capital).Owner == Faction)
			{
				return;
			}
			int Best = -1;
			for (int City = 0; City < CountOf(State.Cities); ++City)
			{
				const FCity& Candidate = At(State.Cities, City);
				if (Candidate.Owner == Faction && (Best < 0 || Candidate.Population > At(State.Cities, Best).Population))
				{
					Best = City;
				}
			}
			if (Best >= 0)
			{
				Data.Capital = Best;
				LogFaction(State, Faction, LocF("log.capital.moved", "The {faction} moves its capital to {city}.", {{"faction", NameOf(Data)}, {"city", CityLabel(State, Best)}}), false);
			}
		}

		void DestroyFaction(FGameState& State, int Faction)
		{
			if (!IsAliveFaction(State, Faction))
			{
				return;
			}
			FFaction& Data = At(State.Factions, Faction);
			Data.bAlive = false;
			for (FCity& City : State.Cities)
			{
				if (City.Owner == Faction)
				{
					City.Owner = -1;
					City.bDelegated = false;
				}
			}
			// Armies scatter; their officers become free where they stand.
			for (size_t Index = 0; Index < State.Armies.size();)
			{
				if (State.Armies[Index].Faction != Faction)
				{
					++Index;
					continue;
				}
				const FArmy Army = State.Armies[Index];
				State.Armies.erase(State.Armies.begin() + static_cast<std::ptrdiff_t>(Index));
				for (const FArmyUnit& Unit : Army.Units)
				{
					if (ValidOfficer(State, Unit.Officer))
					{
						At(State.Officers, Unit.Officer).Army = -1;
						SetFree(State, Unit.Officer, Army.Node);
					}
				}
			}
			for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
			{
				FOfficer& Member = At(State.Officers, Officer);
				if (Member.Status == EOfficerStatus::Serving && Member.Faction == Faction)
				{
					SetFree(State, Officer, Member.City);
				}
				else if (Member.Status == EOfficerStatus::Prisoner && Member.Captor == Faction)
				{
					ReleasePrisoner(State, Officer);
				}
				else if (Member.Status == EOfficerStatus::Prisoner && Member.Faction == Faction)
				{
					At(State.Officers, Officer).Faction = -1;
				}
			}
			for (int Other = 0; Other < CountOf(State.Factions); ++Other)
			{
				if (Other != Faction)
				{
					FRelation& Relation = State.Relation(Faction, Other);
					Relation.AllianceMonths = 0;
					Relation.TruceMonths = 0;
				}
			}
			State.Orders.erase(std::remove_if(State.Orders.begin(), State.Orders.end(), [Faction](const FOrder& Order) { return Order.TargetFaction == Faction; }), State.Orders.end());
			if (IsPlayerFaction(State, Faction))
			{
				LogPlayer(State, LocF("log.faction.destroyedPlayer", "The {faction} has fallen. Your cause is lost.", {{"faction", NameOf(Data)}}), true);
			}
			else
			{
				LogWorld(State, LocF("log.faction.destroyed", "The {faction} has been destroyed.", {{"faction", NameOf(Data)}}), true);
			}
			CheckGameOver(State);
		}

		void UpdateFactions(FGameState& State)
		{
			for (int Faction = 0; Faction < CountOf(State.Factions); ++Faction)
			{
				if (!IsAliveFaction(State, Faction))
				{
					continue;
				}
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
				if (!bHasCity && !bHasArmy)
				{
					DestroyFaction(State, Faction);
					continue;
				}
				EnsureRuler(State, Faction, false);
				FixCapital(State, Faction);
			}
			CheckGameOver(State);
		}

		void CheckGameOver(FGameState& State)
		{
			if (State.Phase == EPhase::GameOver)
			{
				return;
			}
			struct FEndGuard
			{
				FGameState& Target;
				~FEndGuard()
				{
					if (Target.Phase == EPhase::GameOver)
					{
						// Nothing is left to fight once the game is decided.
						Target.BattleQueue.clear();
						Target.bDayInProgress = false;
					}
				}
			} Guard{State};
			int Alive = 0;
			for (const FFaction& Faction : State.Factions)
			{
				Alive += Faction.bAlive ? 1 : 0;
			}
			if (State.PlayerFaction < 0)
			{
				// Spectator game (no player): ends when one faction remains.
				if (Alive <= 1)
				{
					State.Phase = EPhase::GameOver;
					State.Outcome = EOutcome::None;
				}
				return;
			}
			if (!IsAliveFaction(State, State.PlayerFaction))
			{
				State.Phase = EPhase::GameOver;
				State.Outcome = EOutcome::Defeat;
				LogPlayer(State, Loc("log.game.defeat", "Defeat. Your faction has been wiped from the map."), true);
				return;
			}
			if (Alive == 1)
			{
				State.Phase = EPhase::GameOver;
				State.Outcome = EOutcome::Victory;
				LogPlayer(State, LocF("log.game.victory", "Victory! The {faction} has united the realm.", {{"faction", FactionLabel(State, State.PlayerFaction)}}), true);
			}
		}

		void RevealDueOfficers(FGameState& State)
		{
			for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
			{
				FOfficer& Data = At(State.Officers, Officer);
				if (Data.Status != EOfficerStatus::Unborn || Data.AppearYear > State.Year)
				{
					continue;
				}
				Data.Status = EOfficerStatus::Free;
				Data.Faction = -1;
				if (!ValidCity(State, Data.City))
				{
					Data.City = State.Rng.Range(0, CountOf(State.Cities) - 1);
				}
				if (Data.AppearYear > 0)
				{
					LogWorld(State, LocF("log.officer.appears", "Word spreads of a new talent: {officer} has been seen in {city}.", {{"officer", NameOf(Data)}, {"city", CityLabel(State, Data.City)}}), false);
				}
			}
		}

		void SanitizeState(FGameState& State)
		{
			const size_t FactionCount = State.Factions.size();
			if (State.Relations.size() != FactionCount * FactionCount)
			{
				State.Relations.resize(FactionCount * FactionCount);
			}
			for (FSect& Sect : State.Sects)
			{
				Sect.Favor.resize(FactionCount, 0);
			}
			if (State.Cities.empty())
			{
				return;
			}

			// Army units must reference officers that march with them.
			for (FArmy& Army : State.Armies)
			{
				std::vector<FArmyUnit> Kept;
				for (const FArmyUnit& Unit : Army.Units)
				{
					bool bDuplicate = false;
					for (const FArmyUnit& Other : Kept)
					{
						bDuplicate = bDuplicate || Other.Officer == Unit.Officer;
					}
					if (!bDuplicate && ValidOfficer(State, Unit.Officer))
					{
						FOfficer& Officer = At(State.Officers, Unit.Officer);
						if (Officer.Status == EOfficerStatus::Serving && Officer.Faction == Army.Faction)
						{
							Officer.Army = Army.Id;
							Officer.City = -1;
							Kept.push_back(Unit);
						}
					}
				}
				Army.Units = Kept;
			}
			for (size_t Index = 0; Index < State.Armies.size();)
			{
				const FArmy& Army = State.Armies[Index];
				const bool bBroken = Army.Units.empty() || !ValidFaction(State, Army.Faction) || !ValidCity(State, Army.Node)
					|| (Army.Road >= 0 && Army.Road >= CountOf(State.Roads));
				if (bBroken)
				{
					const FArmy Removed = Army;
					State.Armies.erase(State.Armies.begin() + static_cast<std::ptrdiff_t>(Index));
					for (const FArmyUnit& Unit : Removed.Units)
					{
						At(State.Officers, Unit.Officer).Army = -1;
						At(State.Officers, Unit.Officer).City = Removed.Node;
					}
					continue;
				}
				State.NextArmyId = std::max(State.NextArmyId, Army.Id + 1);
				++Index;
			}

			for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
			{
				FOfficer& Data = At(State.Officers, Officer);
				Data.Loyalty = ClampInt(Data.Loyalty, 0, 100);
				switch (Data.Status)
				{
				case EOfficerStatus::Serving:
					if (!IsAliveFaction(State, Data.Faction))
					{
						SetFree(State, Officer, Data.City);
						break;
					}
					if (Data.Army >= 0)
					{
						const FArmy* Army = State.FindArmy(Data.Army);
						bool bListed = false;
						if (Army)
						{
							for (const FArmyUnit& Unit : Army->Units)
							{
								bListed = bListed || Unit.Officer == Officer;
							}
						}
						if (bListed)
						{
							Data.City = -1;
							break;
						}
						Data.Army = -1;
					}
					if (!ValidCity(State, Data.City) || At(State.Cities, Data.City).Owner != Data.Faction)
					{
						const int Refuge = NearestOwnedCity(State, Data.Faction, Data.City);
						if (Refuge >= 0)
						{
							Data.City = Refuge;
						}
						else
						{
							SetFree(State, Officer, Data.City);
						}
					}
					break;
				case EOfficerStatus::Prisoner:
					Data.Army = -1;
					if (!IsAliveFaction(State, Data.Captor) || !ValidCity(State, Data.City) || At(State.Cities, Data.City).Owner != Data.Captor)
					{
						if (!ValidCity(State, Data.City))
						{
							Data.City = 0;
						}
						ReleasePrisoner(State, Officer);
					}
					break;
				case EOfficerStatus::Free:
				case EOfficerStatus::Hidden:
				case EOfficerStatus::Unborn:
					Data.Army = -1;
					Data.Faction = -1;
					Data.Captor = -1;
					if (!ValidCity(State, Data.City))
					{
						Data.City = 0;
					}
					break;
				case EOfficerStatus::Dead:
					Data.Army = -1;
					Data.City = -1;
					break;
				}
			}

			std::vector<int> Pending;
			for (const int Officer : State.PendingPrisoners)
			{
				if (ValidOfficer(State, Officer) && At(State.Officers, Officer).Status == EOfficerStatus::Prisoner && IsPlayerFaction(State, At(State.Officers, Officer).Captor)
					&& std::find(Pending.begin(), Pending.end(), Officer) == Pending.end())
				{
					Pending.push_back(Officer);
				}
			}
			State.PendingPrisoners = Pending;

			for (int Faction = 0; Faction < CountOf(State.Factions); ++Faction)
			{
				if (!IsAliveFaction(State, Faction))
				{
					continue;
				}
				EnsureRuler(State, Faction, false);
				FixCapital(State, Faction);
			}
		}
	}

	// =============================================================================================
	// FGame: session
	// =============================================================================================

	bool FGame::NewGame(const FJson& Scenario, int PlayerFaction, EDifficulty Difficulty, uint64_t Seed, std::string& OutError)
	{
		FGameState Loaded;
		if (!LoadGameState(Scenario, Loaded, OutError))
		{
			return false;
		}
		if (PlayerFaction < -1 || PlayerFaction >= GameRules::CountOf(Loaded.Factions))
		{
			OutError = Loc("error.newGame.faction", "The chosen faction does not exist in this scenario.");
			return false;
		}
		if (PlayerFaction >= 0 && !GameRules::At(Loaded.Factions, PlayerFaction).bAlive)
		{
			OutError = Loc("error.newGame.deadFaction", "The chosen faction is no longer in the game.");
			return false;
		}
		State = std::move(Loaded);
		State.PlayerFaction = PlayerFaction;
		State.Difficulty = Difficulty;
		State.Rng = FRng(Seed);
		State.Phase = EPhase::Planning;
		State.Outcome = EOutcome::None;
		State.Day = 0;
		State.bDayInProgress = false;
		State.BattleQueue.clear();
		State.Orders.clear();
		State.PendingEvents.clear();
		State.PendingPrisoners.clear();
		State.Log.clear();
		GameRules::SanitizeState(State);
		GameRules::RevealDueOfficers(State);
		for (int Faction = 0; Faction < GameRules::CountOf(State.Factions); ++Faction)
		{
			bool bHasCity = false;
			for (const FCity& City : State.Cities)
			{
				bHasCity = bHasCity || City.Owner == Faction;
			}
			if (!bHasCity && State.Factions[static_cast<size_t>(Faction)].bAlive && Faction != PlayerFaction)
			{
				GameRules::At(State.Factions, Faction).bAlive = false;
			}
		}
		if (PlayerFaction >= 0)
		{
			const int Ruler = GameRules::RulerOf(State, PlayerFaction);
			GameRules::LogPlayer(State, LocF("log.game.start", "{ruler} raises the banner of the {faction}. The struggle for the realm begins.", {{"ruler", GameRules::OfficerLabel(State, Ruler)}, {"faction", GameRules::FactionLabel(State, PlayerFaction)}}), true);
		}
		GameRules::BeginPlanning(State);
		return true;
	}

	bool FGame::LoadGame(const FJson& Save, std::string& OutError)
	{
		FGameState Loaded;
		if (!LoadGameState(Save, Loaded, OutError))
		{
			return false;
		}
		State = std::move(Loaded);
		GameRules::SanitizeState(State);
		if (State.Phase != EPhase::Execution)
		{
			State.bDayInProgress = false;
			State.BattleQueue.clear();
		}
		return true;
	}

	FJson FGame::SaveGame() const
	{
		return SaveGameState(State);
	}

	// =============================================================================================
	// FGame: planning queries
	// =============================================================================================

	bool FGame::IsPlanning() const
	{
		return State.Phase == EPhase::Planning;
	}

	bool FGame::IsPlayerCity(int City) const
	{
		return GameRules::ValidCity(State, City) && State.PlayerFaction >= 0 && GameRules::At(State.Cities, City).Owner == State.PlayerFaction;
	}

	std::vector<int> FGame::IdleOfficers(int City) const
	{
		std::vector<int> Result;
		if (!IsPlayerCity(City))
		{
			return Result;
		}
		for (const int Officer : GameRules::OfficersInCity(State, City, State.PlayerFaction))
		{
			if (State.OfficerOrder(Officer) == nullptr)
			{
				Result.push_back(Officer);
			}
		}
		return Result;
	}

	std::vector<FOrder> FGame::PlayerOrders() const
	{
		std::vector<FOrder> Result;
		for (const FOrder& Order : State.Orders)
		{
			if (GameRules::ValidOfficer(State, Order.Officer) && GameRules::At(State.Officers, Order.Officer).Faction == State.PlayerFaction && State.PlayerFaction >= 0)
			{
				Result.push_back(Order);
			}
		}
		return Result;
	}

	std::vector<int> FGame::RecruitTargets(int City) const
	{
		return GameRules::RecruitTargetsOf(State, City, State.PlayerFaction);
	}

	std::vector<int> FGame::MoveDestinations(int City) const
	{
		std::vector<int> Result;
		if (!IsPlayerCity(City))
		{
			return Result;
		}
		for (int Other = 0; Other < GameRules::CountOf(State.Cities); ++Other)
		{
			if (Other != City && IsPlayerCity(Other))
			{
				Result.push_back(Other);
			}
		}
		return Result;
	}

	std::vector<int> FGame::DiplomacyTargets() const
	{
		std::vector<int> Result;
		for (int Faction = 0; Faction < GameRules::CountOf(State.Factions); ++Faction)
		{
			if (Faction != State.PlayerFaction && GameRules::IsAliveFaction(State, Faction))
			{
				Result.push_back(Faction);
			}
		}
		return Result;
	}

	std::vector<int> FGame::SectsNear(int City) const
	{
		return GameRules::SectsNearOf(State, City);
	}

	int FGame::DraftCapacity(int City) const
	{
		return GameRules::DraftCapacityOf(State, City);
	}

	int FGame::DraftCost(int Troops) const
	{
		return GameRules::DraftCostOf(Troops);
	}

	int FGame::RecruitChance(int Recruiter, int Target) const
	{
		return GameRules::RecruitChanceOf(State, Recruiter, Target);
	}

	// =============================================================================================
	// FGame: info
	// =============================================================================================

	std::string FGame::DateText() const
	{
		if (State.Phase == EPhase::Execution)
		{
			return LocF("date.execution", "Year {year}, Month {month}, Day {day}", {{"year", ToText(State.Year)}, {"month", ToText(State.Month)}, {"day", ToText(std::max(1, State.Day))}});
		}
		return LocF("date.planning", "Year {year}, Month {month} ({season})", {{"year", ToText(State.Year)}, {"month", ToText(State.Month)}, {"season", SeasonName(State.Month)}});
	}

	int FGame::CityCount(int Faction) const
	{
		int Count = 0;
		for (const FCity& City : State.Cities)
		{
			Count += (Faction >= 0 && City.Owner == Faction) ? 1 : 0;
		}
		return Count;
	}

	int FGame::GoldIncome(int City) const
	{
		return GameRules::CityGoldIncome(State, City);
	}

	int FGame::HarvestYield(int City) const
	{
		return GameRules::CityHarvest(State, City);
	}

	int FGame::FoodConsumption(int City) const
	{
		return GameRules::ValidCity(State, City) ? GameRules::GarrisonFood(GameRules::At(State.Cities, City).Troops) : 0;
	}

	int FGame::OfficerUpkeep(int City) const
	{
		if (!GameRules::ValidCity(State, City))
		{
			return 0;
		}
		const FCity& Data = GameRules::At(State.Cities, City);
		int Upkeep = GameRules::CountOf(GameRules::OfficersInCity(State, City, Data.Owner)) * GameRules::Balance::OfficerUpkeep;
		for (const FArmy& Army : State.Armies)
		{
			if (Army.Home == City && Army.Faction == Data.Owner)
			{
				Upkeep += GameRules::CountOf(Army.Units) * GameRules::Balance::OfficerUpkeep;
			}
		}
		return Upkeep;
	}
}
