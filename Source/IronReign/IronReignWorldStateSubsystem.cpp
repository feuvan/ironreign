#include "IronReignWorldStateSubsystem.h"

#include "IronReignLog.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"

void UIronReignWorldStateSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);

	Session = MakeShared<FIronSession>();
	Session->Initialize();
}

void UIronReignWorldStateSubsystem::Deinitialize()
{
	if (Session.IsValid())
	{
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
