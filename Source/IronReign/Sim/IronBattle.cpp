#include "Sim/IronBattle.h"

#include "Sim/IronLocale.h"

#include <algorithm>
#include <cmath>
#include <limits>

// Core rules of the tactical battle: names, hex math, queries, actions, turn flow and victory.
// Map generation and deployment live in IronBattleMap.cpp, the battle AI in IronBattleAI.cpp.

namespace IronSim
{
	namespace BattleDetail
	{
		const char* const HexTerrainIds[] = {"plain", "forest", "hill", "mountain", "water", "ford", "bridge", "road", "wall", "gate", "town", "castle", "rubble"};
		const char* const HexTerrainAssets[] = {"Plain", "Forest", "Hill", "Mountain", "Water", "Ford", "Bridge", "Road", "Wall", "Gate", "Town", "Castle", "Rubble"};
		static_assert(sizeof(HexTerrainIds) / sizeof(HexTerrainIds[0]) == static_cast<size_t>(EHexTerrain::Count), "Hex terrain id table out of date");
		static_assert(sizeof(HexTerrainAssets) / sizeof(HexTerrainAssets[0]) == static_cast<size_t>(EHexTerrain::Count), "Hex terrain asset table out of date");

		constexpr double SqrtThree = 1.7320508075688772;
		/** Units whose morale drops below this rout. */
		constexpr int RoutMorale = 10;
		/** Chance that an officer whose unit is wiped out is taken prisoner. */
		constexpr int WipeOutCaptureChance = 30;
		constexpr int DuelKillChance = 5;
		constexpr int DuelCaptureChance = 25;
		/** Used when a siege setup leaves GateHp / WallBonus at 0. */
		constexpr int DefaultGateHp = 1200;
		constexpr int DefaultWallBonus = 30;
		/** Encodes a (challenger, target) pair in IssuedChallenges. */
		constexpr int ChallengeKeyStride = 4096;

		std::string LocationOf(const FBattleSetup& Setup)
		{
			return Setup.Location.empty() ? Loc("battle.location.unknown", "the battlefield") : Setup.Location;
		}

		struct FCube
		{
			int X = 0;
			int Z = 0;
		};

		FCube CubeOf(FHex Hex)
		{
			FCube Cube;
			Cube.X = Hex.Col;
			Cube.Z = Hex.Row - (Hex.Col - (Hex.Col & 1)) / 2;
			return Cube;
		}

		FHex HexOfCube(int X, int Z)
		{
			FHex Hex;
			Hex.Col = X;
			Hex.Row = Z + (X - (X & 1)) / 2;
			return Hex;
		}

		int StatOf(const FBattleUnitSetup& Setup, EStat Stat)
		{
			return ClampInt(Setup.Stats[StatIndex(Stat)], 1, 150);
		}

		double TrainingFactor(int Training)
		{
			return 0.75 + ClampInt(Training, 0, 100) / 200.0;
		}

		double MoraleFactor(int Morale)
		{
			return 0.6 + ClampInt(Morale, 0, 100) / 250.0;
		}

		double OffenseOf(const FBattleUnitSetup& Setup, int Training)
		{
			const double Command = StatOf(Setup, EStat::Command);
			const double Martial = StatOf(Setup, EStat::Martial);
			const double Strategy = StatOf(Setup, EStat::Strategy);
			double Value = 0.6 * Command + 0.4 * Martial;
			if (Setup.Type == ETroopType::Cavalry)
			{
				Value = 0.45 * Command + 0.55 * Martial;
			}
			else if (Setup.Type == ETroopType::Archer)
			{
				Value = 0.6 * Command + 0.2 * Martial + 0.2 * Strategy;
			}
			return std::max(5.0, Value * TrainingFactor(Training));
		}

		double DefenseOf(const FBattleUnitSetup& Setup, int Training)
		{
			const double Command = StatOf(Setup, EStat::Command);
			const double Martial = StatOf(Setup, EStat::Martial);
			const double Strategy = StatOf(Setup, EStat::Strategy);
			double Value = 0.7 * Command + 0.3 * Martial;
			if (Setup.Type == ETroopType::Archer)
			{
				Value = 0.7 * Command + 0.15 * Martial + 0.15 * Strategy;
			}
			return std::max(5.0, Value * TrainingFactor(Training));
		}

		/** Troop type matchups: cavalry > archers, infantry > cavalry, archers > infantry at range. */
		double TypeFactor(ETroopType Attacker, ETroopType Defender, bool bRanged)
		{
			double Factor = 1.0;
			if (Attacker == ETroopType::Archer)
			{
				Factor = bRanged ? 0.85 : 0.65;
			}
			else if (Attacker == ETroopType::Cavalry)
			{
				Factor = 1.1;
			}
			if (Attacker == ETroopType::Cavalry && Defender == ETroopType::Archer)
			{
				Factor *= 1.3;
			}
			if (Attacker == ETroopType::Infantry && Defender == ETroopType::Cavalry)
			{
				Factor *= 1.2;
			}
			if (Attacker == ETroopType::Archer && bRanged && Defender == ETroopType::Infantry)
			{
				Factor *= 1.2;
			}
			return Factor;
		}
	}

	// ---------------------------------------------------------------------------------------------
	// Names
	// ---------------------------------------------------------------------------------------------

	const char* EnumName(EHexTerrain Value)
	{
		const int Index = static_cast<int>(Value);
		return (Index >= 0 && Index < static_cast<int>(EHexTerrain::Count)) ? BattleDetail::HexTerrainIds[Index] : "unknown";
	}

	const char* AssetName(EHexTerrain Value)
	{
		const int Index = static_cast<int>(Value);
		return (Index >= 0 && Index < static_cast<int>(EHexTerrain::Count)) ? BattleDetail::HexTerrainAssets[Index] : "Plain";
	}

	std::string DisplayName(EHexTerrain Value)
	{
		switch (Value)
		{
		case EHexTerrain::Plain: return Loc("hex.plain", "Plain");
		case EHexTerrain::Forest: return Loc("hex.forest", "Forest");
		case EHexTerrain::Hill: return Loc("hex.hill", "Hill");
		case EHexTerrain::Mountain: return Loc("hex.mountain", "Mountain");
		case EHexTerrain::Water: return Loc("hex.water", "Water");
		case EHexTerrain::Ford: return Loc("hex.ford", "Ford");
		case EHexTerrain::Bridge: return Loc("hex.bridge", "Bridge");
		case EHexTerrain::Road: return Loc("hex.road", "Road");
		case EHexTerrain::Wall: return Loc("hex.wall", "Wall");
		case EHexTerrain::Gate: return Loc("hex.gate", "Gate");
		case EHexTerrain::Town: return Loc("hex.town", "Town");
		case EHexTerrain::Castle: return Loc("hex.castle", "Castle");
		case EHexTerrain::Rubble: return Loc("hex.rubble", "Rubble");
		case EHexTerrain::Count: break;
		}
		return std::string();
	}

	std::string DisplayName(ETactic Value)
	{
		switch (Value)
		{
		case ETactic::Fire: return Loc("tactic.fire", "Fire");
		case ETactic::Confuse: return Loc("tactic.confuse", "Confuse");
		case ETactic::Rally: return Loc("tactic.rally", "Rally");
		}
		return std::string();
	}

	// ---------------------------------------------------------------------------------------------
	// Hex math (flat-top, odd-q offset coordinates)
	// ---------------------------------------------------------------------------------------------

	namespace HexMath
	{
		int Distance(FHex A, FHex B)
		{
			const BattleDetail::FCube CubeA = BattleDetail::CubeOf(A);
			const BattleDetail::FCube CubeB = BattleDetail::CubeOf(B);
			const int DeltaX = CubeA.X - CubeB.X;
			const int DeltaZ = CubeA.Z - CubeB.Z;
			const int DeltaY = -DeltaX - DeltaZ;
			return (std::abs(DeltaX) + std::abs(DeltaY) + std::abs(DeltaZ)) / 2;
		}

		void Neighbors(FHex Center, FHex OutNeighbors[6])
		{
			// Cube (X, Z) directions: NE, SE, S, SW, NW, N.
			static const int Directions[6][2] = {{1, -1}, {1, 0}, {0, 1}, {-1, 1}, {-1, 0}, {0, -1}};
			const BattleDetail::FCube Cube = BattleDetail::CubeOf(Center);
			for (int Index = 0; Index < 6; ++Index)
			{
				OutNeighbors[Index] = BattleDetail::HexOfCube(Cube.X + Directions[Index][0], Cube.Z + Directions[Index][1]);
			}
		}

		void ToPixel(FHex Hex, float Size, float& OutX, float& OutY)
		{
			const double Radius = Size;
			OutX = static_cast<float>(Radius * (1.0 + 1.5 * Hex.Col));
			OutY = static_cast<float>(Radius * BattleDetail::SqrtThree * (0.5 + Hex.Row + 0.5 * (Hex.Col & 1)));
		}

		FHex FromPixel(float X, float Y, float Size)
		{
			if (Size <= 0.0f)
			{
				return FHex();
			}
			const double Radius = Size;
			const double LocalX = X - Radius;
			const double LocalY = Y - Radius * BattleDetail::SqrtThree * 0.5;
			const double AxialQ = (2.0 / 3.0 * LocalX) / Radius;
			const double AxialR = (-1.0 / 3.0 * LocalX + BattleDetail::SqrtThree / 3.0 * LocalY) / Radius;
			const double CubeX = AxialQ;
			const double CubeZ = AxialR;
			const double CubeY = -CubeX - CubeZ;
			double RoundX = std::round(CubeX);
			double RoundY = std::round(CubeY);
			double RoundZ = std::round(CubeZ);
			const double DiffX = std::abs(RoundX - CubeX);
			const double DiffY = std::abs(RoundY - CubeY);
			const double DiffZ = std::abs(RoundZ - CubeZ);
			if (DiffX > DiffY && DiffX > DiffZ)
			{
				RoundX = -RoundY - RoundZ;
			}
			else if (DiffY > DiffZ)
			{
				RoundY = -RoundX - RoundZ;
			}
			else
			{
				RoundZ = -RoundX - RoundY;
			}
			return BattleDetail::HexOfCube(static_cast<int>(RoundX), static_cast<int>(RoundZ));
		}

		void BoardSize(int Cols, int Rows, float Size, float& OutWidth, float& OutHeight)
		{
			if (Cols <= 0 || Rows <= 0)
			{
				OutWidth = 0.0f;
				OutHeight = 0.0f;
				return;
			}
			OutWidth = static_cast<float>(Size * (1.5 * Cols + 0.5));
			OutHeight = static_cast<float>(Size * BattleDetail::SqrtThree * (Rows + (Cols > 1 ? 0.5 : 0.0)));
		}
	}

	// ---------------------------------------------------------------------------------------------
	// Setup
	// ---------------------------------------------------------------------------------------------

	void FBattle::Setup(const FBattleSetup& InSetup)
	{
		Config = InSetup;
		if (Config.MaxDays <= 0)
		{
			Config.MaxDays = DaysPerMonth;
		}
		Config.CitySize = ClampInt(Config.CitySize, 1, 3);
		if (Config.Kind == EBattleKind::Siege)
		{
			if (Config.GateHp <= 0)
			{
				Config.GateHp = BattleDetail::DefaultGateHp;
			}
			if (Config.WallBonus <= 0)
			{
				Config.WallBonus = BattleDetail::DefaultWallBonus;
			}
		}

		Grid.clear();
		Burning.clear();
		Gate = {-1, -1};
		Castle = {-1, -1};
		GateHitPoints = 0;
		GateMaxHitPoints = 0;
		BattleUnits.clear();
		CurrentDay = 1;
		CurrentSide = 0;
		bAutoControl[0] = false;
		bAutoControl[1] = false;
		Outcome = FBattleResult();
		PendingChallenger = -1;
		PendingChallenged = -1;
		bDuelActive = false;
		Duel = FDuel();
		DuelUnits[0] = -1;
		DuelUnits[1] = -1;
		PendingEvents.clear();
		BattleLog.clear();
		WallCol = -1;
		SecondGate = {-1, -1};
		SecondGateHitPoints = 0;
		bAnyGateBroken = false;
		IssuedChallenges.clear();
		Rng = FRng(Config.Seed ^ 0xB7E151628AED2A6Bull);
		Rng.Next();

		GenerateMap();

		int GarrisonNumber = 0;
		for (int SideIndex = 0; SideIndex < 2; ++SideIndex)
		{
			const FBattleSideSetup& SideSetup = Config.Sides[SideIndex];
			for (size_t Index = 0; Index < SideSetup.Units.size(); ++Index)
			{
				FBattleUnit NewUnit;
				NewUnit.Id = static_cast<int>(BattleUnits.size());
				NewUnit.Side = SideIndex;
				NewUnit.bCommander = Index == 0;
				NewUnit.Setup = SideSetup.Units[Index];
				if (NewUnit.Setup.Name.empty())
				{
					++GarrisonNumber;
					NewUnit.Setup.Name = LocF("battle.unit.detachment", "Detachment {index}", {{"index", ToText(GarrisonNumber)}});
				}
				NewUnit.Troops = std::max(0, NewUnit.Setup.Troops);
				NewUnit.StartTroops = NewUnit.Troops;
				NewUnit.Morale = ClampInt(SideSetup.Morale, 0, 100);
				NewUnit.Pos = {-1, -1};
				NewUnit.TurnStart = NewUnit.Pos;
				if (NewUnit.Troops <= 0)
				{
					NewUnit.Status = EUnitStatus::Destroyed;
				}
				BattleUnits.push_back(NewUnit);
			}
		}
		DeployUnits();

		Emit(EBattleEventType::Message, -1, -1, FHex(), FHex(), 0, LocF("battle.log.begin", "The battle of {location} begins: {attacker} ({attackerTroops} troops) against {defender} ({defenderTroops} troops).", {{"location", BattleDetail::LocationOf(Config)}, {"attacker", SideName(0)}, {"attackerTroops", ToText(TotalTroops(0))}, {"defender", SideName(1)}, {"defenderTroops", ToText(TotalTroops(1))}}));
		Emit(EBattleEventType::DayStart, -1, -1, FHex(), FHex(), CurrentDay, LocF("battle.log.dayStart", "Day {day} begins.", {{"day", ToText(CurrentDay)}}));
		BeginSideTurn(0);
		CheckVictory();
	}

	// ---------------------------------------------------------------------------------------------
	// Board queries
	// ---------------------------------------------------------------------------------------------

	bool FBattle::IsValidUnit(int UnitId) const
	{
		return UnitId >= 0 && UnitId < static_cast<int>(BattleUnits.size());
	}

	int FBattle::HexIndex(FHex Hex) const
	{
		return Hex.Row * GridCols + Hex.Col;
	}

	bool FBattle::InBounds(FHex Hex) const
	{
		return Hex.Col >= 0 && Hex.Row >= 0 && Hex.Col < GridCols && Hex.Row < GridRows;
	}

	EHexTerrain FBattle::TerrainAt(FHex Hex) const
	{
		if (!InBounds(Hex) || static_cast<size_t>(HexIndex(Hex)) >= Grid.size())
		{
			return EHexTerrain::Mountain;
		}
		return Grid[static_cast<size_t>(HexIndex(Hex))];
	}

	int FBattle::BurningAt(FHex Hex) const
	{
		if (!InBounds(Hex) || static_cast<size_t>(HexIndex(Hex)) >= Burning.size())
		{
			return 0;
		}
		return Burning[static_cast<size_t>(HexIndex(Hex))];
	}

	int FBattle::GateCount() const
	{
		return (InBounds(Gate) ? 1 : 0) + (InBounds(SecondGate) ? 1 : 0);
	}

	FHex FBattle::GateHexAt(int Index) const
	{
		if (Index == 0 && InBounds(Gate))
		{
			return Gate;
		}
		if (Index == 1 && InBounds(SecondGate))
		{
			return SecondGate;
		}
		return {-1, -1};
	}

	int FBattle::GateHpAt(int Index) const
	{
		if (Index == 0 && InBounds(Gate))
		{
			return GateHitPoints;
		}
		if (Index == 1 && InBounds(SecondGate))
		{
			return SecondGateHitPoints;
		}
		return 0;
	}

	int FBattle::TerrainDefenseBonus(FHex Hex, int Side) const
	{
		if (!InBounds(Hex) || Grid.empty())
		{
			return 0;
		}
		const EHexTerrain Terrain = TerrainAt(Hex);
		int Bonus = 0;
		switch (Terrain)
		{
		case EHexTerrain::Forest: Bonus = 20; break;
		case EHexTerrain::Hill: Bonus = 25; break;
		case EHexTerrain::Ford: Bonus = -20; break;
		case EHexTerrain::Rubble: Bonus = 10; break;
		default: break;
		}
		if (Config.Kind == EBattleKind::Siege && Side == 1 && WallCol >= 0 && Hex.Col >= WallCol)
		{
			// Defenders inside the walls; half the bonus while holding the breach itself.
			Bonus += Hex.Col > WallCol ? Config.WallBonus : Config.WallBonus / 2;
			if (Terrain == EHexTerrain::Castle)
			{
				Bonus += 15;
			}
		}
		return Bonus;
	}

	int FBattle::TotalTroops(int Side) const
	{
		int Total = 0;
		for (const FBattleUnit& Each : BattleUnits)
		{
			if (Each.Side == Side && Each.IsActive())
			{
				Total += Each.Troops;
			}
		}
		return Total;
	}

	int FBattle::UnitAt(FHex Hex) const
	{
		for (const FBattleUnit& Each : BattleUnits)
		{
			if (Each.IsActive() && Each.Pos == Hex)
			{
				return Each.Id;
			}
		}
		return -1;
	}

	bool FBattle::IsSideAI(int Side) const
	{
		if (Side < 0 || Side > 1)
		{
			return false;
		}
		return !Config.Sides[Side].bPlayer || bAutoControl[Side];
	}

	bool FBattle::IsPlayerTurn() const
	{
		return !Outcome.bFinished && !HasPendingChallenge() && !bDuelActive && !IsSideAI(CurrentSide);
	}

	int FBattle::TerrainEnterCost(FHex Hex, ETroopType Type, int Side) const
	{
		if (!InBounds(Hex) || Grid.empty())
		{
			return -1;
		}
		switch (TerrainAt(Hex))
		{
		case EHexTerrain::Plain:
		case EHexTerrain::Road:
		case EHexTerrain::Town:
		case EHexTerrain::Bridge:
		case EHexTerrain::Castle:
			return 1;
		case EHexTerrain::Forest:
		case EHexTerrain::Hill:
		case EHexTerrain::Rubble:
			return Type == ETroopType::Cavalry ? 3 : 2;
		case EHexTerrain::Ford:
			return 3;
		case EHexTerrain::Gate:
			return Side == 1 ? 1 : -1;
		case EHexTerrain::Mountain:
		case EHexTerrain::Water:
		case EHexTerrain::Wall:
		case EHexTerrain::Count:
			return -1;
		}
		return -1;
	}

	int FBattle::EnterCost(FHex Hex, const FBattleUnit& Mover) const
	{
		if (BurningAt(Hex) > 0)
		{
			return -1;
		}
		return TerrainEnterCost(Hex, Mover.Setup.Type, Mover.Side);
	}

	bool FBattle::HasEnemyNeighbor(FHex Hex, int Side) const
	{
		for (const FBattleUnit& Each : BattleUnits)
		{
			if (Each.IsActive() && Each.Side != Side && HexMath::Distance(Each.Pos, Hex) == 1)
			{
				return true;
			}
		}
		return false;
	}

	int FBattle::MovePoints(int UnitId) const
	{
		if (!IsValidUnit(UnitId))
		{
			return 0;
		}
		switch (BattleUnits[static_cast<size_t>(UnitId)].Setup.Type)
		{
		case ETroopType::Infantry: return 4;
		case ETroopType::Cavalry: return 6;
		case ETroopType::Archer: return 3;
		}
		return 4;
	}

	std::vector<FReachableHex> FBattle::ComputeReach(int UnitId) const
	{
		std::vector<FReachableHex> Reach;
		if (!IsValidUnit(UnitId) || Grid.empty())
		{
			return Reach;
		}
		const FBattleUnit& Mover = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Mover.IsActive() || !InBounds(Mover.Pos))
		{
			return Reach;
		}
		const int Points = MovePoints(UnitId);
		const int CellCount = GridCols * GridRows;
		std::vector<int> Occupant(static_cast<size_t>(CellCount), -1);
		std::vector<uint8_t> Zoc(static_cast<size_t>(CellCount), 0);
		for (const FBattleUnit& Other : BattleUnits)
		{
			if (!Other.IsActive() || !InBounds(Other.Pos))
			{
				continue;
			}
			Occupant[static_cast<size_t>(HexIndex(Other.Pos))] = Other.Side;
			if (Other.Side != Mover.Side)
			{
				FHex Around[6];
				HexMath::Neighbors(Other.Pos, Around);
				for (const FHex& Near : Around)
				{
					if (InBounds(Near))
					{
						Zoc[static_cast<size_t>(HexIndex(Near))] = 1;
					}
				}
			}
		}

		// Bucket-queue Dijkstra: costs are small integers bounded by the movement points.
		const int Start = HexIndex(Mover.Pos);
		std::vector<int> Best(static_cast<size_t>(CellCount), std::numeric_limits<int>::max());
		std::vector<uint8_t> Done(static_cast<size_t>(CellCount), 0);
		std::vector<std::vector<int>> Buckets(static_cast<size_t>(Points + 1));
		Best[static_cast<size_t>(Start)] = 0;
		Buckets[0].push_back(Start);
		for (int Cost = 0; Cost <= Points; ++Cost)
		{
			for (size_t Index = 0; Index < Buckets[static_cast<size_t>(Cost)].size(); ++Index)
			{
				const int Cell = Buckets[static_cast<size_t>(Cost)][Index];
				if (Done[static_cast<size_t>(Cell)] || Best[static_cast<size_t>(Cell)] != Cost)
				{
					continue;
				}
				Done[static_cast<size_t>(Cell)] = 1;
				// Zone of control: entering a hex next to an enemy ends movement.
				if (Cell != Start && Zoc[static_cast<size_t>(Cell)])
				{
					continue;
				}
				const FHex Here = {Cell % GridCols, Cell / GridCols};
				FHex Around[6];
				HexMath::Neighbors(Here, Around);
				for (const FHex& Next : Around)
				{
					if (!InBounds(Next))
					{
						continue;
					}
					const int NextCell = HexIndex(Next);
					const int Holder = Occupant[static_cast<size_t>(NextCell)];
					if (Holder >= 0 && Holder != Mover.Side)
					{
						continue;
					}
					const int Step = EnterCost(Next, Mover);
					if (Step < 0)
					{
						continue;
					}
					const int Total = Cost + Step;
					if (Total <= Points && Total < Best[static_cast<size_t>(NextCell)])
					{
						Best[static_cast<size_t>(NextCell)] = Total;
						Buckets[static_cast<size_t>(Total)].push_back(NextCell);
					}
				}
			}
		}
		for (int Cell = 0; Cell < CellCount; ++Cell)
		{
			// Friendly units may be passed through but not stopped on; an intact gate cannot be held.
			if (!Done[static_cast<size_t>(Cell)] || Cell == Start || Occupant[static_cast<size_t>(Cell)] >= 0 || Grid[static_cast<size_t>(Cell)] == EHexTerrain::Gate)
			{
				continue;
			}
			FReachableHex Entry;
			Entry.Hex = {Cell % GridCols, Cell / GridCols};
			Entry.Cost = Best[static_cast<size_t>(Cell)];
			Reach.push_back(Entry);
		}
		return Reach;
	}

	bool FBattle::CanAct(int UnitId) const
	{
		if (!IsValidUnit(UnitId) || Outcome.bFinished || HasPendingChallenge() || bDuelActive)
		{
			return false;
		}
		const FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		return Actor.IsActive() && Actor.Side == CurrentSide && !Actor.bActed && Actor.ConfusedDays <= 0;
	}

	bool FBattle::CanMove(int UnitId) const
	{
		return CanAct(UnitId) && !BattleUnits[static_cast<size_t>(UnitId)].bMoved;
	}

	std::vector<FReachableHex> FBattle::Reachable(int UnitId) const
	{
		if (!IsValidUnit(UnitId) || Outcome.bFinished)
		{
			return std::vector<FReachableHex>();
		}
		// Units of the waiting side report their full range (threat display); active units their remaining move.
		if (BattleUnits[static_cast<size_t>(UnitId)].Side == CurrentSide && !CanMove(UnitId))
		{
			return std::vector<FReachableHex>();
		}
		return ComputeReach(UnitId);
	}

	std::vector<int> FBattle::AttackTargets(int UnitId) const
	{
		std::vector<int> Targets;
		if (!IsValidUnit(UnitId) || Outcome.bFinished)
		{
			return Targets;
		}
		const FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Attacker.IsActive() || !InBounds(Attacker.Pos) || (Attacker.Side == CurrentSide && !CanAct(UnitId)))
		{
			return Targets;
		}
		const int Range = Attacker.Setup.Type == ETroopType::Archer ? 2 : 1;
		for (const FBattleUnit& Other : BattleUnits)
		{
			if (Other.IsActive() && Other.Side != Attacker.Side)
			{
				const int Distance = HexMath::Distance(Attacker.Pos, Other.Pos);
				if (Distance >= 1 && Distance <= Range)
				{
					Targets.push_back(Other.Id);
				}
			}
		}
		return Targets;
	}

	int FBattle::AdjacentIntactGate(FHex Hex) const
	{
		int BestSlot = -1;
		for (int Slot = 0; Slot < 2; ++Slot)
		{
			const FHex GateAt = GateHexAt(Slot);
			if (!InBounds(GateAt) || TerrainAt(GateAt) != EHexTerrain::Gate || HexMath::Distance(GateAt, Hex) != 1)
			{
				continue;
			}
			if (BestSlot < 0 || GateHpAt(Slot) < GateHpAt(BestSlot))
			{
				BestSlot = Slot;
			}
		}
		return BestSlot;
	}

	bool FBattle::CanAttackGate(int UnitId) const
	{
		if (!CanAct(UnitId) || Config.Kind != EBattleKind::Siege)
		{
			return false;
		}
		const FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(UnitId)];
		return Attacker.Side == 0 && AdjacentIntactGate(Attacker.Pos) >= 0;
	}

	std::vector<int> FBattle::TacticTargets(int UnitId, ETactic Tactic) const
	{
		std::vector<int> Targets;
		if (!IsValidUnit(UnitId) || Outcome.bFinished)
		{
			return Targets;
		}
		const FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Actor.IsActive() || !InBounds(Actor.Pos) || (Actor.Side == CurrentSide && !CanAct(UnitId)))
		{
			return Targets;
		}
		for (const FBattleUnit& Other : BattleUnits)
		{
			if (!Other.IsActive())
			{
				continue;
			}
			const int Distance = HexMath::Distance(Actor.Pos, Other.Pos);
			if (Tactic == ETactic::Rally)
			{
				if (Other.Side == Actor.Side && Distance <= 1)
				{
					Targets.push_back(Other.Id);
				}
			}
			else if (Other.Side != Actor.Side && Distance >= 1 && Distance <= 2)
			{
				// Fire is useless against troops standing in water.
				if (Tactic == ETactic::Fire && TerrainAt(Other.Pos) == EHexTerrain::Ford)
				{
					continue;
				}
				Targets.push_back(Other.Id);
			}
		}
		return Targets;
	}

	int FBattle::TacticChance(int UnitId, ETactic Tactic, int TargetId) const
	{
		if (!IsValidUnit(UnitId) || !IsValidUnit(TargetId))
		{
			return 0;
		}
		const FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		const FBattleUnit& Subject = BattleUnits[static_cast<size_t>(TargetId)];
		const int Mine = BattleDetail::StatOf(Actor.Setup, EStat::Strategy);
		const int Theirs = BattleDetail::StatOf(Subject.Setup, EStat::Strategy);
		switch (Tactic)
		{
		case ETactic::Fire:
		{
			int Modifier = 0;
			switch (TerrainAt(Subject.Pos))
			{
			case EHexTerrain::Forest: Modifier = 15; break;
			case EHexTerrain::Town: Modifier = 5; break;
			case EHexTerrain::Bridge: Modifier = -10; break;
			case EHexTerrain::Ford: Modifier = -40; break;
			default: break;
			}
			return ClampInt(45 + (Mine - Theirs) + Modifier, 5, 95);
		}
		case ETactic::Confuse:
			return ClampInt(35 + (Mine - Theirs) * 6 / 5, 5, 95);
		case ETactic::Rally:
			return ClampInt(40 + (Mine + BattleDetail::StatOf(Actor.Setup, EStat::Command)) / 4, 10, 95);
		}
		return 0;
	}

	std::vector<int> FBattle::DuelTargets(int UnitId) const
	{
		std::vector<int> Targets;
		if (!IsValidUnit(UnitId) || Outcome.bFinished)
		{
			return Targets;
		}
		const FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Actor.IsActive() || Actor.Setup.Officer < 0 || (Actor.Side == CurrentSide && !CanAct(UnitId)))
		{
			return Targets;
		}
		for (const FBattleUnit& Other : BattleUnits)
		{
			const int Key = UnitId * BattleDetail::ChallengeKeyStride + Other.Id;
			if (Other.IsActive() && Other.Side != Actor.Side && Other.Setup.Officer >= 0 && HexMath::Distance(Actor.Pos, Other.Pos) == 1 && std::find(IssuedChallenges.begin(), IssuedChallenges.end(), Key) == IssuedChallenges.end())
			{
				Targets.push_back(Other.Id);
			}
		}
		return Targets;
	}

	double FBattle::DefenseMultiplier(FHex Hex, int Side) const
	{
		return 100.0 / (100.0 + std::max(-50, TerrainDefenseBonus(Hex, Side)));
	}

	double FBattle::RawDamage(int AttackerId, int AttackerTroops, int AttackerMorale, int TargetId, bool bRanged) const
	{
		if (!IsValidUnit(AttackerId) || !IsValidUnit(TargetId) || AttackerTroops <= 0)
		{
			return 0.0;
		}
		const FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(AttackerId)];
		const FBattleUnit& Defender = BattleUnits[static_cast<size_t>(TargetId)];
		const double Offense = BattleDetail::OffenseOf(Attacker.Setup, Config.Sides[Attacker.Side].Training);
		const double Defense = BattleDetail::DefenseOf(Defender.Setup, Config.Sides[Defender.Side].Training);
		const double Ratio = std::clamp(Offense / Defense, 0.25, 4.0);
		return 0.7 * std::sqrt(static_cast<double>(AttackerTroops)) * 10.0 * std::pow(Ratio, 0.7) * BattleDetail::TypeFactor(Attacker.Setup.Type, Defender.Setup.Type, bRanged) * BattleDetail::MoraleFactor(AttackerMorale);
	}

	double FBattle::ExpectedDamage(int AttackerId, int TargetId, FHex TargetPos, bool bRanged) const
	{
		if (!IsValidUnit(AttackerId) || !IsValidUnit(TargetId))
		{
			return 0.0;
		}
		const FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(AttackerId)];
		const FBattleUnit& Defender = BattleUnits[static_cast<size_t>(TargetId)];
		return RawDamage(AttackerId, Attacker.Troops, Attacker.Morale, TargetId, bRanged) * DefenseMultiplier(TargetPos, Defender.Side);
	}

	double FBattle::ExpectedGateDamage(int UnitId) const
	{
		if (!IsValidUnit(UnitId))
		{
			return 0.0;
		}
		const FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(UnitId)];
		double TypeMultiplier = 1.0;
		if (Attacker.Setup.Type == ETroopType::Cavalry)
		{
			TypeMultiplier = 0.6;
		}
		else if (Attacker.Setup.Type == ETroopType::Archer)
		{
			TypeMultiplier = 0.5;
		}
		const double Offense = BattleDetail::OffenseOf(Attacker.Setup, Config.Sides[Attacker.Side].Training);
		return 0.4 * std::sqrt(static_cast<double>(std::max(0, Attacker.Troops))) * 10.0 * TypeMultiplier * std::sqrt(std::max(0.25, Offense / 60.0)) * BattleDetail::MoraleFactor(Attacker.Morale);
	}

	double FBattle::ExpectedFireDamage(int UnitId, FHex TargetPos) const
	{
		if (!IsValidUnit(UnitId))
		{
			return 0.0;
		}
		const FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		double TerrainFactor = 1.0;
		switch (TerrainAt(TargetPos))
		{
		case EHexTerrain::Forest: TerrainFactor = 1.5; break;
		case EHexTerrain::Town: TerrainFactor = 1.2; break;
		case EHexTerrain::Bridge: TerrainFactor = 0.8; break;
		case EHexTerrain::Ford: TerrainFactor = 0.3; break;
		default: break;
		}
		// Stone walls blunt fire arrows: defenders inside the walls keep half their wall bonus against fire.
		const int TargetId = UnitAt(TargetPos);
		if (Config.Kind == EBattleKind::Siege && TargetId >= 0 && BattleUnits[static_cast<size_t>(TargetId)].Side == 1 && TargetPos.Col > WallCol)
		{
			TerrainFactor *= 100.0 / (100.0 + Config.WallBonus / 2.0);
		}
		const double Strategy = BattleDetail::StatOf(Actor.Setup, EStat::Strategy);
		return 0.35 * std::sqrt(static_cast<double>(std::max(0, Actor.Troops))) * 10.0 * (0.5 + Strategy / 100.0) * TerrainFactor;
	}

	int FBattle::RallyAmount(int UnitId) const
	{
		if (!IsValidUnit(UnitId))
		{
			return 0;
		}
		const FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		return 15 + (BattleDetail::StatOf(Actor.Setup, EStat::Command) + BattleDetail::StatOf(Actor.Setup, EStat::Strategy)) / 10;
	}

	int FBattle::AcceptChance(int ChallengerId, int TargetId) const
	{
		if (!IsValidUnit(ChallengerId) || !IsValidUnit(TargetId))
		{
			return 0;
		}
		const FBattleUnit& Challenger = BattleUnits[static_cast<size_t>(ChallengerId)];
		const FBattleUnit& Challenged = BattleUnits[static_cast<size_t>(TargetId)];
		const int Gap = BattleDetail::StatOf(Challenged.Setup, EStat::Martial) - BattleDetail::StatOf(Challenger.Setup, EStat::Martial);
		int Chance = 50 + Gap * 3 + (ClampInt(Challenged.Setup.Bravery, 0, 100) - 50) * 3 / 5;
		if (Challenged.bCommander)
		{
			Chance -= 15;
		}
		if (Gap >= 5)
		{
			Chance = std::max(Chance, 90);
		}
		return ClampInt(Chance, 5, 95);
	}

	int FBattle::PreviewDamage(int UnitId, int TargetId) const
	{
		if (!IsValidUnit(UnitId) || !IsValidUnit(TargetId))
		{
			return 0;
		}
		const FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(UnitId)];
		const FBattleUnit& Defender = BattleUnits[static_cast<size_t>(TargetId)];
		if (!Attacker.IsActive() || !Defender.IsActive())
		{
			return 0;
		}
		const bool bRanged = Attacker.Setup.Type == ETroopType::Archer && HexMath::Distance(Attacker.Pos, Defender.Pos) >= 2;
		const double Expected = ExpectedDamage(UnitId, TargetId, Defender.Pos, bRanged);
		return std::min(Defender.Troops, static_cast<int>(std::lround(Expected)));
	}

	// ---------------------------------------------------------------------------------------------
	// Damage, morale and falling units
	// ---------------------------------------------------------------------------------------------

	int FBattle::RollDamage(double Expected)
	{
		if (Expected <= 0.0)
		{
			return 0;
		}
		const double Factor = Rng.Uniform(0.85, 1.15);
		return std::max(1, static_cast<int>(std::lround(Expected * Factor)));
	}

	int FBattle::InflictLosses(int TargetId, int Damage, int SourceId, int MoraleBase)
	{
		FBattleUnit& Victim = BattleUnits[static_cast<size_t>(TargetId)];
		const int Before = Victim.Troops;
		const int Loss = ClampInt(Damage, 0, Before);
		Victim.Troops = Before - Loss;
		if (IsValidUnit(SourceId) && SourceId != TargetId)
		{
			BattleUnits[static_cast<size_t>(SourceId)].DamageDealt += Loss;
		}
		// Losing a tenth of the unit costs about 6 morale on top of the base shock.
		const int Shock = Before > 0 ? (60 * Loss + Before / 2) / Before : 0;
		Victim.Morale = ClampInt(Victim.Morale - MoraleBase - Shock, 0, 100);
		return Loss;
	}

	void FBattle::CheckFall(int UnitId, int ByUnit)
	{
		if (!IsValidUnit(UnitId))
		{
			return;
		}
		FBattleUnit& Candidate = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Candidate.IsActive())
		{
			return;
		}
		if (Candidate.Troops <= 0)
		{
			const bool bCaptured = Candidate.Setup.Officer >= 0 && IsValidUnit(ByUnit) && Rng.Chance(BattleDetail::WipeOutCaptureChance);
			UnitFalls(UnitId, ByUnit, bCaptured ? EUnitStatus::Captured : EUnitStatus::Destroyed);
		}
		else if (Candidate.Morale < BattleDetail::RoutMorale)
		{
			UnitFalls(UnitId, ByUnit, EUnitStatus::Routed);
		}
	}

	void FBattle::UnitFalls(int UnitId, int ByUnit, EUnitStatus NewStatus)
	{
		FBattleUnit& Fallen = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Fallen.IsActive() || NewStatus == EUnitStatus::Active)
		{
			return;
		}
		Fallen.Status = NewStatus;
		if (NewStatus == EUnitStatus::Captured || NewStatus == EUnitStatus::Killed)
		{
			// Leaderless troops scatter.
			Fallen.Troops = 0;
		}
		const std::string& Name = Fallen.Setup.Name;
		switch (NewStatus)
		{
		case EUnitStatus::Routed:
			Emit(EBattleEventType::Routed, UnitId, ByUnit, Fallen.Pos, Fallen.Pos, Fallen.Troops, LocF("battle.log.routed", "{unit}'s troops break and flee the field.", {{"unit", Name}}));
			break;
		case EUnitStatus::Destroyed:
			if (Fallen.Setup.Officer >= 0)
			{
				Emit(EBattleEventType::Destroyed, UnitId, ByUnit, Fallen.Pos, Fallen.Pos, 0, LocF("battle.log.destroyed", "{unit}'s unit is wiped out, but {unit} escapes.", {{"unit", Name}}));
			}
			else
			{
				Emit(EBattleEventType::Destroyed, UnitId, ByUnit, Fallen.Pos, Fallen.Pos, 0, LocF("battle.log.garrisonDestroyed", "{unit} is wiped out.", {{"unit", Name}}));
			}
			break;
		case EUnitStatus::Captured:
			Emit(EBattleEventType::Captured, UnitId, ByUnit, Fallen.Pos, Fallen.Pos, 0, LocF("battle.log.captured", "{unit} is taken prisoner.", {{"unit", Name}}));
			break;
		case EUnitStatus::Killed:
			Emit(EBattleEventType::Message, UnitId, ByUnit, Fallen.Pos, Fallen.Pos, 0, LocF("battle.log.killed", "{unit} is slain.", {{"unit", Name}}));
			break;
		case EUnitStatus::Active:
			break;
		}

		// The army feels it: allies waver, enemies take heart.
		const int Shock = Fallen.bCommander ? 10 : 4;
		const int FallenSide = Fallen.Side;
		for (FBattleUnit& Other : BattleUnits)
		{
			if (!Other.IsActive())
			{
				continue;
			}
			Other.Morale = ClampInt(Other.Morale + (Other.Side == FallenSide ? -Shock : 3), 0, 100);
		}
		for (size_t Index = 0; Index < BattleUnits.size(); ++Index)
		{
			if (BattleUnits[Index].Side == FallenSide)
			{
				CheckFall(static_cast<int>(Index), -1);
			}
		}
	}

	void FBattle::ShiftSideMorale(int Side, int Delta, int ExceptUnit)
	{
		for (FBattleUnit& Other : BattleUnits)
		{
			if (Other.IsActive() && Other.Side == Side && Other.Id != ExceptUnit)
			{
				Other.Morale = ClampInt(Other.Morale + Delta, 0, 100);
			}
		}
		if (Delta < 0)
		{
			for (size_t Index = 0; Index < BattleUnits.size(); ++Index)
			{
				if (BattleUnits[Index].Side == Side)
				{
					CheckFall(static_cast<int>(Index), -1);
				}
			}
		}
	}

	// ---------------------------------------------------------------------------------------------
	// Events and log
	// ---------------------------------------------------------------------------------------------

	void FBattle::Emit(EBattleEventType Type, int UnitId, int TargetId, FHex From, FHex To, int Value, const std::string& Text)
	{
		FBattleEvent Event;
		Event.Type = Type;
		Event.Unit = UnitId;
		Event.Target = TargetId;
		Event.From = From;
		Event.To = To;
		Event.Value = Value;
		Event.Text = Text;
		PendingEvents.push_back(Event);
		if (!Text.empty())
		{
			AddLog(Text);
		}
	}

	void FBattle::AddLog(const std::string& Text)
	{
		BattleLog.push_back(LocF("battle.log.line", "Day {day}: {text}", {{"day", ToText(CurrentDay)}, {"text", Text}}));
	}

	std::string FBattle::SideName(int Side) const
	{
		const int Index = Side == 0 ? 0 : 1;
		if (!Config.Sides[Index].Name.empty())
		{
			return Config.Sides[Index].Name;
		}
		return Index == 0 ? Loc("battle.side.attackers", "The attackers") : Loc("battle.side.defenders", "The defenders");
	}

	// ---------------------------------------------------------------------------------------------
	// Actions
	// ---------------------------------------------------------------------------------------------

	bool FBattle::Move(int UnitId, FHex Destination)
	{
		if (!CanMove(UnitId))
		{
			return false;
		}
		int Cost = -1;
		for (const FReachableHex& Entry : ComputeReach(UnitId))
		{
			if (Entry.Hex == Destination)
			{
				Cost = Entry.Cost;
				break;
			}
		}
		if (Cost < 0)
		{
			return false;
		}
		FBattleUnit& Mover = BattleUnits[static_cast<size_t>(UnitId)];
		const FHex From = Mover.Pos;
		Mover.Pos = Destination;
		Mover.bMoved = true;
		Emit(EBattleEventType::Move, UnitId, -1, From, Destination, Cost, std::string());
		CheckVictory();
		return true;
	}

	bool FBattle::UndoMove(int UnitId)
	{
		if (!CanAct(UnitId))
		{
			return false;
		}
		FBattleUnit& Mover = BattleUnits[static_cast<size_t>(UnitId)];
		if (!Mover.bMoved)
		{
			return false;
		}
		const int Holder = UnitAt(Mover.TurnStart);
		if (Holder >= 0 && Holder != UnitId)
		{
			return false;
		}
		const FHex From = Mover.Pos;
		Mover.Pos = Mover.TurnStart;
		Mover.bMoved = false;
		Emit(EBattleEventType::Move, UnitId, -1, From, Mover.Pos, 0, std::string());
		return true;
	}

	bool FBattle::Attack(int UnitId, int TargetId)
	{
		if (!CanAct(UnitId) || !IsValidUnit(TargetId))
		{
			return false;
		}
		const std::vector<int> Targets = AttackTargets(UnitId);
		if (std::find(Targets.begin(), Targets.end(), TargetId) == Targets.end())
		{
			return false;
		}
		FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(UnitId)];
		FBattleUnit& Defender = BattleUnits[static_cast<size_t>(TargetId)];
		const bool bRanged = HexMath::Distance(Attacker.Pos, Defender.Pos) >= 2;
		Attacker.bMoved = true;
		Attacker.bActed = true;

		const int Damage = RollDamage(ExpectedDamage(UnitId, TargetId, Defender.Pos, bRanged));
		const int Loss = InflictLosses(TargetId, Damage, UnitId, 3);
		if (bRanged)
		{
			Emit(EBattleEventType::Attack, UnitId, TargetId, Attacker.Pos, Defender.Pos, Loss, LocF("battle.log.volley", "{unit} looses a volley at {target}: {damage} casualties ({troops} left).", {{"unit", Attacker.Setup.Name}, {"target", Defender.Setup.Name}, {"damage", ToText(Loss)}, {"troops", ToText(Defender.Troops)}}));
		}
		else
		{
			Emit(EBattleEventType::Attack, UnitId, TargetId, Attacker.Pos, Defender.Pos, Loss, LocF("battle.log.attack", "{unit} attacks {target}: {damage} casualties ({troops} left).", {{"unit", Attacker.Setup.Name}, {"target", Defender.Setup.Name}, {"damage", ToText(Loss)}, {"troops", ToText(Defender.Troops)}}));
		}

		// Melee defenders that still stand strike back at half strength; ranged attacks are not countered.
		int CounterLoss = 0;
		if (!bRanged && Defender.Troops > 0 && Defender.Morale >= BattleDetail::RoutMorale)
		{
			const int CounterDamage = RollDamage(0.5 * ExpectedDamage(TargetId, UnitId, Attacker.Pos, false));
			CounterLoss = InflictLosses(UnitId, CounterDamage, TargetId, 1);
			Emit(EBattleEventType::Counter, TargetId, UnitId, Defender.Pos, Attacker.Pos, CounterLoss, LocF("battle.log.counter", "{unit} strikes back at {target}: {damage} casualties ({troops} left).", {{"unit", Defender.Setup.Name}, {"target", Attacker.Setup.Name}, {"damage", ToText(CounterLoss)}, {"troops", ToText(Attacker.Troops)}}));
		}
		if (Loss > CounterLoss)
		{
			Attacker.Morale = ClampInt(Attacker.Morale + 2, 0, 100);
		}
		CheckFall(TargetId, UnitId);
		CheckFall(UnitId, TargetId);
		CheckVictory();
		return true;
	}

	bool FBattle::AttackGate(int UnitId)
	{
		if (!CanAttackGate(UnitId))
		{
			return false;
		}
		FBattleUnit& Attacker = BattleUnits[static_cast<size_t>(UnitId)];
		const int Slot = AdjacentIntactGate(Attacker.Pos);
		const FHex GateAt = GateHexAt(Slot);
		Attacker.bMoved = true;
		Attacker.bActed = true;
		const int Damage = RollDamage(ExpectedGateDamage(UnitId));
		int& Remaining = Slot == 0 ? GateHitPoints : SecondGateHitPoints;
		Remaining = std::max(0, Remaining - Damage);
		Emit(EBattleEventType::GateHit, UnitId, -1, Attacker.Pos, GateAt, Damage, LocF("battle.log.gateHit", "{unit} batters the gate: {damage} damage ({hp} left).", {{"unit", Attacker.Setup.Name}, {"damage", ToText(Damage)}, {"hp", ToText(Remaining)}}));
		if (Remaining <= 0)
		{
			Grid[static_cast<size_t>(HexIndex(GateAt))] = EHexTerrain::Rubble;
			bAnyGateBroken = true;
			Emit(EBattleEventType::GateBroken, UnitId, -1, Attacker.Pos, GateAt, 0, LocF("battle.log.gateBroken", "The gate gives way under {unit}'s assault!", {{"unit", Attacker.Setup.Name}}));
			ShiftSideMorale(0, 5, -1);
			ShiftSideMorale(1, -10, -1);
		}
		CheckVictory();
		return true;
	}

	bool FBattle::UseTactic(int UnitId, ETactic Tactic, int TargetId)
	{
		if (!CanAct(UnitId) || !IsValidUnit(TargetId))
		{
			return false;
		}
		const std::vector<int> Targets = TacticTargets(UnitId, Tactic);
		if (std::find(Targets.begin(), Targets.end(), TargetId) == Targets.end())
		{
			return false;
		}
		FBattleUnit& Actor = BattleUnits[static_cast<size_t>(UnitId)];
		FBattleUnit& Subject = BattleUnits[static_cast<size_t>(TargetId)];
		Actor.bMoved = true;
		Actor.bActed = true;
		const int Chance = TacticChance(UnitId, Tactic, TargetId);
		if (!Rng.Chance(Chance))
		{
			Emit(EBattleEventType::TacticFailed, UnitId, TargetId, Actor.Pos, Subject.Pos, Chance, LocF("battle.log.tacticFailed", "{unit} attempts {tactic} on {target}, but it fails.", {{"unit", Actor.Setup.Name}, {"tactic", DisplayName(Tactic)}, {"target", Subject.Setup.Name}}));
			PendingEvents.back().Tactic = static_cast<int>(Tactic);
			return true;
		}
		++Actor.TacticsSucceeded;
		switch (Tactic)
		{
		case ETactic::Fire:
		{
			const FHex Spot = Subject.Pos;
			const int Damage = RollDamage(ExpectedFireDamage(UnitId, Spot));
			const int Loss = InflictLosses(TargetId, Damage, UnitId, 10);
			Burning[static_cast<size_t>(HexIndex(Spot))] = std::max(Burning[static_cast<size_t>(HexIndex(Spot))], 2);
			FHex Around[6];
			HexMath::Neighbors(Spot, Around);
			for (const FHex& Near : Around)
			{
				// Flames spread through the woods.
				if (InBounds(Near) && TerrainAt(Near) == EHexTerrain::Forest && Rng.Chance(50))
				{
					Burning[static_cast<size_t>(HexIndex(Near))] = std::max(Burning[static_cast<size_t>(HexIndex(Near))], 1);
				}
			}
			Emit(EBattleEventType::Tactic, UnitId, TargetId, Actor.Pos, Spot, Loss, LocF("battle.log.fire", "{unit} sets fire to {target}'s position: {damage} casualties.", {{"unit", Actor.Setup.Name}, {"target", Subject.Setup.Name}, {"damage", ToText(Loss)}}));
			PendingEvents.back().Tactic = static_cast<int>(Tactic);
			CheckFall(TargetId, UnitId);
			break;
		}
		case ETactic::Confuse:
			Subject.ConfusedDays = std::max(Subject.ConfusedDays, 1);
			Emit(EBattleEventType::Tactic, UnitId, TargetId, Actor.Pos, Subject.Pos, 1, LocF("battle.log.confuse", "{unit} throws {target} into confusion; it will lose its next turn.", {{"unit", Actor.Setup.Name}, {"target", Subject.Setup.Name}}));
			PendingEvents.back().Tactic = static_cast<int>(Tactic);
			break;
		case ETactic::Rally:
		{
			const int Gain = ClampInt(RallyAmount(UnitId), 0, 100 - Subject.Morale);
			Subject.Morale += Gain;
			Subject.ConfusedDays = 0;
			if (TargetId == UnitId)
			{
				Emit(EBattleEventType::Tactic, UnitId, TargetId, Actor.Pos, Subject.Pos, Gain, LocF("battle.log.rallySelf", "{unit} rallies the troops: morale +{amount}.", {{"unit", Actor.Setup.Name}, {"amount", ToText(Gain)}}));
			}
			else
			{
				Emit(EBattleEventType::Tactic, UnitId, TargetId, Actor.Pos, Subject.Pos, Gain, LocF("battle.log.rally", "{unit} rallies {target}: morale +{amount}.", {{"unit", Actor.Setup.Name}, {"target", Subject.Setup.Name}, {"amount", ToText(Gain)}}));
			}
			PendingEvents.back().Tactic = static_cast<int>(Tactic);
			break;
		}
		}
		CheckVictory();
		return true;
	}

	bool FBattle::Wait(int UnitId)
	{
		if (!CanAct(UnitId))
		{
			return false;
		}
		FBattleUnit& Waiter = BattleUnits[static_cast<size_t>(UnitId)];
		Waiter.bMoved = true;
		Waiter.bActed = true;
		return true;
	}

	bool FBattle::ChallengeDuel(int UnitId, int TargetId)
	{
		if (!CanAct(UnitId) || !IsValidUnit(TargetId))
		{
			return false;
		}
		const std::vector<int> Targets = DuelTargets(UnitId);
		if (std::find(Targets.begin(), Targets.end(), TargetId) == Targets.end())
		{
			return false;
		}
		FBattleUnit& Challenger = BattleUnits[static_cast<size_t>(UnitId)];
		const FBattleUnit& Challenged = BattleUnits[static_cast<size_t>(TargetId)];
		Challenger.bMoved = true;
		Challenger.bActed = true;
		IssuedChallenges.push_back(UnitId * BattleDetail::ChallengeKeyStride + TargetId);
		const int Chance = AcceptChance(UnitId, TargetId);
		Emit(EBattleEventType::DuelChallenge, UnitId, TargetId, Challenger.Pos, Challenged.Pos, Chance, LocF("battle.log.challenge", "{unit} challenges {target} to a duel!", {{"unit", Challenger.Setup.Name}, {"target", Challenged.Setup.Name}}));
		if (IsSideAI(Challenged.Side))
		{
			if (Rng.Chance(Chance))
			{
				StartDuel(UnitId, TargetId);
			}
			else
			{
				DeclineChallenge(UnitId, TargetId);
			}
		}
		else
		{
			PendingChallenger = UnitId;
			PendingChallenged = TargetId;
		}
		return true;
	}

	void FBattle::AnswerChallenge(bool bAccept)
	{
		if (!HasPendingChallenge() || Outcome.bFinished)
		{
			return;
		}
		const int ChallengerId = PendingChallenger;
		const int ChallengedId = PendingChallenged;
		PendingChallenger = -1;
		PendingChallenged = -1;
		if (bAccept)
		{
			StartDuel(ChallengerId, ChallengedId);
		}
		else
		{
			DeclineChallenge(ChallengerId, ChallengedId);
		}
	}

	void FBattle::StartDuel(int ChallengerId, int ChallengedId)
	{
		const int Ids[2] = {ChallengerId, ChallengedId};
		Emit(EBattleEventType::Message, ChallengedId, ChallengerId, BattleUnits[static_cast<size_t>(ChallengedId)].Pos, BattleUnits[static_cast<size_t>(ChallengerId)].Pos, 0, LocF("battle.log.challengeAccepted", "{target} accepts the challenge of {unit}.", {{"unit", BattleUnits[static_cast<size_t>(ChallengerId)].Setup.Name}, {"target", BattleUnits[static_cast<size_t>(ChallengedId)].Setup.Name}}));
		FDuelist Fighters[2];
		for (int Index = 0; Index < 2; ++Index)
		{
			const FBattleUnit& Fighter = BattleUnits[static_cast<size_t>(Ids[Index])];
			Fighters[Index].Officer = Fighter.Setup.Officer;
			Fighters[Index].Name = Fighter.Setup.Name;
			Fighters[Index].Portrait = Fighter.Setup.Portrait;
			Fighters[Index].Martial = BattleDetail::StatOf(Fighter.Setup, EStat::Martial);
			Fighters[Index].Bravery = Fighter.Setup.Bravery;
			Fighters[Index].Techniques = Fighter.Setup.Techniques;
			Fighters[Index].bPlayer = !IsSideAI(Fighter.Side);
		}
		const uint64_t High = Rng.Next();
		const uint64_t Low = Rng.Next();
		Duel.Setup(Fighters[0], Fighters[1], Config.Techniques, (High << 32) | Low, 10);
		DuelUnits[0] = ChallengerId;
		DuelUnits[1] = ChallengedId;
		bDuelActive = true;
		if (!Fighters[0].bPlayer && !Fighters[1].bPlayer)
		{
			Duel.AutoPlay();
			FinishDuel();
		}
	}

	void FBattle::DeclineChallenge(int ChallengerId, int ChallengedId)
	{
		FBattleUnit& Challenger = BattleUnits[static_cast<size_t>(ChallengerId)];
		FBattleUnit& Challenged = BattleUnits[static_cast<size_t>(ChallengedId)];
		const int Penalty = 10;
		Challenged.Morale = ClampInt(Challenged.Morale - Penalty, 0, 100);
		Challenger.Morale = ClampInt(Challenger.Morale + 5, 0, 100);
		Emit(EBattleEventType::DuelDeclined, ChallengerId, ChallengedId, Challenger.Pos, Challenged.Pos, Penalty, LocF("battle.log.challengeDeclined", "{target} refuses to face {unit}; the troops lose heart.", {{"unit", Challenger.Setup.Name}, {"target", Challenged.Setup.Name}}));
		ShiftSideMorale(Challenged.Side, -2, ChallengedId);
		CheckFall(ChallengedId, -1);
		CheckVictory();
	}

	void FBattle::FinishDuel()
	{
		if (!bDuelActive || !Duel.IsOver())
		{
			return;
		}
		bDuelActive = false;
		const int ChallengerId = DuelUnits[0];
		const int ChallengedId = DuelUnits[1];
		const FHex ChallengerPos = BattleUnits[static_cast<size_t>(ChallengerId)].Pos;
		const FHex ChallengedPos = BattleUnits[static_cast<size_t>(ChallengedId)].Pos;
		const int WinningSide = Duel.Winner();
		if (WinningSide < 0)
		{
			Emit(EBattleEventType::DuelResult, ChallengerId, ChallengedId, ChallengerPos, ChallengedPos, -1, LocF("battle.log.duelDraw", "{a} and {b} fight to a standstill.", {{"a", BattleUnits[static_cast<size_t>(ChallengerId)].Setup.Name}, {"b", BattleUnits[static_cast<size_t>(ChallengedId)].Setup.Name}}));
			CheckVictory();
			return;
		}
		const int WinnerId = DuelUnits[WinningSide];
		const int LoserId = DuelUnits[1 - WinningSide];
		FBattleUnit& Victor = BattleUnits[static_cast<size_t>(WinnerId)];
		FBattleUnit& Loser = BattleUnits[static_cast<size_t>(LoserId)];
		++Victor.DuelsWon;
		Victor.Morale = ClampInt(Victor.Morale + 15, 0, 100);
		const int Lost = Loser.Troops * 30 / 100;
		Loser.Troops -= Lost;
		Victor.DamageDealt += Lost;
		Loser.Morale = ClampInt(Loser.Morale - 30, 0, 100);
		Emit(EBattleEventType::DuelResult, ChallengerId, ChallengedId, ChallengerPos, ChallengedPos, WinnerId, LocF("battle.log.duelWon", "{winner} defeats {loser} in single combat! {loser}'s unit loses {troops} troops.", {{"winner", Victor.Setup.Name}, {"loser", Loser.Setup.Name}, {"troops", ToText(Lost)}}));
		ShiftSideMorale(Victor.Side, 5, WinnerId);
		ShiftSideMorale(Loser.Side, -5, LoserId);
		const int Fate = Rng.Range(0, 99);
		if (Loser.IsActive() && Loser.Setup.Officer >= 0 && Fate < BattleDetail::DuelKillChance)
		{
			UnitFalls(LoserId, WinnerId, EUnitStatus::Killed);
		}
		else if (Loser.IsActive() && Loser.Setup.Officer >= 0 && Fate < BattleDetail::DuelKillChance + BattleDetail::DuelCaptureChance)
		{
			UnitFalls(LoserId, WinnerId, EUnitStatus::Captured);
		}
		else
		{
			CheckFall(LoserId, WinnerId);
		}
		CheckVictory();
	}

	// ---------------------------------------------------------------------------------------------
	// Turn flow
	// ---------------------------------------------------------------------------------------------

	void FBattle::SetAutoControl(int Side, bool bAuto)
	{
		if (Side == 0 || Side == 1)
		{
			bAutoControl[Side] = bAuto;
		}
	}

	void FBattle::ResolveInterruptions()
	{
		if (HasPendingChallenge())
		{
			AnswerChallenge(Rng.Chance(AcceptChance(PendingChallenger, PendingChallenged)));
		}
		if (bDuelActive)
		{
			Duel.AutoPlay();
			FinishDuel();
		}
	}

	void FBattle::EndTurn()
	{
		if (Outcome.bFinished)
		{
			return;
		}
		ResolveInterruptions();
		if (Outcome.bFinished)
		{
			return;
		}
		// Confusion lasts until the end of the confused side's next turn.
		for (FBattleUnit& Each : BattleUnits)
		{
			if (Each.Side == CurrentSide && Each.ConfusedDays > 0)
			{
				--Each.ConfusedDays;
			}
		}
		if (CurrentSide == 0)
		{
			CurrentSide = 1;
			BeginSideTurn(1);
			return;
		}
		if (CurrentDay >= Config.MaxDays)
		{
			EndBattle(1, LocF("battle.summary.dayLimit", "{winner} held {location} until day {day}; the assault has failed.", {{"winner", SideName(1)}, {"location", BattleDetail::LocationOf(Config)}, {"day", ToText(CurrentDay)}}));
			return;
		}
		++CurrentDay;
		CurrentSide = 0;
		BeginDay();
		if (!Outcome.bFinished)
		{
			BeginSideTurn(0);
		}
	}

	void FBattle::BeginSideTurn(int Side)
	{
		for (FBattleUnit& Each : BattleUnits)
		{
			if (Each.Side == Side)
			{
				Each.bMoved = false;
				Each.bActed = false;
				Each.TurnStart = Each.Pos;
			}
		}
	}

	void FBattle::BeginDay()
	{
		Emit(EBattleEventType::DayStart, -1, -1, FHex(), FHex(), CurrentDay, LocF("battle.log.dayStart", "Day {day} begins.", {{"day", ToText(CurrentDay)}}));

		// Fires burn whoever stands in them, then die down.
		for (size_t Cell = 0; Cell < Burning.size(); ++Cell)
		{
			if (Burning[Cell] <= 0)
			{
				continue;
			}
			const FHex Spot = {static_cast<int>(Cell) % GridCols, static_cast<int>(Cell) / GridCols};
			const int Victim = UnitAt(Spot);
			if (Victim >= 0)
			{
				const FBattleUnit& Burned = BattleUnits[static_cast<size_t>(Victim)];
				int Damage = std::max(30, Burned.Troops * 6 / 100);
				if (Grid[Cell] == EHexTerrain::Forest)
				{
					Damage = Damage * 13 / 10;
				}
				const int Loss = InflictLosses(Victim, Damage, -1, 5);
				Emit(EBattleEventType::Burn, Victim, -1, Spot, Spot, Loss, LocF("battle.log.burn", "Flames engulf {unit}: {damage} casualties.", {{"unit", Burned.Setup.Name}, {"damage", ToText(Loss)}}));
				CheckFall(Victim, -1);
			}
			--Burning[Cell];
		}
		CheckVictory();
		if (Outcome.bFinished)
		{
			return;
		}

		// Supplies: a side whose food runs out withdraws (the attacker is checked first).
		for (int SideIndex = 0; SideIndex < 2; ++SideIndex)
		{
			const int FoodDays = Config.Sides[SideIndex].FoodDays;
			if (CurrentDay > FoodDays)
			{
				EndBattle(1 - SideIndex, LocF("battle.summary.food", "{loser} ran out of food at {location} on day {day} and withdrew; {winner} holds the field.", {{"loser", SideName(SideIndex)}, {"winner", SideName(1 - SideIndex)}, {"location", BattleDetail::LocationOf(Config)}, {"day", ToText(CurrentDay)}}));
				return;
			}
			if (FoodDays - CurrentDay < 2)
			{
				Emit(EBattleEventType::Message, -1, -1, FHex(), FHex(), SideIndex, LocF("battle.log.suppliesLow", "{side} is running short of food.", {{"side", SideName(SideIndex)}}));
				ShiftSideMorale(SideIndex, -5, -1);
			}
		}
		CheckVictory();
	}

	void FBattle::CheckVictory()
	{
		if (Outcome.bFinished)
		{
			return;
		}
		if (Config.Kind == EBattleKind::Siege && InBounds(Castle))
		{
			const int Holder = UnitAt(Castle);
			if (Holder >= 0 && BattleUnits[static_cast<size_t>(Holder)].Side == 0)
			{
				EndBattle(0, LocF("battle.summary.castle", "{winner} stormed the castle of {location} on day {day}.", {{"winner", SideName(0)}, {"location", BattleDetail::LocationOf(Config)}, {"day", ToText(CurrentDay)}}));
				return;
			}
		}
		// Side 0 first: if both sides collapse at once the defender keeps the field.
		for (int SideIndex = 0; SideIndex < 2; ++SideIndex)
		{
			bool bAnyActive = false;
			const FBattleUnit* Commander = nullptr;
			for (const FBattleUnit& Each : BattleUnits)
			{
				if (Each.Side != SideIndex)
				{
					continue;
				}
				bAnyActive = bAnyActive || Each.IsActive();
				if (Each.bCommander)
				{
					Commander = &Each;
				}
			}
			if (!bAnyActive)
			{
				EndBattle(1 - SideIndex, LocF("battle.summary.wipedOut", "{winner} won at {location} on day {day}: {loser} has no troops left on the field.", {{"winner", SideName(1 - SideIndex)}, {"loser", SideName(SideIndex)}, {"location", BattleDetail::LocationOf(Config)}, {"day", ToText(CurrentDay)}}));
				return;
			}
			if (Commander && !Commander->IsActive())
			{
				EndBattle(1 - SideIndex, LocF("battle.summary.commanderFell", "{winner} won at {location} on day {day}: {loser}'s commander {commander} has fallen.", {{"winner", SideName(1 - SideIndex)}, {"loser", SideName(SideIndex)}, {"commander", Commander->Setup.Name}, {"location", BattleDetail::LocationOf(Config)}, {"day", ToText(CurrentDay)}}));
				return;
			}
		}
	}

	void FBattle::EndBattle(int Winner, const std::string& Reason)
	{
		if (Outcome.bFinished)
		{
			return;
		}
		Outcome.bFinished = true;
		Outcome.Winner = Winner == 0 ? 0 : 1;
		Outcome.Days = ClampInt(CurrentDay, 1, Config.MaxDays);
		Outcome.bGateBroken = bAnyGateBroken;
		Outcome.Units.clear();
		for (const FBattleUnit& Each : BattleUnits)
		{
			FUnitOutcome Entry;
			Entry.Side = Each.Side;
			Entry.Officer = Each.Setup.Officer;
			Entry.Troops = (Each.Status == EUnitStatus::Active || Each.Status == EUnitStatus::Routed) ? Each.Troops : 0;
			Entry.Status = Each.Status;
			Entry.DamageDealt = Each.DamageDealt;
			Entry.TacticsSucceeded = Each.TacticsSucceeded;
			Entry.DuelsWon = Each.DuelsWon;
			Outcome.Units.push_back(Entry);
		}
		Outcome.Summary = Reason;
		PendingChallenger = -1;
		PendingChallenged = -1;
		bDuelActive = false;
		Emit(EBattleEventType::Victory, -1, -1, FHex(), FHex(), Outcome.Winner, Reason);
	}

	// ---------------------------------------------------------------------------------------------
	// Test hooks
	// ---------------------------------------------------------------------------------------------

	void FBattle::DebugSetTerrain(FHex Hex, EHexTerrain Terrain)
	{
		if (InBounds(Hex) && static_cast<size_t>(HexIndex(Hex)) < Grid.size())
		{
			Grid[static_cast<size_t>(HexIndex(Hex))] = Terrain;
		}
	}

	bool FBattle::DebugPlaceUnit(int UnitId, FHex Hex)
	{
		if (!IsValidUnit(UnitId) || !InBounds(Hex))
		{
			return false;
		}
		const int Holder = UnitAt(Hex);
		if (Holder >= 0 && Holder != UnitId)
		{
			return false;
		}
		FBattleUnit& Placed = BattleUnits[static_cast<size_t>(UnitId)];
		Placed.Pos = Hex;
		Placed.TurnStart = Hex;
		return true;
	}

	void FBattle::DebugSetUnit(int UnitId, int Troops, int Morale)
	{
		if (!IsValidUnit(UnitId))
		{
			return;
		}
		FBattleUnit& Edited = BattleUnits[static_cast<size_t>(UnitId)];
		Edited.Troops = std::max(0, Troops);
		Edited.Morale = ClampInt(Morale, 0, 100);
	}

	FBattleResult ResolveBattleAuto(const FBattleSetup& Setup)
	{
		FBattle Battle;
		Battle.Setup(Setup);
		Battle.AutoResolve();
		return Battle.Result();
	}
}
