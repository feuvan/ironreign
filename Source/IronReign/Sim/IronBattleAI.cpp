#include "Sim/IronBattle.h"

#include "Sim/IronLocale.h"

#include <algorithm>
#include <functional>
#include <limits>
#include <queue>
#include <utility>

// Utility-based battle AI. Each StepAI call performs exactly one action (a move, an action, ending the
// turn, or settling a duel), so the UI can animate AI turns step by step.

namespace IronSim
{
	namespace BattleAIDetail
	{
		enum class EPlanKind : uint8_t
		{
			Wait,
			Attack,
			Gate,
			Tactic,
			Duel
		};

		struct FPlan
		{
			FHex Dest = {-1, -1};
			EPlanKind Kind = EPlanKind::Wait;
			ETactic Tactic = ETactic::Fire;
			int Target = -1;
			double Score = -1.0e300;
		};

		/** Turns-to-goal assumed for unreachable goals. */
		constexpr double FarTurns = 30.0;
		/** Utility of winning or losing the battle outright (commander falls). */
		constexpr double DecisiveValue = 100000.0;
		constexpr int RoutMorale = 10;
		constexpr int Unreached = std::numeric_limits<int>::max();
		/** Safety net for AutoResolve; real battles need a few thousand steps at most. */
		constexpr int MaxAutoSteps = 200000;
		/** Must match the core's encoding of IssuedChallenges. */
		constexpr int ChallengeKeyStride = 4096;

		/** Utility of one morale point for a unit of the given size, in troop-equivalents. */
		double MoraleValue(int Troops)
		{
			return Troops / 300.0;
		}

		int MartialOf(const FBattleUnit& Unit)
		{
			return Unit.Setup.Stats[StatIndex(EStat::Martial)];
		}
	}

	struct FBattleInternals
	{
		struct FContext
		{
			int Side = 0;
			double Aggression = 1.0;
			/** Per unit id: hexes that enemy unit can attack on its next turn (empty when it is no threat). */
			std::vector<std::vector<uint8_t>> Cover;
		};

		/** A commander with an army to hide behind plays it safe; a lone commander has to fight. */
		static bool IsCautiousCommander(const FBattle& Battle, const FBattleUnit& Self);
		static void BuildContext(const FBattle& Battle, FContext& Context);
		static void GoalSources(const FBattle& Battle, int UnitId, std::vector<FHex>& OutSources);
		static void GoalField(const FBattle& Battle, int UnitId, const std::vector<FHex>& Sources, std::vector<int>& OutDistance);
		static double PositionValue(const FBattle& Battle, const FContext& Context, int UnitId, FHex Pos, const std::vector<int>& Goal, const std::vector<double>& ThreatRaw);
		static double AttackValue(const FBattle& Battle, int UnitId, FHex Pos, int TargetId, bool bRanged);
		static void ConsiderActions(const FBattle& Battle, const FContext& Context, int UnitId, FHex Pos, double Base, BattleAIDetail::FPlan& InOutBest);
		static BattleAIDetail::FPlan PlanUnit(const FBattle& Battle, const FContext& Context, int UnitId, double& OutStayValue);
		static void Execute(FBattle& Battle, int UnitId, const BattleAIDetail::FPlan& Plan);
		static bool Act(FBattle& Battle);
	};

	bool FBattleInternals::IsCautiousCommander(const FBattle& Battle, const FBattleUnit& Self)
	{
		if (!Self.bCommander)
		{
			return false;
		}
		for (const FBattleUnit& Ally : Battle.BattleUnits)
		{
			if (Ally.IsActive() && Ally.Side == Self.Side && Ally.Id != Self.Id)
			{
				return true;
			}
		}
		return false;
	}

	void FBattleInternals::BuildContext(const FBattle& Battle, FContext& Context)
	{
		Context.Side = Battle.CurrentSide;
		const int Today = Battle.CurrentDay;
		if (Context.Side == 0)
		{
			// The attacker must win before the day limit or its food runs out: it presses harder every day.
			Context.Aggression = 1.0 + 0.06 * (Today - 1);
			if (Battle.Config.Sides[0].FoodDays - Today <= 3)
			{
				Context.Aggression += 0.5;
			}
		}
		else
		{
			Context.Aggression = 1.0;
		}

		const size_t CellCount = static_cast<size_t>(Battle.GridCols * Battle.GridRows);
		Context.Cover.assign(Battle.BattleUnits.size(), std::vector<uint8_t>());
		for (const FBattleUnit& Enemy : Battle.BattleUnits)
		{
			if (!Enemy.IsActive() || Enemy.Side == Context.Side || Enemy.ConfusedDays > 0 || !Battle.InBounds(Enemy.Pos))
			{
				continue;
			}
			std::vector<uint8_t>& Cover = Context.Cover[static_cast<size_t>(Enemy.Id)];
			Cover.assign(CellCount, 0);
			const bool bLongRange = Enemy.Setup.Type == ETroopType::Archer;
			std::vector<FHex> Origins;
			Origins.push_back(Enemy.Pos);
			for (const FReachableHex& Entry : Battle.ComputeReach(Enemy.Id))
			{
				Origins.push_back(Entry.Hex);
			}
			for (const FHex& Origin : Origins)
			{
				FHex Around[6];
				HexMath::Neighbors(Origin, Around);
				for (const FHex& Near : Around)
				{
					if (Battle.InBounds(Near))
					{
						Cover[static_cast<size_t>(Battle.HexIndex(Near))] = 1;
					}
					if (bLongRange)
					{
						FHex Outer[6];
						HexMath::Neighbors(Near, Outer);
						for (const FHex& Far : Outer)
						{
							if (Battle.InBounds(Far))
							{
								Cover[static_cast<size_t>(Battle.HexIndex(Far))] = 1;
							}
						}
					}
				}
			}
		}
	}

	void FBattleInternals::GoalSources(const FBattle& Battle, int UnitId, std::vector<FHex>& OutSources)
	{
		OutSources.clear();
		const FBattleUnit& Self = Battle.BattleUnits[static_cast<size_t>(UnitId)];
		const bool bArcher = Self.Setup.Type == ETroopType::Archer;
		const bool bSiege = Battle.Config.Kind == EBattleKind::Siege;
		const int Wall = Battle.WallCol;

		// Hexes at exactly Radius from Center (optionally restricted to one side of the wall).
		const auto AddRing = [&](FHex Center, int Radius, int MinCol, int MaxCol)
		{
			for (int Row = Center.Row - Radius - 1; Row <= Center.Row + Radius + 1; ++Row)
			{
				for (int Col = std::max(MinCol, Center.Col - Radius); Col <= std::min(MaxCol, Center.Col + Radius); ++Col)
				{
					const FHex Hex = {Col, Row};
					if (Battle.InBounds(Hex) && HexMath::Distance(Hex, Center) == Radius && Battle.TerrainEnterCost(Hex, Self.Setup.Type, Self.Side) >= 0)
					{
						OutSources.push_back(Hex);
					}
				}
			}
		};
		const auto AddEnemy = [&](const FBattleUnit& Enemy, int MinCol, int MaxCol)
		{
			if (bArcher)
			{
				AddRing(Enemy.Pos, 2, MinCol, MaxCol);
			}
			else
			{
				OutSources.push_back(Enemy.Pos);
			}
		};
		const int AllCols = Battle.GridCols - 1;

		if (!bSiege)
		{
			for (const FBattleUnit& Enemy : Battle.BattleUnits)
			{
				if (Enemy.IsActive() && Enemy.Side != Self.Side)
				{
					AddEnemy(Enemy, 0, AllCols);
				}
			}
		}
		else if (Self.Side == 0)
		{
			bool bAnyIntact = false;
			bool bAnyBroken = false;
			for (int Slot = 0; Slot < Battle.GateCount(); ++Slot)
			{
				const EHexTerrain Terrain = Battle.TerrainAt(Battle.GateHexAt(Slot));
				bAnyIntact = bAnyIntact || Terrain == EHexTerrain::Gate;
				bAnyBroken = bAnyBroken || Terrain == EHexTerrain::Rubble;
			}
			for (const FBattleUnit& Enemy : Battle.BattleUnits)
			{
				// Defenders who sallied out, or who block the breach, are fair game.
				if (Enemy.IsActive() && Enemy.Side != Self.Side && (Enemy.Pos.Col < Wall || bAnyBroken))
				{
					AddEnemy(Enemy, 0, AllCols);
				}
			}
			if (bAnyBroken || !bAnyIntact)
			{
				OutSources.push_back(Battle.Castle);
			}
			else
			{
				for (int Slot = 0; Slot < Battle.GateCount(); ++Slot)
				{
					const FHex GateAt = Battle.GateHexAt(Slot);
					if (Battle.TerrainAt(GateAt) != EHexTerrain::Gate)
					{
						continue;
					}
					if (Self.bCommander)
					{
						AddRing(GateAt, 4, 0, Wall - 1);
					}
					else if (bArcher)
					{
						AddRing(GateAt, 2, 0, Wall - 1);
					}
					else
					{
						AddRing(GateAt, 1, 0, Wall - 1);
					}
				}
			}
		}
		else
		{
			if (Self.bCommander)
			{
				OutSources.push_back(Battle.Castle);
			}
			else
			{
				for (const FBattleUnit& Enemy : Battle.BattleUnits)
				{
					// Intruders inside the walls or in the breach.
					if (Enemy.IsActive() && Enemy.Side != Self.Side && Enemy.Pos.Col >= Wall)
					{
						AddEnemy(Enemy, Wall, AllCols);
					}
				}
				for (int Slot = 0; Slot < Battle.GateCount(); ++Slot)
				{
					const FHex GateAt = Battle.GateHexAt(Slot);
					const bool bBroken = Battle.TerrainAt(GateAt) == EHexTerrain::Rubble;
					if (bArcher)
					{
						// The wall walk next to the gate, in bow range of the approach.
						for (int Row = GateAt.Row - 3; Row <= GateAt.Row + 3; ++Row)
						{
							const FHex Hex = {Wall + 1, Row};
							if (Battle.InBounds(Hex) && Battle.TerrainEnterCost(Hex, Self.Setup.Type, Self.Side) >= 0)
							{
								OutSources.push_back(Hex);
							}
						}
					}
					else if (bBroken)
					{
						// Plug the breach.
						OutSources.push_back(GateAt);
						AddRing(GateAt, 1, Wall + 1, AllCols);
					}
					else
					{
						// Wait two hexes behind the gate, out of reach of fire from outside, ready to counter a breach.
						AddRing(GateAt, 2, Wall + 2, AllCols);
					}
				}
			}
		}

		if (OutSources.empty())
		{
			for (const FBattleUnit& Enemy : Battle.BattleUnits)
			{
				if (Enemy.IsActive() && Enemy.Side != Self.Side)
				{
					OutSources.push_back(Enemy.Pos);
				}
			}
		}
		if (OutSources.empty())
		{
			OutSources.push_back(Self.Pos);
		}
	}

	void FBattleInternals::GoalField(const FBattle& Battle, int UnitId, const std::vector<FHex>& Sources, std::vector<int>& OutDistance)
	{
		const FBattleUnit& Self = Battle.BattleUnits[static_cast<size_t>(UnitId)];
		const size_t CellCount = static_cast<size_t>(Battle.GridCols * Battle.GridRows);
		OutDistance.assign(CellCount, BattleAIDetail::Unreached);
		using FEntry = std::pair<int, int>;
		std::priority_queue<FEntry, std::vector<FEntry>, std::greater<FEntry>> Queue;
		for (const FHex& Source : Sources)
		{
			if (!Battle.InBounds(Source))
			{
				continue;
			}
			const int Cell = Battle.HexIndex(Source);
			if (OutDistance[static_cast<size_t>(Cell)] != 0)
			{
				OutDistance[static_cast<size_t>(Cell)] = 0;
				Queue.push({0, Cell});
			}
		}
		// Reverse Dijkstra: stepping from a neighbor into Here costs Here's entry cost (units and fire ignored).
		while (!Queue.empty())
		{
			const FEntry Top = Queue.top();
			Queue.pop();
			if (Top.first != OutDistance[static_cast<size_t>(Top.second)])
			{
				continue;
			}
			const FHex Here = {Top.second % Battle.GridCols, Top.second / Battle.GridCols};
			int StepCost = Battle.TerrainEnterCost(Here, Self.Setup.Type, Self.Side);
			if (StepCost < 0)
			{
				StepCost = 1;
			}
			FHex Around[6];
			HexMath::Neighbors(Here, Around);
			for (const FHex& Next : Around)
			{
				if (!Battle.InBounds(Next) || Battle.TerrainEnterCost(Next, Self.Setup.Type, Self.Side) < 0)
				{
					continue;
				}
				const int NextCell = Battle.HexIndex(Next);
				const int Total = Top.first + StepCost;
				if (Total < OutDistance[static_cast<size_t>(NextCell)])
				{
					OutDistance[static_cast<size_t>(NextCell)] = Total;
					Queue.push({Total, NextCell});
				}
			}
		}
	}

	double FBattleInternals::PositionValue(const FBattle& Battle, const FContext& Context, int UnitId, FHex Pos, const std::vector<int>& Goal, const std::vector<double>& ThreatRaw)
	{
		const FBattleUnit& Self = Battle.BattleUnits[static_cast<size_t>(UnitId)];
		const bool bSiege = Battle.Config.Kind == EBattleKind::Siege;
		const size_t Cell = static_cast<size_t>(Battle.HexIndex(Pos));
		const int Points = std::max(1, Battle.MovePoints(UnitId));

		// Progress toward the unit's goal, in turns of marching.
		double GoalWeight = 140.0 * Context.Aggression;
		double Risk = 0.35;
		if (bSiege && Self.Side == 0)
		{
			Risk = 0.25;
		}
		if (bSiege && Self.Side == 1)
		{
			GoalWeight = 200.0;
		}
		const bool bCautious = IsCautiousCommander(Battle, Self);
		if (Self.bCommander && bSiege && Self.Side == 1)
		{
			GoalWeight = 800.0;
			Risk = 2.0;
		}
		else if (bCautious)
		{
			GoalWeight *= 0.3;
			Risk = 2.0;
		}
		const int Distance = Goal[Cell];
		const double Turns = Distance == BattleAIDetail::Unreached ? BattleAIDetail::FarTurns : static_cast<double>(Distance) / Points;
		double Value = -GoalWeight * Turns;

		// Good ground.
		Value += 2.0 * Battle.TerrainDefenseBonus(Pos, Self.Side);

		// Danger: expected damage from every enemy able to strike this hex next turn.
		const double Multiplier = Battle.DefenseMultiplier(Pos, Self.Side);
		double Threat = 0.0;
		int Threats = 0;
		for (size_t Id = 0; Id < Context.Cover.size(); ++Id)
		{
			if (!Context.Cover[Id].empty() && Context.Cover[Id][Cell])
			{
				Threat += ThreatRaw[Id] * Multiplier;
				++Threats;
			}
		}
		Value -= Risk * 0.5 * Threat;

		if (Self.bCommander)
		{
			if (bSiege && Self.Side == 1)
			{
				// The castle must never be left empty.
				if (Pos != Battle.Castle)
				{
					Value -= 5000.0;
				}
			}
			else if (bCautious)
			{
				if (Threats > 0)
				{
					const double Shock = 3.0 * Threats + 60.0 * Threat / std::max(1, Self.Troops);
					if (Self.Morale - Shock < 20.0 || Threat >= Self.Troops * 0.8)
					{
						Value -= BattleAIDetail::DecisiveValue * 0.2;
					}
				}
				// Stay close to the army.
				int Nearest = 1000;
				for (const FBattleUnit& Ally : Battle.BattleUnits)
				{
					if (Ally.IsActive() && Ally.Side == Self.Side && Ally.Id != UnitId)
					{
						Nearest = std::min(Nearest, HexMath::Distance(Ally.Pos, Pos));
					}
				}
				if (Nearest < 1000 && Nearest > 2)
				{
					Value -= 40.0 * (Nearest - 2);
				}
			}
		}
		// Archers keep their distance.
		if (Self.Setup.Type == ETroopType::Archer && Battle.HasEnemyNeighbor(Pos, Self.Side))
		{
			Value -= 250.0;
		}
		// Defenders hold the walls instead of sallying out.
		if (bSiege && Self.Side == 1 && Pos.Col < Battle.WallCol)
		{
			Value -= 3000.0;
		}
		return Value;
	}

	double FBattleInternals::AttackValue(const FBattle& Battle, int UnitId, FHex Pos, int TargetId, bool bRanged)
	{
		const FBattleUnit& Self = Battle.BattleUnits[static_cast<size_t>(UnitId)];
		const FBattleUnit& Enemy = Battle.BattleUnits[static_cast<size_t>(TargetId)];
		const double EnemyTroops = std::max(1, Enemy.Troops);
		const double Damage = std::min(EnemyTroops, Battle.RawDamage(UnitId, Self.Troops, Self.Morale, TargetId, bRanged) * Battle.DefenseMultiplier(Enemy.Pos, Enemy.Side));
		const double Shock = 3.0 + 60.0 * Damage / EnemyTroops;
		// Focus fire: a hit is worth more against a unit it hurts proportionally more.
		double Value = Damage * (1.0 + Damage / EnemyTroops) + Shock * BattleAIDetail::MoraleValue(Enemy.Troops);
		if (Enemy.bCommander)
		{
			Value *= 1.6;
		}
		const bool bFalls = Damage >= EnemyTroops - 0.5 || Enemy.Morale - Shock < BattleAIDetail::RoutMorale;
		if (bFalls)
		{
			Value += Enemy.bCommander ? BattleAIDetail::DecisiveValue : (EnemyTroops - Damage) * 0.8 + 300.0;
		}
		else if (!bRanged)
		{
			const int TroopsAfter = std::max(1, static_cast<int>(EnemyTroops - Damage));
			const int MoraleAfter = static_cast<int>(Enemy.Morale - Shock);
			const double Counter = 0.5 * Battle.RawDamage(TargetId, TroopsAfter, MoraleAfter, UnitId, false) * Battle.DefenseMultiplier(Pos, Self.Side);
			const double CounterShock = 1.0 + 60.0 * Counter / std::max(1, Self.Troops);
			const double Caution = IsCautiousCommander(Battle, Self) ? 2.5 : 1.0;
			Value -= Caution * (Counter + CounterShock * BattleAIDetail::MoraleValue(Self.Troops));
			if (Self.Morale - CounterShock < BattleAIDetail::RoutMorale || Counter >= Self.Troops)
			{
				Value -= Self.bCommander ? BattleAIDetail::DecisiveValue : Self.Troops * 0.8;
			}
		}
		return Value;
	}

	void FBattleInternals::ConsiderActions(const FBattle& Battle, const FContext& Context, int UnitId, FHex Pos, double Base, BattleAIDetail::FPlan& InOutBest)
	{
		using BattleAIDetail::EPlanKind;
		const FBattleUnit& Self = Battle.BattleUnits[static_cast<size_t>(UnitId)];
		const auto Offer = [&](double Value, EPlanKind Kind, ETactic Tactic, int Target)
		{
			if (Base + Value > InOutBest.Score + 1.0e-6)
			{
				InOutBest.Dest = Pos;
				InOutBest.Kind = Kind;
				InOutBest.Tactic = Tactic;
				InOutBest.Target = Target;
				InOutBest.Score = Base + Value;
			}
		};
		Offer(0.0, EPlanKind::Wait, ETactic::Fire, -1);

		const bool bArcher = Self.Setup.Type == ETroopType::Archer;
		for (const FBattleUnit& Enemy : Battle.BattleUnits)
		{
			if (!Enemy.IsActive() || Enemy.Side == Self.Side)
			{
				continue;
			}
			const int Distance = HexMath::Distance(Pos, Enemy.Pos);
			const double EnemyTroops = std::max(1, Enemy.Troops);
			if (Distance == 1 || (Distance == 2 && bArcher))
			{
				Offer(AttackValue(Battle, UnitId, Pos, Enemy.Id, Distance == 2), EPlanKind::Attack, ETactic::Fire, Enemy.Id);
			}
			if (Distance >= 1 && Distance <= 2)
			{
				if (Battle.TerrainAt(Enemy.Pos) != EHexTerrain::Ford)
				{
					const double Chance = Battle.TacticChance(UnitId, ETactic::Fire, Enemy.Id) / 100.0;
					const double Damage = std::min(EnemyTroops, Battle.ExpectedFireDamage(UnitId, Enemy.Pos));
					const double Shock = 10.0 + 60.0 * Damage / EnemyTroops;
					double Value = Damage * (1.0 + Damage / EnemyTroops) + Shock * BattleAIDetail::MoraleValue(Enemy.Troops) + 0.5 * std::max(30.0, EnemyTroops * 0.06);
					if (Enemy.bCommander)
					{
						Value *= 1.6;
					}
					if (Damage >= EnemyTroops - 0.5 || Enemy.Morale - Shock < BattleAIDetail::RoutMorale)
					{
						Value += Enemy.bCommander ? BattleAIDetail::DecisiveValue : EnemyTroops * 0.8;
					}
					Offer(Chance * Value, EPlanKind::Tactic, ETactic::Fire, Enemy.Id);
				}
				if (Enemy.ConfusedDays <= 0)
				{
					// Worth roughly the blow the enemy would deal next turn, if it can reach anyone.
					bool bThreatening = false;
					const std::vector<uint8_t>& Cover = Context.Cover[static_cast<size_t>(Enemy.Id)];
					if (!Cover.empty())
					{
						for (const FBattleUnit& Ally : Battle.BattleUnits)
						{
							if (Ally.IsActive() && Ally.Side == Self.Side && Cover[static_cast<size_t>(Battle.HexIndex(Ally.Id == UnitId ? Pos : Ally.Pos))])
							{
								bThreatening = true;
								break;
							}
						}
					}
					const double Chance = Battle.TacticChance(UnitId, ETactic::Confuse, Enemy.Id) / 100.0;
					const double Value = (0.6 * Battle.RawDamage(Enemy.Id, Enemy.Troops, Enemy.Morale, UnitId, Enemy.Setup.Type == ETroopType::Archer) + 50.0) * (bThreatening ? 1.0 : 0.25);
					Offer(Chance * Value, EPlanKind::Tactic, ETactic::Confuse, Enemy.Id);
				}
			}
			if (Distance == 1 && Self.Setup.Officer >= 0 && Enemy.Setup.Officer >= 0)
			{
				// Challenge only when clearly the better fighter (each pair may duel once per battle).
				const int Mine = BattleAIDetail::MartialOf(Self);
				const int Theirs = BattleAIDetail::MartialOf(Enemy);
				const int Margin = Self.bCommander ? 20 : 12;
				const int Key = UnitId * BattleAIDetail::ChallengeKeyStride + Enemy.Id;
				if (Mine - Theirs >= Margin && std::find(Battle.IssuedChallenges.begin(), Battle.IssuedChallenges.end(), Key) == Battle.IssuedChallenges.end())
				{
					const double Accept = Battle.IsSideAI(Enemy.Side) ? Battle.AcceptChance(UnitId, Enemy.Id) / 100.0 : 0.5;
					const double WinChance = std::clamp(0.5 + 0.012 * (Mine - Theirs), 0.05, 0.92);
					const double WinValue = 0.3 * EnemyTroops + 30.0 * BattleAIDetail::MoraleValue(Enemy.Troops) + 0.3 * (Enemy.bCommander ? BattleAIDetail::DecisiveValue : EnemyTroops * 0.7);
					const double LoseValue = 0.3 * Self.Troops + 30.0 * BattleAIDetail::MoraleValue(Self.Troops) + 0.3 * (Self.bCommander ? BattleAIDetail::DecisiveValue : Self.Troops * 0.7);
					const double DeclineValue = 12.0 * BattleAIDetail::MoraleValue(Enemy.Troops);
					const double Value = Accept * (WinChance * WinValue - (1.0 - WinChance) * LoseValue) + (1.0 - Accept) * DeclineValue;
					Offer(Value, EPlanKind::Duel, ETactic::Fire, Enemy.Id);
				}
			}
		}

		if (Battle.Config.Kind == EBattleKind::Siege && Self.Side == 0)
		{
			const int Slot = Battle.AdjacentIntactGate(Pos);
			if (Slot >= 0)
			{
				const double Hp = std::max(1, Battle.GateHpAt(Slot));
				const double Damage = Battle.ExpectedGateDamage(UnitId);
				double Value = 100.0 + 1.3 * std::min(Damage, Hp) + 300.0 * (1.0 - Hp / std::max(1, Battle.GateMaxHitPoints));
				if (Damage >= Hp)
				{
					Value += 2500.0;
				}
				Offer(Value, EPlanKind::Gate, ETactic::Fire, -1);
			}
		}

		for (const FBattleUnit& Ally : Battle.BattleUnits)
		{
			if (!Ally.IsActive() || Ally.Side != Self.Side || (Ally.Id != UnitId && HexMath::Distance(Pos, Ally.Pos) != 1))
			{
				continue;
			}
			const int Gain = std::min(100 - Ally.Morale, Battle.RallyAmount(UnitId));
			if (Gain <= 0 && Ally.ConfusedDays <= 0)
			{
				continue;
			}
			const double Urgency = Ally.Morale < 25 ? 3.0 : (Ally.Morale < 40 ? 1.8 : (Ally.Morale < 55 ? 0.8 : 0.0));
			double Value = Gain * BattleAIDetail::MoraleValue(Ally.Troops) * Urgency;
			if (Ally.ConfusedDays > 0 && !Ally.bActed)
			{
				Value += 300.0;
			}
			if (Ally.bCommander && Ally.Morale < 40)
			{
				Value += 2000.0;
			}
			Offer(Battle.TacticChance(UnitId, ETactic::Rally, Ally.Id) / 100.0 * Value, EPlanKind::Tactic, ETactic::Rally, Ally.Id);
		}
	}

	BattleAIDetail::FPlan FBattleInternals::PlanUnit(const FBattle& Battle, const FContext& Context, int UnitId, double& OutStayValue)
	{
		const FBattleUnit& Self = Battle.BattleUnits[static_cast<size_t>(UnitId)];
		std::vector<FHex> Sources;
		GoalSources(Battle, UnitId, Sources);
		std::vector<int> Goal;
		GoalField(Battle, UnitId, Sources, Goal);
		std::vector<double> ThreatRaw(Battle.BattleUnits.size(), 0.0);
		for (size_t Id = 0; Id < Context.Cover.size(); ++Id)
		{
			if (!Context.Cover[Id].empty())
			{
				const FBattleUnit& Enemy = Battle.BattleUnits[Id];
				ThreatRaw[Id] = Battle.RawDamage(Enemy.Id, Enemy.Troops, Enemy.Morale, UnitId, Enemy.Setup.Type == ETroopType::Archer);
			}
		}

		std::vector<FHex> Candidates;
		Candidates.push_back(Self.Pos);
		if (!Self.bMoved)
		{
			for (const FReachableHex& Entry : Battle.ComputeReach(UnitId))
			{
				Candidates.push_back(Entry.Hex);
			}
		}
		BattleAIDetail::FPlan Best;
		OutStayValue = 0.0;
		for (size_t Index = 0; Index < Candidates.size(); ++Index)
		{
			const double Base = PositionValue(Battle, Context, UnitId, Candidates[Index], Goal, ThreatRaw);
			if (Index == 0)
			{
				OutStayValue = Base;
			}
			ConsiderActions(Battle, Context, UnitId, Candidates[Index], Base, Best);
		}
		return Best;
	}

	void FBattleInternals::Execute(FBattle& Battle, int UnitId, const BattleAIDetail::FPlan& Plan)
	{
		using BattleAIDetail::EPlanKind;
		const FHex Current = Battle.BattleUnits[static_cast<size_t>(UnitId)].Pos;
		if (Plan.Dest != Current && Battle.InBounds(Plan.Dest) && Battle.Move(UnitId, Plan.Dest))
		{
			// The action follows on the next step, so the UI can animate the march first.
			return;
		}
		bool bDone = false;
		switch (Plan.Kind)
		{
		case EPlanKind::Attack:
			bDone = Battle.Attack(UnitId, Plan.Target);
			break;
		case EPlanKind::Gate:
			bDone = Battle.AttackGate(UnitId);
			break;
		case EPlanKind::Tactic:
			bDone = Battle.UseTactic(UnitId, Plan.Tactic, Plan.Target);
			break;
		case EPlanKind::Duel:
			bDone = Battle.ChallengeDuel(UnitId, Plan.Target);
			break;
		case EPlanKind::Wait:
			break;
		}
		if (!bDone && !Battle.Wait(UnitId))
		{
			// Never stall: whatever happened, this unit is done for the turn.
			FBattleUnit& Stuck = Battle.BattleUnits[static_cast<size_t>(UnitId)];
			Stuck.bMoved = true;
			Stuck.bActed = true;
		}
	}

	bool FBattleInternals::Act(FBattle& Battle)
	{
		FContext Context;
		// A unit that has marched acts next, so its move and its blow animate together.
		for (const FBattleUnit& Each : Battle.BattleUnits)
		{
			if (Each.bMoved && Battle.CanAct(Each.Id))
			{
				const int Mover = Each.Id;
				BuildContext(Battle, Context);
				double Stay = 0.0;
				const BattleAIDetail::FPlan Plan = PlanUnit(Battle, Context, Mover, Stay);
				Execute(Battle, Mover, Plan);
				return true;
			}
		}

		BuildContext(Battle, Context);
		int BestUnit = -1;
		BattleAIDetail::FPlan BestPlan;
		double BestGain = 0.0;
		for (const FBattleUnit& Each : Battle.BattleUnits)
		{
			if (!Battle.CanAct(Each.Id))
			{
				continue;
			}
			double Stay = 0.0;
			const BattleAIDetail::FPlan Plan = PlanUnit(Battle, Context, Each.Id, Stay);
			const double Gain = Plan.Score - Stay;
			if (BestUnit < 0 || Gain > BestGain + 1.0e-6)
			{
				BestUnit = Each.Id;
				BestPlan = Plan;
				BestGain = Gain;
			}
		}
		if (BestUnit < 0)
		{
			Battle.EndTurn();
			return true;
		}
		Execute(Battle, BestUnit, BestPlan);
		return true;
	}

	bool FBattle::StepAI()
	{
		if (Outcome.bFinished)
		{
			return false;
		}
		if (HasPendingChallenge())
		{
			if (!IsSideAI(BattleUnits[static_cast<size_t>(PendingChallenged)].Side))
			{
				return false;
			}
			AnswerChallenge(Rng.Chance(AcceptChance(PendingChallenger, PendingChallenged)));
			return true;
		}
		if (bDuelActive)
		{
			const bool bAllAI = IsSideAI(BattleUnits[static_cast<size_t>(DuelUnits[0])].Side) && IsSideAI(BattleUnits[static_cast<size_t>(DuelUnits[1])].Side);
			if (!bAllAI)
			{
				return false;
			}
			Duel.AutoPlay();
			FinishDuel();
			return true;
		}
		if (!IsSideAI(CurrentSide))
		{
			return false;
		}
		return FBattleInternals::Act(*this);
	}

	void FBattle::AutoResolve()
	{
		bAutoControl[0] = true;
		bAutoControl[1] = true;
		int Steps = 0;
		while (!Outcome.bFinished && Steps < BattleAIDetail::MaxAutoSteps)
		{
			if (!StepAI())
			{
				break;
			}
			++Steps;
		}
		if (!Outcome.bFinished)
		{
			EndBattle(1, LocF("battle.summary.calledOff", "{location}: the battle was broken off; {winner} holds the field.", {{"location", Config.Location.empty() ? Loc("battle.location.unknown", "the battlefield") : Config.Location}, {"winner", SideName(1)}}));
		}
	}
}
