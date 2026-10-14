#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "World/IronViewProjection.h"

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

/** What AIronWorldMap3D::PickAt found under the cursor. */
enum class EIronMapPickKind : uint8
{
	None,
	City,
	Army
};

/** Result of AIronWorldMap3D::PickAt. */
struct FIronMapPick
{
	EIronMapPickKind Kind = EIronMapPickKind::None;
	/** Index into State.Cities for a city, FArmy::Id for an army, -1 for None. */
	int32 Id = -1;
	/**
	 * How close the cursor is to the middle of the picked model: 0 dead centre .. 1 the edge of its pick radius. The
	 * best (lowest) score of every city and army wins, so an army camped beside a town is picked where it stands.
	 */
	float Score = 1.0f;
	/** Terrain / sea point under the cursor (map metres), valid when bHasGround (also for None: open ground). */
	FVector2D GroundPointM = FVector2D::ZeroVector;
	bool bHasGround = false;

	bool IsCity() const { return Kind == EIronMapPickKind::City; }
	bool IsArmy() const { return Kind == EIronMapPickKind::Army; }
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
 * Owns the terrain (AIronTerrain), the camera rig (AIronCameraRig) and uses the world's shared AIronEnvironment
 * (lighting, season and look: painted by default, see AIronEnvironment::SetLook and docs/DESIGN.md 12.6).
 * Mirrors the rules engine each tick: city models with faction pennants, sect temples, armies marching along their
 * roads (SM_Unit_<type> x6 + tinted SM_Banner), selection / hover / march-target rings, and the season of the month.
 *
 * Typical use from the strategy screen:
 *   if (AIronWorldMap3D::AreAssetsAvailable()) { Map = AIronWorldMap3D::SpawnMap(World, Session); }
 *   ...when Map->IsSceneReady(): Map->SetActive(true, 0.5f) and stop drawing the 2D map; HasFailed() -> stay 2D.
 *   Battle: Map->SetActive(false) and Board->SetActive(true) in either order; back: Board->SetActive(false),
 *   Map->SetActive(true) (cuts, the board is far away).
 *   Per frame: SetFractionalDay(Fraction); SetFramingInsets(measured panel fractions); labels via ProjectCityLabel /
 *   ProjectArmyLabel, or GetViewProjection() for many points at once (all of them share one snapshot per frame).
 *   Input: Pan / Zoom / Rotate / ResetCameraRotation / FocusCity / FocusArmy; clicks via PickAt (or PickCity /
 *   PickArmy).
 *   After rules changes the map follows by itself each tick; RefreshFromState() forces an immediate full sync.
 *   Leaving: Destroy() (or any EndPlay) also hides the map, turns world rendering off unless the battle board shows,
 *   and gives the view target back to the player controller when it was the camera rig.
 *
 * Viewport pixels are those of APlayerController::DeprojectScreenPositionToWorld / ProjectWorldLocationToScreen:
 * game viewport render pixels, origin top-left (see FIronViewProjection; the UI maps Slate geometry onto them).
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
	 * Otherwise the UI keeps the 2D painted map. Cached: a positive answer is kept, a negative one is probed again at
	 * most every 30 seconds (an import finishing while the game runs is picked up) or after InvalidateAssetCheck().
	 * Each new missing asset is logged once. Game thread.
	 */
	static bool AreAssetsAvailable();
	/** Forgets the cached AreAssetsAvailable answer: the next call probes the assets again (after an import). */
	static void InvalidateAssetCheck();
	/** Finds the world's map or spawns and initializes one (transient, hidden until SetActive(true)). */
	static AIronWorldMap3D* SpawnMap(UWorld* World, TSharedPtr<FIronSession> InSession, int32 InQualityLevel = 2);
	static AIronWorldMap3D* FindMap(UWorld* World);
	/** Spawns environment, terrain (async build) and camera rig. Cities and sects appear once the heightmap is decoded. */
	void Initialize(TSharedPtr<FIronSession> InSession, int32 InQualityLevel = 2);

	// ----- Lifecycle -----

	/**
	 * Shows or hides the map (terrain, sea, trees, cities, armies, rings). Showing makes the camera rig the view target
	 * and turns world rendering on. It blends over BlendSeconds only from a nearby view: the first activation and a
	 * switch back from the battle board (100 km away) always cut. Hiding turns world rendering off again (the 2D
	 * screens draw everything) unless the battle board is the active scene. Deactivating is idempotent and order-safe:
	 * a redundant or late SetActive(false) never blanks the board or a re-activated map. The shared environment stays.
	 * Hiding keeps the view target (re-showing then cuts or blends correctly); EndPlay releases it (see the class doc).
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
	/**
	 * 0 Low .. 3 Epic (see AIronEnvironment::SetQuality). The only quality-dependent choice made at spawn is the
	 * density of the runtime terrain mesh (2 m grid at Epic, 4 m below); trees are the same at every level. Crossing
	 * the Epic boundary rebuilds that mesh in the background and swaps it in when complete (cities, sects and armies
	 * are re-placed on the new triangles in the same frame; the old terrain shows until then). Nothing is rebuilt when
	 * the imported SM_Terrain_* chunks draw the ground: they keep the grid they were cut with.
	 */
	void SetQuality(int32 Level);
	int32 GetQuality() const { return QualityLevel; }
	/** A finer or coarser terrain is being built for the current quality (the old one still shows). */
	bool IsTerrainRebuildPending() const { return PendingTerrain != nullptr; }

	// ----- Highlights (indices into State.Cities / FArmy::Id; -1 = none) -----

	void SetHoveredCity(int32 CityIndex);
	void SetSelectedCity(int32 CityIndex);
	/** March targets, drawn in vermilion. */
	void SetTargetCities(const TArray<int32>& CityIndices);
	void SetSelectedArmy(int32 ArmyId);

	// ----- Picking and projection (viewport pixels) -----

	/**
	 * The local player's view this frame: one snapshot shared by every projection and pick below, recaptured when the
	 * frame, the camera update or the viewport size changed (FIronViewProjection::Refresh). Project hundreds of
	 * overlay points with it; check IsValid() (false without a local player or viewport).
	 */
	const FIronViewProjection& GetViewProjection() const;

	/**
	 * City or army under the cursor, whichever model the cursor is nearest to relative to its size (terrain hit near
	 * the model, or the projected middle of the model), plus the ground point under the cursor. One terrain trace.
	 * Kind None when nothing is within reach or the map is hidden.
	 */
	FIronMapPick PickAt(const FVector2D& ViewportPixel) const;
	/** City under the cursor (terrain hit near the city, or the projected model), -1 if none. */
	int32 PickCity(const FVector2D& ViewportPixel) const;
	/** Same, with the score of PickAt (0 centre .. 1 edge; 1 when none). */
	int32 PickCity(const FVector2D& ViewportPixel, float& OutScore) const;
	/** FArmy::Id of the army under the cursor, -1 if none. */
	int32 PickArmy(const FVector2D& ViewportPixel) const;
	int32 PickArmy(const FVector2D& ViewportPixel, float& OutScore) const;
	/** Map point (metres) on the terrain / sea under the cursor. */
	bool PickMapPoint(const FVector2D& ViewportPixel, FVector2D& OutMapPointM) const;
	/**
	 * Viewport pixel of a map point (metres) at HeightM; false behind the camera or without a view (points beside the
	 * screen still project, outside 0..size). OutDepthCm: depth along the view direction, for far-to-near sorting.
	 */
	bool ProjectToViewport(const FVector2D& MapPointM, float HeightM, FVector2D& OutViewportPixel) const;
	bool ProjectToViewport(const FVector2D& MapPointM, float HeightM, FVector2D& OutViewportPixel, float& OutDepthCm) const;
	/** Anchor just above a city model (for name plaques). */
	bool ProjectCityLabel(int32 CityIndex, FVector2D& OutViewportPixel) const;
	bool ProjectCityLabel(int32 CityIndex, FVector2D& OutViewportPixel, float& OutDepthCm) const;
	/** Anchor just above an army's banner (troop counts), following the drawn model. */
	bool ProjectArmyLabel(int32 ArmyId, FVector2D& OutViewportPixel) const;
	bool ProjectArmyLabel(int32 ArmyId, FVector2D& OutViewportPixel, float& OutDepthCm) const;
	/**
	 * Map point (metres) where the army's model is drawn this frame: on its road from gate to gate (not the rules
	 * engine's city-centre to city-centre position), in its camp beside the walls, or nudged aside from another army.
	 * False when the army has no model (unknown id, no units, or the map was never shown).
	 */
	bool GetArmyMapPoint(int32 ArmyId, FVector2D& OutMapPointM) const;
	/** World location (cm) of the army label anchor (top of the model + AboveModelM), following the drawn model. */
	bool GetArmyLabelWorldLocation(int32 ArmyId, FVector& OutWorldLocationCm, float AboveModelM = 4.0f) const;
	/** World location (cm) of the city label anchor (top of the model + AboveModelM). */
	bool GetCityLabelWorldLocation(int32 CityIndex, FVector& OutWorldLocationCm, float AboveModelM = 6.0f) const;

	// ----- Camera -----

	/** Drag: the map follows the cursor by ScreenDeltaPx (viewport pixels). */
	void Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx);
	/** Wheel notches (positive = in), zooming toward the point under the cursor. */
	void Zoom(float WheelDelta, const FVector2D& CursorViewportPixel);
	/** Yaw offset from north in degrees (clamped to +-45). */
	void Rotate(float DeltaDegrees);
	/** Back to looking north (glides). */
	void ResetCameraRotation();
	/** Flies to a city (centred in the uncovered part of the viewport, see SetFramingInsets). */
	void FocusCity(int32 CityIndex, float DistanceM = 650.0f);
	/** Flies to where the army's model is drawn (GetArmyMapPoint; the rules position when it has no model yet). */
	void FocusArmy(int32 ArmyId, float DistanceM = 650.0f);
	/** Jumps to the player's capital (after a new game or a load). */
	void ResetCameraToPlayer();
	void FocusMapPoint(const FVector2D& MapPointM, float DistanceM);
	/** Depth of the camera target along the view direction (metres). */
	float GetCameraDistanceM() const;
	/**
	 * Fractions (each 0..0.45) of the viewport covered by opaque Slate panels on each side (left, top, right, bottom;
	 * e.g. 388 / 80 / 374 / 184 px of 1920 x 1080 = 0.202, 0.074, 0.195, 0.170). The camera target, and with it
	 * FocusCity, FocusArmy, FocusMapPoint, ResetCameraToPlayer and the zoom pivot, is then drawn at the centre of the
	 * uncovered rectangle; the view direction and perspective do not change. Changes glide; unchanged values are free,
	 * so pass the measured layout every frame. Kept across Initialize and terrain rebuilds.
	 */
	void SetFramingInsets(float Left, float Top, float Right, float Bottom);

	AIronCameraRig* GetCameraRig() const;
	AIronEnvironment* GetEnvironment() const;
	AIronTerrain* GetTerrain() const;

	virtual void Tick(float DeltaSeconds) override;

protected:
	/**
	 * Any reason: hides the map like SetActive(false) (world rendering stays on only for an active battle board). When
	 * the map is destroyed or removed during play it also hands the view target back to the player controller if the
	 * camera rig still holds it. Destroying the map destroys its terrain(s) and camera rig; the environment stays.
	 */
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void LoadAssets();
	/** Builds a terrain for the current quality in the background and swaps it in when complete (see SetQuality). */
	void UpdateTerrainDetail();
	void SwapInPendingTerrain();
	/** Ground (terrain / sea) under a viewport pixel, through View. */
	bool TraceMapPoint(const FIronViewProjection& View, const FVector2D& ViewportPixel, FVector2D& OutMapPointM) const;
	/** Best city / army under the cursor with a score below 1 (see FIronMapPick::Score), or -1. */
	int32 FindCityAt(const FIronViewProjection& View, const FVector2D& ViewportPixel, const FVector2D& GroundM, bool bHasGround, float& OutScore) const;
	int32 FindArmyAt(const FIronViewProjection& View, const FVector2D& ViewportPixel, const FVector2D& GroundM, bool bHasGround, float& OutScore) const;
	/** Tree-free discs (X, Y = map metres, Z = radius metres) around every city model and its army camp. */
	TArray<FVector> CollectTreeExclusions(const IronSim::FGameState& State) const;
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

	/** Terrain being built for a new quality level (hidden until it replaces Terrain). */
	UPROPERTY(Transient)
	TObjectPtr<AIronTerrain> PendingTerrain;

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
	/** Runtime mesh stride Terrain / PendingTerrain were built with; a stride whose build failed is not retried. */
	int32 TerrainStride = 2;
	int32 PendingTerrainStride = 0;
	int32 FailedTerrainStride = 0;
	/** Framing insets (viewport fractions: left, top, right, bottom), forwarded to the camera rig. */
	float FramingLeft = 0.0f;
	float FramingTop = 0.0f;
	float FramingRight = 0.0f;
	float FramingBottom = 0.0f;
	float FractionalDay = 0.0f;
	bool bInitialized = false;
	bool bMapActive = false;
	bool bCitiesBuilt = false;
	bool bBoundsSet = false;
	bool bEverActivated = false;

	/** Per-frame view snapshot behind GetViewProjection (a cache, hence mutable). */
	mutable FIronViewProjection FrameView;
};
