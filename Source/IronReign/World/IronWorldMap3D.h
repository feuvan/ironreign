#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"

#include <string>

#include "IronWorldMap3D.generated.h"

class AIronCameraRig;
class AIronEnvironment;
class AIronTerrain;
class APlayerController;
class FIronSession;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class USceneComponent;
class UStaticMesh;
class UStaticMeshComponent;

namespace IronSim
{
	struct FArmy;
	struct FGameState;
}

/** A city on the 3D map: model, faction pennant, placement. */
USTRUCT()
struct FIronCityVisual
{
	GENERATED_BODY()

public:
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Body = nullptr;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Flag = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> BodyTint = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> FlagTint = nullptr;

	FVector2D MapPoint = FVector2D::ZeroVector;
	float GroundM = 0.0f;
	/** Height of the model's top above the ground (metres); label anchor. */
	float TopM = 30.0f;
	int32 CitySize = 2;
	/** Owner the tint was last applied for (-2 = never). */
	int32 TintedOwner = -2;
};

/** A marching (or waiting) army on the 3D map: squad model x6 plus a faction banner. */
USTRUCT()
struct FIronArmyVisual
{
	GENERATED_BODY()

public:
	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Unit = nullptr;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Banner = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> UnitTint = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> BannerTint = nullptr;

	FVector2D MapPoint = FVector2D::ZeroVector;
	float GroundM = 0.0f;
	float TopM = 20.0f;
	/** Facing (UE yaw, degrees), smoothed. */
	float FacingYaw = 90.0f;
	int32 TintedFaction = -2;
	int32 TroopType = -1;
	bool bHasFacing = false;
	bool bSeen = false;
};

/**
 * Facade of the real-time 3D campaign map for the strategy screen (docs/DESIGN.md section 12).
 *
 * Owns the terrain (AIronTerrain), the camera rig (AIronCameraRig) and uses the world's shared AIronEnvironment.
 * Mirrors the rules engine each tick: city models with faction pennants, sect temples, armies marching along their
 * roads (SM_Unit_<type> x6 + tinted SM_Banner), selection / hover / march-target rings, and the season of the month.
 *
 * Typical use from the strategy screen:
 *   if (AIronWorldMap3D::AreAssetsAvailable()) { Map = AIronWorldMap3D::SpawnMap(World, Session); }
 *   ...when Map->IsSceneReady(): Map->SetActive(true, 0.5f) and stop drawing the 2D map; HasFailed() -> stay 2D.
 *   Per frame: SetFractionalDay(Fraction); labels via ProjectCityLabel / ProjectArmyLabel.
 *   Input: Pan / Zoom / Rotate / FocusCity; clicks via PickCity / PickArmy.
 *   After rules changes the map follows by itself each tick; RefreshFromState() forces an immediate full sync.
 *
 * Viewport pixels are those of APlayerController::DeprojectScreenPositionToWorld / ProjectWorldLocationToScreen:
 * game viewport render pixels, origin top-left (Slate local coordinates x Geometry.Scale for a full-viewport widget).
 */
UCLASS(NotBlueprintable)
class IRONREIGN_API AIronWorldMap3D : public AActor
{
	GENERATED_BODY()

public:
	AIronWorldMap3D();

	// ----- Availability and creation -----

	/**
	 * True when the 3D map can be shown: rendering is possible, the runtime terrain data exists and the key imported
	 * assets load (SM_City_1..3, SM_Unit_Infantry/Cavalry/Archer, SM_Banner, SM_Flag, M_IronTerrain, M_IronTint).
	 * Otherwise the UI keeps the 2D painted map. Cheap after the first positive answer.
	 */
	static bool AreAssetsAvailable();
	/** Finds the world's map or spawns and initializes one (transient, hidden until SetActive(true)). */
	static AIronWorldMap3D* SpawnMap(UWorld* World, TSharedPtr<FIronSession> InSession, int32 InQualityLevel = 2);
	static AIronWorldMap3D* FindMap(UWorld* World);
	/** Spawns environment, terrain (async build) and camera rig. Cities and sects appear once the heightmap is decoded. */
	void Initialize(TSharedPtr<FIronSession> InSession, int32 InQualityLevel = 2);

	// ----- Lifecycle -----

	/**
	 * Shows or hides the map (terrain, sea, trees, cities, armies, rings). Showing makes the camera rig the view target
	 * (blending over BlendSeconds; the first activation always cuts) and turns world rendering on; hiding turns world
	 * rendering off again (the 2D screens draw everything), so activate the next 3D scene after deactivating this one.
	 * The shared environment stays.
	 */
	void SetActive(bool bInActive, float BlendSeconds = 0.0f);
	bool IsMapActive() const { return bMapActive; }
	/** Terrain fully built and cities placed: safe to switch from the 2D map without pop-in. */
	bool IsSceneReady() const;
	/** The terrain could not be built (missing / corrupt data): use the 2D map. */
	bool HasFailed() const;

	// ----- Game state -----

	/** 0..1 progress of the current day during execution (0 while planning); armies interpolate along roads. */
	void SetFractionalDay(float Fraction);
	/** Immediate full sync: rebuilds cities after a new game / load, re-tints owners, syncs armies and the season. */
	void RefreshFromState();
	/** Month 1..12 (the map also follows State.Month by itself). */
	void SetSeasonFromMonth(int32 Month);
	/** 0 Low .. 3 Epic (see AIronEnvironment::SetQuality). The terrain mesh density is chosen once at Initialize. */
	void SetQuality(int32 Level);

	// ----- Highlights (indices into State.Cities / FArmy::Id; -1 = none) -----

	void SetHoveredCity(int32 CityIndex);
	void SetSelectedCity(int32 CityIndex);
	/** March targets, drawn in vermilion. */
	void SetTargetCities(const TArray<int32>& CityIndices);
	void SetSelectedArmy(int32 ArmyId);

	// ----- Picking and projection (viewport pixels) -----

	/** City under the cursor (terrain hit near the city, or the projected model), -1 if none. */
	int32 PickCity(const FVector2D& ViewportPixel) const;
	/** FArmy::Id of the army under the cursor, -1 if none. */
	int32 PickArmy(const FVector2D& ViewportPixel) const;
	/** Map point (metres) on the terrain / sea under the cursor. */
	bool PickMapPoint(const FVector2D& ViewportPixel, FVector2D& OutMapPointM) const;
	/** Viewport pixel of a map point (metres) at HeightM; false when off screen / behind the camera. */
	bool ProjectToViewport(const FVector2D& MapPointM, float HeightM, FVector2D& OutViewportPixel) const;
	/** Anchor just above a city model (for name plaques). */
	bool ProjectCityLabel(int32 CityIndex, FVector2D& OutViewportPixel) const;
	/** Anchor just above an army's banner (troop counts). */
	bool ProjectArmyLabel(int32 ArmyId, FVector2D& OutViewportPixel) const;

	// ----- Camera -----

	/** Drag: the map follows the cursor by ScreenDeltaPx (viewport pixels). */
	void Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx);
	/** Wheel notches (positive = in), zooming toward the point under the cursor. */
	void Zoom(float WheelDelta, const FVector2D& CursorViewportPixel);
	/** Yaw offset from north in degrees (clamped to +-45). */
	void Rotate(float DeltaDegrees);
	/** Flies to a city. */
	void FocusCity(int32 CityIndex, float DistanceM = 650.0f);
	/** Jumps to the player's capital (after a new game or a load). */
	void ResetCameraToPlayer();
	void FocusMapPoint(const FVector2D& MapPointM, float DistanceM);
	float GetCameraDistanceM() const;

	AIronCameraRig* GetCameraRig() const;
	AIronEnvironment* GetEnvironment() const;
	AIronTerrain* GetTerrain() const;

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void LoadAssets();
	void ApplyVisibility();
	bool NeedsCityRebuild(const IronSim::FGameState& State) const;
	void BuildCities(const IronSim::FGameState& State);
	void ClearCities();
	void PlaceSects(const IronSim::FGameState& State);
	void SyncOwners(const IronSim::FGameState& State);
	void SyncArmies(const IronSim::FGameState& State, float DeltaSeconds);
	void UpdateArmyVisual(FIronArmyVisual& Visual, const IronSim::FArmy& Army, const IronSim::FGameState& State, const FVector2D& MapPointM, const FVector2D& Heading, float DeltaSeconds);
	void DestroyArmyVisual(FIronArmyVisual& Visual);
	void SyncSeason(const IronSim::FGameState& State);
	void SnapCameraToPlayer(const IronSim::FGameState& State);
	void UpdateHighlights();
	void ShowCityRing(UStaticMeshComponent* Ring, int32 CityIndex, float DiameterScale);
	void PlaceRing(UStaticMeshComponent* Ring, const FVector2D& MapPointM, float GroundM, float DiameterM);
	UStaticMeshComponent* CreateMeshComponent(UStaticMesh* Mesh);
	UStaticMeshComponent* CreateRing(const FLinearColor& Color);
	UStaticMesh* CityMeshFor(int32 CitySize) const;
	UStaticMesh* UnitMeshFor(int32 TroopType) const;
	float SurfaceAt(const FVector2D& MapPointM) const;
	APlayerController* GetLocalController() const;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(Transient)
	TObjectPtr<AIronEnvironment> Environment;

	UPROPERTY(Transient)
	TObjectPtr<AIronTerrain> Terrain;

	UPROPERTY(Transient)
	TObjectPtr<AIronCameraRig> CameraRig;

	/** Index = city size - 1. Entries may be null. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> CityMeshes;

	/** Index = IronSim::ETroopType. Entries may be null. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> UnitMeshes;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> BannerMesh;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> FlagMesh;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> SectMesh;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> RingMesh;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> TintMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> HighlightMaterial;

	UPROPERTY(Transient)
	TArray<FIronCityVisual> CityVisuals;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> SectMarkers;

	/** Keyed by FArmy::Id. */
	UPROPERTY(Transient)
	TMap<int32, FIronArmyVisual> ArmyVisuals;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> HoverRing;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> SelectedRing;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMeshComponent> ArmyRing;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> TargetRings;

	TWeakPtr<FIronSession> Session;
	/** Scenario the city visuals were built for. */
	std::string BuiltScenarioKey;
	TArray<int32> TargetCities;
	int32 HoveredCity = -1;
	int32 SelectedCity = -1;
	int32 SelectedArmyId = -1;
	int32 LastMonth = 0;
	int32 QualityLevel = 2;
	float FractionalDay = 0.0f;
	bool bInitialized = false;
	bool bMapActive = false;
	bool bCitiesBuilt = false;
	bool bBoundsSet = false;
	bool bEverActivated = false;
};
