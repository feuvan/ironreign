#include "UI/SIronNewGameScreen.h"

#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronRoot.h"

#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScaleBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SNullWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace IronNewGameDetail
{
	constexpr int32 FactionColumns = 3;
	constexpr float PortraitHeight = 150.0f;
}

void SIronNewGameScreen::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	if (Session.IsValid())
	{
		Scenarios = Session->FindScenarios();
	}
	SelectedScenario = Scenarios.Num() > 0 ? 0 : INDEX_NONE;
	SelectedFaction = INDEX_NONE;

	FIronAssets& Assets = FIronAssets::Get();
	const FString BackgroundArt = TEXT("Art/UI/Title_Background.png");
	TSharedRef<SWidget> Background = SNullWidget::NullWidget;
	if (Assets.Exists(BackgroundArt))
	{
		Background =
			SNew(SScaleBox)
			.Stretch(EStretch::ScaleToFill)
			[
				SNew(SImage)
				.Image(Assets.Image(BackgroundArt))
			];
	}

	const TSharedRef<SWidget> ScenarioColumn =
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.newgame.scenario", "Scenario"), 24.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(0.45f)
		.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
		[
			SAssignNew(ScenarioList, SScrollBox)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 12.0f, 0.0f, 8.0f))
		[
			IronStyle::MakeDivider(10.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(0.55f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				SNew(STextBlock)
				.Text(this, &SIronNewGameScreen::DescriptionText)
				.Font(IronStyle::Body(16.0f))
				.ColorAndOpacity(IronStyle::Ink())
				.AutoWrapText(true)
			]
		];

	const TSharedRef<SWidget> FactionColumn =
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.newgame.faction", "Choose Your Faction"), 24.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				SAssignNew(FactionHost, SBox)
			]
		];

	const TSharedRef<SWidget> BottomBar = IronStyle::MakePanel(
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			SAssignNew(DifficultyHost, SBox)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(16.0f, 0.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.common.back", "Back"), FOnClicked::CreateSP(this, &SIronNewGameScreen::OnBack), true, FString(), 160.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.newgame.start", "Begin Campaign"), FOnClicked::CreateSP(this, &SIronNewGameScreen::OnStart), TAttribute<bool>::CreateLambda([this]() { return CanStart(); }), TEXT("March"), 240.0f)
		],
		true,
		FMargin(24.0f, 14.0f));

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
		[
			SNew(SImage)
			.Image(IronStyle::WhiteBrush())
			.ColorAndOpacity(IronStyle::Night().CopyWithNewOpacity(0.72f))
		]
		+ SOverlay::Slot()
		.Padding(FMargin(48.0f, 32.0f, 48.0f, 32.0f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 0.0f, 0.0f, 18.0f))
			[
				IronStyle::MakeHeader(IronUI::Loc("ui.newgame.title", "New Campaign"), 40.0f, true)
			]
			+ SVerticalBox::Slot()
			.FillHeight(1.0f)
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(460.0f)
					[
						IronStyle::MakePanel(ScenarioColumn, false, FMargin(26.0f, 24.0f))
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				.Padding(FMargin(24.0f, 0.0f, 0.0f, 0.0f))
				[
					IronStyle::MakePanel(FactionColumn, false, FMargin(26.0f, 24.0f))
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 18.0f, 0.0f, 0.0f))
			[
				BottomBar
			]
		]
	];

	RebuildScenarioList();
	RebuildFactionGrid();
	RebuildDifficulty();
}

const FIronScenarioEntry* SIronNewGameScreen::SelectedEntry() const
{
	return Scenarios.IsValidIndex(SelectedScenario) ? &Scenarios[SelectedScenario] : nullptr;
}

bool SIronNewGameScreen::CanStart() const
{
	const FIronScenarioEntry* Entry = SelectedEntry();
	return Entry != nullptr && SelectedFaction >= 0 && SelectedFaction < static_cast<int32>(Entry->Info.Factions.size());
}

FText SIronNewGameScreen::DescriptionText() const
{
	const FIronScenarioEntry* Entry = SelectedEntry();
	if (Entry == nullptr)
	{
		return IronUI::Loc("ui.newgame.noScenarios", "No scenarios were found in Content/Data/Scenarios.");
	}
	const FText StartYear = IronUI::LocF("ui.newgame.startYear", "The chronicle begins in the year {year}.", {{"year", IronSim::ToText(Entry->Info.StartYear)}});
	return FText::FromString(StartYear.ToString() + TEXT("\n\n") + IronUI::ToFString(Entry->Info.Description));
}

void SIronNewGameScreen::RebuildScenarioList()
{
	if (!ScenarioList.IsValid())
	{
		return;
	}
	ScenarioList->ClearChildren();
	if (Scenarios.Num() == 0)
	{
		ScenarioList->AddSlot()
		[
			IronStyle::MakeLabel(IronUI::Loc("ui.newgame.noScenariosShort", "No scenarios available."), 16.0f, IronStyle::InkSoft())
		];
		return;
	}

	for (int32 Index = 0; Index < Scenarios.Num(); ++Index)
	{
		const FIronScenarioEntry& Entry = Scenarios[Index];
		ScenarioList->AddSlot()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			SNew(SButton)
			.ButtonStyle(&IronStyle::RowButton())
			.ContentPadding(FMargin(0.0f))
			.OnClicked(FOnClicked::CreateSP(this, &SIronNewGameScreen::OnScenarioClicked, Index))
			[
				SNew(SBorder)
				.BorderImage(IronStyle::WhiteBrush())
				.BorderBackgroundColor_Lambda([this, Index]() -> FSlateColor
				{
					return SelectedScenario == Index ? IronStyle::Gold().CopyWithNewOpacity(0.55f) : IronStyle::PaperDark().CopyWithNewOpacity(0.35f);
				})
				.Padding(FMargin(14.0f, 10.0f))
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(IronUI::ToText(Entry.Info.Name))
						.Font(IronStyle::Heading(21.0f))
						.ColorAndOpacity(IronStyle::Ink())
						.AutoWrapText(true)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 2.0f, 0.0f, 0.0f))
					[
						SNew(STextBlock)
						.Text(IronUI::LocF("ui.newgame.scenarioFactions", "Year {year} - {count} factions", {{"year", IronSim::ToText(Entry.Info.StartYear)}, {"count", IronSim::ToText(static_cast<int>(Entry.Info.Factions.size()))}}))
						.Font(IronStyle::Body(14.0f))
						.ColorAndOpacity(IronStyle::InkSoft())
					]
				]
			]
		];
	}
}

void SIronNewGameScreen::RebuildFactionGrid()
{
	if (!FactionHost.IsValid())
	{
		return;
	}
	const FIronScenarioEntry* Entry = SelectedEntry();
	if (Entry == nullptr || Entry->Info.Factions.empty())
	{
		FactionHost->SetContent(IronStyle::MakeLabel(IronUI::Loc("ui.newgame.pickScenario", "Choose a scenario to see its factions."), 16.0f, IronStyle::InkSoft()));
		return;
	}

	TSharedRef<SUniformGridPanel> Grid = SNew(SUniformGridPanel).SlotPadding(FMargin(8.0f));
	const int32 FactionCount = static_cast<int32>(Entry->Info.Factions.size());
	for (int32 FactionIndex = 0; FactionIndex < FactionCount; ++FactionIndex)
	{
		Grid->AddSlot(FactionIndex % IronNewGameDetail::FactionColumns, FactionIndex / IronNewGameDetail::FactionColumns)
		[
			MakeFactionCard(FactionIndex)
		];
	}
	FactionHost->SetContent(Grid);
}

TSharedRef<SWidget> SIronNewGameScreen::MakeFactionCard(int32 FactionIndex)
{
	const FIronScenarioEntry* Entry = SelectedEntry();
	if (Entry == nullptr || FactionIndex < 0 || FactionIndex >= static_cast<int32>(Entry->Info.Factions.size()))
	{
		return SNullWidget::NullWidget;
	}
	const IronSim::FScenarioInfo::FFactionInfo& Info = Entry->Info.Factions[static_cast<size_t>(FactionIndex)];
	const FLinearColor FactionTint = IronUI::ColorFromRGB(Info.Color);
	const FText Glyph = IronStyle::FactionGlyph(IronUI::ToFString(Info.Key), IronUI::ToFString(Info.Glyph));
	const FString PortraitId = Info.RulerPortrait.empty() ? FString(TEXT("unknown")) : IronUI::ToFString(Info.RulerPortrait);

	return SNew(SButton)
		.ButtonStyle(&IronStyle::RowButton())
		.ContentPadding(FMargin(0.0f))
		.OnClicked(FOnClicked::CreateSP(this, &SIronNewGameScreen::OnFactionClicked, FactionIndex))
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor_Lambda([this, FactionIndex]() -> FSlateColor
			{
				return SelectedFaction == FactionIndex ? IronStyle::Gold() : IronStyle::PaperDark();
			})
			.Padding(FMargin(3.0f))
			[
				SNew(SBorder)
				.BorderImage(IronStyle::WhiteBrush())
				.BorderBackgroundColor_Lambda([this, FactionIndex]() -> FSlateColor
				{
					return SelectedFaction == FactionIndex ? IronUI::ColorFromRGB(0xF6EDD8) : IronStyle::Paper();
				})
				.Padding(FMargin(12.0f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Top)
					[
						IronStyle::MakePortrait(PortraitId, IronNewGameDetail::PortraitHeight)
					]
					+ SHorizontalBox::Slot()
					.FillWidth(1.0f)
					.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot()
							.AutoWidth()
							.VAlign(VAlign_Top)
							[
								IronStyle::MakeBannerFor(FactionTint, Glyph, 64.0f)
							]
							+ SHorizontalBox::Slot()
							.FillWidth(1.0f)
							.VAlign(VAlign_Center)
							.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
							[
								SNew(STextBlock)
								.Text(IronUI::ToText(Info.Name))
								.Font(IronStyle::Heading(22.0f))
								.ColorAndOpacity(IronStyle::Lacquer())
								.AutoWrapText(true)
							]
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
						[
							SNew(STextBlock)
							.Text(IronUI::LocF("ui.newgame.ruler", "Ruler: {name}", {{"name", Info.RulerName}}))
							.Font(IronStyle::BodyBold(15.0f))
							.ColorAndOpacity(IronStyle::Ink())
							.AutoWrapText(true)
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
						[
							IronStyle::MakeLabel(IronUI::LocF("ui.newgame.cities", "Cities: {count}", {{"count", IronSim::ToText(Info.Cities)}}), 15.0f, IronStyle::InkSoft())
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							IronStyle::MakeLabel(IronUI::LocF("ui.newgame.officers", "Officers: {count}", {{"count", IronSim::ToText(Info.Officers)}}), 15.0f, IronStyle::InkSoft())
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							IronStyle::MakeLabel(IronUI::LocF("ui.newgame.troops", "Troops: {count}", {{"count", IronSim::ToText(Info.Troops)}}), 15.0f, IronStyle::InkSoft())
						]
					]
				]
			]
		];
}

void SIronNewGameScreen::RebuildDifficulty()
{
	if (DifficultyHost.IsValid())
	{
		DifficultyHost->SetContent(MakeDifficultyRow());
	}
}

FText SIronNewGameScreen::DifficultyHint() const
{
	switch (Difficulty)
	{
	case IronSim::EDifficulty::Easy:
		return IronUI::Loc("ui.newgame.easyHint", "Rival lords earn less gold and rarely attack.");
	case IronSim::EDifficulty::Normal:
		return IronUI::Loc("ui.newgame.normalHint", "The intended balance of the Nine Provinces.");
	case IronSim::EDifficulty::Hard:
		return IronUI::Loc("ui.newgame.hardHint", "Rival lords earn more gold and press every advantage.");
	}
	return FText::GetEmpty();
}

TSharedRef<SWidget> SIronNewGameScreen::MakeDifficultyRow()
{
	TSharedRef<SHorizontalBox> Choices = SNew(SHorizontalBox);
	Choices->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(0.0f, 0.0f, 12.0f, 0.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.newgame.difficulty", "Difficulty"))
			.Font(IronStyle::BodyBold(17.0f))
			.ColorAndOpacity(IronStyle::Gold())
		];

	const IronSim::EDifficulty Levels[] = {IronSim::EDifficulty::Easy, IronSim::EDifficulty::Normal, IronSim::EDifficulty::Hard};
	for (const IronSim::EDifficulty Level : Levels)
	{
		Choices->AddSlot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(3.0f, 0.0f))
			[
				SNew(SButton)
				.ButtonStyle(&IronStyle::Tab(Level == Difficulty))
				.OnClicked(IronStyle::WithClickSound(FOnClicked::CreateSP(this, &SIronNewGameScreen::OnDifficultyClicked, Level)))
				.HAlign(HAlign_Center)
				.VAlign(VAlign_Center)
				[
					SNew(SBox)
					.MinDesiredWidth(90.0f)
					.HAlign(HAlign_Center)
					[
						SNew(STextBlock)
						.Text(IronUI::ToText(IronSim::DisplayName(Level)))
						.Font(IronStyle::BodyBold(16.0f))
						.ColorAndOpacity(IronStyle::TextLight())
					]
				]
			];
	}

	Choices->AddSlot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		.Padding(FMargin(16.0f, 0.0f, 0.0f, 0.0f))
		[
			SNew(STextBlock)
			.Text(this, &SIronNewGameScreen::DifficultyHint)
			.Font(IronStyle::Body(15.0f))
			.ColorAndOpacity(IronStyle::TextLight())
			.AutoWrapText(true)
		];
	return Choices;
}

FReply SIronNewGameScreen::OnScenarioClicked(int32 ScenarioIndex)
{
	if (ScenarioIndex != SelectedScenario && Scenarios.IsValidIndex(ScenarioIndex))
	{
		SelectedScenario = ScenarioIndex;
		SelectedFaction = INDEX_NONE;
		RebuildFactionGrid();
	}
	return FReply::Handled();
}

FReply SIronNewGameScreen::OnFactionClicked(int32 FactionIndex)
{
	SelectedFaction = FactionIndex;
	return FReply::Handled();
}

FReply SIronNewGameScreen::OnDifficultyClicked(IronSim::EDifficulty Level)
{
	Difficulty = Level;
	RebuildDifficulty();
	return FReply::Handled();
}

FReply SIronNewGameScreen::OnStart()
{
	const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin();
	const FIronScenarioEntry* Entry = SelectedEntry();
	if (!PinnedRoot.IsValid() || !Session.IsValid() || Entry == nullptr || !CanStart())
	{
		return FReply::Handled();
	}

	FText Error;
	if (Session->StartNewGame(Entry->Path, SelectedFaction, Difficulty, Error))
	{
		FIronAudio::Get().PlaySfx(TEXT("Confirm"));
		// This screen is destroyed by ShowStrategy: no member access after this point.
		PinnedRoot->ResetStrategy();
		PinnedRoot->ShowStrategy();
	}
	else
	{
		PinnedRoot->ShowMessage(IronUI::Loc("ui.newgame.startFailed", "The Campaign Cannot Begin"), Error);
	}
	return FReply::Handled();
}

FReply SIronNewGameScreen::OnBack()
{
	FIronAudio::Get().PlaySfx(TEXT("Cancel"));
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->ShowTitle();
	}
	return FReply::Handled();
}
