#include "UI/SIronTitleScreen.h"

#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronRoot.h"

#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace IronTitleDetail
{
	const TCHAR* const BackgroundArt = TEXT("Art/UI/Title_Background.png");
	const TCHAR* const LogoArt = TEXT("Art/UI/Title_Logo.png");
	constexpr float MenuButtonWidth = 320.0f;
}

void SIronTitleScreen::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;

	FIronAssets& Assets = FIronAssets::Get();

	// Painted background scaled to cover the viewport; dark Night fill when the art is missing.
	TSharedRef<SWidget> Background =
		SNew(SImage)
		.Image(IronStyle::WhiteBrush())
		.ColorAndOpacity(IronStyle::Night());
	if (Assets.Exists(IronTitleDetail::BackgroundArt))
	{
		Background =
			SNew(SScaleBox)
			.Stretch(EStretch::ScaleToFill)
			[
				SNew(SImage)
				.Image(Assets.Image(IronTitleDetail::BackgroundArt))
			];
	}

	TSharedRef<SWidget> Logo =
		SNew(STextBlock)
		.Text(IronUI::Loc("ui.title.gameName", "Iron Reign"))
		.Font(IronStyle::Heading(96.0f))
		.ColorAndOpacity(IronStyle::Gold())
		.ShadowOffset(FVector2D(3.0f, 3.0f))
		.ShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.8f));
	if (Assets.Exists(IronTitleDetail::LogoArt))
	{
		Logo =
			SNew(SBox)
			.WidthOverride(960.0f)
			.HeightOverride(320.0f)
			[
				SNew(SImage)
				.Image(Assets.Image(IronTitleDetail::LogoArt))
			];
	}

	ChildSlot
	[
		SNew(SOverlay)
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(IronStyle::Night())
			.Padding(FMargin(0.0f))
			[
				Background
			]
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.0f, 48.0f, 0.0f, 0.0f))
		[
			Logo
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Center)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 150.0f))
		[
			MakeMenu()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Right)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(0.0f, 0.0f, 40.0f, 30.0f))
		[
			MakeLanguagePicker()
		]
		+ SOverlay::Slot()
		.HAlign(HAlign_Left)
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(40.0f, 0.0f, 0.0f, 36.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.title.tagline", "A chronicle of the Nine Provinces"))
			.Font(IronStyle::Body(16.0f))
			.ColorAndOpacity(IronStyle::TextLight())
			.ShadowOffset(FVector2D(1.0f, 1.0f))
			.ShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.85f))
		]
	];
}

TSharedRef<SWidget> SIronTitleScreen::MakeMenu()
{
	const bool bHasSaves = Session.IsValid() && Session->HasAnySave();
	const float Width = IronTitleDetail::MenuButtonWidth;

	TSharedRef<SButton> LoadButton = IronStyle::MakeButton(IronUI::Loc("ui.title.loadGame", "Load Game"), FOnClicked::CreateSP(this, &SIronTitleScreen::OnLoadGame), bHasSaves, TEXT("Load"), Width);
	if (!bHasSaves)
	{
		LoadButton->SetToolTipText(IronUI::Loc("ui.title.noSaves", "No saved campaigns yet."));
	}

	return IronStyle::MakePanel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.title.newGame", "New Game"), FOnClicked::CreateSP(this, &SIronTitleScreen::OnNewGame), true, TEXT("March"), Width)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f))
		[
			LoadButton
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.title.settings", "Settings"), FOnClicked::CreateSP(this, &SIronTitleScreen::OnSettings), true, TEXT("Settings"), Width)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.title.quit", "Quit"), FOnClicked::CreateSP(this, &SIronTitleScreen::OnQuit), true, FString(), Width)
		],
		true,
		FMargin(40.0f, 30.0f));
}

TSharedRef<SWidget> SIronTitleScreen::MakeLanguagePicker()
{
	const FString Current = Session.IsValid() ? Session->GetCulture() : FString(TEXT("en"));
	TSharedRef<SHorizontalBox> Choices = SNew(SHorizontalBox);
	for (const FString& CultureName : FIronSession::SupportedCultures())
	{
		const bool bActive = CultureName.Equals(Current, ESearchCase::IgnoreCase);
		Choices->AddSlot()
			.AutoWidth()
			.Padding(FMargin(3.0f, 0.0f))
			[
				SNew(SButton)
				.ButtonStyle(&IronStyle::Tab(bActive))
				.OnClicked(IronStyle::WithClickSound(FOnClicked::CreateSP(this, &SIronTitleScreen::OnLanguage, CultureName)))
				.HAlign(HAlign_Center)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(FIronSession::CultureDisplayName(CultureName))
					.Font(IronStyle::FontForCulture(CultureName, IronStyle::EFont::BodyBold, 15.0f))
					.ColorAndOpacity(IronStyle::TextLight())
				]
			];
	}

	return IronStyle::MakePanel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(4.0f, 0.0f, 0.0f, 8.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.title.language", "Language"))
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(IronStyle::Gold())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			Choices
		],
		true,
		FMargin(20.0f, 14.0f));
}

FReply SIronTitleScreen::OnNewGame()
{
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->ShowNewGame();
	}
	return FReply::Handled();
}

FReply SIronTitleScreen::OnLoadGame()
{
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->ShowSaveLoad(false);
	}
	return FReply::Handled();
}

FReply SIronTitleScreen::OnSettings()
{
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->ShowSettings();
	}
	return FReply::Handled();
}

FReply SIronTitleScreen::OnQuit()
{
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->RequestQuit();
	}
	return FReply::Handled();
}

FReply SIronTitleScreen::OnLanguage(FString CultureName)
{
	// The root rebuilds this screen when the culture changes; nothing here may touch members afterwards.
	if (Session.IsValid())
	{
		Session->SetCulture(CultureName);
	}
	return FReply::Handled();
}
