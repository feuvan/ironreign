#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Sim/IronBattle.h"
#include "World/IronViewProjection.h"

#include <vector>

#include "IronBattleBoard3D.generated.h"

class ACameraActor;
class AIronEnvironment;
class APlayerController;
class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class UProceduralMeshComponent;
class USceneComponent;
class UStaticMesh;
class UStaticMeshComponent;

/** What the battle screen wants highlighted on the 3D board (the 3D twin of the 2D view's FIronHexHighlights). */
struct FIronBoardHighlights
{
	/** Blue: hexes the selected unit can move to. */
	TArray<IronSim::FHex> Reachable;
	/** Red: enemies (or gates) the selected unit can attack. */
	TArray<IronSim::FHex> AttackTargets;
	/** Purple: targets of the chosen tactic. */
	TArray<IronSim::FHex> TacticTargets;
	/** Orange: officers that can be challenged to a duel. */
	TArray<IronSim::FHex> DuelTargets;
	/** Gold ring that follows this unit, also while it moves (-1 = none). */
	int32 SelectedUnit = -1;
	/** Cream ring under the cursor (Col -1 = none). */
	IronSim::FHex HoveredHex = {-1, -1};
};

/**
 * Where one rules event landed on the board's animation timeline (AIronBattleBoard3D::PlayEvent). Seconds from the
 * moment of the call, on the board clock (AIronBattleBoard3D::GetAnimationClock): it advances with the world's frame
 * time, each frame clamped to 0.1 s, so at normal frame rates it runs with the wall clock. Exact under hitches: due at
 * GetAnimationClock() (taken at the call) + ImpactSeconds, compared against GetAnimationClock(). Simpler, and exact
 * above 10 fps: FPlatformTime::Seconds() at the call + ImpactSeconds.
 */
struct FIronBoardEventTiming
{
	/** The event's animation starts (0 = now; later while earlier animations are still playing). */
	float StartSeconds = 0.0f;
	/**
	 * The moment the result shows, for floating numbers, flashes and sounds: the blow lands (melee 0.15 s after the
	 * start, volley 0.42 s, gate hit 0.15 s), the gate collapses (0.3 s), a fire tactic strikes (0.45 s), the confuse /
	 * rally / failed-tactic effect appears on the target (0.15 s), a move arrives. StartSeconds for events whose result
	 * is immediate (burn, duel result, falls) and for events the board does not animate.
	 */
	float ImpactSeconds = 0.0f;
	/** The event's blocking animations are over (hit reactions included). StartSeconds when nothing was queued. */
	float EndSeconds = 0.0f;
	/** The board queued animations for the event. False when it ignored it (inactive or unbuilt board, DayStart, narration). */
	bool bAnimated = false;
};

/** Plain (non-reflected) animation state of AIronBattleBoard3D. */
namespace IronBoard3D
{
	enum class ETrack : uint8
	{
		Move,       // Unit walks (hops) along Path; Variant 1 = direct glide (undo, resync).
		Lunge,      // Unit lunges toward Other / To and back (melee attack, counter, gate assault).
		Volley,     // Unit shoots a volley of arrows at Other / To (ranged attack).
		Hit,        // Unit (or gate Gate, or hex To) is struck: shake, red emissive flash, light, ground flash.
		GateShake,  // Gate tile Gate shakes; Variant 1 = it breaks (the tile becomes rubble mid-way).
		Cast,       // Unit performs a tactic (small hop).
		FireBurst,  // Fire tactic on hex To: flaring light, rising embers, shock ring; the hex starts burning.
		Swirl,      // Confuse on Other at To: purple rings spiralling up.
		Pulse,      // Rally on Other at To: golden rings expanding.
		Fizzle,     // A failed tactic on To: a grey ring collapsing.
		Sink        // Unit leaves the field: Variant = IronSim::EUnitStatus (routed units flee, others sink).
	};

	struct FTrack
	{
		ETrack Kind = ETrack::Hit;
		int32 Unit = -1;
		int32 Other = -1;
		int32 Gate = -1;
		int32 Variant = 0;
		IronSim::FHex From = {-1, -1};
		IronSim::FHex To = {-1, -1};
		/** Hexes walked by a Move, From first. */
		TArray<IronSim::FHex> Path;
		/** Board-local points (cm) resolved when the track starts. */
		TArray<FVector> Points;
		/** Board clock seconds. */
		double Start = 0.0;
		double Duration = 0.5;
		float Strength = 1.0f;
		FLinearColor Color = FLinearColor::White;
		bool bBlocking = true;
		bool bStarted = false;
		bool bFlag = false;
		/** Pooled effect quads and light owned while the track runs. */
		TArray<int32> Quads;
		int32 Light = -1;
	};

	/** A burning hex: flickering light and looping embers. */
	struct FBurn
	{
		IronSim::FHex Hex = {-1, -1};
		int32 Light = -1;
		TArray<int32> Quads;
		float Phase = 0.0f;
	};

	/** Board-wide highlight layers (one batched mesh and material each), drawn bottom to top. */
	enum class ELayer : uint8
	{
		Grid,
		Burning,
		Reachable,
		Duel,
		Tactic,
		Attack,
		Count
	};
}

/** One battle unit on the board: squad model + tinted plinth (+ commander pennant) under a root that animates. */
USTRUCT()
struct FIronBoardUnitVisual
{
	GENERATED_BODY()

	UPROPERTY()
	TObjectPtr<USceneComponent> Root = nullptr;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Figure = nullptr;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Base = nullptr;

	UPROPERTY()
	TObjectPtr<UStaticMeshComponent> Flag = nullptr;

	/** Every dynamic material on the figure and plinth (side tint + "EmissiveFactor" for the hit flash). */
	UPROPERTY()
	TArray<TObjectPtr<UMaterialInstanceDynamic>> Materials;

	/** The side-colour instance of each part (IronWorld::ApplyTint), recoloured for the "acted" look. */
	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> FigureTint = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> BaseTint = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> FlagTint = nullptr;

	FLinearColor SideColor = FLinearColor::White;
	int32 Side = 0;
	int32 TroopType = 0;
	bool bCommander = false;

	/** Hex the unit stands on when no animation moves it. */
	IronSim::FHex RestHex = {-1, -1};
	/** Last state reported by SyncFromBattle. */
	IronSim::FHex TargetHex = {-1, -1};
	bool bTargetOnField = true;
	bool bTargetConfused = false;
	/** Acted this turn on the side whose turn it is (dimmed once its animations finished). */
	bool bTargetActed = false;
	/** 0..1 blend toward the dimmed side colour, and the value last applied to the tint materials. */
	float Acted = 0.0f;
	float AppliedActed = 0.0f;

	/** Currently drawn (false once it left the field). */
	bool bShown = true;
	bool bAppliedShown = true;

	/** Per-frame animation state (board-local cm). */
	FVector Location = FVector::ZeroVector;
	FVector Offset = FVector::ZeroVector;
	float Shrink = 1.0f;
	float Flash = 0.0f;
	float AppliedFlash = 0.0f;
	FLinearColor FlashColor = FLinearColor::Red;
	/** Facing (UE yaw, degrees; 0 = +X toward the defender's side). */
	float Yaw = 0.0f;
	float DrivenYaw = 0.0f;
	bool bYawDriven = false;
	/** Height of the model top above the ground (m), for label anchors. */
	float TopM = 3.0f;
	/** Pooled quad of the "confused" halo, -1 when none. */
	int32 HaloQuad = -1;
};

/** A pooled effect quad (M_IronHighlight circle shape, own dynamic material). */
USTRUCT()
struct FIronBoardFxQuad
{
	GENERATED_BODY()

	UPROPERTY()
	TObjectPtr<UProceduralMeshComponent> Mesh = nullptr;

	UPROPERTY()
	TObjectPtr<UMaterialInstanceDynamic> Material = nullptr;

	bool bInUse = false;
};

/** A pooled point light (hit flashes, fire, tactics). */
USTRUCT()
struct FIronBoardLight
{
	GENERATED_BODY()

	UPROPERTY()
	TObjectPtr<UPointLightComponent> Light = nullptr;

	bool bInUse = false;
};

/**
 * Facade of the real-time 3D tactical battle for the battle screen (docs/DESIGN.md sections 4, 9 and 12.4).
 *
 * Scene: the hex board at the fixed board origin (IronWorld::BoardOrigin(), X 0 m / Y -100000 m), one instanced mesh
 * component per hex model SM_Hex_<IronSim::AssetName(terrain)> (natural terrains get a random yaw in 60 degree steps),
 * gate hexes as separate tiles that shake and turn into SM_Hex_Rubble, a ring of decorative hexes around the board that
 * continues its rivers, roads, sea, city wall and town, and a large season-tinted ground of slabs below. Lighting is the
 * world's shared AIronEnvironment (sun, sky atmosphere, sky light, clouds, height + volumetric fog, post-process); the
 * board only turns its sun from dawn (day 1) to dusk (the last day; in the painted look a gentle swing around the
 * top-left) and restores it when deactivated, and tints the ground with the season and look (silk-toned plains when
 * painted). The battle camera is an ACameraActor framing the whole board at about 50 degrees pitch, with its own
 * tilt-shift depth of field.
 *
 * Units: per IronSim::FBattleUnit a SM_Unit_<Type> squad on a SM_Unit_Base plinth (both tinted with the side colour
 * through M_IronTint's "Tint"), commanders carry a small SM_Flag. Highlights are batched M_IronHighlight hex rings.
 *
 * Typical use from the battle screen:
 *   if (AIronBattleBoard3D::AreAssetsAvailable())          // otherwise stay on the 2D SIronHexView
 *   {
 *       Board = AIronBattleBoard3D::SpawnBoard(World);
 *       Board->Build(*Battle); Board->SetSeason(Month); Board->SetFramingInsets(...);
 *       StrategyMap3D->SetActive(false); Board->SetActive(true);   // either order works
 *   }
 *   ConsumeEvents:  per event T = Board->PlayEvent(Event) (texts / sounds when GetAnimationClock() reaches its value
 *                   at the call + T.ImpactSeconds); Board->SyncFromBattle(*Battle); Battle->ClearEvents();
 *   Driver tick:    bAnimating = Board->IsAnimating();  (instead of SIronHexView::GetBusyUntil)
 *   Fast-forward:   Board->FinishAnimations(); Board->SyncFromBattle(*Battle);
 *   Selection:      Board->SetHighlights(...) whenever the highlights change; SetHoveredHex on mouse move.
 *   Input:          PickHex (click / hover), Pan (drag), Zoom (wheel), ResetView (key), FocusHex (AI acting off screen).
 *   Overlay:        GetViewProjection() once per paint, then ProjectUnitToViewport (troop bars, names follow the
 *                   animation), ProjectGateToViewport (gate HP bars), ProjectToViewport (hex numbers) - all share it.
 *   Graphics:       SetQuality; the tilt-shift follows AIronEnvironment::SetTiltShiftStrength by itself, the look
 *                   (AIronEnvironment::SetLook: painted by default) follows the shared environment.
 *   Leaving:        Board->SetActive(false); StrategyMap3D->SetActive(true) (either order; the map cuts back).
 *                   Destroy() (or any EndPlay) also deactivates and hands a held view target back to the controller.
 *
 * Viewport pixels are those of APlayerController::DeprojectScreenPositionToWorld / ProjectWorldLocationToScreen: game
 * viewport render pixels, origin top-left (see FIronViewProjection; the UI maps Slate geometry onto them).
 * Every asset is optional at runtime except those checked by AreAssetsAvailable(); nothing here touches the rules.
 */
UCLASS(NotBlueprintable)
class IRONREIGN_API AIronBattleBoard3D : public AActor
{
	GENERATED_BODY()

public:
	AIronBattleBoard3D();

	// ----- Availability and creation -----

	/**
	 * True when the 3D board can be shown: rendering is possible, the asset import completed
	 * (/Game/IronReign/IronReignAssetVersion) and SM_Hex_<all 13 terrains>, SM_Unit_Infantry/Cavalry/Archer,
	 * SM_Unit_Base, M_IronTint and M_IronHighlight (or MI_IronHighlightHex) load. Otherwise keep the 2D hex view.
	 * Cached like AIronWorldMap3D::AreAssetsAvailable: a positive answer is kept, a negative one is probed again at
	 * most every 30 seconds or after InvalidateAssetCheck(); each new missing asset is logged once. Game thread.
	 */
	static bool AreAssetsAvailable();
	/** Forgets the cached AreAssetsAvailable answer: the next call probes the assets again (after an import). */
	static void InvalidateAssetCheck();
	static AIronBattleBoard3D* FindBoard(UWorld* World);
	/** Finds the world's board or spawns one (transient, hidden until SetActive(true)). */
	static AIronBattleBoard3D* SpawnBoard(UWorld* World);

	// ----- Board -----

	/** (Re)builds terrain, surroundings, gates and units for Battle and frames the camera on it. Synchronous. */
	void Build(const IronSim::FBattle& Battle);
	bool IsBuilt() const { return bBuilt; }
	/** Removes every hex, unit and effect (the camera and pools stay for the next battle). */
	void ClearBoard();

	/**
	 * Shows or hides the board. Showing turns world rendering on and makes the battle camera the view target (blending
	 * over BlendSeconds; coming from the strategy map, 100 km away, it always cuts). Hiding finishes running
	 * animations, restores the shared sun and turns world rendering off again (the 2D screens draw everything) unless
	 * the strategy map is the active scene. Deactivating is idempotent and order-safe: a redundant or late
	 * SetActive(false) never blanks the map or a re-activated board.
	 */
	void SetActive(bool bInActive, float BlendSeconds = 0.0f);
	bool IsBoardActive() const { return bBoardActive; }

	/** Month 1..12 of the battle: environment season (instant) and the ground colour around the board. */
	void SetSeason(int32 Month);
	/**
	 * 0 Low .. 3 Epic (forwards to AIronEnvironment::SetQuality; Low drops the depth of field and most embers, Epic
	 * gives effect lights shadows). Takes effect at once: nothing on the board depends on the quality at build time.
	 */
	void SetQuality(int32 Level);
	/** Faint hex grid over the playable board (default on). */
	void SetGridVisible(bool bVisible);
	/** Dims the side colour of units that already acted this turn (default on; see SyncFromBattle). */
	void SetDimActedUnits(bool bDim);

	// ----- Battle state and animation -----

	/**
	 * Remembers the rules state (unit hexes and status, confusion, acted flags, burning hexes, gate HP, day). Units and
	 * gates with queued animations keep their animated state until those animations finish, the rest follows at once
	 * (a unit whose hex changed without a Move event glides there). Units of the side whose turn it is that already
	 * acted (FBattleUnit::bActed, battle not over) fade to a dimmed, desaturated side colour once their own animations
	 * finished; the next turn restores them. Cheap: may be called every frame. Rebuilds the board when Battle is a
	 * different battle (other size or unit count).
	 */
	void SyncFromBattle(const IronSim::FBattle& Battle);
	/**
	 * Queues the animations of rules events in order (moves hop along their path at 0.25 s per hex; attacks lunge,
	 * counters follow; tactics, gate hits, falls...). Call before ClearEvents(). Ignored while the board is inactive.
	 * Returns each event's timing, in order (see PlayEvent).
	 */
	TArray<FIronBoardEventTiming> PlayEvents(const TArray<IronSim::FBattleEvent>& Events);
	/** Same for IronSim::FBattle::Events(). */
	TArray<FIronBoardEventTiming> PlayEvents(const std::vector<IronSim::FBattleEvent>& Events);
	/**
	 * Queues one event and tells where it sits on the animation timeline: schedule its floating numbers and sounds at
	 * ImpactSeconds instead of mirroring the board's private durations. Every event gets a slot (StartSeconds) after
	 * the animations already queued, also those the board does not animate (bAnimated false).
	 */
	FIronBoardEventTiming PlayEvent(const IronSim::FBattleEvent& Event);
	/** True while queued or running animations should hold back the next AI step / the result dialog. */
	bool IsAnimating() const;
	float GetRemainingAnimationSeconds() const;
	/**
	 * The board's animation clock in seconds: it advances only while the board is active, by the frame time clamped
	 * to 0.1 s, and FinishAnimations does not move it. The base of FIronBoardEventTiming's offsets.
	 */
	double GetAnimationClock() const { return Clock; }
	/** Completes every queued animation at once (fast-forward, delegate, leaving the screen). */
	void FinishAnimations();

	// ----- Highlights -----

	void SetHighlights(const FIronBoardHighlights& InHighlights);
	void SetHighlights(const TArray<IronSim::FHex>& Reachable, const TArray<IronSim::FHex>& AttackTargets, const TArray<IronSim::FHex>& TacticTargets, int32 SelectedUnit, const IronSim::FHex& HoveredHex);
	/** Only the hover ring (Col -1 hides it). */
	void SetHoveredHex(const IronSim::FHex& Hex);

	// ----- Picking and projection (viewport pixels) -----

	/**
	 * The local player's view this frame: one snapshot shared by every projection and pick below, recaptured when the
	 * frame, the camera update or the viewport size changed (FIronViewProjection::Refresh). Check IsValid().
	 */
	const FIronViewProjection& GetViewProjection() const;
	/**
	 * Hex under the cursor: a unit model under the cursor wins (its figure stands in front of the hexes behind it),
	 * else the board plane Z = 0 is hit and converted with IronSim::HexMath::FromPixel (metres). False off the board.
	 */
	bool PickHex(const FVector2D& ViewportPixel, IronSim::FHex& OutHex) const;
	/**
	 * Viewport pixel of a hex centre HeightM above the board; false while the board is inactive or the point is behind
	 * the camera (points beside the screen still project, outside 0..size).
	 */
	bool ProjectToViewport(const IronSim::FHex& Hex, float HeightM, FVector2D& OutViewportPixel) const;
	/** Viewport pixel of a world location (cm); OutDepthCm is its depth along the view direction. */
	bool ProjectToViewport(const FVector& WorldLocationCm, FVector2D& OutViewportPixel) const;
	bool ProjectToViewport(const FVector& WorldLocationCm, FVector2D& OutViewportPixel, float& OutDepthCm) const;
	/** Anchor AboveModelM above the unit's model top at its animated position (troop bars, names). */
	bool ProjectUnitToViewport(int32 UnitId, FVector2D& OutViewportPixel, float AboveModelM = 0.6f) const;
	/**
	 * World location (cm) of the top of the gate tile on Hex as drawn now: above the gatehouse while it stands, above
	 * the rubble once it fell (mid-way through the GateBroken animation), shaking with the blows. False when Hex holds
	 * no gate of this board.
	 */
	bool GetGateTopWorldLocation(const IronSim::FHex& Hex, FVector& OutWorldLocationCm) const;
	/** Height (m) of that gate top above the board plane; 0 when Hex holds no gate. */
	float GetGateTopHeightM(const IronSim::FHex& Hex) const;
	/** Viewport pixel AboveTopM above the gate top (gate HP bars); false when no gate, inactive or behind the camera. */
	bool ProjectGateToViewport(const IronSim::FHex& Hex, FVector2D& OutViewportPixel, float AboveTopM = 0.5f) const;
	/** The unit is drawn (on the field and not finished sinking). */
	bool IsUnitShown(int32 UnitId) const;
	/** Animated world location (cm) of the unit's feet. */
	bool GetUnitWorldLocation(int32 UnitId, FVector& OutWorldLocationCm) const;
	/** World location (cm) of a hex centre HeightM above the board. */
	FVector HexToWorldLocation(const IronSim::FHex& Hex, float HeightM = 0.0f) const;
	/** On-screen corner-to-corner width (pixels) of a hex at the camera target: scale overlays with it. */
	float GetHexPixelSize() const;

	// ----- Camera -----

	/** Drag: the board follows the cursor by ScreenDeltaPx (viewport pixels). */
	void Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx);
	/** Wheel notches (positive = in), zooming toward the point under the cursor. */
	void Zoom(float WheelDelta, const FVector2D& CursorViewportPixel);
	/** Back to the whole-board framing. */
	void ResetView(bool bInstant = false);
	/** Glides the camera to a hex (only when it is near or past the screen edge if bOnlyIfOffscreen). */
	void FocusHex(const IronSim::FHex& Hex, bool bOnlyIfOffscreen = true);
	/**
	 * Fractions (0..0.45) of the viewport covered by Slate panels (top bar, unit panel, log): the framing fits the
	 * board into the rest and centres it there.
	 */
	void SetFramingInsets(float Left, float Top, float Right, float Bottom);
	ACameraActor* GetCamera() const;
	AIronEnvironment* GetEnvironment() const;

	// ----- Board math (board-local metres: hex (0,0) centre at the origin, +X = columns, +Y = rows) -----

	static FVector2D HexToLocalM(const IronSim::FHex& Hex);
	/** IronSim::HexMath::FromPixel in metres; true when the hex lies on a Cols x Rows board. */
	static bool LocalMToHex(const FVector2D& LocalM, int32 Cols, int32 Rows, IronSim::FHex& OutHex);

	virtual void Tick(float DeltaSeconds) override;

protected:
	/**
	 * Any reason: deactivates like SetActive(false) (animations finish, the shared sun is restored, world rendering
	 * stays on only for an active strategy map). When the board is destroyed or removed during play it also hands the
	 * view target back to the player controller if the battle camera still holds it, and destroys that camera.
	 */
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	// Setup.
	void EnsureInitialized();
	void LoadAssets();
	UStaticMeshComponent* CreateMeshComponent(UStaticMesh* Mesh, USceneComponent* Parent);
	UProceduralMeshComponent* CreateQuadComponent(USceneComponent* Parent);
	UMaterialInstanceDynamic* CreateHighlightMaterial(bool bHexShape, const FLinearColor& Color, float RingRadius, float RingWidth, float FillOpacity, float PulseMin, float PulseSpeed, float Intensity);
	UInstancedStaticMeshComponent* GetTerrainLayer(int32 TerrainIndex);

	// Build.
	void BuildTerrain();
	void AddHexInstance(int32 TerrainIndex, const IronSim::FHex& Hex, double HeightM, bool bDecorative);
	IronSim::EHexTerrain SurroundingTerrainAt(const IronSim::FHex& Hex) const;
	void BuildGround();
	void BuildUnits(const IronSim::FBattle& Battle);
	void DestroyUnits();
	void FillHexLayer(IronBoard3D::ELayer Layer, const TArray<IronSim::FHex>& Hexes);
	void RefreshHighlightLayers();

	// Grid queries.
	bool InBoard(const IronSim::FHex& Hex) const;
	IronSim::EHexTerrain StoredTerrain(const IronSim::FHex& Hex) const;
	FVector HexLocalCm(const IronSim::FHex& Hex, double HeightM = 0.0) const;
	int32 GateIndexAt(const IronSim::FHex& Hex) const;
	bool IsValidUnit(int32 UnitId) const;
	TArray<IronSim::FHex> FindPath(const IronSim::FHex& From, const IronSim::FHex& To, int32 UnitId) const;

	// Animation.
	void AddTrack(IronBoard3D::FTrack&& Track);
	void QueueHit(int32 UnitId, const IronSim::FHex& Hex, double Start, float Strength, const FLinearColor& Color);
	bool HasUnitTrack(int32 UnitId, bool bMovesOnly) const;
	void ReconcileUnits();
	void UpdateTracks();
	void StartTrack(IronBoard3D::FTrack& Track);
	void UpdateTrack(IronBoard3D::FTrack& Track, double Elapsed);
	void EndTrack(IronBoard3D::FTrack& Track);
	void ApplyUnitTransforms(float DeltaSeconds);
	void ApplyUnitVisibility(FIronBoardUnitVisual& Visual);
	/** Fades the unit's side colour toward the dimmed "acted" look (DeltaSeconds >= the fade time snaps). */
	void ApplyActedLook(int32 UnitId, FIronBoardUnitVisual& Visual, float DeltaSeconds);
	void UpdateGates();
	void UpdateBurning();
	void UpdateHalos();
	void UpdateRings();
	void SnapToSnapshot();
	FVector UnitLocalNow(int32 UnitId) const;
	float IdleYawFor(int32 UnitId) const;

	// Pools.
	int32 AcquireQuad(float RingRadius, float RingWidth, float FillOpacity, float Intensity);
	void ReleaseQuad(int32 QuadIndex);
	void ReleaseQuads(TArray<int32>& QuadIndices);
	/** Places a pooled quad (board-local cm); SizeM is its diameter. Billboards face the camera, else it lies flat. */
	void PlaceQuad(int32 QuadIndex, const FVector& LocalCm, float SizeM, const FLinearColor& Color, bool bBillboard);
	int32 AcquireLight(const FLinearColor& Color, float RadiusCm);
	void ReleaseLight(int32& LightIndex);
	void PlaceLight(int32 LightIndex, const FVector& LocalCm, float IntensityCandela);
	void ReleaseAllEffects();

	// Camera and sun.
	FVector2D GetViewportSizePx() const;
	void RecomputeFraming();
	double PitchForDistance(double DistanceM) const;
	FVector ComputeCameraLocation(const FVector2D& TargetM, double DistanceM, double PitchDegrees) const;
	FVector2D ClampTarget(const FVector2D& TargetM) const;
	bool DeprojectToBoard(const FVector2D& ViewportPixel, FVector2D& OutLocalM) const;
	void UpdateCamera(float DeltaSeconds);
	void UpdateSun(float DeltaSeconds);
	void RestoreSun();
	double DayAlphaFor(int32 Day) const;
	/** Season and look colour of the ground around the board (blends with the environment). */
	FLinearColor GroundColorForSeason() const;
	/** Applies GroundColorForSeason when it changed. */
	void UpdateGroundColor();
	APlayerController* GetLocalController() const;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(Transient)
	TObjectPtr<AIronEnvironment> Environment;

	UPROPERTY(Transient)
	TObjectPtr<ACameraActor> BoardCamera;

	/** Index = IronSim::EHexTerrain. Entries may be null (SM_Hex_Plain stands in). */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> HexMeshes;

	/** Index = IronSim::ETroopType. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> UnitMeshes;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> UnitBaseMesh;

	UPROPERTY(Transient)
	TObjectPtr<UStaticMesh> FlagMesh;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> TintMaterial;

	/** MI_IronHighlightHex (HexShape 1), else M_IronHighlight. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> HexHighlightMaterial;

	/** M_IronHighlight (circle shape) for effects, else the hex instance. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> CircleHighlightMaterial;

	/** One instanced component per hex mesh (index = IronSim::EHexTerrain), board and surroundings together. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UInstancedStaticMeshComponent>> TerrainLayers;

	/** Gate hexes (index = gate index of the battle): separate so they can shake and become rubble. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> GateTiles;

	/**
	 * The ground around the board: a grid of thick slabs (SM_IronCube instances). A static mesh with a distance field
	 * and Lumen cards, so the 4 km surface is part of the Lumen scene (a procedural quad would only be screen traced).
	 */
	UPROPERTY(Transient)
	TObjectPtr<UInstancedStaticMeshComponent> Ground;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> GroundMaterial;

	/** Index = IronBoard3D::ELayer. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UProceduralMeshComponent>> HighlightMeshes;

	UPROPERTY(Transient)
	TObjectPtr<UProceduralMeshComponent> HoverRing;

	UPROPERTY(Transient)
	TObjectPtr<UProceduralMeshComponent> SelectRing;

	/** Index = unit id. */
	UPROPERTY(Transient)
	TArray<FIronBoardUnitVisual> UnitVisuals;

	UPROPERTY(Transient)
	TArray<FIronBoardFxQuad> FxQuads;

	UPROPERTY(Transient)
	TArray<FIronBoardLight> LightPool;

	// ----- Board data (copied from the battle) -----
	int32 BoardCols = 0;
	int32 BoardRows = 0;
	int32 MaxDays = 30;
	uint64 BattleSeed = 1;
	IronSim::ETerrain BattleTerrain = IronSim::ETerrain::Plains;
	/** Side of a coast battle's sea: -1 top (far) rows, 1 bottom rows, 0 none. */
	int32 CoastSide = 0;
	/** IronSim::EHexTerrain per hex, Row * BoardCols + Col (gates as built; their state lives in the gate arrays). */
	TArray<uint8> TerrainGrid;
	TArray<IronSim::FHex> GateHexes;
	TArray<bool> GateTargetBroken;
	TArray<bool> GateShownBroken;
	TArray<bool> GateAppliedBroken;
	TArray<FVector> GateOffsets;

	// ----- Snapshot and animation -----
	TArray<IronSim::FHex> TargetBurning;
	TArray<IronBoard3D::FBurn> Burns;
	TArray<IronBoard3D::FTrack> AnimTracks;
	FIronBoardHighlights Highlights;
	FIronBoardHighlights BuiltHighlights;
	/** Board clock (seconds while active). */
	double Clock = 0.0;
	/** Where the next event's animation starts. */
	double AnimCursor = 0.0;
	/** End of the last blocking animation. */
	double BusyUntil = 0.0;
	int32 TargetDay = 1;

	// ----- Camera -----
	FVector2D GoalTargetM = FVector2D::ZeroVector;
	FVector2D CurrentTargetM = FVector2D::ZeroVector;
	FVector2D TargetVelocity = FVector2D::ZeroVector;
	FVector2D FitTargetM = FVector2D::ZeroVector;
	FVector2D BoardMinM = FVector2D::ZeroVector;
	FVector2D BoardMaxM = FVector2D::ZeroVector;
	FVector2D FramedViewportSize = FVector2D::ZeroVector;
	double GoalDistanceM = 120.0;
	double CurrentDistanceM = 120.0;
	double DistanceVelocity = 0.0;
	double FitDistanceM = 120.0;
	float InsetLeft = 0.0f;
	float InsetTop = 0.0f;
	float InsetRight = 0.0f;
	float InsetBottom = 0.0f;
	bool bUserMovedCamera = false;

	/** Ground colour last applied (A = -1: never). */
	FLinearColor AppliedGroundColor = FLinearColor(0.0f, 0.0f, 0.0f, -1.0f);

	// ----- Sun -----
	double DayAlpha = 0.0;
	double GoalDayAlpha = 0.0;
	double DayAlphaVelocity = 0.0;
	bool bSunOverridden = false;

	int32 SeasonMonth = 4;
	int32 QualityLevel = 2;
	bool bInitialized = false;
	bool bBuilt = false;
	bool bBoardActive = false;
	bool bGridVisible = true;
	bool bHighlightsDirty = true;
	bool bDimActedUnits = true;

	/** Per-frame view snapshot behind GetViewProjection (a cache, hence mutable). */
	mutable FIronViewProjection FrameView;
};
