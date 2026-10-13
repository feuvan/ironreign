#pragma once

#include "CoreMinimal.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;

/**
 * Modal "Factions" screen: every living faction with ruler portrait, banner, cities, officers, troops and its
 * trust / alliance / truce with the player.
 */
class IRONREIGN_API SIronFactionsPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronFactionsPanel) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TSharedRef<SWidget> BuildFactionRow(int32 Faction);
	FReply HandleClose();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
};
