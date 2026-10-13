#include "Sim/IronGame.h"

#include "Sim/IronGameInternal.h"
#include "Sim/IronLocale.h"

#include <algorithm>

namespace IronSim
{
	namespace GameRules
	{
		namespace MilitaryDetail
		{
			int RoadIndexOf(const FGameState& State, int Road)
			{
				return (Road >= 0 && Road < CountOf(State.Roads)) ? Road : -1;
			}

			std::string CommanderName(const FGameState& State, const FArmy& Army)
			{
				return Army.Units.empty() ? Loc("common.unknownOfficer", "an unknown officer") : OfficerLabel(State, Army.Units.front().Officer);
			}

			void EraseArmy(FGameState& State, int ArmyId)
			{
				for (size_t Index = 0; Index < State.Armies.size(); ++Index)
				{
					if (State.Armies[Index].Id == ArmyId)
					{
						State.Armies.erase(State.Armies.begin() + static_cast<std::ptrdiff_t>(Index));
						return;
					}
				}
			}

			/** Officers of units without troops leave the army and go home; empty armies are removed. Returns false if the army is gone. */
			bool PruneArmy(FGameState& State, int ArmyId)
			{
				FArmy* Army = State.FindArmy(ArmyId);
				if (!Army)
				{
					return false;
				}
				std::vector<int> Leaving;
				for (const FArmyUnit& Unit : Army->Units)
				{
					if (Unit.Troops <= 0)
					{
						Leaving.push_back(Unit.Officer);
					}
				}
				const int From = Army->Node;
				for (const int Officer : Leaving)
				{
					if (ValidOfficer(State, Officer))
					{
						SendOfficerHome(State, Officer, From);
					}
				}
				Army = State.FindArmy(ArmyId);
				if (Army && Army->Units.empty())
				{
					EraseArmy(State, ArmyId);
					return false;
				}
				return Army != nullptr;
			}

			void CutOff(FGameState& State, int ArmyId)
			{
				const FArmy* Army = State.FindArmy(ArmyId);
				if (!Army)
				{
					return;
				}
				const FArmy Copy = *Army;
				EraseArmy(State, ArmyId);
				if (IsPlayerFaction(State, Copy.Faction))
				{
					LogPlayer(State, LocF("log.army.cutOff", "The army of {commander} was cut off from home and scattered. Its officers made their way back alone.", {{"commander", CommanderName(State, Copy)}}), true);
				}
				for (const FArmyUnit& Unit : Copy.Units)
				{
					if (ValidOfficer(State, Unit.Officer) && At(State.Officers, Unit.Officer).Army == Copy.Id)
					{
						At(State.Officers, Unit.Officer).Army = -1;
						SendOfficerHome(State, Unit.Officer, Copy.Node);
					}
				}
			}

			void Starve(FGameState& State, int ArmyId)
			{
				FArmy* Army = State.FindArmy(ArmyId);
				if (!Army)
				{
					return;
				}
				Army->Food = 0;
				Army->Morale = std::max(0, Army->Morale - 10);
				for (FArmyUnit& Unit : Army->Units)
				{
					Unit.Troops = Unit.Troops * (100 - Balance::ShortageDesertionPercent) / 100;
				}
				if (!PruneArmy(State, ArmyId))
				{
					return;
				}
				Army = State.FindArmy(ArmyId);
				if (Army->State == EArmyState::Marching)
				{
					if (IsPlayerFaction(State, Army->Faction))
					{
						LogPlayer(State, LocF("log.army.starving", "The army of {commander} has run out of food. Soldiers are deserting and the army is turning back.", {{"commander", CommanderName(State, *Army)}}), true);
					}
					StartReturn(State, ArmyId);
				}
			}

			/** Moves the army onto the next road of its route. */
			void NextLeg(FGameState& State, FArmy& Army, int Leftover)
			{
				Army.Node = Army.Next;
				Army.Next = Army.Route.front();
				Army.Route.erase(Army.Route.begin());
				Army.Road = State.RoadBetween(Army.Node, Army.Next);
				Army.Progress = std::max(0, Leftover);
			}

			/** The army stands at Army.Next. Returns true if it continues along a new road. */
			bool ReachCity(FGameState& State, int ArmyId, std::vector<FPendingBattle>& OutSieges)
			{
				FArmy* Army = State.FindArmy(ArmyId);
				const int City = Army->Next;
				const FCity& Data = At(State.Cities, City);
				const bool bFinal = Army->Route.empty();
				if (Data.Owner == Army->Faction)
				{
					if (bFinal)
					{
						MergeArmy(State, ArmyId, City);
						return false;
					}
					if (State.RoadBetween(City, Army->Route.front()) < 0)
					{
						MergeArmy(State, ArmyId, City);
						return false;
					}
					NextLeg(State, *Army, 0);
					return true;
				}
				if (Army->State == EArmyState::Returning)
				{
					// Home was lost on the way: find another way back.
					StartReturn(State, ArmyId);
					return false;
				}
				if (State.AreHostile(Army->Faction, Data.Owner))
				{
					// Assault the city, even if it was an own city captured by the enemy while we marched.
					Army->Target = City;
					Army->Route.clear();
					OutSieges.push_back(FPendingBattle{EBattleKind::Siege, ArmyId, 0, City});
					return false;
				}
				// Allied or under truce: turn back.
				StartReturn(State, ArmyId);
				return false;
			}

			void MoveArmy(FGameState& State, int ArmyId, std::vector<FPendingBattle>& OutSieges)
			{
				FArmy* Army = State.FindArmy(ArmyId);
				if (!Army)
				{
					return;
				}
				if (Army->Next < 0 || RoadIndexOf(State, Army->Road) < 0)
				{
					if (ValidCity(State, Army->Node) && At(State.Cities, Army->Node).Owner == Army->Faction)
					{
						MergeArmy(State, ArmyId, Army->Node);
					}
					else
					{
						CutOff(State, ArmyId);
					}
					return;
				}
				int Budget = State.ArmySpeed(*Army);
				for (int Guard = 0; Guard < 8 && Budget > 0; ++Guard)
				{
					Army = State.FindArmy(ArmyId);
					if (!Army)
					{
						return;
					}
					const int Length = State.RoadLength(Army->Road);
					const int Remaining = Length - Army->Progress;
					if (Budget < Remaining)
					{
						Army->Progress += Budget;
						return;
					}
					Budget -= std::max(0, Remaining);
					Army->Progress = Length;
					if (!ReachCity(State, ArmyId, OutSieges))
					{
						return;
					}
				}
			}

			void DetectFieldBattles(const FGameState& State, std::vector<FPendingBattle>& OutBattles)
			{
				std::vector<int> Engaged;
				const int Count = CountOf(State.Armies);
				for (int First = 0; First < Count; ++First)
				{
					const FArmy& A = At(State.Armies, First);
					for (int Second = First + 1; Second < Count; ++Second)
					{
						const FArmy& B = At(State.Armies, Second);
						if (A.Road < 0 || A.Road != B.Road || A.Node != B.Next || A.Next != B.Node)
						{
							continue;
						}
						if (!State.AreHostile(A.Faction, B.Faction) || A.Progress + B.Progress < State.RoadLength(A.Road))
						{
							continue;
						}
						if (std::find(Engaged.begin(), Engaged.end(), A.Id) != Engaged.end() || std::find(Engaged.begin(), Engaged.end(), B.Id) != Engaged.end())
						{
							continue;
						}
						// The army on the offensive attacks; otherwise the one that set out first.
						bool bAAttacks = true;
						if (A.State != B.State)
						{
							bAAttacks = A.State == EArmyState::Marching;
						}
						else
						{
							bAAttacks = A.Id < B.Id;
						}
						const FArmy& Attacker = bAAttacks ? A : B;
						const FArmy& Defender = bAAttacks ? B : A;
						OutBattles.push_back(FPendingBattle{EBattleKind::Field, Attacker.Id, Defender.Id, -1});
						Engaged.push_back(A.Id);
						Engaged.push_back(B.Id);
					}
				}
			}

			void AdvanceArmies(FGameState& State)
			{
				std::vector<int> Ids;
				for (const FArmy& Army : State.Armies)
				{
					Ids.push_back(Army.Id);
				}
				std::vector<FPendingBattle> Sieges;
				for (const int Id : Ids)
				{
					FArmy* Army = State.FindArmy(Id);
					if (!Army)
					{
						continue;
					}
					const int Need = ArmyFoodPerDay(Army->TotalTroops());
					if (Army->Food >= Need)
					{
						Army->Food -= Need;
					}
					else
					{
						Starve(State, Id);
						if (!State.FindArmy(Id))
						{
							continue;
						}
					}
					MoveArmy(State, Id, Sieges);
				}
				std::vector<FPendingBattle> Fields;
				DetectFieldBattles(State, Fields);
				State.BattleQueue.insert(State.BattleQueue.end(), Fields.begin(), Fields.end());
				State.BattleQueue.insert(State.BattleQueue.end(), Sieges.begin(), Sieges.end());
			}

			ETerrain RoadTerrain(const FGameState& State, const FArmy& Army)
			{
				if (RoadIndexOf(State, Army.Road) < 0 || !ValidCity(State, Army.Next))
				{
					return ValidCity(State, Army.Node) ? At(State.Cities, Army.Node).Terrain : ETerrain::Plains;
				}
				const FRoad& Road = At(State.Roads, Army.Road);
				const ETerrain Near = At(State.Cities, Army.Next).Terrain;
				const ETerrain Far = ValidCity(State, Army.Node) ? At(State.Cities, Army.Node).Terrain : Near;
				switch (Road.Kind)
				{
				case ERoadKind::River:
					return ETerrain::River;
				case ERoadKind::Pass:
					return (Near == ETerrain::Mountains || Far == ETerrain::Mountains) ? ETerrain::Mountains : ETerrain::Hills;
				case ERoadKind::Road:
					break;
				}
				if (Near == ETerrain::Mountains)
				{
					return ETerrain::Hills;
				}
				if (Near == ETerrain::Coast)
				{
					return ETerrain::Plains;
				}
				return Near;
			}

			void FillFactionSide(const FGameState& State, int Faction, FBattleSideSetup& Side)
			{
				Side.Faction = Faction;
				Side.Name = FactionLabel(State, Faction);
				if (ValidFaction(State, Faction))
				{
					const FFaction& Data = At(State.Factions, Faction);
					Side.Glyph = Data.Glyph;
					Side.Color = Data.Color;
				}
				else
				{
					Side.Glyph.clear();
					Side.Color = 0x8C8577;
				}
				Side.bPlayer = IsPlayerFaction(State, Faction);
			}

			FBattleUnitSetup OfficerUnit(const FGameState& State, int Officer, int Troops, ETroopType Type)
			{
				FBattleUnitSetup Unit;
				Unit.Officer = Officer;
				Unit.Troops = Troops;
				Unit.Type = Type;
				if (ValidOfficer(State, Officer))
				{
					const FOfficer& Data = At(State.Officers, Officer);
					Unit.Name = NameOf(Data);
					Unit.Portrait = Data.Portrait;
					for (int Stat = 0; Stat < StatCount; ++Stat)
					{
						Unit.Stats[Stat] = Data.Stats[Stat];
					}
					Unit.Bravery = Data.Bravery;
					for (const int Technique : Data.Techniques)
					{
						if (ValidTechnique(State, Technique))
						{
							Unit.Techniques.push_back(Technique);
						}
					}
				}
				return Unit;
			}

			void FillArmySide(const FGameState& State, const FArmy& Army, FBattleSideSetup& Side)
			{
				FillFactionSide(State, Army.Faction, Side);
				Side.Training = Army.Training;
				Side.Morale = Army.Morale;
				const int Daily = ArmyFoodPerDay(Army.TotalTroops());
				Side.FoodDays = Daily > 0 ? std::max(1, Army.Food / Daily) : 999;
				for (const FArmyUnit& Unit : Army.Units)
				{
					Side.Units.push_back(OfficerUnit(State, Unit.Officer, Unit.Troops, Unit.Type));
				}
			}

			std::vector<int> DefendingOfficers(const FGameState& State, int City)
			{
				const FCity& Data = At(State.Cities, City);
				std::vector<int> Officers = OfficersInCity(State, City, Data.Owner);
				std::stable_sort(Officers.begin(), Officers.end(), [&State](int Left, int Right) {
					return StatOf(At(State.Officers, Left), EStat::Command) > StatOf(At(State.Officers, Right), EStat::Command);
				});
				if (CountOf(Officers) > Balance::MaxDefenderOfficers)
				{
					Officers.resize(static_cast<size_t>(Balance::MaxDefenderOfficers));
				}
				return Officers;
			}

			void FillCitySide(const FGameState& State, int City, FBattleSideSetup& Side)
			{
				const FCity& Data = At(State.Cities, City);
				FillFactionSide(State, Data.Owner, Side);
				Side.Training = Data.Training;
				Side.Morale = ClampInt(50 + Data.Training / 4 + Data.Order / 10, 30, 100);
				Side.FoodDays = 999;
				const std::vector<int> Officers = DefendingOfficers(State, City);
				const int Total = std::max(0, Data.Troops);
				int Remaining = Total;
				if (!Officers.empty())
				{
					const int Share = Total / CountOf(Officers);
					for (const int Officer : Officers)
					{
						const int Troops = std::min(Share, MaxUnitTroopsOf(State, Officer));
						Side.Units.push_back(OfficerUnit(State, Officer, Troops, At(State.Officers, Officer).Specialty));
						Remaining -= Troops;
					}
				}
				// Leftover troops form nameless garrison detachments.
				const int GarrisonCap = Balance::UnitBaseTroops + Balance::GarrisonUnitStat * Balance::UnitTroopsPerCommand;
				std::vector<int> GarrisonUnits;
				int Created = 0;
				while (Remaining > 0 && Created < Balance::MaxGarrisonUnits)
				{
					const int Troops = std::min(Remaining, GarrisonCap);
					FBattleUnitSetup Unit;
					Unit.Officer = -1;
					Unit.Name = (Side.Units.empty()) ? Loc("battle.unit.garrisonCaptain", "Garrison Captain") : Loc("battle.unit.garrison", "Garrison");
					for (int Stat = 0; Stat < StatCount; ++Stat)
					{
						Unit.Stats[Stat] = Balance::GarrisonUnitStat;
					}
					Unit.Bravery = 50;
					Unit.Troops = Troops;
					Unit.Type = (Created % 2 == 0) ? ETroopType::Archer : ETroopType::Infantry;
					GarrisonUnits.push_back(CountOf(Side.Units));
					Side.Units.push_back(Unit);
					Remaining -= Troops;
					++Created;
				}
				// Anything beyond the unit caps reinforces the garrison detachments (or the officers).
				while (Remaining > 0 && !Side.Units.empty())
				{
					const std::vector<int>& Receivers = GarrisonUnits;
					const int Count = Receivers.empty() ? CountOf(Side.Units) : CountOf(Receivers);
					const int Each = std::max(1, Remaining / Count);
					for (int Index = 0; Index < Count && Remaining > 0; ++Index)
					{
						const int Unit = Receivers.empty() ? Index : At(Receivers, Index);
						const int Add = std::min(Each, Remaining);
						At(Side.Units, Unit).Troops += Add;
						Remaining -= Add;
					}
				}
			}

			/** Maps battle outcomes back to setup units of one side (by order, falling back to the officer). */
			const FUnitOutcome* OutcomeFor(const std::vector<const FUnitOutcome*>& Outcomes, size_t Index, int Officer)
			{
				if (Index < Outcomes.size() && Outcomes[Index]->Officer == Officer)
				{
					return Outcomes[Index];
				}
				if (Officer >= 0)
				{
					for (const FUnitOutcome* Outcome : Outcomes)
					{
						if (Outcome->Officer == Officer)
						{
							return Outcome;
						}
					}
				}
				return Index < Outcomes.size() ? Outcomes[Index] : nullptr;
			}

			void GrantBattleExp(FGameState& State, int Officer, const FUnitOutcome& Outcome, bool bWon)
			{
				if (!ValidOfficer(State, Officer))
				{
					return;
				}
				FOfficer& Data = At(State.Officers, Officer);
				GainExp(Data, EStat::Command, bWon ? 25 : 12);
				GainExp(Data, EStat::Martial, std::min(30, Outcome.DamageDealt / 150) + Outcome.DuelsWon * 25);
				GainExp(Data, EStat::Strategy, Outcome.TacticsSucceeded * 12);
				Data.Merit += bWon ? 15 : 5;
			}

			/** Applies one army's battle outcome. Captured officers go to PrisonCity of the enemy. */
			void ApplyArmySide(FGameState& State, int ArmyId, const std::vector<const FUnitOutcome*>& Outcomes, int EnemyFaction, int PrisonCity, bool bWon, int Days)
			{
				FArmy* Army = State.FindArmy(ArmyId);
				if (!Army)
				{
					return;
				}
				std::vector<int> Captured;
				std::vector<int> Killed;
				for (size_t Index = 0; Index < Army->Units.size(); ++Index)
				{
					FArmyUnit& Unit = Army->Units[Index];
					const FUnitOutcome* Outcome = OutcomeFor(Outcomes, Index, Unit.Officer);
					if (!Outcome)
					{
						continue;
					}
					Unit.Troops = ClampInt(Outcome->Troops, 0, Unit.Troops);
					if (Outcome->Status == EUnitStatus::Captured)
					{
						Captured.push_back(Unit.Officer);
					}
					else if (Outcome->Status == EUnitStatus::Killed)
					{
						Killed.push_back(Unit.Officer);
					}
					GrantBattleExp(State, Unit.Officer, *Outcome, bWon);
				}
				Army = State.FindArmy(ArmyId);
				const int Daily = ArmyFoodPerDay(Army->TotalTroops());
				Army->Food = std::max(0, Army->Food - Daily * std::max(0, Days - 1));
				Army->Morale = bWon ? std::min(100, Army->Morale + 10) : std::max(0, Army->Morale - 15);
				const int Faction = Army->Faction;
				for (const int Officer : Captured)
				{
					CaptureOfficer(State, Officer, EnemyFaction, PrisonCity);
				}
				for (const int Officer : Killed)
				{
					if (IsPlayerFaction(State, Faction) || IsPlayerFaction(State, EnemyFaction))
					{
						LogPlayer(State, LocF("log.officer.killed", "{officer} of the {faction} has fallen in battle.", {{"officer", OfficerLabel(State, Officer)}, {"faction", FactionLabel(State, Faction)}}), true);
					}
					KillOfficer(State, Officer);
				}
				PruneArmy(State, ArmyId);
			}

			void CaptureCity(FGameState& State, int City, int ArmyId, int SurvivingDefenders, const std::vector<int>& ForcedCaptures)
			{
				const FArmy* Army = State.FindArmy(ArmyId);
				if (!Army)
				{
					return;
				}
				const FArmy Copy = *Army;
				EraseArmy(State, ArmyId);
				FCity& Data = At(State.Cities, City);
				const int OldOwner = Data.Owner;
				const int NewOwner = Copy.Faction;
				const int ArmyTroops = Copy.TotalTroops();
				const int Joined = std::max(0, SurvivingDefenders) * Balance::SurrenderPercent / 100;
				const long long TroopSum = static_cast<long long>(ArmyTroops) + Joined;
				Data.Training = TroopSum > 0 ? static_cast<int>((static_cast<long long>(Copy.Training) * ArmyTroops + static_cast<long long>(Data.Training) * Joined) / TroopSum) : Data.Training;
				Data.Owner = NewOwner;
				Data.Gold = Data.Gold * Balance::LootKeepPercent / 100;
				Data.Food = Data.Food * Balance::LootKeepPercent / 100 + Copy.Food;
				Data.Troops = ArmyTroops + Joined;
				Data.Order = std::max(0, Data.Order - Balance::ConquestOrderLoss);
				const bool bHomeDelegated = ValidCity(State, Copy.Home) && At(State.Cities, Copy.Home).Owner == NewOwner && At(State.Cities, Copy.Home).bDelegated;
				Data.bDelegated = IsPlayerFaction(State, NewOwner) && bHomeDelegated;
				for (const FArmyUnit& Unit : Copy.Units)
				{
					if (ValidOfficer(State, Unit.Officer))
					{
						FOfficer& Officer = At(State.Officers, Unit.Officer);
						Officer.Army = -1;
						Officer.City = City;
					}
				}

				LogBetween(State, NewOwner, OldOwner, LocF("log.battle.cityTaken", "{city} has fallen to the {faction}!", {{"city", NameOf(Data)}, {"faction", FactionLabel(State, NewOwner)}}), true);

				// The defeated side's officers in the city are captured or escape to their nearest city.
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					const FOfficer& Member = At(State.Officers, Officer);
					if (Member.Status != EOfficerStatus::Serving || Member.Faction != OldOwner || OldOwner < 0 || Member.City != City || Member.Army >= 0)
					{
						continue;
					}
					const bool bForced = std::find(ForcedCaptures.begin(), ForcedCaptures.end(), Officer) != ForcedCaptures.end();
					const int Refuge = NearestOwnedCity(State, OldOwner, City);
					if (!bForced && Refuge >= 0 && State.Rng.Chance(Balance::FleeChance))
					{
						PlaceInCity(State, Officer, Refuge);
						if (IsPlayerFaction(State, OldOwner))
						{
							LogPlayer(State, LocF("log.officer.fled", "{officer} escaped from {city} to {refuge}.", {{"officer", OfficerLabel(State, Officer)}, {"city", NameOf(Data)}, {"refuge", CityLabel(State, Refuge)}}));
						}
					}
					else
					{
						CaptureOfficer(State, Officer, NewOwner, City);
					}
				}
				for (const int Officer : ForcedCaptures)
				{
					if (ValidOfficer(State, Officer) && At(State.Officers, Officer).Status == EOfficerStatus::Serving && At(State.Officers, Officer).Faction != NewOwner)
					{
						CaptureOfficer(State, Officer, NewOwner, City);
					}
				}

				// Prisoners held in the city are freed.
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					const FOfficer& Member = At(State.Officers, Officer);
					if (Member.Status != EOfficerStatus::Prisoner || Member.City != City || Member.Captor == NewOwner)
					{
						continue;
					}
					if (Member.Faction == NewOwner)
					{
						JoinFaction(State, Officer, NewOwner, City, Member.Loyalty);
						if (IsPlayerFaction(State, NewOwner))
						{
							LogPlayer(State, LocF("log.officer.freed", "{officer} was freed from the dungeons of {city} and rejoins your ranks.", {{"officer", OfficerLabel(State, Officer)}, {"city", NameOf(Data)}}), true);
						}
					}
					else
					{
						ReleasePrisoner(State, Officer);
					}
				}

				if (OldOwner >= 0 && NewOwner >= 0)
				{
					FRelation& Relation = State.Relation(NewOwner, OldOwner);
					Relation.Trust = ClampInt(Relation.Trust - 10, 0, 100);
				}
				FixCapital(State, OldOwner);
			}

			/** Validates the battle at the front of the queue, resolving trivial cases. Returns true if it must be fought. */
			bool PrepareBattle(FGameState& State, const FPendingBattle& Battle)
			{
				FArmy* Attacker = State.FindArmy(Battle.Attacker);
				if (!Attacker || Attacker->Units.empty())
				{
					return false;
				}
				if (Battle.Kind == EBattleKind::Field)
				{
					const FArmy* Defender = State.FindArmy(Battle.Defender);
					if (!Defender || Defender->Units.empty())
					{
						return false;
					}
					return Attacker->Road == Defender->Road && Attacker->Node == Defender->Next && Attacker->Next == Defender->Node
						&& State.AreHostile(Attacker->Faction, Defender->Faction);
				}
				if (!ValidCity(State, Battle.City) || Attacker->State != EArmyState::Marching || Attacker->Next != Battle.City
					|| RoadIndexOf(State, Attacker->Road) < 0 || Attacker->Progress < State.RoadLength(Attacker->Road))
				{
					return false;
				}
				const FCity& Data = At(State.Cities, Battle.City);
				if (Data.Owner == Attacker->Faction)
				{
					MergeArmy(State, Battle.Attacker, Battle.City);
					return false;
				}
				if (!State.AreHostile(Attacker->Faction, Data.Owner))
				{
					StartReturn(State, Battle.Attacker);
					return false;
				}
				if (Data.Troops <= 0)
				{
					const int Faction = Attacker->Faction;
					const int OldOwner = Data.Owner;
					LogBetween(State, Faction, OldOwner, LocF("log.battle.cityAbandoned", "{city} had no soldiers left to defend it and opened its gates to the {faction}.", {{"city", NameOf(Data)}, {"faction", FactionLabel(State, Faction)}}), true);
					CaptureCity(State, Battle.City, Battle.Attacker, 0, std::vector<int>());
					UpdateFactions(State);
					return false;
				}
				return true;
			}
		}

		int MaxUnitTroopsOf(const FGameState& State, int Officer)
		{
			if (!ValidOfficer(State, Officer))
			{
				return Balance::UnitBaseTroops;
			}
			return Balance::UnitBaseTroops + StatOf(At(State.Officers, Officer), EStat::Command) * Balance::UnitTroopsPerCommand;
		}

		std::vector<int> SplitTroops(const FGameState& State, const std::vector<int>& Officers, int Troops)
		{
			std::vector<int> Result(Officers.size(), 0);
			if (Officers.empty() || Troops <= 0)
			{
				return Result;
			}
			std::vector<int> Caps;
			long long CapSum = 0;
			for (const int Officer : Officers)
			{
				Caps.push_back(MaxUnitTroopsOf(State, Officer));
				CapSum += Caps.back();
			}
			const int Total = static_cast<int>(std::min<long long>(Troops, CapSum));
			int Assigned = 0;
			for (size_t Index = 0; Index < Officers.size(); ++Index)
			{
				Result[Index] = static_cast<int>(static_cast<long long>(Total) * Caps[Index] / std::max<long long>(1, CapSum));
				Assigned += Result[Index];
			}
			for (size_t Index = 0; Index < Officers.size() && Assigned < Total; ++Index)
			{
				const int Add = std::min(Total - Assigned, Caps[Index] - Result[Index]);
				Result[Index] += Add;
				Assigned += Add;
			}
			return Result;
		}

		std::vector<int> MarchTargetsOf(const FGameState& State, int City, int Faction)
		{
			std::vector<int> Result;
			if (!ValidCity(State, City) || Faction < 0)
			{
				return Result;
			}
			std::vector<int> Dist;
			std::vector<int> Prev;
			ShortestPaths(State, City, Faction, true, true, Dist, Prev);
			for (int Other = 0; Other < CountOf(State.Cities); ++Other)
			{
				if (Other == City || At(Dist, Other) >= Unreachable)
				{
					continue;
				}
				const int Owner = At(State.Cities, Other).Owner;
				if (Owner == Faction || State.AreHostile(Faction, Owner))
				{
					Result.push_back(Other);
				}
			}
			std::stable_sort(Result.begin(), Result.end(), [&Dist](int Left, int Right) { return At(Dist, Left) < At(Dist, Right); });
			return Result;
		}

		int IncomingHostileTroops(const FGameState& State, int City, int Faction)
		{
			int Total = 0;
			for (const FArmy& Army : State.Armies)
			{
				if (Army.Target == City && Army.State == EArmyState::Marching && Army.Faction != Faction && State.AreHostile(Army.Faction, Faction))
				{
					Total += Army.TotalTroops();
				}
			}
			return Total;
		}

		FOrderCheck CheckArmyRules(const FGameState& State, const FArmyPlan& Plan)
		{
			FOrderCheck Check;
			if (State.Phase != EPhase::Planning)
			{
				return DenyCheck(Check, Loc("army.reason.notPlanning", "Armies can only be formed during the planning phase."));
			}
			if (!ValidCity(State, Plan.City) || At(State.Cities, Plan.City).Owner < 0)
			{
				return DenyCheck(Check, Loc("army.reason.noCity", "Choose a city to march from."));
			}
			const FCity& City = At(State.Cities, Plan.City);
			const int Faction = City.Owner;
			const std::string Where = NameOf(City);
			if (Plan.Officers.empty())
			{
				return DenyCheck(Check, Loc("army.reason.noCommander", "Choose a commander."));
			}
			if (CountOf(Plan.Officers) > MaxArmyUnits)
			{
				return DenyCheck(Check, LocF("army.reason.tooManyOfficers", "An army can have at most {count} officers.", {{"count", ToText(MaxArmyUnits)}}));
			}
			for (size_t Index = 0; Index < Plan.Officers.size(); ++Index)
			{
				const int Officer = Plan.Officers[Index];
				if (!ValidOfficer(State, Officer))
				{
					return DenyCheck(Check, Loc("army.reason.badOfficer", "Choose valid officers."));
				}
				const FOfficer& Data = At(State.Officers, Officer);
				const std::string Who = NameOf(Data);
				if (Data.Status != EOfficerStatus::Serving || Data.Faction != Faction)
				{
					return DenyCheck(Check, LocF("order.reason.notServing", "{officer} does not serve the lord of {city}.", {{"officer", Who}, {"city", Where}}));
				}
				if (Data.Army >= 0 || Data.City != Plan.City)
				{
					return DenyCheck(Check, LocF("order.reason.notInCity", "{officer} is not in {city}.", {{"officer", Who}, {"city", Where}}));
				}
				if (State.OfficerOrder(Officer) != nullptr)
				{
					return DenyCheck(Check, LocF("order.reason.busy", "{officer} already has orders this month.", {{"officer", Who}}));
				}
				for (size_t Other = 0; Other < Index; ++Other)
				{
					if (Plan.Officers[Other] == Officer)
					{
						return DenyCheck(Check, LocF("army.reason.duplicate", "{officer} was chosen twice.", {{"officer", Who}}));
					}
				}
			}
			if (!ValidCity(State, Plan.Target) || Plan.Target == Plan.City)
			{
				return DenyCheck(Check, Loc("army.reason.noTarget", "Choose a destination."));
			}
			const std::string Target = CityLabel(State, Plan.Target);
			std::vector<int> Path;
			int Tenths = 0;
			if (!FindRoute(State, Faction, Plan.City, Plan.Target, Path, Tenths))
			{
				return DenyCheck(Check, LocF("army.reason.unreachable", "{target} cannot be reached through your territory.", {{"target", Target}}));
			}
			const int TargetOwner = At(State.Cities, Plan.Target).Owner;
			if (TargetOwner != Faction && !State.AreHostile(Faction, TargetOwner))
			{
				if (State.AreAllied(Faction, TargetOwner))
				{
					return DenyCheck(Check, LocF("army.reason.allied", "{target} belongs to your ally, the {faction}.", {{"target", Target}, {"faction", FactionLabel(State, TargetOwner)}}));
				}
				return DenyCheck(Check, LocF("army.reason.truce", "You have a truce with the {faction}.", {{"faction", FactionLabel(State, TargetOwner)}}));
			}
			long long Capacity = 0;
			for (const int Officer : Plan.Officers)
			{
				Capacity += MaxUnitTroopsOf(State, Officer);
			}
			const int MinTroops = CountOf(Plan.Officers) * Balance::MinUnitTroops;
			if (Plan.Troops < MinTroops)
			{
				return DenyCheck(Check, LocF("army.reason.fewTroops", "The army needs at least {amount} troops ({per} per officer).", {{"amount", ToText(MinTroops)}, {"per", ToText(Balance::MinUnitTroops)}}));
			}
			if (Plan.Troops > City.Troops)
			{
				return DenyCheck(Check, LocF("army.reason.cityTroops", "{city} has only {amount} troops.", {{"city", Where}, {"amount", ToText(City.Troops)}}));
			}
			if (Plan.Troops > Capacity)
			{
				return DenyCheck(Check, LocF("army.reason.capacity", "These officers can lead at most {amount} troops.", {{"amount", ToText(static_cast<int>(Capacity))}}));
			}
			// Speed from the composition the army will have.
			FArmy Preview;
			const std::vector<int> Split = SplitTroops(State, Plan.Officers, Plan.Troops);
			for (size_t Index = 0; Index < Plan.Officers.size(); ++Index)
			{
				Preview.Units.push_back(FArmyUnit{Plan.Officers[Index], Split[Index], At(State.Officers, Plan.Officers[Index]).Specialty});
			}
			const int Speed = std::max(1, State.ArmySpeed(Preview));
			const int Days = (Tenths + Speed - 1) / Speed;
			const int Daily = ArmyFoodPerDay(Plan.Troops);
			const int FoodDays = Daily > 0 ? Plan.Food / Daily : 0;
			Check.Preview = LocF("army.preview", "{troops} troops reach {target} in {days} days, with food for {fooddays} days.", {{"troops", ToText(Plan.Troops)}, {"target", Target}, {"days", ToText(Days)}, {"fooddays", ToText(FoodDays)}});
			if (Plan.Food > City.Food || Plan.Food < 0)
			{
				return DenyCheck(Check, LocF("army.reason.cityFood", "{city} has only {amount} food.", {{"city", Where}, {"amount", ToText(City.Food)}}));
			}
			if (Plan.Food < Daily * Days)
			{
				return DenyCheck(Check, LocF("army.reason.food", "The army needs at least {amount} food to reach {target}.", {{"amount", ToText(Daily * Days)}, {"target", Target}}));
			}
			Check.bAllowed = true;
			return Check;
		}

		int FormArmyRules(FGameState& State, const FArmyPlan& Plan, std::string& OutError)
		{
			const FOrderCheck Check = CheckArmyRules(State, Plan);
			if (!Check.bAllowed)
			{
				OutError = Check.Reason;
				return 0;
			}
			std::vector<int> Path;
			int Tenths = 0;
			FCity& City = At(State.Cities, Plan.City);
			const int Faction = City.Owner;
			FindRoute(State, Faction, Plan.City, Plan.Target, Path, Tenths);

			FArmy Army;
			Army.Id = State.NextArmyId++;
			Army.Faction = Faction;
			const std::vector<int> Split = SplitTroops(State, Plan.Officers, Plan.Troops);
			for (size_t Index = 0; Index < Plan.Officers.size(); ++Index)
			{
				Army.Units.push_back(FArmyUnit{Plan.Officers[Index], Split[Index], At(State.Officers, Plan.Officers[Index]).Specialty});
			}
			Army.Food = Plan.Food;
			Army.Training = City.Training;
			Army.Morale = ClampInt(50 + City.Training / 3 + StatOf(At(State.Officers, Plan.Officers.front()), EStat::Charm) / 10, 30, 100);
			Army.Home = Plan.City;
			Army.Target = Plan.Target;
			Army.State = EArmyState::Marching;
			Army.Node = Plan.City;
			Army.Next = Path.front();
			Army.Road = State.RoadBetween(Plan.City, Path.front());
			Army.Progress = 0;
			Army.Route.assign(Path.begin() + 1, Path.end());
			Army.bNew = true;

			City.Troops -= Plan.Troops;
			City.Food -= Plan.Food;
			for (const int Officer : Plan.Officers)
			{
				FOfficer& Data = At(State.Officers, Officer);
				Data.City = -1;
				Data.Army = Army.Id;
			}
			State.Armies.push_back(Army);

			const std::string Commander = OfficerLabel(State, Plan.Officers.front());
			const int TargetOwner = At(State.Cities, Plan.Target).Owner;
			if (IsPlayerFaction(State, Faction))
			{
				LogPlayer(State, LocF("log.army.formed", "{commander} sets out from {city} toward {target} with {troops} troops.", {{"commander", Commander}, {"city", NameOf(City)}, {"target", CityLabel(State, Plan.Target)}, {"troops", ToText(Plan.Troops)}}));
			}
			else if (IsPlayerFaction(State, TargetOwner))
			{
				LogPlayer(State, LocF("log.army.incoming", "Scouts report that {commander} of the {faction} is marching on {target} with {troops} troops.", {{"commander", Commander}, {"faction", FactionLabel(State, Faction)}, {"target", CityLabel(State, Plan.Target)}, {"troops", ToText(Plan.Troops)}}), true);
			}
			if (TargetOwner >= 0 && TargetOwner != Faction)
			{
				FRelation& Relation = State.Relation(Faction, TargetOwner);
				Relation.Trust = ClampInt(Relation.Trust - 5, 0, 100);
			}
			return Army.Id;
		}

		void MergeArmy(FGameState& State, int ArmyId, int City)
		{
			const FArmy* Army = State.FindArmy(ArmyId);
			if (!Army || !ValidCity(State, City))
			{
				return;
			}
			const FArmy Copy = *Army;
			MilitaryDetail::EraseArmy(State, ArmyId);
			FCity& Data = At(State.Cities, City);
			const int Troops = Copy.TotalTroops();
			const long long Sum = static_cast<long long>(Data.Troops) + Troops;
			if (Sum > 0)
			{
				Data.Training = static_cast<int>((static_cast<long long>(Data.Training) * Data.Troops + static_cast<long long>(Copy.Training) * Troops) / Sum);
			}
			Data.Troops += Troops;
			Data.Food += Copy.Food;
			for (const FArmyUnit& Unit : Copy.Units)
			{
				if (ValidOfficer(State, Unit.Officer))
				{
					FOfficer& Officer = At(State.Officers, Unit.Officer);
					Officer.Army = -1;
					Officer.City = City;
				}
			}
			if (IsPlayerFaction(State, Copy.Faction))
			{
				const std::string Commander = MilitaryDetail::CommanderName(State, Copy);
				if (Copy.State == EArmyState::Returning)
				{
					LogPlayer(State, LocF("log.army.returned", "The army of {commander} has returned to {city} with {troops} troops.", {{"commander", Commander}, {"city", NameOf(Data)}, {"troops", ToText(Troops)}}));
				}
				else
				{
					LogPlayer(State, LocF("log.army.arrived", "The army of {commander} has arrived in {city} with {troops} troops.", {{"commander", Commander}, {"city", NameOf(Data)}, {"troops", ToText(Troops)}}));
				}
			}
		}

		void StartReturn(FGameState& State, int ArmyId)
		{
			FArmy* Army = State.FindArmy(ArmyId);
			if (!Army)
			{
				return;
			}
			const int Faction = Army->Faction;
			Army->State = EArmyState::Returning;
			if (Army->Next < 0 || MilitaryDetail::RoadIndexOf(State, Army->Road) < 0)
			{
				if (ValidCity(State, Army->Node) && At(State.Cities, Army->Node).Owner == Faction)
				{
					MergeArmy(State, ArmyId, Army->Node);
				}
				else
				{
					MilitaryDetail::CutOff(State, ArmyId);
				}
				return;
			}
			const int Length = State.RoadLength(Army->Road);
			const int Back = Army->Progress;
			const int Forward = std::max(0, Length - Army->Progress);
			std::vector<int> DistBack;
			std::vector<int> PrevBack;
			std::vector<int> DistForward;
			std::vector<int> PrevForward;
			ShortestPaths(State, Army->Node, Faction, true, At(State.Cities, Army->Node).Owner == Faction, DistBack, PrevBack);
			ShortestPaths(State, Army->Next, Faction, true, At(State.Cities, Army->Next).Owner == Faction, DistForward, PrevForward);
			int Best = -1;
			int BestCost = Unreachable;
			bool bBack = true;
			for (int City = 0; City < CountOf(State.Cities); ++City)
			{
				if (At(State.Cities, City).Owner != Faction)
				{
					continue;
				}
				if (At(DistBack, City) < Unreachable && Back + At(DistBack, City) < BestCost)
				{
					Best = City;
					BestCost = Back + At(DistBack, City);
					bBack = true;
				}
				if (At(DistForward, City) < Unreachable && Forward + At(DistForward, City) < BestCost)
				{
					Best = City;
					BestCost = Forward + At(DistForward, City);
					bBack = false;
				}
			}
			if (Best < 0)
			{
				MilitaryDetail::CutOff(State, ArmyId);
				return;
			}
			const std::vector<int>& Prev = bBack ? PrevBack : PrevForward;
			const int Start = bBack ? Army->Node : Army->Next;
			std::vector<int> Path;
			for (int City = Best; City != Start && City >= 0; City = At(Prev, City))
			{
				Path.push_back(City);
			}
			std::reverse(Path.begin(), Path.end());
			if (bBack)
			{
				std::swap(Army->Node, Army->Next);
				Army->Progress = Forward;
			}
			Army->Route = Path;
			Army->Target = Best;
		}

		void BeginExecution(FGameState& State)
		{
			State.Phase = EPhase::Execution;
			State.Day = 1;
			State.bDayInProgress = false;
			State.BattleQueue.clear();
			ExecuteOrders(State);
			for (FArmy& Army : State.Armies)
			{
				Army.bNew = false;
			}
			UpdateFactions(State);
		}

		bool IsPlayerBattle(const FGameState& State, const FPendingBattle& Battle)
		{
			if (State.PlayerFaction < 0)
			{
				return false;
			}
			const FArmy* Attacker = State.FindArmy(Battle.Attacker);
			if (!Attacker)
			{
				return false;
			}
			if (Attacker->Faction == State.PlayerFaction)
			{
				return true;
			}
			if (Battle.Kind == EBattleKind::Field)
			{
				const FArmy* Defender = State.FindArmy(Battle.Defender);
				return Defender && Defender->Faction == State.PlayerFaction;
			}
			return ValidCity(State, Battle.City) && At(State.Cities, Battle.City).Owner == State.PlayerFaction;
		}

		FBattleSetup MakeBattleSetupRules(const FGameState& State, const FPendingBattle& Battle)
		{
			FBattleSetup Setup;
			Setup.Kind = Battle.Kind;
			Setup.Techniques = State.Techniques;
			Setup.MaxDays = DaysPerMonth;
			const FArmy* Attacker = State.FindArmy(Battle.Attacker);
			if (!Attacker)
			{
				return Setup;
			}
			// Deterministic seed derived from the game RNG without advancing it (this function is const).
			const uint64_t RngState = State.Rng.GetState();
			uint32_t Hash = HashCombine(static_cast<uint32_t>(RngState), static_cast<uint32_t>(RngState >> 32));
			Hash = HashCombine(Hash, static_cast<uint32_t>(Battle.Attacker));
			Hash = HashCombine(Hash, static_cast<uint32_t>(Battle.Defender));
			Hash = HashCombine(Hash, static_cast<uint32_t>(Battle.City + 1));
			Hash = HashCombine(Hash, static_cast<uint32_t>((State.Year * 12 + State.Month) * 32 + State.Day));
			Setup.Seed = (static_cast<uint64_t>(Hash) << 32) | HashCombine(Hash, 0x5EEDu);

			MilitaryDetail::FillArmySide(State, *Attacker, Setup.Sides[0]);
			if (Battle.Kind == EBattleKind::Field)
			{
				const FArmy* Defender = State.FindArmy(Battle.Defender);
				if (Defender)
				{
					MilitaryDetail::FillArmySide(State, *Defender, Setup.Sides[1]);
				}
				Setup.Terrain = MilitaryDetail::RoadTerrain(State, *Attacker);
				Setup.Location = LocF("battle.location.road", "Road to {city}", {{"city", CityLabel(State, Attacker->Next)}});
				Setup.CitySize = 1;
				Setup.GateHp = 0;
				Setup.WallBonus = 0;
				return Setup;
			}
			if (!ValidCity(State, Battle.City))
			{
				return Setup;
			}
			const FCity& City = At(State.Cities, Battle.City);
			Setup.Terrain = City.Terrain;
			Setup.Location = LocF("battle.location.siege", "Siege of {city}", {{"city", NameOf(City)}});
			Setup.CitySize = City.Size;
			Setup.GateHp = 300 + City.Defense * 2;
			Setup.WallBonus = ClampInt(15 + City.Defense / 30, 0, 60);
			MilitaryDetail::FillCitySide(State, Battle.City, Setup.Sides[1]);
			return Setup;
		}

		void ApplyBattleResult(FGameState& State, const FPendingBattle& Battle, const FBattleResult& Result)
		{
			if (!State.BattleQueue.empty())
			{
				const FPendingBattle& Front = State.BattleQueue.front();
				if (Front.Kind == Battle.Kind && Front.Attacker == Battle.Attacker && Front.Defender == Battle.Defender && Front.City == Battle.City)
				{
					State.BattleQueue.erase(State.BattleQueue.begin());
				}
			}
			const FArmy* AttackerArmy = State.FindArmy(Battle.Attacker);
			if (!AttackerArmy)
			{
				UpdateFactions(State);
				return;
			}
			const FBattleSetup Setup = MakeBattleSetupRules(State, Battle);
			std::vector<const FUnitOutcome*> Outcomes[2];
			for (const FUnitOutcome& Unit : Result.Units)
			{
				if (Unit.Side == 0 || Unit.Side == 1)
				{
					Outcomes[Unit.Side].push_back(&Unit);
				}
			}
			const bool bAttackerWon = Result.Winner == 0;
			const int Days = std::max(1, Result.Days);
			const int AttackerFaction = AttackerArmy->Faction;
			const int AttackerNode = AttackerArmy->Node;

			if (Battle.Kind == EBattleKind::Field)
			{
				const FArmy* DefenderArmy = State.FindArmy(Battle.Defender);
				if (!DefenderArmy)
				{
					UpdateFactions(State);
					return;
				}
				const int DefenderFaction = DefenderArmy->Faction;
				const int Destination = AttackerArmy->Next;
				const int AttackerPrison = NearestOwnedCity(State, AttackerFaction, AttackerNode);
				const int DefenderPrison = NearestOwnedCity(State, DefenderFaction, DefenderArmy->Node);
				MilitaryDetail::ApplyArmySide(State, Battle.Attacker, Outcomes[0], DefenderFaction, DefenderPrison, bAttackerWon, Days);
				MilitaryDetail::ApplyArmySide(State, Battle.Defender, Outcomes[1], AttackerFaction, AttackerPrison, !bAttackerWon, Days);
				StartReturn(State, bAttackerWon ? Battle.Defender : Battle.Attacker);
				FRelation& Relation = State.Relation(AttackerFaction, DefenderFaction);
				Relation.Trust = ClampInt(Relation.Trust - 5, 0, 100);
				const int Winner = bAttackerWon ? AttackerFaction : DefenderFaction;
				const int Loser = bAttackerWon ? DefenderFaction : AttackerFaction;
				LogBetween(State, AttackerFaction, DefenderFaction, LocF("log.battle.field", "The {winner} defeated the {loser} in a battle on the road to {city}.", {{"winner", FactionLabel(State, Winner)}, {"loser", FactionLabel(State, Loser)}, {"city", CityLabel(State, Destination)}}), IsPlayerFaction(State, AttackerFaction) || IsPlayerFaction(State, DefenderFaction));
			}
			else if (ValidCity(State, Battle.City))
			{
				const int CityIndex = Battle.City;
				const int DefenderFaction = At(State.Cities, CityIndex).Owner;
				MilitaryDetail::ApplyArmySide(State, Battle.Attacker, Outcomes[0], DefenderFaction, CityIndex, bAttackerWon, Days);

				int Survivors = 0;
				std::vector<int> Captured;
				std::vector<int> Killed;
				const std::vector<FBattleUnitSetup>& Defenders = Setup.Sides[1].Units;
				for (size_t Index = 0; Index < Defenders.size(); ++Index)
				{
					const FUnitOutcome* Outcome = MilitaryDetail::OutcomeFor(Outcomes[1], Index, Defenders[Index].Officer);
					if (!Outcome)
					{
						Survivors += Defenders[Index].Troops;
						continue;
					}
					Survivors += ClampInt(Outcome->Troops, 0, Defenders[Index].Troops);
					const int Officer = Defenders[Index].Officer;
					if (Officer < 0)
					{
						continue;
					}
					MilitaryDetail::GrantBattleExp(State, Officer, *Outcome, !bAttackerWon);
					if (Outcome->Status == EUnitStatus::Captured)
					{
						Captured.push_back(Officer);
					}
					else if (Outcome->Status == EUnitStatus::Killed)
					{
						Killed.push_back(Officer);
					}
				}
				At(State.Cities, CityIndex).Troops = Survivors;
				for (const int Officer : Killed)
				{
					if (IsPlayerFaction(State, DefenderFaction) || IsPlayerFaction(State, AttackerFaction))
					{
						LogPlayer(State, LocF("log.officer.killed", "{officer} of the {faction} has fallen in battle.", {{"officer", OfficerLabel(State, Officer)}, {"faction", FactionLabel(State, DefenderFaction)}}), true);
					}
					KillOfficer(State, Officer);
				}
				const FArmy* Survivor = State.FindArmy(Battle.Attacker);
				if (DefenderFaction >= 0)
				{
					FRelation& Relation = State.Relation(AttackerFaction, DefenderFaction);
					Relation.Trust = ClampInt(Relation.Trust - 5, 0, 100);
				}
				if (bAttackerWon && Survivor && Survivor->TotalTroops() > 0)
				{
					MilitaryDetail::CaptureCity(State, CityIndex, Battle.Attacker, Survivors, Captured);
				}
				else
				{
					const int Prison = Survivor ? NearestOwnedCity(State, AttackerFaction, Survivor->Node) : NearestOwnedCity(State, AttackerFaction, AttackerNode);
					for (const int Officer : Captured)
					{
						CaptureOfficer(State, Officer, AttackerFaction, Prison);
					}
					if (Survivor)
					{
						StartReturn(State, Battle.Attacker);
					}
					const FCity& Data = At(State.Cities, CityIndex);
					if (DefenderFaction < 0)
					{
						LogBetween(State, AttackerFaction, DefenderFaction, LocF("log.battle.siegeRepelledIndependent", "The defenders of {city} drove off the {faction}.", {{"city", NameOf(Data)}, {"faction", FactionLabel(State, AttackerFaction)}}), IsPlayerFaction(State, AttackerFaction));
					}
					else
					{
						LogBetween(State, AttackerFaction, DefenderFaction, LocF("log.battle.siegeRepelled", "The {defender} held {city} against the {attacker}.", {{"defender", FactionLabel(State, DefenderFaction)}, {"city", NameOf(Data)}, {"attacker", FactionLabel(State, AttackerFaction)}}), IsPlayerFaction(State, AttackerFaction) || IsPlayerFaction(State, DefenderFaction));
					}
				}
			}
			State.Rng.Next();
			UpdateFactions(State);
		}

		EStepResult StepRules(FGameState& State)
		{
			if (State.Phase == EPhase::GameOver)
			{
				return EStepResult::GameOver;
			}
			if (State.Phase != EPhase::Execution)
			{
				return EStepResult::Idle;
			}
			if (!State.bDayInProgress)
			{
				State.bDayInProgress = true;
				MilitaryDetail::AdvanceArmies(State);
				UpdateFactions(State);
				if (State.Phase == EPhase::GameOver)
				{
					return EStepResult::GameOver;
				}
			}
			while (!State.BattleQueue.empty())
			{
				const FPendingBattle Battle = State.BattleQueue.front();
				if (!MilitaryDetail::PrepareBattle(State, Battle))
				{
					if (!State.BattleQueue.empty())
					{
						State.BattleQueue.erase(State.BattleQueue.begin());
					}
					if (State.Phase == EPhase::GameOver)
					{
						return EStepResult::GameOver;
					}
					continue;
				}
				if (IsPlayerBattle(State, Battle))
				{
					return EStepResult::PlayerBattle;
				}
				const FBattleResult Result = ResolveBattleAuto(MakeBattleSetupRules(State, Battle));
				ApplyBattleResult(State, Battle, Result);
				if (State.Phase == EPhase::GameOver)
				{
					return EStepResult::GameOver;
				}
			}
			State.bDayInProgress = false;
			if (State.Day >= DaysPerMonth)
			{
				EndMonthRules(State);
				return State.Phase == EPhase::GameOver ? EStepResult::GameOver : EStepResult::MonthEnded;
			}
			++State.Day;
			return EStepResult::DayAdvanced;
		}
	}

	// =============================================================================================
	// FGame: military
	// =============================================================================================

	int FGame::MaxUnitTroops(int Officer) const
	{
		return GameRules::MaxUnitTroopsOf(State, Officer);
	}

	std::vector<int> FGame::MarchTargets(int City) const
	{
		if (!IsPlayerCity(City))
		{
			return std::vector<int>();
		}
		return GameRules::MarchTargetsOf(State, City, State.PlayerFaction);
	}

	int FGame::MarchDays(int City, int Target) const
	{
		if (!GameRules::ValidCity(State, City) || !GameRules::ValidCity(State, Target))
		{
			return -1;
		}
		std::vector<int> Path;
		int Tenths = 0;
		if (!GameRules::FindRoute(State, GameRules::At(State.Cities, City).Owner, City, Target, Path, Tenths))
		{
			return -1;
		}
		return (Tenths + 9) / 10;
	}

	int FGame::ArmyDailyFood(int Troops) const
	{
		return GameRules::ArmyFoodPerDay(Troops);
	}

	FOrderCheck FGame::CheckArmy(const FArmyPlan& Plan) const
	{
		if (!IsPlayerCity(Plan.City))
		{
			FOrderCheck Check;
			Check.Reason = Loc("order.reason.notYourCity", "This city is not under your control.");
			return Check;
		}
		return GameRules::CheckArmyRules(State, Plan);
	}

	bool FGame::FormArmy(const FArmyPlan& Plan, std::string& OutError)
	{
		if (!IsPlayerCity(Plan.City))
		{
			OutError = Loc("order.reason.notYourCity", "This city is not under your control.");
			return false;
		}
		return GameRules::FormArmyRules(State, Plan, OutError) > 0;
	}

	bool FGame::DisbandArmy(int ArmyId)
	{
		const FArmy* Army = State.FindArmy(ArmyId);
		if (!Army || !Army->bNew || State.Phase != EPhase::Planning || Army->Faction != State.PlayerFaction || State.PlayerFaction < 0)
		{
			return false;
		}
		if (!IsPlayerCity(Army->Home))
		{
			return false;
		}
		const FArmy Copy = *Army;
		GameRules::MilitaryDetail::EraseArmy(State, ArmyId);
		FCity& Home = GameRules::At(State.Cities, Copy.Home);
		Home.Troops += Copy.TotalTroops();
		Home.Food += Copy.Food;
		for (const FArmyUnit& Unit : Copy.Units)
		{
			if (GameRules::ValidOfficer(State, Unit.Officer))
			{
				FOfficer& Officer = GameRules::At(State.Officers, Unit.Officer);
				Officer.Army = -1;
				Officer.City = Copy.Home;
			}
		}
		return true;
	}

	void FGame::EndPlanning()
	{
		if (State.Phase != EPhase::Planning)
		{
			return;
		}
		// Unanswered events take their last available option; undecided prisoners stay imprisoned.
		for (int Guard = 0; Guard < 64 && !State.PendingEvents.empty(); ++Guard)
		{
			int Choice = 0;
			for (int Index = GameRules::CountOf(State.PendingEvents.front().Choices) - 1; Index >= 0; --Index)
			{
				if (GameRules::CanChooseRules(State, Index))
				{
					Choice = Index;
					break;
				}
			}
			GameRules::ChooseRules(State, Choice);
		}
		State.PendingEvents.clear();
		State.PendingPrisoners.clear();
		GameRules::BeginExecution(State);
	}

	EStepResult FGame::Step()
	{
		return GameRules::StepRules(State);
	}

	const FPendingBattle* FGame::PendingPlayerBattle() const
	{
		if (State.Phase != EPhase::Execution || !State.bDayInProgress || State.BattleQueue.empty())
		{
			return nullptr;
		}
		const FPendingBattle& Front = State.BattleQueue.front();
		return GameRules::IsPlayerBattle(State, Front) ? &Front : nullptr;
	}

	bool FGame::IsPlayerAttacker(const FPendingBattle& Battle) const
	{
		const FArmy* Attacker = State.FindArmy(Battle.Attacker);
		return Attacker && State.PlayerFaction >= 0 && Attacker->Faction == State.PlayerFaction;
	}

	FBattleSetup FGame::MakeBattleSetup(const FPendingBattle& Battle) const
	{
		return GameRules::MakeBattleSetupRules(State, Battle);
	}

	void FGame::ResolvePlayerBattle(const FBattleResult& Result)
	{
		const FPendingBattle* Pending = PendingPlayerBattle();
		if (!Pending)
		{
			return;
		}
		const FPendingBattle Battle = *Pending;
		GameRules::ApplyBattleResult(State, Battle, Result);
	}

	void FGame::AutoResolvePlayerBattle()
	{
		const FPendingBattle* Pending = PendingPlayerBattle();
		if (!Pending)
		{
			return;
		}
		const FPendingBattle Battle = *Pending;
		const FBattleResult Result = ResolveBattleAuto(GameRules::MakeBattleSetupRules(State, Battle));
		GameRules::ApplyBattleResult(State, Battle, Result);
	}
}
