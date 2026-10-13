#include "UI/SIronDialogOrder.h"

#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
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

namespace IronDialogOrderDetail
{
	FText RelationText(const IronSim::FGameState& State, int32 Faction)
	{
		const IronSim::FRelation& Relation = State.Relation(State.PlayerFaction, Faction);
		std::string Status;
		if (Relation.AllianceMonths > 0)
		{
			Status = IronSim::LocF("ui.strategy.allied", "Allied ({months} months)", {{"months", IronSim::ToText(Relation.AllianceMonths)}});
		}
		else if (Relation.TruceMonths > 0)
		{
			Status = IronSim::LocF("ui.strategy.truce", "Truce ({months} months)", {{"months", IronSim::ToText(Relation.TruceMonths)}});
		}
		else
		{
			Status = IronSim::Loc("ui.strategy.hostile", "Hostile");
		}
		return IronUI::LocF("ui.strategy.trustStatus", "Trust {trust}   {status}", {{"trust", IronSim::ToText(Relation.Trust)}, {"status", Status}});
	}
}

void SIronOrderDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;
	OrderKind = InArgs._OrderType;
	Governing = IronStrategy::GoverningStat(OrderKind);

	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	if (bValid)
	{
		const IronSim::FGame& Game = Session->Game();
		for (const int Officer : Game.IdleOfficers(CityIndex))
		{
			Officers.Add(Officer);
		}
		if (Governing >= 0)
		{
			const TSharedPtr<FIronSession> SessionRef = Session;
			const int32 StatSlot = Governing;
			Officers.Sort([SessionRef, StatSlot](const int32& Left, const int32& Right)
			{
				const IronSim::FOfficer* LeftData = IronStrategy::GetOfficer(SessionRef->State(), Left);
				const IronSim::FOfficer* RightData = IronStrategy::GetOfficer(SessionRef->State(), Right);
				const int32 LeftValue = LeftData ? LeftData->Stats[StatSlot] : 0;
				const int32 RightValue = RightData ? RightData->Stats[StatSlot] : 0;
				return LeftValue > RightValue;
			});
		}

		std::vector<int> TargetList;
		switch (GetTargetKind())
		{
		case ETargetKind::Officer:
			TargetList = Game.RecruitTargets(CityIndex);
			break;
		case ETargetKind::City:
			TargetList = Game.MoveDestinations(CityIndex);
			break;
		case ETargetKind::Sect:
			TargetList = Game.SectsNear(CityIndex);
			break;
		case ETargetKind::Faction:
			TargetList = Game.DiplomacyTargets();
			break;
		case ETargetKind::None:
			break;
		}
		for (const int Target : TargetList)
		{
			Targets.Add(Target);
		}

		SelectedOfficer = Officers.Num() > 0 ? Officers[0] : -1;
		SelectedTarget = Targets.Num() > 0 ? Targets[0] : -1;
		if (InArgs._PresetTarget >= 0 && Targets.Contains(InArgs._PresetTarget))
		{
			SelectedTarget = InArgs._PresetTarget;
		}

		if (OrderKind == IronSim::EOrderType::Draft)
		{
			const int32 Capacity = FMath::Max(0, Game.DraftCapacity(CityIndex));
			AmountValue = FMath::Min(Capacity, FMath::Max(100, (Capacity / 2 / 100) * 100));
		}
		else if (OrderKind == IronSim::EOrderType::Gift)
		{
			GoldValue = FMath::Min(CityGold(), 500);
		}
	}

	const FText Title = IronUI::LocF("ui.strategy.orderDialogTitle", "{order}: {city}", {{"order", IronSim::DisplayName(OrderKind)}, {"city", bValid ? IronUI::ToStd(IronStrategy::CityName(Session->State(), CityIndex).ToString()) : std::string()}});

	FText Hint;
	if (Governing >= 0)
	{
		Hint = IronUI::LocF("ui.strategy.governedBy", "Best suited to officers with high {stat}.", {{"stat", IronUI::ToStd(IronStrategy::StatLong(Governing).ToString())}});
	}
	else
	{
		Hint = IronUI::Loc("ui.strategy.anyOfficer", "Any idle officer can carry out this order.");
	}

	const bool bRightColumn = GetTargetKind() != ETargetKind::None || HasAmounts();
	TSharedRef<SHorizontalBox> Columns = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.25f)
		[
			BuildOfficerList()
		];
	if (bRightColumn)
	{
		TSharedRef<SVerticalBox> Right = SNew(SVerticalBox);
		if (GetTargetKind() != ETargetKind::None)
		{
			Right->AddSlot()
			.FillHeight(1.0f)
			[
				BuildTargetList()
			];
		}
		if (HasAmounts())
		{
			Right->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 10.0f, 0.0f, 0.0f))
			[
				BuildAmounts()
			];
		}
		Columns->AddSlot()
		.FillWidth(1.0f)
		.Padding(FMargin(16.0f, 0.0f, 0.0f, 0.0f))
		[
			Right
		];
	}

	const TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 8.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				IronStrategy::MakeWrappedText(Hint, 14.0f, IronStyle::InkSoft())
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
			[
				IronStyle::MakeIconValue(TEXT("Gold"), TAttribute<FText>::CreateLambda([this]() { return IronStrategy::Num(CityGold()); }), 22.0f)
			]
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			Columns
		];

	const TSharedRef<SWidget> Footer = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this]() { return SummaryText(); })
			.ColorAndOpacity_Lambda([this]() { return SummaryColor(); })
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
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.issueOrder", "Issue Order"), FOnClicked::CreateSP(this, &SIronOrderDialog::HandleIssue), TAttribute<bool>::CreateLambda([this]()
				{
					return SelectedOfficer >= 0 && CheckFor(SelectedOfficer).bAllowed;
				}), IronStrategy::OrderIcon(OrderKind), 200.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(6.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.cancel", "Cancel"), FOnClicked::CreateSP(this, &SIronOrderDialog::HandleCancel), true, FString(), 140.0f)
			]
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(Title, Body, Footer, bRightColumn ? 1120.0f : 800.0f, 680.0f)
	];
}

SIronOrderDialog::ETargetKind SIronOrderDialog::GetTargetKind() const
{
	switch (OrderKind)
	{
	case IronSim::EOrderType::Recruit:
		return ETargetKind::Officer;
	case IronSim::EOrderType::Move:
	case IronSim::EOrderType::Transport:
		return ETargetKind::City;
	case IronSim::EOrderType::SectTraining:
		return ETargetKind::Sect;
	case IronSim::EOrderType::Alliance:
	case IronSim::EOrderType::Truce:
	case IronSim::EOrderType::Gift:
		return ETargetKind::Faction;
	default:
		return ETargetKind::None;
	}
}

bool SIronOrderDialog::HasAmounts() const
{
	return OrderKind == IronSim::EOrderType::Draft || OrderKind == IronSim::EOrderType::Transport || OrderKind == IronSim::EOrderType::Gift;
}

int32 SIronOrderDialog::CityGold() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Gold : 0;
}

int32 SIronOrderDialog::CityFood() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Food : 0;
}

int32 SIronOrderDialog::CityTroops() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Troops : 0;
}

IronSim::FOrder SIronOrderDialog::MakeOrder(int32 Officer) const
{
	IronSim::FOrder Order;
	Order.Type = OrderKind;
	Order.Officer = Officer;
	Order.City = CityIndex;
	switch (GetTargetKind())
	{
	case ETargetKind::Officer:
		Order.TargetOfficer = SelectedTarget;
		break;
	case ETargetKind::City:
		Order.TargetCity = SelectedTarget;
		break;
	case ETargetKind::Faction:
		Order.TargetFaction = SelectedTarget;
		break;
	case ETargetKind::Sect:
		Order.TargetSect = SelectedTarget;
		break;
	case ETargetKind::None:
		break;
	}
	if (OrderKind == IronSim::EOrderType::Draft)
	{
		Order.Amount = AmountValue;
	}
	else if (OrderKind == IronSim::EOrderType::Transport)
	{
		Order.Gold = GoldValue;
		Order.Food = FoodValue;
		Order.Troops = TroopsValue;
	}
	else if (OrderKind == IronSim::EOrderType::Gift)
	{
		Order.Gold = GoldValue;
	}
	return Order;
}

IronSim::FOrderCheck SIronOrderDialog::CheckFor(int32 Officer) const
{
	if (!Session.IsValid() || !Session->HasGame() || Officer < 0)
	{
		return IronSim::FOrderCheck();
	}
	return Session->Game().CheckOrder(MakeOrder(Officer));
}

TSharedRef<SWidget> SIronOrderDialog::BuildOfficerList()
{
	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	if (Officers.Num() == 0)
	{
		List->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noIdleOfficers", "No idle officers remain in this city this month."), 15.0f, IronStyle::InkSoft())
		];
	}
	for (const int32 Officer : Officers)
	{
		List->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			BuildOfficerRow(Officer)
		];
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.chooseOfficer", "Officer"))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(62.0f, 0.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeStatsHeader(Governing, 11.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				List
			]
		];
}

TSharedRef<SWidget> SIronOrderDialog::BuildOfficerRow(int32 Officer)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	const FText Name = IronUI::ToText(IronSim::NameOf(*Data));
	const FText Specialty = IronUI::LocF("ui.strategy.officerSubline", "{troop} - Loyalty {loyalty}", {{"troop", IronSim::DisplayName(Data->Specialty)}, {"loyalty", IronSim::ToText(Data->Loyalty)}});

	return SNew(SButton)
		.ButtonStyle(&IronStyle::RowButton())
		.IsFocusable(false)
		.ContentPadding(FMargin(1.0f))
		.OnClicked_Lambda([this, Officer]()
		{
			SelectedOfficer = Officer;
			ErrorText = FText::GetEmpty();
			return FReply::Handled();
		})
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor_Lambda([this, Officer]()
			{
				return FSlateColor(SelectedOfficer == Officer ? IronStyle::Gold().CopyWithNewOpacity(0.45f) : IronStyle::Paper().CopyWithNewOpacity(0.0f));
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
						SNew(STextBlock)
						.Text(Name)
						.Font(IronStyle::BodyBold(15.0f))
						.ColorAndOpacity(IronStyle::Ink())
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						IronStrategy::MakeStatsRow(*Data, Governing, 13.0f)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(Specialty)
						.Font(IronStyle::Body(12.0f))
						.ColorAndOpacity(IronStyle::InkSoft())
					]
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
				[
					SNew(SBox)
					.WidthOverride(220.0f)
					[
						SNew(SVerticalBox)
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(STextBlock)
							.Text_Lambda([this, Officer]()
							{
								const IronSim::FOrderCheck Result = CheckFor(Officer);
								return IronUI::ToText(Result.bAllowed ? Result.Preview : Result.Reason);
							})
							.ColorAndOpacity_Lambda([this, Officer]()
							{
								return FSlateColor(CheckFor(Officer).bAllowed ? IronStyle::Jade() : IronStyle::Danger());
							})
							.Font(IronStyle::BodyBold(13.0f))
							.AutoWrapText(true)
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(STextBlock)
							.Text_Lambda([this, Officer]()
							{
								const IronSim::FOrderCheck Result = CheckFor(Officer);
								if (Result.SuccessChance >= 0)
								{
									return IronUI::LocF("ui.strategy.costAndChance", "Cost {cost}  Success {chance}%", {{"cost", IronSim::ToText(Result.Cost)}, {"chance", IronSim::ToText(Result.SuccessChance)}});
								}
								return IronUI::LocF("ui.strategy.costOnly", "Cost {cost}", {{"cost", IronSim::ToText(Result.Cost)}});
							})
							.Font(IronStyle::Body(12.0f))
							.ColorAndOpacity(IronStyle::InkSoft())
						]
					]
				]
			]
		];
}

FText SIronOrderDialog::TargetTitle(int32 Target) const
{
	const IronSim::FGameState& GameState = Session->State();
	switch (GetTargetKind())
	{
	case ETargetKind::Officer:
		return IronStrategy::OfficerName(GameState, Target);
	case ETargetKind::City:
		return IronStrategy::CityName(GameState, Target);
	case ETargetKind::Faction:
		return IronStrategy::FactionName(GameState, Target);
	case ETargetKind::Sect:
		return IronStrategy::SectName(GameState, Target);
	case ETargetKind::None:
		break;
	}
	return FText::GetEmpty();
}

FText SIronOrderDialog::TargetDetail(int32 Target) const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return FText::GetEmpty();
	}
	const IronSim::FGameState& GameState = Session->State();
	switch (GetTargetKind())
	{
	case ETargetKind::Officer:
	{
		const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Target);
		if (!Data)
		{
			return FText::GetEmpty();
		}
		std::string Where;
		if (Data->Status == IronSim::EOfficerStatus::Serving)
		{
			Where = IronSim::LocF("ui.strategy.servesFaction", "Serves {faction}, loyalty {loyalty}", {{"faction", IronUI::ToStd(IronStrategy::FactionName(GameState, Data->Faction).ToString())}, {"loyalty", IronSim::ToText(Data->Loyalty)}});
		}
		else
		{
			Where = IronSim::LocF("ui.strategy.wanderingIn", "Wandering in {city}", {{"city", IronUI::ToStd(IronStrategy::CityName(GameState, Data->City).ToString())}});
		}
		if (SelectedOfficer >= 0)
		{
			const int32 Chance = Session->Game().RecruitChance(SelectedOfficer, Target);
			return IronUI::LocF("ui.strategy.recruitTargetDetail", "{where} - chance {chance}%", {{"where", Where}, {"chance", IronSim::ToText(Chance)}});
		}
		return IronUI::ToText(Where);
	}
	case ETargetKind::City:
	{
		const IronSim::FCity* Data = IronStrategy::GetCity(GameState, Target);
		if (!Data)
		{
			return FText::GetEmpty();
		}
		return IronUI::LocF("ui.strategy.cityTargetDetail", "Gold {gold}  Food {food}  Troops {troops}", {{"gold", IronUI::ToStd(IronStrategy::Num(Data->Gold).ToString())}, {"food", IronUI::ToStd(IronStrategy::Num(Data->Food).ToString())}, {"troops", IronUI::ToStd(IronStrategy::Num(Data->Troops).ToString())}});
	}
	case ETargetKind::Faction:
		return IronDialogOrderDetail::RelationText(GameState, Target);
	case ETargetKind::Sect:
	{
		const IronSim::FSect* Data = IronStrategy::GetSect(GameState, Target);
		if (!Data)
		{
			return FText::GetEmpty();
		}
		const int32 Favor = (GameState.PlayerFaction >= 0 && GameState.PlayerFaction < static_cast<int32>(Data->Favor.size())) ? Data->Favor[static_cast<size_t>(GameState.PlayerFaction)] : 0;
		return IronUI::LocF("ui.strategy.sectTargetDetail", "{city} - favor {favor}", {{"city", IronUI::ToStd(IronStrategy::CityName(GameState, Data->City).ToString())}, {"favor", IronSim::ToText(Favor)}});
	}
	case ETargetKind::None:
		break;
	}
	return FText::GetEmpty();
}

TSharedRef<SWidget> SIronOrderDialog::BuildTargetRow(int32 Target)
{
	const IronSim::FGameState& GameState = Session->State();
	TSharedRef<SWidget> Leading = SNew(SBox);
	if (GetTargetKind() == ETargetKind::Officer)
	{
		Leading = IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Target), 48.0f);
	}
	else if (GetTargetKind() == ETargetKind::Faction)
	{
		Leading = IronStyle::MakeBanner(Target, 44.0f);
	}
	else
	{
		Leading = SNew(SBox)
			.WidthOverride(28.0f)
			.HeightOverride(28.0f)
			[
				SNew(SImage)
				.Image(FIronAssets::Get().Icon(IronStrategy::OrderIcon(OrderKind)))
			];
	}

	TSharedRef<SVerticalBox> Text = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(TargetTitle(Target))
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(IronStyle::Ink())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this, Target]() { return TargetDetail(Target); })
			.Font(IronStyle::Body(12.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
			.AutoWrapText(true)
		];
	if (GetTargetKind() == ETargetKind::Officer)
	{
		if (const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Target))
		{
			Text->AddSlot()
			.AutoHeight()
			[
				IronStrategy::MakeStatsRow(*Data, IronSim::StatIndex(IronSim::EStat::Charm), 12.0f)
			];
		}
	}

	return SNew(SButton)
		.ButtonStyle(&IronStyle::RowButton())
		.IsFocusable(false)
		.ContentPadding(FMargin(1.0f))
		.OnClicked_Lambda([this, Target]()
		{
			SelectedTarget = Target;
			ErrorText = FText::GetEmpty();
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
					Text
				]
			]
		];
}

TSharedRef<SWidget> SIronOrderDialog::BuildTargetList()
{
	FText Caption;
	switch (GetTargetKind())
	{
	case ETargetKind::Officer:
		Caption = IronUI::Loc("ui.strategy.chooseRecruitTarget", "Whom to persuade");
		break;
	case ETargetKind::City:
		Caption = IronUI::Loc("ui.strategy.chooseDestination", "Destination");
		break;
	case ETargetKind::Faction:
		Caption = IronUI::Loc("ui.strategy.chooseFaction", "Faction");
		break;
	case ETargetKind::Sect:
		Caption = IronUI::Loc("ui.strategy.chooseSect", "Sect");
		break;
	case ETargetKind::None:
		break;
	}

	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	if (Targets.Num() == 0)
	{
		List->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noTargets", "There is no valid target for this order."), 15.0f, IronStyle::InkSoft())
		];
	}
	for (const int32 Target : Targets)
	{
		List->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			BuildTargetRow(Target)
		];
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeSectionTitle(Caption)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				List
			]
		];
}

TSharedRef<SWidget> SIronOrderDialog::BuildAmounts()
{
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.amounts", "Amounts"))
		];

	const TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;
	if (OrderKind == IronSim::EOrderType::Draft)
	{
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.draftAmount", "Troops to draft"), [SessionRef, City]()
			{
				return (SessionRef.IsValid() && SessionRef->HasGame()) ? SessionRef->Game().DraftCapacity(City) : 0;
			}, &AmountValue, 100)
		];
		Box->AddSlot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([this]()
			{
				const int32 Capacity = Session->HasGame() ? Session->Game().DraftCapacity(CityIndex) : 0;
				const int32 Cost = Session->HasGame() ? Session->Game().DraftCost(AmountValue) : 0;
				return IronUI::LocF("ui.strategy.draftInfo", "Up to {capacity} volunteers can be raised. Cost: {cost} gold.", {{"capacity", IronUI::ToStd(IronStrategy::Num(Capacity).ToString())}, {"cost", IronUI::ToStd(IronStrategy::Num(Cost).ToString())}});
			})
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
			.AutoWrapText(true)
		];
	}
	else if (OrderKind == IronSim::EOrderType::Transport)
	{
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.transportGold", "Gold"), [this]() { return CityGold(); }, &GoldValue, 100)
		];
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.transportFood", "Food"), [this]() { return CityFood(); }, &FoodValue, 500)
		];
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.transportTroops", "Troops"), [this]() { return CityTroops(); }, &TroopsValue, 100)
		];
	}
	else if (OrderKind == IronSim::EOrderType::Gift)
	{
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.giftGold", "Gift of gold"), [this]() { return CityGold(); }, &GoldValue, 100)
		];
	}
	return Box;
}

FText SIronOrderDialog::SummaryText() const
{
	if (Officers.Num() == 0)
	{
		return IronUI::Loc("ui.strategy.noOfficerAvailable", "No officer is available.");
	}
	if (SelectedOfficer < 0)
	{
		return IronUI::Loc("ui.strategy.pickOfficer", "Choose an officer.");
	}
	if (GetTargetKind() != ETargetKind::None && SelectedTarget < 0)
	{
		return IronUI::Loc("ui.strategy.pickTarget", "Choose a target.");
	}
	const IronSim::FOrderCheck Result = CheckFor(SelectedOfficer);
	const std::string Name = IronUI::ToStd(IronStrategy::OfficerName(Session->State(), SelectedOfficer).ToString());
	if (!Result.bAllowed)
	{
		return IronUI::LocF("ui.strategy.orderBlocked", "{name}: {reason}", {{"name", Name}, {"reason", Result.Reason}});
	}
	if (Result.SuccessChance >= 0)
	{
		return IronUI::LocF("ui.strategy.orderPreviewChance", "{name}: {preview} (cost {cost} gold, success {chance}%)", {{"name", Name}, {"preview", Result.Preview}, {"cost", IronSim::ToText(Result.Cost)}, {"chance", IronSim::ToText(Result.SuccessChance)}});
	}
	return IronUI::LocF("ui.strategy.orderPreview", "{name}: {preview} (cost {cost} gold)", {{"name", Name}, {"preview", Result.Preview}, {"cost", IronSim::ToText(Result.Cost)}});
}

FSlateColor SIronOrderDialog::SummaryColor() const
{
	if (SelectedOfficer < 0)
	{
		return FSlateColor(IronStyle::InkSoft());
	}
	return FSlateColor(CheckFor(SelectedOfficer).bAllowed ? IronStyle::Ink() : IronStyle::Danger());
}

FReply SIronOrderDialog::HandleIssue()
{
	if (!Session.IsValid() || !Session->HasGame() || SelectedOfficer < 0)
	{
		return FReply::Handled();
	}
	std::string Error;
	if (Session->Game().IssueOrder(MakeOrder(SelectedOfficer), Error))
	{
		Session->NotifyStateChanged();
		CloseDialog();
		return FReply::Handled();
	}
	ErrorText = Error.empty() ? IronUI::Loc("ui.strategy.orderFailed", "The order could not be issued.") : IronUI::ToText(Error);
	return FReply::Handled();
}

FReply SIronOrderDialog::HandleCancel()
{
	CloseDialog();
	return FReply::Handled();
}

void SIronOrderDialog::CloseDialog()
{
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->PopModal();
	}
}
