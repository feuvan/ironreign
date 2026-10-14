#include "IronReignWorldStateSubsystem.h"

#include "IronReignLog.h"
#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"

void UIronReignWorldStateSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	Session = MakeShared<FIronSession>();
	// The 3D scenes (strategy map, battle board) live in this world; the screens reach them through the session.
	Session->SetPresentationWorld(GetWorld());
	Session->Initialize();
}

void UIronReignWorldStateSubsystem::Deinitialize()
{
	if (Session.IsValid())
	{
		// Normally done by AIronReignPlayerController::EndPlay; repeated here (idempotent) so no sound object
		// outlives the world, e.g. when the world is torn down without its actors ending play.
		FIronAudio::Get().Shutdown();
		Session->SetPresentationWorld(nullptr);
		IronStyle::SetSession(nullptr);
		Session.Reset();
		// Styles reference textures owned by FIronAssets: clear the styles first, then release the textures.
		IronStyle::Shutdown();
		FIronAssets::Get().Reset();
	}
	Super::Deinitialize();
}

bool UIronReignWorldStateSubsystem::DoesSupportWorldType(const EWorldType::Type WorldType) const
{
	return WorldType == EWorldType::Game || WorldType == EWorldType::PIE;
}

void UIronReignWorldStateSubsystem::AdvanceDays(const int32 Days)
{
	if (Days <= 0)
	{
		return;
	}

	CurrentDay += Days;
	OnWorldDayAdvanced.Broadcast(CurrentDay);
}
