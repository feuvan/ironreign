#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "UI/IronSession.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class SIronRoot;
class SVerticalBox;

/**
 * Modal list of FIronSession::SaveSlotCount save slots (slot 0 = autosave) with summary and timestamp.
 * Save mode: only during the planning phase, never into the autosave slot, confirms overwrites.
 * Load mode: confirms when a campaign is running, then resets and shows the strategy screen.
 */
class SIronSaveLoadDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronSaveLoadDialog)
		: _SaveMode(false)
		{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		/** true = save dialog, false = load dialog. */
		SLATE_ARGUMENT(bool, SaveMode)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	bool CanSave() const;
	void RebuildSlots();
	FReply OnSlotClicked(int32 SlotIndex);
	FReply OnClose();
	void SaveTo(int32 SlotIndex);
	void LoadFrom(int32 SlotIndex);

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	bool bSaveMode = false;
	TArray<FIronSaveSlot> SlotEntries;
	TSharedPtr<SVerticalBox> SlotList;
};
