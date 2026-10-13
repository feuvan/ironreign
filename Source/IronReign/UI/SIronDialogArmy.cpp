#include "UI/SIronDialogArmy.h"

#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronRoot.h"
#include "UI/SIronStrategyCommon.h"

#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

void SIronArmyDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;

	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	if (bValid)
	{
		const IronSim::FGame& Game = Session->Game();
		for (const int Officer : Game.IdleOfficers(CityIndex))
		{
			Candidates.Add(Officer);
		}
		const TSharedPtr<FIronSession> SessionRef = Session;
		Candidates.Sort([SessionRef](const int32& Left, const int32& Right)
		{
			const IronSim::FOfficer* LeftData = IronStrategy::GetOfficer(SessionRef->State(), Left);
			const IronSim::FOfficer* RightData = IronStrategy::GetOfficer(SessionRef->State(), Right);
			const int32 LeftValue = LeftData ? LeftData->GetStat(IronSim::EStat::Command) + LeftData->GetStat(IronSim::EStat::Martial) : 0;
			const int32 RightValue = RightData ? RightData->GetStat(IronSim::EStat::Command) + RightData->GetStat(IronSim::EStat::Martial) : 0;
			return LeftValue > RightValue;
		});
		for (const int Target : Game.MarchTargets(CityIndex))
		{
			Targets.Add(Target);
		}
		SelectedTarget = Targets.Num() > 0 ? Targets[0] : -1;
		if (InArgs._PresetTarget >= 0 && Targets.Contains(InArgs._PresetTarget))
		{
			SelectedTarget = InArgs._PresetTarget;
		}
		if (Candidates.Num() > 0)
		{
			Chosen.Add(Candidates[0]);
		}
		SuggestTroops();
		SuggestFood();
	}

	TSharedRef<SVerticalBox> OfficerList = SNew(SVerticalBox);
	if (Candidates.Num() == 0)
	{
		OfficerList->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noIdleOfficers", "No idle officers remain in this city this month."), 15.0f, IronStyle::InkSoft())
		];
	}
	for (const int32 Officer : Candidates)
	{
		OfficerList->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			BuildOfficerRow(Officer)
		];
	}

	TSharedRef<SVerticalBox> TargetList = SNew(SVerticalBox);
	if (Targets.Num() == 0)
	{
		TargetList->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noMarchTargets", "No city can be reached from here."), 15.0f, IronStyle::InkSoft())
		];
	}
	for (const int32 Target : Targets)
	{
		TargetList->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			BuildTargetRow(Target)
		];
	}

	const TSharedRef<SWidget> LeftColumn = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeSectionTitle(IronUI::LocF("ui.strategy.armyOfficers", "Officers (up to {count})", {{"count", IronSim::ToText(IronSim::MaxArmyUnits)}}))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(62.0f, 0.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeStatsHeader(IronSim::StatIndex(IronSim::EStat::Command), 11.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				OfficerList
			]
		];

	const TSharedRef<SWidget> RightColumn = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.marchTarget", "Target"))
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				TargetList
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 0.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.troopsAndSupplies", "Troops and supplies"))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.armyTroops", "Troops"), [this]() { return TroopCapacity(); }, &TroopsValue, 100, [this]()
			{
				FoodValue = FMath::Min(FoodValue, CityFood());
			})
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.armyFood", "Food"), [this]() { return CityFood(); }, &FoodValue, 100)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this]()
			{
				const int32 Daily = DailyFood();
				const int32 Days = Daily > 0 ? FoodValue / Daily : 0;
				return IronUI::LocF("ui.strategy.armySupplyInfo", "Up to {capacity} troops can march. Food lasts {days} days ({daily} per day).", {{"capacity", IronUI::ToStd(IronStrategy::Num(TroopCapacity()).ToString())}, {"days", IronSim::ToText(Days)}, {"daily", IronSim::ToText(Daily)}});
			})
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
			.AutoWrapText(true)
		];

	const TSharedRef<SWidget> Body = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.2f)
		[
			LeftColumn
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(16.0f, 0.0f, 0.0f, 0.0f))
		[
			RightColumn
		];

	const TSharedRef<SWidget> Footer = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this]() { return SummaryText(); })
			.ColorAndOpacity_Lambda([this]()
			{
				return FSlateColor(CheckPlan().bAllowed ? IronStyle::Ink() : IronStyle::Danger());
			})
			.Font(IronStyle::BodyBold(15.0f))
			.AutoWrapText(true)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this]() { return ErrorText; })
			.ColorAndOpacity(IronStyle::Danger())
			.Font(IronStyle::Body(14.0f))
			.AutoWrapText(true)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			[
				SNew(SSpacer)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(6.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.marchButton", "March"), FOnClicked::CreateSP(this, &SIronArmyDialog::HandleMarch), TAttribute<bool>::CreateLambda([this]() { return CheckPlan().bAllowed; }), TEXT("March"), 200.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(6.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.cancel", "Cancel"), FOnClicked::CreateSP(this, &SIronArmyDialog::HandleCancel), true, FString(), 140.0f)
			]
		];

	const FText Title = IronUI::LocF("ui.strategy.armyDialogTitle", "March from {city}", {{"city", bValid ? IronUI::ToStd(IronStrategy::CityName(Session->State(), CityIndex).ToString()) : std::string()}});
	ChildSlot
	[
		IronStrategy::MakeDialogFrame(Title, Body, Footer, 1160.0f, 720.0f)
	];
}

int32 SIronArmyDialog::CityTroops() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Troops : 0;
}

int32 SIronArmyDialog::CityFood() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Food : 0;
}

int32 SIronArmyDialog::TroopCapacity() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	int32 Capacity = 0;
	for (const int32 Officer : Chosen)
	{
		Capacity += FMath::Max(0, Session->Game().MaxUnitTroops(Officer));
	}
	return FMath::Min(Capacity, CityTroops());
}

int32 SIronArmyDialog::DailyFood() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	return FMath::Max(0, Session->Game().ArmyDailyFood(TroopsValue));
}

IronSim::FArmyPlan SIronArmyDialog::MakePlan() const
{
	IronSim::FArmyPlan Plan;
	Plan.City = CityIndex;
	for (const int32 Officer : Chosen)
	{
		Plan.Officers.push_back(Officer);
	}
	Plan.Troops = TroopsValue;
	Plan.Food = FoodValue;
	Plan.Target = SelectedTarget;
	return Plan;
}

IronSim::FOrderCheck SIronArmyDialog::CheckPlan() const
{
	if (!Session.IsValid() || !Session->HasGame() || Chosen.Num() == 0 || SelectedTarget < 0)
	{
		return IronSim::FOrderCheck();
	}
	return Session->Game().CheckArmy(MakePlan());
}

void SIronArmyDialog::SuggestTroops()
{
	const int32 Capacity = TroopCapacity();
	const int32 Garrison = CityTroops();
	const int32 Suggested = (Garrison * 3 / 4 / 100) * 100;
	TroopsValue = FMath::Clamp(Suggested, FMath::Min(Capacity, 100), Capacity);
}

void SIronArmyDialog::SuggestFood()
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		FoodValue = 0;
		return;
	}
	const int32 March = SelectedTarget >= 0 ? FMath::Max(0, Session->Game().MarchDays(CityIndex, SelectedTarget)) : 10;
	const int32 Days = March + 20;
	const int32 Wanted = DailyFood() * Days;
	FoodValue = FMath::Clamp(((Wanted + 99) / 100) * 100, 0, CityFood());
}

void SIronArmyDialog::ToggleOfficer(int32 Officer)
{
	ErrorText = FText::GetEmpty();
	if (Chosen.Contains(Officer))
	{
		(void)Chosen.Remove(Officer);
	}
	else if (Chosen.Num() < IronSim::MaxArmyUnits)
	{
		Chosen.Add(Officer);
	}
	else
	{
		ErrorText = IronUI::LocF("ui.strategy.armyFull", "An army has at most {count} officers.", {{"count", IronSim::ToText(IronSim::MaxArmyUnits)}});
		return;
	}
	SuggestTroops();
	SuggestFood();
}

void SIronArmyDialog::MakeCommander(int32 Officer)
{
	if (Chosen.Contains(Officer))
	{
		(void)Chosen.Remove(Officer);
		(void)Chosen.Insert(Officer, 0);
	}
}

void SIronArmyDialog::SelectTarget(int32 Target)
{
	SelectedTarget = Target;
	ErrorText = FText::GetEmpty();
	SuggestFood();
}

TSharedRef<SWidget> SIronArmyDialog::BuildOfficerRow(int32 Officer)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	const FText Name = IronUI::ToText(IronSim::NameOf(*Data));
	const FText Subline = IronUI::LocF("ui.strategy.unitCapacity", "{troop} - up to {troops} troops", {{"troop", IronSim::DisplayName(Data->Specialty)}, {"troops", IronUI::ToStd(IronStrategy::Num(Session->Game().MaxUnitTroops(Officer)).ToString())}});

	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		[
			SNew(SButton)
			.ButtonStyle(&IronStyle::RowButton())
			.IsFocusable(false)
			.ContentPadding(FMargin(1.0f))
			.OnClicked_Lambda([this, Officer]()
			{
				ToggleOfficer(Officer);
				return FReply::Handled();
			})
			[
				SNew(SBorder)
				.BorderImage(IronStyle::WhiteBrush())
				.BorderBackgroundColor_Lambda([this, Officer]()
				{
					const int32 Position = Chosen.Find(Officer);
					if (Position == 0)
					{
						return FSlateColor(IronStyle::Lacquer().CopyWithNewOpacity(0.35f));
					}
					return FSlateColor(Position > 0 ? IronStyle::Gold().CopyWithNewOpacity(0.4f) : IronStyle::Paper().CopyWithNewOpacity(0.0f));
				})
				.Padding(FMargin(4.0f, 3.0f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
					[
						IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Officer), 56.0f)
					]
					+ SHorizontalBox::Slot()
					.FillWidth(1.0f)
					.VAlign(VAlign_Center)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(SHorizontalBox)
							+ SHorizontalBox::Slot()
							.AutoWidth()
							[
								SNew(STextBlock)
								.Text(Name)
								.Font(IronStyle::BodyBold(15.0f))
								.ColorAndOpacity(IronStyle::Ink())
							]
							+ SHorizontalBox::Slot()
							.AutoWidth()
							.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
							[
								SNew(STextBlock)
								.Text_Lambda([this, Officer]()
								{
									const int32 Position = Chosen.Find(Officer);
									if (Position == 0)
									{
										return IronUI::Loc("ui.strategy.roleCommander", "Commander");
									}
									if (Position > 0)
									{
										return IronUI::LocF("ui.strategy.roleDeputy", "Deputy {n}", {{"n", IronSim::ToText(Position)}});
									}
									return FText::GetEmpty();
								})
								.Font(IronStyle::BodyBold(13.0f))
								.ColorAndOpacity(IronStyle::Lacquer())
							]
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							IronStrategy::MakeStatsRow(*Data, IronSim::StatIndex(IronSim::EStat::Command), 13.0f)
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(STextBlock)
							.Text(Subline)
							.Font(IronStyle::Body(12.0f))
							.ColorAndOpacity(IronStyle::InkSoft())
						]
					]
				]
			]
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(4.0f, 0.0f, 0.0f, 0.0f))
		[
			SNew(SBox)
			.Visibility_Lambda([this, Officer]()
			{
				return Chosen.Find(Officer) > 0 ? EVisibility::Visible : EVisibility::Hidden;
			})
			[
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.makeCommander", "Lead"), FOnClicked::CreateLambda([this, Officer]()
				{
					MakeCommander(Officer);
					return FReply::Handled();
				}))
			]
		];
}

TSharedRef<SWidget> SIronArmyDialog::BuildTargetRow(int32 Target)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FCity* Data = IronStrategy::GetCity(GameState, Target);
	if (!Data)
	{
		return SNew(SBox);
	}
	const bool bOwn = Data->Owner == GameState.PlayerFaction;
	const int32 Days = Session->Game().MarchDays(CityIndex, Target);
	const FText Name = IronUI::ToText(IronSim::NameOf(*Data));
	FText Detail;
	if (bOwn)
	{
		Detail = IronUI::LocF("ui.strategy.marchOwnDetail", "Our city - {days} days - troops {troops}", {{"days", IronSim::ToText(Days)}, {"troops", IronUI::ToStd(IronStrategy::Num(Data->Troops).ToString())}});
	}
	else
	{
		Detail = IronUI::LocF("ui.strategy.marchEnemyDetail", "{faction} - {days} days - troops {troops} - defense {defense}", {{"faction", IronUI::ToStd(IronStrategy::FactionName(GameState, Data->Owner).ToString())}, {"days", IronSim::ToText(Days)}, {"troops", IronUI::ToStd(IronStrategy::ApproxNum(Data->Troops).ToString())}, {"defense", IronSim::ToText(Data->Defense)}});
	}

	TSharedRef<SWidget> Leading = SNew(SBox)
		.WidthOverride(30.0f)
		.HeightOverride(40.0f)
		[
			SNew(SImage)
			.Image(IronStyle::WhiteBrush())
			.ColorAndOpacity(IronStyle::FactionColor(Data->Owner))
		];
	if (Data->Owner >= 0)
	{
		Leading = IronStyle::MakeBanner(Data->Owner, 40.0f);
	}

	return SNew(SButton)
		.ButtonStyle(&IronStyle::RowButton())
		.IsFocusable(false)
		.ContentPadding(FMargin(1.0f))
		.OnClicked_Lambda([this, Target]()
		{
			SelectTarget(Target);
			return FReply::Handled();
		})
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor_Lambda([this, Target]()
			{
				return FSlateColor(SelectedTarget == Target ? IronStyle::Gold().CopyWithNewOpacity(0.45f) : IronStyle::Paper().CopyWithNewOpacity(0.0f));
			})
			.Padding(FMargin(4.0f, 3.0f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
				[
					Leading
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				.VAlign(VAlign_Center)
				[
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(Name)
						.Font(IronStyle::BodyBold(15.0f))
						.ColorAndOpacity(bOwn ? IronStyle::Jade() : IronStyle::Ink())
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(Detail)
						.Font(IronStyle::Body(12.0f))
						.ColorAndOpacity(IronStyle::InkSoft())
						.AutoWrapText(true)
					]
				]
			]
		];
}

FText SIronArmyDialog::SummaryText() const
{
	if (Chosen.Num() == 0)
	{
		return IronUI::Loc("ui.strategy.pickCommander", "Choose a commander.");
	}
	if (SelectedTarget < 0)
	{
		return IronUI::Loc("ui.strategy.pickTarget", "Choose a target.");
	}
	const IronSim::FOrderCheck Result = CheckPlan();
	if (!Result.bAllowed)
	{
		return IronUI::ToText(Result.Reason);
	}
	const int32 Days = Session->Game().MarchDays(CityIndex, SelectedTarget);
	return IronUI::LocF("ui.strategy.armyPreview", "{preview} - {troops} troops reach {city} in about {days} days.", {{"preview", Result.Preview}, {"troops", IronUI::ToStd(IronStrategy::Num(TroopsValue).ToString())}, {"city", IronUI::ToStd(IronStrategy::CityName(Session->State(), SelectedTarget).ToString())}, {"days", IronSim::ToText(Days)}});
}

FReply SIronArmyDialog::HandleMarch()
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return FReply::Handled();
	}
	std::string Error;
	if (Session->Game().FormArmy(MakePlan(), Error))
	{
		FIronAudio::Get().PlaySfx(TEXT("March"));
		Session->NotifyStateChanged();
		CloseDialog();
		return FReply::Handled();
	}
	ErrorText = Error.empty() ? IronUI::Loc("ui.strategy.armyFailed", "The army could not be formed.") : IronUI::ToText(Error);
	return FReply::Handled();
}

FReply SIronArmyDialog::HandleCancel()
{
	FIronAudio::Get().PlaySfx(TEXT("Cancel"));
	CloseDialog();
	return FReply::Handled();
}

void SIronArmyDialog::CloseDialog()
{
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->PopModal();
	}
}
