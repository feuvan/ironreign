#include "IronReignPlayerController.h"

#include "IronReignLog.h"
#include "IronReignWorldStateSubsystem.h"
#include "UI/IronSession.h"
#include "UI/SIronRoot.h"

#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Kismet/KismetSystemLibrary.h"

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

	// The game is drawn entirely by Slate; skip rendering the (empty) world.
	TargetViewport->bDisableWorldRendering = true;

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
	Super::EndPlay(EndPlayReason);
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
