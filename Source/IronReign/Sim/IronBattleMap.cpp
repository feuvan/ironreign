#include "Sim/IronBattle.h"

#include <algorithm>
#include <limits>

// Tactical map generation (deterministic from ETerrain + seed) and unit deployment.

namespace IronSim
{
	namespace BattleMapDetail
	{
		bool IsBlocking(EHexTerrain Terrain)
		{
			return Terrain == EHexTerrain::Mountain || Terrain == EHexTerrain::Water || Terrain == EHexTerrain::Wall;
		}

		/** Small paint toolkit over the battle grid. */
		class FMapPainter
		{
		public:
			FMapPainter(std::vector<EHexTerrain>& InGrid, int InWidth, int InHeight, FRng& InRng)
				: Width(InWidth)
				, Height(InHeight)
				, Cells(InGrid)
				, Random(InRng)
			{
			}

			const int Width;
			const int Height;

			bool Inside(FHex Hex) const
			{
				return Hex.Col >= 0 && Hex.Row >= 0 && Hex.Col < Width && Hex.Row < Height;
			}

			EHexTerrain Get(FHex Hex) const
			{
				return Inside(Hex) ? Cells[static_cast<size_t>(Hex.Row * Width + Hex.Col)] : EHexTerrain::Mountain;
			}

			void Set(FHex Hex, EHexTerrain Terrain)
			{
				if (Inside(Hex))
				{
					Cells[static_cast<size_t>(Hex.Row * Width + Hex.Col)] = Terrain;
				}
			}

			FHex RandomHex(int MinCol, int MaxCol, int MinRow, int MaxRow)
			{
				const int Col = Random.Range(std::max(0, MinCol), std::min(Width - 1, MaxCol));
				const int Row = Random.Range(std::max(0, MinRow), std::min(Height - 1, MaxRow));
				return {Col, Row};
			}

			/** Paints Terrain over plain hexes within Radius of Center (the center always, others by chance). */
			void Blob(FHex Center, int Radius, EHexTerrain Terrain, int FillPercent, int MinCol, int MaxCol)
			{
				for (int Row = Center.Row - Radius - 1; Row <= Center.Row + Radius + 1; ++Row)
				{
					for (int Col = Center.Col - Radius; Col <= Center.Col + Radius; ++Col)
					{
						const FHex Hex = {Col, Row};
						if (!Inside(Hex) || Col < MinCol || Col > MaxCol || HexMath::Distance(Hex, Center) > Radius || Get(Hex) != EHexTerrain::Plain)
						{
							continue;
						}
						if (Hex == Center || Random.Chance(FillPercent))
						{
							Set(Hex, Terrain);
						}
					}
				}
			}

			/** A mostly north-south line of mountains. */
			void Ridge(FHex Start, int Length, int MinCol, int MaxCol)
			{
				FHex Current = Start;
				for (int Step = 0; Step < Length; ++Step)
				{
					if (Inside(Current) && Get(Current) != EHexTerrain::Water)
					{
						Set(Current, EHexTerrain::Mountain);
					}
					FHex Around[6];
					HexMath::Neighbors(Current, Around);
					// Index 2 is south, 5 is north.
					const int Pick = Random.Chance(60) ? (Random.Chance(50) ? 2 : 5) : Random.Range(0, 5);
					const FHex Next = Around[Pick];
					if (Inside(Next) && Next.Col >= MinCol && Next.Col <= MaxCol)
					{
						Current = Next;
					}
				}
			}

			/** A 6-connected chain from the top row to the bottom row: it splits the map left/right. */
			std::vector<FHex> River(int StartCol, int MinCol, int MaxCol)
			{
				std::vector<FHex> Chain;
				FHex Current = {ClampInt(StartCol, MinCol, MaxCol), 0};
				Chain.push_back(Current);
				int Guard = 0;
				while (Current.Row < Height - 1 && Guard < 400)
				{
					++Guard;
					const bool bOdd = (Current.Col & 1) != 0;
					const int Roll = Random.Range(0, 99);
					FHex Next = {Current.Col, Current.Row + 1};
					if (Roll >= 50)
					{
						const int Step = Roll < 75 ? 1 : -1;
						const FHex Side = {Current.Col + Step, bOdd ? Current.Row + 1 : Current.Row};
						if (Side.Col >= MinCol && Side.Col <= MaxCol)
						{
							Next = Side;
						}
					}
					Current = Next;
					Chain.push_back(Current);
				}
				return Chain;
			}

			/** Random shortest path (each step gets one hex closer to To). */
			std::vector<FHex> Path(FHex From, FHex To)
			{
				std::vector<FHex> Steps;
				Steps.push_back(From);
				FHex Current = From;
				int Guard = 0;
				while (Current != To && Guard < 200)
				{
					++Guard;
					FHex Around[6];
					HexMath::Neighbors(Current, Around);
					const int Here = HexMath::Distance(Current, To);
					FHex Options[6];
					int OptionCount = 0;
					for (const FHex& Next : Around)
					{
						if (Inside(Next) && HexMath::Distance(Next, To) == Here - 1)
						{
							Options[OptionCount++] = Next;
						}
					}
					if (OptionCount == 0)
					{
						break;
					}
					Current = Options[Random.Range(0, OptionCount - 1)];
					Steps.push_back(Current);
				}
				return Steps;
			}

			/** Lays a road along Steps: bridges over water, a pass through mountains. */
			void Road(const std::vector<FHex>& Steps)
			{
				for (const FHex& Hex : Steps)
				{
					switch (Get(Hex))
					{
					case EHexTerrain::Water:
					case EHexTerrain::Ford:
						Set(Hex, EHexTerrain::Bridge);
						break;
					case EHexTerrain::Plain:
					case EHexTerrain::Forest:
					case EHexTerrain::Hill:
					case EHexTerrain::Mountain:
					case EHexTerrain::Town:
						Set(Hex, EHexTerrain::Road);
						break;
					default:
						break;
					}
				}
			}

			/** Sea along the top or bottom edge between MinCol and MaxCol. */
			void Bay(bool bTop, int MinCol, int MaxCol, int MaxDepth)
			{
				int Depth = std::max(1, MaxDepth - 1);
				for (int Col = MinCol; Col <= MaxCol; ++Col)
				{
					const bool bEdge = Col == MinCol || Col == MaxCol;
					Depth = ClampInt(Depth + Random.Range(-1, 1), 1, MaxDepth);
					const int Use = bEdge ? 1 : Depth;
					for (int Offset = 0; Offset < Use; ++Offset)
					{
						Set({Col, bTop ? Offset : Height - 1 - Offset}, EHexTerrain::Water);
					}
				}
			}

			/** True when some hex of From reaches some hex of To over passable terrain (gates count as passable). */
			bool Connected(const std::vector<FHex>& From, const std::vector<FHex>& To) const
			{
				std::vector<uint8_t> Seen(static_cast<size_t>(Width * Height), 0);
				std::vector<FHex> Queue;
				for (const FHex& Hex : From)
				{
					if (Inside(Hex) && !IsBlocking(Get(Hex)) && !Seen[static_cast<size_t>(Hex.Row * Width + Hex.Col)])
					{
						Seen[static_cast<size_t>(Hex.Row * Width + Hex.Col)] = 1;
						Queue.push_back(Hex);
					}
				}
				for (size_t Head = 0; Head < Queue.size(); ++Head)
				{
					FHex Around[6];
					HexMath::Neighbors(Queue[Head], Around);
					for (const FHex& Next : Around)
					{
						if (!Inside(Next) || IsBlocking(Get(Next)) || Seen[static_cast<size_t>(Next.Row * Width + Next.Col)])
						{
							continue;
						}
						Seen[static_cast<size_t>(Next.Row * Width + Next.Col)] = 1;
						Queue.push_back(Next);
					}
				}
				for (const FHex& Hex : To)
				{
					if (Inside(Hex) && Seen[static_cast<size_t>(Hex.Row * Width + Hex.Col)])
					{
						return true;
					}
				}
				return false;
			}

			/** Opens a passage from From to To: water becomes a ford, mountains become hills. */
			void Carve(FHex From, FHex To)
			{
				for (const FHex& Hex : Path(From, To))
				{
					const EHexTerrain Terrain = Get(Hex);
					if (Terrain == EHexTerrain::Water)
					{
						Set(Hex, EHexTerrain::Ford);
					}
					else if (Terrain == EHexTerrain::Mountain)
					{
						Set(Hex, EHexTerrain::Hill);
					}
				}
			}

			/** Every blocking hex in the column range becomes plain. */
			void ClearColumns(int MinCol, int MaxCol)
			{
				for (int Col = MinCol; Col <= MaxCol; ++Col)
				{
					for (int Row = 0; Row < Height; ++Row)
					{
						if (IsBlocking(Get({Col, Row})))
						{
							Set({Col, Row}, EHexTerrain::Plain);
						}
					}
				}
			}

			std::vector<FHex> ColumnHexes(int MinCol, int MaxCol) const
			{
				std::vector<FHex> Hexes;
				for (int Col = MinCol; Col <= MaxCol; ++Col)
				{
					for (int Row = 0; Row < Height; ++Row)
					{
						Hexes.push_back({Col, Row});
					}
				}
				return Hexes;
			}

			void Scatter(int Count, int MinRadius, int MaxRadius, EHexTerrain Terrain, int FillPercent, int MinCol, int MaxCol)
			{
				for (int Index = 0; Index < Count; ++Index)
				{
					const FHex Center = RandomHex(MinCol, MaxCol, 0, Height - 1);
					const int Radius = Random.Range(MinRadius, MaxRadius);
					Blob(Center, Radius, Terrain, FillPercent, MinCol, MaxCol);
				}
			}

			void Ridges(int Count, int MinLength, int MaxLength, int MinCol, int MaxCol)
			{
				for (int Index = 0; Index < Count; ++Index)
				{
					const FHex Start = RandomHex(MinCol, MaxCol, 1, Height - 2);
					Ridge(Start, Random.Range(MinLength, MaxLength), MinCol, MaxCol);
				}
			}

			/** Turns two or three river hexes far from roads/bridges into fords. */
			void Fords(const std::vector<FHex>& Chain, int Count)
			{
				std::vector<FHex> Crossings;
				for (const FHex& Hex : Chain)
				{
					if (Get(Hex) == EHexTerrain::Bridge)
					{
						Crossings.push_back(Hex);
					}
				}
				int Placed = 0;
				for (int Attempt = 0; Attempt < 40 && Placed < Count && !Chain.empty(); ++Attempt)
				{
					const FHex Hex = Chain[static_cast<size_t>(Random.Range(0, static_cast<int>(Chain.size()) - 1))];
					if (Get(Hex) != EHexTerrain::Water)
					{
						continue;
					}
					bool bTooClose = false;
					for (const FHex& Other : Crossings)
					{
						bTooClose = bTooClose || HexMath::Distance(Other, Hex) < 3;
					}
					if (bTooClose)
					{
						continue;
					}
					Set(Hex, EHexTerrain::Ford);
					Crossings.push_back(Hex);
					++Placed;
				}
			}

			FRng& Rand()
			{
				return Random;
			}

		private:
			std::vector<EHexTerrain>& Cells;
			FRng& Random;
		};

		/** Neighbor of a wall hex on the outer (west) or inner (east) side; in odd-q, (Col +- 1, Row) is always adjacent. */
		FHex WallNeighbor(FHex WallHex, bool bOutside)
		{
			return {WallHex.Col + (bOutside ? -1 : 1), WallHex.Row};
		}

		void PaintField(FMapPainter& Painter, ETerrain Terrain)
		{
			FRng& Random = Painter.Rand();
			const int MapWidth = Painter.Width;
			const int MapHeight = Painter.Height;
			const int Mid = MapHeight / 2;
			// Impassable features stay out of the deployment columns (0-2 and the last three).
			const int MinCol = 3;
			const int MaxCol = MapWidth - 4;
			std::vector<FHex> RiverChain;
			switch (Terrain)
			{
			case ETerrain::Plains:
				Painter.Scatter(Random.Range(2, 3), 0, 1, EHexTerrain::Forest, 60, 1, MapWidth - 2);
				Painter.Scatter(Random.Range(1, 2), 0, 1, EHexTerrain::Hill, 50, 1, MapWidth - 2);
				break;
			case ETerrain::Forest:
				Painter.Scatter(Random.Range(6, 8), 1, 2, EHexTerrain::Forest, 70, 0, MapWidth - 1);
				Painter.Scatter(1, 0, 1, EHexTerrain::Hill, 50, 1, MapWidth - 2);
				break;
			case ETerrain::Hills:
				Painter.Ridges(2, 2, 3, MinCol, MaxCol);
				Painter.Scatter(Random.Range(5, 6), 1, 2, EHexTerrain::Hill, 65, 0, MapWidth - 1);
				Painter.Scatter(2, 0, 1, EHexTerrain::Forest, 60, 1, MapWidth - 2);
				break;
			case ETerrain::River:
				Painter.Scatter(Random.Range(2, 3), 0, 1, EHexTerrain::Forest, 60, 1, MapWidth - 2);
				Painter.Scatter(1, 0, 1, EHexTerrain::Hill, 50, 1, MapWidth - 2);
				RiverChain = Painter.River(MapWidth / 2 - 1 + Random.Range(0, 1), MinCol + 2, MaxCol - 2);
				for (const FHex& Hex : RiverChain)
				{
					Painter.Set(Hex, EHexTerrain::Water);
				}
				break;
			case ETerrain::Mountains:
				Painter.Ridges(Random.Range(3, 4), 3, 5, MinCol, MaxCol);
				Painter.Scatter(4, 0, 1, EHexTerrain::Hill, 60, 1, MapWidth - 2);
				Painter.Scatter(1, 0, 1, EHexTerrain::Forest, 60, 1, MapWidth - 2);
				break;
			case ETerrain::Coast:
				Painter.Bay(Random.Chance(50), MinCol, MaxCol, 3);
				Painter.Scatter(2, 0, 1, EHexTerrain::Forest, 60, 1, MapWidth - 2);
				Painter.Scatter(2, 0, 1, EHexTerrain::Hill, 50, 1, MapWidth - 2);
				break;
			}

			// A road crosses the field (bridging the river, cutting a pass through mountains).
			const FHex RoadStart = {0, Mid + Random.Range(-1, 1)};
			const FHex RoadEnd = {MapWidth - 1, Mid + Random.Range(-2, 2)};
			Painter.Road(Painter.Path(RoadStart, RoadEnd));
			if (!RiverChain.empty())
			{
				Painter.Fords(RiverChain, Random.Range(2, 3));
			}

			Painter.ClearColumns(0, 2);
			Painter.ClearColumns(MapWidth - 3, MapWidth - 1);
			if (!Painter.Connected(Painter.ColumnHexes(0, 2), Painter.ColumnHexes(MapWidth - 3, MapWidth - 1)))
			{
				Painter.Carve({2, Mid}, {MapWidth - 3, Mid});
			}
		}

		struct FSiegeLayout
		{
			int WallCol = -1;
			FHex Gates[2] = {{-1, -1}, {-1, -1}};
			int GateCount = 0;
			FHex Castle = {-1, -1};
		};

		FSiegeLayout PaintSiege(FMapPainter& Painter, ETerrain Terrain, int CitySize)
		{
			FRng& Random = Painter.Rand();
			const int MapWidth = Painter.Width;
			const int MapHeight = Painter.Height;
			const int Mid = MapHeight / 2;
			FSiegeLayout Layout;
			Layout.WallCol = MapWidth * 2 / 3;
			Layout.GateCount = CitySize >= 3 ? 2 : 1;
			if (Layout.GateCount == 1)
			{
				Layout.Gates[0] = {Layout.WallCol, Mid};
			}
			else
			{
				Layout.Gates[0] = {Layout.WallCol, MapHeight / 3};
				Layout.Gates[1] = {Layout.WallCol, MapHeight - 1 - MapHeight / 3};
			}
			Layout.Castle = {MapWidth - 2, Mid};

			// Outside the walls: lighter features, keeping the approach to the wall open.
			const int MinCol = 3;
			const int MaxCol = Layout.WallCol - 3;
			std::vector<FHex> RiverChain;
			switch (Terrain)
			{
			case ETerrain::Plains:
				Painter.Scatter(2, 0, 1, EHexTerrain::Forest, 60, 1, MaxCol);
				Painter.Scatter(1, 0, 1, EHexTerrain::Hill, 50, 1, MaxCol);
				break;
			case ETerrain::Forest:
				Painter.Scatter(4, 1, 2, EHexTerrain::Forest, 65, 0, Layout.WallCol - 2);
				break;
			case ETerrain::Hills:
				Painter.Ridges(1, 2, 2, MinCol, MaxCol);
				Painter.Scatter(3, 1, 1, EHexTerrain::Hill, 60, 0, Layout.WallCol - 2);
				break;
			case ETerrain::River:
				Painter.Scatter(2, 0, 1, EHexTerrain::Forest, 60, 1, MaxCol);
				RiverChain = Painter.River((4 + MaxCol) / 2, 4, MaxCol);
				for (const FHex& Hex : RiverChain)
				{
					Painter.Set(Hex, EHexTerrain::Water);
				}
				break;
			case ETerrain::Mountains:
				Painter.Ridges(2, 2, 3, MinCol, MaxCol);
				Painter.Scatter(2, 0, 1, EHexTerrain::Hill, 60, 1, MaxCol);
				break;
			case ETerrain::Coast:
				Painter.Bay(true, MinCol, Layout.WallCol - 2, 2);
				Painter.Scatter(1, 0, 1, EHexTerrain::Forest, 60, 1, MaxCol);
				break;
			}

			// The wall, its gates, the town and the castle.
			for (int Row = 0; Row < MapHeight; ++Row)
			{
				Painter.Set({Layout.WallCol, Row}, EHexTerrain::Wall);
				for (int Col = Layout.WallCol + 1; Col < MapWidth; ++Col)
				{
					Painter.Set({Col, Row}, Random.Chance(10) ? EHexTerrain::Plain : EHexTerrain::Town);
				}
			}
			for (int Index = 0; Index < Layout.GateCount; ++Index)
			{
				Painter.Set(Layout.Gates[Index], EHexTerrain::Gate);
			}
			Painter.Set(Layout.Castle, EHexTerrain::Castle);
			for (int Index = 0; Index < Layout.GateCount; ++Index)
			{
				const FHex Inner = WallNeighbor(Layout.Gates[Index], false);
				Painter.Road(Painter.Path(Inner, Layout.Castle));
			}

			// Roads from the west edge to every gate.
			const FHex RoadStart = {0, Mid + Random.Range(-1, 1)};
			for (int Index = 0; Index < Layout.GateCount; ++Index)
			{
				const FHex Outer = WallNeighbor(Layout.Gates[Index], true);
				Painter.Road(Painter.Path(RoadStart, Outer));
			}
			if (!RiverChain.empty())
			{
				Painter.Fords(RiverChain, 2);
			}

			// Keep the ground in front of the wall and the attacker's deployment zone open.
			Painter.ClearColumns(Layout.WallCol - 1, Layout.WallCol - 1);
			Painter.ClearColumns(0, 2);
			for (int Index = 0; Index < Layout.GateCount; ++Index)
			{
				const FHex Outer = WallNeighbor(Layout.Gates[Index], true);
				if (!Painter.Connected(Painter.ColumnHexes(0, 2), {Outer}))
				{
					Painter.Carve({2, Outer.Row}, Outer);
				}
			}
			return Layout;
		}

		/** Higher is better. Hexes outside the side's zone get a large penalty so overflow spreads inward. */
		int DeployScore(const FBattleUnit& Placing, FHex Hex, int MapWidth, int MapHeight, EBattleKind Kind, int WallCol, const FHex* Gates, int GateCount, FHex Castle)
		{
			const int Mid = MapHeight / 2;
			const int RowOffset = std::abs(Hex.Row - Mid);
			if (Kind == EBattleKind::Siege && Placing.Side == 1)
			{
				if (Hex.Col <= WallCol)
				{
					return -100000 - HexMath::Distance(Hex, Castle);
				}
				int GateDistance = 1000;
				int GateRowOffset = 1000;
				for (int Index = 0; Index < GateCount; ++Index)
				{
					GateDistance = std::min(GateDistance, HexMath::Distance(Hex, Gates[Index]));
					GateRowOffset = std::min(GateRowOffset, std::abs(Hex.Row - Gates[Index].Row));
				}
				if (Placing.bCommander)
				{
					return Hex == Castle ? 1000 : -10 * HexMath::Distance(Hex, Castle);
				}
				if (Placing.Setup.Type == ETroopType::Archer)
				{
					// On the wall walk near the gates, within bow range of the approach.
					return -20 * (Hex.Col - (WallCol + 1)) - 4 * GateRowOffset;
				}
				return -10 * GateDistance - (Hex == Castle ? 50 : 0);
			}

			const int Depth = Placing.Side == 0 ? Hex.Col : MapWidth - 1 - Hex.Col;
			const int ZonePenalty = Depth > 2 ? (Depth - 2) * 100 : 0;
			if (Placing.bCommander)
			{
				return -ZonePenalty - 10 * Depth - 5 * RowOffset;
			}
			if (Placing.Setup.Type == ETroopType::Archer)
			{
				return -ZonePenalty - 10 * std::abs(Depth - 1) - 3 * RowOffset;
			}
			if (Placing.Setup.Type == ETroopType::Cavalry)
			{
				return -ZonePenalty - 10 * std::abs(Depth - 2) - 3 * std::abs(RowOffset - 3);
			}
			return -ZonePenalty - 10 * std::abs(Depth - 2) - 3 * RowOffset;
		}
	}

	void FBattle::GenerateMap()
	{
		if (Config.Kind == EBattleKind::Siege)
		{
			GridCols = Config.CitySize >= 3 ? 18 : (Config.CitySize == 2 ? 17 : 16);
			GridRows = Config.CitySize >= 3 ? 12 : 11;
		}
		else
		{
			GridCols = 16;
			GridRows = 11;
		}
		Grid.assign(static_cast<size_t>(GridCols * GridRows), EHexTerrain::Plain);
		Burning.assign(static_cast<size_t>(GridCols * GridRows), 0);

		// The map depends only on the seed, the terrain, the battle kind and the city size.
		uint64_t MapSeed = Config.Seed * 0x9E3779B97F4A7C15ull;
		MapSeed ^= static_cast<uint64_t>(Config.Terrain) << 40;
		MapSeed ^= static_cast<uint64_t>(Config.Kind) << 48;
		MapSeed ^= static_cast<uint64_t>(Config.CitySize) << 56;
		FRng MapRng(MapSeed ^ 0x6A09E667F3BCC909ull);
		MapRng.Next();
		BattleMapDetail::FMapPainter Painter(Grid, GridCols, GridRows, MapRng);

		WallCol = -1;
		Gate = {-1, -1};
		SecondGate = {-1, -1};
		Castle = {-1, -1};
		GateHitPoints = 0;
		GateMaxHitPoints = 0;
		SecondGateHitPoints = 0;
		if (Config.Kind == EBattleKind::Siege)
		{
			const BattleMapDetail::FSiegeLayout Layout = BattleMapDetail::PaintSiege(Painter, Config.Terrain, Config.CitySize);
			WallCol = Layout.WallCol;
			Gate = Layout.Gates[0];
			if (Layout.GateCount > 1)
			{
				SecondGate = Layout.Gates[1];
			}
			Castle = Layout.Castle;
			GateMaxHitPoints = Config.GateHp;
			GateHitPoints = GateMaxHitPoints;
			SecondGateHitPoints = Layout.GateCount > 1 ? GateMaxHitPoints : 0;
		}
		else
		{
			BattleMapDetail::PaintField(Painter, Config.Terrain);
		}
	}

	void FBattle::DeployUnits()
	{
		const FHex Gates[2] = {Gate, SecondGate};
		const int GateTotal = GateCount();
		for (int SideIndex = 0; SideIndex < 2; ++SideIndex)
		{
			for (FBattleUnit& Placing : BattleUnits)
			{
				if (Placing.Side != SideIndex || !Placing.IsActive())
				{
					continue;
				}
				FHex BestHex = {-1, -1};
				int BestScore = std::numeric_limits<int>::min();
				for (int Row = 0; Row < GridRows; ++Row)
				{
					for (int Col = 0; Col < GridCols; ++Col)
					{
						const FHex Hex = {Col, Row};
						if (TerrainEnterCost(Hex, Placing.Setup.Type, Placing.Side) < 0 || TerrainAt(Hex) == EHexTerrain::Gate || UnitAt(Hex) >= 0)
						{
							continue;
						}
						const int Score = BattleMapDetail::DeployScore(Placing, Hex, GridCols, GridRows, Config.Kind, WallCol, Gates, GateTotal, Castle);
						if (Score > BestScore)
						{
							BestScore = Score;
							BestHex = Hex;
						}
					}
				}
				if (!InBounds(BestHex))
				{
					// No room at all: the unit cannot take the field.
					Placing.Status = EUnitStatus::Routed;
					continue;
				}
				Placing.Pos = BestHex;
				Placing.TurnStart = BestHex;
			}
		}
	}
}
