#include "World/IronWorldMap3D.h"

#include "Sim/IronState.h"
#include "UI/IronSession.h"
#include "World/IronAssetManifest.h"
#include "World/IronCameraRig.h"
#include "World/IronEnvironment.h"
#include "World/IronTerrain.h"
#include "World/IronWorldAssets.h"
#include "World/IronWorldMath.h"

#include "Camera/PlayerCameraManager.h"
#include "Components/SceneComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/StaticMesh.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/App.h"

namespace IronWorldMap3DDetail
{
	constexpr int32 TroopTypeCount = 3;
	const TCHAR* const CityModels[3] = {TEXT("City_1"), TEXT("City_2"), TEXT("City_3")};
	/** Index = IronSim::ETroopType (Infantry, Cavalry, Archer). */
	const TCHAR* const UnitModels[TroopTypeCount] = {TEXT("Unit_Infantry"), TEXT("Unit_Cavalry"), TEXT("Unit_Archer")};
	/** Footprint radius per city size (models are ~45 / 75 / 120 m across). */
	constexpr float CityRadiusM[3] = {24.0f, 39.0f, 62.0f};
	/** Pennant scale per city size: a 10 m flag would vanish at strategic zoom. */
	constexpr double FlagScale[3] = {2.0, 2.4, 3.0};
	/** Squad dioramas (<= 6 m) are shown x6 on the strategy map (DESIGN.md 12.3). */
	constexpr double ArmyModelScale = 6.0;
	constexpr double ArmyBannerScale = 1.6;
	constexpr double ArmySpacingM = 32.0;
	constexpr float ArmyPickRadiusM = 20.0f;
	constexpr float CameraStartDistanceM = 1100.0f;
	constexpr float RingLiftM = 1.0f;

	FLinearColor HoverColor()
	{
		return IronWorld::ColorFromRGB(0xF2E6C8);
	}

	FLinearColor SelectedColor()
	{
		return IronWorld::ColorFromRGB(0xE6B84E);
	}

	FLinearColor TargetColor()
	{
		return IronWorld::ColorFromRGB(0xD8452F);
	}

	float CityRadius(int32 CitySize)
	{
		return CityRadiusM[FMath::Clamp(CitySize, 1, 3) - 1];
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

	/** Troop type with the most soldiers (the commander's type wins ties). */
	int32 DominantTroopType(const IronSim::FArmy& Army)
	{
		int32 Totals[TroopTypeCount] = {0, 0, 0};
		for (const IronSim::FArmyUnit& Unit : Army.Units)
		{
			const int32 Type = static_cast<int32>(Unit.Type);
			if (Type >= 0 && Type < TroopTypeCount)
			{
				Totals[Type] += Unit.Troops;
			}
		}
		int32 Best = Army.Units.empty() ? 0 : FMath::Clamp(static_cast<int32>(Army.Units.front().Type), 0, TroopTypeCount - 1);
		for (int32 Type = 0; Type < TroopTypeCount; ++Type)
		{
			if (Totals[Type] > Totals[Best])
			{
				Best = Type;
			}
		}
		return Best;
	}
}

AIronWorldMap3D::AIronWorldMap3D()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(SceneRoot);
}

// ---------------------------------------------------------------------------------------------------------------------
// Availability and creation
// ---------------------------------------------------------------------------------------------------------------------

bool AIronWorldMap3D::AreAssetsAvailable()
{
	static bool bConfirmed = false;
	static bool bReportedMissing = false;
	if (bConfirmed)
	{
		return true;
	}
	if (!FApp::CanEverRender())
	{
		return false;
	}

	FString Missing;
	if (!AIronTerrain::AreDataFilesPresent())
	{
		Missing = TEXT("Content/Data/Art3D/Terrain/Terrain.json + Height.png");
	}
	else if (LoadObject<UIronAssetManifest>(nullptr, TEXT("/Game/IronReign/IronReignAssetVersion.IronReignAssetVersion"), nullptr, LOAD_NoWarn | LOAD_Quiet) == nullptr)
	{
		// Written last by Content/Python/ironreign_import.py: without it the import never completed.
		Missing = TEXT("/Game/IronReign/IronReignAssetVersion (run the asset import)");
	}
	else
	{
		static const TCHAR* const RequiredModels[] = {TEXT("City_1"), TEXT("City_2"), TEXT("City_3"), TEXT("Unit_Infantry"), TEXT("Unit_Cavalry"), TEXT("Unit_Archer"), TEXT("Banner"), TEXT("Flag")};
		for (const TCHAR* ModelName : RequiredModels)
		{
			if (IronWorld::LoadModel(ModelName) == nullptr)
			{
				Missing = IronWorld::ModelObjectPath(ModelName);
				break;
			}
		}
		if (Missing.IsEmpty() && IronWorld::LoadMaterial(TEXT("MI_IronTerrain")) == nullptr && IronWorld::LoadMaterial(TEXT("M_IronTerrain")) == nullptr)
		{
			Missing = IronWorld::MaterialObjectPath(TEXT("M_IronTerrain"));
		}
		if (Missing.IsEmpty() && IronWorld::LoadMaterial(TEXT("M_IronTint")) == nullptr)
		{
			Missing = IronWorld::MaterialObjectPath(TEXT("M_IronTint"));
		}
	}

	if (!Missing.IsEmpty())
	{
		if (!bReportedMissing)
		{
			bReportedMissing = true;
			UE_LOG(LogIronWorld, Log, TEXT("3D campaign map unavailable (missing %s); using the 2D map."), *Missing);
		}
		return false;
	}
	bConfirmed = true;
	return true;
}

AIronWorldMap3D* AIronWorldMap3D::FindMap(UWorld* World)
{
	if (World == nullptr)
	{
		return nullptr;
	}
	for (TActorIterator<AIronWorldMap3D> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			return *It;
		}
	}
	return nullptr;
}

AIronWorldMap3D* AIronWorldMap3D::SpawnMap(UWorld* World, TSharedPtr<FIronSession> InSession, int32 InQualityLevel)
{
	if (World == nullptr)
	{
		return nullptr;
	}
	AIronWorldMap3D* MapActor = FindMap(World);
	if (MapActor == nullptr)
	{
		FActorSpawnParameters SpawnParams;
		SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
		SpawnParams.ObjectFlags |= RF_Transient;
		MapActor = World->SpawnActor<AIronWorldMap3D>(AIronWorldMap3D::StaticClass(), FTransform::Identity, SpawnParams);
	}
	if (MapActor != nullptr && !MapActor->bInitialized)
	{
		MapActor->Initialize(InSession, InQualityLevel);
	}
	return MapActor;
}

void AIronWorldMap3D::Initialize(TSharedPtr<FIronSession> InSession, int32 InQualityLevel)
{
	UWorld* GameWorld = GetWorld();
	if (bInitialized || GameWorld == nullptr)
	{
		return;
	}
	bInitialized = true;
	Session = InSession;
	QualityLevel = FMath::Clamp(InQualityLevel, 0, 3);
	LoadAssets();

	Environment = AIronEnvironment::FindOrSpawn(GameWorld);
	if (Environment != nullptr)
	{
		Environment->SetQuality(QualityLevel);
	}

	FActorSpawnParameters SpawnParams;
	SpawnParams.Owner = this;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	SpawnParams.ObjectFlags |= RF_Transient;

	Terrain = GameWorld->SpawnActor<AIronTerrain>(AIronTerrain::StaticClass(), FTransform::Identity, SpawnParams);
	if (Terrain != nullptr)
	{
		Terrain->BeginBuild(QualityLevel >= 3 ? 1 : 2);
		if (Environment != nullptr)
		{
			Environment->RegisterSeasonMaterial(Terrain->GetTerrainMaterial());
		}
	}

	CameraRig = GameWorld->SpawnActor<AIronCameraRig>(AIronCameraRig::StaticClass(), FTransform::Identity, SpawnParams);
	if (CameraRig != nullptr)
	{
		CameraRig->SetTerrain(Terrain.Get());
		// Read the camera after it moved this frame (tilt-shift focus, highlights).
		AddTickPrerequisiteActor(CameraRig.Get());
	}

	const TSharedPtr<FIronSession> Pinned = Session.Pin();
	if (Pinned.IsValid() && Pinned->HasGame())
	{
		const IronSim::FGameState& State = Pinned->State();
		if (CameraRig != nullptr)
		{
			CameraRig->SetMapBounds(FVector2D(static_cast<double>(State.Map.Width), static_cast<double>(State.Map.Height)));
		}
		SnapCameraToPlayer(State);
		LastMonth = State.Month;
		if (Environment != nullptr)
		{
			Environment->SetSeason(State.Month, true);
		}
	}

	// Hidden until the strategy screen activates it.
	bMapActive = false;
	ApplyVisibility();
	if (CameraRig != nullptr)
	{
		CameraRig->SetActorTickEnabled(false);
	}
}

void AIronWorldMap3D::LoadAssets()
{
	CityMeshes.Reset();
	for (const TCHAR* ModelName : IronWorldMap3DDetail::CityModels)
	{
		CityMeshes.Add(IronWorld::LoadModel(ModelName));
	}
	UnitMeshes.Reset();
	for (const TCHAR* ModelName : IronWorldMap3DDetail::UnitModels)
	{
		UnitMeshes.Add(IronWorld::LoadModel(ModelName));
	}
	BannerMesh = IronWorld::LoadModel(TEXT("Banner"));
	FlagMesh = IronWorld::LoadModel(TEXT("Flag"));
	SectMesh = IronWorld::LoadModel(TEXT("Sect"));
	TintMaterial = IronWorld::LoadMaterial(TEXT("M_IronTint"));
	HighlightMaterial = IronWorld::LoadMaterial(TEXT("M_IronHighlight"));
	// M_IronHighlight draws the ring from the plane's UVs; without it a plain plane would be an opaque square, so the
	// map then shows no rings (the panels still show the selection).
	RingMesh = HighlightMaterial != nullptr ? IronWorld::LoadPlaneMesh() : nullptr;
	if (HighlightMaterial == nullptr)
	{
		UE_LOG(LogIronWorld, Warning, TEXT("M_IronHighlight was not imported; selection rings are disabled."));
	}
}

AIronCameraRig* AIronWorldMap3D::GetCameraRig() const
{
	return CameraRig.Get();
}

AIronEnvironment* AIronWorldMap3D::GetEnvironment() const
{
	return Environment.Get();
}

AIronTerrain* AIronWorldMap3D::GetTerrain() const
{
	return Terrain.Get();
}

APlayerController* AIronWorldMap3D::GetLocalController() const
{
	UWorld* GameWorld = GetWorld();
	return GameWorld != nullptr ? GameWorld->GetFirstPlayerController() : nullptr;
}

float AIronWorldMap3D::SurfaceAt(const FVector2D& MapPointM) const
{
	return Terrain != nullptr ? Terrain->SampleSurface(MapPointM) : 0.0f;
}

// ---------------------------------------------------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------------------------------------------------

void AIronWorldMap3D::SetActive(bool bInActive, float BlendSeconds)
{
	bMapActive = bInActive;
	ApplyVisibility();
	if (CameraRig != nullptr)
	{
		CameraRig->SetActorTickEnabled(bMapActive);
	}

	UWorld* GameWorld = GetWorld();
	if (GameWorld != nullptr)
	{
		if (UGameViewportClient* GameViewport = GameWorld->GetGameViewport())
		{
			// AIronReignPlayerController disables world rendering for the pure-Slate screens.
			GameViewport->bDisableWorldRendering = !bMapActive;
		}
	}

	if (bMapActive)
	{
		APlayerController* Controller = GetLocalController();
		if (Controller != nullptr && CameraRig != nullptr)
		{
			// The first time there is nothing sensible to blend from (the controller sits at the world origin).
			const float Blend = bEverActivated ? FMath::Max(0.0f, BlendSeconds) : 0.0f;
			Controller->SetViewTargetWithBlend(CameraRig.Get(), Blend, EViewTargetBlendFunction::VTBlend_EaseInOut, 2.0f, false);
			bEverActivated = true;
		}
		RefreshFromState();
	}
}

void AIronWorldMap3D::ApplyVisibility()
{
	SetActorHiddenInGame(!bMapActive);
	if (Terrain != nullptr)
	{
		Terrain->SetActorHiddenInGame(!bMapActive);
	}
}

bool AIronWorldMap3D::IsSceneReady() const
{
	return Terrain != nullptr && Terrain->IsBuildComplete() && bCitiesBuilt;
}

bool AIronWorldMap3D::HasFailed() const
{
	return Terrain == nullptr || Terrain->HasFailed();
}

void AIronWorldMap3D::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	if (EndPlayReason == EEndPlayReason::Destroyed)
	{
		// The terrain and camera belong to this map; the environment is shared and stays.
		if (Terrain != nullptr)
		{
			Terrain->Destroy();
		}
		if (CameraRig != nullptr)
		{
			CameraRig->Destroy();
		}
	}
	Terrain = nullptr;
	CameraRig = nullptr;
	Super::EndPlay(EndPlayReason);
}

void AIronWorldMap3D::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (!bInitialized)
	{
		return;
	}

	const TSharedPtr<FIronSession> Pinned = Session.Pin();
	if (Pinned.IsValid() && Pinned->HasGame() && Terrain != nullptr && Terrain->IsHeightReady())
	{
		const IronSim::FGameState& State = Pinned->State();
		if (!bBoundsSet && CameraRig != nullptr)
		{
			CameraRig->SetMapBounds(Terrain->GetMapSizeM());
			bBoundsSet = true;
		}
		if (!bCitiesBuilt || NeedsCityRebuild(State))
		{
			BuildCities(State);
		}
		if (bMapActive)
		{
			SyncOwners(State);
			SyncArmies(State, DeltaSeconds);
			SyncSeason(State);
		}
	}

	if (!bMapActive)
	{
		return;
	}
	UpdateHighlights();
	if (Environment != nullptr && CameraRig != nullptr)
	{
		Environment->SetTiltShift(CameraRig->GetCameraDistanceCm(), CameraRig->GetFieldOfView());
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Game state
// ---------------------------------------------------------------------------------------------------------------------

void AIronWorldMap3D::SetFractionalDay(float Fraction)
{
	FractionalDay = FMath::Clamp(Fraction, 0.0f, 1.0f);
}

void AIronWorldMap3D::RefreshFromState()
{
	const TSharedPtr<FIronSession> Pinned = Session.Pin();
	if (!Pinned.IsValid() || !Pinned->HasGame() || Terrain == nullptr || !Terrain->IsHeightReady())
	{
		return;
	}
	const IronSim::FGameState& State = Pinned->State();
	if (!bCitiesBuilt || NeedsCityRebuild(State))
	{
		BuildCities(State);
	}
	else
	{
		for (FIronCityVisual& Visual : CityVisuals)
		{
			Visual.TintedOwner = -2;
		}
		SyncOwners(State);
	}
	SyncArmies(State, 0.0f);
	SyncSeason(State);
}

void AIronWorldMap3D::SetSeasonFromMonth(int32 Month)
{
	LastMonth = Month;
	if (Environment != nullptr)
	{
		Environment->SetSeason(Month);
	}
}

void AIronWorldMap3D::SyncSeason(const IronSim::FGameState& State)
{
	if (State.Month != LastMonth)
	{
		SetSeasonFromMonth(State.Month);
	}
}

void AIronWorldMap3D::SetQuality(int32 Level)
{
	QualityLevel = FMath::Clamp(Level, 0, 3);
	if (Environment != nullptr)
	{
		Environment->SetQuality(QualityLevel);
	}
}

void AIronWorldMap3D::SnapCameraToPlayer(const IronSim::FGameState& State)
{
	if (CameraRig == nullptr)
	{
		return;
	}
	FVector2D Focus(static_cast<double>(State.Map.Width) * 0.5, static_cast<double>(State.Map.Height) * 0.5);
	float DistanceM = static_cast<float>(IronWorld::CameraMaxDistanceM) * 0.85f;
	if (State.PlayerFaction >= 0 && State.PlayerFaction < static_cast<int>(State.Factions.size()))
	{
		const int Capital = State.Factions[static_cast<size_t>(State.PlayerFaction)].Capital;
		if (Capital >= 0 && Capital < static_cast<int>(State.Cities.size()))
		{
			Focus = IronWorld::FromSim(State.Cities[static_cast<size_t>(Capital)].Position);
			DistanceM = IronWorldMap3DDetail::CameraStartDistanceM;
		}
	}
	CameraRig->SnapTo(Focus, DistanceM);
}

bool AIronWorldMap3D::NeedsCityRebuild(const IronSim::FGameState& State) const
{
	return CityVisuals.Num() != static_cast<int32>(State.Cities.size()) || BuiltScenarioKey != State.ScenarioKey;
}

UStaticMeshComponent* AIronWorldMap3D::CreateMeshComponent(UStaticMesh* Mesh)
{
	UStaticMeshComponent* Component = NewObject<UStaticMeshComponent>(this);
	Component->SetupAttachment(SceneRoot);
	Component->SetMobility(EComponentMobility::Movable);
	Component->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Component->SetGenerateOverlapEvents(false);
	Component->SetCanEverAffectNavigation(false);
	Component->SetStaticMesh(Mesh);
	Component->RegisterComponent();
	return Component;
}

UStaticMesh* AIronWorldMap3D::CityMeshFor(int32 CitySize) const
{
	const int32 Wanted = FMath::Clamp(CitySize, 1, 3) - 1;
	// The requested size first, then the nearest other size.
	const int32 Order[3] = {Wanted, Wanted == 0 ? 1 : Wanted - 1, Wanted == 2 ? 0 : 2};
	for (const int32 Index : Order)
	{
		if (CityMeshes.IsValidIndex(Index) && CityMeshes[Index] != nullptr)
		{
			return CityMeshes[Index].Get();
		}
	}
	return nullptr;
}

UStaticMesh* AIronWorldMap3D::UnitMeshFor(int32 TroopType) const
{
	if (UnitMeshes.IsValidIndex(TroopType) && UnitMeshes[TroopType] != nullptr)
	{
		return UnitMeshes[TroopType].Get();
	}
	for (const TObjectPtr<UStaticMesh>& Mesh : UnitMeshes)
	{
		if (Mesh != nullptr)
		{
			return Mesh.Get();
		}
	}
	return nullptr;
}

void AIronWorldMap3D::ClearCities()
{
	for (FIronCityVisual& Visual : CityVisuals)
	{
		if (Visual.Body != nullptr)
		{
			Visual.Body->DestroyComponent();
		}
		if (Visual.Flag != nullptr)
		{
			Visual.Flag->DestroyComponent();
		}
	}
	CityVisuals.Reset();
	for (const TObjectPtr<UStaticMeshComponent>& Marker : SectMarkers)
	{
		if (Marker != nullptr)
		{
			Marker->DestroyComponent();
		}
	}
	SectMarkers.Reset();
	bCitiesBuilt = false;
}

void AIronWorldMap3D::BuildCities(const IronSim::FGameState& State)
{
	using namespace IronWorldMap3DDetail;
	ClearCities();

	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	// Gates face the default camera (map south, +Y).
	const double FacingYaw = IronWorld::ModelYawDegrees(ModelParams.FrontYawDegrees, IronWorld::SouthYawDegrees);
	const FRotator Facing(0.0, FacingYaw, 0.0);

	const int32 CityCount = static_cast<int32>(State.Cities.size());
	CityVisuals.SetNum(CityCount);
	for (int32 CityIndex = 0; CityIndex < CityCount; ++CityIndex)
	{
		const IronSim::FCity& City = State.Cities[static_cast<size_t>(CityIndex)];
		FIronCityVisual& Visual = CityVisuals[CityIndex];
		Visual.CitySize = FMath::Clamp(City.Size, 1, 3);
		Visual.MapPoint = IronWorld::FromSim(City.Position);
		Visual.GroundM = SurfaceAt(Visual.MapPoint);
		Visual.TintedOwner = -2;

		if (UStaticMesh* BodyMesh = CityMeshFor(Visual.CitySize))
		{
			const double Scale = ModelParams.ScaleOf(CityModels[Visual.CitySize - 1]);
			Visual.Body = CreateMeshComponent(BodyMesh);
			Visual.Body->SetWorldLocationAndRotation(IronWorld::MapToWorld(Visual.MapPoint, Visual.GroundM), Facing);
			Visual.Body->SetWorldScale3D(FVector(Scale));
			Visual.TopM = FMath::Max(10.0f, MeshTopM(BodyMesh, Scale));
		}

		if (FlagMesh != nullptr)
		{
			// The pennant stands at the front-right corner of the walls, toward the camera.
			const float Radius = CityRadius(Visual.CitySize);
			const FVector2D FlagPoint = Visual.MapPoint + FVector2D(Radius * 0.8, Radius * 0.85);
			const double Scale = FlagScale[Visual.CitySize - 1] * ModelParams.ScaleOf(TEXT("Flag"));
			Visual.Flag = CreateMeshComponent(FlagMesh.Get());
			Visual.Flag->SetCastShadow(true);
			Visual.Flag->SetWorldLocationAndRotation(IronWorld::MapToWorld(FlagPoint, SurfaceAt(FlagPoint)), Facing);
			Visual.Flag->SetWorldScale3D(FVector(Scale));
		}
	}

	BuiltScenarioKey = State.ScenarioKey;
	bCitiesBuilt = true;
	SyncOwners(State);
	PlaceSects(State);

	if (HoverRing == nullptr)
	{
		HoverRing = CreateRing(HoverColor());
	}
	if (SelectedRing == nullptr)
	{
		SelectedRing = CreateRing(SelectedColor());
	}
	if (ArmyRing == nullptr)
	{
		ArmyRing = CreateRing(SelectedColor());
	}
}

void AIronWorldMap3D::PlaceSects(const IronSim::FGameState& State)
{
	if (SectMesh == nullptr)
	{
		return;
	}
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	const double Scale = ModelParams.ScaleOf(TEXT("Sect"));
	const FRotator Facing(0.0, IronWorld::ModelYawDegrees(ModelParams.FrontYawDegrees, IronWorld::SouthYawDegrees), 0.0);
	const float SeaLevel = Terrain != nullptr ? Terrain->GetSeaLevelM() : 0.0f;

	for (const IronSim::FSect& Sect : State.Sects)
	{
		if (Sect.City < 0 || Sect.City >= CityVisuals.Num())
		{
			continue;
		}
		const FIronCityVisual& Home = CityVisuals[Sect.City];
		const double SpotDistance = static_cast<double>(IronWorldMap3DDetail::CityRadius(Home.CitySize)) + 48.0;
		// Temples like high ground: try eight spots around the city, keep the highest dry one clear of other cities.
		FVector2D Best = Home.MapPoint + FVector2D(SpotDistance * 0.7, -SpotDistance * 0.7);
		float BestHeight = -TNumericLimits<float>::Max();
		for (int32 Step = 0; Step < 8; ++Step)
		{
			const double Angle = UE_DOUBLE_PI * 0.25 * static_cast<double>(Step);
			const FVector2D Candidate = Home.MapPoint + FVector2D(FMath::Cos(Angle), FMath::Sin(Angle)) * SpotDistance;
			const float Height = Terrain != nullptr ? Terrain->SampleHeight(Candidate) : 0.0f;
			if (Height < SeaLevel + 1.0f)
			{
				continue;
			}
			bool bClear = true;
			for (const FIronCityVisual& Other : CityVisuals)
			{
				if (&Other != &Home && FVector2D::Distance(Other.MapPoint, Candidate) < static_cast<double>(IronWorldMap3DDetail::CityRadius(Other.CitySize)) + 30.0)
				{
					bClear = false;
					break;
				}
			}
			if (bClear && Height > BestHeight)
			{
				BestHeight = Height;
				Best = Candidate;
			}
		}
		UStaticMeshComponent* Marker = CreateMeshComponent(SectMesh.Get());
		Marker->SetWorldLocationAndRotation(IronWorld::MapToWorld(Best, SurfaceAt(Best)), Facing);
		Marker->SetWorldScale3D(FVector(Scale));
		SectMarkers.Add(Marker);
	}
}

void AIronWorldMap3D::SyncOwners(const IronSim::FGameState& State)
{
	const int32 CityCount = FMath::Min(CityVisuals.Num(), static_cast<int32>(State.Cities.size()));
	for (int32 CityIndex = 0; CityIndex < CityCount; ++CityIndex)
	{
		FIronCityVisual& Visual = CityVisuals[CityIndex];
		const int32 OwnerIndex = State.Cities[static_cast<size_t>(CityIndex)].Owner;
		if (OwnerIndex == Visual.TintedOwner)
		{
			continue;
		}
		Visual.TintedOwner = OwnerIndex;
		const FLinearColor Color = IronWorld::FactionColor(State, OwnerIndex);
		if (Visual.Flag != nullptr)
		{
			Visual.FlagTint = IronWorld::ApplyTint(Visual.Flag.Get(), Color, Visual.FlagTint.Get(), TintMaterial.Get());
		}
		if (Visual.Body != nullptr)
		{
			Visual.BodyTint = IronWorld::ApplyTint(Visual.Body.Get(), Color, Visual.BodyTint.Get(), TintMaterial.Get());
		}
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Armies
// ---------------------------------------------------------------------------------------------------------------------

void AIronWorldMap3D::SyncArmies(const IronSim::FGameState& State, float DeltaSeconds)
{
	using namespace IronWorldMap3DDetail;
	for (TPair<int32, FIronArmyVisual>& Pair : ArmyVisuals)
	{
		Pair.Value.bSeen = false;
	}

	TArray<FVector2D> Placed;
	for (const IronSim::FArmy& Army : State.Armies)
	{
		if (Army.Units.empty())
		{
			continue;
		}
		FVector2D Point = FVector2D::ZeroVector;
		FVector2D Heading = FVector2D::ZeroVector;
		if (Army.Next >= 0 && Army.Road >= 0)
		{
			// On the road: interpolated position, facing along the road.
			Point = IronWorld::FromSim(State.ArmyPosition(Army, FractionalDay));
			const float Length = static_cast<float>(FMath::Max(1, State.RoadLength(Army.Road)));
			const float Along = FMath::Clamp((static_cast<float>(Army.Progress) + FractionalDay * static_cast<float>(State.ArmySpeed(Army))) / Length, 0.0f, 1.0f);
			const FVector2D Behind = IronWorld::FromSim(State.RoadPoint(Army.Road, Army.Node, FMath::Max(0.0f, Along - 0.02f)));
			const FVector2D Ahead = IronWorld::FromSim(State.RoadPoint(Army.Road, Army.Node, FMath::Min(1.0f, Along + 0.02f)));
			Heading = Ahead - Behind;
		}
		else
		{
			// Waiting in a city: camp beside the walls, toward the camera.
			Point = IronWorld::FromSim(State.ArmyPosition(Army, 0.0f));
			const int32 CitySize = CityVisuals.IsValidIndex(Army.Node) ? CityVisuals[Army.Node].CitySize : 2;
			Point += FVector2D(static_cast<double>(CityRadius(CitySize)) + 18.0, 14.0);
		}
		for (int32 Guard = 0; Guard < 8; ++Guard)
		{
			bool bOverlaps = false;
			for (const FVector2D& Other : Placed)
			{
				if (FVector2D::DistSquared(Other, Point) < ArmySpacingM * ArmySpacingM)
				{
					bOverlaps = true;
					break;
				}
			}
			if (!bOverlaps)
			{
				break;
			}
			Point.X += ArmySpacingM;
		}
		Placed.Add(Point);

		FIronArmyVisual& Visual = ArmyVisuals.FindOrAdd(Army.Id);
		Visual.bSeen = true;
		UpdateArmyVisual(Visual, Army, State, Point, Heading, DeltaSeconds);
	}

	for (TMap<int32, FIronArmyVisual>::TIterator It = ArmyVisuals.CreateIterator(); It; ++It)
	{
		if (!It.Value().bSeen)
		{
			DestroyArmyVisual(It.Value());
			It.RemoveCurrent();
		}
	}
}

void AIronWorldMap3D::UpdateArmyVisual(FIronArmyVisual& Visual, const IronSim::FArmy& Army, const IronSim::FGameState& State, const FVector2D& MapPointM, const FVector2D& Heading, float DeltaSeconds)
{
	using namespace IronWorldMap3DDetail;
	const IronWorld::FModelParams& ModelParams = IronWorld::GetModelParams();
	const int32 Type = DominantTroopType(Army);

	if (Visual.Unit == nullptr || Visual.TroopType != Type)
	{
		if (UStaticMesh* UnitMesh = UnitMeshFor(Type))
		{
			if (Visual.Unit == nullptr)
			{
				Visual.Unit = CreateMeshComponent(UnitMesh);
			}
			else
			{
				// The old tint instances belong to the old mesh's slots.
				Visual.Unit->EmptyOverrideMaterials();
				Visual.Unit->SetStaticMesh(UnitMesh);
			}
			// New mesh: the tint instance must be recreated for its slots.
			Visual.UnitTint = nullptr;
			Visual.TintedFaction = -2;
		}
		Visual.TroopType = Type;
	}
	if (Visual.Banner == nullptr && BannerMesh != nullptr)
	{
		Visual.Banner = CreateMeshComponent(BannerMesh.Get());
		Visual.TintedFaction = -2;
	}
	if (Visual.TintedFaction != Army.Faction)
	{
		Visual.TintedFaction = Army.Faction;
		const FLinearColor Color = IronWorld::FactionColor(State, Army.Faction);
		if (Visual.Unit != nullptr)
		{
			Visual.UnitTint = IronWorld::ApplyTint(Visual.Unit.Get(), Color, Visual.UnitTint.Get(), TintMaterial.Get());
		}
		if (Visual.Banner != nullptr)
		{
			Visual.BannerTint = IronWorld::ApplyTint(Visual.Banner.Get(), Color, Visual.BannerTint.Get(), TintMaterial.Get());
		}
	}

	// Facing: along the road while marching, toward the camera while waiting. Smoothed, then snapped when settled so a
	// resting army stops touching its transform (keeps virtual shadow map pages cached).
	const float TargetYaw = Heading.SizeSquared() > 1.0e-4 ? static_cast<float>(IronWorld::DirectionToYawDegrees(Heading)) : static_cast<float>(IronWorld::SouthYawDegrees);
	if (!Visual.bHasFacing)
	{
		Visual.FacingYaw = TargetYaw;
		Visual.bHasFacing = true;
	}
	else
	{
		const float Delta = FMath::FindDeltaAngleDegrees(Visual.FacingYaw, TargetYaw);
		Visual.FacingYaw = FMath::Abs(Delta) < 0.05f ? TargetYaw : Visual.FacingYaw + Delta * FMath::Min(1.0f, DeltaSeconds * 6.0f);
	}

	Visual.MapPoint = MapPointM;
	Visual.GroundM = SurfaceAt(MapPointM);
	const FRotator ModelRotation(0.0, IronWorld::ModelYawDegrees(ModelParams.FrontYawDegrees, static_cast<double>(Visual.FacingYaw)), 0.0);
	float Top = 0.0f;
	if (Visual.Unit != nullptr)
	{
		const double Scale = ArmyModelScale * ModelParams.ScaleOf(UnitModels[FMath::Clamp(Type, 0, TroopTypeCount - 1)]);
		Visual.Unit->SetWorldLocationAndRotation(IronWorld::MapToWorld(MapPointM, Visual.GroundM), ModelRotation);
		Visual.Unit->SetWorldScale3D(FVector(Scale));
		Top = FMath::Max(Top, MeshTopM(Visual.Unit->GetStaticMesh(), Scale));
	}
	if (Visual.Banner != nullptr)
	{
		// The standard-bearer walks behind and to the right of the squad.
		const double YawRadians = FMath::DegreesToRadians(static_cast<double>(Visual.FacingYaw));
		const FVector2D Ahead(FMath::Cos(YawRadians), FMath::Sin(YawRadians));
		const FVector2D Side(-Ahead.Y, Ahead.X);
		const FVector2D BannerPoint = MapPointM - Ahead * 10.0 + Side * 7.0;
		const double Scale = ArmyBannerScale * ModelParams.ScaleOf(TEXT("Banner"));
		Visual.Banner->SetWorldLocationAndRotation(IronWorld::MapToWorld(BannerPoint, SurfaceAt(BannerPoint)), ModelRotation);
		Visual.Banner->SetWorldScale3D(FVector(Scale));
		Top = FMath::Max(Top, MeshTopM(Visual.Banner->GetStaticMesh(), Scale));
	}
	Visual.TopM = FMath::Max(8.0f, Top);
}

void AIronWorldMap3D::DestroyArmyVisual(FIronArmyVisual& Visual)
{
	if (Visual.Unit != nullptr)
	{
		Visual.Unit->DestroyComponent();
		Visual.Unit = nullptr;
	}
	if (Visual.Banner != nullptr)
	{
		Visual.Banner->DestroyComponent();
		Visual.Banner = nullptr;
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Highlights
// ---------------------------------------------------------------------------------------------------------------------

void AIronWorldMap3D::SetHoveredCity(int32 CityIndex)
{
	HoveredCity = CityIndex;
}

void AIronWorldMap3D::SetSelectedCity(int32 CityIndex)
{
	SelectedCity = CityIndex;
}

void AIronWorldMap3D::SetTargetCities(const TArray<int32>& CityIndices)
{
	TargetCities = CityIndices;
}

void AIronWorldMap3D::SetSelectedArmy(int32 ArmyId)
{
	SelectedArmyId = ArmyId;
}

UStaticMeshComponent* AIronWorldMap3D::CreateRing(const FLinearColor& Color)
{
	if (RingMesh == nullptr)
	{
		return nullptr;
	}
	// A 1 m plane (UV 0..1) that M_IronHighlight renders as a glowing, gently pulsing ring.
	UStaticMeshComponent* Ring = CreateMeshComponent(RingMesh.Get());
	Ring->SetCastShadow(false);
	if (UMaterialInstanceDynamic* RingMaterial = IronWorld::MakeColoredMaterial(HighlightMaterial.Get(), Ring, Color))
	{
		Ring->SetMaterial(0, RingMaterial);
	}
	Ring->SetVisibility(false);
	return Ring;
}

void AIronWorldMap3D::PlaceRing(UStaticMeshComponent* Ring, const FVector2D& MapPointM, float GroundM, float DiameterM)
{
	if (Ring == nullptr)
	{
		return;
	}
	// The plane is 100 x 100 cm, so the scale is the diameter in metres.
	Ring->SetWorldLocation(IronWorld::MapToWorld(MapPointM, static_cast<double>(GroundM + IronWorldMap3DDetail::RingLiftM)));
	Ring->SetWorldScale3D(FVector(DiameterM, DiameterM, 1.0f));
	Ring->SetVisibility(true);
}

void AIronWorldMap3D::ShowCityRing(UStaticMeshComponent* Ring, int32 CityIndex, float DiameterScale)
{
	if (Ring == nullptr)
	{
		return;
	}
	if (!CityVisuals.IsValidIndex(CityIndex))
	{
		Ring->SetVisibility(false);
		return;
	}
	const FIronCityVisual& Visual = CityVisuals[CityIndex];
	PlaceRing(Ring, Visual.MapPoint, Visual.GroundM, 2.0f * IronWorldMap3DDetail::CityRadius(Visual.CitySize) * DiameterScale);
}

void AIronWorldMap3D::UpdateHighlights()
{
	if (!bCitiesBuilt)
	{
		return;
	}
	ShowCityRing(SelectedRing.Get(), SelectedCity, 1.3f);
	ShowCityRing(HoverRing.Get(), HoveredCity != SelectedCity ? HoveredCity : -1, 1.18f);

	while (TargetRings.Num() < TargetCities.Num() && RingMesh != nullptr)
	{
		TargetRings.Add(CreateRing(IronWorldMap3DDetail::TargetColor()));
	}
	for (int32 RingIndex = 0; RingIndex < TargetRings.Num(); ++RingIndex)
	{
		const int32 CityIndex = TargetCities.IsValidIndex(RingIndex) ? TargetCities[RingIndex] : -1;
		ShowCityRing(TargetRings[RingIndex].Get(), CityIndex, 1.22f);
	}

	if (ArmyRing != nullptr)
	{
		const FIronArmyVisual* Visual = ArmyVisuals.Find(SelectedArmyId);
		if (Visual != nullptr && Visual->Unit != nullptr)
		{
			PlaceRing(ArmyRing.Get(), Visual->MapPoint, Visual->GroundM, 36.0f);
		}
		else
		{
			ArmyRing->SetVisibility(false);
		}
	}
}

// ---------------------------------------------------------------------------------------------------------------------
// Picking and projection
// ---------------------------------------------------------------------------------------------------------------------

bool AIronWorldMap3D::PickMapPoint(const FVector2D& ViewportPixel, FVector2D& OutMapPointM) const
{
	const APlayerController* Controller = GetLocalController();
	if (!bMapActive || Controller == nullptr)
	{
		return false;
	}
	FVector RayOrigin;
	FVector RayDirection;
	if (!Controller->DeprojectScreenPositionToWorld(static_cast<float>(ViewportPixel.X), static_cast<float>(ViewportPixel.Y), RayOrigin, RayDirection))
	{
		return false;
	}
	FVector Hit;
	if (Terrain != nullptr && Terrain->TraceSurface(RayOrigin, RayDirection, Hit))
	{
		OutMapPointM = IronWorld::WorldToMap(Hit);
		return true;
	}
	// Before the heightmap is ready: the sea-level plane.
	if (RayDirection.Z < -1.0e-4)
	{
		const double Distance = -RayOrigin.Z / RayDirection.Z;
		OutMapPointM = IronWorld::WorldToMap(RayOrigin + RayDirection * Distance);
		return true;
	}
	return false;
}

bool AIronWorldMap3D::ProjectToViewport(const FVector2D& MapPointM, float HeightM, FVector2D& OutViewportPixel) const
{
	const APlayerController* Controller = GetLocalController();
	if (Controller == nullptr)
	{
		return false;
	}
	FVector2D ScreenPosition;
	if (!Controller->ProjectWorldLocationToScreen(IronWorld::MapToWorld(MapPointM, static_cast<double>(HeightM)), ScreenPosition, false))
	{
		return false;
	}
	OutViewportPixel = ScreenPosition;
	return true;
}

int32 AIronWorldMap3D::PickCity(const FVector2D& ViewportPixel) const
{
	if (!bMapActive || CityVisuals.Num() == 0)
	{
		return -1;
	}
	// Within a footprint radius that grows with the zoom, measured on the ground under the cursor or around the
	// projected middle of the model (tall roofs seen from a steep angle cover ground behind the city).
	const double Slack = static_cast<double>(GetCameraDistanceM()) * 0.02;
	FVector2D GroundPoint = FVector2D::ZeroVector;
	const bool bHasGround = PickMapPoint(ViewportPixel, GroundPoint);
	int32 Best = -1;
	double BestScore = 1.0;
	for (int32 CityIndex = 0; CityIndex < CityVisuals.Num(); ++CityIndex)
	{
		const FIronCityVisual& Visual = CityVisuals[CityIndex];
		const double Radius = static_cast<double>(IronWorldMap3DDetail::CityRadius(Visual.CitySize)) + Slack;
		if (bHasGround)
		{
			const double GroundScore = FVector2D::Distance(GroundPoint, Visual.MapPoint) / Radius;
			if (GroundScore < BestScore)
			{
				BestScore = GroundScore;
				Best = CityIndex;
			}
		}
		const float MiddleM = Visual.GroundM + Visual.TopM * 0.5f;
		FVector2D Centre;
		FVector2D Edge;
		if (ProjectToViewport(Visual.MapPoint, MiddleM, Centre) && ProjectToViewport(Visual.MapPoint + FVector2D(Radius, 0.0), MiddleM, Edge))
		{
			const double PixelRadius = FMath::Max(12.0, FVector2D::Distance(Centre, Edge));
			const double ScreenScore = FVector2D::Distance(ViewportPixel, Centre) / PixelRadius;
			if (ScreenScore < BestScore)
			{
				BestScore = ScreenScore;
				Best = CityIndex;
			}
		}
	}
	return Best;
}

int32 AIronWorldMap3D::PickArmy(const FVector2D& ViewportPixel) const
{
	if (!bMapActive || ArmyVisuals.Num() == 0)
	{
		return -1;
	}
	const double Radius = static_cast<double>(IronWorldMap3DDetail::ArmyPickRadiusM) + static_cast<double>(GetCameraDistanceM()) * 0.015;
	FVector2D GroundPoint = FVector2D::ZeroVector;
	const bool bHasGround = PickMapPoint(ViewportPixel, GroundPoint);
	int32 Best = -1;
	double BestScore = 1.0;
	for (const TPair<int32, FIronArmyVisual>& Pair : ArmyVisuals)
	{
		const FIronArmyVisual& Visual = Pair.Value;
		if (bHasGround)
		{
			const double GroundScore = FVector2D::Distance(GroundPoint, Visual.MapPoint) / Radius;
			if (GroundScore < BestScore)
			{
				BestScore = GroundScore;
				Best = Pair.Key;
			}
		}
		const float MiddleM = Visual.GroundM + Visual.TopM * 0.5f;
		FVector2D Centre;
		FVector2D Edge;
		if (ProjectToViewport(Visual.MapPoint, MiddleM, Centre) && ProjectToViewport(Visual.MapPoint + FVector2D(Radius, 0.0), MiddleM, Edge))
		{
			const double PixelRadius = FMath::Max(10.0, FVector2D::Distance(Centre, Edge));
			const double ScreenScore = FVector2D::Distance(ViewportPixel, Centre) / PixelRadius;
			if (ScreenScore < BestScore)
			{
				BestScore = ScreenScore;
				Best = Pair.Key;
			}
		}
	}
	return Best;
}

bool AIronWorldMap3D::ProjectCityLabel(int32 CityIndex, FVector2D& OutViewportPixel) const
{
	if (!CityVisuals.IsValidIndex(CityIndex))
	{
		return false;
	}
	const FIronCityVisual& Visual = CityVisuals[CityIndex];
	return ProjectToViewport(Visual.MapPoint, Visual.GroundM + Visual.TopM + 6.0f, OutViewportPixel);
}

bool AIronWorldMap3D::ProjectArmyLabel(int32 ArmyId, FVector2D& OutViewportPixel) const
{
	const FIronArmyVisual* Visual = ArmyVisuals.Find(ArmyId);
	if (Visual == nullptr)
	{
		return false;
	}
	return ProjectToViewport(Visual->MapPoint, Visual->GroundM + Visual->TopM + 4.0f, OutViewportPixel);
}

// ---------------------------------------------------------------------------------------------------------------------
// Camera
// ---------------------------------------------------------------------------------------------------------------------

void AIronWorldMap3D::Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx)
{
	if (CameraRig != nullptr)
	{
		CameraRig->Pan(ScreenDeltaPx, ViewportSizePx);
	}
}

void AIronWorldMap3D::Zoom(float WheelDelta, const FVector2D& CursorViewportPixel)
{
	if (CameraRig == nullptr)
	{
		return;
	}
	FVector2D CursorMapPoint = FVector2D::ZeroVector;
	const bool bHasCursorPoint = PickMapPoint(CursorViewportPixel, CursorMapPoint);
	CameraRig->Zoom(WheelDelta, CursorMapPoint, bHasCursorPoint);
}

void AIronWorldMap3D::Rotate(float DeltaDegrees)
{
	if (CameraRig != nullptr)
	{
		CameraRig->Rotate(DeltaDegrees);
	}
}

void AIronWorldMap3D::FocusCity(int32 CityIndex, float DistanceM)
{
	if (CameraRig == nullptr)
	{
		return;
	}
	if (CityVisuals.IsValidIndex(CityIndex))
	{
		CameraRig->FocusOn(CityVisuals[CityIndex].MapPoint, DistanceM);
		return;
	}
	const TSharedPtr<FIronSession> Pinned = Session.Pin();
	if (Pinned.IsValid() && Pinned->HasGame() && CityIndex >= 0 && CityIndex < static_cast<int32>(Pinned->State().Cities.size()))
	{
		CameraRig->FocusOn(IronWorld::FromSim(Pinned->State().Cities[static_cast<size_t>(CityIndex)].Position), DistanceM);
	}
}

void AIronWorldMap3D::ResetCameraToPlayer()
{
	const TSharedPtr<FIronSession> Pinned = Session.Pin();
	if (Pinned.IsValid() && Pinned->HasGame())
	{
		SnapCameraToPlayer(Pinned->State());
	}
}

void AIronWorldMap3D::FocusMapPoint(const FVector2D& MapPointM, float DistanceM)
{
	if (CameraRig != nullptr)
	{
		CameraRig->FocusOn(MapPointM, DistanceM);
	}
}

float AIronWorldMap3D::GetCameraDistanceM() const
{
	return CameraRig != nullptr ? CameraRig->GetCameraDistanceCm() * static_cast<float>(IronWorld::MetresPerCm) : static_cast<float>(IronWorld::CameraMaxDistanceM);
}
