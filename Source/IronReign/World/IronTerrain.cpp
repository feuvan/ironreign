#include "World/IronTerrain.h"

#include "Sim/IronJson.h"
#include "World/IronAssetManifest.h"
#include "World/IronWorldAssets.h"
#include "World/IronWorldMath.h"

#include "Async/Async.h"
#include "Components/HierarchicalInstancedStaticMeshComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "ProceduralMeshComponent.h"

#include <string>

/** Output of the terrain worker; turned into components on the game thread. */
struct FIronTerrainBuildResult
{
	bool bSucceeded = false;
	FString Error;
	FIronHeightField Field;
	/** The imported SM_Terrain_* chunks match Field (same Height.png and grid): no sections were built. */
	bool bStaticChunks = false;
	/** One mesh section per chunk, row-major (8 x 5); empty when bStaticChunks. */
	TArray<FProcMeshSection> Sections;
	/** Instance transforms per tree type: pine, broad, bamboo. */
	TArray<FTransform> Trees[3];
	int32 TreesSkipped = 0;
};

namespace IronTerrainDetail
{
	constexpr int32 ChunksX = 8;
	constexpr int32 ChunksY = 5;
	/** Chunk components registered per frame (each creates its render proxy on the game thread). */
	constexpr int32 SectionsPerTick = 4;
	constexpr int32 StaticChunksPerTick = 8;
	/** The sea reaches this far beyond the map so the horizon never shows its edge. */
	constexpr double SeaMarginM = 8000.0;
	constexpr int32 SeaCells = 24;
	constexpr double DetailTileM = 50.0;
	constexpr double WaterTileM = 100.0;
	constexpr int32 TreeTypeCount = 3;
	const TCHAR* const TreeModels[TreeTypeCount] = {TEXT("Tree_Pine"), TEXT("Tree_Broad"), TEXT("Tree_Bamboo")};
	/** Trees fade out far beyond the farthest camera position (cm). */
	constexpr int32 TreeCullStartCm = 450000;
	constexpr int32 TreeCullEndCm = 560000;

	struct FBuildRequest
	{
		TSharedPtr<IImageWrapper> PngWrapper;
		FString TreesJsonPath;
		/** Vertex stride of the runtime (procedural) mesh. */
		int32 Stride = 2;
		double TreeScales[TreeTypeCount] = {1.0, 1.0, 1.0};
		/** Imported SM_Terrain_* chunks are loaded: their grid stride and the Height.png identity they were cut from. */
		int32 StaticChunkStride = 0;
		FString StaticChunkHash;
		/** Tree-free discs: X, Y = map metres, Z = radius metres. */
		TArray<FVector> TreeExclusions;
	};

	FString TerrainDir()
	{
		return IronWorld::Art3DDir() / TEXT("Terrain");
	}

	/** "Terrain_3_1": the model name of an imported chunk (/Game/IronReign/Models/SM_Terrain_3_1). */
	FString StaticChunkName(int32 ChunkX, int32 ChunkY)
	{
		return FString::Printf(TEXT("Terrain_%d_%d"), ChunkX, ChunkY);
	}

	/** True when the map point (metres) lies inside one of the discs (X, Y = centre in map metres, Z = radius). */
	bool InsideAnyDisc(const TArray<FVector>& DiscsM, double XM, double YM)
	{
		for (const FVector& Disc : DiscsM)
		{
			if (FMath::Square(XM - Disc.X) + FMath::Square(YM - Disc.Y) < FMath::Square(Disc.Z))
			{
				return true;
			}
		}
		return false;
	}

	bool ParseInfo(const IronSim::FJson& Json, FIronTerrainInfo& Out)
	{
		if (!Json.IsObject())
		{
			return false;
		}
		Out.MapWidthM = Json.GetNumber("width", Out.MapWidthM);
		Out.MapHeightM = Json.GetNumber("height", Out.MapHeightM);
		Out.GridStepM = Json.GetNumber("gridStep", Out.GridStepM);
		Out.MinElevationM = Json.GetNumber("minHeight", Out.MinElevationM);
		Out.MaxElevationM = Json.GetNumber("maxHeight", Out.MaxElevationM);
		Out.SeaLevelM = Json.GetNumber("seaLevel", Out.SeaLevelM);
		return Out.MapWidthM > 0.0 && Out.MapHeightM > 0.0 && Out.GridStepM > 0.0 && Out.MaxElevationM > Out.MinElevationM;
	}

	/** Smooth vertex normal from central differences on the mesh grid, and the +X tangent orthogonal to it. */
	FVector NormalAt(const FIronHeightField& Field, int32 VX, int32 VY, FVector& OutTangent)
	{
		const int32 LastColumn = Field.MeshColumns.Num() - 1;
		const int32 LastRow = Field.MeshRows.Num() - 1;
		const int32 PixelX = Field.MeshColumns[VX];
		const int32 PixelY = Field.MeshRows[VY];
		const int32 WestX = Field.MeshColumns[FMath::Max(VX - 1, 0)];
		const int32 EastX = Field.MeshColumns[FMath::Min(VX + 1, LastColumn)];
		const int32 NorthY = Field.MeshRows[FMath::Max(VY - 1, 0)];
		const int32 SouthY = Field.MeshRows[FMath::Min(VY + 1, LastRow)];
		const double SpanX = static_cast<double>(FMath::Max(1, EastX - WestX)) * Field.Info.GridStepM;
		const double SpanY = static_cast<double>(FMath::Max(1, SouthY - NorthY)) * Field.Info.GridStepM;
		const double SlopeX = (static_cast<double>(Field.At(EastX, PixelY)) - static_cast<double>(Field.At(WestX, PixelY))) / SpanX;
		const double SlopeY = (static_cast<double>(Field.At(PixelX, SouthY)) - static_cast<double>(Field.At(PixelX, NorthY))) / SpanY;

		const FVector Normal = FVector(-SlopeX, -SlopeY, 1.0).GetSafeNormal();
		const FVector AlongX(1.0, 0.0, SlopeX);
		const FVector Tangent = (AlongX - Normal * FVector::DotProduct(AlongX, Normal)).GetSafeNormal();
		OutTangent = Tangent.IsNearlyZero() ? FVector(1.0, 0.0, 0.0) : Tangent;
		return Normal;
	}

	/** Two triangles per cell (A = top-left, B = top-right, C = bottom-right, D = bottom-left): A D B and B D C. */
	void AddGridIndices(int32 VerticesPerRow, int32 Rows, TArray<uint32>& OutIndices)
	{
		OutIndices.Reset((VerticesPerRow - 1) * (Rows - 1) * 6);
		for (int32 Row = 0; Row < Rows - 1; ++Row)
		{
			for (int32 Column = 0; Column < VerticesPerRow - 1; ++Column)
			{
				const uint32 A = static_cast<uint32>(Row * VerticesPerRow + Column);
				const uint32 B = A + 1;
				const uint32 D = A + static_cast<uint32>(VerticesPerRow);
				const uint32 C = D + 1;
				OutIndices.Add(A);
				OutIndices.Add(D);
				OutIndices.Add(B);
				OutIndices.Add(B);
				OutIndices.Add(D);
				OutIndices.Add(C);
			}
		}
	}

	/** Mesh section for the vertex range [FirstX, LastX] x [FirstY, LastY] (inclusive: neighbours share edges). */
	void BuildChunk(const FIronHeightField& Field, int32 FirstX, int32 LastX, int32 FirstY, int32 LastY, FProcMeshSection& Out)
	{
		const int32 Width = LastX - FirstX + 1;
		const int32 Height = LastY - FirstY + 1;
		const double Step = Field.Info.GridStepM;
		Out.ProcVertexBuffer.Reset(Width * Height);
		Out.SectionLocalBox = FBox(ForceInit);
		for (int32 VY = FirstY; VY <= LastY; ++VY)
		{
			for (int32 VX = FirstX; VX <= LastX; ++VX)
			{
				const int32 PixelX = Field.MeshColumns[VX];
				const int32 PixelY = Field.MeshRows[VY];
				const double XM = static_cast<double>(PixelX) * Step;
				const double YM = static_cast<double>(PixelY) * Step;
				FVector Tangent;
				FProcMeshVertex& Vertex = Out.ProcVertexBuffer.AddDefaulted_GetRef();
				Vertex.Position = IronWorld::MapToWorld(FVector2D(XM, YM), static_cast<double>(Field.At(PixelX, PixelY)));
				Vertex.Normal = NormalAt(Field, VX, VY, Tangent);
				Vertex.Tangent = FProcMeshTangent(Tangent, false);
				Vertex.Color = FColor::White;
				Vertex.UV0 = FVector2D(XM / Field.Info.MapWidthM, YM / Field.Info.MapHeightM);
				Vertex.UV1 = FVector2D(XM / DetailTileM, YM / DetailTileM);
				Out.SectionLocalBox += Vertex.Position;
			}
		}
		AddGridIndices(Width, Height, Out.ProcIndexBuffer);
		Out.bEnableCollision = false;
		Out.bSectionVisible = true;
	}

	/** Flat grid at ZM (sea, sea floor). UV0 = metres / WaterTileM, UV1 = map UV (x / width, y / height). */
	void BuildFlatGrid(const FVector2D& MinM, const FVector2D& MaxM, double ZM, int32 Cells, const FIronTerrainInfo& Info, FProcMeshSection& Out)
	{
		const int32 Side = Cells + 1;
		Out.ProcVertexBuffer.Reset(Side * Side);
		Out.SectionLocalBox = FBox(ForceInit);
		for (int32 Row = 0; Row < Side; ++Row)
		{
			for (int32 Column = 0; Column < Side; ++Column)
			{
				const double XM = FMath::Lerp(MinM.X, MaxM.X, static_cast<double>(Column) / static_cast<double>(Cells));
				const double YM = FMath::Lerp(MinM.Y, MaxM.Y, static_cast<double>(Row) / static_cast<double>(Cells));
				FProcMeshVertex& Vertex = Out.ProcVertexBuffer.AddDefaulted_GetRef();
				Vertex.Position = IronWorld::MapToWorld(FVector2D(XM, YM), ZM);
				Vertex.Normal = FVector(0.0, 0.0, 1.0);
				Vertex.Tangent = FProcMeshTangent(FVector(1.0, 0.0, 0.0), false);
				Vertex.Color = FColor::White;
				Vertex.UV0 = FVector2D(XM / WaterTileM, YM / WaterTileM);
				Vertex.UV1 = FVector2D(XM / Info.MapWidthM, YM / Info.MapHeightM);
				Out.SectionLocalBox += Vertex.Position;
			}
		}
		AddGridIndices(Side, Side, Out.ProcIndexBuffer);
		Out.bEnableCollision = false;
		Out.bSectionVisible = true;
	}

	/** Trees.json: [{"t":"pine|broad|bamboo","x":m,"y":m,"s":scale,"r":yawDegrees}, ...]. */
	void BuildTrees(const FBuildRequest& Request, FIronTerrainBuildResult& Result)
	{
		if (Request.TreesJsonPath.IsEmpty() || !FPaths::FileExists(Request.TreesJsonPath))
		{
			return;
		}
		IronSim::FJson Root;
		FString Error;
		if (!IronWorld::ReadJsonFile(Request.TreesJsonPath, Root, Error))
		{
			UE_LOG(LogIronWorld, Warning, TEXT("Trees.json: %s"), *Error);
			return;
		}
		const IronSim::FJson& List = Root.IsArray() ? Root : Root.Get("trees");
		if (!List.IsArray())
		{
			return;
		}
		const FIronHeightField& Field = Result.Field;
		const FIronTerrainInfo& Info = Field.Info;
		for (const IronSim::FJson& Item : List.Items())
		{
			const std::string Kind = Item.GetString("t", "broad");
			const int32 Type = Kind == "pine" ? 0 : (Kind == "bamboo" ? 2 : 1);
			const double XM = Item.GetNumber("x", -1.0);
			const double YM = Item.GetNumber("y", -1.0);
			if (XM < 0.0 || YM < 0.0 || XM > Info.MapWidthM || YM > Info.MapHeightM)
			{
				++Result.TreesSkipped;
				continue;
			}
			// Trees.json keeps 25 m off a city point; the city models reach much farther.
			if (InsideAnyDisc(Request.TreeExclusions, XM, YM))
			{
				++Result.TreesSkipped;
				continue;
			}
			const double Ground = static_cast<double>(Field.Sample(XM, YM));
			if (Ground < Info.SeaLevelM + 0.3)
			{
				++Result.TreesSkipped;
				continue;
			}
			const double Scale = FMath::Max(0.05, Item.GetNumber("s", 1.0)) * Request.TreeScales[Type];
			const double Yaw = Item.GetNumber("r", 0.0);
			// Sink the trunk a little so trees on slopes do not float.
			const FVector Location = IronWorld::MapToWorld(FVector2D(XM, YM), Ground - 0.4 * Scale);
			Result.Trees[Type].Add(FTransform(FRotator(0.0, Yaw, 0.0), Location, FVector(Scale)));
		}
	}

	TSharedPtr<FIronTerrainBuildResult> RunBuild(const FBuildRequest& Request)
	{
		TSharedPtr<FIronTerrainBuildResult> Result = MakeShared<FIronTerrainBuildResult>();
		if (!FIronHeightField::Load(Request.PngWrapper, Result->Field, Result->Error))
		{
			return Result;
		}
		FIronHeightField& Field = Result->Field;
		if (Request.StaticChunkStride > 0)
		{
			// The imported chunks stand in for the runtime mesh only when they were cut from this very heightmap on a
			// grid of at least 8 x 5 cells: then the samples below follow their triangles exactly.
			Field.BuildMeshGrid(Request.StaticChunkStride);
			const bool bSameSource = Request.StaticChunkHash == Field.SourceHash;
			const bool bFullGrid = Field.MeshColumns.Num() - 1 >= ChunksX && Field.MeshRows.Num() - 1 >= ChunksY;
			Result->bStaticChunks = bSameSource && bFullGrid;
			if (!Result->bStaticChunks)
			{
				UE_LOG(LogIronWorld, Warning, TEXT("SM_Terrain_* were imported from another Height.png (%s, now %s); the terrain uses the runtime mesh, which Lumen only sees on screen. Re-run the asset import."),
					*Request.StaticChunkHash, *Field.SourceHash);
			}
		}
		if (!Result->bStaticChunks)
		{
			Field.BuildMeshGrid(Request.Stride);
			const int32 CellsX = Field.MeshColumns.Num() - 1;
			const int32 CellsY = Field.MeshRows.Num() - 1;
			const int32 CountX = FMath::Clamp(ChunksX, 1, CellsX);
			const int32 CountY = FMath::Clamp(ChunksY, 1, CellsY);
			Result->Sections.Reserve(CountX * CountY);
			for (int32 ChunkY = 0; ChunkY < CountY; ++ChunkY)
			{
				for (int32 ChunkX = 0; ChunkX < CountX; ++ChunkX)
				{
					BuildChunk(Field, CellsX * ChunkX / CountX, CellsX * (ChunkX + 1) / CountX, CellsY * ChunkY / CountY, CellsY * (ChunkY + 1) / CountY, Result->Sections.AddDefaulted_GetRef());
				}
			}
		}
		// After the final mesh grid: trees stand on the triangles that are drawn.
		BuildTrees(Request, *Result);
		Result->bSucceeded = true;
		return Result;
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// FIronHeightField
// ---------------------------------------------------------------------------------------------------------------------

bool FIronHeightField::IsValid() const
{
	return SamplesX >= 2 && SamplesY >= 2 && Heights.Num() == SamplesX * SamplesY && MeshColumns.Num() >= 2 && MeshRows.Num() >= 2 && Info.GridStepM > 0.0;
}

void FIronHeightField::BuildMeshGrid(int32 InStride)
{
	Stride = FMath::Max(1, InStride);
	MeshColumns.Reset();
	MeshRows.Reset();
	if (SamplesX < 2 || SamplesY < 2)
	{
		return;
	}
	for (int32 Column = 0; Column < SamplesX - 1; Column += Stride)
	{
		MeshColumns.Add(Column);
	}
	MeshColumns.Add(SamplesX - 1);
	for (int32 Row = 0; Row < SamplesY - 1; Row += Stride)
	{
		MeshRows.Add(Row);
	}
	MeshRows.Add(SamplesY - 1);
}

float FIronHeightField::Sample(double XM, double YM) const
{
	if (!IsValid())
	{
		return static_cast<float>(Info.SeaLevelM);
	}
	const double PixelX = FMath::Clamp(XM / Info.GridStepM, 0.0, static_cast<double>(SamplesX - 1));
	const double PixelY = FMath::Clamp(YM / Info.GridStepM, 0.0, static_cast<double>(SamplesY - 1));
	// Mesh columns are multiples of Stride except the last one, so the cell index is a plain division.
	const int32 CellX = FMath::Clamp(FMath::FloorToInt32(PixelX / static_cast<double>(Stride)), 0, MeshColumns.Num() - 2);
	const int32 CellY = FMath::Clamp(FMath::FloorToInt32(PixelY / static_cast<double>(Stride)), 0, MeshRows.Num() - 2);
	const int32 X0 = MeshColumns[CellX];
	const int32 X1 = MeshColumns[CellX + 1];
	const int32 Y0 = MeshRows[CellY];
	const int32 Y1 = MeshRows[CellY + 1];
	const double FracX = FMath::Clamp((PixelX - static_cast<double>(X0)) / static_cast<double>(FMath::Max(1, X1 - X0)), 0.0, 1.0);
	const double FracY = FMath::Clamp((PixelY - static_cast<double>(Y0)) / static_cast<double>(FMath::Max(1, Y1 - Y0)), 0.0, 1.0);
	const double HeightA = At(X0, Y0);
	const double HeightB = At(X1, Y0);
	const double HeightC = At(X1, Y1);
	const double HeightD = At(X0, Y1);
	// Same split as the mesh: triangle A D B above the B-D diagonal, B D C below it.
	const double Result = FracX + FracY <= 1.0
		? HeightA + FracX * (HeightB - HeightA) + FracY * (HeightD - HeightA)
		: HeightC + (1.0 - FracX) * (HeightD - HeightC) + (1.0 - FracY) * (HeightB - HeightC);
	return static_cast<float>(Result);
}

float FIronHeightField::SampleSurface(double XM, double YM) const
{
	return FMath::Max(Sample(XM, YM), static_cast<float>(Info.SeaLevelM));
}

bool FIronHeightField::Trace(const FVector& OriginCm, const FVector& Direction, FVector& OutHitCm, double MaxDistanceCm) const
{
	if (!IsValid())
	{
		return false;
	}
	const FVector Dir = Direction.GetSafeNormal();
	if (Dir.IsNearlyZero())
	{
		return false;
	}
	const double TopCm = (FMath::Max(Info.MaxElevationM, Info.SeaLevelM) + 1.0) * IronWorld::CmPerMetre;
	const double BottomCm = (FMath::Min(Info.MinElevationM, Info.SeaLevelM) - 1.0) * IronWorld::CmPerMetre;
	double StartT = 0.0;
	double EndT = MaxDistanceCm;
	if (Dir.Z < -1.0e-6)
	{
		StartT = FMath::Max(0.0, (TopCm - OriginCm.Z) / Dir.Z);
		EndT = FMath::Min(EndT, (BottomCm - OriginCm.Z) / Dir.Z);
	}
	else if (Dir.Z > 1.0e-6)
	{
		if (OriginCm.Z > TopCm)
		{
			return false;
		}
		EndT = FMath::Min(EndT, (TopCm - OriginCm.Z) / Dir.Z);
	}
	else if (OriginCm.Z > TopCm || OriginCm.Z < BottomCm)
	{
		return false;
	}
	if (StartT >= EndT)
	{
		return false;
	}

	auto Clearance = [this, &OriginCm, &Dir](double T)
	{
		const FVector Point = OriginCm + Dir * T;
		return Point.Z - static_cast<double>(SampleSurface(Point.X * IronWorld::MetresPerCm, Point.Y * IronWorld::MetresPerCm)) * IronWorld::CmPerMetre;
	};

	if (Clearance(StartT) <= 0.0)
	{
		OutHitCm = OriginCm + Dir * StartT;
		return true;
	}
	const double StepCm = FMath::Max(50.0, Info.GridStepM * static_cast<double>(Stride) * IronWorld::CmPerMetre);
	double PreviousT = StartT;
	for (int32 Guard = 0; Guard < 100000 && PreviousT < EndT; ++Guard)
	{
		const double NextT = FMath::Min(PreviousT + StepCm, EndT);
		if (Clearance(NextT) <= 0.0)
		{
			double Low = PreviousT;
			double High = NextT;
			for (int32 Iteration = 0; Iteration < 16; ++Iteration)
			{
				const double Mid = 0.5 * (Low + High);
				if (Clearance(Mid) <= 0.0)
				{
					High = Mid;
				}
				else
				{
					Low = Mid;
				}
			}
			OutHitCm = OriginCm + Dir * High;
			return true;
		}
		PreviousT = NextT;
	}
	return false;
}

FString FIronHeightField::HashSourceBytes(const TArray<uint8>& Bytes)
{
	// Bitwise reflected CRC-32 (polynomial 0xEDB88320, initial and final XOR 0xFFFFFFFF), as zlib.crc32. A 1-2 MB
	// heightmap takes a few milliseconds on the build worker.
	uint32 Crc = 0xFFFFFFFFu;
	for (const uint8 Byte : Bytes)
	{
		Crc ^= static_cast<uint32>(Byte);
		for (int32 Bit = 0; Bit < 8; ++Bit)
		{
			Crc = (Crc >> 1) ^ (0xEDB88320u & (0u - (Crc & 1u)));
		}
	}
	return FString::Printf(TEXT("%08x-%d"), Crc ^ 0xFFFFFFFFu, Bytes.Num());
}

TSharedPtr<IImageWrapper> FIronHeightField::CreatePngWrapper()
{
	IImageWrapperModule& ImageWrapperModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName(TEXT("ImageWrapper")));
	return ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
}

bool FIronHeightField::Load(const TSharedPtr<IImageWrapper>& PngWrapper, FIronHeightField& OutField, FString& OutError)
{
	const FString Dir = IronTerrainDetail::TerrainDir();
	const FString InfoPath = Dir / TEXT("Terrain.json");
	const FString HeightPath = Dir / TEXT("Height.png");

	IronSim::FJson InfoJson;
	if (!IronWorld::ReadJsonFile(InfoPath, InfoJson, OutError))
	{
		return false;
	}
	FIronTerrainInfo TerrainInfo;
	if (!IronTerrainDetail::ParseInfo(InfoJson, TerrainInfo))
	{
		OutError = FString::Printf(TEXT("%s has invalid sizes."), *InfoPath);
		return false;
	}

	TArray<uint8> PngBytes;
	if (!FFileHelper::LoadFileToArray(PngBytes, *HeightPath, FILEREAD_Silent))
	{
		OutError = FString::Printf(TEXT("could not read %s"), *HeightPath);
		return false;
	}
	const FString PngHash = HashSourceBytes(PngBytes);
	if (!PngWrapper.IsValid() || !PngWrapper->SetCompressed(PngBytes.GetData(), PngBytes.Num()))
	{
		OutError = FString::Printf(TEXT("%s is not a readable PNG"), *HeightPath);
		return false;
	}
	const int32 Width = static_cast<int32>(PngWrapper->GetWidth());
	const int32 Height = static_cast<int32>(PngWrapper->GetHeight());
	const int64 PixelCount = static_cast<int64>(Width) * static_cast<int64>(Height);
	if (Width < 2 || Height < 2)
	{
		OutError = FString::Printf(TEXT("%s is too small (%dx%d)"), *HeightPath, Width, Height);
		return false;
	}

	// 16-bit greyscale is the contract; 8-bit grey and 16-bit RGBA (red channel) are tolerated. The PNG decoder
	// returns 16-bit samples in native (little-endian) byte order.
	enum class ELayout : uint8
	{
		Grey16,
		Grey8,
		Rgba16
	};
	TArray64<uint8> Raw;
	ELayout Layout = ELayout::Grey16;
	if (!PngWrapper->GetRaw(ERGBFormat::Gray, 16, Raw) || Raw.Num() < PixelCount * 2)
	{
		Raw.Reset();
		Layout = ELayout::Grey8;
		if (!PngWrapper->GetRaw(ERGBFormat::Gray, 8, Raw) || Raw.Num() < PixelCount)
		{
			Raw.Reset();
			Layout = ELayout::Rgba16;
			if (!PngWrapper->GetRaw(ERGBFormat::RGBA, 16, Raw) || Raw.Num() < PixelCount * 8)
			{
				OutError = FString::Printf(TEXT("%s could not be decoded (expected 16-bit greyscale)"), *HeightPath);
				return false;
			}
		}
	}

	const double ExpectedWidth = TerrainInfo.MapWidthM / TerrainInfo.GridStepM + 1.0;
	if (FMath::Abs(ExpectedWidth - static_cast<double>(Width)) > 0.5)
	{
		// Keep the map extent authoritative: derive the pixel spacing from the image.
		const double DerivedStep = TerrainInfo.MapWidthM / static_cast<double>(Width - 1);
		UE_LOG(LogIronWorld, Warning, TEXT("Height.png is %dx%d, Terrain.json expects %.0f px wide; using %.3f m per pixel."), Width, Height, ExpectedWidth, DerivedStep);
		TerrainInfo.GridStepM = DerivedStep;
	}

	OutField.Info = TerrainInfo;
	OutField.SamplesX = Width;
	OutField.SamplesY = Height;
	OutField.SourceHash = PngHash;
	OutField.Heights.SetNumUninitialized(static_cast<int32>(PixelCount));
	const double Range = TerrainInfo.MaxElevationM - TerrainInfo.MinElevationM;
	for (int64 Index = 0; Index < PixelCount; ++Index)
	{
		double Normalized = 0.0;
		switch (Layout)
		{
		case ELayout::Grey16:
			Normalized = static_cast<double>(static_cast<uint32>(Raw[Index * 2]) | (static_cast<uint32>(Raw[Index * 2 + 1]) << 8)) / 65535.0;
			break;
		case ELayout::Grey8:
			Normalized = static_cast<double>(Raw[Index]) / 255.0;
			break;
		default:
			Normalized = static_cast<double>(static_cast<uint32>(Raw[Index * 8]) | (static_cast<uint32>(Raw[Index * 8 + 1]) << 8)) / 65535.0;
			break;
		}
		OutField.Heights[static_cast<int32>(Index)] = static_cast<float>(TerrainInfo.MinElevationM + Normalized * Range);
	}
	OutField.BuildMeshGrid(1);
	return true;
}

// ---------------------------------------------------------------------------------------------------------------------
// AIronTerrain
// ---------------------------------------------------------------------------------------------------------------------

AIronTerrain::AIronTerrain()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(SceneRoot);
}

bool AIronTerrain::AreDataFilesPresent()
{
	const FString Dir = IronTerrainDetail::TerrainDir();
	return FPaths::FileExists(Dir / TEXT("Terrain.json")) && FPaths::FileExists(Dir / TEXT("Height.png"));
}

UMaterialInstanceDynamic* AIronTerrain::GetTerrainMaterial() const
{
	return TerrainMaterial.Get();
}

void AIronTerrain::BeginBuild(int32 MeshStride)
{
	if (bBuildStarted)
	{
		return;
	}
	bBuildStarted = true;
	CreateTerrainMaterial();

	IronTerrainDetail::FBuildRequest Request;
	Request.PngWrapper = FIronHeightField::CreatePngWrapper();
	Request.TreesJsonPath = IronTerrainDetail::TerrainDir() / TEXT("Trees.json");
	Request.Stride = FMath::Clamp(MeshStride, 1, 8);
	Request.TreeExclusions = TreeExclusionDiscs;
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	for (int32 Type = 0; Type < IronTerrainDetail::TreeTypeCount; ++Type)
	{
		Request.TreeScales[Type] = ModelParams.ScaleOf(IronTerrainDetail::TreeModels[Type]);
	}
	// The imported static chunks (kept alive by StaticChunkMeshes); the worker confirms they match the heightmap.
	FString StaticHash;
	int32 StaticStride = 0;
	if (LoadStaticChunks(StaticHash, StaticStride))
	{
		Request.StaticChunkHash = StaticHash;
		Request.StaticChunkStride = StaticStride;
	}

	// Only plain data crosses to the worker; the result comes back through the future (polled in Tick), so the
	// actor may be destroyed while the worker runs.
	BuildFuture = Async(EAsyncExecution::ThreadPool, [Request]()
	{
		return IronTerrainDetail::RunBuild(Request);
	});
	SetActorTickEnabled(true);
}

void AIronTerrain::SetTreeExclusions(const TArray<FVector>& InDiscsM)
{
	if (bBuildStarted)
	{
		// The worker already has its request: clear these on the game thread instead.
		ClearTrees(InDiscsM);
		return;
	}
	TreeExclusionDiscs = InDiscsM;
}

void AIronTerrain::ClearTrees(const TArray<FVector>& DiscsM)
{
	if (DiscsM.Num() == 0)
	{
		return;
	}
	// Trees not planted yet are filtered by CreateTrees; remove the planted ones now.
	TreeClearings.Append(DiscsM);
	for (const TObjectPtr<UHierarchicalInstancedStaticMeshComponent>& Forest : TreeComponents)
	{
		if (Forest == nullptr)
		{
			continue;
		}
		TArray<int32> Cleared;
		const int32 InstanceCount = Forest->GetInstanceCount();
		for (int32 InstanceIndex = 0; InstanceIndex < InstanceCount; ++InstanceIndex)
		{
			FTransform InstanceTransform;
			if (Forest->GetInstanceTransform(InstanceIndex, InstanceTransform, true))
			{
				const FVector2D TreePoint = IronWorld::WorldToMap(InstanceTransform.GetLocation());
				if (IronTerrainDetail::InsideAnyDisc(DiscsM, TreePoint.X, TreePoint.Y))
				{
					Cleared.Add(InstanceIndex);
				}
			}
		}
		if (Cleared.Num() > 0)
		{
			Forest->RemoveInstances(Cleared);
		}
	}
}

bool AIronTerrain::LoadStaticChunks(FString& OutSourceHash, int32& OutStride)
{
	StaticChunkMeshes.Reset();
	const UIronAssetManifest* Manifest = IronWorld::LoadAssetManifest();
	if (Manifest == nullptr || Manifest->TerrainMeshStride <= 0 || Manifest->TerrainHeightHash.IsEmpty())
	{
		UE_LOG(LogIronWorld, Log, TEXT("No imported SM_Terrain_* chunks; the terrain is built as a runtime mesh (Lumen sees it on screen only)."));
		return false;
	}
	for (int32 ChunkY = 0; ChunkY < IronTerrainDetail::ChunksY; ++ChunkY)
	{
		for (int32 ChunkX = 0; ChunkX < IronTerrainDetail::ChunksX; ++ChunkX)
		{
			const FString ChunkName = IronTerrainDetail::StaticChunkName(ChunkX, ChunkY);
			UStaticMesh* ChunkMesh = IronWorld::LoadModel(ChunkName);
			if (ChunkMesh == nullptr)
			{
				// Never mix imported and runtime chunks: their seams would not line up.
				UE_LOG(LogIronWorld, Warning, TEXT("%s is missing; the terrain is built as a runtime mesh. Re-run the asset import."), *IronWorld::ModelObjectPath(ChunkName));
				StaticChunkMeshes.Reset();
				return false;
			}
			StaticChunkMeshes.Add(ChunkMesh);
		}
	}
	OutSourceHash = Manifest->TerrainHeightHash;
	OutStride = FMath::Clamp(Manifest->TerrainMeshStride, 1, 8);
	return true;
}

void AIronTerrain::CreateTerrainMaterial()
{
	UMaterialInterface* Base = IronWorld::LoadMaterial(TEXT("MI_IronTerrain"));
	if (Base == nullptr)
	{
		Base = IronWorld::LoadMaterial(TEXT("M_IronTerrain"));
	}
	if (Base != nullptr)
	{
		TerrainMaterial = UMaterialInstanceDynamic::Create(Base, this);
		return;
	}
	UE_LOG(LogIronWorld, Warning, TEXT("M_IronTerrain was not imported; the terrain uses a plain fallback colour."));
	TerrainMaterial = IronWorld::MakeColoredMaterial(IronWorld::LoadEngineMaterial(IronWorld::EngineBasicShapeMaterialPath), this, FLinearColor(0.16f, 0.24f, 0.10f));
}

void AIronTerrain::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	if (BuildFuture.IsValid() && BuildFuture.IsReady())
	{
		const TSharedPtr<FIronTerrainBuildResult> Result = BuildFuture.Get();
		BuildFuture = TFuture<TSharedPtr<FIronTerrainBuildResult>>();
		HandleBuildResult(Result);
	}
	if (PendingResult.IsValid())
	{
		CreatePendingComponents();
	}
	if (bBuildComplete || bFailed)
	{
		SetActorTickEnabled(false);
	}
}

void AIronTerrain::HandleBuildResult(const TSharedPtr<FIronTerrainBuildResult>& Result)
{
	if (!Result.IsValid() || !Result->bSucceeded)
	{
		bFailed = true;
		UE_LOG(LogIronWorld, Warning, TEXT("The 3D terrain is unavailable: %s"), Result.IsValid() ? *Result->Error : TEXT("the build produced no result"));
		return;
	}
	HeightField = MoveTemp(Result->Field);
	bHeightReady = true;
	bStaticChunks = Result->bStaticChunks;
	if (!bStaticChunks)
	{
		StaticChunkMeshes.Reset();
	}
	if (TerrainMaterial != nullptr)
	{
		// M_IronTerrain maps its textures from world position over this rectangle (cm).
		const FIronTerrainInfo& TerrainInfo = HeightField.Info;
		TerrainMaterial->SetVectorParameterValue(FName(TEXT("MapOrigin")), FLinearColor(0.0f, 0.0f, 0.0f, 0.0f));
		TerrainMaterial->SetVectorParameterValue(FName(TEXT("MapSize")), FLinearColor(static_cast<float>(TerrainInfo.MapWidthM * IronWorld::CmPerMetre), static_cast<float>(TerrainInfo.MapHeightM * IronWorld::CmPerMetre), 0.0f, 0.0f));
	}
	UE_LOG(LogIronWorld, Log, TEXT("Terrain %dx%d px (%.2f m grid, mesh stride %d): %d %s chunks, trees %d/%d/%d (%d skipped)."),
		HeightField.SamplesX, HeightField.SamplesY, HeightField.Info.GridStepM, HeightField.Stride,
		bStaticChunks ? StaticChunkMeshes.Num() : Result->Sections.Num(), bStaticChunks ? TEXT("imported static") : TEXT("runtime"),
		Result->Trees[0].Num(), Result->Trees[1].Num(), Result->Trees[2].Num(), Result->TreesSkipped);

	CreateSea();
	PendingResult = Result;
	NextSection = 0;
	NextTreeType = 0;
	OnHeightReady.Broadcast();
}

UProceduralMeshComponent* AIronTerrain::NewMeshComponent()
{
	UProceduralMeshComponent* MeshComponent = NewObject<UProceduralMeshComponent>(this);
	MeshComponent->SetupAttachment(SceneRoot);
	MeshComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	MeshComponent->SetGenerateOverlapEvents(false);
	MeshComponent->SetCanEverAffectNavigation(false);
	return MeshComponent;
}

UStaticMeshComponent* AIronTerrain::NewStaticChunk(UStaticMesh* ChunkMesh)
{
	UStaticMeshComponent* ChunkComponent = NewObject<UStaticMeshComponent>(this);
	ChunkComponent->SetupAttachment(SceneRoot);
	ChunkComponent->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	ChunkComponent->SetGenerateOverlapEvents(false);
	ChunkComponent->SetCanEverAffectNavigation(false);
	ChunkComponent->SetStaticMesh(ChunkMesh);
	if (TerrainMaterial != nullptr)
	{
		ChunkComponent->SetMaterial(0, TerrainMaterial.Get());
	}
	ChunkComponent->RegisterComponent();
	return ChunkComponent;
}

void AIronTerrain::CreatePendingComponents()
{
	FIronTerrainBuildResult& Result = *PendingResult;
	if (Result.bStaticChunks)
	{
		// The vertices are in world space (cm): the components sit at the actor origin like the runtime chunks.
		int32 Budget = IronTerrainDetail::StaticChunksPerTick;
		while (Budget > 0 && NextSection < StaticChunkMeshes.Num())
		{
			StaticChunks.Add(NewStaticChunk(StaticChunkMeshes[NextSection].Get()));
			++NextSection;
			--Budget;
		}
		if (NextSection < StaticChunkMeshes.Num())
		{
			return;
		}
	}
	else
	{
		int32 Budget = IronTerrainDetail::SectionsPerTick;
		while (Budget > 0 && NextSection < Result.Sections.Num())
		{
			UProceduralMeshComponent* Chunk = NewMeshComponent();
			Chunk->SetProcMeshSection(0, Result.Sections[NextSection]);
			if (TerrainMaterial != nullptr)
			{
				Chunk->SetMaterial(0, TerrainMaterial.Get());
			}
			Chunk->RegisterComponent();
			Chunks.Add(Chunk);
			// The component keeps its own copy; free the worker's.
			Result.Sections[NextSection] = FProcMeshSection();
			++NextSection;
			--Budget;
		}
		if (NextSection < Result.Sections.Num())
		{
			return;
		}
	}
	if (NextTreeType < IronTerrainDetail::TreeTypeCount)
	{
		// One tree type per frame.
		CreateTrees(NextTreeType);
		++NextTreeType;
		return;
	}
	PendingResult.Reset();
	bBuildComplete = true;
	OnBuildComplete.Broadcast();
}

void AIronTerrain::CreateTrees(int32 TreeType)
{
	TArray<FTransform>& Transforms = PendingResult->Trees[TreeType];
	if (TreeClearings.Num() > 0)
	{
		Transforms.RemoveAllSwap([this](const FTransform& Tree)
		{
			const FVector2D TreePoint = IronWorld::WorldToMap(Tree.GetLocation());
			return IronTerrainDetail::InsideAnyDisc(TreeClearings, TreePoint.X, TreePoint.Y);
		});
	}
	if (Transforms.Num() == 0)
	{
		return;
	}
	UStaticMesh* TreeMesh = IronWorld::LoadModel(IronTerrainDetail::TreeModels[TreeType]);
	if (TreeMesh == nullptr)
	{
		UE_LOG(LogIronWorld, Log, TEXT("SM_%s was not imported; %d trees skipped."), IronTerrainDetail::TreeModels[TreeType], Transforms.Num());
		Transforms.Empty();
		return;
	}
	UHierarchicalInstancedStaticMeshComponent* Forest = NewObject<UHierarchicalInstancedStaticMeshComponent>(this);
	Forest->SetupAttachment(SceneRoot);
	Forest->SetStaticMesh(TreeMesh);
	Forest->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Forest->SetGenerateOverlapEvents(false);
	Forest->SetCanEverAffectNavigation(false);
	Forest->SetCullDistances(IronTerrainDetail::TreeCullStartCm, IronTerrainDetail::TreeCullEndCm);
	Forest->RegisterComponent();
	Forest->AddInstances(Transforms, false);
	TreeComponents.Add(Forest);
	Transforms.Empty();
}

void AIronTerrain::CreateSea()
{
	const FIronTerrainInfo& TerrainInfo = HeightField.Info;
	UMaterialInterface* BasicMaterial = IronWorld::LoadEngineMaterial(IronWorld::EngineBasicShapeMaterialPath);
	UMaterialInterface* Water = IronWorld::LoadMaterial(TEXT("MI_IronWater"));
	if (Water == nullptr)
	{
		Water = IronWorld::LoadMaterial(TEXT("M_IronWater"));
	}
	const bool bImportedWater = Water != nullptr;
	if (!bImportedWater)
	{
		UE_LOG(LogIronWorld, Warning, TEXT("M_IronWater was not imported; the sea uses a plain fallback colour."));
		Water = IronWorld::MakeColoredMaterial(BasicMaterial, this, FLinearColor(0.02f, 0.06f, 0.09f));
	}
	WaterMaterial = Water;

	const FVector2D MinM(-IronTerrainDetail::SeaMarginM, -IronTerrainDetail::SeaMarginM);
	const FVector2D MaxM(TerrainInfo.MapWidthM + IronTerrainDetail::SeaMarginM, TerrainInfo.MapHeightM + IronTerrainDetail::SeaMarginM);
	if (Water != nullptr)
	{
		FProcMeshSection Section;
		IronTerrainDetail::BuildFlatGrid(MinM, MaxM, TerrainInfo.SeaLevelM, IronTerrainDetail::SeaCells, TerrainInfo, Section);
		SeaMesh = NewMeshComponent();
		SeaMesh->SetProcMeshSection(0, Section);
		SeaMesh->SetMaterial(0, Water);
		SeaMesh->SetCastShadow(false);
		SeaMesh->RegisterComponent();
	}

	// The water shades the depth behind it: give the open sea beyond the terrain a dark floor to look into.
	UMaterialInstanceDynamic* FloorMaterial = nullptr;
	if (bImportedWater)
	{
		if (UMaterialInterface* TintBase = IronWorld::LoadMaterial(TEXT("M_IronTint")))
		{
			FloorMaterial = UMaterialInstanceDynamic::Create(TintBase, this);
			if (FloorMaterial != nullptr)
			{
				FloorMaterial->SetVectorParameterValue(FName(IronWorld::TintParameter), FLinearColor(0.02f, 0.035f, 0.04f));
			}
		}
		else
		{
			FloorMaterial = IronWorld::MakeColoredMaterial(BasicMaterial, this, FLinearColor(0.02f, 0.035f, 0.04f));
		}
	}
	if (FloorMaterial != nullptr)
	{
		FProcMeshSection Section;
		const double FloorM = FMath::Min(TerrainInfo.MinElevationM, TerrainInfo.SeaLevelM) - 2.0;
		IronTerrainDetail::BuildFlatGrid(MinM, MaxM, FloorM, 4, TerrainInfo, Section);
		SeaFloorMesh = NewMeshComponent();
		SeaFloorMesh->SetProcMeshSection(0, Section);
		SeaFloorMesh->SetMaterial(0, FloorMaterial);
		SeaFloorMesh->SetCastShadow(false);
		SeaFloorMesh->RegisterComponent();
	}
}

float AIronTerrain::SampleHeight(const FVector2D& MapPointM) const
{
	return bHeightReady ? HeightField.Sample(MapPointM.X, MapPointM.Y) : static_cast<float>(HeightField.Info.SeaLevelM);
}

float AIronTerrain::SampleSurface(const FVector2D& MapPointM) const
{
	return bHeightReady ? HeightField.SampleSurface(MapPointM.X, MapPointM.Y) : static_cast<float>(HeightField.Info.SeaLevelM);
}

bool AIronTerrain::TraceSurface(const FVector& OriginCm, const FVector& Direction, FVector& OutHitCm) const
{
	return bHeightReady && HeightField.Trace(OriginCm, Direction, OutHitCm);
}
