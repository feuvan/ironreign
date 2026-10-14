#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "IronCameraRig.generated.h"

class AIronTerrain;
class UCameraComponent;
class USceneComponent;

/**
 * RTS camera over the strategy map. State is a target point on the map (metres), a distance (250..2600 m), a pitch
 * derived from the distance (45 deg close up, 70 deg zoomed out) and a yaw offset from "looking north" (+-45 deg).
 * Every value follows its goal through a critically damped spring; FocusOn flies along an arc. The actor itself is the
 * camera (view target for APlayerController::SetViewTargetWithBlend).
 *
 * Framing insets (SetFramingInsets) shift the camera sideways, keeping its direction and perspective, so the target
 * point is drawn in the middle of the part of the viewport the Slate panels leave uncovered instead of the viewport
 * centre: FocusOn, SnapTo and the zoom pivot all centre there.
 *
 * Input comes from Slate through AIronWorldMap3D (Pan / Zoom / Rotate); there is no Unreal input binding.
 */
UCLASS(NotBlueprintable)
class IRONREIGN_API AIronCameraRig : public AActor
{
	GENERATED_BODY()

public:
	AIronCameraRig();

	virtual void Tick(float DeltaSeconds) override;

	/** Ground heights for the focus point and terrain clearance (weakly held). */
	void SetTerrain(AIronTerrain* InTerrain);
	/** Map rectangle (metres) the target point is clamped to. */
	void SetMapBounds(const FVector2D& MapSizeM);

	/** Drag: the map follows the cursor. ScreenDeltaPx in viewport pixels, ViewportSizePx the viewport size. */
	void Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx);
	/** Wheel: positive = zoom in, one notch = 1. Zooms toward CursorMapPointM when bHasCursorPoint. */
	void Zoom(float WheelDelta, const FVector2D& CursorMapPointM, bool bHasCursorPoint = true);
	/** Adds to the yaw offset (degrees, clamped to +-45). */
	void Rotate(float DeltaDegrees);
	/** Back to looking north. */
	void ResetRotation();
	/**
	 * Fractions (each clamped to 0..0.45) of the viewport covered by opaque panels on each side. The target point is
	 * then drawn at the centre of the uncovered rectangle. Changes glide (~0.25 s) unless bInstant or while the rig does
	 * not tick (hidden map); unchanged values cost nothing, so the UI may pass its measured layout every frame.
	 */
	void SetFramingInsets(float Left, float Top, float Right, float Bottom, bool bInstant = false);
	/** Where the target point is drawn, as a fraction of the viewport (0.5, 0.5 without insets). */
	FVector2D GetFramingCentre() const;
	/** Flies to a map point along an arc (the camera rises mid-flight on long trips). */
	void FocusOn(const FVector2D& MapPointM, float DistanceM, float DurationSeconds = 1.2f);
	/** Jumps without animation. */
	void SnapTo(const FVector2D& MapPointM, float DistanceM);
	/**
	 * Re-reads the ground under the current target at once (no spring) and re-poses the camera. Call when the terrain
	 * heights arrive after a SnapTo that could only see sea level. Works while the rig's tick is disabled.
	 */
	void ResnapGround();

	/**
	 * Depth of the target point along the view direction in cm, after terrain clearance: the focal distance of the
	 * tilt-shift (depth of field measures scene depth, not the slant distance of an off-centre target).
	 */
	float GetCameraDistanceCm() const;
	float GetCameraDistanceM() const { return GetCameraDistanceCm() * 0.01f; }
	float GetFieldOfView() const;
	/** Current (smoothed) target point in map metres. */
	FVector2D GetTargetMapPoint() const { return CurrentTarget; }
	/** World location (cm) the camera looks at (target point on the ground). */
	FVector GetFocusWorldLocation() const;
	float GetPitchDegrees() const { return static_cast<float>(CurrentPitchDegrees); }
	float GetYawOffsetDegrees() const { return static_cast<float>(CurrentYawOffset); }
	bool IsFlying() const { return bFlying; }
	UCameraComponent* GetCamera() const;

private:
	void CancelFlight();
	FVector2D ClampToMap(const FVector2D& MapPointM) const;
	double GroundUnderTarget(const FVector2D& MapPointM) const;
	double SurfaceAt(const FVector2D& MapPointM) const;
	static double PitchForDistance(double DistanceM);
	FVector2D GetViewportSizePx() const;
	void UpdatePose();

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<UCameraComponent> Camera;

	TWeakObjectPtr<AIronTerrain> Terrain;
	FVector2D MapSize = FVector2D(2400.0, 1500.0);

	FVector2D GoalTarget = FVector2D(1200.0, 750.0);
	FVector2D CurrentTarget = FVector2D(1200.0, 750.0);
	FVector2D TargetVelocity = FVector2D::ZeroVector;
	double GoalDistanceM = 1400.0;
	double CurrentDistanceM = 1400.0;
	double DistanceVelocity = 0.0;
	double GoalYawOffset = 0.0;
	double CurrentYawOffset = 0.0;
	double YawVelocity = 0.0;
	double CurrentPitchDegrees = 55.0;
	double GroundZM = 0.0;
	double GroundVelocity = 0.0;
	bool bGroundInitialized = false;

	/** Framing insets (viewport fractions) and the screen offset of the target point they ask for, in clip space (+Y up). */
	float InsetLeft = 0.0f;
	float InsetTop = 0.0f;
	float InsetRight = 0.0f;
	float InsetBottom = 0.0f;
	FVector2D GoalScreenOffset = FVector2D::ZeroVector;
	FVector2D CurrentScreenOffset = FVector2D::ZeroVector;
	FVector2D ScreenOffsetVelocity = FVector2D::ZeroVector;

	bool bFlying = false;
	double FlightElapsed = 0.0;
	double FlightDuration = 1.0;
	double FlightLiftM = 0.0;
	FVector2D FlightFrom = FVector2D::ZeroVector;
	FVector2D FlightTo = FVector2D::ZeroVector;
	double FlightFromDistanceM = 0.0;
	double FlightToDistanceM = 0.0;
};
