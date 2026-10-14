#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Sim/IronJson.h"
#include "World/IronEnvironment.h"
#include "World/IronTerrain.h"
#include "World/IronWorldAssets.h"
#include "World/IronWorldMath.h"

#include "IImageWrapper.h"
#include "Misc/Paths.h"

#include <string>

namespace IronWorldTestDetail
{
	/** A small synthetic heightfield with distinct heights per pixel. */
	FIronHeightField MakeField(int32 Width, int32 Height, double Step, int32 Stride)
	{
		FIronHeightField Field;
		Field.Info.MapWidthM = static_cast<double>(Width - 1) * Step;
		Field.Info.MapHeightM = static_cast<double>(Height - 1) * Step;
		Field.Info.GridStepM = Step;
		Field.Info.MinElevationM = -10.0;
		Field.Info.MaxElevationM = 60.0;
		Field.Info.SeaLevelM = 0.0;
		Field.SamplesX = Width;
		Field.SamplesY = Height;
		Field.Heights.SetNum(Width * Height);
		for (int32 Y = 0; Y < Height; ++Y)
		{
			for (int32 X = 0; X < Width; ++X)
			{
				Field.Heights[Y * Width + X] = static_cast<float>(X * 3 + Y * 7 + (X * Y) % 3) - 2.0f;
			}
		}
		Field.BuildMeshGrid(Stride);
		return Field;
	}

	bool Near(double Actual, double Expected, double Tolerance = 1.0e-3)
	{
		return FMath::IsNearlyEqual(Actual, Expected, Tolerance);
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronWorldMathTest, "IronReign.World.Math", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronWorldMathTest::RunTest(const FString& /*Parameters*/)
{
	using IronWorldTestDetail::Near;

	const FVector WorldPoint = IronWorld::MapToWorld(FVector2D(1200.0, 750.0), 12.5);
	TestTrue(TEXT("Map metres become centimetres"), Near(WorldPoint.X, 120000.0) && Near(WorldPoint.Y, 75000.0) && Near(WorldPoint.Z, 1250.0));
	const FVector2D MapPoint = IronWorld::WorldToMap(WorldPoint);
	TestTrue(TEXT("WorldToMap inverts MapToWorld"), Near(MapPoint.X, 1200.0) && Near(MapPoint.Y, 750.0));
	TestTrue(TEXT("WorldToHeightM"), Near(IronWorld::WorldToHeightM(WorldPoint), 12.5));

	const FVector2D Hex10 = IronWorld::HexToBoardLocalM(1, 0);
	TestTrue(TEXT("Odd hex columns shift down half a row"), Near(Hex10.X, 6.0) && Near(Hex10.Y, 3.464));
	const FVector2D Hex21 = IronWorld::HexToBoardLocalM(2, 1);
	TestTrue(TEXT("Even hex columns are not shifted"), Near(Hex21.X, 12.0) && Near(Hex21.Y, 6.928));
	TestTrue(TEXT("The battle board sits 100 km south of the map origin"), Near(IronWorld::BoardOrigin().Y, -10000000.0));

	for (int32 Col = 0; Col < 18; ++Col)
	{
		for (int32 Row = 0; Row < 12; ++Row)
		{
			int32 FoundCol = -1;
			int32 FoundRow = -1;
			const bool bInside = IronWorld::WorldToHex(IronWorld::HexToWorld(Col, Row, 0.0) + FVector(80.0, -60.0, 0.0), FoundCol, FoundRow);
			if (!bInside || FoundCol != Col || FoundRow != Row)
			{
				AddError(FString::Printf(TEXT("WorldToHex near hex (%d,%d) returned (%d,%d) inside=%d"), Col, Row, FoundCol, FoundRow, bInside ? 1 : 0));
			}
		}
	}

	TestTrue(TEXT("A model facing south keeps frontYaw"), Near(IronWorld::ModelYawDegrees(90.0, IronWorld::SouthYawDegrees), 90.0));
	TestTrue(TEXT("A model facing north turns 180 degrees"), Near(IronWorld::ModelYawDegrees(90.0, IronWorld::NorthYawDegrees), -90.0));
	TestTrue(TEXT("Direction +Y is yaw 90"), Near(IronWorld::DirectionToYawDegrees(FVector2D(0.0, 1.0)), 90.0));

	double Value = 0.0;
	double Velocity = 0.0;
	double Highest = 0.0;
	for (int32 Step = 0; Step < 240; ++Step)
	{
		Value = IronWorld::SmoothDamp(Value, 10.0, Velocity, 0.2, 1.0 / 60.0);
		Highest = FMath::Max(Highest, Value);
	}
	TestTrue(TEXT("SmoothDamp reaches its target"), Near(Value, 10.0, 0.01));
	TestTrue(TEXT("SmoothDamp does not overshoot"), Highest <= 10.0 + 1.0e-6);

	const FLinearColor Grey = IronWorld::ColorFromRGB(IronWorld::IndependentRGB);
	TestTrue(TEXT("sRGB colours become linear"), Grey.R > 0.2f && Grey.R < 0.3f);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronWorldHeightFieldTest, "IronReign.World.HeightField", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronWorldHeightFieldTest::RunTest(const FString& /*Parameters*/)
{
	using IronWorldTestDetail::Near;

	// Full resolution: every pixel is a vertex; samples between vertices follow the mesh triangles.
	const FIronHeightField Fine = IronWorldTestDetail::MakeField(6, 5, 2.0, 1);
	TestTrue(TEXT("The synthetic field is valid"), Fine.IsValid());
	for (int32 Y = 0; Y < 5; ++Y)
	{
		for (int32 X = 0; X < 6; ++X)
		{
			if (!Near(Fine.Sample(X * 2.0, Y * 2.0), Fine.At(X, Y)))
			{
				AddError(FString::Printf(TEXT("Sample at vertex (%d,%d) = %f, expected %f"), X, Y, Fine.Sample(X * 2.0, Y * 2.0), Fine.At(X, Y)));
			}
		}
	}
	// Cell (1,1)..(2,2), point at 25% / 25%: upper-left triangle A D B.
	const double HeightA = Fine.At(1, 1);
	const double HeightB = Fine.At(2, 1);
	const double HeightD = Fine.At(1, 2);
	TestTrue(TEXT("Upper-left triangle interpolation"), Near(Fine.Sample(2.5, 2.5), HeightA + 0.25 * (HeightB - HeightA) + 0.25 * (HeightD - HeightA)));
	// Point at 75% / 75%: lower-right triangle B D C.
	const double HeightC = Fine.At(2, 2);
	TestTrue(TEXT("Lower-right triangle interpolation"), Near(Fine.Sample(3.5, 3.5), HeightC + 0.25 * (HeightD - HeightC) + 0.25 * (HeightB - HeightC)));
	TestTrue(TEXT("Samples clamp at the map edge"), Near(Fine.Sample(-50.0, -50.0), Fine.At(0, 0)) && Near(Fine.Sample(500.0, 500.0), Fine.At(5, 4)));

	// Stride 2 on 6 x 5 pixels: columns 0 2 4 5, rows 0 2 4.
	const FIronHeightField Coarse = IronWorldTestDetail::MakeField(6, 5, 2.0, 2);
	TestEqual(TEXT("Mesh columns at stride 2"), Coarse.MeshColumns.Num(), 4);
	TestEqual(TEXT("Mesh rows at stride 2"), Coarse.MeshRows.Num(), 3);
	TestTrue(TEXT("The last column is always a mesh column"), Coarse.MeshColumns.Num() == 4 && Coarse.MeshColumns[3] == 5);
	TestTrue(TEXT("Coarse samples hit mesh vertices exactly"), Near(Coarse.Sample(4.0, 4.0), Coarse.At(2, 2)) && Near(Coarse.Sample(10.0, 8.0), Coarse.At(5, 4)));
	TestTrue(TEXT("Coarse samples interpolate along mesh edges"), Near(Coarse.Sample(2.0, 0.0), 0.5 * (Coarse.At(0, 0) + Coarse.At(2, 0))));

	// Rays.
	FVector Hit;
	const FVector Origin = IronWorld::MapToWorld(FVector2D(3.0, 5.0), 500.0);
	TestTrue(TEXT("A downward ray hits the surface"), Fine.Trace(Origin, FVector(0.0, 0.0, -1.0), Hit));
	TestTrue(TEXT("The hit lies on the rendered surface"), Near(Hit.Z, Fine.SampleSurface(3.0, 5.0) * IronWorld::CmPerMetre, 1.0));
	const FVector Slanted = FVector(0.4, 0.3, -1.0).GetSafeNormal();
	if (TestTrue(TEXT("A slanted ray hits the surface"), Fine.Trace(IronWorld::MapToWorld(FVector2D(1.0, 1.0), 40.0), Slanted, Hit)))
	{
		const FVector2D HitMap = IronWorld::WorldToMap(Hit);
		TestTrue(TEXT("The slanted hit lies on the rendered surface"), Near(Hit.Z, Fine.SampleSurface(HitMap.X, HitMap.Y) * IronWorld::CmPerMetre, 2.0));
	}
	TestFalse(TEXT("An upward ray from above the terrain misses"), Fine.Trace(Origin, FVector(0.0, 0.0, 1.0), Hit));

	// The import records this identity for SM_Terrain_* with Python's zlib.crc32: the CRC-32 check value of "123456789".
	const char* const CheckText = "123456789";
	TArray<uint8> CheckBytes;
	CheckBytes.Append(reinterpret_cast<const uint8*>(CheckText), 9);
	TestEqual(TEXT("Heightmap identity = zlib CRC-32 and byte count"), FIronHeightField::HashSourceBytes(CheckBytes), FString(TEXT("cbf43926-9")));
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronWorldTerrainDataTest, "IronReign.World.TerrainData", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronWorldTerrainDataTest::RunTest(const FString& /*Parameters*/)
{
	if (!AIronTerrain::AreDataFilesPresent())
	{
		AddInfo(TEXT("Content/Data/Art3D/Terrain is not generated yet; nothing to check."));
		return true;
	}
	FIronHeightField Field;
	FString Error;
	if (!TestTrue(TEXT("Terrain.json and Height.png load"), FIronHeightField::Load(FIronHeightField::CreatePngWrapper(), Field, Error)))
	{
		AddError(Error);
		return true;
	}
	TestTrue(TEXT("The heightfield is valid"), Field.IsValid());
	const double ExpectedWidth = Field.Info.MapWidthM / Field.Info.GridStepM + 1.0;
	TestTrue(FString::Printf(TEXT("Height.png width %d matches Terrain.json (%.0f)"), Field.SamplesX, ExpectedWidth), FMath::Abs(ExpectedWidth - Field.SamplesX) < 0.5);

	float Lowest = TNumericLimits<float>::Max();
	float Highest = -TNumericLimits<float>::Max();
	for (const float Height : Field.Heights)
	{
		Lowest = FMath::Min(Lowest, Height);
		Highest = FMath::Max(Highest, Height);
	}
	AddInfo(FString::Printf(TEXT("Terrain %dx%d px, %.1f m .. %.1f m"), Field.SamplesX, Field.SamplesY, Lowest, Highest));
	TestTrue(TEXT("Heights stay inside minHeight..maxHeight"), Lowest >= Field.Info.MinElevationM - 0.01 && Highest <= Field.Info.MaxElevationM + 0.01);
	TestTrue(TEXT("The terrain has relief"), Highest - Lowest > 10.0f);

	// Every city of the shipped scenario must stand on dry land.
	IronSim::FJson Scenario;
	const FString ScenarioPath = FPaths::ProjectContentDir() / TEXT("Data") / TEXT("Scenarios") / TEXT("BrokenMandate.json");
	if (IronWorld::ReadJsonFile(ScenarioPath, Scenario, Error))
	{
		const IronSim::FJson& Cities = Scenario.Get("cities");
		for (const IronSim::FJson& City : Cities.Items())
		{
			const double X = City.GetNumber("x");
			const double Y = City.GetNumber("y");
			const float Ground = Field.Sample(X, Y);
			if (Ground < Field.Info.SeaLevelM + 0.5)
			{
				AddWarning(FString::Printf(TEXT("City %s at (%.0f, %.0f) is under water (%.1f m)"), UTF8_TO_TCHAR(City.GetString("key").c_str()), X, Y, Ground));
			}
		}
	}
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronWorldLookTest, "IronReign.World.Look", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronWorldLookTest::RunTest(const FString& /*Parameters*/)
{
	using IronWorldTestDetail::Near;

	// Painted and realistic month looks (docs/DESIGN.md 12.6): same season, different style.
	for (int32 Month = 1; Month <= 12; ++Month)
	{
		const FIronSeasonLook Real = FIronSeasonLook::ForMonth(Month, EIronLook::Realistic);
		const FIronSeasonLook Painted = FIronSeasonLook::ForMonth(Month, EIronLook::Painted);
		const FIronSeasonLook Plain = FIronSeasonLook::ForMonth(Month);
		TestTrue(FString::Printf(TEXT("Month %d: ForMonth(Month) is the realistic look"), Month), Near(Plain.Painted, 0.0) && Near(Plain.SunBearingDegrees, Real.SunBearingDegrees));
		TestTrue(FString::Printf(TEXT("Month %d: painted amounts"), Month), Near(Real.Painted, 0.0) && Near(Painted.Painted, 1.0));
		TestTrue(FString::Printf(TEXT("Month %d: the season is the same in both looks"), Month), Near(Real.Snow, Painted.Snow) && Near(Real.Autumn, Painted.Autumn) && Near(Real.Wetness, Painted.Wetness));
		TestTrue(FString::Printf(TEXT("Month %d: painted light is soft, filled and unbloomed"), Month),
			Painted.SunIntensityLux < Real.SunIntensityLux && Painted.SkyLightIntensity > Real.SkyLightIntensity && Painted.SunSourceAngleDegrees > Real.SunSourceAngleDegrees && Near(Painted.BloomIntensity, 0.0));
		TestTrue(FString::Printf(TEXT("Month %d: painted key light from the north-west, high"), Month), Painted.SunBearingDegrees > 270.0f && Painted.SunBearingDegrees < 360.0f && Painted.SunElevationDegrees >= 40.0f);
		TestTrue(FString::Printf(TEXT("Month %d: painted sky is less blue"), Month), Painted.RayleighScatteringScale < Real.RayleighScatteringScale);
	}
	const FIronSeasonLook Half = FIronSeasonLook::Blend(FIronSeasonLook::ForMonth(4, EIronLook::Realistic), FIronSeasonLook::ForMonth(4, EIronLook::Painted), 0.5f);
	TestTrue(TEXT("A look switch blends the painted amount"), Near(Half.Painted, 0.5));

	// AreAssetsAvailable's cache: positives stick, negatives are re-probed after RetrySeconds.
	IronWorld::FAssetCheckCache Cache;
	TestFalse(TEXT("An empty cache is not fresh"), Cache.IsFresh(0.0));
	TestTrue(TEXT("The first missing asset is reported"), Cache.Store(TEXT("SM_City_1"), 100.0));
	TestTrue(TEXT("A negative answer is reused for a while"), Cache.IsFresh(100.0 + IronWorld::FAssetCheckCache::RetrySeconds - 1.0) && !Cache.bAvailable);
	TestFalse(TEXT("A negative answer is probed again later"), Cache.IsFresh(100.0 + IronWorld::FAssetCheckCache::RetrySeconds + 1.0));
	TestFalse(TEXT("The same missing asset is not reported twice"), Cache.Store(TEXT("SM_City_1"), 140.0));
	TestTrue(TEXT("Becoming available is reported"), Cache.Store(FString(), 200.0));
	TestTrue(TEXT("A positive answer sticks"), Cache.IsFresh(1.0e9) && Cache.bAvailable);
	Cache.Invalidate();
	TestFalse(TEXT("Invalidate forces a new probe"), Cache.IsFresh(201.0));
	return true;
}

#endif
