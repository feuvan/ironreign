#include "IronReignWorldStateSubsystem.h"

void UIronReignWorldStateSubsystem::AdvanceDays(const int32 Days)
{
	if (Days <= 0)
	{
		return;
	}

	CurrentDay += Days;
	OnWorldDayAdvanced.Broadcast(CurrentDay);
}
