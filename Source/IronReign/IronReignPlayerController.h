#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"

#include <string>

#include "IronReignPlayerController.generated.h"

class AIronEnvironment;
class AIronWorldMap3D;
class FIronSession;
class SIronRoot;
class UGameViewportClient;

/**
 * Local UI controller: shows the mouse cursor, adds SIronRoot to the game viewport with UI-only input and attaches
 * FIronAudio to the world for music and effects. The widget is removed and the audio shut down again in EndPlay.
 *
 * World rendering is off while only Slate screens are shown (the Entry map has nothing to draw); the 3D scenes turn it
 * on while they are active (AIronWorldMap3D / AIronBattleBoard3D::SetActive).
 *
 * The controller owns the lifetime of the real-time 3D campaign map (docs/DESIGN.md section 12): while a campaign runs
 * and the session presents the map in 3D (FIronSession::Uses3DMap), it spawns AIronWorldMap3D (terrain build starts at
 * once, the strategy screen activates the map when its scene is ready); a load of the same scenario only resyncs it,
 * another scenario rebuilds it, and ending the campaign or switching to 2D hides and destroys it (back to the Slate
 * view target). Graphics options (quality, tilt-shift, ink outlines) are applied live to the map, the battle board and
 * the shared environment, which always shows the painted (gongbi) look (FIronSession::ApplyEnvironmentOptions).
 */
UCLASS()
class IRONREIGN_API AIronReignPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AIronReignPlayerController();

	virtual void Tick(float DeltaSeconds) override;

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void HandleQuitRequested();
	void RemoveRootWidget();

	/** Spawns, resyncs or destroys the 3D campaign map to match the session; applies changed graphics options. */
	void UpdateWorldPresentation(float DeltaSeconds);
	/** Hides (world rendering off unless the battle board is up) and destroys the map, restoring the view target. */
	void DestroyWorldMap();
	/** Pushes quality to the map and the battle board, the look, tilt-shift and ink outlines to the shared environment. */
	void ApplyGraphicsSettings();

	TSharedPtr<SIronRoot> RootWidget;
	TWeakObjectPtr<UGameViewportClient> RootViewport;
	TWeakPtr<FIronSession> CampaignSession;

	/** The 3D map this controller spawned, the campaign (FIronSession::GetCampaignSerial) and scenario it shows. */
	TWeakObjectPtr<AIronWorldMap3D> WorldMap;
	std::string WorldMapScenarioKey;
	int32 WorldMapCampaignSerial = -1;
	/** Campaign serial of a spawn that returned no map (not retried for that campaign). */
	int32 FailedMapSpawnSerial = -1;

	/** FIronSession::GetGraphicsRevision() last applied, and the environment it reached (re-applied to a new one). */
	int32 AppliedGraphicsRevision = -1;
	TWeakObjectPtr<AIronEnvironment> GraphicsEnvironment;
	float GraphicsPollSeconds = 0.0f;

	/** True once this controller attached FIronAudio to its world (only the local UI controller does). */
	bool bAudioAttached = false;
};
