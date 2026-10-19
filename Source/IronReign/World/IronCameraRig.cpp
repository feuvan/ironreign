#include "World/IronCameraRig.h"

#include "World/IronTerrain.h"
#include "World/IronWorldMath.h"

#include "Camera/CameraComponent.h"
#include "Components/SceneComponent.h"
#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Math/RotationMatrix.h"

namespace IronCameraRigDetail
{
	constexpr double TargetSmoothTime = 0.12;
	constexpr double DistanceSmoothTime = 0.18;
	constexpr double YawSmoothTime = 0.15;
	constexpr double GroundSmoothTime = 0.35;
	/** Distance multiplier per wheel notch. */
	constexpr double ZoomStepFactor = 0.82;
	/** Secant steps solving the zoom target's ground height, and the mismatch (cm) that ends them. */
	constexpr int32 ZoomSolveSteps = 8;
	constexpr double ZoomSolveToleranceCm = 1.0;
	/** The camera never gets closer than this to the terrain below it (metres). */
	constexpr double MinClearanceM = 40.0;
	constexpr double MaxFlightLiftM = 900.0;
	constexpr double MaxStepSeconds = 0.1;
	/** Framing changes (panels opening, window resizes) glide over about this long. */
	constexpr double FramingSmoothTime = 0.25;
	constexpr float MaxInset = 0.45f;
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

double AIronCameraRig::GroundUnderTarget(const FVector2D& MapPointM, double DistanceM) const
{
	// Averaged over a footprint that grows with the zoom, so the focus glides over ridges instead of bouncing.
	const double Radius = FMath::Clamp(DistanceM * 0.06, 10.0, 150.0);
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
	CurrentScreenOffset.X = IronWorld::SmoothDamp(CurrentScreenOffset.X, GoalScreenOffset.X, ScreenOffsetVelocity.X, IronCameraRigDetail::FramingSmoothTime, StepSeconds);
	CurrentScreenOffset.Y = IronWorld::SmoothDamp(CurrentScreenOffset.Y, GoalScreenOffset.Y, ScreenOffsetVelocity.Y, IronCameraRigDetail::FramingSmoothTime, StepSeconds);

	const double Ground = GroundUnderTarget(CurrentTarget, CurrentDistanceM);
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

FVector2D AIronCameraRig::GetViewportSizePx() const
{
	FVector2D Size(1920.0, 1080.0);
	const UWorld* GameWorld = GetWorld();
	const UGameViewportClient* GameViewport = GameWorld != nullptr ? GameWorld->GetGameViewport() : nullptr;
	if (GameViewport != nullptr)
	{
		FVector2D Measured = FVector2D::ZeroVector;
		GameViewport->GetViewportSize(Measured);
		if (Measured.X > 1.0 && Measured.Y > 1.0)
		{
			Size = Measured;
		}
	}
	return Size;
}

FVector AIronCameraRig::GoalPoseRay(double DistanceM, const FVector2D& Clip) const
{
	const FVector2D ViewportSize = GetViewportSizePx();
	const double TanHalfH = FMath::Tan(FMath::DegreesToRadians(static_cast<double>(GetFieldOfView()) * 0.5));
	const double TanHalfV = TanHalfH * ViewportSize.Y / FMath::Max(1.0, ViewportSize.X);
	const FRotationMatrix Axes(FRotator(-PitchForDistance(FMath::Min(DistanceM, IronWorld::CameraMaxDistanceM)), IronWorld::NorthYawDegrees + GoalYawOffset, 0.0));
	return Axes.GetScaledAxis(EAxis::X) + Axes.GetScaledAxis(EAxis::Y) * (Clip.X * TanHalfH) + Axes.GetScaledAxis(EAxis::Z) * (Clip.Y * TanHalfV);
}

void AIronCameraRig::UpdatePose()
{
	CurrentPitchDegrees = PitchForDistance(FMath::Min(CurrentDistanceM, IronWorld::CameraMaxDistanceM));
	const FRotator ViewRotation(-CurrentPitchDegrees, IronWorld::NorthYawDegrees + CurrentYawOffset, 0.0);
	const FVector Focus = GetFocusWorldLocation();
	const double DistanceCm = CurrentDistanceM * IronWorld::CmPerMetre;

	// Framing insets: the point drawn at the viewport centre (Aim) lies beside the focus, so the focus lands at clip
	// position CurrentScreenOffset, the middle of the uncovered part of the screen. The horizontal field of view is the
	// camera's (aspect-ratio axis constraint "maintain X FOV", the engine default); the vertical one follows the aspect.
	const FVector2D ViewportSize = GetViewportSizePx();
	const double TanHalfH = FMath::Tan(FMath::DegreesToRadians(static_cast<double>(GetFieldOfView()) * 0.5));
	const double TanHalfV = TanHalfH * ViewportSize.Y / FMath::Max(1.0, ViewportSize.X);
	const FRotationMatrix ViewAxes(ViewRotation);
	const FVector Right = ViewAxes.GetScaledAxis(EAxis::Y);
	const FVector Up = ViewAxes.GetScaledAxis(EAxis::Z);
	const FVector Aim = Focus - Right * (CurrentScreenOffset.X * DistanceCm * TanHalfH) - Up * (CurrentScreenOffset.Y * DistanceCm * TanHalfV);
	FVector CameraLocation = Aim - ViewRotation.Vector() * DistanceCm;
	FRotator CameraRotation = ViewRotation;

	// Close to mountains the camera rises instead of clipping into them, still aiming at the same screen-centre point.
	const double MinZ = (SurfaceAt(IronWorld::WorldToMap(CameraLocation)) + IronCameraRigDetail::MinClearanceM) * IronWorld::CmPerMetre;
	if (CameraLocation.Z < MinZ)
	{
		CameraLocation.Z = MinZ;
		CameraRotation = (Aim - CameraLocation).Rotation();
	}
	SetActorLocationAndRotation(CameraLocation, CameraRotation);
}

FVector AIronCameraRig::GetFocusWorldLocation() const
{
	return IronWorld::MapToWorld(CurrentTarget, GroundZM);
}

float AIronCameraRig::GetCameraDistanceCm() const
{
	const double Depth = FVector::DotProduct(GetFocusWorldLocation() - GetActorLocation(), GetActorForwardVector());
	return static_cast<float>(FMath::Max(1.0, Depth));
}

void AIronCameraRig::SetFramingInsets(float Left, float Top, float Right, float Bottom, bool bInstant)
{
	using IronCameraRigDetail::MaxInset;
	const float NewLeft = FMath::Clamp(Left, 0.0f, MaxInset);
	const float NewTop = FMath::Clamp(Top, 0.0f, MaxInset);
	const float NewRight = FMath::Clamp(Right, 0.0f, MaxInset);
	const float NewBottom = FMath::Clamp(Bottom, 0.0f, MaxInset);
	const bool bChanged = !FMath::IsNearlyEqual(NewLeft, InsetLeft, 1.0e-4f) || !FMath::IsNearlyEqual(NewTop, InsetTop, 1.0e-4f)
		|| !FMath::IsNearlyEqual(NewRight, InsetRight, 1.0e-4f) || !FMath::IsNearlyEqual(NewBottom, InsetBottom, 1.0e-4f);
	if (!bChanged && !bInstant)
	{
		return;
	}
	InsetLeft = NewLeft;
	InsetTop = NewTop;
	InsetRight = NewRight;
	InsetBottom = NewBottom;
	// Centre of the uncovered rectangle in clip space: x = left - right, y = bottom - top (clip +Y is up).
	GoalScreenOffset = FVector2D(static_cast<double>(InsetLeft - InsetRight), static_cast<double>(InsetBottom - InsetTop));
	if (bInstant || !IsActorTickEnabled())
	{
		CurrentScreenOffset = GoalScreenOffset;
		ScreenOffsetVelocity = FVector2D::ZeroVector;
		UpdatePose();
	}
}

FVector2D AIronCameraRig::GetFramingCentre() const
{
	return FVector2D(0.5 + 0.5 * CurrentScreenOffset.X, 0.5 - 0.5 * CurrentScreenOffset.Y);
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

void AIronCameraRig::ZoomTowardCursor(float WheelDelta, const FVector2D& CursorClip)
{
	if (FMath::IsNearlyZero(WheelDelta))
	{
		return;
	}
	CancelFlight();
	const double OldDistanceM = FMath::Max(1.0, GoalDistanceM);
	const double NewDistanceM = FMath::Clamp(GoalDistanceM * FMath::Pow(IronCameraRigDetail::ZoomStepFactor, static_cast<double>(WheelDelta)), IronWorld::CameraMinDistanceM, IronWorld::CameraMaxDistanceM);
	GoalDistanceM = NewDistanceM;

	// The point under the cursor in the goal pose as UpdatePose draws it once settled (UpdatePose: camera = focus -
	// distance * the ray through the framing centre; the clearance rise over mountains is left out).
	const FVector OldCursorRay = GoalPoseRay(OldDistanceM, CursorClip);
	const FVector OldFocus = IronWorld::MapToWorld(GoalTarget, GroundUnderTarget(GoalTarget, OldDistanceM));
	const FVector OldCamera = OldFocus - GoalPoseRay(OldDistanceM, GoalScreenOffset) * (OldDistanceM * IronWorld::CmPerMetre);
	const AIronTerrain* TerrainActor = Terrain.Get();
	FVector CursorHit = FVector::ZeroVector;
	if (TerrainActor == nullptr || !TerrainActor->TraceSurface(OldCamera, OldCursorRay, CursorHit))
	{
		// No heightmap yet (or the ray misses it): the level of the focus.
		if (OldCursorRay.Z > -1.0e-3)
		{
			return;
		}
		CursorHit = OldCamera + OldCursorRay * ((OldFocus.Z - OldCamera.Z) / OldCursorRay.Z);
	}
	const FVector NewCursorRay = GoalPoseRay(NewDistanceM, CursorClip);
	if (NewCursorRay.Z > -1.0e-3)
	{
		return;
	}

	// The new focus F must put the camera F - D * NewCentreRay on the line through CursorHit along NewCursorRay, so
	// F.XY = FocusBase + F.Z * FocusSlope; and F.Z is the ground under F. Solve that one unknown with secant steps.
	const FVector NewCentreRay = GoalPoseRay(NewDistanceM, GoalScreenOffset);
	const double NewDistanceCm = NewDistanceM * IronWorld::CmPerMetre;
	const FVector2D CursorRayXY(NewCursorRay.X, NewCursorRay.Y);
	const FVector2D FocusBase = FVector2D(CursorHit.X, CursorHit.Y) + FVector2D(NewCentreRay.X, NewCentreRay.Y) * NewDistanceCm - CursorRayXY * ((CursorHit.Z + NewDistanceCm * NewCentreRay.Z) / NewCursorRay.Z);
	const FVector2D FocusSlope = CursorRayXY / NewCursorRay.Z;
	const auto FocusMapPointAt = [&FocusBase, &FocusSlope](double FocusZCm)
	{
		return IronWorld::WorldToMap(FVector(FocusBase + FocusSlope * FocusZCm, 0.0));
	};
	const auto Mismatch = [this, &FocusMapPointAt, NewDistanceM](double FocusZCm)
	{
		return FocusZCm - GroundUnderTarget(FocusMapPointAt(FocusZCm), NewDistanceM) * IronWorld::CmPerMetre;
	};
	// The ground lies within the terrain's elevation range: keep the steps there.
	double LowestCm = OldFocus.Z;
	double HighestCm = OldFocus.Z;
	if (TerrainActor != nullptr)
	{
		const FIronTerrainInfo& TerrainInfo = TerrainActor->GetInfo();
		LowestCm = FMath::Min(LowestCm, FMath::Min(TerrainInfo.MinElevationM, TerrainInfo.SeaLevelM) * IronWorld::CmPerMetre);
		HighestCm = FMath::Max(HighestCm, FMath::Max(TerrainInfo.MaxElevationM, TerrainInfo.SeaLevelM) * IronWorld::CmPerMetre);
	}
	double PreviousZ = OldFocus.Z;
	double PreviousMismatch = Mismatch(PreviousZ);
	double BestZ = PreviousZ;
	double BestMismatch = FMath::Abs(PreviousMismatch);
	double FocusZ = FMath::Clamp(PreviousZ - PreviousMismatch, LowestCm, HighestCm);
	for (int32 SolveStep = 0; SolveStep < IronCameraRigDetail::ZoomSolveSteps && BestMismatch > IronCameraRigDetail::ZoomSolveToleranceCm; ++SolveStep)
	{
		const double FocusMismatch = Mismatch(FocusZ);
		if (FMath::Abs(FocusMismatch) < BestMismatch)
		{
			BestZ = FocusZ;
			BestMismatch = FMath::Abs(FocusMismatch);
		}
		const double MismatchChange = FocusMismatch - PreviousMismatch;
		if (FMath::Abs(MismatchChange) < 1.0e-9)
		{
			break;
		}
		const double NextZ = FMath::Clamp(FocusZ - FocusMismatch * (FocusZ - PreviousZ) / MismatchChange, LowestCm, HighestCm);
		PreviousZ = FocusZ;
		PreviousMismatch = FocusMismatch;
		FocusZ = NextZ;
	}
	GoalTarget = ClampToMap(FocusMapPointAt(BestZ));
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
	CurrentScreenOffset = GoalScreenOffset;
	ScreenOffsetVelocity = FVector2D::ZeroVector;
	GroundZM = GroundUnderTarget(CurrentTarget, CurrentDistanceM);
	GroundVelocity = 0.0;
	bGroundInitialized = true;
	UpdatePose();
}

void AIronCameraRig::ResnapGround()
{
	GroundZM = GroundUnderTarget(CurrentTarget, CurrentDistanceM);
	GroundVelocity = 0.0;
	bGroundInitialized = true;
	UpdatePose();
}
