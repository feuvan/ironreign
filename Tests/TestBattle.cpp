#include "IronTest.h"

#include "Sim/IronBattle.h"

#include <algorithm>
#include <cmath>
#include <string>
#include <vector>

using IronSim::EBattleEventType;
using IronSim::EBattleKind;
using IronSim::EDuelMove;
using IronSim::EHexTerrain;
using IronSim::ETactic;
using IronSim::ETerrain;
using IronSim::ETroopType;
using IronSim::EUnitStatus;
using IronSim::FBattle;
using IronSim::FBattleEvent;
using IronSim::FBattleResult;
using IronSim::FBattleSetup;
using IronSim::FBattleUnit;
using IronSim::FBattleUnitSetup;
using IronSim::FHex;
using IronSim::FReachableHex;
using IronSim::FTechnique;
namespace HexMath = IronSim::HexMath;

namespace BattleTestUtil
{
	const ETerrain AllTerrains[] = {ETerrain::Plains, ETerrain::Forest, ETerrain::Hills, ETerrain::River, ETerrain::Mountains, ETerrain::Coast};

	FBattleUnitSetup MakeUnit(const std::string& Name, int Officer, int Martial, int Command, int Strategy, int Troops, ETroopType Type)
	{
		FBattleUnitSetup Unit;
		Unit.Officer = Officer;
		Unit.Name = Name;
		Unit.Stats[0] = Martial;
		Unit.Stats[1] = Command;
		Unit.Stats[2] = Strategy;
		Unit.Troops = Troops;
		Unit.Type = Type;
		return Unit;
	}

	/** Two AI armies of UnitsPerSide units (infantry, cavalry, archers, infantry, archers...) with all stats 60. */
	FBattleSetup MakeArmies(EBattleKind Kind, ETerrain Terrain, uint64_t Seed, int AttackTroops, int DefendTroops, int UnitsPerSide = 5, int CitySize = 2)
	{
		const ETroopType Types[5] = {ETroopType::Infantry, ETroopType::Cavalry, ETroopType::Archer, ETroopType::Infantry, ETroopType::Archer};
		FBattleSetup Setup;
		Setup.Kind = Kind;
		Setup.Terrain = Terrain;
		Setup.Seed = Seed;
		Setup.Location = "Test Field";
		Setup.CitySize = CitySize;
		Setup.GateHp = 1200;
		Setup.WallBonus = 30;
		Setup.Sides[0].Name = "Red";
		Setup.Sides[1].Name = "Blue";
		for (int Side = 0; Side < 2; ++Side)
		{
			const int Total = Side == 0 ? AttackTroops : DefendTroops;
			for (int Index = 0; Index < UnitsPerSide; ++Index)
			{
				const std::string Name = std::string(Side == 0 ? "Red " : "Blue ") + std::to_string(Index + 1);
				Setup.Sides[Side].Units.push_back(MakeUnit(Name, Side * 10 + Index, 60, 60, 60, Total / UnitsPerSide, Types[Index % 5]));
			}
		}
		return Setup;
	}

	/** One unit per side, both sides player-controlled so nothing moves on its own. */
	FBattleSetup MakeDuo(ETroopType AttackerType, ETroopType DefenderType, int AttackerTroops = 5000, int DefenderTroops = 5000)
	{
		FBattleSetup Setup;
		Setup.Kind = EBattleKind::Field;
		Setup.Terrain = ETerrain::Plains;
		Setup.Seed = 99;
		Setup.Location = "Test Field";
		Setup.Sides[0].bPlayer = true;
		Setup.Sides[1].bPlayer = true;
		Setup.Sides[0].Units.push_back(MakeUnit("Red", 1, 60, 60, 60, AttackerTroops, AttackerType));
		Setup.Sides[1].Units.push_back(MakeUnit("Blue", 2, 60, 60, 60, DefenderTroops, DefenderType));
		return Setup;
	}

	void Paint(FBattle& Battle, EHexTerrain Terrain)
	{
		for (int Row = 0; Row < Battle.Rows(); ++Row)
		{
			for (int Col = 0; Col < Battle.Cols(); ++Col)
			{
				Battle.DebugSetTerrain({Col, Row}, Terrain);
			}
		}
	}

	int ReachCost(const std::vector<FReachableHex>& Reach, FHex Hex)
	{
		for (const FReachableHex& Entry : Reach)
		{
			if (Entry.Hex == Hex)
			{
				return Entry.Cost;
			}
		}
		return -1;
	}

	int CountEvents(const FBattle& Battle, EBattleEventType Type)
	{
		int Count = 0;
		for (const FBattleEvent& Event : Battle.Events())
		{
			Count += Event.Type == Type ? 1 : 0;
		}
		return Count;
	}

	const FBattleEvent* LastEvent(const FBattle& Battle, EBattleEventType Type)
	{
		const FBattleEvent* Found = nullptr;
		for (const FBattleEvent& Event : Battle.Events())
		{
			if (Event.Type == Type)
			{
				Found = &Event;
			}
		}
		return Found;
	}

	bool Blocking(EHexTerrain Terrain)
	{
		return Terrain == EHexTerrain::Mountain || Terrain == EHexTerrain::Water || Terrain == EHexTerrain::Wall;
	}

	/** Terrain-only path (gates count as passable: they can be broken). */
	bool HasPath(const FBattle& Battle, FHex From, FHex To)
	{
		std::vector<uint8_t> Seen(static_cast<size_t>(Battle.Cols() * Battle.Rows()), 0);
		std::vector<FHex> Queue;
		Queue.push_back(From);
		Seen[static_cast<size_t>(From.Row * Battle.Cols() + From.Col)] = 1;
		for (size_t Head = 0; Head < Queue.size(); ++Head)
		{
			if (Queue[Head] == To)
			{
				return true;
			}
			FHex Around[6];
			HexMath::Neighbors(Queue[Head], Around);
			for (const FHex& Next : Around)
			{
				if (!Battle.InBounds(Next) || Blocking(Battle.TerrainAt(Next)) || Seen[static_cast<size_t>(Next.Row * Battle.Cols() + Next.Col)])
				{
					continue;
				}
				Seen[static_cast<size_t>(Next.Row * Battle.Cols() + Next.Col)] = 1;
				Queue.push_back(Next);
			}
		}
		return false;
	}

	void EndDay(FBattle& Battle)
	{
		Battle.EndTurn();
		Battle.EndTurn();
	}

	double WinRate(EBattleKind Kind, int AttackTroops, int DefendTroops, int Count)
	{
		int Wins = 0;
		for (int Index = 0; Index < Count; ++Index)
		{
			const FBattleSetup Setup = MakeArmies(Kind, AllTerrains[Index % 6], 5000 + static_cast<uint64_t>(Index) * 37, AttackTroops, DefendTroops);
			const FBattleResult Result = IronSim::ResolveBattleAuto(Setup);
			Wins += Result.Winner == 0 ? 1 : 0;
		}
		return static_cast<double>(Wins) / Count;
	}
}

// -------------------------------------------------------------------------------------------------
// Hex math
// -------------------------------------------------------------------------------------------------

IRON_TEST(BattleHexNeighborsAndDistance)
{
	// Odd-q: odd columns sit half a hex lower.
	FHex Around[6];
	HexMath::Neighbors({2, 2}, Around);
	const FHex EvenExpected[6] = {{3, 1}, {3, 2}, {2, 3}, {1, 2}, {1, 1}, {2, 1}};
	for (const FHex& Hex : EvenExpected)
	{
		IRON_EXPECT(std::find(std::begin(Around), std::end(Around), Hex) != std::end(Around));
	}
	HexMath::Neighbors({3, 2}, Around);
	const FHex OddExpected[6] = {{4, 2}, {4, 3}, {3, 3}, {2, 3}, {2, 2}, {3, 1}};
	for (const FHex& Hex : OddExpected)
	{
		IRON_EXPECT(std::find(std::begin(Around), std::end(Around), Hex) != std::end(Around));
	}

	IRON_EXPECT_EQ(HexMath::Distance({0, 0}, {0, 0}), 0);
	IRON_EXPECT_EQ(HexMath::Distance({0, 0}, {1, 0}), 1);
	IRON_EXPECT_EQ(HexMath::Distance({0, 0}, {2, 0}), 2);
	IRON_EXPECT_EQ(HexMath::Distance({0, 0}, {0, 3}), 3);
	IRON_EXPECT_EQ(HexMath::Distance({0, 0}, {15, 10}), 18);
	IRON_EXPECT_EQ(HexMath::Distance({5, 5}, {7, 5}), 2);

	int RingCounts[3] = {0, 0, 0};
	for (int Row = 0; Row < 20; ++Row)
	{
		for (int Col = 0; Col < 20; ++Col)
		{
			const FHex Hex = {Col, Row};
			const int Distance = HexMath::Distance({10, 10}, Hex);
			if (Distance <= 2)
			{
				++RingCounts[Distance];
			}
			IRON_EXPECT_EQ(HexMath::Distance(Hex, {10, 10}), Distance);
			HexMath::Neighbors(Hex, Around);
			for (const FHex& Near : Around)
			{
				IRON_EXPECT_EQ(HexMath::Distance(Hex, Near), 1);
				IRON_EXPECT(std::abs(HexMath::Distance(Near, {10, 10}) - Distance) <= 1);
			}
		}
	}
	IRON_EXPECT_EQ(RingCounts[0], 1);
	IRON_EXPECT_EQ(RingCounts[1], 6);
	IRON_EXPECT_EQ(RingCounts[2], 12);
}

IRON_TEST(BattleHexPixelRoundTrip)
{
	const float Sizes[] = {64.0f, 37.5f, 20.0f};
	for (const float Size : Sizes)
	{
		float Width = 0.0f;
		float Height = 0.0f;
		HexMath::BoardSize(18, 12, Size, Width, Height);
		for (int Row = 0; Row < 12; ++Row)
		{
			for (int Col = 0; Col < 18; ++Col)
			{
				const FHex Hex = {Col, Row};
				float X = 0.0f;
				float Y = 0.0f;
				HexMath::ToPixel(Hex, Size, X, Y);
				IRON_EXPECT(HexMath::FromPixel(X, Y, Size) == Hex);
				// Points well inside the hex map back to it.
				const float Inner = Size * 0.8f;
				IRON_EXPECT(HexMath::FromPixel(X + Inner * 0.7f, Y, Size) == Hex);
				IRON_EXPECT(HexMath::FromPixel(X, Y - Inner * 0.8f, Size) == Hex);
				IRON_EXPECT(HexMath::FromPixel(X - Inner * 0.5f, Y + Inner * 0.6f, Size) == Hex);
				// The whole hex fits on the board.
				IRON_EXPECT(X - Size >= -0.01f && X + Size <= Width + 0.01f);
				IRON_EXPECT(Y - Size * 0.866f >= -0.01f && Y + Size * 0.866f <= Height + 0.01f);
			}
		}
	}
	float Width = 0.0f;
	float Height = 0.0f;
	HexMath::BoardSize(16, 11, 64.0f, Width, Height);
	IRON_EXPECT(std::abs(Width - 1568.0f) < 0.5f);
	IRON_EXPECT(std::abs(Height - 1274.8f) < 0.5f);
}

// -------------------------------------------------------------------------------------------------
// Map generation and deployment
// -------------------------------------------------------------------------------------------------

IRON_TEST(BattleMapsAreValidForEveryTerrain)
{
	for (const ETerrain Terrain : BattleTestUtil::AllTerrains)
	{
		for (int Variant = 0; Variant < 4; ++Variant)
		{
			const bool bSiege = Variant > 0;
			const int CitySize = bSiege ? Variant : 2;
			for (uint64_t Seed = 1; Seed <= 25; ++Seed)
			{
				FBattleSetup Setup = BattleTestUtil::MakeArmies(bSiege ? EBattleKind::Siege : EBattleKind::Field, Terrain, Seed * 7 + 3, 20000, 20000, 5, CitySize);
				if (bSiege)
				{
					// Extra nameless garrison detachments.
					for (int Extra = 0; Extra < 3; ++Extra)
					{
						Setup.Sides[1].Units.push_back(BattleTestUtil::MakeUnit(std::string(), -1, 40, 40, 40, 1500, ETroopType::Infantry));
					}
				}
				FBattle Battle;
				Battle.Setup(Setup);
				const std::string Where = std::string(IronSim::EnumName(Terrain)) + (bSiege ? " siege " + std::to_string(CitySize) : std::string(" field")) + " seed " + std::to_string(Seed);
				const int Cols = Battle.Cols();
				const int Rows = Battle.Rows();
				IRON_EXPECT(!Battle.IsOver());
				if (!bSiege)
				{
					IRON_EXPECT(Cols == 16 && Rows == 11);
				}
				else
				{
					IRON_EXPECT_EQ(Cols, CitySize == 1 ? 16 : (CitySize == 2 ? 17 : 18));
					IRON_EXPECT_EQ(Rows, CitySize == 3 ? 12 : 11);
				}

				// Deployment zones are open ground.
				for (int Row = 0; Row < Rows; ++Row)
				{
					for (int Col = 0; Col < 3; ++Col)
					{
						IRON_EXPECT_MSG(!BattleTestUtil::Blocking(Battle.TerrainAt({Col, Row})), Where);
						if (!bSiege)
						{
							IRON_EXPECT_MSG(!BattleTestUtil::Blocking(Battle.TerrainAt({Cols - 1 - Col, Row})), Where);
						}
					}
				}

				// Units stand on distinct passable hexes in their zones.
				std::vector<FHex> Taken;
				for (const FBattleUnit& Unit : Battle.Units())
				{
					IRON_EXPECT_MSG(Unit.IsActive(), Where);
					IRON_EXPECT(Battle.InBounds(Unit.Pos));
					IRON_EXPECT(Battle.UnitAt(Unit.Pos) == Unit.Id);
					IRON_EXPECT(std::find(Taken.begin(), Taken.end(), Unit.Pos) == Taken.end());
					Taken.push_back(Unit.Pos);
					const EHexTerrain Ground = Battle.TerrainAt(Unit.Pos);
					IRON_EXPECT_MSG(!BattleTestUtil::Blocking(Ground) && Ground != EHexTerrain::Gate, Where);
					if (Unit.Side == 0)
					{
						IRON_EXPECT_MSG(Unit.Pos.Col <= 2, Where);
					}
					else if (bSiege)
					{
						IRON_EXPECT_MSG(Unit.Pos.Col > Battle.WallColumn(), Where);
					}
					else
					{
						IRON_EXPECT_MSG(Unit.Pos.Col >= Cols - 3, Where);
					}
				}
				const FBattleUnit& AttackCommander = Battle.Unit(0);
				IRON_EXPECT(AttackCommander.bCommander);
				IRON_EXPECT_MSG(AttackCommander.Pos.Col <= 1, Where);
				const FBattleUnit& DefendCommander = Battle.Unit(static_cast<int>(Setup.Sides[0].Units.size()));
				IRON_EXPECT(DefendCommander.bCommander && DefendCommander.Side == 1);
				if (bSiege)
				{
					IRON_EXPECT_MSG(DefendCommander.Pos == Battle.CastleHex(), Where);
				}
				else
				{
					IRON_EXPECT_MSG(DefendCommander.Pos.Col >= Cols - 2, Where);
				}

				// The armies can reach each other.
				for (const FBattleUnit& Attacker : Battle.Units())
				{
					for (const FBattleUnit& Defender : Battle.Units())
					{
						if (Attacker.Side == 0 && Defender.Side == 1)
						{
							IRON_EXPECT_MSG(BattleTestUtil::HasPath(Battle, Attacker.Pos, Defender.Pos), Where);
						}
					}
				}

				if (bSiege)
				{
					const int Wall = Battle.WallColumn();
					IRON_EXPECT_MSG(Wall >= Cols / 2 && Wall <= Cols - 4, Where);
					IRON_EXPECT_EQ(Battle.GateCount(), CitySize >= 3 ? 2 : 1);
					IRON_EXPECT(Battle.GateHexAt(0) == Battle.GateHex());
					IRON_EXPECT_EQ(Battle.GateHp(), 1200);
					IRON_EXPECT_EQ(Battle.GateMaxHp(), 1200);
					for (int Index = 0; Index < Battle.GateCount(); ++Index)
					{
						const FHex Gate = Battle.GateHexAt(Index);
						IRON_EXPECT(Gate.Col == Wall);
						IRON_EXPECT(Battle.TerrainAt(Gate) == EHexTerrain::Gate);
						IRON_EXPECT_EQ(Battle.GateHpAt(Index), 1200);
						IRON_EXPECT_MSG(!BattleTestUtil::Blocking(Battle.TerrainAt({Wall - 1, Gate.Row})), Where);
					}
					int Towns = 0;
					for (int Row = 0; Row < Rows; ++Row)
					{
						const EHexTerrain WallHex = Battle.TerrainAt({Wall, Row});
						IRON_EXPECT(WallHex == EHexTerrain::Wall || WallHex == EHexTerrain::Gate);
						for (int Col = Wall + 1; Col < Cols; ++Col)
						{
							Towns += Battle.TerrainAt({Col, Row}) == EHexTerrain::Town ? 1 : 0;
						}
					}
					IRON_EXPECT_MSG(Towns >= 15, Where);
					IRON_EXPECT(Battle.TerrainAt(Battle.CastleHex()) == EHexTerrain::Castle);
					IRON_EXPECT(Battle.CastleHex().Col >= Cols - 3);
				}
				else
				{
					IRON_EXPECT(Battle.WallColumn() == -1);
					IRON_EXPECT_EQ(Battle.GateCount(), 0);
					if (Terrain == ETerrain::River)
					{
						int Crossings = 0;
						int Water = 0;
						for (int Row = 0; Row < Rows; ++Row)
						{
							for (int Col = 0; Col < Cols; ++Col)
							{
								const EHexTerrain Hex = Battle.TerrainAt({Col, Row});
								Crossings += (Hex == EHexTerrain::Ford || Hex == EHexTerrain::Bridge) ? 1 : 0;
								Water += Hex == EHexTerrain::Water ? 1 : 0;
							}
						}
						IRON_EXPECT_MSG(Crossings >= 2 && Water >= 5, Where);
					}
				}

				// Same seed, same map.
				FBattle Again;
				Again.Setup(Setup);
				bool bSame = true;
				for (int Row = 0; Row < Rows; ++Row)
				{
					for (int Col = 0; Col < Cols; ++Col)
					{
						bSame = bSame && Again.TerrainAt({Col, Row}) == Battle.TerrainAt({Col, Row});
					}
				}
				IRON_EXPECT_MSG(bSame, Where);
			}
		}
	}

	// Different seeds give different maps.
	FBattle First;
	First.Setup(BattleTestUtil::MakeArmies(EBattleKind::Field, ETerrain::Forest, 1, 10000, 10000));
	FBattle Second;
	Second.Setup(BattleTestUtil::MakeArmies(EBattleKind::Field, ETerrain::Forest, 2, 10000, 10000));
	int Differences = 0;
	for (int Row = 0; Row < First.Rows(); ++Row)
	{
		for (int Col = 0; Col < First.Cols(); ++Col)
		{
			Differences += First.TerrainAt({Col, Row}) != Second.TerrainAt({Col, Row}) ? 1 : 0;
		}
	}
	IRON_EXPECT(Differences > 5);
	IRON_EXPECT(std::string(IronSim::AssetName(EHexTerrain::Plain)) == "Plain");
	IRON_EXPECT(std::string(IronSim::EnumName(EHexTerrain::Rubble)) == "rubble");
	IRON_EXPECT(!IronSim::DisplayName(EHexTerrain::Castle).empty());
	IRON_EXPECT(!IronSim::DisplayName(ETactic::Confuse).empty());
}

// -------------------------------------------------------------------------------------------------
// Movement
// -------------------------------------------------------------------------------------------------

IRON_TEST(BattleMovementCostsAndZoneOfControl)
{
	FBattle Battle;
	Battle.Setup(BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry));
	// A one-hex corridor along row 5; (c, 5) and (c + 1, 5) are always adjacent in odd-q.
	BattleTestUtil::Paint(Battle, EHexTerrain::Mountain);
	for (int Col = 0; Col < Battle.Cols(); ++Col)
	{
		Battle.DebugSetTerrain({Col, 5}, EHexTerrain::Plain);
	}
	Battle.DebugSetTerrain({4, 4}, EHexTerrain::Plain);
	Battle.DebugSetTerrain({12, 0}, EHexTerrain::Plain);
	IRON_EXPECT(Battle.DebugPlaceUnit(0, {2, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {12, 0}));
	IRON_EXPECT_EQ(Battle.MovePoints(0), 4);

	std::vector<FReachableHex> Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {3, 5}), 1);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {6, 5}), 4);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {7, 5}), -1);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {0, 5}), 2);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {2, 5}), -1);

	// Zone of control: (4, 5) touches the enemy at (4, 4), so movement ends there.
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {4, 4}));
	Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {4, 5}), 2);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {5, 5}), -1);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {6, 5}), -1);
	IRON_EXPECT(!Battle.Move(0, {5, 5}));
	IRON_EXPECT(!Battle.Move(0, {4, 4}));

	// Terrain costs: forest 2 (cavalry 3), ford 3.
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {12, 0}));
	Battle.DebugSetTerrain({3, 5}, EHexTerrain::Forest);
	Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {3, 5}), 2);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {5, 5}), 4);
	Battle.DebugSetTerrain({3, 5}, EHexTerrain::Ford);
	Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {3, 5}), 3);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {4, 5}), 4);
	Battle.DebugSetTerrain({3, 5}, EHexTerrain::Plain);

	// The waiting side's units report their full range; they cannot move on the other side's turn.
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {12, 5}));
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Battle.Reachable(1), {11, 5}), 1);
	IRON_EXPECT(!Battle.CanMove(1));
	IRON_EXPECT(!Battle.Move(1, {11, 5}));

	// Move, undo, move again; one move per turn.
	Battle.ClearEvents();
	IRON_EXPECT(Battle.Move(0, {5, 5}));
	const FBattleEvent* Moved = BattleTestUtil::LastEvent(Battle, EBattleEventType::Move);
	IRON_EXPECT(Moved != nullptr && Moved->Unit == 0 && Moved->From == FHex({2, 5}) && Moved->To == FHex({5, 5}) && Moved->Value == 3);
	IRON_EXPECT(!Battle.Move(0, {6, 5}));
	IRON_EXPECT(Battle.Reachable(0).empty());
	IRON_EXPECT(Battle.UndoMove(0));
	IRON_EXPECT(Battle.Unit(0).Pos == FHex({2, 5}));
	IRON_EXPECT(!Battle.UndoMove(0));
	IRON_EXPECT(Battle.Move(0, {4, 5}));
	IRON_EXPECT(Battle.Wait(0));
	IRON_EXPECT(!Battle.UndoMove(0));
	IRON_EXPECT(!Battle.CanAct(0));

	// Cavalry: 6 points, forest costs 3. Archers: 3 points.
	FBattle Riders;
	Riders.Setup(BattleTestUtil::MakeDuo(ETroopType::Cavalry, ETroopType::Archer));
	BattleTestUtil::Paint(Riders, EHexTerrain::Mountain);
	for (int Col = 0; Col < Riders.Cols(); ++Col)
	{
		Riders.DebugSetTerrain({Col, 5}, EHexTerrain::Plain);
	}
	Riders.DebugSetTerrain({3, 5}, EHexTerrain::Forest);
	Riders.DebugSetTerrain({12, 0}, EHexTerrain::Plain);
	IRON_EXPECT(Riders.DebugPlaceUnit(0, {2, 5}));
	IRON_EXPECT(Riders.DebugPlaceUnit(1, {12, 0}));
	IRON_EXPECT_EQ(Riders.MovePoints(0), 6);
	IRON_EXPECT_EQ(Riders.MovePoints(1), 3);
	Reach = Riders.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {3, 5}), 3);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {6, 5}), 6);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {7, 5}), -1);
}

IRON_TEST(BattleUnitsBlockEnemiesButNotFriends)
{
	FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
	Setup.Sides[0].Units.push_back(BattleTestUtil::MakeUnit("Red 2", 3, 60, 60, 60, 3000, ETroopType::Infantry));
	FBattle Battle;
	Battle.Setup(Setup);
	BattleTestUtil::Paint(Battle, EHexTerrain::Mountain);
	for (int Col = 0; Col < Battle.Cols(); ++Col)
	{
		Battle.DebugSetTerrain({Col, 5}, EHexTerrain::Plain);
	}
	Battle.DebugSetTerrain({14, 0}, EHexTerrain::Plain);
	// Units: 0 = Red, 1 = Red 2, 2 = Blue.
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {3, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(0, {2, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(2, {14, 0}));
	std::vector<FReachableHex> Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {3, 5}), -1);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {4, 5}), 2);
	// An enemy in the corridor blocks it.
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {0, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(2, {4, 5}));
	Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {3, 5}), 1);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, {5, 5}), -1);
	IRON_EXPECT(Battle.UnitAt({4, 5}) == 2);
	IRON_EXPECT(Battle.UnitAt({9, 9}) == -1);
}

// -------------------------------------------------------------------------------------------------
// Combat
// -------------------------------------------------------------------------------------------------

namespace BattleTestUtil
{
	/** Expected damage of a lone attacker against a lone defender standing on Ground. */
	int Preview(ETroopType AttackerType, ETroopType DefenderType, EHexTerrain Ground, int Distance = 1, int AttackerTroops = 5000)
	{
		FBattle Battle;
		Battle.Setup(MakeDuo(AttackerType, DefenderType, AttackerTroops, 5000));
		Paint(Battle, EHexTerrain::Plain);
		IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
		IRON_EXPECT(Battle.DebugPlaceUnit(1, {5 + Distance, 5}));
		Battle.DebugSetTerrain({5 + Distance, 5}, Ground);
		return Battle.PreviewDamage(0, 1);
	}
}

IRON_TEST(BattleAttackDamageIsSane)
{
	FBattle Battle;
	Battle.Setup(BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry));
	BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
	IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {6, 5}));
	IRON_EXPECT(Battle.AttackTargets(0) == std::vector<int>({1}));
	const int Preview = Battle.PreviewDamage(0, 1);
	IRON_EXPECT_MSG(Preview > 250 && Preview < 700, std::to_string(Preview));
	Battle.ClearEvents();
	IRON_EXPECT(Battle.Attack(0, 1));
	const FBattleEvent* Hit = BattleTestUtil::LastEvent(Battle, EBattleEventType::Attack);
	const FBattleEvent* Counter = BattleTestUtil::LastEvent(Battle, EBattleEventType::Counter);
	IRON_EXPECT(Hit != nullptr && Counter != nullptr);
	if (Hit && Counter)
	{
		IRON_EXPECT(Hit->Unit == 0 && Hit->Target == 1 && Hit->From == FHex({5, 5}) && Hit->To == FHex({6, 5}));
		IRON_EXPECT_MSG(Hit->Value * 100 >= Preview * 84 && Hit->Value * 100 <= Preview * 116, std::to_string(Hit->Value) + " vs " + std::to_string(Preview));
		IRON_EXPECT(Counter->Unit == 1 && Counter->Target == 0);
		IRON_EXPECT(Counter->Value > 0 && Counter->Value < Hit->Value);
		IRON_EXPECT_EQ(Battle.Unit(1).Troops, 5000 - Hit->Value);
		IRON_EXPECT_EQ(Battle.Unit(0).Troops, 5000 - Counter->Value);
		IRON_EXPECT_EQ(Battle.Unit(0).DamageDealt, Hit->Value);
		IRON_EXPECT(!Hit->Text.empty());
	}
	IRON_EXPECT(Battle.Unit(1).Morale < 70);
	IRON_EXPECT(!Battle.Attack(0, 1));
	IRON_EXPECT(!Battle.CanAct(0));
	IRON_EXPECT(Battle.Log().size() >= 3);

	// Archers at range 2: no counterattack.
	FBattle Volley;
	Volley.Setup(BattleTestUtil::MakeDuo(ETroopType::Archer, ETroopType::Infantry));
	BattleTestUtil::Paint(Volley, EHexTerrain::Plain);
	IRON_EXPECT(Volley.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Volley.DebugPlaceUnit(1, {7, 5}));
	Volley.ClearEvents();
	IRON_EXPECT(Volley.Attack(0, 1));
	IRON_EXPECT_EQ(BattleTestUtil::CountEvents(Volley, EBattleEventType::Attack), 1);
	IRON_EXPECT_EQ(BattleTestUtil::CountEvents(Volley, EBattleEventType::Counter), 0);
	IRON_EXPECT_EQ(Volley.Unit(0).Troops, 5000);

	// Melee units cannot reach two hexes away.
	FBattle Far;
	Far.Setup(BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry));
	BattleTestUtil::Paint(Far, EHexTerrain::Plain);
	IRON_EXPECT(Far.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Far.DebugPlaceUnit(1, {7, 5}));
	IRON_EXPECT(Far.AttackTargets(0).empty());
	IRON_EXPECT(!Far.Attack(0, 1));

	// Matchups and terrain.
	const int InfantryVsArchers = BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Archer, EHexTerrain::Plain);
	const int CavalryVsArchers = BattleTestUtil::Preview(ETroopType::Cavalry, ETroopType::Archer, EHexTerrain::Plain);
	IRON_EXPECT(CavalryVsArchers > InfantryVsArchers * 12 / 10);
	IRON_EXPECT(BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Cavalry, EHexTerrain::Plain) > BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Infantry, EHexTerrain::Plain));
	IRON_EXPECT(BattleTestUtil::Preview(ETroopType::Archer, ETroopType::Infantry, EHexTerrain::Plain, 2) > BattleTestUtil::Preview(ETroopType::Archer, ETroopType::Cavalry, EHexTerrain::Plain, 2));
	const int OnPlain = BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Infantry, EHexTerrain::Plain);
	const int InForest = BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Infantry, EHexTerrain::Forest);
	const int OnHill = BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Infantry, EHexTerrain::Hill);
	const int InFord = BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Infantry, EHexTerrain::Ford);
	IRON_EXPECT(InForest < OnPlain && OnHill < InForest && InFord > OnPlain);
	const int Doubled = BattleTestUtil::Preview(ETroopType::Infantry, ETroopType::Infantry, EHexTerrain::Plain, 1, 10000);
	IRON_EXPECT(Doubled * 100 > OnPlain * 130 && Doubled * 100 < OnPlain * 150);
}

IRON_TEST(BattleTacticsFireConfuseRally)
{
	// Fire: a brilliant strategist against a dull officer in the woods.
	FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
	Setup.Sides[0].Units[0].Stats[2] = 95;
	Setup.Sides[1].Units[0].Stats[2] = 20;
	FBattle Battle;
	Battle.Setup(Setup);
	BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
	IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {7, 5}));
	Battle.DebugSetTerrain({7, 5}, EHexTerrain::Forest);
	IRON_EXPECT(Battle.TacticTargets(0, ETactic::Fire) == std::vector<int>({1}));
	IRON_EXPECT_EQ(Battle.TacticChance(0, ETactic::Fire, 1), 95);
	bool bBurned = false;
	for (int Day = 0; Day < 10 && !bBurned; ++Day)
	{
		Battle.ClearEvents();
		IRON_EXPECT(Battle.UseTactic(0, ETactic::Fire, 1));
		const FBattleEvent* Done = BattleTestUtil::LastEvent(Battle, EBattleEventType::Tactic);
		if (Done)
		{
			bBurned = true;
			IRON_EXPECT(Done->Tactic == ETactic::Fire && Done->Unit == 0 && Done->Target == 1 && Done->Value > 0);
			IRON_EXPECT_EQ(Battle.Unit(1).Troops, 5000 - Done->Value);
			IRON_EXPECT_EQ(Battle.BurningAt({7, 5}), 2);
			IRON_EXPECT_EQ(Battle.Unit(0).TacticsSucceeded, 1);
		}
		else
		{
			IRON_EXPECT(BattleTestUtil::LastEvent(Battle, EBattleEventType::TacticFailed) != nullptr);
		}
		IRON_EXPECT(!Battle.UseTactic(0, ETactic::Fire, 1));
		BattleTestUtil::EndDay(Battle);
	}
	IRON_EXPECT(bBurned);
	// The fire burns the unit standing in it at dawn, then dies down; nobody may enter it meanwhile.
	IRON_EXPECT(BattleTestUtil::CountEvents(Battle, EBattleEventType::Burn) == 1);
	IRON_EXPECT_EQ(Battle.BurningAt({7, 5}), 1);
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {12, 2}));
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Battle.Reachable(0), {7, 5}), -1);
	BattleTestUtil::EndDay(Battle);
	IRON_EXPECT_EQ(Battle.BurningAt({7, 5}), 0);

	// Fire is useless against troops standing in water.
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {7, 5}));
	Battle.DebugSetTerrain({7, 5}, EHexTerrain::Ford);
	IRON_EXPECT(Battle.TacticTargets(0, ETactic::Fire).empty());

	// Confuse: the target loses its next turn.
	FBattle Mind;
	Mind.Setup(Setup);
	BattleTestUtil::Paint(Mind, EHexTerrain::Plain);
	IRON_EXPECT(Mind.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Mind.DebugPlaceUnit(1, {7, 5}));
	bool bConfused = false;
	for (int Day = 0; Day < 10 && !bConfused; ++Day)
	{
		Mind.ClearEvents();
		IRON_EXPECT(Mind.UseTactic(0, ETactic::Confuse, 1));
		const FBattleEvent* Done = BattleTestUtil::LastEvent(Mind, EBattleEventType::Tactic);
		if (Done)
		{
			bConfused = true;
			IRON_EXPECT(Done->Tactic == ETactic::Confuse);
			IRON_EXPECT(Mind.Unit(1).ConfusedDays > 0);
			Mind.EndTurn();
			IRON_EXPECT_EQ(Mind.ActiveSide(), 1);
			IRON_EXPECT(!Mind.CanMove(1));
			IRON_EXPECT(!Mind.CanAct(1));
			IRON_EXPECT(!Mind.Move(1, {8, 5}));
			IRON_EXPECT(!Mind.Attack(1, 0));
			BattleTestUtil::EndDay(Mind);
			IRON_EXPECT_EQ(Mind.ActiveSide(), 1);
			IRON_EXPECT(Mind.CanMove(1));
		}
		else
		{
			BattleTestUtil::EndDay(Mind);
		}
	}
	IRON_EXPECT(bConfused);

	// Rally: restores morale and cures confusion.
	FBattleSetup RallySetup = Setup;
	RallySetup.Sides[0].Units.push_back(BattleTestUtil::MakeUnit("Red 2", 3, 60, 60, 60, 4000, ETroopType::Infantry));
	FBattle Camp;
	Camp.Setup(RallySetup);
	BattleTestUtil::Paint(Camp, EHexTerrain::Plain);
	// Units: 0 = Red (strategist), 1 = Red 2, 2 = Blue.
	IRON_EXPECT(Camp.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Camp.DebugPlaceUnit(1, {6, 5}));
	IRON_EXPECT(Camp.DebugPlaceUnit(2, {12, 2}));
	Camp.DebugSetUnit(1, 4000, 20);
	IRON_EXPECT(Camp.TacticTargets(0, ETactic::Rally).size() == 2);
	bool bRallied = false;
	for (int Day = 0; Day < 10 && !bRallied; ++Day)
	{
		Camp.ClearEvents();
		IRON_EXPECT(Camp.UseTactic(0, ETactic::Rally, 1));
		const FBattleEvent* Done = BattleTestUtil::LastEvent(Camp, EBattleEventType::Tactic);
		if (Done)
		{
			bRallied = true;
			IRON_EXPECT(Done->Tactic == ETactic::Rally && Done->Value > 0);
			IRON_EXPECT_EQ(Camp.Unit(1).Morale, 20 + Done->Value);
		}
		BattleTestUtil::EndDay(Camp);
	}
	IRON_EXPECT(bRallied);
}

IRON_TEST(BattleGateBreaksAndOpensTheWay)
{
	FBattleSetup Setup = BattleTestUtil::MakeArmies(EBattleKind::Siege, ETerrain::Plains, 4, 8000, 3000, 1);
	Setup.Sides[0].bPlayer = true;
	Setup.Sides[1].bPlayer = true;
	Setup.GateHp = 900;
	FBattle Battle;
	Battle.Setup(Setup);
	const FHex Gate = Battle.GateHex();
	const FHex Outside = {Gate.Col - 1, Gate.Row};
	const FHex Inside = {Gate.Col + 1, Gate.Row};
	IRON_EXPECT(Battle.TerrainAt(Gate) == EHexTerrain::Gate);

	// Defenders pass through their own gate (but cannot stop on it); attackers cannot.
	Battle.EndTurn();
	IRON_EXPECT(Battle.DebugPlaceUnit(1, Inside));
	std::vector<FReachableHex> Reach = Battle.Reachable(1);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, Gate), -1);
	IRON_EXPECT(BattleTestUtil::ReachCost(Reach, Outside) > 0);
	IRON_EXPECT(Battle.DebugPlaceUnit(1, Battle.CastleHex()));
	Battle.EndTurn();

	IRON_EXPECT(Battle.DebugPlaceUnit(0, Outside));
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Battle.Reachable(0), Gate), -1);
	IRON_EXPECT(Battle.CanAttackGate(0));
	int Hits = 0;
	while (Battle.GateHp() > 0 && Hits < 20)
	{
		const int Before = Battle.GateHp();
		Battle.ClearEvents();
		IRON_EXPECT(Battle.AttackGate(0));
		const FBattleEvent* Hit = BattleTestUtil::LastEvent(Battle, EBattleEventType::GateHit);
		IRON_EXPECT(Hit != nullptr && Hit->Unit == 0 && Hit->To == Gate && Hit->Value > 0);
		IRON_EXPECT(Battle.GateHp() == std::max(0, Before - (Hit ? Hit->Value : 0)));
		IRON_EXPECT(!Battle.AttackGate(0));
		++Hits;
		if (Battle.GateHp() > 0)
		{
			BattleTestUtil::EndDay(Battle);
		}
	}
	IRON_EXPECT(Hits >= 2 && Hits < 20);
	IRON_EXPECT(BattleTestUtil::LastEvent(Battle, EBattleEventType::GateBroken) != nullptr);
	IRON_EXPECT(Battle.TerrainAt(Gate) == EHexTerrain::Rubble);
	IRON_EXPECT_EQ(Battle.GateHpAt(0), 0);
	BattleTestUtil::EndDay(Battle);
	IRON_EXPECT(!Battle.CanAttackGate(0));
	Reach = Battle.Reachable(0);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, Gate), 2);
	IRON_EXPECT_EQ(BattleTestUtil::ReachCost(Reach, Inside), 3);
}

// -------------------------------------------------------------------------------------------------
// Victory conditions
// -------------------------------------------------------------------------------------------------

IRON_TEST(BattleEndsWhenTheCommanderFalls)
{
	FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry, 8000, 5000);
	Setup.Sides[1].Units.push_back(BattleTestUtil::MakeUnit("Blue 2", 4, 60, 60, 60, 5000, ETroopType::Infantry));
	FBattle Battle;
	Battle.Setup(Setup);
	BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
	IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {6, 5}));
	IRON_EXPECT(Battle.DebugPlaceUnit(2, {12, 2}));
	Battle.DebugSetUnit(1, 40, 60);
	IRON_EXPECT(Battle.Attack(0, 1));
	IRON_EXPECT(Battle.IsOver());
	IRON_EXPECT_EQ(Battle.Result().Winner, 0);
	IRON_EXPECT(Battle.Unit(1).Status == EUnitStatus::Destroyed || Battle.Unit(1).Status == EUnitStatus::Captured);
	IRON_EXPECT(Battle.Unit(2).IsActive());
	IRON_EXPECT(BattleTestUtil::LastEvent(Battle, EBattleEventType::Victory) != nullptr);
	IRON_EXPECT(!Battle.Result().Summary.empty());
	IRON_EXPECT_EQ(static_cast<int>(Battle.Result().Units.size()), 3);
	IRON_EXPECT_EQ(Battle.Result().Units[1].Troops, 0);
	IRON_EXPECT_EQ(Battle.Result().Units[2].Troops, 5000);
	IRON_EXPECT(!Battle.IsPlayerTurn());
	IRON_EXPECT(!Battle.Move(0, {4, 5}));
	IRON_EXPECT(!Battle.StepAI());

	// A routed commander loses the battle too.
	FBattle Panic;
	Panic.Setup(Setup);
	BattleTestUtil::Paint(Panic, EHexTerrain::Plain);
	IRON_EXPECT(Panic.DebugPlaceUnit(0, {5, 5}));
	IRON_EXPECT(Panic.DebugPlaceUnit(1, {6, 5}));
	IRON_EXPECT(Panic.DebugPlaceUnit(2, {12, 2}));
	Panic.DebugSetUnit(1, 5000, 11);
	IRON_EXPECT(Panic.Attack(0, 1));
	IRON_EXPECT(Panic.IsOver() && Panic.Result().Winner == 0);
	IRON_EXPECT(Panic.Unit(1).Status == EUnitStatus::Routed);
	IRON_EXPECT(Panic.Result().Units[1].Troops > 0);
}

IRON_TEST(BattleCastleCaptureWinsTheSiege)
{
	FBattleSetup Setup = BattleTestUtil::MakeArmies(EBattleKind::Siege, ETerrain::Hills, 8, 10000, 10000, 2);
	Setup.Sides[0].bPlayer = true;
	Setup.Sides[1].bPlayer = true;
	FBattle Battle;
	Battle.Setup(Setup);
	const FHex Castle = Battle.CastleHex();
	IRON_EXPECT(Battle.UnitAt(Castle) == 2);
	// The defending commander steps away; a raider slips in next to the castle.
	IRON_EXPECT(Battle.DebugPlaceUnit(2, {Castle.Col, Castle.Row == 0 ? 3 : 0}));
	IRON_EXPECT(Battle.DebugPlaceUnit(3, {Castle.Col, Castle.Row == 1 ? 4 : 1}));
	IRON_EXPECT(Battle.DebugPlaceUnit(1, {Castle.Col - 2, Castle.Row}));
	IRON_EXPECT(BattleTestUtil::ReachCost(Battle.Reachable(1), Castle) > 0);
	IRON_EXPECT(Battle.Move(1, Castle));
	IRON_EXPECT(Battle.IsOver());
	IRON_EXPECT_EQ(Battle.Result().Winner, 0);
}

IRON_TEST(BattleDefenderWinsAtTheDayLimit)
{
	FBattleSetup Setup = BattleTestUtil::MakeArmies(EBattleKind::Field, ETerrain::Plains, 3, 10000, 10000, 2);
	Setup.Sides[0].bPlayer = true;
	Setup.Sides[1].bPlayer = true;
	Setup.MaxDays = 5;
	FBattle Battle;
	Battle.Setup(Setup);
	int Turns = 0;
	while (!Battle.IsOver() && Turns < 100)
	{
		IRON_EXPECT_EQ(Battle.ActiveSide(), Turns % 2);
		IRON_EXPECT_EQ(Battle.Day(), 1 + Turns / 2);
		IRON_EXPECT(Battle.IsPlayerTurn());
		Battle.EndTurn();
		++Turns;
	}
	IRON_EXPECT_EQ(Turns, 10);
	IRON_EXPECT_EQ(Battle.Result().Winner, 1);
	IRON_EXPECT_EQ(Battle.Result().Days, 5);
	IRON_EXPECT_EQ(Battle.Day(), 5);
	IRON_EXPECT(BattleTestUtil::CountEvents(Battle, EBattleEventType::DayStart) == 5);
}

IRON_TEST(BattleAttackerWithdrawsWhenFoodRunsOut)
{
	FBattleSetup Setup = BattleTestUtil::MakeArmies(EBattleKind::Siege, ETerrain::Plains, 3, 30000, 10000, 3);
	Setup.Sides[0].bPlayer = true;
	Setup.Sides[1].bPlayer = true;
	Setup.Sides[0].FoodDays = 3;
	FBattle Battle;
	Battle.Setup(Setup);
	BattleTestUtil::EndDay(Battle);
	BattleTestUtil::EndDay(Battle);
	IRON_EXPECT(!Battle.IsOver());
	const int MoraleBefore = Battle.Unit(0).Morale;
	BattleTestUtil::EndDay(Battle);
	IRON_EXPECT(Battle.IsOver());
	IRON_EXPECT_EQ(Battle.Result().Winner, 1);
	IRON_EXPECT_EQ(Battle.Result().Days, 4);
	IRON_EXPECT(MoraleBefore < 70);
}

// -------------------------------------------------------------------------------------------------
// Duels inside battles
// -------------------------------------------------------------------------------------------------

IRON_TEST(BattleAIChallengesAndThePlayerAnswers)
{
	FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
	Setup.Sides[0].Units[0].Stats[0] = 50;
	Setup.Sides[1].bPlayer = false;
	Setup.Sides[1].Units[0].Stats[0] = 95;
	FTechnique Fang;
	Fang.Key = "fang";
	Fang.Name = "Fang";
	Fang.Kind = EDuelMove::Strike;
	Fang.Power = 180;
	Setup.Techniques.push_back(Fang);
	Setup.Sides[1].Units[0].Techniques.push_back(0);

	for (int Accept = 0; Accept < 2; ++Accept)
	{
		FBattle Battle;
		Battle.Setup(Setup);
		BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
		IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
		IRON_EXPECT(Battle.DebugPlaceUnit(1, {6, 5}));
		IRON_EXPECT(Battle.IsPlayerTurn());
		IRON_EXPECT(!Battle.StepAI());
		IRON_EXPECT(Battle.Wait(0));
		Battle.EndTurn();
		IRON_EXPECT(!Battle.IsPlayerTurn());
		int Steps = 0;
		while (Battle.StepAI() && Steps < 20)
		{
			++Steps;
		}
		IRON_EXPECT(Battle.HasPendingChallenge());
		IRON_EXPECT_EQ(Battle.ChallengerUnit(), 1);
		IRON_EXPECT_EQ(Battle.ChallengedUnit(), 0);
		IRON_EXPECT(!Battle.IsPlayerTurn());
		IRON_EXPECT(!Battle.StepAI());
		IRON_EXPECT(BattleTestUtil::LastEvent(Battle, EBattleEventType::DuelChallenge) != nullptr);
		if (Accept == 0)
		{
			const int MoraleBefore = Battle.Unit(0).Morale;
			Battle.AnswerChallenge(false);
			IRON_EXPECT(!Battle.HasPendingChallenge());
			IRON_EXPECT(Battle.Unit(0).Morale < MoraleBefore);
			IRON_EXPECT(BattleTestUtil::LastEvent(Battle, EBattleEventType::DuelDeclined) != nullptr);
		}
		else
		{
			Battle.AnswerChallenge(true);
			IRON_EXPECT(Battle.HasActiveDuel());
			IRON_EXPECT_EQ(Battle.DuelUnit(0), 1);
			IRON_EXPECT_EQ(Battle.DuelUnit(1), 0);
			IRON_EXPECT(Battle.ActiveDuel().Side(1).bPlayer);
			IRON_EXPECT(!Battle.ActiveDuel().Side(0).bPlayer);
			IRON_EXPECT(!Battle.StepAI());
			int Rounds = 0;
			while (!Battle.ActiveDuel().IsOver() && Rounds < 20)
			{
				Battle.ActiveDuel().PlayVersusAI(1, Rounds % 2 == 0 ? EDuelMove::Guard : EDuelMove::Feint, -1);
				++Rounds;
			}
			const int TroopsBefore = Battle.Unit(0).Troops + Battle.Unit(1).Troops;
			Battle.FinishDuel();
			IRON_EXPECT(!Battle.HasActiveDuel());
			const FBattleEvent* Result = BattleTestUtil::LastEvent(Battle, EBattleEventType::DuelResult);
			IRON_EXPECT(Result != nullptr);
			if (Result && Result->Value >= 0)
			{
				IRON_EXPECT(Battle.Unit(0).Troops + Battle.Unit(1).Troops < TroopsBefore);
				IRON_EXPECT_EQ(Battle.Unit(Result->Value).DuelsWon, 1);
			}
		}
		// The AI turn carries on (or the duel decided the battle).
		Steps = 0;
		while (Battle.StepAI() && Steps < 20)
		{
			++Steps;
		}
		IRON_EXPECT(Battle.IsOver() || Battle.IsPlayerTurn());
		if (!Battle.IsOver())
		{
			// The AI does not repeat a challenge to the same officer.
			Battle.EndTurn();
			Steps = 0;
			while (Battle.StepAI() && Steps < 20)
			{
				++Steps;
			}
			IRON_EXPECT(!Battle.HasPendingChallenge());
		}
	}
}

IRON_TEST(BattlePlayerChallengeIsAnsweredByTheAI)
{
	int Accepted = 0;
	int Declined = 0;
	for (uint64_t Seed = 1; Seed <= 30; ++Seed)
	{
		FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
		Setup.Seed = Seed;
		Setup.Sides[0].Units[0].Stats[0] = 70;
		Setup.Sides[1].bPlayer = false;
		Setup.Sides[1].Units[0].Stats[0] = 80;
		Setup.Sides[1].Units[0].Bravery = 60;
		FBattle Battle;
		Battle.Setup(Setup);
		BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
		IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
		IRON_EXPECT(Battle.DebugPlaceUnit(1, {6, 5}));
		IRON_EXPECT(Battle.DuelTargets(0) == std::vector<int>({1}));
		IRON_EXPECT(Battle.ChallengeDuel(0, 1));
		IRON_EXPECT(!Battle.HasPendingChallenge());
		IRON_EXPECT(!Battle.CanAct(0));
		if (Battle.HasActiveDuel())
		{
			++Accepted;
			IRON_EXPECT(Battle.ActiveDuel().Side(0).bPlayer);
			IRON_EXPECT(!Battle.IsPlayerTurn());
			Battle.ActiveDuel().AutoPlay();
			Battle.FinishDuel();
			IRON_EXPECT(!Battle.HasActiveDuel());
		}
		else
		{
			++Declined;
			IRON_EXPECT(BattleTestUtil::LastEvent(Battle, EBattleEventType::DuelDeclined) != nullptr);
		}
		IRON_EXPECT(Battle.IsOver() || Battle.IsPlayerTurn());
		// Each pair duels at most once per battle.
		BattleTestUtil::EndDay(Battle);
		IRON_EXPECT(Battle.IsOver() || (Battle.CanAct(0) && Battle.DuelTargets(0).empty() && !Battle.ChallengeDuel(0, 1)));
	}
	// A stronger officer accepts nearly always.
	IRON_EXPECT(Accepted >= 20);

	// A much weaker, timid officer usually declines.
	Accepted = 0;
	for (uint64_t Seed = 1; Seed <= 30; ++Seed)
	{
		FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
		Setup.Seed = Seed;
		Setup.Sides[0].Units[0].Stats[0] = 95;
		Setup.Sides[1].bPlayer = false;
		Setup.Sides[1].Units[0].Stats[0] = 55;
		Setup.Sides[1].Units[0].Bravery = 30;
		FBattle Battle;
		Battle.Setup(Setup);
		BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
		IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
		IRON_EXPECT(Battle.DebugPlaceUnit(1, {6, 5}));
		IRON_EXPECT(Battle.ChallengeDuel(0, 1));
		Accepted += Battle.HasActiveDuel() ? 1 : 0;
	}
	IRON_EXPECT(Accepted <= 6);
	IRON_EXPECT(Declined >= 0);
}

// -------------------------------------------------------------------------------------------------
// AI and turn flow
// -------------------------------------------------------------------------------------------------

namespace BattleTestUtil
{
	struct FProgress
	{
		int Day = 0;
		int Side = 0;
		int Moved = 0;
		int Acted = 0;
		int Active = 0;
		bool bChallenge = false;
		bool bDuel = false;
		bool bOver = false;

		bool operator==(const FProgress& Other) const
		{
			return Day == Other.Day && Side == Other.Side && Moved == Other.Moved && Acted == Other.Acted && Active == Other.Active && bChallenge == Other.bChallenge && bDuel == Other.bDuel && bOver == Other.bOver;
		}
	};

	FProgress Snapshot(const FBattle& Battle)
	{
		FProgress Progress;
		Progress.Day = Battle.Day();
		Progress.Side = Battle.ActiveSide();
		for (const FBattleUnit& Unit : Battle.Units())
		{
			Progress.Moved += Unit.bMoved ? 1 : 0;
			Progress.Acted += Unit.bActed ? 1 : 0;
			Progress.Active += Unit.IsActive() ? 1 : 0;
		}
		Progress.bChallenge = Battle.HasPendingChallenge();
		Progress.bDuel = Battle.HasActiveDuel();
		Progress.bOver = Battle.IsOver();
		return Progress;
	}
}

IRON_TEST(BattleStepAIAlwaysProgressesAndTerminates)
{
	for (int Kind = 0; Kind < 2; ++Kind)
	{
		for (int Index = 0; Index < 12; ++Index)
		{
			const ETerrain Terrain = BattleTestUtil::AllTerrains[Index % 6];
			const int Attackers = 10000 + 5000 * (Index % 4);
			FBattleSetup Setup = BattleTestUtil::MakeArmies(Kind == 0 ? EBattleKind::Field : EBattleKind::Siege, Terrain, 300 + static_cast<uint64_t>(Index), Attackers, 15000, 3 + Index % 3, 1 + Index % 3);
			// Officers of uneven strength so duels happen now and then.
			Setup.Sides[0].Units[1].Stats[0] = 95;
			Setup.Sides[1].Units[1].Stats[0] = 40;
			FBattle Battle;
			Battle.Setup(Setup);
			int Steps = 0;
			int StepsThisTurn = 0;
			int LastSide = Battle.ActiveSide();
			while (!Battle.IsOver() && Steps < 20000)
			{
				const BattleTestUtil::FProgress Before = BattleTestUtil::Snapshot(Battle);
				const size_t EventsBefore = Battle.Events().size();
				IRON_EXPECT(Battle.StepAI());
				const BattleTestUtil::FProgress After = BattleTestUtil::Snapshot(Battle);
				IRON_EXPECT(!(Before == After) || Battle.Events().size() != EventsBefore);
				++Steps;
				++StepsThisTurn;
				if (Battle.ActiveSide() != LastSide)
				{
					// One move and one action per unit, plus ending the turn and settling duels.
					IRON_EXPECT(StepsThisTurn <= 2 * static_cast<int>(Battle.Units().size()) + 4);
					StepsThisTurn = 0;
					LastSide = Battle.ActiveSide();
				}
			}
			IRON_EXPECT(Battle.IsOver());
			IRON_EXPECT(Battle.Result().bFinished);
			IRON_EXPECT(Battle.Result().Winner == 0 || Battle.Result().Winner == 1);
			IRON_EXPECT(Battle.Result().Days >= 1 && Battle.Result().Days <= Setup.MaxDays);
			IRON_EXPECT(!Battle.StepAI());
			IRON_EXPECT(!Battle.Log().empty());
		}
	}
}

IRON_TEST(BattleStepAIHandsTurnsBackToThePlayer)
{
	FBattleSetup Setup = BattleTestUtil::MakeArmies(EBattleKind::Field, ETerrain::Plains, 17, 15000, 15000, 4);
	Setup.Sides[0].bPlayer = true;
	FBattle Battle;
	Battle.Setup(Setup);
	IRON_EXPECT(!Battle.IsSideAI(0));
	IRON_EXPECT(Battle.IsSideAI(1));
	for (int Day = 1; Day <= 4 && !Battle.IsOver(); ++Day)
	{
		IRON_EXPECT(Battle.IsPlayerTurn());
		IRON_EXPECT_EQ(Battle.Day(), Day);
		IRON_EXPECT(!Battle.StepAI());
		Battle.EndTurn();
		int Steps = 0;
		Battle.ClearEvents();
		while (Battle.StepAI())
		{
			++Steps;
		}
		IRON_EXPECT(Steps >= 1 && Steps <= 9);
		IRON_EXPECT(Battle.IsOver() || Battle.IsPlayerTurn() || Battle.HasPendingChallenge());
		// AI moves are reported with their path ends.
		for (const FBattleEvent& Event : Battle.Events())
		{
			if (Event.Type == EBattleEventType::Move)
			{
				IRON_EXPECT(Battle.Unit(Event.Unit).Side == 1);
				IRON_EXPECT(Event.From != Event.To);
				IRON_EXPECT(Battle.InBounds(Event.To));
			}
		}
	}
	// Delegating hands the player's side to the AI.
	Battle.SetAutoControl(0, true);
	IRON_EXPECT(Battle.IsSideAI(0));
	IRON_EXPECT(Battle.IsOver() || Battle.StepAI());
	Battle.AutoResolve();
	IRON_EXPECT(Battle.IsOver());
}

IRON_TEST(BattleIsDeterministic)
{
	for (int Kind = 0; Kind < 2; ++Kind)
	{
		const FBattleSetup Setup = BattleTestUtil::MakeArmies(Kind == 0 ? EBattleKind::Field : EBattleKind::Siege, ETerrain::Forest, 1234, 22000, 18000);
		FBattle First;
		First.Setup(Setup);
		First.AutoResolve();
		FBattle Second;
		Second.Setup(Setup);
		Second.AutoResolve();
		IRON_EXPECT(First.Log() == Second.Log());
		const FBattleResult Result = IronSim::ResolveBattleAuto(Setup);
		IRON_EXPECT_EQ(Result.Winner, First.Result().Winner);
		IRON_EXPECT_EQ(Result.Days, First.Result().Days);
		IRON_EXPECT(Result.Summary == First.Result().Summary);
		IRON_EXPECT_EQ(Result.Units.size(), First.Units().size());
		for (size_t Index = 0; Index < Result.Units.size(); ++Index)
		{
			IRON_EXPECT_EQ(Result.Units[Index].Troops, First.Result().Units[Index].Troops);
			IRON_EXPECT(Result.Units[Index].Status == First.Result().Units[Index].Status);
			IRON_EXPECT_EQ(Result.Units[Index].Officer, First.Unit(static_cast<int>(Index)).Setup.Officer);
		}
	}
}

IRON_TEST(BattleAIUsesTacticsSensibly)
{
	// Fire against an enemy in the woods.
	{
		FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
		Setup.Sides[0].bPlayer = false;
		Setup.Sides[0].Units[0].Stats[2] = 95;
		Setup.Sides[1].Units[0].Stats[2] = 20;
		FBattle Battle;
		Battle.Setup(Setup);
		BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
		IRON_EXPECT(Battle.DebugPlaceUnit(0, {5, 5}));
		IRON_EXPECT(Battle.DebugPlaceUnit(1, {7, 5}));
		Battle.DebugSetTerrain({7, 5}, EHexTerrain::Forest);
		Battle.ClearEvents();
		int Steps = 0;
		while (Battle.ActiveSide() == 0 && Battle.StepAI() && Steps < 10)
		{
			++Steps;
		}
		bool bFire = false;
		for (const FBattleEvent& Event : Battle.Events())
		{
			bFire = bFire || ((Event.Type == EBattleEventType::Tactic || Event.Type == EBattleEventType::TacticFailed) && Event.Tactic == ETactic::Fire && Event.Unit == 0);
		}
		IRON_EXPECT(bFire);
	}
	// Rally when morale is low and no enemy is near.
	{
		FBattleSetup Setup = BattleTestUtil::MakeDuo(ETroopType::Infantry, ETroopType::Infantry);
		Setup.Sides[0].bPlayer = false;
		FBattle Battle;
		Battle.Setup(Setup);
		BattleTestUtil::Paint(Battle, EHexTerrain::Plain);
		IRON_EXPECT(Battle.DebugPlaceUnit(0, {1, 5}));
		IRON_EXPECT(Battle.DebugPlaceUnit(1, {15, 5}));
		Battle.DebugSetUnit(0, 5000, 18);
		Battle.ClearEvents();
		int Steps = 0;
		while (Battle.ActiveSide() == 0 && Battle.StepAI() && Steps < 10)
		{
			++Steps;
		}
		bool bRally = false;
		for (const FBattleEvent& Event : Battle.Events())
		{
			bRally = bRally || ((Event.Type == EBattleEventType::Tactic || Event.Type == EBattleEventType::TacticFailed) && Event.Tactic == ETactic::Rally);
		}
		IRON_EXPECT(bRally);
	}
	// Archers shoot from range; attackers batter the gate in sieges.
	int Ranged = 0;
	int ArcherMelee = 0;
	int GateHits = 0;
	int Sieges = 0;
	for (int Index = 0; Index < 12; ++Index)
	{
		const bool bSiege = Index % 2 == 1;
		FBattle Battle;
		Battle.Setup(BattleTestUtil::MakeArmies(bSiege ? EBattleKind::Siege : EBattleKind::Field, BattleTestUtil::AllTerrains[Index % 6], 900 + static_cast<uint64_t>(Index), 30000, 15000));
		Battle.AutoResolve();
		for (const FBattleEvent& Event : Battle.Events())
		{
			if (Event.Type == EBattleEventType::Attack && Battle.Unit(Event.Unit).Setup.Type == ETroopType::Archer)
			{
				(HexMath::Distance(Event.From, Event.To) == 2 ? Ranged : ArcherMelee) += 1;
			}
			GateHits += Event.Type == EBattleEventType::GateHit ? 1 : 0;
		}
		Sieges += bSiege ? 1 : 0;
	}
	IRON_EXPECT_MSG(Ranged > 3 * ArcherMelee, std::to_string(Ranged) + " ranged vs " + std::to_string(ArcherMelee) + " melee");
	IRON_EXPECT(GateHits >= Sieges * 2);
}

// -------------------------------------------------------------------------------------------------
// Balance (AI vs AI, all stats 60)
// -------------------------------------------------------------------------------------------------

IRON_TEST(BattleBalanceFieldTroopRatios)
{
	const double Double = BattleTestUtil::WinRate(EBattleKind::Field, 30000, 15000, 30);
	const double Even = BattleTestUtil::WinRate(EBattleKind::Field, 20000, 20000, 40);
	const double Half = BattleTestUtil::WinRate(EBattleKind::Field, 15000, 30000, 30);
	IRON_EXPECT_MSG(Double >= 0.8, std::to_string(Double));
	IRON_EXPECT_MSG(Even >= 0.25 && Even <= 0.75, std::to_string(Even));
	IRON_EXPECT_MSG(Half <= 0.2, std::to_string(Half));
}

IRON_TEST(BattleBalanceSiegesNeedSuperiorForce)
{
	const double Even = BattleTestUtil::WinRate(EBattleKind::Siege, 20000, 20000, 30);
	const double Double = BattleTestUtil::WinRate(EBattleKind::Siege, 40000, 20000, 30);
	IRON_EXPECT_MSG(Even <= 0.15, std::to_string(Even));
	IRON_EXPECT_MSG(Double >= 0.8, std::to_string(Double));
}

IRON_TEST(BattleCommandersStayOutOfHarmsWay)
{
	int Falls = 0;
	int CommanderFirst = 0;
	for (int Index = 0; Index < 24; ++Index)
	{
		FBattle Battle;
		Battle.Setup(BattleTestUtil::MakeArmies(EBattleKind::Field, BattleTestUtil::AllTerrains[Index % 6], 700 + static_cast<uint64_t>(Index), 20000 + 2000 * (Index % 3), 20000));
		Battle.AutoResolve();
		int FirstFall[2] = {-1, -1};
		for (const FBattleEvent& Event : Battle.Events())
		{
			const bool bFall = Event.Type == EBattleEventType::Routed || Event.Type == EBattleEventType::Destroyed || Event.Type == EBattleEventType::Captured;
			if (bFall && FirstFall[Battle.Unit(Event.Unit).Side] < 0)
			{
				FirstFall[Battle.Unit(Event.Unit).Side] = Event.Unit;
			}
		}
		for (const int Fallen : FirstFall)
		{
			if (Fallen >= 0)
			{
				++Falls;
				CommanderFirst += Battle.Unit(Fallen).bCommander ? 1 : 0;
			}
		}
	}
	IRON_EXPECT(Falls >= 24);
	IRON_EXPECT_MSG(CommanderFirst * 100 <= Falls * 15, std::to_string(CommanderFirst) + " of " + std::to_string(Falls));
}

IRON_TEST(BattleEmptySideLosesAtOnce)
{
	FBattleSetup Setup = BattleTestUtil::MakeArmies(EBattleKind::Siege, ETerrain::Plains, 5, 10000, 0, 2);
	FBattle Battle;
	Battle.Setup(Setup);
	IRON_EXPECT(Battle.IsOver());
	IRON_EXPECT_EQ(Battle.Result().Winner, 0);
	IRON_EXPECT_EQ(Battle.Result().Days, 1);
	IRON_EXPECT(!Battle.StepAI());

	FBattleSetup NoArmy = BattleTestUtil::MakeArmies(EBattleKind::Field, ETerrain::Plains, 5, 10000, 10000, 2);
	NoArmy.Sides[0].Units.clear();
	const FBattleResult Result = IronSim::ResolveBattleAuto(NoArmy);
	IRON_EXPECT(Result.bFinished);
	IRON_EXPECT_EQ(Result.Winner, 1);
}

IRON_TEST(BattleLoneCommandersStillFight)
{
	// A commander without an army cannot hide behind one: it has to engage to win.
	for (int Kind = 0; Kind < 2; ++Kind)
	{
		int Wins = 0;
		for (uint64_t Seed = 1; Seed <= 6; ++Seed)
		{
			const FBattleSetup Setup = BattleTestUtil::MakeArmies(Kind == 0 ? EBattleKind::Field : EBattleKind::Siege, BattleTestUtil::AllTerrains[Seed % 6], Seed, 9000, 2500, 1);
			const FBattleResult Result = IronSim::ResolveBattleAuto(Setup);
			Wins += Result.Winner == 0 ? 1 : 0;
			IRON_EXPECT(Result.Units[0].DamageDealt > 0);
		}
		IRON_EXPECT_MSG(Wins >= 5, std::to_string(Wins));
	}
}
