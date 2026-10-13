#include "UI/SIronStrategyScreen.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronCityPanel.h"
#include "UI/SIronCommandPanel.h"
#include "UI/SIronFactionsPanel.h"
#include "UI/SIronMapView.h"
#include "UI/SIronOfficerTable.h"
#include "UI/SIronRoot.h"
#include "UI/SIronStrategyCommon.h"
#include "UI/SIronStrategyDialogs.h"

#include "Framework/Application/SlateApplication.h"
#include "InputCoreTypes.h"
#include "Templates/TypeHash.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Layout/SWidgetSwitcher.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronStrategyScreenDetail
{
	constexpr int32 SpeedSteps = 4;
	constexpr float SpeedFactors[SpeedSteps] = {0.0f, 1.0f, 2.0f, 4.0f};
	constexpr int32 MaxLogRows = 60;

	FText LogDate(const IronSim::FLogEntry& Entry)
	{
		if (Entry.Day > 0)
		{
			return IronUI::LocF("ui.strategy.logDateDay", "{year}.{month}.{day}", {{"year", IronSim::ToText(Entry.Year)}, {"month", IronSim::ToText(Entry.Month)}, {"day", IronSim::ToText(Entry.Day)}});
		}
		return IronUI::LocF("ui.strategy.logDate", "{year}.{month}", {{"year", IronSim::ToText(Entry.Year)}, {"month", IronSim::ToText(Entry.Month)}});
	}
}

SIronStrategyScreen::~SIronStrategyScreen()
{
	if (Session.IsValid())
	{
		(void)Session->OnStateChanged.Remove(StateChangedHandle);
		(void)Session->OnCultureChanged.Remove(CultureChangedHandle);
	}
}

void SIronStrategyScreen::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;

	if (Session.IsValid())
	{
		StateChangedHandle = Session->OnStateChanged.AddSP(this, &SIronStrategyScreen::HandleStateChanged);
		CultureChangedHandle = Session->OnCultureChanged.AddSP(this, &SIronStrategyScreen::HandleCultureChanged);
		if (Session->HasGame())
		{
			const IronSim::FGameState& GameState = Session->State();
			const IronSim::FFaction* Player = IronStrategy::GetFaction(GameState, GameState.PlayerFaction);
			if (Player && IronStrategy::GetCity(GameState, Player->Capital) != nullptr && GameState.Cities[static_cast<size_t>(Player->Capital)].Owner == GameState.PlayerFaction)
			{
				SelectedCity = Player->Capital;
			}
			else
			{
				const std::vector<int> Owned = GameState.FactionCities(GameState.PlayerFaction);
				SelectedCity = Owned.empty() ? -1 : Owned[0];
			}
			Flow = GameState.Phase == IronSim::EPhase::Execution ? EIronStrategyFlow::Running : EIronStrategyFlow::Planning;
		}
	}
	SyncFlowWithGame();
	BuildLayout();
	TickHandle = RegisterActiveTimer(0.0f, FWidgetActiveTimerDelegate::CreateSP(this, &SIronStrategyScreen::HandleTick));
}

// -------------------------------------------------------------------------------------------------
// Layout
// -------------------------------------------------------------------------------------------------

void SIronStrategyScreen::BuildLayout()
{
	const bool bHadMap = MapView.IsValid();
	const FVector2f SavedCenter = bHadMap ? MapView->GetViewCenter() : FVector2f(0.0f, 0.0f);
	const float SavedZoom = bHadMap ? MapView->GetZoom() : 1.0f;

	ChildSlot
	[
		SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::Night())
		.Padding(FMargin(0.0f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				BuildTopBar()
			]
			+ SVerticalBox::Slot()
			.FillHeight(1.0f)
			.Padding(FMargin(4.0f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(380.0f)
					[
						SAssignNew(CityPanel, SIronCityPanel)
						.Session(Session)
						.City(SelectedCity)
					]
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				.Padding(FMargin(4.0f, 0.0f))
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.FillHeight(1.0f)
					[
						SNew(SBorder)
						.BorderImage(IronStyle::WhiteBrush())
						.BorderBackgroundColor(IronStyle::Gold().CopyWithNewOpacity(0.8f))
						.Padding(FMargin(2.0f))
						[
							SAssignNew(MapView, SIronMapView)
							.Session(Session)
							.FractionalDay_Lambda([this]() { return GetFractionalDay(); })
							.SelectedCity_Lambda([this]() { return SelectedCity; })
							.OnCityClicked(FOnIronMapCityClicked::CreateSP(this, &SIronStrategyScreen::HandleCityClicked))
						]
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 4.0f, 0.0f, 0.0f))
					[
						SNew(SBox)
						.HeightOverride(176.0f)
						[
							BuildLogPanel()
						]
					]
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				[
					SNew(SBox)
					.WidthOverride(370.0f)
					[
						SAssignNew(CommandPanel, SIronCommandPanel)
						.Session(Session)
						.Root(Root)
						.City(SelectedCity)
					]
				]
			]
		]
	];

	if (bHadMap)
	{
		MapView->SetView(SavedCenter, SavedZoom);
	}
	LastLogSignature = 0;
	RebuildLog();
}

TSharedRef<SWidget> SIronStrategyScreen::BuildTopBar()
{
	const bool bHasGame = Session.IsValid() && Session->HasGame();
	const int32 Player = bHasGame ? Session->State().PlayerFaction : -1;
	TSharedPtr<FIronSession> SessionRef = Session;

	TSharedRef<SHorizontalBox> Bar = SNew(SHorizontalBox);
	if (Player >= 0)
	{
		Bar->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			IronStyle::MakeBanner(Player, 58.0f)
		];
	}
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(8.0f, 0.0f, 22.0f, 0.0f))
	[
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([SessionRef]()
			{
				if (!SessionRef.IsValid() || !SessionRef->HasGame())
				{
					return FText::GetEmpty();
				}
				return IronStrategy::FactionName(SessionRef->State(), SessionRef->State().PlayerFaction);
			})
			.Font(IronStyle::Heading(20.0f))
			.ColorAndOpacity(IronStyle::Gold())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([SessionRef]()
			{
				if (!SessionRef.IsValid() || !SessionRef->HasGame())
				{
					return FText::GetEmpty();
				}
				const IronSim::FGameState& LiveState = SessionRef->State();
				const IronSim::FFaction* Faction = IronStrategy::GetFaction(LiveState, LiveState.PlayerFaction);
				return IronUI::LocF("ui.strategy.lordName", "Lord {name}", {{"name", IronUI::ToStd(IronStrategy::OfficerName(LiveState, Faction ? Faction->Ruler : -1).ToString())}});
			})
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::TextLight())
		]
	];

	// Date and phase.
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(0.0f, 0.0f, 26.0f, 0.0f))
	[
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([SessionRef]()
			{
				if (!SessionRef.IsValid() || !SessionRef->HasGame())
				{
					return FText::GetEmpty();
				}
				return IronUI::ToText(SessionRef->Game().DateText());
			})
			.Font(IronStyle::Heading(20.0f))
			.ColorAndOpacity(IronStyle::TextLight())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this]()
			{
				if (!Session.IsValid() || !Session->HasGame())
				{
					return FText::GetEmpty();
				}
				const IronSim::FGameState& LiveState = Session->State();
				switch (Flow)
				{
				case EIronStrategyFlow::Planning:
					return IronUI::LocF("ui.strategy.phasePlanning", "{season} - Planning", {{"season", IronSim::SeasonName(LiveState.Month)}});
				case EIronStrategyFlow::GameOver:
					return IronUI::Loc("ui.strategy.phaseOver", "The war is over");
				case EIronStrategyFlow::BattlePrompt:
				case EIronStrategyFlow::InBattle:
				case EIronStrategyFlow::BattleReport:
					return IronUI::LocF("ui.strategy.phaseBattle", "Day {day} of {days} - Battle!", {{"day", IronSim::ToText(LiveState.Day)}, {"days", IronSim::ToText(IronSim::DaysPerMonth)}});
				case EIronStrategyFlow::Running:
					break;
				}
				if (SpeedIndex == 0)
				{
					return IronUI::LocF("ui.strategy.phasePaused", "Day {day} of {days} - Paused", {{"day", IronSim::ToText(LiveState.Day)}, {"days", IronSim::ToText(IronSim::DaysPerMonth)}});
				}
				return IronUI::LocF("ui.strategy.phaseDay", "Day {day} of {days}", {{"day", IronSim::ToText(LiveState.Day)}, {"days", IronSim::ToText(IronSim::DaysPerMonth)}});
			})
			.Font(IronStyle::BodyBold(14.0f))
			.ColorAndOpacity(IronStyle::Gold())
		]
	];

	// Treasury.
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(0.0f, 0.0f, 14.0f, 0.0f))
	[
		IronStyle::MakeIconValue(TEXT("Gold"), TAttribute<FText>::CreateLambda([SessionRef]()
		{
			return (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::Num(SessionRef->State().FactionTotalGold(SessionRef->State().PlayerFaction)) : FText::GetEmpty();
		}), 26.0f, IronStyle::TextLight())
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(0.0f, 0.0f, 14.0f, 0.0f))
	[
		IronStyle::MakeIconValue(TEXT("Food"), TAttribute<FText>::CreateLambda([SessionRef]()
		{
			return (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::Num(SessionRef->State().FactionTotalFood(SessionRef->State().PlayerFaction)) : FText::GetEmpty();
		}), 26.0f, IronStyle::TextLight())
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(0.0f, 0.0f, 14.0f, 0.0f))
	[
		IronStyle::MakeIconValue(TEXT("Troops"), TAttribute<FText>::CreateLambda([SessionRef]()
		{
			return (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::Num(SessionRef->State().FactionTotalTroops(SessionRef->State().PlayerFaction)) : FText::GetEmpty();
		}), 26.0f, IronStyle::TextLight())
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	[
		IronStyle::MakeIconValue(TEXT("Walls"), TAttribute<FText>::CreateLambda([SessionRef]()
		{
			if (!SessionRef.IsValid() || !SessionRef->HasGame())
			{
				return FText::GetEmpty();
			}
			const IronSim::FGameState& LiveState = SessionRef->State();
			return IronUI::LocF("ui.strategy.citiesOfficers", "{cities} cities, {officers} officers", {{"cities", IronSim::ToText(SessionRef->Game().CityCount(LiveState.PlayerFaction))}, {"officers", IronSim::ToText(static_cast<int>(LiveState.FactionOfficers(LiveState.PlayerFaction).size()))}});
		}), 26.0f, IronStyle::TextLight())
	];

	Bar->AddSlot()
	.FillWidth(1.0f)
	[
		SNew(SSpacer)
	];

	// Menu buttons.
	const TAttribute<bool> MenusEnabled = TAttribute<bool>::CreateSP(this, &SIronStrategyScreen::CanUseMenus);
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(3.0f, 0.0f))
	[
		IronStyle::MakeButton(IronUI::Loc("ui.strategy.officers", "Officers"), FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleOfficers), MenusEnabled, TEXT("Officers"))
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(3.0f, 0.0f))
	[
		IronStyle::MakeButton(IronUI::Loc("ui.strategy.factions", "Factions"), FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleFactions), MenusEnabled, TEXT("Factions"))
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(3.0f, 0.0f))
	[
		IronStyle::MakeButton(IronUI::Loc("ui.strategy.save", "Save"), FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleSave), TAttribute<bool>::CreateSP(this, &SIronStrategyScreen::CanEndTurn), TEXT("Save"))
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(3.0f, 0.0f))
	[
		IronStyle::MakeButton(IronUI::Loc("ui.strategy.load", "Load"), FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleLoad), MenusEnabled, TEXT("Load"))
	];
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	.Padding(FMargin(3.0f, 0.0f, 12.0f, 0.0f))
	[
		IronStyle::MakeButton(IronUI::Loc("ui.strategy.settings", "Settings"), FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleSettings), true, TEXT("Settings"))
	];

	// End Turn during planning, speed controls during execution.
	Bar->AddSlot()
	.AutoWidth()
	.VAlign(VAlign_Center)
	[
		SNew(SWidgetSwitcher)
		.WidgetIndex_Lambda([this]() { return Flow == EIronStrategyFlow::Planning ? 0 : 1; })
		+ SWidgetSwitcher::Slot()
		[
			BuildPlanningControls()
		]
		+ SWidgetSwitcher::Slot()
		[
			BuildExecutionControls()
		]
	];

	return SNew(SBorder)
		.BorderImage(IronStyle::PanelDark())
		.Padding(FMargin(16.0f, 8.0f))
		[
			Bar
		];
}

TSharedRef<SWidget> SIronStrategyScreen::BuildPlanningControls()
{
	return IronStyle::MakeButton(IronUI::Loc("ui.strategy.endTurn", "End Turn"), FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleEndTurn), TAttribute<bool>::CreateSP(this, &SIronStrategyScreen::CanEndTurn), TEXT("EndTurn"), 170.0f);
}

TSharedRef<SWidget> SIronStrategyScreen::BuildSpeedButton(int32 Index, const FText& Label)
{
	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor_Lambda([this, Index]()
		{
			return FSlateColor(SpeedIndex == Index ? IronStyle::Gold() : FLinearColor::Transparent);
		})
		.Padding(FMargin(2.0f))
		[
			IronStyle::MakeButton(Label, FOnClicked::CreateSP(this, &SIronStrategyScreen::HandleSpeed, Index), TAttribute<bool>::CreateLambda([this]()
			{
				return Flow == EIronStrategyFlow::Running;
			}), FString(), 64.0f)
		];
}

TSharedRef<SWidget> SIronStrategyScreen::BuildExecutionControls()
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(2.0f, 0.0f))
		[
			BuildSpeedButton(0, IronUI::Loc("ui.strategy.pause", "Pause"))
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(2.0f, 0.0f))
		[
			BuildSpeedButton(1, IronUI::Loc("ui.strategy.speed1", "1x"))
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(2.0f, 0.0f))
		[
			BuildSpeedButton(2, IronUI::Loc("ui.strategy.speed2", "2x"))
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(2.0f, 0.0f))
		[
			BuildSpeedButton(3, IronUI::Loc("ui.strategy.speed4", "4x"))
		];
}

TSharedRef<SWidget> SIronStrategyScreen::BuildLogPanel()
{
	return IronStyle::MakePanel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 3.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.strategy.chronicle", "Chronicle"))
			.Font(IronStyle::Heading(16.0f))
			.ColorAndOpacity(IronStyle::Lacquer())
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				SAssignNew(LogBox, SVerticalBox)
			]
		],
		false,
		FMargin(14.0f, 8.0f));
}

uint32 SIronStrategyScreen::ComputeLogSignature() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 1;
	}
	const IronSim::FGameState& GameState = Session->State();
	uint32 Hash = GetTypeHash(static_cast<int32>(GameState.Log.size()));
	if (!GameState.Log.empty())
	{
		const IronSim::FLogEntry& Last = GameState.Log.back();
		Hash = (Hash ^ GetTypeHash(IronUI::ToFString(Last.Text))) * 16777619u;
		Hash = (Hash ^ static_cast<uint32>(Last.Day + Last.Month * 31 + Last.Year * 400)) * 16777619u;
	}
	return Hash == 0 ? 2 : Hash;
}

void SIronStrategyScreen::RebuildLog()
{
	if (!LogBox.IsValid())
	{
		return;
	}
	const uint32 Signature = ComputeLogSignature();
	if (Signature == LastLogSignature)
	{
		return;
	}
	LastLogSignature = Signature;
	LogBox->ClearChildren();
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}

	const IronSim::FGameState& GameState = Session->State();
	const int32 Player = GameState.PlayerFaction;
	int32 Rows = 0;
	for (int32 Index = static_cast<int32>(GameState.Log.size()) - 1; Index >= 0 && Rows < IronStrategyScreenDetail::MaxLogRows; --Index)
	{
		const IronSim::FLogEntry& Entry = GameState.Log[static_cast<size_t>(Index)];
		const bool bOwn = Player >= 0 && Entry.Faction == Player;
		if (!bOwn && !Entry.bImportant)
		{
			continue;
		}
		++Rows;
		const FLinearColor Marker = IronStyle::FactionColor(Entry.Faction);
		const FLinearColor Blended = IronStyle::Ink() * 0.4f + Marker * 0.6f;
		const FLinearColor TextColor = bOwn ? IronStyle::Ink() : FLinearColor(Blended.R, Blended.G, Blended.B, 1.0f);
		LogBox->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(0.0f, 3.0f, 6.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(8.0f)
				.HeightOverride(12.0f)
				[
					SNew(SImage)
					.Image(IronStyle::WhiteBrush())
					.ColorAndOpacity(Marker)
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(74.0f)
				[
					SNew(STextBlock)
					.Text(IronStrategyScreenDetail::LogDate(Entry))
					.Font(IronStyle::Body(12.0f))
					.ColorAndOpacity(IronStyle::InkSoft())
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Top)
			[
				SNew(STextBlock)
				.Text(IronUI::ToText(Entry.Text))
				.Font(Entry.bImportant ? IronStyle::BodyBold(13.0f) : IronStyle::Body(13.0f))
				.ColorAndOpacity(TextColor)
				.AutoWrapText(true)
			]
		];
	}
	if (Rows == 0)
	{
		LogBox->AddSlot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.strategy.chronicleEmpty", "The chronicle is still empty."))
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		];
	}
}

// -------------------------------------------------------------------------------------------------
// Session events and selection
// -------------------------------------------------------------------------------------------------

void SIronStrategyScreen::HandleStateChanged()
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	SyncFlowWithGame();
	if (CityPanel.IsValid())
	{
		CityPanel->Refresh();
	}
	if (CommandPanel.IsValid())
	{
		CommandPanel->Refresh();
	}
	RebuildLog();
}

void SIronStrategyScreen::HandleCultureChanged()
{
	BuildLayout();
}

void SIronStrategyScreen::HandleCityClicked(int32 InCity)
{
	SelectCity(InCity);
}

void SIronStrategyScreen::SelectCity(int32 InCity)
{
	SelectedCity = InCity;
	if (CityPanel.IsValid())
	{
		CityPanel->SetCity(InCity);
	}
	if (CommandPanel.IsValid())
	{
		CommandPanel->SetCity(InCity);
	}
}

FReply SIronStrategyScreen::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey() == EKeys::SpaceBar && HandleSpaceKey())
	{
		return FReply::Handled();
	}
	return SCompoundWidget::OnKeyDown(MyGeometry, InKeyEvent);
}

FReply SIronStrategyScreen::OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey() == EKeys::SpaceBar && HandleSpaceKey())
	{
		return FReply::Handled();
	}
	return FReply::Unhandled();
}

bool SIronStrategyScreen::HandleSpaceKey()
{
	if (!Session.IsValid() || !Session->HasGame() || IsRootModalOpen())
	{
		return false;
	}
	if (Flow == EIronStrategyFlow::Planning)
	{
		(void)HandleEndTurn();
		return true;
	}
	if (Flow == EIronStrategyFlow::Running)
	{
		(void)HandleSpeed(SpeedIndex == 0 ? FMath::Clamp(ResumeSpeedIndex, 1, IronStrategyScreenDetail::SpeedSteps - 1) : 0);
		return true;
	}
	return false;
}

// -------------------------------------------------------------------------------------------------
// Turn flow
// -------------------------------------------------------------------------------------------------

bool SIronStrategyScreen::IsRootModalOpen() const
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	return RootPtr.IsValid() && RootPtr->HasModal();
}

float SIronStrategyScreen::SpeedMultiplier() const
{
	const int32 Index = FMath::Clamp(SpeedIndex, 0, IronStrategyScreenDetail::SpeedSteps - 1);
	return IronStrategyScreenDetail::SpeedFactors[Index];
}

float SIronStrategyScreen::GetFractionalDay() const
{
	return Flow == EIronStrategyFlow::Running ? FMath::Clamp(DayFraction, 0.0f, 1.0f) : 0.0f;
}

void SIronStrategyScreen::SyncFlowWithGame()
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	const IronSim::FGameState& GameState = Session->State();
	if (GameState.Outcome != IronSim::EOutcome::None || GameState.Phase == IronSim::EPhase::GameOver)
	{
		Flow = EIronStrategyFlow::GameOver;
		return;
	}
	switch (Flow)
	{
	case EIronStrategyFlow::Planning:
		if (GameState.Phase == IronSim::EPhase::Execution)
		{
			Flow = EIronStrategyFlow::Running;
			DayFraction = 0.0f;
		}
		break;
	case EIronStrategyFlow::Running:
		if (GameState.Phase == IronSim::EPhase::Planning)
		{
			Flow = EIronStrategyFlow::Planning;
			DayFraction = 0.0f;
		}
		break;
	case EIronStrategyFlow::GameOver:
		Flow = GameState.Phase == IronSim::EPhase::Execution ? EIronStrategyFlow::Running : EIronStrategyFlow::Planning;
		break;
	case EIronStrategyFlow::BattlePrompt:
	case EIronStrategyFlow::InBattle:
	case EIronStrategyFlow::BattleReport:
		break;
	}
}

EActiveTimerReturnType SIronStrategyScreen::HandleTick(double InCurrentTime, float InDeltaTime)
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return EActiveTimerReturnType::Continue;
	}
	const float Delta = FMath::Clamp(InDeltaTime, 0.0f, 0.1f);
	if (Flow == EIronStrategyFlow::Running)
	{
		AdvanceExecution(Delta);
	}
	WatchSeconds += Delta;
	if (WatchSeconds >= 0.25f)
	{
		WatchSeconds = 0.0f;
		WatchFlow();
	}
	return EActiveTimerReturnType::Continue;
}

void SIronStrategyScreen::WatchFlow()
{
	SyncFlowWithGame();
	const bool bModal = IsRootModalOpen();
	switch (Flow)
	{
	case EIronStrategyFlow::Planning:
		if (!bModal)
		{
			PumpPlanningModals();
		}
		break;
	case EIronStrategyFlow::BattlePrompt:
		// The prompt was closed without an answer (e.g. Escape): ask again.
		if (!bModal)
		{
			ShowBattlePrompt();
		}
		break;
	case EIronStrategyFlow::BattleReport:
		if (!bModal)
		{
			Flow = EIronStrategyFlow::Running;
		}
		break;
	case EIronStrategyFlow::GameOver:
		if (!bModal)
		{
			ShowGameOver();
		}
		break;
	case EIronStrategyFlow::InBattle:
		// We are only painted (and ticked) when the battle screen is gone; recover if its callback never came.
		InBattleSeconds += 0.25f;
		if (InBattleSeconds > 1.0f)
		{
			InBattleSeconds = 0.0f;
			const bool bStillPending = Session->Game().PendingPlayerBattle() != nullptr;
			Flow = bStillPending ? EIronStrategyFlow::BattlePrompt : EIronStrategyFlow::Running;
		}
		break;
	case EIronStrategyFlow::Running:
		break;
	}
	if (!IsRootModalOpen())
	{
		EnsureFocus();
	}
}

void SIronStrategyScreen::EnsureFocus()
{
	if (!FSlateApplication::IsInitialized() || !MapView.IsValid())
	{
		return;
	}
	if (HasKeyboardFocus() || HasFocusedDescendants())
	{
		return;
	}
	TSharedPtr<SWidget> Focused = FSlateApplication::Get().GetKeyboardFocusedWidget();
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	const bool bRootOrNothing = !Focused.IsValid() || (RootPtr.IsValid() && Focused.Get() == static_cast<SWidget*>(RootPtr.Get()));
	if (bRootOrNothing)
	{
		FSlateApplication::Get().SetKeyboardFocus(MapView, EFocusCause::SetDirectly);
	}
}

void SIronStrategyScreen::AdvanceExecution(float DeltaSeconds)
{
	if (IsRootModalOpen())
	{
		return;
	}
	const float Multiplier = SpeedMultiplier();
	if (Multiplier <= 0.0f)
	{
		return;
	}
	// A day interrupted by a player battle simply continues with the next Step().
	DayFraction += DeltaSeconds * FMath::Max(0.1f, Session->GetDaysPerSecond()) * Multiplier;
	if (DayFraction >= 1.0f)
	{
		DayFraction = FMath::Min(DayFraction - 1.0f, 0.95f);
		StepDay();
	}
}

void SIronStrategyScreen::StepDay()
{
	IronSim::FGame& Game = Session->Game();
	const IronSim::EStepResult Result = Game.Step();
	switch (Result)
	{
	case IronSim::EStepResult::Idle:
		DayFraction = 0.0f;
		if (Game.IsPlanning())
		{
			Flow = EIronStrategyFlow::Planning;
		}
		break;
	case IronSim::EStepResult::DayAdvanced:
		break;
	case IronSim::EStepResult::PlayerBattle:
		DayFraction = 0.0f;
		Flow = EIronStrategyFlow::BattlePrompt;
		break;
	case IronSim::EStepResult::MonthEnded:
		DayFraction = 0.0f;
		OnMonthEnded();
		break;
	case IronSim::EStepResult::GameOver:
		DayFraction = 0.0f;
		Flow = EIronStrategyFlow::GameOver;
		break;
	}
	SyncFlowWithGame();
	Session->NotifyStateChanged();

	switch (Flow)
	{
	case EIronStrategyFlow::BattlePrompt:
		ShowBattlePrompt();
		break;
	case EIronStrategyFlow::Planning:
		PumpPlanningModals();
		break;
	case EIronStrategyFlow::GameOver:
		ShowGameOver();
		break;
	case EIronStrategyFlow::Running:
	case EIronStrategyFlow::InBattle:
	case EIronStrategyFlow::BattleReport:
		break;
	}
}

void SIronStrategyScreen::OnMonthEnded()
{
	Flow = EIronStrategyFlow::Planning;
	HandledPrisoners.Reset();
	Session->AutoSave();
}

int32 SIronStrategyScreen::NextPendingPrisoner() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return -1;
	}
	const IronSim::FGameState& GameState = Session->State();
	for (const int Prisoner : GameState.PendingPrisoners)
	{
		const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Prisoner);
		if (Data && Data->Status == IronSim::EOfficerStatus::Prisoner && !HandledPrisoners.Contains(Prisoner))
		{
			return Prisoner;
		}
	}
	return -1;
}

void SIronStrategyScreen::PumpPlanningModals()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid() || !Session.IsValid() || !Session->HasGame() || RootPtr->HasModal())
	{
		return;
	}
	const IronSim::FGameState& GameState = Session->State();
	if (GameState.Outcome != IronSim::EOutcome::None)
	{
		Flow = EIronStrategyFlow::GameOver;
		ShowGameOver();
		return;
	}
	if (!Session->Game().IsPlanning())
	{
		return;
	}
	const int32 MonthKey = GameState.Year * 12 + GameState.Month;
	if (MonthKey != HandledPrisonersMonth)
	{
		HandledPrisonersMonth = MonthKey;
		HandledPrisoners.Reset();
	}
	if (Session->Game().CurrentEvent() != nullptr)
	{
		ShowEventModal();
		return;
	}
	const int32 Prisoner = NextPendingPrisoner();
	if (Prisoner >= 0)
	{
		ShowPrisonerModal(Prisoner);
	}
}

void SIronStrategyScreen::ShowEventModal()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid())
	{
		return;
	}
	TWeakPtr<SIronStrategyScreen> WeakSelf = SharedThis(this);
	FIronAudio::Get().PlaySfx(TEXT("Event"));
	// Events must be answered: Escape does not close them.
	RootPtr->PushModalWithEscape(SNew(SIronEventDialog)
		.Session(Session)
		.OnChoose([WeakSelf](int32 ChoiceIndex)
		{
			if (TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin())
			{
				Self->HandleEventChoice(ChoiceIndex);
			}
		}), nullptr);
}

void SIronStrategyScreen::HandleEventChoice(int32 ChoiceIndex)
{
	if (Session.IsValid() && Session->HasGame() && Session->Game().CurrentEvent() != nullptr)
	{
		Session->Game().ChooseEventOption(ChoiceIndex);
	}
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->PopModal();
	}
	if (Session.IsValid())
	{
		Session->NotifyStateChanged();
	}
	PumpPlanningModals();
}

void SIronStrategyScreen::ShowPrisonerModal(int32 Prisoner)
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid())
	{
		return;
	}
	TWeakPtr<SIronStrategyScreen> WeakSelf = SharedThis(this);
	RootPtr->PushModalWithEscape(SNew(SIronPrisonerDialog)
		.Session(Session)
		.Prisoner(Prisoner)
		.OnDecided([WeakSelf](int32 Decided, const FText& Message)
		{
			if (TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin())
			{
				Self->HandlePrisonerDecided(Decided, Message);
			}
		}), nullptr);
}

void SIronStrategyScreen::HandlePrisonerDecided(int32 Prisoner, const FText& Message)
{
	HandledPrisoners.Add(Prisoner);
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid())
	{
		return;
	}
	RootPtr->PopModal();
	if (Session.IsValid())
	{
		Session->NotifyStateChanged();
	}
	if (Message.IsEmpty())
	{
		PumpPlanningModals();
		return;
	}
	const FText Title = (Session.IsValid() && Session->HasGame()) ? IronStrategy::OfficerName(Session->State(), Prisoner) : IronUI::Loc("ui.strategy.prisonerTitle", "Prisoner");
	TWeakPtr<SIronStrategyScreen> WeakSelf = SharedThis(this);
	RootPtr->ShowMessage(Title, Message, [WeakSelf]()
	{
		if (TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin())
		{
			Self->PumpPlanningModals();
		}
	});
}

void SIronStrategyScreen::ShowBattlePrompt()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid() || RootPtr->HasModal() || !Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	IronSim::FGame& Game = Session->Game();
	const IronSim::FPendingBattle* Pending = Game.PendingPlayerBattle();
	if (Pending == nullptr)
	{
		Flow = EIronStrategyFlow::Running;
		return;
	}
	const IronSim::FPendingBattle Battle = *Pending;
	const IronSim::FBattleSetup Setup = Game.MakeBattleSetup(Battle);
	const bool bAttacker = Game.IsPlayerAttacker(Battle);
	const int32 BesiegedCity = Battle.Kind == IronSim::EBattleKind::Siege ? Battle.City : -1;
	if (BesiegedCity >= 0 && MapView.IsValid())
	{
		MapView->CenterOnCity(BesiegedCity);
	}

	TWeakPtr<SIronStrategyScreen> WeakSelf = SharedThis(this);
	RootPtr->PushModalWithEscape(SNew(SIronBattlePrompt)
		.Session(Session)
		.Setup(Setup)
		.City(BesiegedCity)
		.PlayerAttacker(bAttacker)
		.OnCommand([WeakSelf]()
		{
			if (TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin())
			{
				Self->StartPlayerBattle();
			}
		})
		.OnDelegate([WeakSelf]()
		{
			if (TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin())
			{
				Self->DelegatePlayerBattle();
			}
		}), nullptr);
}

void SIronStrategyScreen::StartPlayerBattle()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid())
	{
		return;
	}
	RootPtr->PopModal();
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	const IronSim::FPendingBattle* Pending = Session->Game().PendingPlayerBattle();
	if (Pending == nullptr)
	{
		Flow = EIronStrategyFlow::Running;
		return;
	}
	const IronSim::FBattleSetup Setup = Session->Game().MakeBattleSetup(*Pending);
	Flow = EIronStrategyFlow::InBattle;
	InBattleSeconds = 0.0f;
	RootPtr->ShowBattle(Setup, FOnIronBattleFinished::CreateSP(this, &SIronStrategyScreen::HandleBattleFinished));
}

void SIronStrategyScreen::HandleBattleFinished(const IronSim::FBattleResult& Result)
{
	if (Session.IsValid() && Session->HasGame() && Session->Game().PendingPlayerBattle() != nullptr)
	{
		Session->Game().ResolvePlayerBattle(Result);
	}
	Flow = EIronStrategyFlow::Running;
	DayFraction = 0.0f;
	InBattleSeconds = 0.0f;
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->ShowStrategy();
	}
	if (Session.IsValid())
	{
		Session->NotifyStateChanged();
	}
	SyncFlowWithGame();
}

SIronStrategyScreen::FLogMark SIronStrategyScreen::MarkLog() const
{
	FLogMark Mark;
	if (Session.IsValid() && Session->HasGame())
	{
		const IronSim::FGameState& GameState = Session->State();
		Mark.Size = static_cast<int32>(GameState.Log.size());
		if (!GameState.Log.empty())
		{
			Mark.LastText = GameState.Log.back().Text;
		}
	}
	return Mark;
}

FText SIronStrategyScreen::CollectNewLog(const FLogMark& Mark, int32 MaxLines) const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return FText::GetEmpty();
	}
	const IronSim::FGameState& GameState = Session->State();
	const int32 Count = static_cast<int32>(GameState.Log.size());
	int32 Start = Mark.Size;
	if (Mark.Size >= IronSim::MaxLogEntries || Start > Count)
	{
		// The chronicle is capped and drops old entries: find where the snapshot ended instead.
		Start = Count;
		for (int32 Index = Count - 1; Index >= 0; --Index)
		{
			if (GameState.Log[static_cast<size_t>(Index)].Text == Mark.LastText)
			{
				Start = Index + 1;
				break;
			}
		}
	}
	FString Lines;
	int32 Added = 0;
	for (int32 Index = Start; Index < Count && Added < MaxLines; ++Index)
	{
		const IronSim::FLogEntry& Entry = GameState.Log[static_cast<size_t>(Index)];
		if (Entry.Faction != GameState.PlayerFaction && !Entry.bImportant)
		{
			continue;
		}
		if (!Lines.IsEmpty())
		{
			Lines += TEXT("\n");
		}
		Lines += IronUI::ToFString(Entry.Text);
		++Added;
	}
	return FText::FromString(Lines);
}

void SIronStrategyScreen::DelegatePlayerBattle()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid())
	{
		return;
	}
	RootPtr->PopModal();
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	const FLogMark Mark = MarkLog();
	if (Session->Game().PendingPlayerBattle() != nullptr)
	{
		Session->Game().AutoResolvePlayerBattle();
	}
	FText Report = CollectNewLog(Mark, 8);
	if (Report.IsEmpty())
	{
		Report = IronUI::Loc("ui.strategy.battleDelegated", "Your generals have fought the battle.");
	}
	Flow = EIronStrategyFlow::BattleReport;
	DayFraction = 0.0f;
	Session->NotifyStateChanged();
	SyncFlowWithGame();

	TWeakPtr<SIronStrategyScreen> WeakSelf = SharedThis(this);
	RootPtr->ShowMessage(IronUI::Loc("ui.strategy.battleReport", "Battle Report"), Report, [WeakSelf]()
	{
		TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin();
		if (Self.IsValid() && Self->Flow == EIronStrategyFlow::BattleReport)
		{
			Self->Flow = EIronStrategyFlow::Running;
			Self->SyncFlowWithGame();
		}
	});
}

void SIronStrategyScreen::ShowGameOver()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid() || RootPtr->HasModal())
	{
		return;
	}
	const TWeakPtr<SIronRoot> WeakRoot = Root;
	const TSharedPtr<FIronSession> SessionRef = Session;
	RootPtr->PushModalWithEscape(SNew(SIronGameOverDialog)
		.Session(Session)
		.OnReturn([WeakRoot, SessionRef]()
		{
			TSharedPtr<SIronRoot> Pinned = WeakRoot.Pin();
			if (!Pinned.IsValid())
			{
				return;
			}
			Pinned->PopModal();
			Pinned->ShowTitle();
			if (SessionRef.IsValid())
			{
				SessionRef->EndGame();
			}
		}), nullptr);
}

// -------------------------------------------------------------------------------------------------
// Top bar actions
// -------------------------------------------------------------------------------------------------

bool SIronStrategyScreen::CanEndTurn() const
{
	return Session.IsValid() && Session->HasGame() && Flow == EIronStrategyFlow::Planning && Session->Game().IsPlanning() && !IsRootModalOpen();
}

bool SIronStrategyScreen::CanUseMenus() const
{
	return Session.IsValid() && Session->HasGame() && (Flow == EIronStrategyFlow::Planning || Flow == EIronStrategyFlow::Running) && !IsRootModalOpen();
}

FReply SIronStrategyScreen::HandleEndTurn()
{
	if (!CanEndTurn())
	{
		return FReply::Handled();
	}
	IronSim::FGame& Game = Session->Game();
	if (Game.CurrentEvent() != nullptr || NextPendingPrisoner() >= 0)
	{
		// Pending decisions must be answered first.
		PumpPlanningModals();
		return FReply::Handled();
	}
	FIronAudio::Get().PlaySfx(TEXT("EndTurn"));
	Game.EndPlanning();
	Flow = EIronStrategyFlow::Running;
	DayFraction = 0.0f;
	if (SpeedIndex == 0)
	{
		SpeedIndex = FMath::Clamp(ResumeSpeedIndex, 1, IronStrategyScreenDetail::SpeedSteps - 1);
	}
	SyncFlowWithGame();
	Session->NotifyStateChanged();
	return FReply::Handled();
}

FReply SIronStrategyScreen::HandleSpeed(int32 NewSpeedIndex)
{
	const int32 Clamped = FMath::Clamp(NewSpeedIndex, 0, IronStrategyScreenDetail::SpeedSteps - 1);
	if (Clamped == 0 && SpeedIndex != 0)
	{
		ResumeSpeedIndex = SpeedIndex;
	}
	SpeedIndex = Clamped;
	return FReply::Handled();
}

FReply SIronStrategyScreen::HandleOfficers()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid() || !CanUseMenus())
	{
		return FReply::Handled();
	}
	TWeakPtr<SIronStrategyScreen> WeakSelf = SharedThis(this);
	RootPtr->PushModal(SNew(SIronOfficerTable)
		.Session(Session)
		.Root(Root)
		.OnShowCity([WeakSelf](int32 ShownCity)
		{
			TSharedPtr<SIronStrategyScreen> Self = WeakSelf.Pin();
			if (Self.IsValid())
			{
				Self->SelectCity(ShownCity);
				if (Self->MapView.IsValid())
				{
					Self->MapView->CenterOnCity(ShownCity);
				}
			}
		}));
	return FReply::Handled();
}

FReply SIronStrategyScreen::HandleFactions()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanUseMenus())
	{
		RootPtr->PushModal(SNew(SIronFactionsPanel).Session(Session).Root(Root));
	}
	return FReply::Handled();
}

FReply SIronStrategyScreen::HandleSave()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanEndTurn())
	{
		RootPtr->ShowSaveLoad(true);
	}
	return FReply::Handled();
}

FReply SIronStrategyScreen::HandleLoad()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanUseMenus())
	{
		RootPtr->ShowSaveLoad(false);
	}
	return FReply::Handled();
}

FReply SIronStrategyScreen::HandleSettings()
{
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->ShowSettings();
	}
	return FReply::Handled();
}
