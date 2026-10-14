#include "UI/SIronBattleScreen.h"

#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronDuelDialog.h"
#include "UI/SIronHexView.h"
#include "World/IronBattleBoard3D.h"
#include "World/IronEnvironment.h"
#include "World/IronWorldMap3D.h"

#include "Engine/World.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformTime.h"
#include "Input/Events.h"
#include "InputCoreTypes.h"
#include "Layout/Geometry.h"
#include "Styling/SlateColor.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SNullWidget.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

#include <algorithm>

namespace IronBattleScreenDetail
{
	/** Failed AI steps tolerated before End Turn is offered as an escape hatch. */
	constexpr int32 MaxStalls = 3;
	constexpr int32 MaxLogLines = 200;
	constexpr double ResultDelaySeconds = 1.2;

	// 3D board.
	/** Fractions of a 1920 x 1080 screen covered by the top bar, unit panel and bottom bar, until they are measured. */
	constexpr float EstimatedTopInset = 0.11f;
	constexpr float EstimatedRightInset = 0.21f;
	constexpr float EstimatedBottomInset = 0.16f;
	/** Smallest change of a measured inset that reframes the board. */
	constexpr float InsetTolerance = 0.004f;
	/** Month shown on the board when no campaign is running. */
	constexpr int32 DefaultBoardMonth = 4;

	/**
	 * The world the 3D scenes live in: the session's presentation world (set for the session's whole life by
	 * UIronReignWorldStateSubsystem), or null, which keeps the 2D board. Never GEngine->GameViewport: with several PIE
	 * instances that is another instance's world.
	 */
	UWorld* FindBattleWorld(const FIronSession* InSession)
	{
		return InSession != nullptr ? InSession->GetPresentationWorld() : nullptr;
	}

	/** Converts any Slate 2D vector type (FVector2D, FVector2f, deprecation wrappers) to FVector2f. */
	template <typename VectorType>
	FVector2f ScreenVec(const VectorType& Value)
	{
		return FVector2f(static_cast<float>(Value.X), static_cast<float>(Value.Y));
	}

	bool ContainsId(const std::vector<int>& Ids, int32 Id)
	{
		return std::find(Ids.begin(), Ids.end(), Id) != Ids.end();
	}

	/** The tactic used by an action mode; false for modes that are not tactics. */
	bool ModeTactic(EIronBattleMode InMode, IronSim::ETactic& OutTactic)
	{
		switch (InMode)
		{
		case EIronBattleMode::Fire:
			OutTactic = IronSim::ETactic::Fire;
			return true;
		case EIronBattleMode::Confuse:
			OutTactic = IronSim::ETactic::Confuse;
			return true;
		case EIronBattleMode::Rally:
			OutTactic = IronSim::ETactic::Rally;
			return true;
		case EIronBattleMode::None:
		case EIronBattleMode::Attack:
		case EIronBattleMode::Duel:
			break;
		}
		return false;
	}

	int32 TacticSlot(IronSim::ETactic Tactic)
	{
		return FMath::Clamp(static_cast<int32>(Tactic), 0, 2);
	}

	TSharedRef<SWidget> MakeDividerImage()
	{
		return SNew(SBox)
			.HeightOverride(12.0f)
			.Padding(FMargin(0.0f, 2.0f))
			[
				SNew(SImage)
				.Image(IronStyle::Divider())
			];
	}
}

// -------------------------------------------------------------------------------------------------
// Construction and layout
// -------------------------------------------------------------------------------------------------

void SIronBattleScreen::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	FinishedDelegate = InArgs._OnFinished;

	Battle = MakeShared<IronSim::FBattle>();
	Battle->Setup(InArgs._Setup);
	for (int32 SideIndex = 0; SideIndex < 2; ++SideIndex)
	{
		if (InArgs._Setup.Sides[SideIndex].bPlayer)
		{
			PlayerSide = SideIndex;
			break;
		}
	}

	// The campaign map pauses for the battle (StopBoard3D gives it the view back): on the 3D board it would only be a
	// second scene to render far away, behind the 2D board it would be hidden.
	if (UWorld* BattleWorld = IronBattleScreenDetail::FindBattleWorld(Session.Get()))
	{
		AIronWorldMap3D* CampaignMap = AIronWorldMap3D::FindMap(BattleWorld);
		if (CampaignMap != nullptr && CampaignMap->IsMapActive())
		{
			PausedMap = CampaignMap;
			CampaignMap->SetActive(false);
		}
	}
	StartBoard3D();

	ChildSlot
	[
		BuildLayout()
	];

	if (Session.IsValid())
	{
		CultureChangedHandle = Session->OnCultureChanged.AddSP(this, &SIronBattleScreen::OnCultureChanged);
	}

	FIronAudio::Get().PlayMusic(TEXT("Battle"));

	// Setup events (e.g. the first DayStart) play as the screen opens.
	ConsumeEvents(true);
	NextStepTime = FPlatformTime::Seconds() + 1.0;
	RegisterActiveTimer(0.0f, FWidgetActiveTimerDelegate::CreateSP(this, &SIronBattleScreen::OnDriverTick));
}

SIronBattleScreen::~SIronBattleScreen()
{
	if (Session.IsValid() && CultureChangedHandle.IsValid())
	{
		Session->OnCultureChanged.Remove(CultureChangedHandle);
	}
	// Normally done when the player continues from the result; here only if the screen goes away some other way.
	StopBoard3D(false);
}

void SIronBattleScreen::OnCultureChanged()
{
	RebuildLayout();
}

void SIronBattleScreen::RebuildLayout()
{
	ChildSlot
	[
		BuildLayout()
	];
	ShownLogCount = -1;
	ShownTechniqueUnit = -2;
	bFocusRequested = false;
	RefreshAll();
}

TSharedRef<SWidget> SIronBattleScreen::BuildLayout()
{
	SAssignNew(HexView, SIronHexView)
		.Battle(Battle)
		.Session(Session)
		.Board(Board)
		.OnHexClicked(FOnIronHexClicked::CreateSP(this, &SIronBattleScreen::OnHexClicked))
		.OnCancel(FOnIronHexCancel::CreateSP(this, &SIronBattleScreen::CancelAction));
	HexView->SetCoveredInsets(BoardInsets);

	TopBarWidget.Reset();
	UnitPanelWidget.Reset();
	BottomBarWidget.Reset();
	const TSharedRef<SWidget> Content = bBoard3D ? BuildBoardLayout() : BuildFlatLayout();

	const TSharedRef<SWidget> Layout = SNew(SOverlay)
		+ SOverlay::Slot()
		[
			Content
		]
		+ SOverlay::Slot()
		[
			SNew(SBorder)
			.Visibility(TAttribute<EVisibility>::CreateSP(this, &SIronBattleScreen::GetLocalModalVisibility))
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(FLinearColor(0.0f, 0.0f, 0.0f, 0.6f))
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			[
				SAssignNew(LocalModalHost, SBox)
			]
		];

	if (LocalModals.Num() > 0 && LocalModalHost.IsValid())
	{
		LocalModalHost->SetContent(LocalModals.Last());
	}
	return Layout;
}

TSharedRef<SWidget> SIronBattleScreen::BuildFlatLayout()
{
	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::Night())
		.Padding(FMargin(10.0f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				BuildTopBar()
			]
			+ SVerticalBox::Slot()
			.FillHeight(1.0f)
			.Padding(FMargin(0.0f, 8.0f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				[
					SNew(SBorder)
					.BorderImage(IronStyle::PanelDark())
					.Padding(FMargin(10.0f))
					[
						HexView.ToSharedRef()
					]
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
				[
					BuildUnitPanel()
				]
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				BuildBottomBar()
			]
		];
}

TSharedRef<SWidget> SIronBattleScreen::BuildBoardLayout()
{
	// No background anywhere: the 3D board shows through the hex view, which covers the whole screen under the panels.
	// The containers between the panels are not hit-testable, so the cursor reaches the board through the gaps.
	TopBarWidget = BuildTopBar();
	UnitPanelWidget = BuildUnitPanel();
	BottomBarWidget = BuildBottomBar();
	return SNew(SOverlay)
		.Visibility(EVisibility::SelfHitTestInvisible)
		+ SOverlay::Slot()
		[
			HexView.ToSharedRef()
		]
		+ SOverlay::Slot()
		[
			SNew(SBox)
			.Visibility(EVisibility::SelfHitTestInvisible)
			.Padding(FMargin(10.0f))
			[
				SNew(SVerticalBox)
				.Visibility(EVisibility::SelfHitTestInvisible)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					TopBarWidget.ToSharedRef()
				]
				+ SVerticalBox::Slot()
				.FillHeight(1.0f)
				.Padding(FMargin(0.0f, 8.0f))
				.HAlign(HAlign_Right)
				[
					UnitPanelWidget.ToSharedRef()
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					BottomBarWidget.ToSharedRef()
				]
			]
		];
}

TSharedRef<SWidget> SIronBattleScreen::BuildTopBar()
{
	const IronSim::FBattleSetup& BattleSetup = Battle->GetSetup();
	const FText LocationText = BattleSetup.Location.empty() ? IronUI::Loc("ui.battle.title", "Battle") : IronUI::ToText(BattleSetup.Location);
	const FLinearColor Light = IronStyle::TextLight();

	return IronStyle::MakePanel(
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			BuildSideHeader(0)
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		.Padding(FMargin(16.0f, 0.0f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				SNew(STextBlock)
				.Text(LocationText)
				.Font(IronStyle::Heading(26.0f))
				.ColorAndOpacity(IronStyle::Gold())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				SNew(STextBlock)
				.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetDayText))
				.Font(IronStyle::BodyBold(17.0f))
				.ColorAndOpacity(Light)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(FMargin(0.0f, 4.0f, 0.0f, 0.0f))
			[
				SNew(SHorizontalBox)
				.Visibility(TAttribute<EVisibility>::CreateSP(this, &SIronBattleScreen::GetGateVisibility))
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
				[
					SNew(STextBlock)
					.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetGateText))
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(Light)
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(SBox)
					.WidthOverride(160.0f)
					[
						IronStyle::MakeBar(TAttribute<float>::CreateSP(this, &SIronBattleScreen::GetGateFraction), IronStyle::Gold(), 8.0f)
					]
				]
			]
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			BuildSideHeader(1)
		],
		true, FMargin(18.0f, 10.0f));
}

TSharedRef<SWidget> SIronBattleScreen::BuildSideHeader(int32 Side)
{
	const IronSim::FBattleSetup& BattleSetup = Battle->GetSetup();
	const bool bLeft = Side == 0;
	const EHorizontalAlignment TextAlign = bLeft ? HAlign_Left : HAlign_Right;
	const FLinearColor Light = IronStyle::TextLight();

	FText RoleText;
	if (Side == PlayerSide)
	{
		RoleText = bLeft ? IronUI::Loc("ui.battle.role.attackerPlayer", "Attacker - your army") : IronUI::Loc("ui.battle.role.defenderPlayer", "Defender - your army");
	}
	else
	{
		RoleText = bLeft ? IronUI::Loc("ui.battle.role.attacker", "Attacker") : IronUI::Loc("ui.battle.role.defender", "Defender");
	}

	const TSharedRef<SWidget> Info = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(TextAlign)
		[
			SNew(STextBlock)
			.Text(IronUI::ToText(SideNameOf(Side)))
			.Font(IronStyle::Heading(22.0f))
			.ColorAndOpacity(Light)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(TextAlign)
		[
			SNew(STextBlock)
			.Text(RoleText)
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::Gold())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f, 0.0f, 2.0f))
		[
			IronStyle::MakeBar(TAttribute<float>::CreateLambda([this, Side]() { return GetSideTroopsFraction(Side); }), IronBattleUI::SideColor(BattleSetup, Side), 10.0f)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(TextAlign)
		[
			SNew(STextBlock)
			.Text(TAttribute<FText>::CreateLambda([this, Side]() { return GetSideTroopsText(Side); }))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(Light)
		];

	const TSharedRef<SWidget> Banner = IronStyle::MakeBanner(BattleSetup.Sides[bLeft ? 0 : 1].Faction, 72.0f);
	if (bLeft)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.0f, 0.0f, 12.0f, 0.0f))
			[
				Banner
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				Info
			];
	}
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			Info
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
		[
			Banner
		];
}

TSharedRef<SWidget> SIronBattleScreen::BuildActionButton(EIronBattleAction Action, const FText& Label, const FString& IconName)
{
	const TSharedRef<SBox> Holder = SNew(SBox)
		.Padding(FMargin(3.0f))
		[
			IronStyle::MakeButton(Label, FOnClicked::CreateSP(this, &SIronBattleScreen::OnActionClicked, Action), TAttribute<bool>::CreateLambda([this, Action]() { return IsActionEnabled(Action); }), IconName, 0.0f)
		];
	if (Action == EIronBattleAction::AttackGate)
	{
		Holder->SetVisibility(TAttribute<EVisibility>::CreateSP(this, &SIronBattleScreen::GetGateActionVisibility));
	}
	return Holder;
}

TSharedRef<SWidget> SIronBattleScreen::BuildUnitPanel()
{
	const FLinearColor InkColor = IronStyle::Ink();
	const FLinearColor SoftColor = IronStyle::InkSoft();

	const TSharedRef<SVerticalBox> StatRows = SNew(SVerticalBox);
	for (int32 StatIndex = 0; StatIndex < IronSim::StatCount; ++StatIndex)
	{
		StatRows->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(IronUI::ToText(IronSim::DisplayName(static_cast<IronSim::EStat>(StatIndex))))
				.Font(IronStyle::Body(14.0f))
				.ColorAndOpacity(SoftColor)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(6.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(34.0f)
				[
					SNew(STextBlock)
					.Text(TAttribute<FText>::CreateLambda([this, StatIndex]() { return GetStatValueText(StatIndex); }))
					.Font(IronStyle::BodyBold(14.0f))
					.ColorAndOpacity(InkColor)
					.Justification(ETextJustify::Right)
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(120.0f)
				[
					IronStyle::MakeBar(TAttribute<float>::CreateLambda([this, StatIndex]() { return GetStatFraction(StatIndex); }), IronStyle::Indigo(), 6.0f)
				]
			]
		];
	}

	const auto MakeActionRow = [](const TSharedRef<SWidget>& LeftButton, const TSharedRef<SWidget>& RightButton) -> TSharedRef<SWidget>
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			[
				LeftButton
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			[
				RightButton
			];
	};

	const TSharedRef<SWidget> NoUnitContent = SNew(STextBlock)
		.Visibility(TAttribute<EVisibility>::CreateSP(this, &SIronBattleScreen::GetNoUnitVisibility))
		.Text(IronUI::Loc("ui.battle.unit.none", "Select one of your units on the board to give it orders. Hover over any hex for details."))
		.Font(IronStyle::Body(15.0f))
		.ColorAndOpacity(SoftColor)
		.AutoWrapText(true);

	const TSharedRef<SWidget> UnitContent = SNew(SVerticalBox)
		.Visibility(TAttribute<EVisibility>::CreateSP(this, &SIronBattleScreen::GetUnitVisibility))
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetUnitNameText))
			.Font(IronStyle::Heading(24.0f))
			.ColorAndOpacity(IronStyle::Lacquer())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetUnitSideText))
			.Font(IronStyle::BodyBold(14.0f))
			.ColorAndOpacity(TAttribute<FSlateColor>::CreateSP(this, &SIronBattleScreen::GetUnitSideColor))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 8.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				IronStyle::MakePortrait(TAttribute<FString>::CreateSP(this, &SIronBattleScreen::GetUnitPortrait), 150.0f)
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetUnitTypeText))
					.Font(IronStyle::BodyBold(16.0f))
					.ColorAndOpacity(InkColor)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
				[
					SNew(STextBlock)
					.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetUnitStatusText))
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(SoftColor)
					.AutoWrapText(true)
				]
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetUnitTroopsText))
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(InkColor)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f, 0.0f, 6.0f))
		[
			IronStyle::MakeBar(TAttribute<float>::CreateSP(this, &SIronBattleScreen::GetUnitTroopsFraction), IronStyle::Jade(), 10.0f)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetUnitMoraleText))
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(InkColor)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f, 0.0f, 6.0f))
		[
			IronStyle::MakeBar(TAttribute<float>::CreateSP(this, &SIronBattleScreen::GetUnitMoraleFraction), IronStyle::Gold(), 10.0f)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronBattleScreenDetail::MakeDividerImage()
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			StatRows
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 8.0f, 0.0f, 2.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.battle.unit.techniques", "Techniques"))
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(IronStyle::Lacquer())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SAssignNew(TechniqueBox, SVerticalBox)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronBattleScreenDetail::MakeDividerImage()
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f, 0.0f, 6.0f))
		[
			SNew(STextBlock)
			.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetModeHintText))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(SoftColor)
			.AutoWrapText(true)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			MakeActionRow(
				BuildActionButton(EIronBattleAction::Attack, IronUI::Loc("ui.battle.action.attack", "Attack"), TEXT("Attack")),
				BuildActionButton(EIronBattleAction::Fire, IronUI::ToText(IronSim::DisplayName(IronSim::ETactic::Fire)), TEXT("Fire")))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			MakeActionRow(
				BuildActionButton(EIronBattleAction::Confuse, IronUI::ToText(IronSim::DisplayName(IronSim::ETactic::Confuse)), TEXT("Confuse")),
				BuildActionButton(EIronBattleAction::Rally, IronUI::ToText(IronSim::DisplayName(IronSim::ETactic::Rally)), TEXT("Rally")))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			MakeActionRow(
				BuildActionButton(EIronBattleAction::Duel, IronUI::Loc("ui.battle.action.duel", "Duel"), TEXT("Duel")),
				BuildActionButton(EIronBattleAction::Wait, IronUI::Loc("ui.battle.action.wait", "Wait"), TEXT("Wait")))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			MakeActionRow(
				BuildActionButton(EIronBattleAction::Undo, IronUI::Loc("ui.battle.action.undo", "Undo Move"), TEXT("Undo")),
				BuildActionButton(EIronBattleAction::AttackGate, IronUI::Loc("ui.battle.action.attackGate", "Attack Gate"), TEXT("Attack")))
		];

	return SNew(SBox)
		.WidthOverride(380.0f)
		[
			IronStyle::MakePanel(
				SNew(SScrollBox)
				+ SScrollBox::Slot()
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						NoUnitContent
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						UnitContent
					]
				],
				false, FMargin(18.0f))
		];
}

TSharedRef<SWidget> SIronBattleScreen::BuildBottomBar()
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		[
			SNew(SBox)
			.HeightOverride(150.0f)
			[
				IronStyle::MakePanel(SAssignNew(LogBox, SScrollBox), false, FMargin(16.0f, 10.0f))
			]
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
		[
			SNew(SBox)
			.WidthOverride(380.0f)
			.HeightOverride(150.0f)
			[
				IronStyle::MakePanel(
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.FillHeight(1.0f)
					.HAlign(HAlign_Center)
					.VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Text(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetTurnText))
						.Font(IronStyle::BodyBold(16.0f))
						.ColorAndOpacity(IronStyle::Gold())
						.Justification(ETextJustify::Center)
						.AutoWrapText(true)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.FillWidth(1.0f)
						.Padding(FMargin(0.0f, 0.0f, 4.0f, 0.0f))
						[
							IronStyle::MakeButton(IronUI::Loc("ui.battle.endTurn", "End Turn"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnEndTurnClicked), TAttribute<bool>::CreateSP(this, &SIronBattleScreen::IsEndTurnEnabled), TEXT("EndTurn"), 0.0f)
						]
						+ SHorizontalBox::Slot()
						.FillWidth(1.0f)
						.Padding(FMargin(4.0f, 0.0f, 0.0f, 0.0f))
						[
							IronStyle::MakeButton(TAttribute<FText>::CreateSP(this, &SIronBattleScreen::GetDelegateLabel), FOnClicked::CreateSP(this, &SIronBattleScreen::OnDelegateClicked), TAttribute<bool>::CreateSP(this, &SIronBattleScreen::IsDelegateEnabled), TEXT("Delegate"), 0.0f)
						]
					],
					true, FMargin(16.0f, 10.0f))
			]
		];
}

TSharedRef<SWidget> SIronBattleScreen::MakeModalFrame(const TSharedRef<SWidget>& Content, float Width) const
{
	return SNew(SBox)
		.WidthOverride(Width)
		[
			IronStyle::MakePanel(Content, false, FMargin(28.0f))
		];
}

// -------------------------------------------------------------------------------------------------
// 3D board
// -------------------------------------------------------------------------------------------------

bool SIronBattleScreen::StartBoard3D()
{
	// Presentation mode Auto / 3D with the board's imported assets available (FIronSession::Uses3DBattle).
	if (!Session.IsValid() || !Session->Uses3DBattle())
	{
		return false;
	}
	UWorld* BattleWorld = IronBattleScreenDetail::FindBattleWorld(Session.Get());
	AIronBattleBoard3D* NewBoard = BattleWorld != nullptr ? AIronBattleBoard3D::SpawnBoard(BattleWorld) : nullptr;
	if (NewBoard == nullptr)
	{
		return false;
	}
	NewBoard->Build(*Battle);
	if (!NewBoard->IsBuilt())
	{
		return false;
	}
	NewBoard->SetSeason(Session->HasGame() ? Session->State().Month : IronBattleScreenDetail::DefaultBoardMonth);
	NewBoard->SetQuality(Session->GetGraphicsQuality());
	// The look and the other graphics options at once: without a 3D map the player controller's poll would apply them
	// up to half a second later (ink outlines popping in). The controller keeps applying them on every settings change;
	// the board's camera follows the environment's tilt-shift strength by itself.
	if (AIronEnvironment* BoardEnvironment = NewBoard->GetEnvironment())
	{
		Session->ApplyEnvironmentOptions(*BoardEnvironment);
	}
	// Frame for the usual panel sizes at once; UpdateBoardFraming refines it from the real layout.
	NewBoard->SetFramingInsets(0.0f, IronBattleScreenDetail::EstimatedTopInset, IronBattleScreenDetail::EstimatedRightInset, IronBattleScreenDetail::EstimatedBottomInset);
	NewBoard->ResetView(true);
	NewBoard->SetActive(true);
	Board = NewBoard;
	bBoard3D = true;
	bBoardFramed = false;
	return true;
}

void SIronBattleScreen::StopBoard3D(bool bRestoreMap)
{
	AIronBattleBoard3D* ShownBoard = Board.Get();
	Board.Reset();
	bBoard3D = false;
	if (ShownBoard != nullptr)
	{
		// Finishes running animations, restores the shared sun and turns world rendering off unless the map shows.
		ShownBoard->SetActive(false);
		if (bRestoreMap)
		{
			// Free the hexes and units until the next battle builds the board again.
			ShownBoard->ClearBoard();
		}
	}
	AIronWorldMap3D* CampaignMap = PausedMap.Get();
	PausedMap.Reset();
	if (bRestoreMap && CampaignMap != nullptr && !CampaignMap->HasFailed())
	{
		CampaignMap->SetActive(true);
	}
}

void SIronBattleScreen::FallBackTo2D()
{
	if (AIronBattleBoard3D* ShownBoard = Board.Get())
	{
		ShownBoard->SetActive(false);
	}
	Board.Reset();
	bBoard3D = false;
	BoardInsets = FMargin(0.0f);
	RebuildLayout();
}

void SIronBattleScreen::UpdateBoardFraming()
{
	AIronBattleBoard3D* ShownBoard = Board.Get();
	if (ShownBoard == nullptr || !HexView.IsValid() || !TopBarWidget.IsValid() || !UnitPanelWidget.IsValid() || !BottomBarWidget.IsValid())
	{
		return;
	}
	// The hex view covers the screen; the panels' edges in its space give the covered fractions.
	const FGeometry& ViewGeometry = HexView->GetTickSpaceGeometry();
	const FVector2f ViewSize = IronBattleScreenDetail::ScreenVec(ViewGeometry.GetLocalSize());
	if (ViewSize.X < 64.0f || ViewSize.Y < 64.0f)
	{
		return;
	}
	const FVector2f TopBarMax = IronBattleScreenDetail::ScreenVec(ViewGeometry.AbsoluteToLocal(TopBarWidget->GetTickSpaceGeometry().GetAbsolutePositionAtCoordinates(FVector2D(1.0, 1.0))));
	const FVector2f UnitPanelMin = IronBattleScreenDetail::ScreenVec(ViewGeometry.AbsoluteToLocal(UnitPanelWidget->GetTickSpaceGeometry().GetAbsolutePositionAtCoordinates(FVector2D(0.0, 0.0))));
	const FVector2f BottomBarMin = IronBattleScreenDetail::ScreenVec(ViewGeometry.AbsoluteToLocal(BottomBarWidget->GetTickSpaceGeometry().GetAbsolutePositionAtCoordinates(FVector2D(0.0, 0.0))));
	if (TopBarMax.Y <= 0.0f || UnitPanelMin.X <= 0.0f || BottomBarMin.Y <= 0.0f)
	{
		// Not laid out yet.
		return;
	}
	const FMargin NewInsets(
		0.0f,
		FMath::Clamp(TopBarMax.Y / ViewSize.Y, 0.0f, 0.45f),
		FMath::Clamp((ViewSize.X - UnitPanelMin.X) / ViewSize.X, 0.0f, 0.45f),
		FMath::Clamp((ViewSize.Y - BottomBarMin.Y) / ViewSize.Y, 0.0f, 0.45f));
	const bool bChanged = FMath::Abs(NewInsets.Top - BoardInsets.Top) > IronBattleScreenDetail::InsetTolerance
		|| FMath::Abs(NewInsets.Right - BoardInsets.Right) > IronBattleScreenDetail::InsetTolerance
		|| FMath::Abs(NewInsets.Bottom - BoardInsets.Bottom) > IronBattleScreenDetail::InsetTolerance;
	if (bBoardFramed && !bChanged)
	{
		return;
	}
	BoardInsets = NewInsets;
	HexView->SetCoveredInsets(BoardInsets);
	ShownBoard->SetFramingInsets(BoardInsets.Left, BoardInsets.Top, BoardInsets.Right, BoardInsets.Bottom);
	if (!bBoardFramed)
	{
		// First real layout: frame the whole board at once instead of gliding from the estimate.
		bBoardFramed = true;
		ShownBoard->ResetView(true);
	}
}

// -------------------------------------------------------------------------------------------------
// Turn flow
// -------------------------------------------------------------------------------------------------

float SIronBattleScreen::StepSeconds() const
{
	return Session.IsValid() ? FMath::Clamp(Session->GetBattleStepSeconds(), 0.05f, 3.0f) : 0.35f;
}

bool SIronBattleScreen::IsHumanTurn() const
{
	return PlayerSide >= 0 && !bDelegated && !bFinishedFired && !Battle->IsOver() && Battle->ActiveSide() == PlayerSide && Battle->IsPlayerTurn();
}

EActiveTimerReturnType SIronBattleScreen::OnDriverTick(double /*InCurrentTime*/, float /*InDeltaTime*/)
{
	if (bBoard3D)
	{
		if (!HexView.IsValid() || !HexView->IsBoardMode())
		{
			FallBackTo2D();
		}
		else
		{
			UpdateBoardFraming();
		}
	}
	if (!bFocusRequested && HexView.IsValid() && FSlateApplication::IsInitialized() && !IsAnyModalOpen())
	{
		bFocusRequested = true;
		FSlateApplication::Get().SetKeyboardFocus(HexView, EFocusCause::SetDirectly);
	}
	if (bFinishedFired || IsAnyModalOpen())
	{
		return EActiveTimerReturnType::Continue;
	}

	const double Now = FPlatformTime::Seconds();
	// 2D move animations, or the 3D board's queued animations.
	const bool bAnimating = HexView.IsValid() && HexView->IsAnimating();
	if (Battle->IsOver())
	{
		if (OverSince < 0.0)
		{
			OverSince = Now;
			Mode = EIronBattleMode::None;
			RefreshAll();
		}
		if (!bAnimating && Now - OverSince >= IronBattleScreenDetail::ResultDelaySeconds)
		{
			ShowResult();
		}
		return EActiveTimerReturnType::Continue;
	}
	if (bAnimating)
	{
		if (bBoard3D)
		{
			// The 3D animations outlast the step time: the AI still pauses briefly after each one before acting again.
			NextStepTime = FMath::Max(NextStepTime, Now + StepSeconds() * 0.5);
		}
		return EActiveTimerReturnType::Continue;
	}
	if (Battle->HasPendingChallenge())
	{
		ShowChallenge();
		return EActiveTimerReturnType::Continue;
	}
	if (Battle->HasActiveDuel())
	{
		OpenDuel();
		return EActiveTimerReturnType::Continue;
	}
	if (IsHumanTurn())
	{
		AnnouncePlayerTurn();
		return EActiveTimerReturnType::Continue;
	}
	if (StallCount > IronBattleScreenDetail::MaxStalls || Now < NextStepTime)
	{
		return EActiveTimerReturnType::Continue;
	}

	// An AI side (the enemy, or the player's own side when delegated) acts: one action per step.
	NextStepTime = Now + StepSeconds();
	if (Battle->StepAI())
	{
		StallCount = 0;
		ConsumeEvents(true);
	}
	else
	{
		HandleStall();
	}
	return EActiveTimerReturnType::Continue;
}

void SIronBattleScreen::HandleStall()
{
	ConsumeEvents(true);
	if (Battle->IsOver() || Battle->HasPendingChallenge() || Battle->HasActiveDuel() || IsHumanTurn())
	{
		StallCount = 0;
		return;
	}
	++StallCount;
	if (StallCount > IronBattleScreenDetail::MaxStalls)
	{
		// Give up stepping; End Turn becomes available so the battle can never deadlock.
		return;
	}
	// The AI reported nothing to do although its side is active: end that side's turn for it.
	const int32 DayBefore = Battle->Day();
	const int32 SideBefore = Battle->ActiveSide();
	Battle->EndTurn();
	const bool bProgressed = Battle->IsOver() || Battle->Day() != DayBefore || Battle->ActiveSide() != SideBefore;
	if (bProgressed)
	{
		StallCount = 0;
	}
	else if (bDelegated)
	{
		// The engine does not step a delegated side: resolve the rest at once.
		Battle->AutoResolve();
		if (HexView.IsValid())
		{
			HexView->ClearAnimations();
		}
		ConsumeEvents(false);
		return;
	}
	ConsumeEvents(true);
}

void SIronBattleScreen::AnnouncePlayerTurn()
{
	const int32 TurnKey = Battle->Day() * 2 + Battle->ActiveSide();
	if (TurnKey == AnnouncedTurnKey)
	{
		return;
	}
	AnnouncedTurnKey = TurnKey;
	if (HexView.IsValid())
	{
		HexView->ShowBanner(IronUI::LocF("ui.battle.banner.yourTurn", "Day {day}: your orders, my lord", {{"day", IronSim::ToText(Battle->Day())}}));
	}
	RefreshAll();
}

void SIronBattleScreen::ConsumeEvents(bool bAnimate)
{
	if (HexView.IsValid())
	{
		if (bAnimate)
		{
			for (const IronSim::FBattleEvent& Event : Battle->Events())
			{
				HexView->PlayEvent(Event);
			}
		}
		// 3D: the board takes the resolved state after queueing the events (a fast-forward snaps it); no-op in 2D.
		HexView->SyncBoard(!bAnimate);
	}
	Battle->ClearEvents();
	RefreshAll();
}

// -------------------------------------------------------------------------------------------------
// Refresh
// -------------------------------------------------------------------------------------------------

void SIronBattleScreen::RefreshAll()
{
	if (SelectedUnit >= 0 && (!IsValidUnitId(SelectedUnit) || !Battle->Unit(SelectedUnit).IsActive()))
	{
		SelectedUnit = -1;
	}
	RefreshActionCache();

	bool bModeValid = false;
	switch (Mode)
	{
	case EIronBattleMode::None:
		bModeValid = true;
		break;
	case EIronBattleMode::Attack:
		bModeValid = IsActionEnabled(EIronBattleAction::Attack);
		break;
	case EIronBattleMode::Fire:
		bModeValid = IsActionEnabled(EIronBattleAction::Fire);
		break;
	case EIronBattleMode::Confuse:
		bModeValid = IsActionEnabled(EIronBattleAction::Confuse);
		break;
	case EIronBattleMode::Rally:
		bModeValid = IsActionEnabled(EIronBattleAction::Rally);
		break;
	case EIronBattleMode::Duel:
		bModeValid = IsActionEnabled(EIronBattleAction::Duel);
		break;
	}
	if (!bModeValid)
	{
		Mode = EIronBattleMode::None;
	}

	RefreshHighlights();
	RefreshLog(false);
	RefreshTechniques(false);
}

void SIronBattleScreen::RefreshActionCache()
{
	bCanCommand = false;
	bCanAttackGate = false;
	CachedReachable.clear();
	CachedAttackTargets.clear();
	for (std::vector<int>& Targets : CachedTacticTargets)
	{
		Targets.clear();
	}
	CachedDuelTargets.clear();

	const IronSim::FBattleUnit* Selected = GetPanelUnit();
	if (Selected == nullptr || !IsHumanTurn() || Selected->Side != PlayerSide || !Selected->IsActive() || Selected->bActed)
	{
		return;
	}
	bCanCommand = true;
	if (!Selected->bMoved)
	{
		CachedReachable = Battle->Reachable(SelectedUnit);
	}
	CachedAttackTargets = Battle->AttackTargets(SelectedUnit);
	CachedTacticTargets[IronBattleScreenDetail::TacticSlot(IronSim::ETactic::Fire)] = Battle->TacticTargets(SelectedUnit, IronSim::ETactic::Fire);
	CachedTacticTargets[IronBattleScreenDetail::TacticSlot(IronSim::ETactic::Confuse)] = Battle->TacticTargets(SelectedUnit, IronSim::ETactic::Confuse);
	CachedTacticTargets[IronBattleScreenDetail::TacticSlot(IronSim::ETactic::Rally)] = Battle->TacticTargets(SelectedUnit, IronSim::ETactic::Rally);
	CachedDuelTargets = Battle->DuelTargets(SelectedUnit);
	bCanAttackGate = Battle->CanAttackGate(SelectedUnit);
}

void SIronBattleScreen::RefreshHighlights()
{
	if (!HexView.IsValid())
	{
		return;
	}
	FIronHexHighlights NewHighlights;
	NewHighlights.SelectedUnit = SelectedUnit;
	if (bCanCommand && IsValidUnitId(SelectedUnit))
	{
		NewHighlights.ActingUnit = SelectedUnit;
		const auto AddUnitHexes = [this](const std::vector<int>& Ids, TArray<IronSim::FHex>& OutHexes)
		{
			for (const int TargetId : Ids)
			{
				if (IsValidUnitId(TargetId))
				{
					OutHexes.Add(Battle->Unit(TargetId).Pos);
				}
			}
		};
		IronSim::ETactic Tactic = IronSim::ETactic::Fire;
		switch (Mode)
		{
		case EIronBattleMode::None:
		{
			const IronSim::FHex CurrentPos = Battle->Unit(SelectedUnit).Pos;
			for (const IronSim::FReachableHex& Entry : CachedReachable)
			{
				if (Entry.Hex != CurrentPos)
				{
					NewHighlights.Reachable.Add(Entry.Hex);
				}
			}
			AddUnitHexes(CachedAttackTargets, NewHighlights.AttackTargets);
			break;
		}
		case EIronBattleMode::Attack:
			AddUnitHexes(CachedAttackTargets, NewHighlights.AttackTargets);
			break;
		case EIronBattleMode::Fire:
		case EIronBattleMode::Confuse:
		case EIronBattleMode::Rally:
			if (IronBattleScreenDetail::ModeTactic(Mode, Tactic))
			{
				AddUnitHexes(CachedTacticTargets[IronBattleScreenDetail::TacticSlot(Tactic)], NewHighlights.TacticTargets);
				NewHighlights.bTacticPreview = true;
				NewHighlights.PreviewTactic = Tactic;
			}
			break;
		case EIronBattleMode::Duel:
			AddUnitHexes(CachedDuelTargets, NewHighlights.DuelTargets);
			break;
		}
	}
	HexView->SetHighlights(NewHighlights);
}

void SIronBattleScreen::RefreshLog(bool bForce)
{
	const std::vector<std::string>& Lines = Battle->Log();
	const int32 Count = static_cast<int32>(Lines.size());
	if (!LogBox.IsValid() || (!bForce && Count == ShownLogCount))
	{
		return;
	}
	ShownLogCount = Count;
	LogBox->ClearChildren();
	const int32 First = FMath::Max(0, Count - IronBattleScreenDetail::MaxLogLines);
	for (int32 LineIndex = Count - 1; LineIndex >= First; --LineIndex)
	{
		LogBox->AddSlot()
		.Padding(FMargin(0.0f, 1.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::ToText(Lines[static_cast<size_t>(LineIndex)]))
			.Font(LineIndex == Count - 1 ? IronStyle::BodyBold(14.0f) : IronStyle::Body(14.0f))
			.ColorAndOpacity(LineIndex == Count - 1 ? IronStyle::Ink() : IronStyle::InkSoft())
			.AutoWrapText(true)
		];
	}
	LogBox->ScrollToStart();
}

void SIronBattleScreen::RefreshTechniques(bool bForce)
{
	if (!TechniqueBox.IsValid() || (!bForce && ShownTechniqueUnit == SelectedUnit))
	{
		return;
	}
	ShownTechniqueUnit = SelectedUnit;
	TechniqueBox->ClearChildren();
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr)
	{
		return;
	}
	const std::vector<IronSim::FTechnique>& Table = Battle->GetSetup().Techniques;
	int32 Shown = 0;
	for (const int TechniqueIndex : PanelUnit->Setup.Techniques)
	{
		if (TechniqueIndex < 0 || TechniqueIndex >= static_cast<int>(Table.size()))
		{
			continue;
		}
		const IronSim::FTechnique& Technique = Table[static_cast<size_t>(TechniqueIndex)];
		TechniqueBox->AddSlot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(IronUI::LocF("ui.battle.techniqueLabel", "{technique} ({move})", {{"technique", IronSim::NameOf(Technique)}, {"move", IronSim::DisplayName(Technique.Kind)}}))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(IronStyle::Ink())
		];
		++Shown;
	}
	if (Shown == 0)
	{
		TechniqueBox->AddSlot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.battle.unit.noTechniques", "None"))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		];
	}
}

// -------------------------------------------------------------------------------------------------
// Modals
// -------------------------------------------------------------------------------------------------

bool SIronBattleScreen::IsAnyModalOpen() const
{
	if (LocalModals.Num() > 0)
	{
		return true;
	}
	const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin();
	return PinnedRoot.IsValid() && PinnedRoot->HasModal();
}

void SIronBattleScreen::PushScreenModal(const TSharedRef<SWidget>& Widget, bool bMustAnswer)
{
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		if (bMustAnswer)
		{
			PinnedRoot->PushModalWithEscape(Widget, nullptr);
		}
		else
		{
			PinnedRoot->PushModal(Widget);
		}
	}
	else
	{
		LocalModals.Add(Widget);
		if (LocalModalHost.IsValid())
		{
			LocalModalHost->SetContent(Widget);
		}
	}
}

void SIronBattleScreen::PopScreenModal()
{
	// The root refocuses itself when a modal closes; give the board keyboard focus back on the next tick.
	bFocusRequested = false;
	if (LocalModals.Num() > 0)
	{
		LocalModals.RemoveAt(LocalModals.Num() - 1);
		if (LocalModalHost.IsValid())
		{
			LocalModalHost->SetContent(LocalModals.Num() > 0 ? LocalModals.Last() : SNullWidget::NullWidget);
		}
		return;
	}
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		if (PinnedRoot->HasModal())
		{
			PinnedRoot->PopModal();
		}
	}
}

void SIronBattleScreen::ShowChallenge()
{
	const int32 ChallengerId = Battle->ChallengerUnit();
	const int32 ChallengedId = Battle->ChallengedUnit();
	if (!IsValidUnitId(ChallengerId) || !IsValidUnitId(ChallengedId))
	{
		Battle->AnswerChallenge(false);
		ConsumeEvents(true);
		return;
	}

	const auto MakeFighter = [](const IronSim::FBattleUnit& Fighter, const FText& FighterName) -> TSharedRef<SWidget>
	{
		const FString PortraitId = Fighter.Setup.Portrait.empty() ? FString(TEXT("unknown")) : IronUI::ToFString(Fighter.Setup.Portrait);
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				IronStyle::MakePortrait(PortraitId, 170.0f)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
			[
				SNew(STextBlock)
				.Text(FighterName)
				.Font(IronStyle::Heading(20.0f))
				.ColorAndOpacity(IronStyle::Ink())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.HAlign(HAlign_Center)
			[
				SNew(STextBlock)
				.Text(IronUI::LocF("ui.battle.challenge.martial", "Martial {value}", {{"value", IronSim::ToText(Fighter.Setup.Stats[IronSim::StatIndex(IronSim::EStat::Martial)])}}))
				.Font(IronStyle::Body(14.0f))
				.ColorAndOpacity(IronStyle::InkSoft())
			];
	};

	const std::string ChallengerName = UnitNameOf(ChallengerId);
	const std::string ChallengedName = UnitNameOf(ChallengedId);
	const TSharedRef<SWidget> Content = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.battle.challenge.title", "A Challenge!"), 28.0f, false)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 12.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				MakeFighter(Battle->Unit(ChallengerId), IronUI::ToText(ChallengerName))
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(24.0f, 0.0f))
			[
				SNew(STextBlock)
				.Text(IronUI::Loc("ui.battle.duel.versus", "VS"))
				.Font(IronStyle::Heading(36.0f))
				.ColorAndOpacity(IronStyle::Lacquer())
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				MakeFighter(Battle->Unit(ChallengedId), IronUI::ToText(ChallengedName))
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Text(IronUI::LocF("ui.battle.challenge.text", "{enemy} challenges {officer} to a duel!", {{"enemy", ChallengerName}, {"officer", ChallengedName}}))
			.Font(IronStyle::BodyBold(18.0f))
			.ColorAndOpacity(IronStyle::Ink())
			.Justification(ETextJustify::Center)
			.AutoWrapText(true)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 4.0f, 0.0f, 14.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.battle.challenge.hint", "Refusing will shake the morale of your troops."))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(6.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.battle.challenge.accept", "Accept"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnChallengeAccept), true, TEXT("Duel"), 180.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(6.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.battle.challenge.decline", "Decline"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnChallengeDecline), true, FString(), 180.0f)
			]
		];

	PushScreenModal(MakeModalFrame(Content, 660.0f), true);
}

FReply SIronBattleScreen::OnChallengeAccept()
{
	AnswerChallenge(true);
	return FReply::Handled();
}

FReply SIronBattleScreen::OnChallengeDecline()
{
	FIronAudio::Get().PlaySfx(TEXT("Cancel"));
	AnswerChallenge(false);
	return FReply::Handled();
}

void SIronBattleScreen::AnswerChallenge(bool bAccept)
{
	PopScreenModal();
	if (Battle->HasPendingChallenge())
	{
		Battle->AnswerChallenge(bAccept);
	}
	// An accepted challenge leaves an active duel; the driver opens the duel dialog on its next tick.
	ConsumeEvents(true);
}

void SIronBattleScreen::OpenDuel()
{
	int32 PlayerDuelSide = -1;
	if (!bDelegated && PlayerSide >= 0)
	{
		for (int32 DuelSide = 0; DuelSide < 2; ++DuelSide)
		{
			const int32 DuelUnitId = Battle->DuelUnit(DuelSide);
			if (IsValidUnitId(DuelUnitId) && Battle->Unit(DuelUnitId).Side == PlayerSide)
			{
				PlayerDuelSide = DuelSide;
				break;
			}
		}
		if (PlayerDuelSide < 0)
		{
			const IronSim::FBattle& ConstBattle = *Battle;
			for (int32 DuelSide = 0; DuelSide < 2; ++DuelSide)
			{
				if (ConstBattle.ActiveDuel().Side(DuelSide).bPlayer)
				{
					PlayerDuelSide = DuelSide;
					break;
				}
			}
		}
	}

	FIronAudio::Get().PlayMusic(TEXT("Duel"));
	PushScreenModal(SNew(SIronDuelDialog)
		.Battle(Battle)
		.Session(Session)
		.PlayerSide(PlayerDuelSide)
		.OnClosed(FSimpleDelegate::CreateSP(this, &SIronBattleScreen::OnDuelClosed)), true);
}

void SIronBattleScreen::OnDuelClosed()
{
	const TSharedRef<SIronBattleScreen> KeepAlive = SharedThis(this);
	PopScreenModal();
	FIronAudio::Get().PlayMusic(TEXT("Battle"));
	if (Battle->HasActiveDuel())
	{
		if (!Battle->ActiveDuel().IsOver())
		{
			Battle->ActiveDuel().AutoPlay();
		}
		Battle->FinishDuel();
	}
	ConsumeEvents(true);
}

void SIronBattleScreen::ShowResult()
{
	const IronSim::FBattleResult& Outcome = Battle->Result();
	const int32 Winner = Outcome.Winner;
	const bool bHasWinner = Winner == 0 || Winner == 1;

	FText Title;
	if (!bHasWinner)
	{
		Title = IronUI::Loc("ui.battle.result.draw", "Stalemate");
	}
	else if (PlayerSide >= 0)
	{
		Title = Winner == PlayerSide ? IronUI::Loc("ui.battle.result.victory", "Victory!") : IronUI::Loc("ui.battle.result.defeat", "Defeat");
	}
	else
	{
		Title = IronUI::LocF("ui.battle.result.sideWins", "{side} is victorious", {{"side", SideNameOf(Winner)}});
	}
	const FText Line = bHasWinner
		? IronUI::LocF("ui.battle.result.line", "{side} won the battle after {days} days.", {{"side", SideNameOf(Winner)}, {"days", IronSim::ToText(Outcome.Days)}})
		: IronUI::LocF("ui.battle.result.noWinner", "The battle ended without a victor after {days} days.", {{"days", IronSim::ToText(Outcome.Days)}});

	const auto MakeRow = [](const FText& UnitText, const FText& SideText, const FText& TroopText, const FText& StatusText, const FLinearColor& StatusColor, bool bHeader) -> TSharedRef<SWidget>
	{
		const FSlateFontInfo RowFont = bHeader ? IronStyle::BodyBold(14.0f) : IronStyle::Body(14.0f);
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.4f)
			[
				SNew(STextBlock)
				.Text(UnitText)
				.Font(RowFont)
				.ColorAndOpacity(IronStyle::Ink())
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			[
				SNew(STextBlock)
				.Text(SideText)
				.Font(RowFont)
				.ColorAndOpacity(IronStyle::InkSoft())
			]
			+ SHorizontalBox::Slot()
			.FillWidth(0.6f)
			[
				SNew(STextBlock)
				.Text(TroopText)
				.Font(RowFont)
				.ColorAndOpacity(IronStyle::Ink())
				.Justification(ETextJustify::Right)
			]
			+ SHorizontalBox::Slot()
			.FillWidth(0.9f)
			.Padding(FMargin(14.0f, 0.0f, 0.0f, 0.0f))
			[
				SNew(STextBlock)
				.Text(StatusText)
				.Font(RowFont)
				.ColorAndOpacity(StatusColor)
			];
	};

	const TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
	Rows->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 0.0f, 0.0f, 4.0f))
	[
		MakeRow(IronUI::Loc("ui.battle.result.colUnit", "Commander"), IronUI::Loc("ui.battle.result.colSide", "Army"), IronUI::Loc("ui.battle.result.colTroops", "Troops"), IronUI::Loc("ui.battle.result.colOutcome", "Outcome"), IronStyle::Ink(), true)
	];
	const std::vector<IronSim::FBattleUnit>& AllUnits = Battle->Units();
	for (int32 SideIndex = 0; SideIndex < 2; ++SideIndex)
	{
		for (int32 UnitIndex = 0; UnitIndex < static_cast<int32>(AllUnits.size()); ++UnitIndex)
		{
			const IronSim::FBattleUnit& Entry = AllUnits[static_cast<size_t>(UnitIndex)];
			if (Entry.Side != SideIndex)
			{
				continue;
			}
			IronSim::EUnitStatus FinalStatus = Entry.Status;
			int32 FinalTroops = Entry.Troops;
			if (UnitIndex < static_cast<int32>(Outcome.Units.size()))
			{
				FinalStatus = Outcome.Units[static_cast<size_t>(UnitIndex)].Status;
				FinalTroops = Outcome.Units[static_cast<size_t>(UnitIndex)].Troops;
			}
			const FLinearColor StatusColor = FinalStatus == IronSim::EUnitStatus::Active ? IronStyle::Jade() : IronStyle::Danger();
			Rows->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 1.0f))
			[
				MakeRow(IronUI::ToText(UnitNameOf(UnitIndex)), IronUI::ToText(SideNameOf(SideIndex)), IronUI::Number(FinalTroops), IronBattleUI::UnitStatusName(FinalStatus), StatusColor, false)
			];
		}
	}

	const TSharedRef<SVerticalBox> Content = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			IronStyle::MakeHeader(Title, 34.0f, false)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
		[
			SNew(STextBlock)
			.Text(Line)
			.Font(IronStyle::BodyBold(17.0f))
			.ColorAndOpacity(IronStyle::Ink())
		];
	if (Outcome.bGateBroken)
	{
		Content->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.battle.result.gateBroken", "The city gate was broken."))
			.Font(IronStyle::Body(15.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		];
	}
	if (!Outcome.Summary.empty())
	{
		Content->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f, 0.0f, 0.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::ToText(Outcome.Summary))
			.Font(IronStyle::Body(15.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
			.Justification(ETextJustify::Center)
			.AutoWrapText(true)
		];
	}
	Content->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 8.0f))
	[
		IronBattleScreenDetail::MakeDividerImage()
	];
	Content->AddSlot()
	.AutoHeight()
	[
		SNew(SBox)
		.MaxDesiredHeight(380.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				Rows
			]
		]
	];
	Content->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	.Padding(FMargin(0.0f, 14.0f, 0.0f, 0.0f))
	[
		IronStyle::MakeButton(IronUI::Loc("ui.battle.result.continue", "Continue"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnResultContinue), true, FString(), 220.0f)
	];

	if (bHasWinner && PlayerSide >= 0)
	{
		// One-shot sting; the strategy music takes over once the player continues.
		FIronAudio::Get().PlayMusic(Winner == PlayerSide ? TEXT("Victory") : TEXT("Defeat"), false);
	}
	PushScreenModal(MakeModalFrame(Content, 780.0f), true);
}

FReply SIronBattleScreen::OnResultContinue()
{
	if (bFinishedFired)
	{
		return FReply::Handled();
	}
	bFinishedFired = true;
	// OnFinished usually replaces this screen: keep it alive until the handler returns.
	const TSharedRef<SIronBattleScreen> KeepAlive = SharedThis(this);
	PopScreenModal();
	// The view goes back to the campaign map (if it was showing) or to the 2D screens.
	StopBoard3D(true);
	const IronSim::FBattleResult FinalResult = Battle->Result();
	FinishedDelegate.ExecuteIfBound(FinalResult);
	return FReply::Handled();
}

void SIronBattleScreen::ShowDelegatePrompt()
{
	const TSharedRef<SWidget> Content = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.battle.delegate.title", "Delegate Command"), 26.0f, false)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 16.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.battle.delegate.text", "Your officers will fight on under their own command. Watch the battle unfold, or skip straight to its outcome?"))
			.Font(IronStyle::Body(16.0f))
			.ColorAndOpacity(IronStyle::Ink())
			.Justification(ETextJustify::Center)
			.AutoWrapText(true)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(5.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.battle.delegate.watch", "Watch"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnDelegateWatch), true, TEXT("Delegate"), 150.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(5.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.battle.delegate.skip", "Skip to Result"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnDelegateSkip), true, FString(), 150.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(5.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.battle.delegate.cancel", "Cancel"), FOnClicked::CreateSP(this, &SIronBattleScreen::OnDelegateCancel), true, FString(), 150.0f)
			]
		];
	PushScreenModal(MakeModalFrame(Content, 620.0f));
}

FReply SIronBattleScreen::OnDelegateWatch()
{
	FIronAudio::Get().PlaySfx(TEXT("Confirm"));
	PopScreenModal();
	if (PlayerSide < 0 || Battle->IsOver())
	{
		return FReply::Handled();
	}
	bDelegated = true;
	Battle->SetAutoControl(PlayerSide, true);
	SelectedUnit = -1;
	Mode = EIronBattleMode::None;
	StallCount = 0;
	NextStepTime = FPlatformTime::Seconds() + 0.2;
	RefreshAll();
	return FReply::Handled();
}

FReply SIronBattleScreen::OnDelegateSkip()
{
	FIronAudio::Get().PlaySfx(TEXT("Confirm"));
	PopScreenModal();
	if (PlayerSide < 0 || Battle->IsOver())
	{
		return FReply::Handled();
	}
	bDelegated = true;
	Battle->SetAutoControl(PlayerSide, true);
	Battle->AutoResolve();
	if (HexView.IsValid())
	{
		HexView->ClearAnimations();
	}
	SelectedUnit = -1;
	Mode = EIronBattleMode::None;
	StallCount = 0;
	ConsumeEvents(false);
	return FReply::Handled();
}

FReply SIronBattleScreen::OnDelegateCancel()
{
	FIronAudio::Get().PlaySfx(TEXT("Cancel"));
	PopScreenModal();
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Input
// -------------------------------------------------------------------------------------------------

FReply SIronBattleScreen::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey() == EKeys::Escape && !IsAnyModalOpen() && CancelAction())
	{
		return FReply::Handled();
	}
	return SCompoundWidget::OnKeyDown(MyGeometry, InKeyEvent);
}

bool SIronBattleScreen::CancelAction()
{
	if (Mode != EIronBattleMode::None)
	{
		Mode = EIronBattleMode::None;
		RefreshHighlights();
		return true;
	}
	if (SelectedUnit >= 0)
	{
		SelectUnit(-1);
		return true;
	}
	return false;
}

void SIronBattleScreen::SelectUnit(int32 UnitId)
{
	SelectedUnit = IsValidUnitId(UnitId) ? UnitId : -1;
	Mode = EIronBattleMode::None;
	RefreshAll();
}

void SIronBattleScreen::OnHexClicked(IronSim::FHex Hex)
{
	if (bFinishedFired || IsAnyModalOpen() || !Battle->InBounds(Hex))
	{
		return;
	}
	const int32 ClickedId = Battle->UnitAt(Hex);
	const bool bClickedUnit = IsValidUnitId(ClickedId) && Battle->Unit(ClickedId).IsActive();

	if (bCanCommand && IsValidUnitId(SelectedUnit))
	{
		const int32 ActorId = SelectedUnit;
		IronSim::ETactic Tactic = IronSim::ETactic::Fire;
		switch (Mode)
		{
		case EIronBattleMode::None:
			if (bClickedUnit && IronBattleScreenDetail::ContainsId(CachedAttackTargets, ClickedId))
			{
				AfterPlayerAction(Battle->Attack(ActorId, ClickedId));
				return;
			}
			if (!bClickedUnit && ReachableContains(Hex))
			{
				AfterPlayerAction(Battle->Move(ActorId, Hex));
				return;
			}
			break;
		case EIronBattleMode::Attack:
			if (bClickedUnit && IronBattleScreenDetail::ContainsId(CachedAttackTargets, ClickedId))
			{
				AfterPlayerAction(Battle->Attack(ActorId, ClickedId));
				return;
			}
			break;
		case EIronBattleMode::Fire:
		case EIronBattleMode::Confuse:
		case EIronBattleMode::Rally:
			if (bClickedUnit && IronBattleScreenDetail::ModeTactic(Mode, Tactic) && IronBattleScreenDetail::ContainsId(CachedTacticTargets[IronBattleScreenDetail::TacticSlot(Tactic)], ClickedId))
			{
				AfterPlayerAction(Battle->UseTactic(ActorId, Tactic, ClickedId));
				return;
			}
			break;
		case EIronBattleMode::Duel:
			if (bClickedUnit && IronBattleScreenDetail::ContainsId(CachedDuelTargets, ClickedId))
			{
				AfterPlayerAction(Battle->ChallengeDuel(ActorId, ClickedId));
				return;
			}
			break;
		}
		if (Mode != EIronBattleMode::None && !(bClickedUnit && Battle->Unit(ClickedId).Side == PlayerSide))
		{
			// A click outside the targets cancels the action mode but keeps the unit selected.
			Mode = EIronBattleMode::None;
			RefreshHighlights();
			return;
		}
	}

	// Select (own units) or inspect (any unit); an empty hex clears the selection.
	SelectUnit(bClickedUnit ? ClickedId : -1);
}

void SIronBattleScreen::AfterPlayerAction(bool bSucceeded)
{
	Mode = EIronBattleMode::None;
	if (bSucceeded && IsValidUnitId(SelectedUnit))
	{
		const IronSim::FBattleUnit& Actor = Battle->Unit(SelectedUnit);
		if (Actor.bActed || !Actor.IsActive())
		{
			SelectedUnit = -1;
		}
	}
	ConsumeEvents(true);
}

FReply SIronBattleScreen::OnActionClicked(EIronBattleAction Action)
{
	if (!IsActionEnabled(Action) || IsAnyModalOpen())
	{
		return FReply::Handled();
	}
	const auto ToggleMode = [this](EIronBattleMode NewMode)
	{
		Mode = (Mode == NewMode) ? EIronBattleMode::None : NewMode;
		RefreshHighlights();
	};
	switch (Action)
	{
	case EIronBattleAction::Attack:
		ToggleMode(EIronBattleMode::Attack);
		break;
	case EIronBattleAction::Fire:
		ToggleMode(EIronBattleMode::Fire);
		break;
	case EIronBattleAction::Confuse:
		ToggleMode(EIronBattleMode::Confuse);
		break;
	case EIronBattleAction::Rally:
		ToggleMode(EIronBattleMode::Rally);
		break;
	case EIronBattleAction::Duel:
		ToggleMode(EIronBattleMode::Duel);
		break;
	case EIronBattleAction::AttackGate:
		AfterPlayerAction(Battle->AttackGate(SelectedUnit));
		break;
	case EIronBattleAction::Wait:
		AfterPlayerAction(Battle->Wait(SelectedUnit));
		break;
	case EIronBattleAction::Undo:
		AfterPlayerAction(Battle->UndoMove(SelectedUnit));
		break;
	}
	return FReply::Handled();
}

FReply SIronBattleScreen::OnEndTurnClicked()
{
	if (!IsEndTurnEnabled())
	{
		return FReply::Handled();
	}
	FIronAudio::Get().PlaySfx(TEXT("EndTurn"));
	SelectedUnit = -1;
	Mode = EIronBattleMode::None;
	Battle->EndTurn();
	StallCount = 0;
	NextStepTime = FPlatformTime::Seconds() + StepSeconds();
	ConsumeEvents(true);
	return FReply::Handled();
}

FReply SIronBattleScreen::OnDelegateClicked()
{
	if (!IsDelegateEnabled())
	{
		return FReply::Handled();
	}
	if (bDelegated)
	{
		// Take command again; the AI finishes nothing more for the player's side.
		bDelegated = false;
		Battle->SetAutoControl(PlayerSide, false);
		StallCount = 0;
		RefreshAll();
		return FReply::Handled();
	}
	ShowDelegatePrompt();
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Queries
// -------------------------------------------------------------------------------------------------

bool SIronBattleScreen::IsValidUnitId(int32 UnitId) const
{
	return Battle.IsValid() && UnitId >= 0 && UnitId < static_cast<int32>(Battle->Units().size());
}

const IronSim::FBattleUnit* SIronBattleScreen::GetPanelUnit() const
{
	return IsValidUnitId(SelectedUnit) ? &Battle->Unit(SelectedUnit) : nullptr;
}

bool SIronBattleScreen::IsActionEnabled(EIronBattleAction Action) const
{
	if (!bCanCommand)
	{
		return false;
	}
	switch (Action)
	{
	case EIronBattleAction::Attack:
		return !CachedAttackTargets.empty();
	case EIronBattleAction::Fire:
		return !CachedTacticTargets[IronBattleScreenDetail::TacticSlot(IronSim::ETactic::Fire)].empty();
	case EIronBattleAction::Confuse:
		return !CachedTacticTargets[IronBattleScreenDetail::TacticSlot(IronSim::ETactic::Confuse)].empty();
	case EIronBattleAction::Rally:
		return !CachedTacticTargets[IronBattleScreenDetail::TacticSlot(IronSim::ETactic::Rally)].empty();
	case EIronBattleAction::Duel:
		return !CachedDuelTargets.empty();
	case EIronBattleAction::AttackGate:
		return bCanAttackGate;
	case EIronBattleAction::Wait:
		return true;
	case EIronBattleAction::Undo:
	{
		const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
		return PanelUnit != nullptr && PanelUnit->bMoved;
	}
	}
	return false;
}

bool SIronBattleScreen::ReachableContains(IronSim::FHex Hex) const
{
	for (const IronSim::FReachableHex& Entry : CachedReachable)
	{
		if (Entry.Hex == Hex)
		{
			return true;
		}
	}
	return false;
}

int32 SIronBattleScreen::SideTroops(int32 Side, bool bStartTroops) const
{
	int32 Total = 0;
	for (const IronSim::FBattleUnit& Entry : Battle->Units())
	{
		if (Entry.Side != Side)
		{
			continue;
		}
		if (bStartTroops)
		{
			Total += Entry.StartTroops;
		}
		else if (Entry.IsActive())
		{
			Total += Entry.Troops;
		}
	}
	return Total;
}

std::string SIronBattleScreen::UnitNameOf(int32 UnitId) const
{
	return IsValidUnitId(UnitId) ? IronBattleUI::UnitName(Session.Get(), Battle->Unit(UnitId)) : std::string();
}

std::string SIronBattleScreen::SideNameOf(int32 Side) const
{
	return IronBattleUI::SideName(Session.Get(), Battle->GetSetup(), Side);
}

// -------------------------------------------------------------------------------------------------
// Attribute getters
// -------------------------------------------------------------------------------------------------

FText SIronBattleScreen::GetDayText() const
{
	const int32 MaxDays = Battle->GetSetup().MaxDays;
	return IronUI::LocF("ui.battle.day", "Day {day} / {max}", {{"day", IronSim::ToText(FMath::Min(Battle->Day(), MaxDays))}, {"max", IronSim::ToText(MaxDays)}});
}

FText SIronBattleScreen::GetTurnText() const
{
	if (Battle->IsOver())
	{
		return IronUI::Loc("ui.battle.turn.over", "The battle is over.");
	}
	if (Battle->HasPendingChallenge() || Battle->HasActiveDuel())
	{
		return IronUI::Loc("ui.battle.turn.duel", "A duel is under way.");
	}
	if (IsHumanTurn())
	{
		return IronUI::Loc("ui.battle.turn.player", "Your turn: give your orders.");
	}
	if (bDelegated && Battle->ActiveSide() == PlayerSide)
	{
		return IronUI::Loc("ui.battle.turn.delegated", "Your officers act on their own.");
	}
	return IronUI::LocF("ui.battle.turn.other", "{side} is moving...", {{"side", SideNameOf(Battle->ActiveSide())}});
}

FText SIronBattleScreen::GetSideTroopsText(int32 Side) const
{
	return IronUI::LocF("ui.battle.sideTroops", "{troops} / {start} troops", {{"troops", IronSim::ToText(SideTroops(Side, false))}, {"start", IronSim::ToText(SideTroops(Side, true))}});
}

float SIronBattleScreen::GetSideTroopsFraction(int32 Side) const
{
	const int32 Start = SideTroops(Side, true);
	return Start > 0 ? FMath::Clamp(static_cast<float>(SideTroops(Side, false)) / static_cast<float>(Start), 0.0f, 1.0f) : 0.0f;
}

FText SIronBattleScreen::GetGateText() const
{
	const int32 MaxHp = Battle->GateMaxHp();
	if (Battle->GateCount() >= 2)
	{
		return IronUI::LocF("ui.battle.gates", "Gates {hpA} and {hpB} / {max}", {{"hpA", IronSim::ToText(FMath::Max(0, Battle->GateHpAt(0)))}, {"hpB", IronSim::ToText(FMath::Max(0, Battle->GateHpAt(1)))}, {"max", IronSim::ToText(MaxHp)}});
	}
	return IronUI::LocF("ui.battle.gate", "Gate {hp} / {max}", {{"hp", IronSim::ToText(FMath::Max(0, Battle->GateHpAt(0)))}, {"max", IronSim::ToText(MaxHp)}});
}

float SIronBattleScreen::GetGateFraction() const
{
	const int32 Count = Battle->GateCount();
	const int32 MaxHp = Battle->GateMaxHp();
	if (Count <= 0 || MaxHp <= 0)
	{
		return 0.0f;
	}
	int32 Remaining = 0;
	for (int32 GateIndex = 0; GateIndex < Count; ++GateIndex)
	{
		Remaining += FMath::Max(0, Battle->GateHpAt(GateIndex));
	}
	return FMath::Clamp(static_cast<float>(Remaining) / static_cast<float>(MaxHp * Count), 0.0f, 1.0f);
}

EVisibility SIronBattleScreen::GetGateVisibility() const
{
	return (Battle->GetSetup().Kind == IronSim::EBattleKind::Siege && Battle->GateCount() > 0 && Battle->GateMaxHp() > 0) ? EVisibility::Visible : EVisibility::Collapsed;
}

FText SIronBattleScreen::GetUnitNameText() const
{
	return GetPanelUnit() != nullptr ? IronUI::ToText(UnitNameOf(SelectedUnit)) : FText::GetEmpty();
}

FText SIronBattleScreen::GetUnitSideText() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	return PanelUnit != nullptr ? IronUI::ToText(SideNameOf(PanelUnit->Side)) : FText::GetEmpty();
}

FSlateColor SIronBattleScreen::GetUnitSideColor() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	return FSlateColor(PanelUnit != nullptr ? IronBattleUI::SideColor(Battle->GetSetup(), PanelUnit->Side) : IronStyle::InkSoft());
}

FText SIronBattleScreen::GetUnitTypeText() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	return PanelUnit != nullptr ? IronUI::ToText(IronSim::DisplayName(PanelUnit->Setup.Type)) : FText::GetEmpty();
}

FText SIronBattleScreen::GetUnitTroopsText() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr)
	{
		return FText::GetEmpty();
	}
	return IronUI::LocF("ui.battle.unit.troops", "Troops {troops} / {max}", {{"troops", IronSim::ToText(PanelUnit->Troops)}, {"max", IronSim::ToText(PanelUnit->StartTroops)}});
}

float SIronBattleScreen::GetUnitTroopsFraction() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr || PanelUnit->StartTroops <= 0)
	{
		return 0.0f;
	}
	return FMath::Clamp(static_cast<float>(PanelUnit->Troops) / static_cast<float>(PanelUnit->StartTroops), 0.0f, 1.0f);
}

FText SIronBattleScreen::GetUnitMoraleText() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr)
	{
		return FText::GetEmpty();
	}
	return IronUI::LocF("ui.battle.unit.morale", "Morale {morale} / 100", {{"morale", IronSim::ToText(PanelUnit->Morale)}});
}

float SIronBattleScreen::GetUnitMoraleFraction() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	return PanelUnit != nullptr ? FMath::Clamp(static_cast<float>(PanelUnit->Morale) / 100.0f, 0.0f, 1.0f) : 0.0f;
}

FText SIronBattleScreen::GetUnitStatusText() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr)
	{
		return FText::GetEmpty();
	}
	TArray<FString> Parts;
	if (PanelUnit->bCommander)
	{
		Parts.Add(IronUI::Loc("ui.battle.unit.commander", "Commander").ToString());
	}
	if (!PanelUnit->IsActive())
	{
		Parts.Add(IronBattleUI::UnitStatusName(PanelUnit->Status).ToString());
	}
	else
	{
		if (PanelUnit->ConfusedDays > 0)
		{
			Parts.Add(IronUI::LocF("ui.battle.unit.confused", "Confused ({days} days)", {{"days", IronSim::ToText(PanelUnit->ConfusedDays)}}).ToString());
		}
		if (PanelUnit->Side == Battle->ActiveSide())
		{
			if (PanelUnit->bActed)
			{
				Parts.Add(IronUI::Loc("ui.battle.unit.acted", "Done for this turn").ToString());
			}
			else if (PanelUnit->bMoved)
			{
				Parts.Add(IronUI::Loc("ui.battle.unit.moved", "Moved").ToString());
			}
			else
			{
				Parts.Add(IronUI::Loc("ui.battle.unit.ready", "Ready").ToString());
			}
		}
	}
	return FText::FromString(FString::Join(Parts, TEXT(", ")));
}

FText SIronBattleScreen::GetStatValueText(int32 StatIndex) const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr || StatIndex < 0 || StatIndex >= IronSim::StatCount)
	{
		return FText::GetEmpty();
	}
	return IronUI::Number(PanelUnit->Setup.Stats[StatIndex]);
}

float SIronBattleScreen::GetStatFraction(int32 StatIndex) const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr || StatIndex < 0 || StatIndex >= IronSim::StatCount)
	{
		return 0.0f;
	}
	return FMath::Clamp(static_cast<float>(PanelUnit->Setup.Stats[StatIndex]) / static_cast<float>(IronSim::MaxStatValue), 0.0f, 1.0f);
}

FString SIronBattleScreen::GetUnitPortrait() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr || PanelUnit->Setup.Portrait.empty())
	{
		return FString(TEXT("unknown"));
	}
	return IronUI::ToFString(PanelUnit->Setup.Portrait);
}

EVisibility SIronBattleScreen::GetUnitVisibility() const
{
	return GetPanelUnit() != nullptr ? EVisibility::Visible : EVisibility::Collapsed;
}

EVisibility SIronBattleScreen::GetNoUnitVisibility() const
{
	return GetPanelUnit() == nullptr ? EVisibility::Visible : EVisibility::Collapsed;
}

FText SIronBattleScreen::GetModeHintText() const
{
	const IronSim::FBattleUnit* PanelUnit = GetPanelUnit();
	if (PanelUnit == nullptr)
	{
		return FText::GetEmpty();
	}
	if (!bCanCommand)
	{
		if (PanelUnit->Side != PlayerSide)
		{
			return IronUI::Loc("ui.battle.hint.enemy", "An enemy unit. Hover over it to see its strength.");
		}
		if (!IsHumanTurn())
		{
			return IronUI::Loc("ui.battle.hint.notYourTurn", "Wait for your turn to give orders.");
		}
		return IronUI::Loc("ui.battle.hint.done", "This unit has finished its turn.");
	}
	IronSim::ETactic Tactic = IronSim::ETactic::Fire;
	switch (Mode)
	{
	case EIronBattleMode::None:
		return PanelUnit->bMoved
			? IronUI::Loc("ui.battle.hint.act", "Choose an action, or Wait to end this unit's turn.")
			: IronUI::Loc("ui.battle.hint.move", "Click a blue hex to move or a red enemy to attack.");
	case EIronBattleMode::Attack:
		return IronUI::Loc("ui.battle.hint.attack", "Choose an enemy to attack. Right-click to cancel.");
	case EIronBattleMode::Fire:
	case EIronBattleMode::Confuse:
	case EIronBattleMode::Rally:
		if (IronBattleScreenDetail::ModeTactic(Mode, Tactic))
		{
			return IronUI::LocF("ui.battle.hint.tactic", "Choose a target for {tactic}. Right-click to cancel.", {{"tactic", IronSim::DisplayName(Tactic)}});
		}
		break;
	case EIronBattleMode::Duel:
		return IronUI::Loc("ui.battle.hint.duel", "Choose an enemy officer to challenge. Right-click to cancel.");
	}
	return FText::GetEmpty();
}

bool SIronBattleScreen::IsEndTurnEnabled() const
{
	if (bFinishedFired || Battle->IsOver())
	{
		return false;
	}
	return IsHumanTurn() || StallCount > IronBattleScreenDetail::MaxStalls;
}

bool SIronBattleScreen::IsDelegateEnabled() const
{
	return PlayerSide >= 0 && !bFinishedFired && !Battle->IsOver();
}

FText SIronBattleScreen::GetDelegateLabel() const
{
	return bDelegated ? IronUI::Loc("ui.battle.takeCommand", "Take Command") : IronUI::Loc("ui.battle.delegate", "Delegate");
}

EVisibility SIronBattleScreen::GetGateActionVisibility() const
{
	return bCanAttackGate ? EVisibility::Visible : EVisibility::Collapsed;
}

EVisibility SIronBattleScreen::GetLocalModalVisibility() const
{
	return LocalModals.Num() > 0 ? EVisibility::Visible : EVisibility::Collapsed;
}
