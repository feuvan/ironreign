#include "UI/SIronSaveLoadDialog.h"

#include "Sim/IronLocale.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronRoot.h"

#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronSaveLoadDetail
{
	FText SlotName(int32 SlotIndex)
	{
		if (SlotIndex == 0)
		{
			return IronUI::Loc("ui.saveload.autosave", "Autosave");
		}
		return IronUI::LocF("ui.saveload.slot", "Slot {slot}", {{"slot", IronSim::ToText(SlotIndex)}});
	}
}

void SIronSaveLoadDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	bSaveMode = InArgs._SaveMode;

	const bool bShowSaveNotice = bSaveMode && !CanSave();
	const FText Title = bSaveMode ? IronUI::Loc("ui.saveload.saveTitle", "Save Campaign") : IronUI::Loc("ui.saveload.loadTitle", "Load Campaign");

	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(780.0f)
		[
			IronStyle::MakePanel(
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					IronStyle::MakeHeader(Title, 28.0f)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 10.0f, 0.0f, 0.0f))
				[
					SNew(STextBlock)
					.Visibility(bShowSaveNotice ? EVisibility::Visible : EVisibility::Collapsed)
					.Text(IronUI::Loc("ui.saveload.onlyPlanning", "You can only save during the planning phase, before ending the turn."))
					.Font(IronStyle::BodyBold(15.0f))
					.ColorAndOpacity(IronStyle::Danger())
					.AutoWrapText(true)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 14.0f, 0.0f, 16.0f))
				[
					SNew(SBox)
					.MaxDesiredHeight(640.0f)
					[
						SNew(SScrollBox)
						+ SScrollBox::Slot()
						[
							SAssignNew(SlotList, SVerticalBox)
						]
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Right)
				[
					IronStyle::MakeButton(IronUI::Loc("ui.common.close", "Close"), FOnClicked::CreateSP(this, &SIronSaveLoadDialog::OnClose), true, FString(), 150.0f)
				],
				false,
				FMargin(34.0f, 28.0f))
		]
	];

	RebuildSlots();
}

bool SIronSaveLoadDialog::CanSave() const
{
	return Session.IsValid() && Session->HasGame() && Session->Game().IsPlanning();
}

void SIronSaveLoadDialog::RebuildSlots()
{
	if (!SlotList.IsValid())
	{
		return;
	}
	SlotList->ClearChildren();
	SlotEntries = Session.IsValid() ? Session->ListSaveSlots() : TArray<FIronSaveSlot>();
	const bool bCanSave = CanSave();

	for (const FIronSaveSlot& Entry : SlotEntries)
	{
		const bool bAutosave = Entry.Slot == 0;
		const bool bEnabled = bSaveMode ? (bCanSave && !bAutosave) : Entry.bUsed;
		const FText Detail = Entry.bUsed ? Entry.Summary : IronUI::Loc("ui.saveload.empty", "Empty");
		const FText Stamp = Entry.bUsed ? FText::FromString(Entry.Timestamp.ToString(TEXT("%Y-%m-%d  %H:%M"))) : FText::GetEmpty();

		SlotList->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			SNew(SButton)
			.ButtonStyle(&IronStyle::RowButton())
			.ContentPadding(FMargin(0.0f))
			.IsEnabled(bEnabled)
			.OnClicked(FOnClicked::CreateSP(this, &SIronSaveLoadDialog::OnSlotClicked, Entry.Slot))
			[
				SNew(SBorder)
				.BorderImage(IronStyle::WhiteBrush())
				.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(Entry.bUsed ? 0.45f : 0.22f))
				.Padding(FMargin(16.0f, 12.0f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					[
						SNew(SBox)
						.WidthOverride(150.0f)
						[
							SNew(STextBlock)
							.Text(IronSaveLoadDetail::SlotName(Entry.Slot))
							.Font(IronStyle::BodyBold(17.0f))
							.ColorAndOpacity(IronStyle::Lacquer())
						]
					]
					+ SHorizontalBox::Slot()
					.FillWidth(1.0f)
					.VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Text(Detail)
						.Font(IronStyle::Body(16.0f))
						.ColorAndOpacity(Entry.bUsed ? IronStyle::Ink() : IronStyle::InkSoft())
						.AutoWrapText(true)
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
					[
						SNew(STextBlock)
						.Text(Stamp)
						.Font(IronStyle::Body(14.0f))
						.ColorAndOpacity(IronStyle::InkSoft())
					]
				]
			]
		];
	}
}

FReply SIronSaveLoadDialog::OnSlotClicked(int32 SlotIndex)
{
	const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin();
	if (!PinnedRoot.IsValid() || !Session.IsValid())
	{
		return FReply::Handled();
	}

	const FIronSaveSlot* Entry = SlotEntries.FindByPredicate([SlotIndex](const FIronSaveSlot& Candidate)
	{
		return Candidate.Slot == SlotIndex;
	});
	const bool bUsed = Entry != nullptr && Entry->bUsed;
	// Keeps this dialog alive while a confirmation is open on top of it.
	const TSharedRef<SIronSaveLoadDialog> Self = SharedThis(this);

	if (bSaveMode)
	{
		if (bUsed)
		{
			PinnedRoot->ShowConfirm(
				IronUI::Loc("ui.saveload.overwriteTitle", "Overwrite Save"),
				IronUI::LocF("ui.saveload.overwriteText", "Replace the campaign saved in slot {slot}?", {{"slot", IronSim::ToText(SlotIndex)}}),
				[Self, SlotIndex](bool bConfirmed)
				{
					if (bConfirmed)
					{
						Self->SaveTo(SlotIndex);
					}
				});
		}
		else
		{
			SaveTo(SlotIndex);
		}
	}
	else if (Session->HasGame())
	{
		PinnedRoot->ShowConfirm(
			IronUI::Loc("ui.saveload.loadConfirmTitle", "Load Campaign"),
			IronUI::Loc("ui.saveload.loadConfirmText", "Load this campaign? Progress since your last save will be lost."),
			[Self, SlotIndex](bool bConfirmed)
			{
				if (bConfirmed)
				{
					Self->LoadFrom(SlotIndex);
				}
			});
	}
	else
	{
		LoadFrom(SlotIndex);
	}
	return FReply::Handled();
}

void SIronSaveLoadDialog::SaveTo(int32 SlotIndex)
{
	const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin();
	if (!PinnedRoot.IsValid() || !Session.IsValid())
	{
		return;
	}
	FText Error;
	if (Session->SaveToSlot(SlotIndex, Error))
	{
		// This dialog is the top modal here (any confirmation popped itself before calling back).
		PinnedRoot->PopModal();
		PinnedRoot->ShowMessage(
			IronUI::Loc("ui.saveload.savedTitle", "Campaign Saved"),
			IronUI::LocF("ui.saveload.savedText", "The campaign was saved to slot {slot}.", {{"slot", IronSim::ToText(SlotIndex)}}));
	}
	else
	{
		PinnedRoot->ShowMessage(IronUI::Loc("ui.saveload.saveFailed", "Save Failed"), Error);
	}
}

void SIronSaveLoadDialog::LoadFrom(int32 SlotIndex)
{
	const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin();
	if (!PinnedRoot.IsValid() || !Session.IsValid())
	{
		return;
	}
	FText Error;
	if (Session->LoadFromSlot(SlotIndex, Error))
	{
		PinnedRoot->ClearModals();
		PinnedRoot->ResetStrategy();
		PinnedRoot->ShowStrategy();
	}
	else
	{
		PinnedRoot->ShowMessage(IronUI::Loc("ui.saveload.loadFailedTitle", "Load Failed"), Error);
	}
}

FReply SIronSaveLoadDialog::OnClose()
{
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->PopModal();
	}
	return FReply::Handled();
}
