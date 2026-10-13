#include "IronReignGameMode.h"

#include "IronReignPlayerController.h"

AIronReignGameMode::AIronReignGameMode()
{
	PrimaryActorTick.bCanEverTick = false;
	DefaultPawnClass = nullptr;
	HUDClass = nullptr;
	PlayerControllerClass = AIronReignPlayerController::StaticClass();
}

bool AIronReignGameMode::PlayerCanRestart_Implementation(APlayerController* /*Player*/)
{
	return false;
}
