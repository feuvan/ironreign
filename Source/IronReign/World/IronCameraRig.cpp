#include "World/IronCameraRig.h"

#include "World/IronTerrain.h"
#include "World/IronWorldMath.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"

namespace IronCameraRigDetail
{
	constexpr double TargetSmoothTime = 0.12;
	constexpr double DistanceSmoothTime = 0.18;
	constexpr double YawSmoothTime = 0.15;
	constexpr double GroundSmoothTime = 0.35;
	/** Distance multiplier per wheel notch. */
	constexpr double ZoomStepFactor = 0.82;
	/** The camera never gets closer than this to the terrain below it (metres). */
	constexpr double MinClearanceM = 40.0;
	constexpr double MaxFlightLiftM = 900.0;
	constexpr double MaxStepSeconds = 0.1;
}

AIronCameraRig::AIronCameraRig()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(SceneRoot);

	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	Camera->SetupAttachment(SceneRoot);
	Camera->SetFieldOfView(IronWorld::CameraFieldOfViewDegrees);
	Camera->bConstrainAspectRatio = false;
	Camera->bUsePawnControlRotation = false;
}

UCameraComponent* AIronCameraRig::GetCamera() const
{
	return Camera.Get();
}

float AIronCameraRig::GetFieldOfView() const
{
	return Camera != nullptr ? Camera->FieldOfView : IronWorld::CameraFieldOfViewDegrees;
}

void AIronCameraRig::SetTerrain(AIronTerrain* InTerrain)
{
	Terrain = InTerrain;
	bGroundInitialized = false;
}

void AIronCameraRig::SetMapBounds(const FVector2D& MapSizeM)
{
	MapSize = FVector2D(FMath::Max(1.0, MapSizeM.X), FMath::Max(1.0, MapSizeM.Y));
	GoalTarget = ClampToMap(GoalTarget);
	CurrentTarget = ClampToMap(CurrentTarget);
}

FVector2D AIronCameraRig::ClampToMap(const FVector2D& MapPointM) const
{
	return FVector2D(FMath::Clamp(MapPointM.X, 0.0, MapSize.X), FMath::Clamp(MapPointM.Y, 0.0, MapSize.Y));
}

double AIronCameraRig::SurfaceAt(const FVector2D& MapPointM) const
{
	const AIronTerrain* TerrainActor = Terrain.Get();
	return TerrainActor != nullptr ? static_cast<double>(TerrainActor->SampleSurface(MapPointM)) : 0.0;
}

double AIronCameraRig::GroundUnderTarget(const FVector2D& MapPointM) const
{
	// Averaged over a footprint that grows with the zoom, so the focus glides over ridges instead of bouncing.
	const double Radius = FMath::Clamp(CurrentDistanceM * 0.06, 10.0, 150.0);
	double Sum = 2.0 * SurfaceAt(MapPointM);
	Sum += SurfaceAt(MapPointM + FVector2D(Radius, 0.0));
	Sum += SurfaceAt(MapPointM + FVector2D(-Radius, 0.0));
	Sum += SurfaceAt(MapPointM + FVector2D(0.0, Radius));
	Sum += SurfaceAt(MapPointM + FVector2D(0.0, -Radius));
	return Sum / 6.0;
}

double AIronCameraRig::PitchForDistance(double DistanceM)
{
	const double Alpha = FMath::Clamp((DistanceM - IronWorld::CameraMinDistanceM) / (IronWorld::CameraMaxDistanceM - IronWorld::CameraMinDistanceM), 0.0, 1.0);
	const double Shaped = Alpha * Alpha * (3.0 - 2.0 * Alpha);
	return FMath::Lerp(IronWorld::CameraMinPitchDegrees, IronWorld::CameraMaxPitchDegrees, Shaped);
}

void AIronCameraRig::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const double StepSeconds = FMath::Clamp(static_cast<double>(DeltaSeconds), 0.0, IronCameraRigDetail::MaxStepSeconds);

	if (bFlying)
	{
		FlightElapsed += StepSeconds;
		const double Alpha = FMath::Clamp(FlightElapsed / FMath::Max(0.01, FlightDuration), 0.0, 1.0);
		const double Eased = IronWorld::EaseInOut(Alpha);
		CurrentTarget = FlightFrom + (FlightTo - FlightFrom) * Eased;
		CurrentDistanceM = FMath::Lerp(FlightFromDistanceM, FlightToDistanceM, Eased) + FlightLiftM * FMath::Sin(UE_DOUBLE_PI * Alpha);
		TargetVelocity = FVector2D::ZeroVector;
		DistanceVelocity = 0.0;
		if (Alpha >= 1.0)
		{
			bFlying = false;
			GoalTarget = FlightTo;
			CurrentTarget = FlightTo;
			GoalDistanceM = FlightToDistanceM;
			CurrentDistanceM = FlightToDistanceM;
		}
	}
	else
	{
		CurrentTarget.X = IronWorld::SmoothDamp(CurrentTarget.X, GoalTarget.X, TargetVelocity.X, IronCameraRigDetail::TargetSmoothTime, StepSeconds);
		CurrentTarget.Y = IronWorld::SmoothDamp(CurrentTarget.Y, GoalTarget.Y, TargetVelocity.Y, IronCameraRigDetail::TargetSmoothTime, StepSeconds);
		CurrentDistanceM = IronWorld::SmoothDamp(CurrentDistanceM, GoalDistanceM, DistanceVelocity, IronCameraRigDetail::DistanceSmoothTime, StepSeconds);
	}
	CurrentYawOffset = IronWorld::SmoothDamp(CurrentYawOffset, GoalYawOffset, YawVelocity, IronCameraRigDetail::YawSmoothTime, StepSeconds);

	const double Ground = GroundUnderTarget(CurrentTarget);
	if (!bGroundInitialized)
	{
		GroundZM = Ground;
		GroundVelocity = 0.0;
		bGroundInitialized = true;
	}
	else
	{
		GroundZM = IronWorld::SmoothDamp(GroundZM, Ground, GroundVelocity, IronCameraRigDetail::GroundSmoothTime, StepSeconds);
	}
	UpdatePose();
}

void AIronCameraRig::UpdatePose()
{
	CurrentPitchDegrees = PitchForDistance(FMath::Min(CurrentDistanceM, IronWorld::CameraMaxDistanceM));
	const FRotator ViewRotation(-CurrentPitchDegrees, IronWorld::NorthYawDegrees + CurrentYawOffset, 0.0);
	const FVector Focus = GetFocusWorldLocation();
	FVector CameraLocation = Focus - ViewRotation.Vector() * (CurrentDistanceM * IronWorld::CmPerMetre);
	FRotator CameraRotation = ViewRotation;

	// Close to mountains the camera rises instead of clipping into them, still aiming at the focus point.
	const double MinZ = (SurfaceAt(IronWorld::WorldToMap(CameraLocation)) + IronCameraRigDetail::MinClearanceM) * IronWorld::CmPerMetre;
	if (CameraLocation.Z < MinZ)
	{
		CameraLocation.Z = MinZ;
		CameraRotation = (Focus - CameraLocation).Rotation();
	}
	SetActorLocationAndRotation(CameraLocation, CameraRotation);
}

FVector AIronCameraRig::GetFocusWorldLocation() const
{
	return IronWorld::MapToWorld(CurrentTarget, GroundZM);
}

float AIronCameraRig::GetCameraDistanceCm() const
{
	return static_cast<float>(FVector::Distance(GetActorLocation(), GetFocusWorldLocation()));
}

void AIronCameraRig::CancelFlight()
{
	if (!bFlying)
	{
		return;
	}
	bFlying = false;
	GoalTarget = CurrentTarget;
	GoalDistanceM = FMath::Clamp(CurrentDistanceM, IronWorld::CameraMinDistanceM, IronWorld::CameraMaxDistanceM);
}

void AIronCameraRig::Pan(const FVector2D& ScreenDeltaPx, const FVector2D& ViewportSizePx)
{
	if (ViewportSizePx.X <= 1.0)
	{
		return;
	}
	CancelFlight();
	const double HalfFovRadians = FMath::DegreesToRadians(static_cast<double>(GetFieldOfView()) * 0.5);
	const double MetresPerPixel = 2.0 * CurrentDistanceM * FMath::Tan(HalfFovRadians) / ViewportSizePx.X;
	const double YawRadians = FMath::DegreesToRadians(IronWorld::NorthYawDegrees + CurrentYawOffset);
	const FVector2D ViewAhead(FMath::Cos(YawRadians), FMath::Sin(YawRadians));
	const FVector2D ViewRight(-ViewAhead.Y, ViewAhead.X);
	// Screen-vertical motion covers more ground than horizontal because the view is tilted.
	const double AheadStretch = 1.0 / FMath::Max(0.35, FMath::Sin(FMath::DegreesToRadians(CurrentPitchDegrees)));
	const FVector2D Delta = (ViewRight * -ScreenDeltaPx.X + ViewAhead * (ScreenDeltaPx.Y * AheadStretch)) * MetresPerPixel;
	GoalTarget = ClampToMap(GoalTarget + Delta);
	CurrentTarget = ClampToMap(CurrentTarget + Delta);
	TargetVelocity = FVector2D::ZeroVector;
}

void AIronCameraRig::Zoom(float WheelDelta, const FVector2D& CursorMapPointM, bool bHasCursorPoint)
{
	if (FMath::IsNearlyZero(WheelDelta))
	{
		return;
	}
	CancelFlight();
	const double Factor = FMath::Pow(IronCameraRigDetail::ZoomStepFactor, static_cast<double>(WheelDelta));
	const double NewDistanceM = FMath::Clamp(GoalDistanceM * Factor, IronWorld::CameraMinDistanceM, IronWorld::CameraMaxDistanceM);
	if (bHasCursorPoint)
	{
		// Keep the point under the cursor roughly in place.
		const double Ratio = NewDistanceM / FMath::Max(1.0, GoalDistanceM);
		GoalTarget = ClampToMap(CursorMapPointM + (GoalTarget - CursorMapPointM) * Ratio);
	}
	GoalDistanceM = NewDistanceM;
}

void AIronCameraRig::Rotate(float DeltaDegrees)
{
	GoalYawOffset = FMath::Clamp(GoalYawOffset + static_cast<double>(DeltaDegrees), -IronWorld::CameraMaxYawOffsetDegrees, IronWorld::CameraMaxYawOffsetDegrees);
}

void AIronCameraRig::ResetRotation()
{
	GoalYawOffset = 0.0;
}

void AIronCameraRig::FocusOn(const FVector2D& MapPointM, float DistanceM, float DurationSeconds)
{
	const FVector2D Destination = ClampToMap(MapPointM);
	const double ClampedDistanceM = FMath::Clamp(static_cast<double>(DistanceM), IronWorld::CameraMinDistanceM, IronWorld::CameraMaxDistanceM);
	const double TravelM = FVector2D::Distance(CurrentTarget, Destination);
	GoalTarget = Destination;
	GoalDistanceM = ClampedDistanceM;
	if (TravelM < 1.0 && FMath::Abs(ClampedDistanceM - CurrentDistanceM) < 1.0)
	{
		bFlying = false;
		return;
	}
	bFlying = true;
	FlightElapsed = 0.0;
	FlightFrom = CurrentTarget;
	FlightTo = Destination;
	FlightFromDistanceM = CurrentDistanceM;
	FlightToDistanceM = ClampedDistanceM;
	FlightLiftM = FMath::Clamp(TravelM * 0.3, 0.0, IronCameraRigDetail::MaxFlightLiftM);
	FlightDuration = FMath::Max(0.2, static_cast<double>(DurationSeconds)) * FMath::Clamp(0.7 + TravelM / 2000.0, 0.7, 1.5);
}

void AIronCameraRig::SnapTo(const FVector2D& MapPointM, float DistanceM)
{
	bFlying = false;
	GoalTarget = ClampToMap(MapPointM);
	CurrentTarget = GoalTarget;
	GoalDistanceM = FMath::Clamp(static_cast<double>(DistanceM), IronWorld::CameraMinDistanceM, IronWorld::CameraMaxDistanceM);
	CurrentDistanceM = GoalDistanceM;
	TargetVelocity = FVector2D::ZeroVector;
	DistanceVelocity = 0.0;
	GroundZM = GroundUnderTarget(CurrentTarget);
	GroundVelocity = 0.0;
	bGroundInitialized = true;
	UpdatePose();
}

void AIronCameraRig::ResnapGround()
{
	GroundZM = GroundUnderTarget(CurrentTarget);
	GroundVelocity = 0.0;
	bGroundInitialized = true;
	UpdatePose();
}
