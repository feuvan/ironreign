#include "World/IronViewProjection.h"

#include "Camera/PlayerCameraManager.h"
#include "CoreGlobals.h"
#include "Engine/GameViewportClient.h"
#include "Engine/LocalPlayer.h"
#include "GameFramework/PlayerController.h"
#include "SceneView.h"

namespace IronViewProjectionDetail
{
	/** The game viewport's size in render pixels (zero when the player has no viewport). */
	FVector2D PlayerViewportSize(const APlayerController* Controller)
	{
		FVector2D Size = FVector2D::ZeroVector;
		const ULocalPlayer* LocalPlayer = Controller != nullptr ? Controller->GetLocalPlayer() : nullptr;
		const UGameViewportClient* ViewportClient = LocalPlayer != nullptr ? LocalPlayer->ViewportClient.Get() : nullptr;
		if (ViewportClient != nullptr)
		{
			ViewportClient->GetViewportSize(Size);
		}
		return Size;
	}

	FVector Dehomogenize(const FVector4& Point)
	{
		const FVector Xyz(Point.X, Point.Y, Point.Z);
		return Point.W != 0.0 ? Xyz / Point.W : Xyz;
	}
}

bool FIronViewProjection::Capture(const APlayerController* Controller, FIronViewProjection& OutView)
{
	OutView.bValid = false;
	ULocalPlayer* LocalPlayer = Controller != nullptr ? Controller->GetLocalPlayer() : nullptr;
	UGameViewportClient* ViewportClient = LocalPlayer != nullptr ? LocalPlayer->ViewportClient.Get() : nullptr;
	FViewport* PlayerViewport = ViewportClient != nullptr ? ViewportClient->Viewport : nullptr;
	if (PlayerViewport == nullptr)
	{
		return false;
	}
	// The very call ProjectWorldLocationToScreen / DeprojectScreenPositionToWorld make (UGameplayStatics), and the one
	// the renderer's view setup makes: the camera cache, FOV, aspect-ratio constraint and letterbox bars all match.
	FSceneViewProjectionData ProjectionData;
	if (!LocalPlayer->GetProjectionData(PlayerViewport, ProjectionData))
	{
		return false;
	}
	const FIntRect& Constrained = ProjectionData.GetConstrainedViewRect();
	if (Constrained.Width() <= 0 || Constrained.Height() <= 0)
	{
		return false;
	}
	OutView.ViewOrigin = ProjectionData.ViewOrigin;
	OutView.ViewRotationMatrix = ProjectionData.ViewRotationMatrix;
	OutView.InverseViewRotationMatrix = ProjectionData.ViewRotationMatrix.Inverse();
	OutView.ProjectionMatrix = ProjectionData.ProjectionMatrix;
	OutView.InverseProjectionMatrix = ProjectionData.ProjectionMatrix.Inverse();
	OutView.ViewRect = Constrained;
	OutView.ViewportRect = ProjectionData.GetViewRect();
	OutView.bValid = true;
	return true;
}

bool FIronViewProjection::Refresh(const APlayerController* Controller)
{
	const APlayerCameraManager* CameraManager = Controller != nullptr ? Controller->PlayerCameraManager.Get() : nullptr;
	// The camera cache is rewritten once per frame after the actors ticked; Slate paints after that. Comparing its time
	// stamp also catches a snapshot taken earlier in the same frame, before the camera moved.
	const float CameraTime = CameraManager != nullptr ? CameraManager->GetCameraCacheTime() : -1.0f;
	const FVector2D ViewportSize = IronViewProjectionDetail::PlayerViewportSize(Controller);
	if (bCaptured && CapturedController == Controller && CapturedFrame == GFrameCounter && CapturedCameraTime == CameraTime && CapturedViewportSize == ViewportSize)
	{
		return bValid;
	}
	Capture(Controller, *this);
	bCaptured = true;
	CapturedController = Controller;
	CapturedFrame = GFrameCounter;
	CapturedCameraTime = CameraTime;
	CapturedViewportSize = ViewportSize;
	return bValid;
}

bool FIronViewProjection::Project(const FVector& WorldLocationCm, FVector2D& OutViewportPixel, float& OutDepthCm) const
{
	if (!bValid)
	{
		return false;
	}
	// Translation first, then rotation and projection (the order of FSceneViewProjectionData::ComputeViewProjectionMatrix,
	// applied step by step so the 100 km offset of the battle board loses no precision).
	const FVector4 ViewSpace = ViewRotationMatrix.TransformFVector4(FVector4(WorldLocationCm - ViewOrigin, 1.0));
	const FVector4 Clip = ProjectionMatrix.TransformFVector4(ViewSpace);
	if (Clip.W <= 0.0)
	{
		return false;
	}
	// FSceneView::ProjectWorldToScreen: clip space -1..1 to 0..1 (Y down), then into the view rectangle.
	const double InverseW = 1.0 / Clip.W;
	const double NormalizedX = 0.5 + 0.5 * Clip.X * InverseW;
	const double NormalizedY = 0.5 - 0.5 * Clip.Y * InverseW;
	OutViewportPixel = FVector2D(
		static_cast<double>(ViewRect.Min.X) + NormalizedX * static_cast<double>(ViewRect.Width()),
		static_cast<double>(ViewRect.Min.Y) + NormalizedY * static_cast<double>(ViewRect.Height()));
	OutDepthCm = static_cast<float>(Clip.W);
	return true;
}

bool FIronViewProjection::Project(const FVector& WorldLocationCm, FVector2D& OutViewportPixel) const
{
	float DepthCm = 0.0f;
	return Project(WorldLocationCm, OutViewportPixel, DepthCm);
}

bool FIronViewProjection::Deproject(const FVector2D& ViewportPixel, FVector& OutRayOriginCm, FVector& OutRayDirection) const
{
	if (!bValid)
	{
		return false;
	}
	// FSceneView::DeprojectScreenToWorld (inverse projection, then inverse view), without truncating to whole pixels.
	const double NormalizedX = (ViewportPixel.X - static_cast<double>(ViewRect.Min.X)) / static_cast<double>(ViewRect.Width());
	const double NormalizedY = (ViewportPixel.Y - static_cast<double>(ViewRect.Min.Y)) / static_cast<double>(ViewRect.Height());
	const double ClipX = (NormalizedX - 0.5) * 2.0;
	const double ClipY = (0.5 - NormalizedY) * 2.0;
	// Reversed Z: the near plane is Z = 1; any smaller Z lies farther along the same ray.
	const FVector NearView = IronViewProjectionDetail::Dehomogenize(InverseProjectionMatrix.TransformFVector4(FVector4(ClipX, ClipY, 1.0, 1.0)));
	const FVector FartherView = IronViewProjectionDetail::Dehomogenize(InverseProjectionMatrix.TransformFVector4(FVector4(ClipX, ClipY, 0.5, 1.0)));
	const FVector4 NearWorld = InverseViewRotationMatrix.TransformFVector4(FVector4(NearView, 1.0));
	const FVector4 RayWorld = InverseViewRotationMatrix.TransformFVector4(FVector4(FartherView - NearView, 0.0));
	OutRayOriginCm = FVector(NearWorld.X, NearWorld.Y, NearWorld.Z) + ViewOrigin;
	OutRayDirection = FVector(RayWorld.X, RayWorld.Y, RayWorld.Z).GetSafeNormal();
	return !OutRayDirection.IsNearlyZero();
}

bool FIronViewProjection::IsInView(const FVector2D& ViewportPixel) const
{
	return bValid
		&& ViewportPixel.X >= static_cast<double>(ViewRect.Min.X) && ViewportPixel.X <= static_cast<double>(ViewRect.Max.X)
		&& ViewportPixel.Y >= static_cast<double>(ViewRect.Min.Y) && ViewportPixel.Y <= static_cast<double>(ViewRect.Max.Y);
}

FVector FIronViewProjection::GetViewDirection() const
{
	// View space looks along +Z.
	const FVector4 Forward = InverseViewRotationMatrix.TransformFVector4(FVector4(0.0, 0.0, 1.0, 0.0));
	return FVector(Forward.X, Forward.Y, Forward.Z).GetSafeNormal();
}
