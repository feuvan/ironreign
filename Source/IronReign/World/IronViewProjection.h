#pragma once

#include "CoreMinimal.h"

class APlayerController;

/**
 * One frame's projection of the local player's view (docs/DESIGN.md section 12.6).
 *
 * Holds exactly what APlayerController::ProjectWorldLocationToScreen and DeprojectScreenPositionToWorld rebuild on
 * every call through ULocalPlayer::GetProjectionData: the camera manager's cached view (including a running
 * view-target blend), its field of view, the aspect-ratio axis constraint, the letterbox bars of a camera with a
 * constrained aspect ratio, and the viewport size. Capturing it once and projecting hundreds of overlay anchors with
 * it costs two 4x4 multiplications per point instead of one GetProjectionData call per point, with the same results.
 *
 * Pixels are game viewport render pixels with the origin at the top-left of the viewport, like
 * ProjectWorldLocationToScreen(..., bPlayerViewportRelative = false). Plain data, cheap to copy. A snapshot is valid
 * for the frame it was captured in: AIronWorldMap3D::GetViewProjection / AIronBattleBoard3D::GetViewProjection keep
 * one that is refreshed whenever the frame, the camera update or the viewport size changed.
 */
struct IRONREIGN_API FIronViewProjection
{
	/** Captures Controller's view now. False (and Out invalid) without a local player, viewport or view rectangle. */
	static bool Capture(const APlayerController* Controller, FIronViewProjection& OutView);

	/**
	 * Recaptures unless this snapshot already shows Controller's current view: same engine frame (GFrameCounter),
	 * same camera manager update and same viewport size. Returns IsValid().
	 */
	bool Refresh(const APlayerController* Controller);

	bool IsValid() const { return bValid; }

	/**
	 * Viewport pixel of a world location (cm) and its depth along the view direction (cm: the clip-space W of the
	 * perspective projection, the value depth of field and sorting use). False behind the camera or when invalid;
	 * points beside or beyond the screen edges still project (outside 0..size), as with ProjectWorldLocationToScreen.
	 */
	bool Project(const FVector& WorldLocationCm, FVector2D& OutViewportPixel, float& OutDepthCm) const;
	bool Project(const FVector& WorldLocationCm, FVector2D& OutViewportPixel) const;

	/**
	 * Ray through a viewport pixel: origin on the near plane (world cm) and unit direction, like
	 * DeprojectScreenPositionToWorld. Sub-pixel exact (the engine call truncates the pixel to whole pixels), so
	 * Deproject(Project(P)) passes through P. False when invalid.
	 */
	bool Deproject(const FVector2D& ViewportPixel, FVector& OutRayOriginCm, FVector& OutRayDirection) const;

	/** The pixel lies inside the rendered view rectangle (not on a letterbox bar). */
	bool IsInView(const FVector2D& ViewportPixel) const;

	/** Rendered view rectangle in viewport pixels (inside the letterbox bars of a constrained aspect ratio). */
	const FIntRect& GetViewRect() const { return ViewRect; }
	/** The player's whole share of the viewport (equal to GetViewRect() without letterbox bars). */
	const FIntRect& GetViewportRect() const { return ViewportRect; }
	/** Camera location (world cm). */
	const FVector& GetViewOrigin() const { return ViewOrigin; }
	/** Unit view direction in world space. */
	FVector GetViewDirection() const;

private:
	FVector ViewOrigin = FVector::ZeroVector;
	/** World to view space rotation (UE's axis swap included: view X right, Y up, Z forward). */
	FMatrix ViewRotationMatrix = FMatrix::Identity;
	FMatrix InverseViewRotationMatrix = FMatrix::Identity;
	/** View to clip space (reversed Z: the near plane at Z = 1). */
	FMatrix ProjectionMatrix = FMatrix::Identity;
	FMatrix InverseProjectionMatrix = FMatrix::Identity;
	FIntRect ViewRect;
	FIntRect ViewportRect;
	bool bValid = false;

	// What Refresh compares; only identities, never dereferenced.
	const APlayerController* CapturedController = nullptr;
	uint64 CapturedFrame = 0;
	float CapturedCameraTime = -1.0f;
	FVector2D CapturedViewportSize = FVector2D::ZeroVector;
	bool bCaptured = false;
};
