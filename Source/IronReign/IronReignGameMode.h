#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "IronReignGameMode.generated.h"

class APlayerController;

/**
 * Iron Reign is pure Slate: no pawn, no HUD. The player controller puts SIronRoot into the game viewport
 * (see AIronReignPlayerController) and the campaign lives in UIronReignWorldStateSubsystem.
 */
UCLASS()
class IRONREIGN_API AIronReignGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	AIronReignGameMode();

	/** Players are never (re)spawned as pawns. */
	virtual bool PlayerCanRestart_Implementation(APlayerController* Player) override;
};
