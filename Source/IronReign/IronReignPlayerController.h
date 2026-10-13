#pragma once

#include "CoreMinimal.h"
#include "GameFramework/PlayerController.h"
#include "IronReignPlayerController.generated.h"

class SIronRoot;
class UGameViewportClient;

/**
 * Local UI controller: shows the mouse cursor, adds SIronRoot to the game viewport with UI-only input and disables
 * world rendering (the Entry map has nothing to draw). The widget is removed again in EndPlay.
 */
UCLASS()
class IRONREIGN_API AIronReignPlayerController : public APlayerController
{
	GENERATED_BODY()

public:
	AIronReignPlayerController();

protected:
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
	void HandleQuitRequested();
	void RemoveRootWidget();

	TSharedPtr<SIronRoot> RootWidget;
	TWeakObjectPtr<UGameViewportClient> RootViewport;
};
