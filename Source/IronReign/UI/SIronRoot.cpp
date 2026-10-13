#include "UI/SIronRoot.h"

#include "IronReignLog.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronBattleScreen.h"
#include "UI/SIronNewGameScreen.h"
#include "UI/SIronSaveLoadDialog.h"
#include "UI/SIronSettingsDialog.h"
#include "UI/SIronStrategyScreen.h"
#include "UI/SIronTitleScreen.h"

#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformMisc.h"
#include "InputCoreTypes.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace IronRootDetail
{
	/** Parchment dialog: header, body, right-aligned buttons. */
	TSharedRef<SWidget> MakeDialogFrame(const FText& Title, const TSharedRef<SWidget>& Body, const TSharedRef<SWidget>& Buttons, float Width)
	{
		return SNew(SBox)
			.WidthOverride(Width)
			[
				IronStyle::MakePanel(
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						IronStyle::MakeHeader(Title, 26.0f)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 16.0f, 0.0f, 22.0f))
					[
						Body
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Right)
					[
						Buttons
					],
					false,
					FMargin(36.0f, 30.0f))
			];
	}

	TSharedRef<SWidget> MakeMessageText(const FText& Message)
	{
		return SNew(STextBlock)
			.Text(Message)
			.Font(IronStyle::Body(17.0f))
			.ColorAndOpacity(IronStyle::Ink())
			.AutoWrapText(true);
	}
}

void SIronRoot::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	QuitRequested = InArgs._OnQuitRequested;

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SAssignNew(ScreenHost, SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(IronStyle::Night())
			.Padding(FMargin(0.0f))
		]
		+ SOverlay::Slot()
		[
			SAssignNew(ModalLayer, SOverlay)
			.Visibility(EVisibility::SelfHitTestInvisible)
		]
	];

	if (Session.IsValid())
	{
		Session->OnCultureChanged.AddSP(this, &SIronRoot::HandleCultureChanged);
	}
	ShowTitle();
}

TSharedRef<SWidget> SIronRoot::MakeTitleScreen()
{
	return SNew(SIronTitleScreen)
		.Session(Session)
		.Root(TWeakPtr<SIronRoot>(SharedThis(this)));
}

TSharedRef<SWidget> SIronRoot::MakeNewGameScreen()
{
	return SNew(SIronNewGameScreen)
		.Session(Session)
		.Root(TWeakPtr<SIronRoot>(SharedThis(this)));
}

void SIronRoot::ShowTitle()
{
	ClearModals();
	CurrentScreen = EScreen::Title;
	SetScreen(MakeTitleScreen());
	FIronAudio::Get().PlayMusic(TEXT("Title"));
}

void SIronRoot::ShowNewGame()
{
	ClearModals();
	CurrentScreen = EScreen::NewGame;
	SetScreen(MakeNewGameScreen());
	FIronAudio::Get().PlayMusic(TEXT("Title"));
}

void SIronRoot::ShowStrategy()
{
	if (!StrategyScreen.IsValid())
	{
		StrategyScreen = SNew(SIronStrategyScreen)
			.Session(Session)
			.Root(TWeakPtr<SIronRoot>(SharedThis(this)));
	}
	CurrentScreen = EScreen::Strategy;
	SetScreen(StrategyScreen.ToSharedRef());
	// Also when coming back from a battle (the strategy screen is cached, so this is the place that sees every return).
	FIronAudio::Get().PlayMusic(TEXT("Strategy"));
}

void SIronRoot::ResetStrategy()
{
	StrategyScreen.Reset();
}

void SIronRoot::ShowBattle(const IronSim::FBattleSetup& Setup, FOnIronBattleFinished OnFinished)
{
	// The battle prompt (Command / Delegate) that led here is no longer relevant.
	ClearModals();
	CurrentScreen = EScreen::Battle;
	SetScreen(
		SNew(SIronBattleScreen)
		.Session(Session)
		.Root(TWeakPtr<SIronRoot>(SharedThis(this)))
		.Setup(Setup)
		.OnFinished(OnFinished));
}

void SIronRoot::SetScreen(const TSharedRef<SWidget>& Screen)
{
	ScreenHost->SetContent(Screen);
	// Screens with keyboard handling (strategy, battle) get focus; unhandled keys such as Escape bubble up to the root.
	const bool bScreenFocused = !HasModal() && Screen->SupportsKeyboardFocus() && FSlateApplication::IsInitialized()
		&& FSlateApplication::Get().SetKeyboardFocus(Screen, EFocusCause::SetDirectly);
	if (!bScreenFocused)
	{
		FocusRoot();
	}
}

void SIronRoot::FocusRoot()
{
	if (FSlateApplication::IsInitialized())
	{
		FSlateApplication::Get().SetKeyboardFocus(SharedThis(this), EFocusCause::SetDirectly);
	}
}

void SIronRoot::HandleCultureChanged()
{
	// The strategy and battle screens relabel themselves; simple screens are rebuilt (modals stay open).
	switch (CurrentScreen)
	{
	case EScreen::Title:
		SetScreen(MakeTitleScreen());
		break;
	case EScreen::NewGame:
		SetScreen(MakeNewGameScreen());
		break;
	case EScreen::None:
	case EScreen::Strategy:
	case EScreen::Battle:
		break;
	}
}

// -------------------------------------------------------------------------------------------------
// Modals
// -------------------------------------------------------------------------------------------------

void SIronRoot::PushModal(const TSharedRef<SWidget>& Widget)
{
	PushModalInternal(Widget, true, nullptr);
}

void SIronRoot::PushModalWithEscape(const TSharedRef<SWidget>& Widget, TFunction<void()> OnEscape)
{
	PushModalInternal(Widget, false, MoveTemp(OnEscape));
}

void SIronRoot::PushModalInternal(const TSharedRef<SWidget>& Widget, bool bPopOnEscape, TFunction<void()> OnEscape)
{
	// The dim layer swallows every click so nothing underneath reacts while the modal is open.
	const TSharedRef<SWidget> Layer =
		SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(FLinearColor(0.0f, 0.0f, 0.0f, 0.55f))
		.Padding(FMargin(24.0f))
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Center)
		.OnMouseButtonDown_Lambda([](const FGeometry&, const FPointerEvent&) { return FReply::Handled(); })
		[
			Widget
		];

	ModalLayer->AddSlot()
	[
		Layer
	];
	ModalStack.Add(Layer);

	FModalInfo Info;
	Info.bPopOnEscape = bPopOnEscape;
	Info.OnEscape = MoveTemp(OnEscape);
	if (FSlateApplication::IsInitialized())
	{
		Info.PreviousFocus = FSlateApplication::Get().GetKeyboardFocusedWidget();
	}
	ModalInfos.Add(MoveTemp(Info));
	// Keys go to the root while a modal is open (Escape handling, no shortcuts reaching the screen below).
	FocusRoot();
}

void SIronRoot::PopModal()
{
	if (ModalStack.Num() == 0)
	{
		return;
	}
	const int32 TopIndex = ModalStack.Num() - 1;
	const TSharedRef<SWidget> Layer = ModalStack[TopIndex];
	ModalStack.RemoveAt(TopIndex);
	TSharedPtr<SWidget> FocusToRestore;
	if (ModalInfos.IsValidIndex(TopIndex))
	{
		FocusToRestore = ModalInfos[TopIndex].PreviousFocus.Pin();
		ModalInfos.RemoveAt(TopIndex);
	}
	ModalLayer->RemoveSlot(Layer);

	const bool bRestored = FocusToRestore.IsValid() && FSlateApplication::IsInitialized()
		&& FSlateApplication::Get().SetKeyboardFocus(FocusToRestore, EFocusCause::SetDirectly);
	if (!bRestored)
	{
		FocusRoot();
	}
}

bool SIronRoot::HasModal() const
{
	return ModalStack.Num() > 0;
}

void SIronRoot::ClearModals()
{
	const bool bHadModals = ModalStack.Num() > 0;
	if (ModalLayer.IsValid())
	{
		ModalLayer->ClearChildren();
	}
	ModalStack.Reset();
	ModalInfos.Reset();
	if (bHadModals)
	{
		FocusRoot();
	}
}

void SIronRoot::ShowMessage(const FText& Title, const FText& Message, TFunction<void()> OnClose)
{
	const TWeakPtr<SIronRoot> WeakRoot = SharedThis(this);
	const TSharedRef<TFunction<void()>> CloseCallback = MakeShared<TFunction<void()>>(MoveTemp(OnClose));
	const TFunction<void()> Close = [WeakRoot, CloseCallback]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->PopModal();
		}
		if (*CloseCallback)
		{
			(*CloseCallback)();
		}
	};

	const TSharedRef<SWidget> Buttons = IronStyle::MakeButton(
		IronUI::Loc("ui.common.ok", "OK"),
		FOnClicked::CreateLambda([Close]()
		{
			Close();
			return FReply::Handled();
		}),
		true,
		FString(),
		140.0f);

	PushModalWithEscape(IronRootDetail::MakeDialogFrame(Title, IronRootDetail::MakeMessageText(Message), Buttons, 600.0f), Close);
}

void SIronRoot::ShowConfirm(const FText& Title, const FText& Message, TFunction<void(bool)> OnResult)
{
	const TWeakPtr<SIronRoot> WeakRoot = SharedThis(this);
	const TSharedRef<TFunction<void(bool)>> ResultCallback = MakeShared<TFunction<void(bool)>>(MoveTemp(OnResult));
	const TFunction<void(bool)> Finish = [WeakRoot, ResultCallback](bool bAccepted)
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->PopModal();
		}
		if (*ResultCallback)
		{
			(*ResultCallback)(bAccepted);
		}
	};

	const TSharedRef<SWidget> Buttons =
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(0.0f, 0.0f, 12.0f, 0.0f))
		[
			IronStyle::MakeButton(
				IronUI::Loc("ui.common.cancel", "Cancel"),
				FOnClicked::CreateLambda([Finish]()
				{
					FIronAudio::Get().PlaySfx(TEXT("Cancel"));
					Finish(false);
					return FReply::Handled();
				}),
				true,
				FString(),
				140.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			IronStyle::MakeButton(
				IronUI::Loc("ui.common.ok", "OK"),
				FOnClicked::CreateLambda([Finish]()
				{
					FIronAudio::Get().PlaySfx(TEXT("Confirm"));
					Finish(true);
					return FReply::Handled();
				}),
				true,
				FString(),
				140.0f)
		];

	PushModalWithEscape(
		IronRootDetail::MakeDialogFrame(Title, IronRootDetail::MakeMessageText(Message), Buttons, 600.0f),
		[Finish]()
		{
			Finish(false);
		});
}

void SIronRoot::ShowSaveLoad(bool bSave)
{
	PushModal(
		SNew(SIronSaveLoadDialog)
		.Session(Session)
		.Root(TWeakPtr<SIronRoot>(SharedThis(this)))
		.SaveMode(bSave));
}

void SIronRoot::ShowSettings()
{
	PushModal(
		SNew(SIronSettingsDialog)
		.Session(Session)
		.Root(TWeakPtr<SIronRoot>(SharedThis(this))));
}

void SIronRoot::ShowGameMenu()
{
	const TWeakPtr<SIronRoot> WeakRoot = SharedThis(this);
	const TWeakPtr<FIronSession> WeakSession = Session;
	const bool bCanSave = Session.IsValid() && Session->HasGame() && Session->Game().IsPlanning();
	const float ButtonWidth = 300.0f;

	const FOnClicked ResumeClicked = FOnClicked::CreateLambda([WeakRoot]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->PopModal();
		}
		return FReply::Handled();
	});
	const FOnClicked SaveClicked = FOnClicked::CreateLambda([WeakRoot]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->ShowSaveLoad(true);
		}
		return FReply::Handled();
	});
	const FOnClicked LoadClicked = FOnClicked::CreateLambda([WeakRoot]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->ShowSaveLoad(false);
		}
		return FReply::Handled();
	});
	const FOnClicked SettingsClicked = FOnClicked::CreateLambda([WeakRoot]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->ShowSettings();
		}
		return FReply::Handled();
	});
	const FOnClicked ToTitleClicked = FOnClicked::CreateLambda([WeakRoot, WeakSession]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->ShowConfirm(
				IronUI::Loc("ui.menu.toTitleTitle", "Return to Title"),
				IronUI::Loc("ui.menu.toTitleText", "Abandon the campaign and return to the title screen? Progress since your last save will be lost."),
				[WeakRoot, WeakSession](bool bConfirmed)
				{
					const TSharedPtr<SIronRoot> ConfirmRoot = WeakRoot.Pin();
					if (!bConfirmed || !ConfirmRoot.IsValid())
					{
						return;
					}
					if (const TSharedPtr<FIronSession> PinnedSession = WeakSession.Pin())
					{
						PinnedSession->EndGame();
					}
					ConfirmRoot->ResetStrategy();
					ConfirmRoot->ShowTitle();
				});
		}
		return FReply::Handled();
	});
	const FOnClicked QuitClicked = FOnClicked::CreateLambda([WeakRoot]()
	{
		if (const TSharedPtr<SIronRoot> PinnedRoot = WeakRoot.Pin())
		{
			PinnedRoot->ShowConfirm(
				IronUI::Loc("ui.menu.quitTitle", "Quit Game"),
				IronUI::Loc("ui.menu.quitText", "Quit Iron Reign? Progress since your last save will be lost."),
				[WeakRoot](bool bConfirmed)
				{
					const TSharedPtr<SIronRoot> ConfirmRoot = WeakRoot.Pin();
					if (bConfirmed && ConfirmRoot.IsValid())
					{
						ConfirmRoot->RequestQuit();
					}
				});
		}
		return FReply::Handled();
	});

	const TSharedRef<SWidget> Menu =
		SNew(SBox)
		.WidthOverride(420.0f)
		[
			IronStyle::MakePanel(
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 0.0f, 0.0f, 14.0f))
				[
					IronStyle::MakeHeader(IronUI::Loc("ui.menu.title", "Campaign Menu"), 28.0f, true)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 5.0f))
				[
					IronStyle::MakeButton(IronUI::Loc("ui.menu.resume", "Resume"), ResumeClicked, true, FString(), ButtonWidth)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 5.0f))
				[
					IronStyle::MakeButton(IronUI::Loc("ui.menu.save", "Save Game"), SaveClicked, bCanSave, TEXT("Save"), ButtonWidth)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 5.0f))
				[
					IronStyle::MakeButton(IronUI::Loc("ui.menu.load", "Load Game"), LoadClicked, true, TEXT("Load"), ButtonWidth)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 5.0f))
				[
					IronStyle::MakeButton(IronUI::Loc("ui.menu.settings", "Settings"), SettingsClicked, true, TEXT("Settings"), ButtonWidth)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 5.0f))
				[
					IronStyle::MakeButton(IronUI::Loc("ui.menu.toTitle", "Return to Title"), ToTitleClicked, true, FString(), ButtonWidth)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 5.0f))
				[
					IronStyle::MakeButton(IronUI::Loc("ui.menu.quit", "Quit Game"), QuitClicked, true, FString(), ButtonWidth)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 10.0f, 0.0f, 0.0f))
				[
					SNew(STextBlock)
					.Visibility(bCanSave ? EVisibility::Collapsed : EVisibility::Visible)
					.Text(IronUI::Loc("ui.menu.saveHint", "Saving is possible during the planning phase."))
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(IronStyle::PaperDark())
				],
				true,
				FMargin(34.0f, 28.0f))
		];

	PushModal(Menu);
}

void SIronRoot::RequestQuit()
{
	if (!QuitRequested.ExecuteIfBound())
	{
		FPlatformMisc::RequestExit(false);
	}
}

// -------------------------------------------------------------------------------------------------
// Input
// -------------------------------------------------------------------------------------------------

FReply SIronRoot::OnKeyDown(const FGeometry& /*MyGeometry*/, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey() != EKeys::Escape)
	{
		return FReply::Unhandled();
	}

	if (HasModal())
	{
		const int32 TopIndex = ModalStack.Num() - 1;
		if (ModalInfos.IsValidIndex(TopIndex) && !ModalInfos[TopIndex].bPopOnEscape)
		{
			// Copy first: the handler usually pops the modal, which destroys the stored function.
			const TFunction<void()> Handler = ModalInfos[TopIndex].OnEscape;
			if (Handler)
			{
				FIronAudio::Get().PlaySfx(TEXT("Cancel"));
				Handler();
			}
		}
		else
		{
			FIronAudio::Get().PlaySfx(TEXT("Cancel"));
			PopModal();
		}
		return FReply::Handled();
	}

	switch (CurrentScreen)
	{
	case EScreen::NewGame:
		ShowTitle();
		return FReply::Handled();
	case EScreen::Strategy:
		if (Session.IsValid() && Session->HasGame())
		{
			ShowGameMenu();
			return FReply::Handled();
		}
		break;
	case EScreen::None:
	case EScreen::Title:
	case EScreen::Battle:
		break;
	}
	return FReply::Unhandled();
}
