#include "World/IronBattleBoard3D.h"

#include "World/IronAssetManifest.h"
#include "World/IronEnvironment.h"
#include "World/IronWorldAssets.h"
#include "World/IronWorldMap3D.h"
#include "World/IronWorldMath.h"

#include "Algo/Reverse.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "Camera/PlayerCameraManager.h"
#include "Components/DirectionalLightComponent.h"
#include "Components/InstancedStaticMeshComponent.h"
#include "Components/PointLightComponent.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "HAL/PlatformTime.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Math/RotationMatrix.h"
#include "Misc/App.h"
#include "ProceduralMeshComponent.h"

namespace IronBattleBoard3DDetail
{
	constexpr int32 TerrainCount = static_cast<int32>(IronSim::EHexTerrain::Count);
	constexpr int32 LayerCount = static_cast<int32>(IronBoard3D::ELayer::Count);
	constexpr int32 TroopTypeCount = 3;
	/** Index = IronSim::ETroopType (Infantry, Cavalry, Archer). */
	const TCHAR* const UnitModels[TroopTypeCount] = {TEXT("Unit_Infantry"), TEXT("Unit_Cavalry"), TEXT("Unit_Archer")};

	constexpr double SqrtThree = 1.7320508075688772;
	constexpr double HexRadiusCm = IronWorld::HexRadiusM * IronWorld::CmPerMetre;
	constexpr double HexHalfHeightCm = HexRadiusCm * 0.5 * SqrtThree;

	// Surroundings: decorative hexes a step below the board, then a large ground plane.
	constexpr int32 SurroundSideColumns = 7;
	constexpr int32 SurroundFarRows = 8;
	constexpr int32 SurroundNearRows = 6;
	constexpr double SurroundDropM = 0.25;
	constexpr double GroundDropM = 1.35;
	constexpr double GroundSizeM = 4000.0;
	/**
	 * The ground is GroundTiles x GroundTiles slabs of GroundSizeM / GroundTiles metres, GroundThicknessM thick: closed
	 * boxes at a moderate non-uniform scale (10:1) keep their distance fields usable for Lumen.
	 */
	constexpr int32 GroundTiles = 20;
	constexpr double GroundThicknessM = 20.0;

	// Units (squad models are <= 6 m; the hex's inscribed circle is 6.9 m across).
	constexpr double FlagScale = 0.38;
	constexpr double FlagBackCm = -170.0;
	constexpr double FlagSideCm = 185.0;
	constexpr double UnitPickRadiusCm = 230.0;
	constexpr double MaxPlinthLiftCm = 60.0;
	constexpr float FlashEmissive = 4.0f;
	/** The "acted" look: side colour desaturated by this much and darkened to this brightness, faded over ActedFadeSeconds. */
	constexpr float ActedDesaturation = 0.65f;
	constexpr float ActedBrightness = 0.5f;
	constexpr float ActedFadeSeconds = 0.3f;
	/** Gate top used when the gate tile has no mesh (metres above the board). */
	constexpr float DefaultGateTopM = 6.0f;

	// Camera.
	constexpr float FieldOfViewDegrees = 38.0f;
	constexpr double FitPitchDegrees = 50.0;
	constexpr double ClosePitchDegrees = 40.0;
	constexpr double MaxPitchDegrees = 58.0;
	constexpr double MinDistanceM = 28.0;
	constexpr double MaxZoomOutFactor = 1.3;
	constexpr double ZoomStepFactor = 0.85;
	constexpr double FramingMarginM = 1.5;
	constexpr double UnitHeightForFramingM = 3.5;
	constexpr double TargetSmoothTime = 0.12;
	constexpr double DistanceSmoothTime = 0.16;
	constexpr double MaxStepSeconds = 0.1;
	/** Tilt-shift blur at infinity as a fraction of the image width (about half the strategy map's). */
	constexpr double TiltShiftCoc = 0.010;
	constexpr double SensorWidthMm = 24.576;
	constexpr double FocusMarginFraction = 0.12;
	/** A view target farther than this (cm) from the board camera is another scene (the strategy map, 100 km away). */
	constexpr double BlendMaxDistanceCm = 2.0e6;

	// Animation (seconds, centimetres).
	constexpr double MoveSecondsPerHex = 0.25;
	constexpr double GlideSeconds = 0.2;
	constexpr double HopCm = 55.0;
	constexpr double LungeSeconds = 0.36;
	constexpr double LungeHitSeconds = 0.15;
	constexpr double LungeFraction = 0.38;
	constexpr double LungeMaxCm = 260.0;
	constexpr double VolleySeconds = 0.5;
	constexpr int32 VolleyArrows = 5;
	constexpr double HitSeconds = 0.42;
	constexpr double GateShakeSeconds = 0.45;
	constexpr double GateBreakSeconds = 0.75;
	constexpr double GateSwapSeconds = 0.3;
	constexpr double CastSeconds = 0.3;
	constexpr double EffectDelaySeconds = 0.15;
	/** A fire tactic's burst strikes its target this long after the effect starts. */
	constexpr double FireHitDelaySeconds = 0.3;
	constexpr double FireSeconds = 1.2;
	constexpr double SwirlSeconds = 1.3;
	constexpr double PulseSeconds = 1.1;
	constexpr double FizzleSeconds = 0.6;
	constexpr double SinkSeconds = 0.9;
	constexpr double SinkDepthCm = 240.0;
	constexpr double FleeDistanceCm = 300.0;
	constexpr double EmberLifeSeconds = 0.75;
	constexpr double BurnEmberCycleSeconds = 1.4;

	// Sun over the battle's days: dawn in the east, dusk in the west (compass bearing the light comes from).
	constexpr double DawnBearingDegrees = 100.0;
	constexpr double DuskBearingDegrees = 250.0;
	constexpr double HorizonElevationDegrees = 13.0;
	constexpr double SunSmoothTime = 0.8;

	// Point lights in candela (illuminance = I / d^2 lux), scaled to the environment's ~8 lux sun: a hit lights the
	// ground under it at ~2-3x the sun for a moment, a burning hex glows orange around itself.
	constexpr double HitCandela = 110.0;
	constexpr double FireBurstCandela = 220.0;
	constexpr double BurnCandela = 70.0;
	constexpr double SwirlCandela = 70.0;
	constexpr double PulseCandela = 90.0;

	constexpr int32 MaxFxQuads = 240;
	constexpr int32 MaxLights = 40;

	/** Look of a board-wide highlight layer (M_IronHighlight parameters, height above the hex tops, draw order). */
	struct FLayerStyle
	{
		uint32 Rgb;
		float Alpha;
		float RingRadius;
		float RingWidth;
		float FillOpacity;
		float PulseMin;
		float PulseSpeed;
		float Intensity;
		float LiftCm;
		int32 SortPriority;
		float SizeScale;
	};

	/** Index = IronBoard3D::ELayer. */
	const FLayerStyle LayerStyles[LayerCount] = {
		// Grid: faint warm lines along the hex edges of the playable board.
		{0xF4E9D0, 0.26f, 0.985f, 0.03f, 0.0f, 1.0f, 0.0f, 1.2f, 12.0f, 1, 1.0f},
		// Burning: smouldering ground glow.
		{0xFF6A1E, 0.9f, 0.72f, 0.3f, 0.5f, 0.55f, 6.0f, 2.2f, 13.0f, 2, 0.96f},
		// Reachable: calm blue.
		{0x5AA9FF, 0.85f, 0.86f, 0.07f, 0.26f, 0.8f, 1.6f, 2.4f, 15.0f, 3, 0.97f},
		// Duel: orange.
		{0xFFAA3C, 0.95f, 0.86f, 0.09f, 0.22f, 0.55f, 2.6f, 2.8f, 16.0f, 4, 0.97f},
		// Tactic: purple.
		{0xB77CFF, 0.95f, 0.86f, 0.09f, 0.24f, 0.55f, 2.6f, 2.8f, 17.0f, 5, 0.97f},
		// Attack: vermilion, pulsing faster.
		{0xFF4B3A, 0.95f, 0.86f, 0.09f, 0.26f, 0.55f, 3.0f, 3.0f, 18.0f, 6, 0.97f},
	};
	const FLayerStyle HoverStyle = {0xFFF6E0, 0.9f, 0.93f, 0.05f, 0.1f, 1.0f, 0.0f, 2.0f, 20.0f, 7, 1.0f};
	const FLayerStyle SelectStyle = {0xFFD45E, 1.0f, 0.9f, 0.08f, 0.14f, 0.7f, 2.0f, 3.2f, 21.0f, 8, 1.0f};

	// Effect colours (sRGB).
	constexpr uint32 HitRgb = 0xFF2A1A;
	constexpr uint32 BurnRgb = 0xFF7A26;
	constexpr uint32 EmberHotRgb = 0xFFC45A;
	constexpr uint32 EmberCoolRgb = 0xE0401A;
	constexpr uint32 ArrowRgb = 0xFFE9B0;
	constexpr uint32 DustRgb = 0x8E7A60;
	constexpr uint32 ConfuseRgb = 0xA35BFF;
	constexpr uint32 RallyRgb = 0xFFCF5A;
	constexpr uint32 FizzleRgb = 0x9A948A;
	constexpr uint32 CaptureRgb = 0xFFF0C8;

	// Ground around the board: green, autumn and snow tones blended with the environment's season look.
	constexpr uint32 GroundGreenRgb = 0x627543;
	constexpr uint32 GroundAutumnRgb = 0x8E7444;
	constexpr uint32 GroundSnowRgb = 0xC4C8CC;

	const FName& ColorParam()
	{
		static const FName ParamName(TEXT("Color"));
		return ParamName;
	}

	const FName& TintParam()
	{
		static const FName ParamName(TEXT("Tint"));
		return ParamName;
	}

	const FName& EmissiveParam()
	{
		static const FName ParamName(TEXT("EmissiveFactor"));
		return ParamName;
	}

	void SetHighlightShape(UMaterialInstanceDynamic* Material, float HexShape, float RingRadius, float RingWidth, float FillOpacity, float PulseMin, float PulseSpeed, float Intensity)
	{
		if (Material == nullptr)
		{
			return;
		}
		Material->SetScalarParameterValue(FName(TEXT("HexShape")), HexShape);
		Material->SetScalarParameterValue(FName(TEXT("RingRadius")), RingRadius);
		Material->SetScalarParameterValue(FName(TEXT("RingWidth")), RingWidth);
		Material->SetScalarParameterValue(FName(TEXT("FillOpacity")), FillOpacity);
		Material->SetScalarParameterValue(FName(TEXT("PulseMin")), PulseMin);
		Material->SetScalarParameterValue(FName(TEXT("PulseSpeed")), PulseSpeed);
		Material->SetScalarParameterValue(FName(TEXT("Intensity")), Intensity);
	}

	FLinearColor Rgb(uint32 Value, float Alpha = 1.0f)
	{
		return IronWorld::ColorFromRGB(Value, Alpha);
	}

	FLinearColor WithAlpha(const FLinearColor& Color, double Alpha)
	{
		FLinearColor Result = Color;
		Result.A = static_cast<float>(FMath::Clamp(Alpha, 0.0, 1.0));
		return Result;
	}

	/** Side colour of a unit that already acted this turn: toward grey and darker, still telling the sides apart. */
	FLinearColor ActedColor(const FLinearColor& SideColor)
	{
		const float Luminance = SideColor.GetLuminance();
		const FLinearColor Grey(Luminance, Luminance, Luminance, 1.0f);
		FLinearColor Result = FMath::Lerp(SideColor, Grey, ActedDesaturation) * ActedBrightness;
		Result.A = SideColor.A;
		return Result;
	}

	IronWorld::FAssetCheckCache& BoardAssetCheck()
	{
		static IronWorld::FAssetCheckCache Cache;
		return Cache;
	}

	FString HexModelName(int32 TerrainIndex)
	{
		return FString::Printf(TEXT("Hex_%s"), UTF8_TO_TCHAR(IronSim::AssetName(static_cast<IronSim::EHexTerrain>(TerrainIndex))));
	}

	/** Terrains that look the same from every side: their tiles get a random yaw in 60 degree steps. */
	bool IsNaturalTerrain(int32 TerrainIndex)
	{
		switch (static_cast<IronSim::EHexTerrain>(TerrainIndex))
		{
		case IronSim::EHexTerrain::Plain:
		case IronSim::EHexTerrain::Forest:
		case IronSim::EHexTerrain::Hill:
		case IronSim::EHexTerrain::Mountain:
		case IronSim::EHexTerrain::Water:
			return true;
		default:
			return false;
		}
	}

	uint32 HexHash(int32 Col, int32 Row, uint32 Salt)
	{
		uint32 Value = (static_cast<uint32>(Col) * 73856093u) ^ (static_cast<uint32>(Row) * 19349663u) ^ (Salt * 83492791u);
		Value ^= Value >> 13;
		Value *= 0x5BD1E995u;
		Value ^= Value >> 15;
		return Value;
	}

	/** Deterministic 0..1 from an integer. */
	double Unit01(uint32 Value)
	{
		return static_cast<double>(HexHash(static_cast<int32>(Value), 17, 0x9E37u) & 0xFFFFFFu) / 16777215.0;
	}

	double EaseOut(double Alpha)
	{
		const double T = FMath::Clamp(Alpha, 0.0, 1.0);
		return 1.0 - (1.0 - T) * (1.0 - T);
	}

	double EaseIn(double Alpha)
	{
		const double T = FMath::Clamp(Alpha, 0.0, 1.0);
		return T * T;
	}

	double YawOf(const FVector& Direction)
	{
		return FMath::RadiansToDegrees(FMath::Atan2(Direction.Y, Direction.X));
	}

	/** Top of a mesh above its origin, in metres, at a uniform scale. */
	float MeshTopM(const UStaticMesh* Mesh, double Scale)
	{
		if (Mesh == nullptr)
		{
			return 0.0f;
		}
		const FBoxSphereBounds Bounds = Mesh->GetBounds();
		return static_cast<float>((Bounds.Origin.Z + Bounds.BoxExtent.Z) * Scale * IronWorld::MetresPerCm);
	}

	/**
	 * Appends a quad lying flat at Center (cm) with U along +X and V along +Y, so M_IronHighlight's flat-top hexagon has
	 * its corners on +-X like the board's hexes. Same vertex order and winding as the engine's procedural box (+Z face).
	 */
	void AppendQuad(TArray<FVector>& Vertices, TArray<int32>& Triangles, TArray<FVector>& Normals, TArray<FVector2D>& Uvs, const FVector& Center, double HalfX, double HalfY)
	{
		const int32 First = Vertices.Num();
		Vertices.Add(Center + FVector(-HalfX, HalfY, 0.0));
		Vertices.Add(Center + FVector(HalfX, HalfY, 0.0));
		Vertices.Add(Center + FVector(HalfX, -HalfY, 0.0));
		Vertices.Add(Center + FVector(-HalfX, -HalfY, 0.0));
		Uvs.Add(FVector2D(0.0, 1.0));
		Uvs.Add(FVector2D(1.0, 1.0));
		Uvs.Add(FVector2D(1.0, 0.0));
		Uvs.Add(FVector2D(0.0, 0.0));
		for (int32 Corner = 0; Corner < 4; ++Corner)
		{
			Normals.Add(FVector::UpVector);
		}
		Triangles.Add(First);
		Triangles.Add(First + 1);
		Triangles.Add(First + 3);
		Triangles.Add(First + 1);
		Triangles.Add(First + 2);
		Triangles.Add(First + 3);
	}

	/** Replaces section 0 of Mesh with one flat quad centred on the component origin. */
	void SetSingleQuad(UProceduralMeshComponent* Mesh, double HalfX, double HalfY)
	{
		if (Mesh == nullptr)
		{
			return;
		}
		TArray<FVector> Vertices;
		TArray<int32> Triangles;
		TArray<FVector> Normals;
		TArray<FVector2D> Uvs;
		AppendQuad(Vertices, Triangles, Normals, Uvs, FVector::ZeroVector, HalfX, HalfY);
		Mesh->CreateMeshSection_LinearColor(0, Vertices, Triangles, Normals, Uvs, TArray<FLinearColor>(), TArray<FProcMeshTangent>(), false);
	}

	/** Thresholds of the noise fields that paint the decorative surroundings, per battle terrain. */
	struct FSurroundTuning
	{
		double Forest;
		double Hill;
		double Mountain;
	};

	FSurroundTuning SurroundTuning(IronSim::ETerrain Terrain)
	{
		switch (Terrain)
		{
		case IronSim::ETerrain::Forest:
			return {-0.08, 0.38, 2.0};
		case IronSim::ETerrain::Hills:
			return {0.30, 0.02, 0.38};
		case IronSim::ETerrain::River:
			return {0.18, 0.34, 2.0};
		case IronSim::ETerrain::Mountains:
			return {0.34, -0.12, 0.16};
		case IronSim::ETerrain::Coast:
			return {0.26, 0.34, 2.0};
		case IronSim::ETerrain::Plains:
		default:
			return {0.22, 0.32, 2.0};
		}
	}
}

AIronBattleBoard3D::AIronBattleBoard3D()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = false;
	// Animations must finish even if something pauses the game, or the battle screen would wait forever.
	PrimaryActorTick.bTickEvenWhenPaused = true;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SceneRoot->SetMobility(EComponentMobility::Movable);
	SetRootComponent(SceneRoot);
}

// ---------------------------------------------------------------------------------------------------------------------
// Availability and creation
// ---------------------------------------------------------------------------------------------------------------------

bool AIronBattleBoard3D::AreAssetsAvailable()
{
	using namespace IronBattleBoard3DDetail;
	if (!FApp::CanEverRender())
	{
		return false;
	}
	IronWorld::FAssetCheckCache& Cache = BoardAssetCheck();
	const double NowSeconds = FPlatformTime::Seconds();
	if (Cache.IsFresh(NowSeconds))
	{
		return Cache.bAvailable;
	}

	FString Missing;
	if (LoadObject<UIronAssetManifest>(nullptr, TEXT("/Game/IronReign/IronReignAssetVersion.IronReignAssetVersion"), nullptr, LOAD_NoWarn | LOAD_Quiet) == nullptr)
	{
		// Written last by Content/Python/ironreign_import.py: without it the import never completed.
		Missing = TEXT("/Game/IronReign/IronReignAssetVersion (run the asset import)");
	}
	for (int32 TerrainIndex = 0; Missing.IsEmpty() && TerrainIndex < TerrainCount; ++TerrainIndex)
	{
		const FString ModelName = HexModelName(TerrainIndex);
		if (IronWorld::LoadModel(ModelName) == nullptr)
		{
			Missing = IronWorld::ModelObjectPath(ModelName);
		}
	}
	const TCHAR* const UnitParts[] = {UnitModels[0], UnitModels[1], UnitModels[2], TEXT("Unit_Base")};
	for (const TCHAR* ModelName : UnitParts)
	{
		if (Missing.IsEmpty() && IronWorld::LoadModel(ModelName) == nullptr)
		{
			Missing = IronWorld::ModelObjectPath(ModelName);
		}
	}
	if (Missing.IsEmpty() && IronWorld::LoadMaterial(TEXT("M_IronTint")) == nullptr)
	{
		Missing = IronWorld::MaterialObjectPath(TEXT("M_IronTint"));
	}
	if (Missing.IsEmpty() && IronWorld::LoadMaterial(TEXT("MI_IronHighlightHex")) == nullptr && IronWorld::LoadMaterial(TEXT("M_IronHighlight")) == nullptr)
	{
		// Without highlights the player could not see where units may move: keep the 2D board.
		Missing = IronWorld::MaterialObjectPath(TEXT("M_IronHighlight"));
	}

	if (Cache.Store(Missing, NowSeconds))
	{
		if (Missing.IsEmpty())
		{
			UE_LOG(LogIronWorld, Log, TEXT("The 3D battle board assets are available now."));
		}
		else
		{
			UE_LOG(LogIronWorld, Log, TEXT("3D battle board unavailable (missing %s); using the 2D hex board (checked again every %.0f s)."), *Missing, IronWorld::FAssetCheckCache::RetrySeconds);
		}
	}
	return Cache.bAvailable;
}

void AIronBattleBoard3D::InvalidateAssetCheck()
{
	IronBattleBoard3DDetail::BoardAssetCheck().Invalidate();
}

AIronBattleBoard3D* AIronBattleBoard3D::FindBoard(UWorld* World)
{
	if (World == nullptr)
	{
		return nullptr;
	}
	for (TActorIterator<AIronBattleBoard3D> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			return *It;
		}
	}
	return nullptr;
}

AIronBattleBoard3D* AIronBattleBoard3D::SpawnBoard(UWorld* World)
{
	if (World == nullptr)
	{
		return nullptr;
	}
	AIronBattleBoard3D* Board = FindBoard(World);
	if (Board == nullptr)
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		SpawnParams.ObjectFlags |= RF_Transient;
		Board = World->SpawnActor<AIronBattleBoard3D>(AIronBattleBoard3D::StaticClass(), FTransform(IronWorld::BoardOrigin()), SpawnParams);
	}
	if (Board != nullptr)
	{
		Board->EnsureInitialized();
	}
	return Board;
}

void AIronBattleBoard3D::EnsureInitialized()
{
	using namespace IronBattleBoard3DDetail;
	UWorld* GameWorld = GetWorld();
	if (bInitialized || GameWorld == nullptr)
	{
		return;
	}
	bInitialized = true;
	SetActorLocation(IronWorld::BoardOrigin());
	LoadAssets();

	// Lighting: the world's shared environment (sun, sky atmosphere, sky light, clouds, fog, post-process). It is
	// spawned here when the strategy map never was. The board's own sun turn runs after the environment's tick.
	Environment = AIronEnvironment::FindOrSpawn(GameWorld);
	if (Environment != nullptr)
	{
		AddTickPrerequisiteActor(Environment.Get());
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.Owner = this;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	SpawnParams.ObjectFlags |= RF_Transient;
	BoardCamera = GameWorld->SpawnActor<ACameraActor>(ACameraActor::StaticClass(), FTransform(IronWorld::BoardOrigin() + FVector(0.0, 10000.0, 10000.0)), SpawnParams);
	if (BoardCamera != nullptr)
	{
		if (UCameraComponent* CameraComponent = BoardCamera->GetCameraComponent())
		{
			CameraComponent->SetFieldOfView(FieldOfViewDegrees);
			CameraComponent->bConstrainAspectRatio = false;
			CameraComponent->bUsePawnControlRotation = false;
			CameraComponent->PostProcessBlendWeight = 1.0f;
			// Battle-specific tilt-shift on the camera (it overrides the environment's map focus while this camera is the
			// view target, so the strategy map's settings are never touched).
			FPostProcessSettings& Settings = CameraComponent->PostProcessSettings;
			Settings.bOverride_DepthOfFieldFocalDistance = true;
			Settings.DepthOfFieldFocalDistance = 0.0f;
			Settings.bOverride_DepthOfFieldFstop = true;
			Settings.DepthOfFieldFstop = 4.0f;
			Settings.bOverride_DepthOfFieldMinFstop = true;
			Settings.DepthOfFieldMinFstop = 0.0f;
			Settings.bOverride_DepthOfFieldSensorWidth = true;
			Settings.DepthOfFieldSensorWidth = static_cast<float>(SensorWidthMm);
			Settings.bOverride_DepthOfFieldFocalRegion = true;
			Settings.DepthOfFieldFocalRegion = 0.0f;
			// A slightly stronger vignette than the map: the eye stays on the board, the surroundings fall off.
			Settings.bOverride_VignetteIntensity = true;
			Settings.VignetteIntensity = 0.5f;
		}
	}

	// Highlight layers: one batched procedural mesh per kind, rebuilt when the highlights change.
	HighlightMeshes.SetNum(LayerCount);
	if (HexHighlightMaterial != nullptr)
	{
		for (int32 LayerIndex = 0; LayerIndex < LayerCount; ++LayerIndex)
		{
			const FLayerStyle& Style = LayerStyles[LayerIndex];
			UProceduralMeshComponent* LayerMesh = CreateQuadComponent(SceneRoot.Get());
			if (UMaterialInstanceDynamic* LayerMaterial = CreateHighlightMaterial(true, Rgb(Style.Rgb, Style.Alpha), Style.RingRadius, Style.RingWidth, Style.FillOpacity, Style.PulseMin, Style.PulseSpeed, Style.Intensity))
			{
				LayerMesh->SetMaterial(0, LayerMaterial);
			}
			LayerMesh->SetTranslucentSortPriority(Style.SortPriority);
			LayerMesh->SetVisibility(false);
			HighlightMeshes[LayerIndex] = LayerMesh;
		}

		const FLayerStyle* const RingStyles[2] = {&HoverStyle, &SelectStyle};
		for (int32 RingIndex = 0; RingIndex < 2; ++RingIndex)
		{
			const FLayerStyle& Style = *RingStyles[RingIndex];
			UProceduralMeshComponent* Ring = CreateQuadComponent(SceneRoot.Get());
			SetSingleQuad(Ring, HexRadiusCm * Style.SizeScale, HexHalfHeightCm * Style.SizeScale);
			if (UMaterialInstanceDynamic* RingMaterial = CreateHighlightMaterial(true, Rgb(Style.Rgb, Style.Alpha), Style.RingRadius, Style.RingWidth, Style.FillOpacity, Style.PulseMin, Style.PulseSpeed, Style.Intensity))
			{
				Ring->SetMaterial(0, RingMaterial);
			}
			Ring->SetTranslucentSortPriority(Style.SortPriority);
			Ring->SetVisibility(false);
			if (RingIndex == 0)
			{
				HoverRing = Ring;
			}
			else
			{
				SelectRing = Ring;
			}
		}
	}

	SetActorHiddenInGame(!bBoardActive);
	SetActorTickEnabled(bBoardActive);
}

void AIronBattleBoard3D::LoadAssets()
{
	using namespace IronBattleBoard3DDetail;
	HexMeshes.Reset();
	for (int32 TerrainIndex = 0; TerrainIndex < TerrainCount; ++TerrainIndex)
	{
		UStaticMesh* Mesh = IronWorld::LoadModel(HexModelName(TerrainIndex));
		if (Mesh == nullptr)
		{
			UE_LOG(LogIronWorld, Warning, TEXT("%s was not imported; SM_Hex_Plain stands in."), *IronWorld::ModelObjectPath(HexModelName(TerrainIndex)));
		}
		HexMeshes.Add(Mesh);
	}
	UnitMeshes.Reset();
	for (const TCHAR* ModelName : UnitModels)
	{
		UnitMeshes.Add(IronWorld::LoadModel(ModelName));
	}
	UnitBaseMesh = IronWorld::LoadModel(TEXT("Unit_Base"));
	FlagMesh = IronWorld::LoadModel(TEXT("Flag"));
	TintMaterial = IronWorld::LoadMaterial(TEXT("M_IronTint"));
	HexHighlightMaterial = IronWorld::LoadMaterial(TEXT("MI_IronHighlightHex"));
	CircleHighlightMaterial = IronWorld::LoadMaterial(TEXT("M_IronHighlight"));
	if (HexHighlightMaterial == nullptr)
	{
		HexHighlightMaterial = CircleHighlightMaterial;
	}
	if (CircleHighlightMaterial == nullptr)
	{
		CircleHighlightMaterial = HexHighlightMaterial;
	}
	if (HexHighlightMaterial == nullptr)
	{
		UE_LOG(LogIronWorld, Warning, TEXT("M_IronHighlight was not imported; the 3D board has no highlights or effects."));
	}
	if (FlagMesh == nullptr)
	{
		UE_LOG(LogIronWorld, Log, TEXT("SM_Flag was not imported; commanders carry no pennant on the 3D board."));
	}
}

UStaticMeshComponent* AIronBattleBoard3D::CreateMeshComponent(UStaticMesh* Mesh, USceneComponent* Parent)
{
	UStaticMeshComponent* Component = NewObject<UStaticMeshComponent>(this);
	Component->SetupAttachment(Parent != nullptr ? Parent : SceneRoot.Get());
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetGenerateOverlapEvents(false);
	Component->SetCanEverAffectNavigation(false);
	Component->SetStaticMesh(Mesh);
	Component->RegisterComponent();
	return Component;
}

UProceduralMeshComponent* AIronBattleBoard3D::CreateQuadComponent(USceneComponent* Parent)
{
	UProceduralMeshComponent* Component = NewObject<UProceduralMeshComponent>(this);
	Component->SetupAttachment(Parent != nullptr ? Parent : SceneRoot.Get());
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetGenerateOverlapEvents(false);
	Component->SetCanEverAffectNavigation(false);
	Component->SetCastShadow(false);
	Component->RegisterComponent();
	return Component;
}

UMaterialInstanceDynamic* AIronBattleBoard3D::CreateHighlightMaterial(bool bHexShape, const FLinearColor& Color, float RingRadius, float RingWidth, float FillOpacity, float PulseMin, float PulseSpeed, float Intensity)
{
	UMaterialInterface* Parent = bHexShape ? HexHighlightMaterial.Get() : CircleHighlightMaterial.Get();
	if (Parent == nullptr)
	{
		return nullptr;
	}
	UMaterialInstanceDynamic* Material = UMaterialInstanceDynamic::Create(Parent, this);
	if (Material != nullptr)
	{
		Material->SetVectorParameterValue(IronBattleBoard3DDetail::ColorParam(), Color);
		IronBattleBoard3DDetail::SetHighlightShape(Material, bHexShape ? 1.0f : 0.0f, RingRadius, RingWidth, FillOpacity, PulseMin, PulseSpeed, Intensity);
	}
	return Material;
}

UInstancedStaticMeshComponent* AIronBattleBoard3D::GetTerrainLayer(int32 TerrainIndex)
{
	using namespace IronBattleBoard3DDetail;
	int32 MeshIndex = TerrainIndex;
	if (!HexMeshes.IsValidIndex(MeshIndex) || HexMeshes[MeshIndex] == nullptr)
	{
		MeshIndex = static_cast<int32>(IronSim::EHexTerrain::Plain);
	}
	if (!HexMeshes.IsValidIndex(MeshIndex) || HexMeshes[MeshIndex] == nullptr)
	{
		return nullptr;
	}
	if (TerrainLayers.Num() < TerrainCount)
	{
		TerrainLayers.SetNum(TerrainCount);
	}
	if (TerrainLayers[MeshIndex] == nullptr)
	{
		UInstancedStaticMeshComponent* TerrainLayer = NewObject<UInstancedStaticMeshComponent>(this);
		TerrainLayer->SetupAttachment(SceneRoot.Get());
		TerrainLayer->SetMobility(EComponentMobility::Movable);
		TerrainLayer->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		TerrainLayer->SetGenerateOverlapEvents(false);
		TerrainLayer->SetCanEverAffectNavigation(false);
		TerrainLayer->SetStaticMesh(HexMeshes[MeshIndex].Get());
		TerrainLayer->RegisterComponent();
		TerrainLayers[MeshIndex] = TerrainLayer;
	}
	return TerrainLayers[MeshIndex].Get();
}

// ---------------------------------------------------------------------------------------------------------------------
// Board
// ---------------------------------------------------------------------------------------------------------------------

void AIronBattleBoard3D::Build(const IronSim::FBattle& Battle)
{
	EnsureInitialized();
	if (!bInitialized)
	{
		return;
	}
	ClearBoard();

	const IronSim::FBattleSetup& BattleSetup = Battle.GetSetup();
	BoardCols = FMath::Max(1, Battle.Cols());
	BoardRows = FMath::Max(1, Battle.Rows());
	MaxDays = FMath::Max(2, BattleSetup.MaxDays);
	BattleSeed = BattleSetup.Seed;
	BattleTerrain = BattleSetup.Terrain;

	TerrainGrid.SetNum(BoardCols * BoardRows);
	for (int32 Row = 0; Row < BoardRows; ++Row)
	{
		for (int32 Col = 0; Col < BoardCols; ++Col)
		{
			TerrainGrid[Row * BoardCols + Col] = static_cast<uint8>(Battle.TerrainAt({Col, Row}));
		}
	}

	// A coast battle's bay touches the top or the bottom row: the open sea continues on that side.
	CoastSide = 0;
	if (BattleTerrain == IronSim::ETerrain::Coast)
	{
		int32 TopWater = 0;
		int32 BottomWater = 0;
		for (int32 Col = 0; Col < BoardCols; ++Col)
		{
			TopWater += StoredTerrain({Col, 0}) == IronSim::EHexTerrain::Water ? 1 : 0;
			BottomWater += StoredTerrain({Col, BoardRows - 1}) == IronSim::EHexTerrain::Water ? 1 : 0;
		}
		CoastSide = TopWater == 0 && BottomWater == 0 ? 0 : (TopWater >= BottomWater ? -1 : 1);
	}

	const int32 GateCount = FMath::Max(0, Battle.GateCount());
	for (int32 GateIndex = 0; GateIndex < GateCount; ++GateIndex)
	{
		const IronSim::FHex GateHex = Battle.GateHexAt(GateIndex);
		if (!InBoard(GateHex))
		{
			continue;
		}
		const bool bBroken = Battle.GateHpAt(GateIndex) <= 0 || Battle.TerrainAt(GateHex) == IronSim::EHexTerrain::Rubble;
		GateHexes.Add(GateHex);
		GateTargetBroken.Add(bBroken);
		GateShownBroken.Add(bBroken);
		GateAppliedBroken.Add(bBroken);
		GateOffsets.Add(FVector::ZeroVector);
	}

	BuildTerrain();
	BuildGround();
	BuildUnits(Battle);

	TArray<IronSim::FHex> AllHexes;
	if (bGridVisible)
	{
		for (int32 Row = 0; Row < BoardRows; ++Row)
		{
			for (int32 Col = 0; Col < BoardCols; ++Col)
			{
				AllHexes.Add({Col, Row});
			}
		}
	}
	FillHexLayer(IronBoard3D::ELayer::Grid, AllHexes);
	Highlights = FIronBoardHighlights();
	BuiltHighlights = FIronBoardHighlights();
	bHighlightsDirty = true;

	TargetDay = Battle.Day();
	GoalDayAlpha = DayAlphaFor(TargetDay);
	DayAlpha = GoalDayAlpha;
	DayAlphaVelocity = 0.0;

	bBuilt = true;
	bUserMovedCamera = false;
	RecomputeFraming();
	ResetView(true);
	SyncFromBattle(Battle);
	SnapToSnapshot();
}

void AIronBattleBoard3D::ClearBoard()
{
	for (IronBoard3D::FTrack& Track : AnimTracks)
	{
		ReleaseQuads(Track.Quads);
		ReleaseLight(Track.Light);
	}
	AnimTracks.Reset();
	AnimCursor = Clock;
	BusyUntil = Clock;
	ReleaseAllEffects();
	DestroyUnits();

	for (const TObjectPtr<UInstancedStaticMeshComponent>& TerrainLayer : TerrainLayers)
	{
		if (TerrainLayer != nullptr)
		{
			TerrainLayer->ClearInstances();
		}
	}
	for (const TObjectPtr<UStaticMeshComponent>& Tile : GateTiles)
	{
		if (Tile != nullptr)
		{
			Tile->DestroyComponent();
		}
	}
	GateTiles.Reset();
	GateHexes.Reset();
	GateTargetBroken.Reset();
	GateShownBroken.Reset();
	GateAppliedBroken.Reset();
	GateOffsets.Reset();

	for (const TObjectPtr<UProceduralMeshComponent>& LayerMesh : HighlightMeshes)
	{
		if (LayerMesh != nullptr)
		{
			LayerMesh->ClearAllMeshSections();
			LayerMesh->SetVisibility(false);
		}
	}
	if (HoverRing != nullptr)
	{
		HoverRing->SetVisibility(false);
	}
	if (SelectRing != nullptr)
	{
		SelectRing->SetVisibility(false);
	}
	TargetBurning.Reset();
	TerrainGrid.Reset();
	bBuilt = false;
}

void AIronBattleBoard3D::BuildTerrain()
{
	using namespace IronBattleBoard3DDetail;
	for (const TObjectPtr<UInstancedStaticMeshComponent>& TerrainLayer : TerrainLayers)
	{
		if (TerrainLayer != nullptr)
		{
			TerrainLayer->ClearInstances();
		}
	}

	// The playable board at Z = 0 (gates are separate tiles).
	for (int32 Row = 0; Row < BoardRows; ++Row)
	{
		for (int32 Col = 0; Col < BoardCols; ++Col)
		{
			const IronSim::FHex Hex = {Col, Row};
			if (GateIndexAt(Hex) < 0)
			{
				AddHexInstance(static_cast<int32>(StoredTerrain(Hex)), Hex, 0.0, false);
			}
		}
	}

	// Decorative surroundings a step lower: the battlefield reads as a raised diorama inside a living landscape.
	for (int32 Row = -SurroundFarRows; Row < BoardRows + SurroundNearRows; ++Row)
	{
		for (int32 Col = -SurroundSideColumns; Col < BoardCols + SurroundSideColumns; ++Col)
		{
			const IronSim::FHex Hex = {Col, Row};
			if (!InBoard(Hex))
			{
				AddHexInstance(static_cast<int32>(SurroundingTerrainAt(Hex)), Hex, -SurroundDropM, true);
			}
		}
	}

	// Gate tiles.
	for (const TObjectPtr<UStaticMeshComponent>& Tile : GateTiles)
	{
		if (Tile != nullptr)
		{
			Tile->DestroyComponent();
		}
	}
	GateTiles.Reset();
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	const FRotator TileRotation(0.0, IronWorld::ModelYawDegrees(ModelParams.FrontYawDegrees, IronWorld::SouthYawDegrees), 0.0);
	const int32 GateMesh = static_cast<int32>(IronSim::EHexTerrain::Gate);
	const int32 RubbleMesh = static_cast<int32>(IronSim::EHexTerrain::Rubble);
	const int32 PlainMesh = static_cast<int32>(IronSim::EHexTerrain::Plain);
	for (int32 GateIndex = 0; GateIndex < GateHexes.Num(); ++GateIndex)
	{
		int32 MeshIndex = GateShownBroken[GateIndex] ? RubbleMesh : GateMesh;
		if (HexMeshes[MeshIndex] == nullptr)
		{
			MeshIndex = PlainMesh;
		}
		UStaticMeshComponent* Tile = CreateMeshComponent(HexMeshes[MeshIndex].Get(), SceneRoot.Get());
		Tile->SetRelativeLocationAndRotation(HexLocalCm(GateHexes[GateIndex]), TileRotation);
		Tile->SetRelativeScale3D(FVector(ModelParams.ScaleOf(HexModelName(MeshIndex))));
		GateTiles.Add(Tile);
		GateAppliedBroken[GateIndex] = GateShownBroken[GateIndex];
	}
}

void AIronBattleBoard3D::AddHexInstance(int32 TerrainIndex, const IronSim::FHex& Hex, double HeightM, bool bDecorative)
{
	using namespace IronBattleBoard3DDetail;
	UInstancedStaticMeshComponent* TerrainLayer = GetTerrainLayer(TerrainIndex);
	if (TerrainLayer == nullptr)
	{
		return;
	}
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	// The hexes keep the Blender frame (corners on +-X, walls along +-Y) after the importer's front-yaw correction.
	double Yaw = IronWorld::ModelYawDegrees(ModelParams.FrontYawDegrees, IronWorld::SouthYawDegrees);
	if (IsNaturalTerrain(TerrainIndex))
	{
		const uint32 Salt = static_cast<uint32>(BattleSeed) ^ (bDecorative ? 0x51u : 0x17u);
		Yaw += 60.0 * static_cast<double>(HexHash(Hex.Col, Hex.Row, Salt) % 6u);
	}
	const int32 MeshTerrain = HexMeshes.IsValidIndex(TerrainIndex) && HexMeshes[TerrainIndex] != nullptr ? TerrainIndex : static_cast<int32>(IronSim::EHexTerrain::Plain);
	const double Scale = ModelParams.ScaleOf(HexModelName(MeshTerrain));
	TerrainLayer->AddInstance(FTransform(FRotator(0.0, Yaw, 0.0), HexLocalCm(Hex, HeightM), FVector(Scale)), false);
}

IronSim::EHexTerrain AIronBattleBoard3D::SurroundingTerrainAt(const IronSim::FHex& Hex) const
{
	using namespace IronBattleBoard3DDetail;
	using IronSim::EHexTerrain;
	const IronSim::FHex Nearest = {FMath::Clamp(Hex.Col, 0, BoardCols - 1), FMath::Clamp(Hex.Row, 0, BoardRows - 1)};
	const EHexTerrain Edge = StoredTerrain(Nearest);
	const bool bAboveOrBelow = Hex.Col == Nearest.Col;
	const bool bBeside = Hex.Row == Nearest.Row;
	const int32 Ring = IronSim::HexMath::Distance(Hex, Nearest);
	const bool bEdgeIsGate = GateIndexAt(Nearest) >= 0;

	// Features that run off the board continue: the river and the sea, the city wall, the town, the road.
	if (bAboveOrBelow)
	{
		if (Edge == EHexTerrain::Water || Edge == EHexTerrain::Ford || Edge == EHexTerrain::Bridge)
		{
			return EHexTerrain::Water;
		}
		if (Edge == EHexTerrain::Wall || bEdgeIsGate)
		{
			return EHexTerrain::Wall;
		}
	}
	if (Edge == EHexTerrain::Town || Edge == EHexTerrain::Castle)
	{
		return EHexTerrain::Town;
	}
	if (bBeside && (Edge == EHexTerrain::Road || Edge == EHexTerrain::Bridge))
	{
		return EHexTerrain::Road;
	}
	if (Edge == EHexTerrain::Water && !bAboveOrBelow)
	{
		return EHexTerrain::Water;
	}
	// Coast: the open sea beyond a beach row on the bay's side.
	if (CoastSide != 0)
	{
		const int32 RowsOut = CoastSide < 0 ? -Hex.Row : Hex.Row - (BoardRows - 1);
		if (RowsOut >= 2)
		{
			return EHexTerrain::Water;
		}
		if (RowsOut == 1)
		{
			return EHexTerrain::Plain;
		}
	}

	// Natural landscape from two smooth noise fields, clustered like the board's own forests and hills.
	const FSurroundTuning Tuning = SurroundTuning(BattleTerrain);
	const FVector2D LocalM = HexToLocalM(Hex);
	const double SeedX = static_cast<double>(BattleSeed % 997u) * 0.37;
	const double SeedY = static_cast<double>((BattleSeed / 997u) % 991u) * 0.53;
	const double Wood = static_cast<double>(FMath::PerlinNoise2D(FVector2D(LocalM.X * 0.045 + SeedX, LocalM.Y * 0.045 + SeedY)));
	const double Relief = static_cast<double>(FMath::PerlinNoise2D(FVector2D(LocalM.X * 0.035 + SeedY + 31.7, LocalM.Y * 0.035 + SeedX + 11.3)));
	if (Ring >= 2 && Relief > Tuning.Mountain)
	{
		return EHexTerrain::Mountain;
	}
	if (Relief > Tuning.Hill || (Edge == EHexTerrain::Mountain && Ring <= 2))
	{
		return EHexTerrain::Hill;
	}
	if (Wood > Tuning.Forest)
	{
		return EHexTerrain::Forest;
	}
	return EHexTerrain::Plain;
}

void AIronBattleBoard3D::BuildGround()
{
	using namespace IronBattleBoard3DDetail;
	if (Ground == nullptr)
	{
		UStaticMesh* SlabMesh = IronWorld::LoadCubeMesh();
		if (SlabMesh == nullptr)
		{
			UE_LOG(LogIronWorld, Warning, TEXT("Neither SM_IronCube nor the engine cube loads; the 3D board has no ground around it."));
			return;
		}
		Ground = NewObject<UInstancedStaticMeshComponent>(this);
		Ground->SetupAttachment(SceneRoot.Get());
		Ground->SetMobility(EComponentMobility::Movable);
		Ground->SetCollisionEnabled(ECollisionEnabled::NoCollision);
		Ground->SetGenerateOverlapEvents(false);
		Ground->SetCanEverAffectNavigation(false);
		Ground->SetStaticMesh(SlabMesh);
		// M_IronTint carries the instanced-static-mesh usage flag (a cooked game cannot add it later).
		UMaterialInterface* GroundParent = TintMaterial.Get();
		if (GroundParent == nullptr)
		{
			GroundParent = IronWorld::LoadEngineMaterial(IronWorld::EngineBasicShapeMaterialPath);
		}
		if (GroundParent != nullptr)
		{
			GroundMaterial = UMaterialInstanceDynamic::Create(GroundParent, this);
			if (GroundMaterial != nullptr)
			{
				GroundMaterial->SetScalarParameterValue(FName(TEXT("Roughness")), 0.95f);
				Ground->SetMaterial(0, GroundMaterial.Get());
			}
		}
		Ground->RegisterComponent();

		// Fit the mesh's bounding box (whatever its pivot) to a slab whose top face lies at the component origin.
		const FBoxSphereBounds SlabBounds = SlabMesh->GetBounds();
		const FVector SlabSizeCm = SlabBounds.BoxExtent * 2.0;
		const double TileCm = GroundSizeM / static_cast<double>(GroundTiles) * IronWorld::CmPerMetre;
		const FVector TileScale(TileCm / FMath::Max(1.0, SlabSizeCm.X), TileCm / FMath::Max(1.0, SlabSizeCm.Y), GroundThicknessM * IronWorld::CmPerMetre / FMath::Max(1.0, SlabSizeCm.Z));
		const double HalfGroundCm = GroundSizeM * 0.5 * IronWorld::CmPerMetre;
		TArray<FTransform> Tiles;
		Tiles.Reserve(GroundTiles * GroundTiles);
		for (int32 TileY = 0; TileY < GroundTiles; ++TileY)
		{
			for (int32 TileX = 0; TileX < GroundTiles; ++TileX)
			{
				const FVector TileCentre((static_cast<double>(TileX) + 0.5) * TileCm - HalfGroundCm, (static_cast<double>(TileY) + 0.5) * TileCm - HalfGroundCm, 0.0);
				const FVector Pivot(TileCentre.X - SlabBounds.Origin.X * TileScale.X, TileCentre.Y - SlabBounds.Origin.Y * TileScale.Y, -(SlabBounds.Origin.Z + SlabBounds.BoxExtent.Z) * TileScale.Z);
				Tiles.Add(FTransform(FRotator::ZeroRotator, Pivot, TileScale));
			}
		}
		Ground->AddInstances(Tiles, false);
	}
	const FVector2D CentreM = HexToLocalM({BoardCols / 2, BoardRows / 2});
	Ground->SetRelativeLocation(FVector(CentreM.X * IronWorld::CmPerMetre, CentreM.Y * IronWorld::CmPerMetre, -GroundDropM * IronWorld::CmPerMetre));
	Ground->SetVisibility(true);
	if (GroundMaterial != nullptr)
	{
		const FLinearColor Color = GroundColorForSeason();
		GroundMaterial->SetVectorParameterValue(TintParam(), Color);
		GroundMaterial->SetVectorParameterValue(ColorParam(), Color);
	}
}

void AIronBattleBoard3D::BuildUnits(const IronSim::FBattle& Battle)
{
	using namespace IronBattleBoard3DDetail;
	DestroyUnits();
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	// Models face the unit root's +X (its facing); the root turns with the unit.
	const FRotator ModelRotation(0.0, IronWorld::ModelYawDegrees(ModelParams.FrontYawDegrees, 0.0), 0.0);
	const IronSim::FBattleSetup& BattleSetup = Battle.GetSetup();
	const std::vector<IronSim::FBattleUnit>& BattleUnits = Battle.Units();

	UnitVisuals.SetNum(static_cast<int32>(BattleUnits.size()));
	for (int32 UnitId = 0; UnitId < UnitVisuals.Num(); ++UnitId)
	{
		const IronSim::FBattleUnit& BattleUnit = BattleUnits[static_cast<size_t>(UnitId)];
		FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
		Visual = FIronBoardUnitVisual();
		Visual.Side = BattleUnit.Side == 0 ? 0 : 1;
		Visual.TroopType = FMath::Clamp(static_cast<int32>(BattleUnit.Setup.Type), 0, TroopTypeCount - 1);
		Visual.bCommander = BattleUnit.bCommander;
		Visual.RestHex = BattleUnit.Pos;
		Visual.TargetHex = BattleUnit.Pos;
		Visual.bTargetOnField = BattleUnit.IsActive();
		Visual.bShown = Visual.bTargetOnField;
		Visual.bAppliedShown = true;
		Visual.Yaw = Visual.Side == 0 ? 0.0f : 180.0f;
		Visual.Location = HexLocalCm(Visual.RestHex);

		USceneComponent* UnitRoot = NewObject<USceneComponent>(this);
		UnitRoot->SetupAttachment(SceneRoot.Get());
		UnitRoot->SetMobility(EComponentMobility::Movable);
		UnitRoot->RegisterComponent();
		UnitRoot->SetRelativeLocationAndRotation(Visual.Location, FRotator(0.0, Visual.Yaw, 0.0));
		Visual.Root = UnitRoot;

		const FLinearColor SideColor = IronWorld::ColorFromRGB(BattleSetup.Sides[Visual.Side].Color);
		float TopM = 2.5f;
		// The squad and its pennant stand on top of the plinth (a thin disc; capped in case a model is taller).
		double PlinthTopCm = 0.0;
		if (UnitBaseMesh != nullptr)
		{
			const double Scale = ModelParams.ScaleOf(TEXT("Unit_Base"));
			Visual.Base = CreateMeshComponent(UnitBaseMesh.Get(), UnitRoot);
			Visual.Base->SetRelativeRotation(ModelRotation);
			Visual.Base->SetRelativeScale3D(FVector(Scale));
			PlinthTopCm = FMath::Clamp(static_cast<double>(MeshTopM(UnitBaseMesh.Get(), Scale)) * IronWorld::CmPerMetre, 0.0, MaxPlinthLiftCm);
		}
		UStaticMesh* FigureMesh = UnitMeshes.IsValidIndex(Visual.TroopType) ? UnitMeshes[Visual.TroopType].Get() : nullptr;
		for (int32 Fallback = 0; FigureMesh == nullptr && Fallback < UnitMeshes.Num(); ++Fallback)
		{
			FigureMesh = UnitMeshes[Fallback].Get();
		}
		if (FigureMesh != nullptr)
		{
			const double Scale = ModelParams.ScaleOf(UnitModels[Visual.TroopType]);
			Visual.Figure = CreateMeshComponent(FigureMesh, UnitRoot);
			Visual.Figure->SetRelativeLocationAndRotation(FVector(0.0, 0.0, PlinthTopCm), ModelRotation);
			Visual.Figure->SetRelativeScale3D(FVector(Scale));
			TopM = FMath::Max(TopM, static_cast<float>(PlinthTopCm * IronWorld::MetresPerCm) + MeshTopM(FigureMesh, Scale));
		}
		if (Visual.bCommander && FlagMesh != nullptr)
		{
			// A small pennant behind the squad, on its right: the commander reads at a glance.
			const double Scale = FlagScale * ModelParams.ScaleOf(TEXT("Flag"));
			Visual.Flag = CreateMeshComponent(FlagMesh.Get(), UnitRoot);
			Visual.Flag->SetRelativeLocationAndRotation(FVector(FlagBackCm, FlagSideCm, PlinthTopCm), ModelRotation);
			Visual.Flag->SetRelativeScale3D(FVector(Scale));
			TopM = FMath::Max(TopM, static_cast<float>(PlinthTopCm * IronWorld::MetresPerCm) + MeshTopM(FlagMesh.Get(), Scale));
		}
		Visual.TopM = TopM;
		Visual.SideColor = SideColor;

		// Side colour on every Tint slot, then a dynamic instance on every other figure / plinth slot for the hit flash.
		UStaticMeshComponent* const Parts[3] = {Visual.Figure.Get(), Visual.Base.Get(), Visual.Flag.Get()};
		TObjectPtr<UMaterialInstanceDynamic>* const PartTints[3] = {&Visual.FigureTint, &Visual.BaseTint, &Visual.FlagTint};
		for (int32 PartIndex = 0; PartIndex < 3; ++PartIndex)
		{
			UStaticMeshComponent* Part = Parts[PartIndex];
			if (Part == nullptr)
			{
				continue;
			}
			if (UMaterialInstanceDynamic* Tint = IronWorld::ApplyTint(Part, SideColor, nullptr, TintMaterial.Get()))
			{
				*PartTints[PartIndex] = Tint;
				Visual.Materials.AddUnique(Tint);
			}
			if (Part == Visual.Flag.Get())
			{
				continue;
			}
			for (int32 SlotIndex = 0; SlotIndex < Part->GetNumMaterials(); ++SlotIndex)
			{
				UMaterialInterface* SlotMaterial = Part->GetMaterial(SlotIndex);
				UMaterialInstanceDynamic* Dynamic = Cast<UMaterialInstanceDynamic>(SlotMaterial);
				if (Dynamic == nullptr && SlotMaterial != nullptr)
				{
					Dynamic = Part->CreateDynamicMaterialInstance(SlotIndex, SlotMaterial);
				}
				if (Dynamic != nullptr)
				{
					Visual.Materials.AddUnique(Dynamic);
				}
			}
		}
	}
}

void AIronBattleBoard3D::DestroyUnits()
{
	for (FIronBoardUnitVisual& Visual : UnitVisuals)
	{
		ReleaseQuad(Visual.HaloQuad);
		Visual.HaloQuad = INDEX_NONE;
		UStaticMeshComponent* const Parts[3] = {Visual.Figure.Get(), Visual.Base.Get(), Visual.Flag.Get()};
		for (UStaticMeshComponent* Part : Parts)
		{
			if (Part != nullptr)
			{
				Part->DestroyComponent();
			}
		}
		if (Visual.Root != nullptr)
		{
			Visual.Root->DestroyComponent();
		}
	}
	UnitVisuals.Reset();
}

void AIronBattleBoard3D::FillHexLayer(IronBoard3D::ELayer Layer, const TArray<IronSim::FHex>& Hexes)
{
	using namespace IronBattleBoard3DDetail;
	const int32 LayerIndex = static_cast<int32>(Layer);
	if (!HighlightMeshes.IsValidIndex(LayerIndex) || HighlightMeshes[LayerIndex] == nullptr)
	{
		return;
	}
	UProceduralMeshComponent* LayerMesh = HighlightMeshes[LayerIndex].Get();
	const FLayerStyle& Style = LayerStyles[LayerIndex];
	TArray<FVector> Vertices;
	TArray<int32> Triangles;
	TArray<FVector> Normals;
	TArray<FVector2D> Uvs;
	TArray<IronSim::FHex> Added;
	for (const IronSim::FHex& Hex : Hexes)
	{
		if (!InBoard(Hex) || Added.Contains(Hex))
		{
			continue;
		}
		Added.Add(Hex);
		AppendQuad(Vertices, Triangles, Normals, Uvs, HexLocalCm(Hex) + FVector(0.0, 0.0, Style.LiftCm), HexRadiusCm * Style.SizeScale, HexHalfHeightCm * Style.SizeScale);
	}
	LayerMesh->ClearAllMeshSections();
	if (Vertices.Num() > 0)
	{
		LayerMesh->CreateMeshSection_LinearColor(0, Vertices, Triangles, Normals, Uvs, TArray<FLinearColor>(), TArray<FProcMeshTangent>(), false);
	}
	LayerMesh->SetVisibility(Vertices.Num() > 0);
}

void AIronBattleBoard3D::RefreshHighlightLayers()
{
	if (!bHighlightsDirty || !bBuilt)
	{
		return;
	}
	bHighlightsDirty = false;
	if (Highlights.Reachable != BuiltHighlights.Reachable)
	{
		FillHexLayer(IronBoard3D::ELayer::Reachable, Highlights.Reachable);
	}
	if (Highlights.AttackTargets != BuiltHighlights.AttackTargets)
	{
		FillHexLayer(IronBoard3D::ELayer::Attack, Highlights.AttackTargets);
	}
	if (Highlights.TacticTargets != BuiltHighlights.TacticTargets)
	{
		FillHexLayer(IronBoard3D::ELayer::Tactic, Highlights.TacticTargets);
	}
	if (Highlights.DuelTargets != BuiltHighlights.DuelTargets)
	{
		FillHexLayer(IronBoard3D::ELayer::Duel, Highlights.DuelTargets);
	}
	BuiltHighlights = Highlights;
}

void AIronBattleBoard3D::SetActive(bool bInActive, float BlendSeconds)
{
	if (!bInActive && !bBoardActive)
	{
		// Redundant or late deactivation (EnsureInitialized already hid the board): leave world rendering to whichever
		// scene is showing.
		return;
	}
	if (bInActive)
	{
		EnsureInitialized();
	}
	if (!bInActive && bBoardActive)
	{
		FinishAnimations();
		ReleaseAllEffects();
		RestoreSun();
	}
	bBoardActive = bInActive;
	SetActorHiddenInGame(!bBoardActive);
	SetActorTickEnabled(bBoardActive);

	UWorld* GameWorld = GetWorld();
	if (GameWorld != nullptr)
	{
		if (UGameViewportClient* GameViewport = GameWorld->GetGameViewport())
		{
			// AIronReignPlayerController disables world rendering for the pure-Slate screens. Hiding the board only turns
			// it off when the strategy map is not the scene on screen.
			const AIronWorldMap3D* ActiveMap = bBoardActive ? nullptr : AIronWorldMap3D::FindMap(GameWorld);
			if (bBoardActive || ActiveMap == nullptr || !ActiveMap->IsMapActive())
			{
				GameViewport->bDisableWorldRendering = !bBoardActive;
			}
		}
	}
	if (!bBoardActive)
	{
		return;
	}

	APlayerController* Controller = GetLocalController();
	if (Controller != nullptr && BoardCamera != nullptr)
	{
		// Blend only from a nearby view: the strategy map is 100 km away, a blend would sweep over open sea.
		const APlayerCameraManager* CameraManager = Controller->PlayerCameraManager;
		const bool bNearby = CameraManager != nullptr
			&& FVector::DistSquared(CameraManager->GetCameraLocation(), BoardCamera->GetActorLocation()) < FMath::Square(IronBattleBoard3DDetail::BlendMaxDistanceCm);
		Controller->SetViewTargetWithBlend(BoardCamera.Get(), bNearby ? FMath::Max(0.0f, BlendSeconds) : 0.0f, EViewTargetBlendFunction::VTBlend_EaseInOut, 2.0f, false);
	}
	// The sun starts at the current day instead of sweeping in from wherever the map left it.
	DayAlpha = GoalDayAlpha;
	DayAlphaVelocity = 0.0;
	if (bBuilt)
	{
		SnapToSnapshot();
	}
	UpdateCamera(0.0f);
	UpdateSun(0.0f);
}

void AIronBattleBoard3D::SetSeason(int32 Month)
{
	SeasonMonth = FMath::Clamp(Month, 1, 12);
	EnsureInitialized();
	if (Environment != nullptr)
	{
		Environment->SetSeason(SeasonMonth, true);
		// The environment just placed its sun for the new season: that is what the strategy map gets back later.
		if (bSunOverridden && Environment->GetSun() != nullptr)
		{
			SavedSunRotation = Environment->GetSun()->GetComponentRotation();
		}
	}
	if (GroundMaterial != nullptr)
	{
		const FLinearColor Color = GroundColorForSeason();
		GroundMaterial->SetVectorParameterValue(IronBattleBoard3DDetail::TintParam(), Color);
		GroundMaterial->SetVectorParameterValue(IronBattleBoard3DDetail::ColorParam(), Color);
	}
}

void AIronBattleBoard3D::SetQuality(int32 Level)
{
	QualityLevel = FMath::Clamp(Level, 0, 3);
	if (Environment != nullptr)
	{
		Environment->SetQuality(QualityLevel);
	}
	for (const FIronBoardLight& Entry : LightPool)
	{
		if (Entry.Light != nullptr)
		{
			Entry.Light->SetCastShadows(QualityLevel >= 3);
		}
	}
}

void AIronBattleBoard3D::SetGridVisible(bool bVisible)
{
	bGridVisible = bVisible;
	TArray<IronSim::FHex> AllHexes;
	if (bGridVisible && bBuilt)
	{
		for (int32 Row = 0; Row < BoardRows; ++Row)
		{
			for (int32 Col = 0; Col < BoardCols; ++Col)
			{
				AllHexes.Add({Col, Row});
			}
		}
	}
	FillHexLayer(IronBoard3D::ELayer::Grid, AllHexes);
}

void AIronBattleBoard3D::SetDimActedUnits(bool bDim)
{
	bDimActedUnits = bDim;
	if (!bBoardActive)
	{
		// Inactive boards do not tick: apply the look now.
		ApplyUnitTransforms(1.0f);
	}
}

void AIronBattleBoard3D::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	// Whoever ends the board, the screens get their state back: deactivated like SetActive(false), so the shared sun
	// returns to the map's season and world rendering stays on only when the strategy map is the scene.
	SetActive(false);
	RestoreSun();
	if (EndPlayReason == EEndPlayReason::Destroyed || EndPlayReason == EEndPlayReason::RemovedFromWorld)
	{
		// The battle camera is about to go: give the view back to the controller (a world tearing down needs none).
		APlayerController* Controller = GetLocalController();
		if (IsValid(Controller) && BoardCamera != nullptr && Controller->GetViewTarget() == BoardCamera.Get())
		{
			Controller->SetViewTargetWithBlend(Controller, 0.0f);
		}
	}
	if (EndPlayReason == EEndPlayReason::Destroyed && BoardCamera != nullptr)
	{
		BoardCamera->Destroy();
	}
	BoardCamera = nullptr;
	Super::EndPlay(EndPlayReason);
}

// ---------------------------------------------------------------------------------------------------------------------
// Grid queries and board math
// ---------------------------------------------------------------------------------------------------------------------

FVector2D AIronBattleBoard3D::HexToLocalM(const IronSim::FHex& Hex)
{
	return IronWorld::HexToBoardLocalM(Hex.Col, Hex.Row);
}

bool AIronBattleBoard3D::LocalMToHex(const FVector2D& LocalM, int32 Cols, int32 Rows, IronSim::FHex& OutHex)
{
	// HexMath pixels put the board's top-left corner at the origin, so hex (0,0) is centred at (R, R * sqrt(3) / 2).
	const double Radius = IronWorld::HexRadiusM;
	const double PixelX = LocalM.X + Radius;
	const double PixelY = LocalM.Y + Radius * 0.5 * IronBattleBoard3DDetail::SqrtThree;
	OutHex = IronSim::HexMath::FromPixel(static_cast<float>(PixelX), static_cast<float>(PixelY), static_cast<float>(Radius));
	return OutHex.Col >= 0 && OutHex.Row >= 0 && OutHex.Col < Cols && OutHex.Row < Rows;
}

bool AIronBattleBoard3D::InBoard(const IronSim::FHex& Hex) const
{
	return Hex.Col >= 0 && Hex.Row >= 0 && Hex.Col < BoardCols && Hex.Row < BoardRows;
}

IronSim::EHexTerrain AIronBattleBoard3D::StoredTerrain(const IronSim::FHex& Hex) const
{
	const int32 Index = Hex.Row * BoardCols + Hex.Col;
	if (!InBoard(Hex) || !TerrainGrid.IsValidIndex(Index))
	{
		return IronSim::EHexTerrain::Plain;
	}
	return static_cast<IronSim::EHexTerrain>(TerrainGrid[Index]);
}

FVector AIronBattleBoard3D::HexLocalCm(const IronSim::FHex& Hex, double HeightM) const
{
	const FVector2D LocalM = HexToLocalM(Hex);
	return FVector(LocalM.X * IronWorld::CmPerMetre, LocalM.Y * IronWorld::CmPerMetre, HeightM * IronWorld::CmPerMetre);
}

FVector AIronBattleBoard3D::HexToWorldLocation(const IronSim::FHex& Hex, float HeightM) const
{
	return GetActorLocation() + HexLocalCm(Hex, static_cast<double>(HeightM));
}

int32 AIronBattleBoard3D::GateIndexAt(const IronSim::FHex& Hex) const
{
	for (int32 GateIndex = 0; GateIndex < GateHexes.Num(); ++GateIndex)
	{
		if (GateHexes[GateIndex] == Hex)
		{
			return GateIndex;
		}
	}
	return INDEX_NONE;
}

bool AIronBattleBoard3D::IsValidUnit(int32 UnitId) const
{
	return UnitVisuals.IsValidIndex(UnitId);
}

TArray<IronSim::FHex> AIronBattleBoard3D::FindPath(const IronSim::FHex& From, const IronSim::FHex& To, int32 UnitId) const
{
	using IronSim::EHexTerrain;
	TArray<IronSim::FHex> Path;
	if (!InBoard(From) || !InBoard(To) || From == To)
	{
		Path.Add(From);
		Path.Add(To);
		return Path;
	}

	// Cheapest route over the terrain costs of DESIGN.md section 4 (cavalry pay more in rough ground), around enemy
	// units, walls, intact gates (defenders pass their own) and burning hexes. Matches the rules engine closely enough
	// for animation; the destination is always enterable.
	const int32 MoverSide = IsValidUnit(UnitId) ? UnitVisuals[UnitId].Side : 0;
	const bool bCavalry = IsValidUnit(UnitId) && UnitVisuals[UnitId].TroopType == static_cast<int32>(IronSim::ETroopType::Cavalry);
	const auto StepCost = [this, MoverSide, bCavalry, UnitId](const IronSim::FHex& Candidate) -> int32
	{
		int32 TerrainCost = -1;
		const int32 Gate = GateIndexAt(Candidate);
		if (Gate >= 0)
		{
			TerrainCost = GateShownBroken[Gate] ? (bCavalry ? 3 : 2) : (MoverSide == 1 ? 1 : -1);
		}
		else
		{
			switch (StoredTerrain(Candidate))
			{
			case EHexTerrain::Plain:
			case EHexTerrain::Road:
			case EHexTerrain::Town:
			case EHexTerrain::Bridge:
			case EHexTerrain::Castle:
				TerrainCost = 1;
				break;
			case EHexTerrain::Forest:
			case EHexTerrain::Hill:
			case EHexTerrain::Rubble:
				TerrainCost = bCavalry ? 3 : 2;
				break;
			case EHexTerrain::Ford:
				TerrainCost = 3;
				break;
			default:
				TerrainCost = -1;
				break;
			}
		}
		if (TerrainCost < 0 || TargetBurning.Contains(Candidate))
		{
			return -1;
		}
		for (int32 OtherId = 0; OtherId < UnitVisuals.Num(); ++OtherId)
		{
			const FIronBoardUnitVisual& Other = UnitVisuals[OtherId];
			if (OtherId != UnitId && Other.bShown && Other.Side != MoverSide && Other.RestHex == Candidate)
			{
				return -1;
			}
		}
		return TerrainCost;
	};

	const int32 CellCount = BoardCols * BoardRows;
	const int32 StartIndex = From.Row * BoardCols + From.Col;
	const int32 GoalIndex = To.Row * BoardCols + To.Col;
	TArray<int32> Cost;
	TArray<int32> Previous;
	TArray<bool> Settled;
	Cost.Init(MAX_int32, CellCount);
	Previous.Init(INDEX_NONE, CellCount);
	Settled.Init(false, CellCount);
	Cost[StartIndex] = 0;
	for (int32 Iteration = 0; Iteration < CellCount; ++Iteration)
	{
		int32 Best = INDEX_NONE;
		for (int32 Index = 0; Index < CellCount; ++Index)
		{
			if (!Settled[Index] && Cost[Index] != MAX_int32 && (Best == INDEX_NONE || Cost[Index] < Cost[Best]))
			{
				Best = Index;
			}
		}
		if (Best == INDEX_NONE || Best == GoalIndex)
		{
			break;
		}
		Settled[Best] = true;
		IronSim::FHex Around[6];
		IronSim::HexMath::Neighbors({Best % BoardCols, Best / BoardCols}, Around);
		for (const IronSim::FHex& Next : Around)
		{
			if (!InBoard(Next))
			{
				continue;
			}
			const int32 NextIndex = Next.Row * BoardCols + Next.Col;
			int32 Step = StepCost(Next);
			if (NextIndex == GoalIndex)
			{
				Step = FMath::Max(1, Step);
			}
			if (Step < 0 || Settled[NextIndex] || Cost[Best] + Step >= Cost[NextIndex])
			{
				continue;
			}
			Cost[NextIndex] = Cost[Best] + Step;
			Previous[NextIndex] = Best;
		}
	}

	if (Previous[GoalIndex] != INDEX_NONE)
	{
		for (int32 Index = GoalIndex; Index != INDEX_NONE && Path.Num() <= CellCount; Index = Previous[Index])
		{
			Path.Add({Index % BoardCols, Index / BoardCols});
		}
		Algo::Reverse(Path);
		if (Path.Num() >= 2 && Path[0] == From)
		{
			return Path;
		}
	}

	// No route on the stored board (it changed under us): follow the straight line, hex by hex.
	Path.Reset();
	Path.Add(From);
	const FVector2D StartM = HexToLocalM(From);
	const FVector2D EndM = HexToLocalM(To);
	const int32 Samples = FMath::Max(2, IronSim::HexMath::Distance(From, To) * 4);
	for (int32 Sample = 1; Sample <= Samples; ++Sample)
	{
		IronSim::FHex Step;
		LocalMToHex(StartM + (EndM - StartM) * (static_cast<double>(Sample) / static_cast<double>(Samples)), BoardCols, BoardRows, Step);
		if (Step != Path.Last())
		{
			Path.Add(Step);
		}
	}
	if (Path.Last() != To)
	{
		Path.Add(To);
	}
	return Path;
}

// ---------------------------------------------------------------------------------------------------------------------
// Battle state
// ---------------------------------------------------------------------------------------------------------------------

void AIronBattleBoard3D::SyncFromBattle(const IronSim::FBattle& Battle)
{
	if (!bBuilt || Battle.Cols() != BoardCols || Battle.Rows() != BoardRows || static_cast<int32>(Battle.Units().size()) != UnitVisuals.Num())
	{
		Build(Battle);
		return;
	}

	const std::vector<IronSim::FBattleUnit>& BattleUnits = Battle.Units();
	for (int32 UnitId = 0; UnitId < UnitVisuals.Num(); ++UnitId)
	{
		const IronSim::FBattleUnit& BattleUnit = BattleUnits[static_cast<size_t>(UnitId)];
		FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
		Visual.TargetHex = BattleUnit.Pos;
		Visual.bTargetOnField = BattleUnit.IsActive();
		Visual.bTargetConfused = BattleUnit.IsActive() && BattleUnit.ConfusedDays > 0;
		// The battle screen's rule for dimmed unit plates: acted, on the side to move, while the battle runs.
		Visual.bTargetActed = BattleUnit.IsActive() && BattleUnit.bActed && BattleUnit.Side == Battle.ActiveSide() && !Battle.IsOver();
	}

	TargetBurning.Reset();
	bool bTerrainChanged = false;
	for (int32 Row = 0; Row < BoardRows; ++Row)
	{
		for (int32 Col = 0; Col < BoardCols; ++Col)
		{
			const IronSim::FHex Hex = {Col, Row};
			if (Battle.BurningAt(Hex) > 0)
			{
				TargetBurning.Add(Hex);
			}
			if (GateIndexAt(Hex) < 0)
			{
				const uint8 Terrain = static_cast<uint8>(Battle.TerrainAt(Hex));
				uint8& Stored = TerrainGrid[Row * BoardCols + Col];
				if (Stored != Terrain)
				{
					Stored = Terrain;
					bTerrainChanged = true;
				}
			}
		}
	}

	for (int32 GateIndex = 0; GateIndex < GateHexes.Num(); ++GateIndex)
	{
		// The battle lists its gates in a fixed order; match by hex in case a scripted board differs.
		bool bBroken = Battle.TerrainAt(GateHexes[GateIndex]) == IronSim::EHexTerrain::Rubble;
		for (int32 BattleGate = 0; BattleGate < Battle.GateCount(); ++BattleGate)
		{
			if (Battle.GateHexAt(BattleGate) == GateHexes[GateIndex])
			{
				bBroken = bBroken || Battle.GateHpAt(BattleGate) <= 0;
			}
		}
		GateTargetBroken[GateIndex] = bBroken;
	}

	if (bTerrainChanged)
	{
		BuildTerrain();
	}
	if (Battle.Day() != TargetDay)
	{
		TargetDay = Battle.Day();
		GoalDayAlpha = DayAlphaFor(TargetDay);
	}
	if (!bBoardActive)
	{
		SnapToSnapshot();
	}
}

void AIronBattleBoard3D::SnapToSnapshot()
{
	for (FIronBoardUnitVisual& Visual : UnitVisuals)
	{
		if (InBoard(Visual.TargetHex))
		{
			Visual.RestHex = Visual.TargetHex;
		}
		Visual.bShown = Visual.bTargetOnField;
		Visual.Location = HexLocalCm(Visual.RestHex);
		Visual.Offset = FVector::ZeroVector;
		Visual.Shrink = 1.0f;
		Visual.Flash = 0.0f;
		Visual.bYawDriven = false;
	}
	ApplyUnitTransforms(1.0f);
	for (int32 GateIndex = 0; GateIndex < GateHexes.Num(); ++GateIndex)
	{
		GateShownBroken[GateIndex] = GateTargetBroken[GateIndex];
		GateOffsets[GateIndex] = FVector::ZeroVector;
	}
	UpdateGates();
	if (bBoardActive)
	{
		UpdateBurning();
		UpdateHalos();
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Event animation
// ---------------------------------------------------------------------------------------------------------------------

TArray<FIronBoardEventTiming> AIronBattleBoard3D::PlayEvents(const TArray<IronSim::FBattleEvent>& Events)
{
	TArray<FIronBoardEventTiming> Timings;
	Timings.Reserve(Events.Num());
	for (const IronSim::FBattleEvent& Event : Events)
	{
		Timings.Add(PlayEvent(Event));
	}
	return Timings;
}

TArray<FIronBoardEventTiming> AIronBattleBoard3D::PlayEvents(const std::vector<IronSim::FBattleEvent>& Events)
{
	TArray<FIronBoardEventTiming> Timings;
	Timings.Reserve(static_cast<int32>(Events.size()));
	for (const IronSim::FBattleEvent& Event : Events)
	{
		Timings.Add(PlayEvent(Event));
	}
	return Timings;
}

void AIronBattleBoard3D::AddTrack(IronBoard3D::FTrack&& Track)
{
	if (Track.bBlocking)
	{
		BusyUntil = FMath::Max(BusyUntil, Track.Start + Track.Duration);
	}
	AnimTracks.Add(MoveTemp(Track));
}

void AIronBattleBoard3D::QueueHit(int32 UnitId, const IronSim::FHex& Hex, double Start, float Strength, const FLinearColor& Color)
{
	IronBoard3D::FTrack Impact;
	Impact.Kind = IronBoard3D::ETrack::Hit;
	Impact.Unit = IsValidUnit(UnitId) ? UnitId : INDEX_NONE;
	Impact.To = Hex;
	Impact.Start = Start;
	Impact.Duration = IronBattleBoard3DDetail::HitSeconds;
	Impact.Strength = Strength;
	Impact.Color = Color;
	AddTrack(MoveTemp(Impact));
}

FIronBoardEventTiming AIronBattleBoard3D::PlayEvent(const IronSim::FBattleEvent& Event)
{
	using namespace IronBattleBoard3DDetail;
	using IronBoard3D::ETrack;
	using IronBoard3D::FTrack;
	using EEvent = IronSim::EBattleEventType;

	FIronBoardEventTiming Timing;
	if (!bBuilt || !bBoardActive)
	{
		if (Event.Type == EEvent::DayStart)
		{
			TargetDay = Event.Value;
			GoalDayAlpha = DayAlphaFor(Event.Value);
		}
		return Timing;
	}
	// Every event gets a slot after the animations already queued; ImpactAt moves to the blow / effect below.
	const double EventStart = FMath::Max(Clock, AnimCursor);
	double ImpactAt = EventStart;
	const int32 FirstNewTrack = AnimTracks.Num();
	switch (Event.Type)
	{
	case EEvent::DayStart:
		// Dawn of a new day: the sun moves on (smoothly, without holding the battle back).
		TargetDay = Event.Value;
		GoalDayAlpha = DayAlphaFor(Event.Value);
		break;

	case EEvent::Move:
		if (IsValidUnit(Event.Unit) && Event.From != Event.To)
		{
			FTrack Walk;
			Walk.Kind = ETrack::Move;
			Walk.Unit = Event.Unit;
			Walk.From = Event.From;
			Walk.To = Event.To;
			Walk.Start = EventStart;
			if (Event.Value <= 0)
			{
				// UndoMove: a quick glide back.
				Walk.Variant = 1;
				Walk.Path = {Event.From, Event.To};
				Walk.Duration = GlideSeconds;
			}
			else
			{
				Walk.Path = FindPath(Event.From, Event.To, Event.Unit);
				Walk.Duration = MoveSecondsPerHex * static_cast<double>(FMath::Max(1, Walk.Path.Num() - 1));
			}
			AnimCursor = EventStart + Walk.Duration;
			ImpactAt = EventStart + Walk.Duration;
			AddTrack(MoveTemp(Walk));
		}
		break;

	case EEvent::Attack:
	case EEvent::Counter:
		if (IsValidUnit(Event.Unit))
		{
			// Distance 2 = archer volley (never countered); everything else is a melee lunge.
			const bool bRanged = IronSim::HexMath::Distance(Event.From, Event.To) >= 2;
			FTrack Strike;
			Strike.Kind = bRanged ? ETrack::Volley : ETrack::Lunge;
			Strike.Unit = Event.Unit;
			Strike.Other = Event.Target;
			Strike.From = Event.From;
			Strike.To = Event.To;
			Strike.Start = EventStart;
			Strike.Duration = bRanged ? VolleySeconds : LungeSeconds;
			AddTrack(MoveTemp(Strike));
			const double HitAt = EventStart + (bRanged ? VolleySeconds - 0.08 : LungeHitSeconds);
			const float Strength = 0.7f + FMath::Clamp(static_cast<float>(Event.Value) / 800.0f, 0.0f, 0.8f);
			QueueHit(Event.Target, Event.To, HitAt, Strength, Rgb(HitRgb));
			ImpactAt = HitAt;
			AnimCursor = EventStart + (bRanged ? VolleySeconds + 0.05 : LungeSeconds);
		}
		break;

	case EEvent::GateHit:
	{
		// To is the gate that was hit: great cities have two gates.
		const int32 Gate = GateIndexAt(Event.To);
		if (IsValidUnit(Event.Unit))
		{
			FTrack Strike;
			Strike.Kind = ETrack::Lunge;
			Strike.Unit = Event.Unit;
			Strike.From = Event.From;
			Strike.To = Event.To;
			Strike.Start = EventStart;
			Strike.Duration = LungeSeconds;
			AddTrack(MoveTemp(Strike));
		}
		if (Gate >= 0)
		{
			FTrack Shake;
			Shake.Kind = ETrack::GateShake;
			Shake.Gate = Gate;
			Shake.To = Event.To;
			Shake.Start = EventStart + LungeHitSeconds;
			Shake.Duration = GateShakeSeconds;
			Shake.Strength = 1.0f;
			AddTrack(MoveTemp(Shake));
		}
		QueueHit(INDEX_NONE, Event.To, EventStart + LungeHitSeconds, 0.8f, Rgb(BurnRgb));
		ImpactAt = EventStart + LungeHitSeconds;
		AnimCursor = EventStart + LungeSeconds + 0.05;
		break;
	}

	case EEvent::GateBroken:
	{
		const int32 Gate = GateIndexAt(Event.To);
		if (Gate >= 0)
		{
			FTrack Break;
			Break.Kind = ETrack::GateShake;
			Break.Variant = 1;
			Break.Gate = Gate;
			Break.To = Event.To;
			Break.Start = EventStart;
			Break.Duration = GateBreakSeconds;
			Break.Strength = 1.8f;
			AddTrack(MoveTemp(Break));
		}
		QueueHit(INDEX_NONE, Event.To, EventStart + GateSwapSeconds, 1.5f, Rgb(BurnRgb));
		ImpactAt = EventStart + GateSwapSeconds;
		AnimCursor = EventStart + GateBreakSeconds * 0.8;
		break;
	}

	case EEvent::Tactic:
	case EEvent::TacticFailed:
	{
		if (IsValidUnit(Event.Unit))
		{
			FTrack Casting;
			Casting.Kind = ETrack::Cast;
			Casting.Unit = Event.Unit;
			Casting.Start = EventStart;
			Casting.Duration = CastSeconds;
			AddTrack(MoveTemp(Casting));
		}
		const double EffectStart = EventStart + EffectDelaySeconds;
		ImpactAt = EffectStart;
		FTrack Effect;
		Effect.Other = Event.Target;
		Effect.To = Event.To;
		Effect.Start = EffectStart;
		if (Event.Type == EEvent::TacticFailed)
		{
			Effect.Kind = ETrack::Fizzle;
			Effect.Duration = FizzleSeconds;
			AnimCursor = EffectStart + 0.35;
		}
		else if (Event.Tactic == static_cast<int32>(IronSim::ETactic::Fire))
		{
			Effect.Kind = ETrack::FireBurst;
			Effect.Duration = FireSeconds;
			QueueHit(Event.Target, Event.To, EffectStart + FireHitDelaySeconds, 1.2f, Rgb(BurnRgb));
			ImpactAt = EffectStart + FireHitDelaySeconds;
			AnimCursor = EffectStart + 0.6;
		}
		else if (Event.Tactic == static_cast<int32>(IronSim::ETactic::Confuse))
		{
			Effect.Kind = ETrack::Swirl;
			Effect.Duration = SwirlSeconds;
			AnimCursor = EffectStart + 0.65;
		}
		else
		{
			Effect.Kind = ETrack::Pulse;
			Effect.Duration = PulseSeconds;
			AnimCursor = EffectStart + 0.55;
		}
		AddTrack(MoveTemp(Effect));
		break;
	}

	case EEvent::Burn:
		QueueHit(Event.Unit, Event.To, EventStart, 0.9f, Rgb(BurnRgb));
		AnimCursor = EventStart + 0.3;
		break;

	case EEvent::DuelResult:
		// Value = the winning unit id (-1 for a draw).
		if (IsValidUnit(Event.Value) && (Event.Value == Event.Unit || Event.Value == Event.Target))
		{
			const int32 Loser = Event.Value == Event.Unit ? Event.Target : Event.Unit;
			QueueHit(Loser, IsValidUnit(Loser) ? UnitVisuals[Loser].RestHex : Event.To, EventStart, 1.3f, Rgb(HitRgb));
			FTrack Cheer;
			Cheer.Kind = ETrack::Pulse;
			Cheer.Other = Event.Value;
			Cheer.To = UnitVisuals[Event.Value].RestHex;
			Cheer.Start = EventStart + 0.1;
			Cheer.Duration = PulseSeconds;
			Cheer.bBlocking = false;
			AddTrack(MoveTemp(Cheer));
			AnimCursor = EventStart + 0.35;
		}
		break;

	case EEvent::Routed:
	case EEvent::Destroyed:
	case EEvent::Captured:
		if (IsValidUnit(Event.Unit))
		{
			FTrack Fall;
			Fall.Kind = ETrack::Sink;
			Fall.Unit = Event.Unit;
			Fall.From = Event.From;
			Fall.Variant = static_cast<int32>(Event.Type == EEvent::Routed ? IronSim::EUnitStatus::Routed : (Event.Type == EEvent::Captured ? IronSim::EUnitStatus::Captured : IronSim::EUnitStatus::Destroyed));
			Fall.Start = EventStart;
			Fall.Duration = SinkSeconds;
			AddTrack(MoveTemp(Fall));
			AnimCursor = EventStart + SinkSeconds * 0.5;
		}
		break;

	default:
		break;
	}

	// The event's own blocking tracks (the queue only grows here) give its end.
	double EndAt = EventStart;
	for (int32 TrackIndex = FirstNewTrack; TrackIndex < AnimTracks.Num(); ++TrackIndex)
	{
		const IronBoard3D::FTrack& Track = AnimTracks[TrackIndex];
		if (Track.bBlocking)
		{
			EndAt = FMath::Max(EndAt, Track.Start + Track.Duration);
		}
	}
	Timing.bAnimated = AnimTracks.Num() > FirstNewTrack;
	Timing.StartSeconds = static_cast<float>(EventStart - Clock);
	Timing.ImpactSeconds = static_cast<float>(ImpactAt - Clock);
	Timing.EndSeconds = static_cast<float>(EndAt - Clock);
	return Timing;
}

bool AIronBattleBoard3D::IsAnimating() const
{
	return bBoardActive && bBuilt && Clock < BusyUntil;
}

float AIronBattleBoard3D::GetRemainingAnimationSeconds() const
{
	return IsAnimating() ? static_cast<float>(BusyUntil - Clock) : 0.0f;
}

void AIronBattleBoard3D::FinishAnimations()
{
	for (IronBoard3D::FTrack& Track : AnimTracks)
	{
		EndTrack(Track);
	}
	AnimTracks.Reset();
	AnimCursor = Clock;
	BusyUntil = Clock;
	if (bBuilt)
	{
		SnapToSnapshot();
	}
}

bool AIronBattleBoard3D::HasUnitTrack(int32 UnitId, bool bMovesOnly) const
{
	for (const IronBoard3D::FTrack& Track : AnimTracks)
	{
		if (Track.Unit == UnitId && (!bMovesOnly || Track.Kind == IronBoard3D::ETrack::Move || Track.Kind == IronBoard3D::ETrack::Sink))
		{
			return true;
		}
	}
	return false;
}

void AIronBattleBoard3D::ReconcileUnits()
{
	using namespace IronBattleBoard3DDetail;
	for (int32 UnitId = 0; UnitId < UnitVisuals.Num(); ++UnitId)
	{
		FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
		// Units with queued moves or falls keep their animated state; the others follow the rules state.
		if (!HasUnitTrack(UnitId, true))
		{
			if (!Visual.bTargetOnField)
			{
				Visual.bShown = false;
			}
			else if (!Visual.bShown)
			{
				Visual.bShown = true;
				Visual.RestHex = Visual.TargetHex;
			}
			else if (Visual.RestHex != Visual.TargetHex && InBoard(Visual.TargetHex))
			{
				// Moved without a Move event (fast-forward, scripted): walk or glide there.
				IronBoard3D::FTrack Walk;
				Walk.Kind = IronBoard3D::ETrack::Move;
				Walk.Unit = UnitId;
				Walk.From = Visual.RestHex;
				Walk.To = Visual.TargetHex;
				Walk.Start = Clock;
				if (IronSim::HexMath::Distance(Walk.From, Walk.To) <= 1)
				{
					Walk.Variant = 1;
					Walk.Path = {Walk.From, Walk.To};
					Walk.Duration = GlideSeconds;
				}
				else
				{
					Walk.Path = FindPath(Walk.From, Walk.To, UnitId);
					Walk.Duration = MoveSecondsPerHex * static_cast<double>(FMath::Max(1, Walk.Path.Num() - 1));
				}
				AddTrack(MoveTemp(Walk));
			}
		}
		Visual.Location = HexLocalCm(Visual.RestHex);
		Visual.Offset = FVector::ZeroVector;
		Visual.Shrink = 1.0f;
		Visual.Flash = 0.0f;
		Visual.bYawDriven = false;
	}
}

void AIronBattleBoard3D::UpdateTracks()
{
	for (int32 TrackIndex = 0; TrackIndex < AnimTracks.Num();)
	{
		IronBoard3D::FTrack& Track = AnimTracks[TrackIndex];
		if (Clock < Track.Start)
		{
			++TrackIndex;
			continue;
		}
		if (!Track.bStarted)
		{
			StartTrack(Track);
		}
		const double Elapsed = FMath::Min(Clock - Track.Start, Track.Duration);
		UpdateTrack(Track, Elapsed);
		if (Clock - Track.Start >= Track.Duration)
		{
			EndTrack(Track);
			AnimTracks.RemoveAt(TrackIndex);
			continue;
		}
		++TrackIndex;
	}
}

FVector AIronBattleBoard3D::UnitLocalNow(int32 UnitId) const
{
	if (!IsValidUnit(UnitId))
	{
		return FVector::ZeroVector;
	}
	const FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
	return Visual.Location + Visual.Offset;
}

void AIronBattleBoard3D::StartTrack(IronBoard3D::FTrack& Track)
{
	using namespace IronBattleBoard3DDetail;
	using IronBoard3D::ETrack;
	Track.bStarted = true;
	const bool bRich = QualityLevel >= 1;
	const FVector TargetPoint = IsValidUnit(Track.Other) && UnitVisuals[Track.Other].bShown ? UnitVisuals[Track.Other].Location : HexLocalCm(Track.To);

	switch (Track.Kind)
	{
	case ETrack::Move:
		Track.Points.Reset();
		for (const IronSim::FHex& Step : Track.Path)
		{
			Track.Points.Add(HexLocalCm(Step));
		}
		if (IsValidUnit(Track.Unit))
		{
			UnitVisuals[Track.Unit].RestHex = Track.From;
		}
		break;

	case ETrack::Lunge:
	case ETrack::Volley:
	{
		const FVector Self = IsValidUnit(Track.Unit) ? UnitVisuals[Track.Unit].Location : HexLocalCm(Track.From);
		Track.Points = {Self, TargetPoint};
		if (Track.Kind == ETrack::Volley)
		{
			for (int32 Arrow = 0; Arrow < VolleyArrows; ++Arrow)
			{
				Track.Quads.Add(AcquireQuad(0.0f, 1.0f, 0.0f, 5.0f));
			}
		}
		break;
	}

	case ETrack::Hit:
	{
		const bool bOnUnit = IsValidUnit(Track.Unit) && UnitVisuals[Track.Unit].bShown;
		Track.Points = {bOnUnit ? UnitVisuals[Track.Unit].Location : HexLocalCm(Track.To)};
		Track.Light = AcquireLight(Track.Color, 900.0f);
		Track.Quads.Add(AcquireQuad(0.0f, 1.0f, 0.25f, 2.5f));
		break;
	}

	case ETrack::GateShake:
	{
		Track.Points = {HexLocalCm(Track.To)};
		const int32 DustCount = Track.Variant == 1 ? (bRich ? 9 : 4) : (bRich ? 4 : 2);
		for (int32 Puff = 0; Puff < DustCount; ++Puff)
		{
			Track.Quads.Add(AcquireQuad(0.0f, 1.0f, 0.0f, 0.6f));
		}
		break;
	}

	case ETrack::Cast:
		break;

	case ETrack::FireBurst:
	{
		Track.Points = {HexLocalCm(Track.To)};
		Track.Light = AcquireLight(Rgb(BurnRgb), 1300.0f);
		const int32 Embers = bRich ? 16 : 6;
		for (int32 Ember = 0; Ember < Embers; ++Ember)
		{
			Track.Quads.Add(AcquireQuad(0.0f, 1.0f, 0.0f, 6.0f));
		}
		// Last quad: the shock ring.
		Track.Quads.Add(AcquireQuad(0.8f, 0.12f, 0.1f, 3.0f));
		break;
	}

	case ETrack::Swirl:
		Track.Points = {TargetPoint};
		Track.Light = AcquireLight(Rgb(ConfuseRgb), 800.0f);
		for (int32 Ring = 0; Ring < 3; ++Ring)
		{
			Track.Quads.Add(AcquireQuad(0.78f, 0.14f, 0.0f, 3.5f));
		}
		break;

	case ETrack::Pulse:
		Track.Points = {TargetPoint};
		Track.Light = AcquireLight(Rgb(RallyRgb), 900.0f);
		for (int32 Ring = 0; Ring < 2; ++Ring)
		{
			Track.Quads.Add(AcquireQuad(0.85f, 0.1f, 0.15f, 3.0f));
		}
		break;

	case ETrack::Fizzle:
		Track.Points = {TargetPoint};
		Track.Quads.Add(AcquireQuad(0.8f, 0.12f, 0.0f, 1.2f));
		break;

	case ETrack::Sink:
	{
		Track.Points = {IsValidUnit(Track.Unit) ? UnitVisuals[Track.Unit].Location : HexLocalCm(Track.From)};
		const int32 DustCount = bRich ? 5 : 2;
		for (int32 Puff = 0; Puff < DustCount; ++Puff)
		{
			Track.Quads.Add(AcquireQuad(0.0f, 1.0f, 0.0f, 0.6f));
		}
		if (Track.Variant == static_cast<int32>(IronSim::EUnitStatus::Captured))
		{
			Track.Quads.Add(AcquireQuad(0.8f, 0.12f, 0.1f, 3.0f));
		}
		break;
	}
	}
}

void AIronBattleBoard3D::UpdateTrack(IronBoard3D::FTrack& Track, double Elapsed)
{
	using namespace IronBattleBoard3DDetail;
	using IronBoard3D::ETrack;
	const double Progress = Track.Duration > 0.0 ? FMath::Clamp(Elapsed / Track.Duration, 0.0, 1.0) : 1.0;
	const double Fade = 1.0 - Progress;
	FIronBoardUnitVisual* Visual = IsValidUnit(Track.Unit) ? &UnitVisuals[Track.Unit] : nullptr;

	switch (Track.Kind)
	{
	case ETrack::Move:
	{
		if (Visual == nullptr || Track.Points.Num() < 2)
		{
			break;
		}
		const int32 Segments = Track.Points.Num() - 1;
		const double SegmentTime = Track.Duration / static_cast<double>(Segments);
		const int32 Segment = FMath::Clamp(static_cast<int32>(FMath::FloorToDouble(Elapsed / SegmentTime)), 0, Segments - 1);
		const double Alpha = FMath::Clamp((Elapsed - SegmentTime * static_cast<double>(Segment)) / SegmentTime, 0.0, 1.0);
		const FVector& SegmentStart = Track.Points[Segment];
		const FVector& SegmentEnd = Track.Points[Segment + 1];
		const bool bGlide = Track.Variant == 1;
		FVector Position = SegmentStart + (SegmentEnd - SegmentStart) * (bGlide ? IronWorld::EaseInOut(Alpha) : Alpha);
		if (!bGlide)
		{
			// One hop per hex.
			Position.Z += HopCm * FMath::Sin(UE_DOUBLE_PI * Alpha);
			const FVector Heading = SegmentEnd - SegmentStart;
			if (Heading.SizeSquared2D() > 1.0)
			{
				Visual->bYawDriven = true;
				Visual->DrivenYaw = static_cast<float>(YawOf(Heading));
			}
		}
		Visual->Location = Position;
		break;
	}

	case ETrack::Lunge:
	{
		if (Visual == nullptr || Track.Points.Num() < 2)
		{
			break;
		}
		const FVector Direction = (Track.Points[1] - Track.Points[0]).GetSafeNormal2D();
		const double Reach = FMath::Min(FVector::Dist2D(Track.Points[0], Track.Points[1]) * LungeFraction, LungeMaxCm);
		const double Amount = Elapsed < LungeHitSeconds ? EaseOut(Elapsed / LungeHitSeconds) : 1.0 - IronWorld::EaseInOut((Elapsed - LungeHitSeconds) / FMath::Max(0.01, Track.Duration - LungeHitSeconds));
		Visual->Offset += Direction * (Reach * Amount) + FVector(0.0, 0.0, 30.0 * FMath::Sin(UE_DOUBLE_PI * Amount));
		if (Direction.SizeSquared2D() > 0.5)
		{
			Visual->bYawDriven = true;
			Visual->DrivenYaw = static_cast<float>(YawOf(Direction));
		}
		break;
	}

	case ETrack::Volley:
	{
		if (Track.Points.Num() < 2)
		{
			break;
		}
		const FVector Direction = (Track.Points[1] - Track.Points[0]).GetSafeNormal2D();
		if (Visual != nullptr)
		{
			// The archers draw back, then loose.
			Visual->Offset -= Direction * (30.0 * FMath::Sin(UE_DOUBLE_PI * FMath::Min(1.0, Elapsed / 0.25)));
			if (Direction.SizeSquared2D() > 0.5)
			{
				Visual->bYawDriven = true;
				Visual->DrivenYaw = static_cast<float>(YawOf(Direction));
			}
		}
		const FVector Side(-Direction.Y, Direction.X, 0.0);
		const FVector Launch = Track.Points[0] + FVector(0.0, 0.0, 220.0);
		const FVector Land = Track.Points[1] + FVector(0.0, 0.0, 120.0);
		const double Flight = FMath::Max(0.05, Track.Duration - 0.2);
		for (int32 Arrow = 0; Arrow < Track.Quads.Num(); ++Arrow)
		{
			const double Along = (Elapsed - 0.045 * static_cast<double>(Arrow)) / Flight;
			if (Along <= 0.0 || Along >= 1.0)
			{
				PlaceQuad(Track.Quads[Arrow], Launch, 0.0f, FLinearColor::Transparent, true);
				continue;
			}
			const double Spread = 45.0 * (static_cast<double>(Arrow) - 0.5 * static_cast<double>(Track.Quads.Num() - 1));
			const FVector Position = Launch + (Land - Launch) * Along + Side * Spread + FVector(0.0, 0.0, 420.0 * FMath::Sin(UE_DOUBLE_PI * Along));
			PlaceQuad(Track.Quads[Arrow], Position, 0.32f, Rgb(ArrowRgb), true);
		}
		break;
	}

	case ETrack::Hit:
	{
		const double Strength = static_cast<double>(Track.Strength);
		if (Visual != nullptr)
		{
			Visual->Offset += FVector(22.0 * Strength * FMath::Sin(Elapsed * 55.0) * Fade, 0.0, 0.0);
			const float FlashAmount = static_cast<float>(Fade * Fade * FMath::Min(1.0, Strength));
			if (FlashAmount > Visual->Flash)
			{
				Visual->Flash = FlashAmount;
				Visual->FlashColor = Track.Color;
			}
		}
		const FVector Impact = Track.Points.Num() > 0 ? Track.Points[0] : HexLocalCm(Track.To);
		PlaceLight(Track.Light, Impact + FVector(0.0, 0.0, 220.0), static_cast<float>(HitCandela * Strength * Fade * Fade));
		if (Track.Quads.Num() > 0)
		{
			PlaceQuad(Track.Quads[0], Impact + FVector(0.0, 0.0, 15.0), 6.5f, WithAlpha(Track.Color, 0.7 * Fade * Fade), false);
		}
		break;
	}

	case ETrack::GateShake:
	{
		const double Strength = static_cast<double>(Track.Strength);
		if (GateOffsets.IsValidIndex(Track.Gate))
		{
			GateOffsets[Track.Gate] = FVector(FMath::Sin(Elapsed * 62.0) * 14.0 * Strength * Fade, FMath::Cos(Elapsed * 47.0) * 9.0 * Strength * Fade, 0.0);
		}
		const bool bBreak = Track.Variant == 1;
		if (bBreak && !Track.bFlag && Elapsed >= GateSwapSeconds)
		{
			Track.bFlag = true;
			if (GateShownBroken.IsValidIndex(Track.Gate))
			{
				GateShownBroken[Track.Gate] = true;
			}
		}
		// Dust: from the first blow, or from the collapse when the gate breaks.
		const double DustStart = bBreak ? GateSwapSeconds : 0.0;
		const double DustAlpha = (Elapsed - DustStart) / FMath::Max(0.05, Track.Duration - DustStart);
		const FVector Centre = Track.Points.Num() > 0 ? Track.Points[0] : HexLocalCm(Track.To);
		for (int32 Puff = 0; Puff < Track.Quads.Num(); ++Puff)
		{
			if (DustAlpha <= 0.0 || DustAlpha >= 1.0)
			{
				PlaceQuad(Track.Quads[Puff], Centre, 0.0f, FLinearColor::Transparent, true);
				continue;
			}
			const double Angle = 2.0 * UE_DOUBLE_PI * (static_cast<double>(Puff) + 0.3 * Unit01(static_cast<uint32>(Puff) + 11u)) / static_cast<double>(Track.Quads.Num());
			const double Radius = (bBreak ? 140.0 : 90.0) + (bBreak ? 320.0 : 160.0) * EaseOut(DustAlpha);
			const FVector Position = Centre + FVector(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius, 60.0 + 180.0 * DustAlpha);
			PlaceQuad(Track.Quads[Puff], Position, static_cast<float>((bBreak ? 2.6 : 1.8) + 2.4 * DustAlpha), Rgb(DustRgb, static_cast<float>(0.55 * (1.0 - DustAlpha))), true);
		}
		break;
	}

	case ETrack::Cast:
		if (Visual != nullptr)
		{
			Visual->Offset.Z += 40.0 * FMath::Sin(UE_DOUBLE_PI * Progress);
		}
		break;

	case ETrack::FireBurst:
	{
		const FVector Centre = Track.Points.Num() > 0 ? Track.Points[0] : HexLocalCm(Track.To);
		const double Envelope = Progress < 0.12 ? Progress / 0.12 : FMath::Pow(1.0 - (Progress - 0.12) / 0.88, 1.5);
		const double Flicker = 0.75 + 0.25 * static_cast<double>(FMath::PerlinNoise1D(static_cast<float>(Clock * 9.0)));
		PlaceLight(Track.Light, Centre + FVector(0.0, 0.0, 200.0), static_cast<float>(FireBurstCandela * Envelope * Flicker));
		const int32 Embers = Track.Quads.Num() - 1;
		for (int32 Ember = 0; Ember < Embers; ++Ember)
		{
			const double Life = (Elapsed - 0.05 * static_cast<double>(Ember % 8)) / EmberLifeSeconds;
			if (Life <= 0.0 || Life >= 1.0)
			{
				PlaceQuad(Track.Quads[Ember], Centre, 0.0f, FLinearColor::Transparent, true);
				continue;
			}
			const double Angle = 2.0 * UE_DOUBLE_PI * Unit01(static_cast<uint32>(Ember) * 7u + 3u);
			const double Radius = 60.0 + 200.0 * Unit01(static_cast<uint32>(Ember) * 13u + 5u) * FMath::Sqrt(Life);
			const FVector Position = Centre + FVector(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius, 40.0 + 480.0 * Life);
			const FLinearColor Color = FMath::Lerp(Rgb(EmberHotRgb), Rgb(EmberCoolRgb), static_cast<float>(Life));
			PlaceQuad(Track.Quads[Ember], Position, static_cast<float>(0.55 * (1.0 - 0.6 * Life)), WithAlpha(Color, FMath::Pow(1.0 - Life, 1.2)), true);
		}
		if (Embers >= 0)
		{
			const double RingAlpha = FMath::Min(1.0, Progress * 1.6);
			PlaceQuad(Track.Quads[Embers], Centre + FVector(0.0, 0.0, 12.0), static_cast<float>(1.5 + 6.5 * EaseOut(RingAlpha)), Rgb(BurnRgb, static_cast<float>(0.85 * (1.0 - RingAlpha))), false);
		}
		break;
	}

	case ETrack::Swirl:
	{
		const FVector Centre = IsValidUnit(Track.Other) && UnitVisuals[Track.Other].bShown ? UnitLocalNow(Track.Other) : (Track.Points.Num() > 0 ? Track.Points[0] : HexLocalCm(Track.To));
		const double Envelope = FMath::Sin(UE_DOUBLE_PI * Progress);
		PlaceLight(Track.Light, Centre + FVector(0.0, 0.0, 250.0), static_cast<float>(SwirlCandela * Envelope));
		for (int32 Ring = 0; Ring < Track.Quads.Num(); ++Ring)
		{
			const double Angle = Elapsed * 6.5 + 2.0 * UE_DOUBLE_PI * static_cast<double>(Ring) / 3.0;
			const double Radius = 110.0 * (1.0 - 0.4 * Progress);
			const FVector Position = Centre + FVector(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius, 60.0 + 260.0 * Progress + 35.0 * static_cast<double>(Ring));
			PlaceQuad(Track.Quads[Ring], Position, static_cast<float>(2.4 * (1.0 - 0.35 * Progress)), Rgb(ConfuseRgb, static_cast<float>(0.9 * Envelope)), false);
		}
		if (IsValidUnit(Track.Other))
		{
			// The target staggers.
			FIronBoardUnitVisual& Target = UnitVisuals[Track.Other];
			Target.bYawDriven = true;
			Target.DrivenYaw = IdleYawFor(Track.Other) + static_cast<float>(16.0 * FMath::Sin(Elapsed * 14.0) * Fade);
		}
		break;
	}

	case ETrack::Pulse:
	{
		const FVector Centre = IsValidUnit(Track.Other) && UnitVisuals[Track.Other].bShown ? UnitLocalNow(Track.Other) : (Track.Points.Num() > 0 ? Track.Points[0] : HexLocalCm(Track.To));
		PlaceLight(Track.Light, Centre + FVector(0.0, 0.0, 250.0), static_cast<float>(PulseCandela * FMath::Sin(UE_DOUBLE_PI * Progress)));
		for (int32 Ring = 0; Ring < Track.Quads.Num(); ++Ring)
		{
			const double RingAlpha = (Elapsed - 0.28 * static_cast<double>(Ring)) / 0.75;
			if (RingAlpha <= 0.0 || RingAlpha >= 1.0)
			{
				PlaceQuad(Track.Quads[Ring], Centre, 0.0f, FLinearColor::Transparent, false);
				continue;
			}
			PlaceQuad(Track.Quads[Ring], FVector(Centre.X, Centre.Y, 15.0 + 5.0 * static_cast<double>(Ring)), static_cast<float>(2.0 + 8.0 * EaseOut(RingAlpha)), Rgb(RallyRgb, static_cast<float>(0.9 * (1.0 - RingAlpha))), false);
		}
		if (IsValidUnit(Track.Other))
		{
			// The rallied troops cheer (two small jumps).
			UnitVisuals[Track.Other].Offset.Z += 35.0 * FMath::Abs(FMath::Sin(2.0 * UE_DOUBLE_PI * Progress)) * Fade;
		}
		break;
	}

	case ETrack::Fizzle:
	{
		const FVector Centre = Track.Points.Num() > 0 ? Track.Points[0] : HexLocalCm(Track.To);
		if (Track.Quads.Num() > 0)
		{
			PlaceQuad(Track.Quads[0], FVector(Centre.X, Centre.Y, 20.0), static_cast<float>(4.0 - 3.0 * EaseOut(Progress)), Rgb(FizzleRgb, static_cast<float>(0.7 * Fade)), false);
		}
		break;
	}

	case ETrack::Sink:
	{
		if (Visual == nullptr)
		{
			break;
		}
		const bool bRouted = Track.Variant == static_cast<int32>(IronSim::EUnitStatus::Routed);
		double Drop = 0.0;
		if (bRouted)
		{
			// Broken troops turn and flee toward their own side of the field while they fade into the ground.
			const FVector Flee(Visual->Side == 0 ? -1.0 : 1.0, 0.0, 0.0);
			Visual->Offset += Flee * (FleeDistanceCm * IronWorld::EaseInOut(Progress));
			Visual->bYawDriven = true;
			Visual->DrivenYaw = Visual->Side == 0 ? 180.0f : 0.0f;
			Drop = SinkDepthCm * EaseIn(FMath::Max(0.0, (Progress - 0.35) / 0.65));
		}
		else
		{
			Drop = SinkDepthCm * IronWorld::EaseInOut(Progress);
			Visual->Shrink = static_cast<float>(1.0 - 0.2 * Progress);
		}
		Visual->Offset.Z -= Drop;
		const FVector Centre = Track.Points.Num() > 0 ? Track.Points[0] : Visual->Location;
		const bool bCaptured = Track.Variant == static_cast<int32>(IronSim::EUnitStatus::Captured);
		const int32 DustCount = Track.Quads.Num() - (bCaptured ? 1 : 0);
		for (int32 Puff = 0; Puff < DustCount; ++Puff)
		{
			const double Angle = 2.0 * UE_DOUBLE_PI * (static_cast<double>(Puff) + 0.4 * Unit01(static_cast<uint32>(Puff) + 29u)) / static_cast<double>(FMath::Max(1, DustCount));
			const double Radius = 150.0 + 150.0 * Progress;
			const FVector Position = Centre + FVector(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius, 40.0 + 80.0 * Progress);
			PlaceQuad(Track.Quads[Puff], Position, static_cast<float>(2.0 + 1.5 * Progress), Rgb(DustRgb, static_cast<float>(0.5 * Fade)), true);
		}
		if (bCaptured && Track.Quads.Num() > 0)
		{
			PlaceQuad(Track.Quads.Last(), FVector(Centre.X, Centre.Y, 18.0), static_cast<float>(3.0 + 3.0 * Progress), Rgb(CaptureRgb, static_cast<float>(0.8 * Fade)), false);
		}
		break;
	}
	}
}

void AIronBattleBoard3D::EndTrack(IronBoard3D::FTrack& Track)
{
	using IronBoard3D::ETrack;
	ReleaseQuads(Track.Quads);
	ReleaseLight(Track.Light);
	FIronBoardUnitVisual* Visual = IsValidUnit(Track.Unit) ? &UnitVisuals[Track.Unit] : nullptr;
	switch (Track.Kind)
	{
	case ETrack::Move:
		if (Visual != nullptr && InBoard(Track.To))
		{
			Visual->RestHex = Track.To;
			Visual->Location = HexLocalCm(Track.To);
		}
		break;
	case ETrack::Sink:
		if (Visual != nullptr)
		{
			Visual->bShown = false;
		}
		break;
	case ETrack::GateShake:
		if (GateOffsets.IsValidIndex(Track.Gate))
		{
			GateOffsets[Track.Gate] = FVector::ZeroVector;
			if (Track.Variant == 1)
			{
				GateShownBroken[Track.Gate] = true;
			}
		}
		break;
	default:
		break;
	}
}

float AIronBattleBoard3D::IdleYawFor(int32 UnitId) const
{
	const FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
	// Face the nearest enemy still on the field; the attacker looks east (+X) and the defender west by default.
	float BestYaw = Visual.Side == 0 ? 0.0f : 180.0f;
	double BestDistanceSq = TNumericLimits<double>::Max();
	for (int32 OtherId = 0; OtherId < UnitVisuals.Num(); ++OtherId)
	{
		const FIronBoardUnitVisual& Other = UnitVisuals[OtherId];
		if (OtherId == UnitId || !Other.bShown || Other.Side == Visual.Side)
		{
			continue;
		}
		const FVector Delta = Other.Location - Visual.Location;
		const double DistanceSq = Delta.SizeSquared2D();
		if (DistanceSq > 1.0 && DistanceSq < BestDistanceSq)
		{
			BestDistanceSq = DistanceSq;
			BestYaw = static_cast<float>(IronBattleBoard3DDetail::YawOf(Delta));
		}
	}
	return BestYaw;
}

void AIronBattleBoard3D::ApplyUnitVisibility(FIronBoardUnitVisual& Visual)
{
	if (Visual.Root == nullptr || Visual.bShown == Visual.bAppliedShown)
	{
		return;
	}
	Visual.Root->SetVisibility(Visual.bShown, true);
	Visual.bAppliedShown = Visual.bShown;
}

void AIronBattleBoard3D::ApplyActedLook(int32 UnitId, FIronBoardUnitVisual& Visual, float DeltaSeconds)
{
	using namespace IronBattleBoard3DDetail;
	// A unit dims once its own animations (the attack it just made, the walk) are over; the next turn restores it.
	const bool bDimmed = bDimActedUnits && Visual.bTargetActed && !HasUnitTrack(UnitId, false);
	const float Goal = bDimmed ? 1.0f : 0.0f;
	const float Step = FMath::Max(0.0f, DeltaSeconds) / ActedFadeSeconds;
	Visual.Acted = Visual.Acted < Goal ? FMath::Min(Goal, Visual.Acted + Step) : FMath::Max(Goal, Visual.Acted - Step);
	if (FMath::IsNearlyEqual(Visual.Acted, Visual.AppliedActed, 0.02f) && (Visual.Acted != Goal || Visual.AppliedActed == Goal))
	{
		return;
	}
	Visual.AppliedActed = Visual.Acted;
	const FLinearColor Color = FMath::Lerp(Visual.SideColor, ActedColor(Visual.SideColor), Visual.Acted);
	UStaticMeshComponent* const Parts[3] = {Visual.Figure.Get(), Visual.Base.Get(), Visual.Flag.Get()};
	UMaterialInstanceDynamic* const PartTints[3] = {Visual.FigureTint.Get(), Visual.BaseTint.Get(), Visual.FlagTint.Get()};
	for (int32 PartIndex = 0; PartIndex < 3; ++PartIndex)
	{
		if (Parts[PartIndex] != nullptr && PartTints[PartIndex] != nullptr)
		{
			IronWorld::ApplyTint(Parts[PartIndex], Color, PartTints[PartIndex], TintMaterial.Get());
		}
	}
}

void AIronBattleBoard3D::ApplyUnitTransforms(float DeltaSeconds)
{
	using namespace IronBattleBoard3DDetail;
	for (int32 UnitId = 0; UnitId < UnitVisuals.Num(); ++UnitId)
	{
		FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
		ApplyUnitVisibility(Visual);
		if (!Visual.bShown || Visual.Root == nullptr)
		{
			continue;
		}
		ApplyActedLook(UnitId, Visual, DeltaSeconds);
		// Facing: along the path / toward the target while acting, else toward the nearest enemy. Settled units stop
		// touching their transform (keeps virtual shadow map pages cached).
		const float GoalYaw = Visual.bYawDriven ? Visual.DrivenYaw : IdleYawFor(UnitId);
		const float Delta = FMath::FindDeltaAngleDegrees(Visual.Yaw, GoalYaw);
		const float TurnRate = Visual.bYawDriven ? 16.0f : 7.0f;
		Visual.Yaw = FMath::Abs(Delta) < 0.05f ? GoalYaw : Visual.Yaw + Delta * FMath::Min(1.0f, DeltaSeconds * TurnRate);

		const FTransform Wanted(FRotator(0.0, static_cast<double>(Visual.Yaw), 0.0), Visual.Location + Visual.Offset, FVector(static_cast<double>(Visual.Shrink)));
		if (!Visual.Root->GetRelativeTransform().Equals(Wanted, 0.01))
		{
			Visual.Root->SetRelativeTransform(Wanted);
		}

		if (!FMath::IsNearlyEqual(Visual.Flash, Visual.AppliedFlash, 0.01f))
		{
			// Red (or fire-orange) glow on every model material with an "EmissiveFactor" (the tint material ignores it).
			const FLinearColor Glow = Visual.FlashColor * (Visual.Flash * FlashEmissive);
			for (const TObjectPtr<UMaterialInstanceDynamic>& Material : Visual.Materials)
			{
				if (Material != nullptr)
				{
					Material->SetVectorParameterValue(EmissiveParam(), FLinearColor(Glow.R, Glow.G, Glow.B, 1.0f));
				}
			}
			Visual.AppliedFlash = Visual.Flash;
		}
	}
}

void AIronBattleBoard3D::UpdateGates()
{
	using namespace IronBattleBoard3DDetail;
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	for (int32 GateIndex = 0; GateIndex < GateHexes.Num(); ++GateIndex)
	{
		bool bBreaking = false;
		for (const IronBoard3D::FTrack& Track : AnimTracks)
		{
			bBreaking = bBreaking || (Track.Kind == IronBoard3D::ETrack::GateShake && Track.Variant == 1 && Track.Gate == GateIndex);
		}
		if (!bBreaking)
		{
			GateShownBroken[GateIndex] = GateTargetBroken[GateIndex];
		}
		UStaticMeshComponent* Tile = GateTiles.IsValidIndex(GateIndex) ? GateTiles[GateIndex].Get() : nullptr;
		if (Tile == nullptr)
		{
			continue;
		}
		if (GateShownBroken[GateIndex] != GateAppliedBroken[GateIndex])
		{
			int32 MeshIndex = static_cast<int32>(GateShownBroken[GateIndex] ? IronSim::EHexTerrain::Rubble : IronSim::EHexTerrain::Gate);
			if (HexMeshes[MeshIndex] == nullptr)
			{
				MeshIndex = static_cast<int32>(IronSim::EHexTerrain::Plain);
			}
			Tile->SetStaticMesh(HexMeshes[MeshIndex].Get());
			Tile->SetRelativeScale3D(FVector(ModelParams.ScaleOf(HexModelName(MeshIndex))));
			GateAppliedBroken[GateIndex] = GateShownBroken[GateIndex];
		}
		const FVector Wanted = HexLocalCm(GateHexes[GateIndex]) + GateOffsets[GateIndex];
		if (!Tile->GetRelativeLocation().Equals(Wanted, 0.01))
		{
			Tile->SetRelativeLocation(Wanted);
		}
	}
}

void AIronBattleBoard3D::UpdateBurning()
{
	using namespace IronBattleBoard3DDetail;
	// Burning hexes, except where a fire tactic has not flared up yet.
	TArray<IronSim::FHex> Wanted;
	for (const IronSim::FHex& Hex : TargetBurning)
	{
		bool bPending = false;
		for (const IronBoard3D::FTrack& Track : AnimTracks)
		{
			bPending = bPending || (Track.Kind == IronBoard3D::ETrack::FireBurst && !Track.bStarted && Track.To == Hex);
		}
		if (!bPending)
		{
			Wanted.Add(Hex);
		}
	}

	bool bChanged = false;
	for (int32 BurnIndex = Burns.Num() - 1; BurnIndex >= 0; --BurnIndex)
	{
		if (!Wanted.Contains(Burns[BurnIndex].Hex))
		{
			ReleaseLight(Burns[BurnIndex].Light);
			ReleaseQuads(Burns[BurnIndex].Quads);
			Burns.RemoveAt(BurnIndex);
			bChanged = true;
		}
	}
	for (const IronSim::FHex& Hex : Wanted)
	{
		if (Burns.ContainsByPredicate([&Hex](const IronBoard3D::FBurn& Existing) { return Existing.Hex == Hex; }))
		{
			continue;
		}
		IronBoard3D::FBurn Fire;
		Fire.Hex = Hex;
		Fire.Phase = static_cast<float>(10.0 * Unit01(HexHash(Hex.Col, Hex.Row, 0x0F1Eu)));
		Fire.Light = AcquireLight(Rgb(BurnRgb), 1000.0f);
		const int32 Embers = QualityLevel >= 1 ? 5 : 2;
		for (int32 Ember = 0; Ember < Embers; ++Ember)
		{
			Fire.Quads.Add(AcquireQuad(0.0f, 1.0f, 0.0f, 6.0f));
		}
		Burns.Add(MoveTemp(Fire));
		bChanged = true;
	}
	if (bChanged)
	{
		TArray<IronSim::FHex> Burning;
		for (const IronBoard3D::FBurn& Fire : Burns)
		{
			Burning.Add(Fire.Hex);
		}
		FillHexLayer(IronBoard3D::ELayer::Burning, Burning);
	}

	// Flickering light and looping embers.
	for (IronBoard3D::FBurn& Fire : Burns)
	{
		const FVector Centre = HexLocalCm(Fire.Hex);
		const double Time = Clock + static_cast<double>(Fire.Phase);
		const double Flicker = 0.7 + 0.3 * static_cast<double>(FMath::PerlinNoise1D(static_cast<float>(Time * 7.0))) + 0.1 * FMath::Sin(Time * 23.0);
		PlaceLight(Fire.Light, Centre + FVector(0.0, 0.0, 180.0), static_cast<float>(BurnCandela * Flicker));
		for (int32 Ember = 0; Ember < Fire.Quads.Num(); ++Ember)
		{
			const double Cycle = FMath::Frac((Time + 0.29 * static_cast<double>(Ember)) / BurnEmberCycleSeconds);
			const double Angle = 2.0 * UE_DOUBLE_PI * Unit01(static_cast<uint32>(Ember) * 31u + static_cast<uint32>(Fire.Hex.Col * 7 + Fire.Hex.Row));
			const double Radius = 40.0 + 150.0 * Unit01(static_cast<uint32>(Ember) * 17u + 1u);
			const FVector Position = Centre + FVector(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius, 30.0 + 420.0 * Cycle);
			const double Alpha = (Cycle < 0.08 ? Cycle / 0.08 : 1.0) * (1.0 - Cycle) * 0.9;
			const FLinearColor Color = FMath::Lerp(Rgb(EmberHotRgb), Rgb(EmberCoolRgb), static_cast<float>(Cycle));
			PlaceQuad(Fire.Quads[Ember], Position, static_cast<float>(0.42 * (1.0 - 0.5 * Cycle)), WithAlpha(Color, Alpha), true);
		}
	}
}

void AIronBattleBoard3D::UpdateHalos()
{
	using namespace IronBattleBoard3DDetail;
	for (int32 UnitId = 0; UnitId < UnitVisuals.Num(); ++UnitId)
	{
		FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
		bool bWanted = Visual.bShown && Visual.bTargetConfused && Visual.bTargetOnField;
		for (const IronBoard3D::FTrack& Track : AnimTracks)
		{
			// Not before the Confuse swirl reached the unit, and not while it falls.
			const bool bPendingSwirl = Track.Kind == IronBoard3D::ETrack::Swirl && Track.Other == UnitId && !Track.bStarted;
			const bool bFalling = Track.Kind == IronBoard3D::ETrack::Sink && Track.Unit == UnitId;
			bWanted = bWanted && !bPendingSwirl && !bFalling;
		}
		if (bWanted && Visual.HaloQuad == INDEX_NONE)
		{
			Visual.HaloQuad = AcquireQuad(0.78f, 0.16f, 0.0f, 3.0f);
		}
		else if (!bWanted && Visual.HaloQuad != INDEX_NONE)
		{
			ReleaseQuad(Visual.HaloQuad);
			Visual.HaloQuad = INDEX_NONE;
		}
		if (Visual.HaloQuad != INDEX_NONE)
		{
			// A dazed purple ring circling above the squad.
			const double Phase = Clock + 0.7 * static_cast<double>(UnitId);
			const FVector Position = Visual.Location + Visual.Offset + FVector(0.0, 0.0, (static_cast<double>(Visual.TopM) + 0.5) * IronWorld::CmPerMetre + 15.0 * FMath::Sin(Phase * 3.0));
			PlaceQuad(Visual.HaloQuad, Position, static_cast<float>(1.6 + 0.15 * FMath::Sin(Phase * 5.0)), Rgb(ConfuseRgb, 0.85f), false);
		}
	}
}

void AIronBattleBoard3D::UpdateRings()
{
	using namespace IronBattleBoard3DDetail;
	if (HoverRing != nullptr)
	{
		const bool bHover = InBoard(Highlights.HoveredHex);
		if (bHover)
		{
			HoverRing->SetRelativeLocation(HexLocalCm(Highlights.HoveredHex) + FVector(0.0, 0.0, HoverStyle.LiftCm));
		}
		if (HoverRing->IsVisible() != bHover)
		{
			HoverRing->SetVisibility(bHover);
		}
	}
	if (SelectRing != nullptr)
	{
		const int32 Selected = Highlights.SelectedUnit;
		const bool bSelected = IsValidUnit(Selected) && UnitVisuals[Selected].bShown;
		if (bSelected)
		{
			// Follows the unit while it walks (stays on the ground under its hops).
			const FVector UnitLocal = UnitLocalNow(Selected);
			SelectRing->SetRelativeLocation(FVector(UnitLocal.X, UnitLocal.Y, SelectStyle.LiftCm));
		}
		if (SelectRing->IsVisible() != bSelected)
		{
			SelectRing->SetVisibility(bSelected);
		}
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Effect pools
// ---------------------------------------------------------------------------------------------------------------------

int32 AIronBattleBoard3D::AcquireQuad(float RingRadius, float RingWidth, float FillOpacity, float Intensity)
{
	using namespace IronBattleBoard3DDetail;
	int32 Found = INDEX_NONE;
	for (int32 QuadIndex = 0; QuadIndex < FxQuads.Num(); ++QuadIndex)
	{
		if (!FxQuads[QuadIndex].bInUse && FxQuads[QuadIndex].Mesh != nullptr && FxQuads[QuadIndex].Material != nullptr)
		{
			Found = QuadIndex;
			break;
		}
	}
	if (Found == INDEX_NONE)
	{
		if (FxQuads.Num() >= MaxFxQuads || CircleHighlightMaterial == nullptr)
		{
			return INDEX_NONE;
		}
		UProceduralMeshComponent* QuadMesh = CreateQuadComponent(SceneRoot.Get());
		SetSingleQuad(QuadMesh, 50.0, 50.0);
		UMaterialInstanceDynamic* QuadMaterial = CreateHighlightMaterial(false, FLinearColor::White, 0.0f, 1.0f, 0.0f, 1.0f, 0.0f, 3.0f);
		if (QuadMaterial == nullptr)
		{
			QuadMesh->DestroyComponent();
			return INDEX_NONE;
		}
		QuadMesh->SetMaterial(0, QuadMaterial);
		QuadMesh->SetTranslucentSortPriority(20);
		QuadMesh->SetVisibility(false);
		FIronBoardFxQuad NewQuad;
		NewQuad.Mesh = QuadMesh;
		NewQuad.Material = QuadMaterial;
		Found = FxQuads.Add(NewQuad);
	}
	FIronBoardFxQuad& Quad = FxQuads[Found];
	Quad.bInUse = true;
	// Circle shape; RingRadius 0 + RingWidth 1 = a soft round glow, otherwise a ring. No material pulse for effects.
	SetHighlightShape(Quad.Material.Get(), 0.0f, RingRadius, RingWidth, FillOpacity, 1.0f, 0.0f, Intensity);
	Quad.Mesh->SetVisibility(false);
	return Found;
}

void AIronBattleBoard3D::ReleaseQuad(int32 QuadIndex)
{
	if (!FxQuads.IsValidIndex(QuadIndex))
	{
		return;
	}
	FIronBoardFxQuad& Quad = FxQuads[QuadIndex];
	Quad.bInUse = false;
	if (Quad.Mesh != nullptr)
	{
		Quad.Mesh->SetVisibility(false);
	}
}

void AIronBattleBoard3D::ReleaseQuads(TArray<int32>& QuadIndices)
{
	for (const int32 QuadIndex : QuadIndices)
	{
		ReleaseQuad(QuadIndex);
	}
	QuadIndices.Reset();
}

void AIronBattleBoard3D::PlaceQuad(int32 QuadIndex, const FVector& LocalCm, float SizeM, const FLinearColor& Color, bool bBillboard)
{
	if (!FxQuads.IsValidIndex(QuadIndex))
	{
		return;
	}
	FIronBoardFxQuad& Quad = FxQuads[QuadIndex];
	if (Quad.Mesh == nullptr || Quad.Material == nullptr)
	{
		return;
	}
	if (Color.A <= 0.003f || SizeM <= 0.01f)
	{
		if (Quad.Mesh->IsVisible())
		{
			Quad.Mesh->SetVisibility(false);
		}
		return;
	}
	FRotator Rotation = FRotator::ZeroRotator;
	if (bBillboard && BoardCamera != nullptr)
	{
		const FVector ToCamera = BoardCamera->GetActorLocation() - (GetActorLocation() + LocalCm);
		if (!ToCamera.IsNearlyZero())
		{
			Rotation = FRotationMatrix::MakeFromZ(ToCamera.GetSafeNormal()).Rotator();
		}
	}
	Quad.Mesh->SetRelativeLocationAndRotation(LocalCm, Rotation);
	Quad.Mesh->SetRelativeScale3D(FVector(static_cast<double>(SizeM), static_cast<double>(SizeM), 1.0));
	Quad.Material->SetVectorParameterValue(IronBattleBoard3DDetail::ColorParam(), Color);
	if (!Quad.Mesh->IsVisible())
	{
		Quad.Mesh->SetVisibility(true);
	}
}

int32 AIronBattleBoard3D::AcquireLight(const FLinearColor& Color, float RadiusCm)
{
	using namespace IronBattleBoard3DDetail;
	int32 Found = INDEX_NONE;
	for (int32 LightIndex = 0; LightIndex < LightPool.Num(); ++LightIndex)
	{
		if (!LightPool[LightIndex].bInUse && LightPool[LightIndex].Light != nullptr)
		{
			Found = LightIndex;
			break;
		}
	}
	if (Found == INDEX_NONE)
	{
		if (LightPool.Num() >= MaxLights)
		{
			return INDEX_NONE;
		}
		UPointLightComponent* NewLight = NewObject<UPointLightComponent>(this);
		NewLight->SetupAttachment(SceneRoot.Get());
		NewLight->SetMobility(EComponentMobility::Movable);
		// Candela: illuminance = I / d^2 lux, comparable with the environment's ~8 lux sun.
		NewLight->IntensityUnits = ELightUnits::Candelas;
		NewLight->SetCastShadows(QualityLevel >= 3);
		NewLight->SetSourceRadius(30.0f);
		NewLight->SetIntensity(0.0f);
		NewLight->SetVisibility(false);
		NewLight->RegisterComponent();
		FIronBoardLight NewEntry;
		NewEntry.Light = NewLight;
		Found = LightPool.Add(NewEntry);
	}
	FIronBoardLight& Entry = LightPool[Found];
	Entry.bInUse = true;
	Entry.Light->SetLightColor(Color);
	Entry.Light->SetAttenuationRadius(RadiusCm);
	Entry.Light->SetIntensity(0.0f);
	Entry.Light->SetVisibility(false);
	return Found;
}

void AIronBattleBoard3D::ReleaseLight(int32& LightIndex)
{
	if (LightPool.IsValidIndex(LightIndex))
	{
		FIronBoardLight& Entry = LightPool[LightIndex];
		Entry.bInUse = false;
		if (Entry.Light != nullptr)
		{
			Entry.Light->SetVisibility(false);
		}
	}
	LightIndex = INDEX_NONE;
}

void AIronBattleBoard3D::PlaceLight(int32 LightIndex, const FVector& LocalCm, float IntensityCandela)
{
	if (!LightPool.IsValidIndex(LightIndex) || LightPool[LightIndex].Light == nullptr)
	{
		return;
	}
	UPointLightComponent* PointLight = LightPool[LightIndex].Light.Get();
	const bool bLit = IntensityCandela > 0.5f;
	if (bLit)
	{
		PointLight->SetRelativeLocation(LocalCm);
		PointLight->SetIntensity(IntensityCandela);
	}
	if (PointLight->IsVisible() != bLit)
	{
		PointLight->SetVisibility(bLit);
	}
}

void AIronBattleBoard3D::ReleaseAllEffects()
{
	for (IronBoard3D::FBurn& Fire : Burns)
	{
		ReleaseLight(Fire.Light);
		ReleaseQuads(Fire.Quads);
	}
	Burns.Reset();
	for (FIronBoardUnitVisual& Visual : UnitVisuals)
	{
		ReleaseQuad(Visual.HaloQuad);
		Visual.HaloQuad = INDEX_NONE;
	}
	for (int32 QuadIndex = 0; QuadIndex < FxQuads.Num(); ++QuadIndex)
	{
		ReleaseQuad(QuadIndex);
	}
	for (int32 LightIndex = 0; LightIndex < LightPool.Num(); ++LightIndex)
	{
		int32 Released = LightIndex;
		ReleaseLight(Released);
	}
	if (HighlightMeshes.IsValidIndex(static_cast<int32>(IronBoard3D::ELayer::Burning)))
	{
		FillHexLayer(IronBoard3D::ELayer::Burning, TArray<IronSim::FHex>());
	}
	// Every track lost its effects: forget their pool indices so EndTrack does not release reused entries.
	for (IronBoard3D::FTrack& Track : AnimTracks)
	{
		Track.Quads.Reset();
		Track.Light = INDEX_NONE;
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Highlights
// ---------------------------------------------------------------------------------------------------------------------

void AIronBattleBoard3D::SetHighlights(const FIronBoardHighlights& InHighlights)
{
	const bool bLayersChanged = InHighlights.Reachable != Highlights.Reachable || InHighlights.AttackTargets != Highlights.AttackTargets || InHighlights.TacticTargets != Highlights.TacticTargets || InHighlights.DuelTargets != Highlights.DuelTargets;
	Highlights = InHighlights;
	bHighlightsDirty = bHighlightsDirty || bLayersChanged;
}

void AIronBattleBoard3D::SetHighlights(const TArray<IronSim::FHex>& Reachable, const TArray<IronSim::FHex>& AttackTargets, const TArray<IronSim::FHex>& TacticTargets, int32 SelectedUnit, const IronSim::FHex& HoveredHex)
{
	FIronBoardHighlights NewHighlights;
	NewHighlights.Reachable = Reachable;
	NewHighlights.AttackTargets = AttackTargets;
	NewHighlights.TacticTargets = TacticTargets;
	NewHighlights.SelectedUnit = SelectedUnit;
	NewHighlights.HoveredHex = HoveredHex;
	SetHighlights(NewHighlights);
}

void AIronBattleBoard3D::SetHoveredHex(const IronSim::FHex& Hex)
{
	Highlights.HoveredHex = Hex;
}

// ---------------------------------------------------------------------------------------------------------------------
// Picking and projection
// ---------------------------------------------------------------------------------------------------------------------

APlayerController* AIronBattleBoard3D::GetLocalController() const
{
	UWorld* GameWorld = GetWorld();
	return GameWorld != nullptr ? GameWorld->GetFirstPlayerController() : nullptr;
}

const FIronViewProjection& AIronBattleBoard3D::GetViewProjection() const
{
	FrameView.Refresh(GetLocalController());
	return FrameView;
}

bool AIronBattleBoard3D::DeprojectToBoard(const FVector2D& ViewportPixel, FVector2D& OutLocalM) const
{
	FVector RayOrigin;
	FVector RayDirection;
	if (!bBoardActive || !GetViewProjection().Deproject(ViewportPixel, RayOrigin, RayDirection))
	{
		return false;
	}
	const FVector BoardLocation = GetActorLocation();
	if (RayDirection.Z > -1.0e-4)
	{
		return false;
	}
	const double Distance = (BoardLocation.Z - RayOrigin.Z) / RayDirection.Z;
	if (Distance <= 0.0)
	{
		return false;
	}
	const FVector Hit = RayOrigin + RayDirection * Distance - BoardLocation;
	OutLocalM = FVector2D(Hit.X * IronWorld::MetresPerCm, Hit.Y * IronWorld::MetresPerCm);
	return true;
}

bool AIronBattleBoard3D::PickHex(const FVector2D& ViewportPixel, IronSim::FHex& OutHex) const
{
	using namespace IronBattleBoard3DDetail;
	if (!bBuilt || !bBoardActive)
	{
		return false;
	}
	// Units first: a squad model covers the hexes behind it, and players click the model they see (the nearest one).
	const FIronViewProjection& View = GetViewProjection();
	int32 BestUnit = INDEX_NONE;
	float BestDepth = TNumericLimits<float>::Max();
	for (int32 UnitId = 0; UnitId < UnitVisuals.Num(); ++UnitId)
	{
		const FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
		if (!Visual.bShown || !InBoard(Visual.RestHex))
		{
			continue;
		}
		const FVector Middle = GetActorLocation() + Visual.Location + Visual.Offset + FVector(0.0, 0.0, static_cast<double>(Visual.TopM) * 0.45 * IronWorld::CmPerMetre);
		FVector2D Centre;
		FVector2D Edge;
		float Depth = 0.0f;
		if (!View.Project(Middle, Centre, Depth) || !View.Project(Middle + FVector(UnitPickRadiusCm, 0.0, 0.0), Edge))
		{
			continue;
		}
		const double PixelRadius = FMath::Max(8.0, FVector2D::Distance(Centre, Edge));
		if (FVector2D::Distance(ViewportPixel, Centre) > PixelRadius)
		{
			continue;
		}
		if (Depth < BestDepth)
		{
			BestDepth = Depth;
			BestUnit = UnitId;
		}
	}
	if (BestUnit != INDEX_NONE)
	{
		OutHex = UnitVisuals[BestUnit].RestHex;
		return true;
	}

	FVector2D LocalM;
	if (!DeprojectToBoard(ViewportPixel, LocalM))
	{
		return false;
	}
	return LocalMToHex(LocalM, BoardCols, BoardRows, OutHex);
}

bool AIronBattleBoard3D::ProjectToViewport(const FVector& WorldLocationCm, FVector2D& OutViewportPixel, float& OutDepthCm) const
{
	return bBoardActive && GetViewProjection().Project(WorldLocationCm, OutViewportPixel, OutDepthCm);
}

bool AIronBattleBoard3D::ProjectToViewport(const FVector& WorldLocationCm, FVector2D& OutViewportPixel) const
{
	float DepthCm = 0.0f;
	return ProjectToViewport(WorldLocationCm, OutViewportPixel, DepthCm);
}

bool AIronBattleBoard3D::ProjectToViewport(const IronSim::FHex& Hex, float HeightM, FVector2D& OutViewportPixel) const
{
	return ProjectToViewport(HexToWorldLocation(Hex, HeightM), OutViewportPixel);
}

bool AIronBattleBoard3D::ProjectUnitToViewport(int32 UnitId, FVector2D& OutViewportPixel, float AboveModelM) const
{
	if (!IsUnitShown(UnitId))
	{
		return false;
	}
	const FIronBoardUnitVisual& Visual = UnitVisuals[UnitId];
	const double HeightCm = (static_cast<double>(Visual.TopM) + static_cast<double>(AboveModelM)) * IronWorld::CmPerMetre;
	return ProjectToViewport(GetActorLocation() + Visual.Location + Visual.Offset + FVector(0.0, 0.0, HeightCm), OutViewportPixel);
}

float AIronBattleBoard3D::GetGateTopHeightM(const IronSim::FHex& Hex) const
{
	using namespace IronBattleBoard3DDetail;
	const int32 GateIndex = GateIndexAt(Hex);
	if (GateIndex == INDEX_NONE)
	{
		return 0.0f;
	}
	// The tile as drawn now: the gatehouse, or the rubble once UpdateGates swapped the mesh.
	const UStaticMeshComponent* Tile = GateTiles.IsValidIndex(GateIndex) ? GateTiles[GateIndex].Get() : nullptr;
	const UStaticMesh* TileMesh = Tile != nullptr ? Tile->GetStaticMesh() : nullptr;
	if (TileMesh == nullptr)
	{
		return DefaultGateTopM;
	}
	return FMath::Max(0.5f, MeshTopM(TileMesh, Tile->GetRelativeScale3D().Z));
}

bool AIronBattleBoard3D::GetGateTopWorldLocation(const IronSim::FHex& Hex, FVector& OutWorldLocationCm) const
{
	const int32 GateIndex = GateIndexAt(Hex);
	if (GateIndex == INDEX_NONE)
	{
		return false;
	}
	const FVector Shake = GateOffsets.IsValidIndex(GateIndex) ? GateOffsets[GateIndex] : FVector::ZeroVector;
	OutWorldLocationCm = GetActorLocation() + HexLocalCm(Hex, static_cast<double>(GetGateTopHeightM(Hex))) + Shake;
	return true;
}

bool AIronBattleBoard3D::ProjectGateToViewport(const IronSim::FHex& Hex, FVector2D& OutViewportPixel, float AboveTopM) const
{
	FVector Top;
	return GetGateTopWorldLocation(Hex, Top) && ProjectToViewport(Top + FVector(0.0, 0.0, static_cast<double>(AboveTopM) * IronWorld::CmPerMetre), OutViewportPixel);
}

bool AIronBattleBoard3D::IsUnitShown(int32 UnitId) const
{
	return IsValidUnit(UnitId) && UnitVisuals[UnitId].bShown;
}

bool AIronBattleBoard3D::GetUnitWorldLocation(int32 UnitId, FVector& OutWorldLocationCm) const
{
	if (!IsValidUnit(UnitId))
	{
		return false;
	}
	OutWorldLocationCm = GetActorLocation() + UnitLocalNow(UnitId);
	return true;
}

float AIronBattleBoard3D::GetHexPixelSize() const
{
	const FVector Target = GetActorLocation() + FVector(CurrentTargetM.X * IronWorld::CmPerMetre, CurrentTargetM.Y * IronWorld::CmPerMetre, 0.0);
	FVector2D Centre;
	FVector2D Edge;
	if (!bBoardActive || !GetViewProjection().Project(Target, Centre) || !GetViewProjection().Project(Target + FVector(2.0 * IronBattleBoard3DDetail::HexRadiusCm, 0.0, 0.0), Edge))
	{
		return 0.0f;
	}
	return static_cast<float>(FVector2D::Distance(Centre, Edge));
}

// ---------------------------------------------------------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------------------------------------------------------

ACameraActor* AIronBattleBoard3D::GetCamera() const
{
	return BoardCamera.Get();
}

AIronEnvironment* AIronBattleBoard3D::GetEnvironment() const
{
	return Environment.Get();
}

FVector2D AIronBattleBoard3D::GetViewportSizePx() const
{
	FVector2D Size(1920.0, 1080.0);
	UWorld* GameWorld = GetWorld();
	if (GameWorld != nullptr)
	{
		if (UGameViewportClient* GameViewport = GameWorld->GetGameViewport())
		{
			FVector2D Measured = FVector2D::ZeroVector;
			GameViewport->GetViewportSize(Measured);
			if (Measured.X > 1.0 && Measured.Y > 1.0)
			{
				Size = Measured;
			}
		}
	}
	return Size;
}

void AIronBattleBoard3D::RecomputeFraming()
{
	using namespace IronBattleBoard3DDetail;
	const FVector2D Viewport = GetViewportSizePx();
	FramedViewportSize = Viewport;
	const double Aspect = Viewport.X / FMath::Max(1.0, Viewport.Y);

	const double HalfHeightM = HexHalfHeightCm * IronWorld::MetresPerCm;
	const double OddShiftM = BoardCols > 1 ? 0.5 * IronWorld::HexRowSpacingM : 0.0;
	BoardMinM = FVector2D(-IronWorld::HexRadiusM - FramingMarginM, -HalfHeightM - FramingMarginM);
	BoardMaxM = FVector2D(static_cast<double>(BoardCols - 1) * IronWorld::HexColumnSpacingM + IronWorld::HexRadiusM + FramingMarginM, static_cast<double>(BoardRows - 1) * IronWorld::HexRowSpacingM + OddShiftM + HalfHeightM + FramingMarginM);
	FitTargetM = (BoardMinM + BoardMaxM) * 0.5;

	// Smallest distance at the fit pitch that keeps every board corner (and the units standing there) inside the part
	// of the screen the Slate panels leave free.
	const double PitchRadians = FMath::DegreesToRadians(FitPitchDegrees);
	const FVector Forward(0.0, -FMath::Cos(PitchRadians), -FMath::Sin(PitchRadians));
	const FVector Right(1.0, 0.0, 0.0);
	const FVector Up(0.0, -FMath::Sin(PitchRadians), FMath::Cos(PitchRadians));
	const double TanHalf = FMath::Tan(FMath::DegreesToRadians(static_cast<double>(FieldOfViewDegrees) * 0.5));
	const double TanH = TanHalf * FMath::Max(0.25, 1.0 - static_cast<double>(InsetLeft) - static_cast<double>(InsetRight));
	const double TanV = TanHalf / Aspect * FMath::Max(0.25, 1.0 - static_cast<double>(InsetTop) - static_cast<double>(InsetBottom));
	double Needed = MinDistanceM;
	for (int32 Corner = 0; Corner < 8; ++Corner)
	{
		const FVector Point((Corner & 1) != 0 ? BoardMaxM.X : BoardMinM.X, (Corner & 2) != 0 ? BoardMaxM.Y : BoardMinM.Y, (Corner & 4) != 0 ? UnitHeightForFramingM : 0.0);
		const FVector Relative = Point - FVector(FitTargetM, 0.0);
		const double Along = FVector::DotProduct(Relative, Forward);
		Needed = FMath::Max(Needed, FMath::Abs(FVector::DotProduct(Relative, Right)) / TanH - Along);
		Needed = FMath::Max(Needed, FMath::Abs(FVector::DotProduct(Relative, Up)) / TanV - Along);
	}
	FitDistanceM = Needed;
	if (!bUserMovedCamera)
	{
		GoalTargetM = FitTargetM;
		GoalDistanceM = FitDistanceM;
	}
}

double AIronBattleBoard3D::PitchForDistance(double DistanceM) const
{
	using namespace IronBattleBoard3DDetail;
	// Lower and more cinematic close up, about 50 degrees at the whole-board framing, a little steeper beyond.
	const double Alpha = (DistanceM - MinDistanceM) / FMath::Max(1.0, FitDistanceM - MinDistanceM);
	if (Alpha <= 1.0)
	{
		return FMath::Lerp(ClosePitchDegrees, FitPitchDegrees, IronWorld::EaseInOut(FMath::Max(0.0, Alpha)));
	}
	return FMath::Min(FitPitchDegrees + (Alpha - 1.0) * 15.0, MaxPitchDegrees);
}

FVector AIronBattleBoard3D::ComputeCameraLocation(const FVector2D& TargetM, double DistanceM, double PitchDegrees) const
{
	using namespace IronBattleBoard3DDetail;
	const FVector2D Viewport = GetViewportSizePx();
	const double Aspect = Viewport.X / FMath::Max(1.0, Viewport.Y);
	const double PitchRadians = FMath::DegreesToRadians(PitchDegrees);
	const FVector Forward(0.0, -FMath::Cos(PitchRadians), -FMath::Sin(PitchRadians));
	const FVector Right(1.0, 0.0, 0.0);
	const FVector Up(0.0, -FMath::Sin(PitchRadians), FMath::Cos(PitchRadians));
	const double TanH = FMath::Tan(FMath::DegreesToRadians(static_cast<double>(FieldOfViewDegrees) * 0.5));
	const double TanV = TanH / Aspect;
	// Shift the camera sideways so the target lands in the middle of the free (not covered) part of the screen.
	const double ScreenX = static_cast<double>(InsetLeft) - static_cast<double>(InsetRight);
	const double ScreenY = static_cast<double>(InsetBottom) - static_cast<double>(InsetTop);
	const double DistanceCm = DistanceM * IronWorld::CmPerMetre;
	const FVector TargetWorld = GetActorLocation() + FVector(TargetM.X * IronWorld::CmPerMetre, TargetM.Y * IronWorld::CmPerMetre, 0.0);
	return TargetWorld - Forward * DistanceCm - Right * (ScreenX * DistanceCm * TanH) - Up * (ScreenY * DistanceCm * TanV);
}

FVector2D AIronBattleBoard3D::ClampTarget(const FVector2D& TargetM) const
{
	return FVector2D(FMath::Clamp(TargetM.X, BoardMinM.X, BoardMaxM.X), FMath::Clamp(TargetM.Y, BoardMinM.Y, BoardMaxM.Y));
}

void AIronBattleBoard3D::Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx)
{
	using namespace IronBattleBoard3DDetail;
	const FVector2D Viewport = ViewportSizePx.X > 1.0 && ViewportSizePx.Y > 1.0 ? ViewportSizePx : GetViewportSizePx();
	const double TanHalf = FMath::Tan(FMath::DegreesToRadians(static_cast<double>(FieldOfViewDegrees) * 0.5));
	const double MetresPerPixel = 2.0 * CurrentDistanceM * TanHalf / Viewport.X;
	const double PitchRadians = FMath::DegreesToRadians(PitchForDistance(CurrentDistanceM));
	// The ground point under the cursor follows it: screen-right is +X, screen-up is map north (-Y).
	GoalTargetM.X -= ScreenDeltaPx.X * MetresPerPixel;
	GoalTargetM.Y -= ScreenDeltaPx.Y * MetresPerPixel / FMath::Max(0.3, FMath::Sin(PitchRadians));
	GoalTargetM = ClampTarget(GoalTargetM);
	bUserMovedCamera = true;
}

void AIronBattleBoard3D::Zoom(float WheelDelta, const FVector2D& CursorViewportPixel)
{
	using namespace IronBattleBoard3DDetail;
	const double OldDistance = FMath::Max(1.0, GoalDistanceM);
	const double NewDistance = FMath::Clamp(OldDistance * FMath::Pow(ZoomStepFactor, static_cast<double>(WheelDelta)), MinDistanceM, FitDistanceM * MaxZoomOutFactor);
	if (NewDistance >= FitDistanceM * 0.98)
	{
		// Zoomed all the way out: back to the whole board.
		GoalTargetM = FitTargetM;
	}
	else
	{
		FVector2D CursorM;
		if (DeprojectToBoard(CursorViewportPixel, CursorM))
		{
			GoalTargetM = CursorM + (GoalTargetM - CursorM) * (NewDistance / OldDistance);
		}
	}
	GoalDistanceM = NewDistance;
	GoalTargetM = ClampTarget(GoalTargetM);
	bUserMovedCamera = true;
}

void AIronBattleBoard3D::ResetView(bool bInstant)
{
	GoalTargetM = FitTargetM;
	GoalDistanceM = FitDistanceM;
	bUserMovedCamera = false;
	if (bInstant)
	{
		CurrentTargetM = GoalTargetM;
		CurrentDistanceM = GoalDistanceM;
		TargetVelocity = FVector2D::ZeroVector;
		DistanceVelocity = 0.0;
		UpdateCamera(0.0f);
	}
}

void AIronBattleBoard3D::FocusHex(const IronSim::FHex& Hex, bool bOnlyIfOffscreen)
{
	using namespace IronBattleBoard3DDetail;
	if (!InBoard(Hex))
	{
		return;
	}
	if (bOnlyIfOffscreen)
	{
		const FVector2D Viewport = GetViewportSizePx();
		FVector2D Pixel;
		if (ProjectToViewport(Hex, 1.0f, Pixel))
		{
			const double MinX = Viewport.X * (static_cast<double>(InsetLeft) + FocusMarginFraction);
			const double MaxX = Viewport.X * (1.0 - static_cast<double>(InsetRight) - FocusMarginFraction);
			const double MinY = Viewport.Y * (static_cast<double>(InsetTop) + FocusMarginFraction);
			const double MaxY = Viewport.Y * (1.0 - static_cast<double>(InsetBottom) - FocusMarginFraction);
			if (Pixel.X >= MinX && Pixel.X <= MaxX && Pixel.Y >= MinY && Pixel.Y <= MaxY)
			{
				return;
			}
		}
	}
	GoalTargetM = ClampTarget(HexToLocalM(Hex));
	bUserMovedCamera = true;
}

void AIronBattleBoard3D::SetFramingInsets(float Left, float Top, float Right, float Bottom)
{
	InsetLeft = FMath::Clamp(Left, 0.0f, 0.45f);
	InsetTop = FMath::Clamp(Top, 0.0f, 0.45f);
	InsetRight = FMath::Clamp(Right, 0.0f, 0.45f);
	InsetBottom = FMath::Clamp(Bottom, 0.0f, 0.45f);
	if (bBuilt)
	{
		RecomputeFraming();
	}
}

void AIronBattleBoard3D::UpdateCamera(float DeltaSeconds)
{
	using namespace IronBattleBoard3DDetail;
	if (BoardCamera == nullptr || !bBuilt)
	{
		return;
	}
	if (!GetViewportSizePx().Equals(FramedViewportSize, 1.0))
	{
		RecomputeFraming();
	}
	const double Step = FMath::Clamp(static_cast<double>(DeltaSeconds), 0.0, MaxStepSeconds);
	GoalDistanceM = FMath::Clamp(GoalDistanceM, MinDistanceM, FitDistanceM * MaxZoomOutFactor);
	GoalTargetM = ClampTarget(GoalTargetM);
	CurrentTargetM.X = IronWorld::SmoothDamp(CurrentTargetM.X, GoalTargetM.X, TargetVelocity.X, TargetSmoothTime, Step);
	CurrentTargetM.Y = IronWorld::SmoothDamp(CurrentTargetM.Y, GoalTargetM.Y, TargetVelocity.Y, TargetSmoothTime, Step);
	CurrentDistanceM = IronWorld::SmoothDamp(CurrentDistanceM, GoalDistanceM, DistanceVelocity, DistanceSmoothTime, Step);

	const double PitchDegrees = PitchForDistance(CurrentDistanceM);
	const FVector CameraLocation = ComputeCameraLocation(CurrentTargetM, CurrentDistanceM, PitchDegrees);
	BoardCamera->SetActorLocationAndRotation(CameraLocation, FRotator(-PitchDegrees, IronWorld::NorthYawDegrees, 0.0));

	UCameraComponent* CameraComponent = BoardCamera->GetCameraComponent();
	if (CameraComponent == nullptr)
	{
		return;
	}
	// Tilt-shift: focus on the camera target, aperture solved for a fixed blur fraction at infinity (the same thin-lens
	// model as AIronEnvironment::SetTiltShift, with a gentler blur so the board stays readable). The camera's settings
	// override the environment's volume, so they follow its quality and tilt-shift strength here (the strategy map's
	// focus in the environment is never touched). A focal distance of 0 turns depth of field off.
	FPostProcessSettings& Settings = CameraComponent->PostProcessSettings;
	Settings.bOverride_DepthOfFieldFocalDistance = true;
	Settings.bOverride_DepthOfFieldFstop = true;
	const int32 SceneQuality = Environment != nullptr ? Environment->GetQuality() : QualityLevel;
	const double Strength = Environment != nullptr ? static_cast<double>(Environment->GetTiltShiftStrength()) : 1.0;
	const bool bDepthOfField = SceneQuality >= 1 && Strength > 0.001;
	const double FocusCm = CurrentDistanceM * IronWorld::CmPerMetre;
	if (!bDepthOfField)
	{
		Settings.DepthOfFieldFocalDistance = 0.0f;
		return;
	}
	const double HalfFovRadians = FMath::DegreesToRadians(static_cast<double>(FieldOfViewDegrees) * 0.5);
	const double FocalLengthMm = 0.5 * SensorWidthMm / FMath::Tan(HalfFovRadians);
	const double FocusMm = FocusCm * 10.0;
	const double Fstop = 0.5 * FocalLengthMm * FocalLengthMm / (FMath::Max(1.0, FocusMm - FocalLengthMm) * SensorWidthMm * TiltShiftCoc * Strength);
	Settings.DepthOfFieldFocalDistance = static_cast<float>(FocusCm);
	Settings.DepthOfFieldFstop = static_cast<float>(FMath::Clamp(Fstop, 0.0001, 32.0));
	Settings.DepthOfFieldFocalRegion = static_cast<float>(FocusCm * 0.1);
}

// ---------------------------------------------------------------------------------------------------------------------
// Sun and season
// ---------------------------------------------------------------------------------------------------------------------

double AIronBattleBoard3D::DayAlphaFor(int32 Day) const
{
	return FMath::Clamp(static_cast<double>(Day - 1) / static_cast<double>(FMath::Max(1, MaxDays - 1)), 0.0, 1.0);
}

void AIronBattleBoard3D::UpdateSun(float DeltaSeconds)
{
	using namespace IronBattleBoard3DDetail;
	if (!bBoardActive || Environment == nullptr)
	{
		return;
	}
	UDirectionalLightComponent* SunLight = Environment->GetSun();
	if (SunLight == nullptr)
	{
		return;
	}
	if (!bSunOverridden)
	{
		SavedSunRotation = SunLight->GetComponentRotation();
		bSunOverridden = true;
	}
	const double Step = FMath::Clamp(static_cast<double>(DeltaSeconds), 0.0, MaxStepSeconds);
	DayAlpha = Step > 0.0 ? IronWorld::SmoothDamp(DayAlpha, GoalDayAlpha, DayAlphaVelocity, SunSmoothTime, Step) : DayAlpha;

	// Day 1 at dawn (low eastern light), noon at mid-battle (as high as the season allows), the last day at dusk. The
	// sky atmosphere reddens the low sun by itself.
	const double Noon = FMath::Clamp(static_cast<double>(Environment->GetCurrentLook().SunElevationDegrees) + 12.0, 28.0, 56.0);
	const double Elevation = FMath::Lerp(HorizonElevationDegrees, Noon, FMath::Sin(UE_DOUBLE_PI * DayAlpha));
	const double BearingRadians = FMath::DegreesToRadians(FMath::Lerp(DawnBearingDegrees, DuskBearingDegrees, DayAlpha));
	// Same convention as AIronEnvironment: bearing 0 = light from the north (-Y), 90 = from the east (+X).
	const double TowardSunX = FMath::Sin(BearingRadians);
	const double TowardSunY = -FMath::Cos(BearingRadians);
	const double LightYaw = FMath::RadiansToDegrees(FMath::Atan2(-TowardSunY, -TowardSunX));
	const FRotator Wanted(-Elevation, LightYaw, 0.0);
	if (!SunLight->GetComponentRotation().Equals(Wanted, 0.01))
	{
		SunLight->SetWorldRotation(Wanted);
	}
}

void AIronBattleBoard3D::RestoreSun()
{
	if (!bSunOverridden)
	{
		return;
	}
	bSunOverridden = false;
	UDirectionalLightComponent* SunLight = Environment != nullptr ? Environment->GetSun() : nullptr;
	if (SunLight != nullptr)
	{
		SunLight->SetWorldRotation(SavedSunRotation);
	}
}

FLinearColor AIronBattleBoard3D::GroundColorForSeason() const
{
	using namespace IronBattleBoard3DDetail;
	double Autumn = 0.0;
	double Snow = 0.0;
	if (Environment != nullptr)
	{
		Autumn = static_cast<double>(Environment->GetCurrentLook().Autumn);
		Snow = static_cast<double>(Environment->GetCurrentLook().Snow);
	}
	else
	{
		const FIronSeasonLook Look = FIronSeasonLook::ForMonth(SeasonMonth);
		Autumn = static_cast<double>(Look.Autumn);
		Snow = static_cast<double>(Look.Snow);
	}
	const FLinearColor Leaves = FMath::Lerp(Rgb(GroundGreenRgb), Rgb(GroundAutumnRgb), static_cast<float>(FMath::Clamp(Autumn, 0.0, 1.0)));
	return FMath::Lerp(Leaves, Rgb(GroundSnowRgb), static_cast<float>(FMath::Clamp(Snow * 0.85, 0.0, 1.0)));
}

// ---------------------------------------------------------------------------------------------------------------------
// Tick
// ---------------------------------------------------------------------------------------------------------------------

void AIronBattleBoard3D::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bBoardActive)
	{
		return;
	}
	const float Step = FMath::Clamp(DeltaSeconds, 0.0f, static_cast<float>(IronBattleBoard3DDetail::MaxStepSeconds));
	if (bBuilt)
	{
		Clock += static_cast<double>(Step);
		ReconcileUnits();
		for (FVector& GateOffset : GateOffsets)
		{
			GateOffset = FVector::ZeroVector;
		}
		UpdateTracks();
		ApplyUnitTransforms(Step);
		UpdateGates();
		UpdateBurning();
		UpdateHalos();
		RefreshHighlightLayers();
		UpdateRings();
	}
	UpdateCamera(Step);
	UpdateSun(Step);
}
