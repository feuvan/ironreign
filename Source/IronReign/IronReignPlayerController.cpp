#include "IronReignPlayerController.h"

#include "IronReignLog.h"
#include "IronReignWorldStateSubsystem.h"
#include "Sim/IronState.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/SIronRoot.h"
#include "World/IronBattleBoard3D.h"
#include "World/IronEnvironment.h"
#include "World/IronWorldMap3D.h"

#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Kismet/KismetSystemLibrary.h"

namespace IronPlayerControllerDetail
{
	/** How often a missing graphics target (no environment reached yet, e.g. a board spawned later) is looked for. */
	constexpr float GraphicsPollIntervalSeconds = 0.5f;
}

AIronReignPlayerController::AIronReignPlayerController()
{
	bShowMouseCursor = true;
	bEnableClickEvents = false;
	bEnableMouseOverEvents = false;
	DefaultMouseCursor = EMouseCursor::Default;
}

void AIronReignPlayerController::BeginPlay()
{
	Super::BeginPlay();

	if (!IsLocalPlayerController())
	{
		return;
	}

	UWorld* GameWorld = GetWorld();
	UGameViewportClient* TargetViewport = GameWorld != nullptr ? GameWorld->GetGameViewport() : nullptr;
	UIronReignWorldStateSubsystem* WorldState = GameWorld != nullptr ? GameWorld->GetSubsystem<UIronReignWorldStateSubsystem>() : nullptr;
	TSharedPtr<FIronSession> IronSession;
	if (WorldState != nullptr)
	{
		IronSession = WorldState->GetSession();
	}
	if (TargetViewport == nullptr || !IronSession.IsValid())
	{
		UE_LOG(LogIronReign, Warning, TEXT("Iron Reign UI not created: no game viewport or campaign session in this world."));
		return;
	}
	CampaignSession = IronSession;

	// Slate draws the screens; the world is only rendered while a 3D scene is active (its SetActive turns rendering on
	// and off). Nothing is active yet on a fresh world, so the (empty) Entry map is not drawn behind the title.
	const AIronWorldMap3D* ExistingMap = AIronWorldMap3D::FindMap(GameWorld);
	const AIronBattleBoard3D* ExistingBoard = AIronBattleBoard3D::FindBoard(GameWorld);
	const bool bSceneActive = (ExistingMap != nullptr && ExistingMap->IsMapActive()) || (ExistingBoard != nullptr && ExistingBoard->IsBoardActive());
	TargetViewport->bDisableWorldRendering = !bSceneActive;

	// Before the root exists so the title music starts with the first screen. The session already applied the saved
	// volumes (FIronSession::Initialize).
	FIronAudio::Get().Initialize(GameWorld);
	bAudioAttached = true;

	RootWidget = SNew(SIronRoot)
		.Session(IronSession)
		.OnQuitRequested(FSimpleDelegate::CreateUObject(this, &AIronReignPlayerController::HandleQuitRequested));
	TargetViewport->AddViewportWidgetContent(RootWidget.ToSharedRef(), 10);
	RootViewport = TargetViewport;

	bShowMouseCursor = true;
	FInputModeUIOnly UiInputMode;
	UiInputMode.SetWidgetToFocus(RootWidget);
	UiInputMode.SetLockMouseToViewportBehavior(EMouseLockMode::DoNotLock);
	SetInputMode(UiInputMode);
}

void AIronReignPlayerController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
	RemoveRootWidget();
	// The world tears its actors down itself; only forget the map (destroying here would race the world's cleanup).
	WorldMap.Reset();
	GraphicsEnvironment.Reset();
	CampaignSession.Reset();
	if (bAudioAttached)
	{
		// Release every sound object while the world is still alive (UIronReignWorldStateSubsystem::Deinitialize
		// repeats this as a safety net; Shutdown is idempotent).
		bAudioAttached = false;
		FIronAudio::Get().Shutdown();
	}
	Super::EndPlay(EndPlayReason);
}

void AIronReignPlayerController::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// Only the local UI controller (the one that created the screens) manages the presentation.
	if (RootWidget.IsValid())
	{
		UpdateWorldPresentation(DeltaSeconds);
	}
}

void AIronReignPlayerController::RemoveRootWidget()
{
	if (RootWidget.IsValid())
	{
		if (UGameViewportClient* TargetViewport = RootViewport.Get())
		{
			TargetViewport->RemoveViewportWidgetContent(RootWidget.ToSharedRef());
		}
		RootWidget.Reset();
	}
	RootViewport.Reset();
}

void AIronReignPlayerController::HandleQuitRequested()
{
	// Ends PIE in the editor and quits a packaged game.
	UKismetSystemLibrary::QuitGame(this, this, EQuitPreference::Quit, false);
}

// -------------------------------------------------------------------------------------------------
// 3D campaign map lifetime and graphics options
// -------------------------------------------------------------------------------------------------

void AIronReignPlayerController::UpdateWorldPresentation(float DeltaSeconds)
{
	const TSharedPtr<FIronSession> IronSession = CampaignSession.Pin();
	UWorld* GameWorld = GetWorld();
	if (!IronSession.IsValid() || GameWorld == nullptr)
	{
		return;
	}

	const int32 Serial = IronSession->GetCampaignSerial();
	// HasGame first: Uses3DMap loads the key assets on its first positive check.
	const bool bWantMap = IronSession->HasGame() && IronSession->Uses3DMap();
	AIronWorldMap3D* Map = WorldMap.Get();

	if (Map != nullptr && (!bWantMap || Map->HasFailed()))
	{
		// Campaign over (title screen), 2D chosen in the settings, or a scene that could not be built: back to Slate.
		// A failed map is kept destroyed for this campaign (FailedMapSpawnSerial) so it is not rebuilt in a loop.
		if (Map->HasFailed())
		{
			FailedMapSpawnSerial = WorldMapCampaignSerial;
			UE_LOG(LogIronReign, Warning, TEXT("The 3D campaign map could not be built; using the 2D map for this campaign."));
		}
		DestroyWorldMap();
		Map = nullptr;
	}

	if (Map != nullptr && Serial != WorldMapCampaignSerial)
	{
		// Another campaign (new game or load). The same scenario keeps the scene, whose terrain build is the expensive
		// part, and resyncs it (cities, owners, armies, season, camera on the player's capital). Another scenario
		// rebuilds it: the tree clearings around the cities are cut once, when the map initializes.
		if (IronSession->State().ScenarioKey == WorldMapScenarioKey)
		{
			WorldMapCampaignSerial = Serial;
			Map->RefreshFromState();
			Map->ResetCameraToPlayer();
		}
		else
		{
			DestroyWorldMap();
			Map = nullptr;
		}
	}

	if (Map == nullptr && bWantMap && FailedMapSpawnSerial != Serial)
	{
		Map = AIronWorldMap3D::SpawnMap(GameWorld, IronSession, IronSession->GetGraphicsQuality());
		if (Map != nullptr)
		{
			WorldMap = Map;
			WorldMapCampaignSerial = Serial;
			WorldMapScenarioKey = IronSession->State().ScenarioKey;
			// The new map's environment gets the options below.
			AppliedGraphicsRevision = -1;
			UE_LOG(LogIronReign, Log, TEXT("Spawned the 3D campaign map (quality %d); the 2D map shows until its scene is ready."), IronSession->GetGraphicsQuality());
		}
		else
		{
			FailedMapSpawnSerial = Serial;
			UE_LOG(LogIronReign, Warning, TEXT("The 3D campaign map could not be spawned; using the 2D map for this campaign."));
		}
	}

	bool bApply = AppliedGraphicsRevision != IronSession->GetGraphicsRevision();
	if (!bApply && !GraphicsEnvironment.IsValid())
	{
		// No 3D environment received the options yet (2D so far, or a battle board spawned by the battle screen).
		GraphicsPollSeconds += DeltaSeconds;
		if (GraphicsPollSeconds >= IronPlayerControllerDetail::GraphicsPollIntervalSeconds)
		{
			GraphicsPollSeconds = 0.0f;
			bApply = Map != nullptr || AIronBattleBoard3D::FindBoard(GameWorld) != nullptr;
		}
	}
	if (bApply)
	{
		ApplyGraphicsSettings();
	}
}

void AIronReignPlayerController::DestroyWorldMap()
{
	AIronWorldMap3D* Map = WorldMap.Get();
	WorldMap.Reset();
	WorldMapCampaignSerial = -1;
	WorldMapScenarioKey.clear();
	if (Map == nullptr)
	{
		return;
	}
	// The map's EndPlay hides it (world rendering stays on only for an active battle board), hands the view target back
	// to this controller when its camera rig held it, and destroys its terrain and camera rig; the shared environment
	// stays.
	Map->Destroy();
}

void AIronReignPlayerController::ApplyGraphicsSettings()
{
	const TSharedPtr<FIronSession> IronSession = CampaignSession.Pin();
	if (!IronSession.IsValid())
	{
		return;
	}
	AppliedGraphicsRevision = IronSession->GetGraphicsRevision();
	GraphicsPollSeconds = 0.0f;
	const int32 Quality = IronSession->GetGraphicsQuality();

	AIronEnvironment* Environment = nullptr;
	if (AIronWorldMap3D* Map = WorldMap.Get())
	{
		Map->SetQuality(Quality);
		Environment = Map->GetEnvironment();
	}
	if (AIronBattleBoard3D* Board = AIronBattleBoard3D::FindBoard(GetWorld()))
	{
		// The board's camera follows the environment's tilt-shift strength by itself every frame.
		Board->SetQuality(Quality);
		if (Environment == nullptr)
		{
			Environment = Board->GetEnvironment();
		}
	}
	GraphicsEnvironment = Environment;
	if (Environment != nullptr)
	{
		// One environment per world, shared by the map and the board (both forwarded the quality to it above): the
		// look and the post-process options stick for both scenes.
		IronSession->ApplyEnvironmentOptions(*Environment);
	}
}
