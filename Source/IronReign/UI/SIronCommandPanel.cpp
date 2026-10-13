#include "UI/SIronCommandPanel.h"

#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronDialogArmy.h"
#include "UI/SIronDialogOrder.h"
#include "UI/SIronDialogTown.h"
#include "UI/SIronRoot.h"
#include "UI/SIronStrategyCommon.h"
#include "UI/SIronStrategyDialogs.h"

#include "Templates/TypeHash.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/Layout/SUniformGridPanel.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronCommandPanelDetail
{
	uint32 Mix(uint32 Hash, int32 Value)
	{
		return (Hash ^ static_cast<uint32>(Value)) * 16777619u + 0x9E3779B9u;
	}

	TSharedRef<SWidget> MakeCaption(const FText& Text)
	{
		return SNew(STextBlock)
			.Text(Text)
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
			.AutoWrapText(true);
	}
}

void SIronCommandPanel::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;
	Rebuild();
}

void SIronCommandPanel::SetCity(int32 InCity)
{
	if (InCity == CityIndex)
	{
		Refresh();
		return;
	}
	CityIndex = InCity;
	Rebuild();
}

void SIronCommandPanel::Refresh()
{
	if (ComputeSignature() != Signature)
	{
		Rebuild();
	}
}

uint32 SIronCommandPanel::ComputeSignature() const
{
	uint32 Hash = GetTypeHash(CityIndex);
	Hash = IronCommandPanelDetail::Mix(Hash, static_cast<int32>(ActiveTab));
	if (!Session.IsValid() || !Session->HasGame())
	{
		return Hash;
	}
	const IronSim::FGameState& GameState = Session->State();
	Hash = IronCommandPanelDetail::Mix(Hash, static_cast<int32>(GameState.Phase));
	Hash = IronCommandPanelDetail::Mix(Hash, GameState.Year * 12 + GameState.Month);
	Hash = IronCommandPanelDetail::Mix(Hash, GameState.PlayerFaction);
	if (const IronSim::FCity* Data = IronStrategy::GetCity(GameState, CityIndex))
	{
		Hash = IronCommandPanelDetail::Mix(Hash, Data->Owner);
		Hash = IronCommandPanelDetail::Mix(Hash, Data->bDelegated ? 1 : 0);
	}
	Hash = IronCommandPanelDetail::Mix(Hash, static_cast<int32>(GameState.Orders.size()));
	for (const IronSim::FOrder& Order : GameState.Orders)
	{
		if (Order.City == CityIndex)
		{
			Hash = IronCommandPanelDetail::Mix(Hash, Order.Officer);
			Hash = IronCommandPanelDetail::Mix(Hash, static_cast<int32>(Order.Type));
		}
	}
	for (const IronSim::FArmy& Army : GameState.Armies)
	{
		if (Army.Faction == GameState.PlayerFaction)
		{
			Hash = IronCommandPanelDetail::Mix(Hash, Army.Id);
			Hash = IronCommandPanelDetail::Mix(Hash, Army.bNew ? 1 : 0);
		}
	}
	Hash = IronCommandPanelDetail::Mix(Hash, static_cast<int32>(GameState.PrisonersInCity(CityIndex).size()));
	Hash = IronCommandPanelDetail::Mix(Hash, static_cast<int32>(GameState.FreeOfficersInCity(CityIndex).size()));
	for (const IronSim::FFaction& Faction : GameState.Factions)
	{
		Hash = IronCommandPanelDetail::Mix(Hash, Faction.bAlive ? 1 : 0);
	}
	return Hash;
}

bool SIronCommandPanel::CanCommand() const
{
	return Session.IsValid() && Session->HasGame() && Session->Game().IsPlanning() && Session->Game().IsPlayerCity(CityIndex);
}

bool SIronCommandPanel::HasIdleOfficers() const
{
	return CanCommand() && !Session->Game().IdleOfficers(CityIndex).empty();
}

void SIronCommandPanel::Rebuild()
{
	Signature = ComputeSignature();

	TSharedRef<SWidget> Content = SNew(SBox);
	const bool bHasCity = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	if (!bHasCity)
	{
		Content = SNew(SBox)
			.VAlign(VAlign_Center)
			.HAlign(HAlign_Center)
			[
				IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.selectOwnCity", "Select one of your cities to give orders."), 15.0f, IronStyle::InkSoft())
			];
	}
	else if (!Session->Game().IsPlayerCity(CityIndex))
	{
		Content = BuildForeignContent();
	}
	else if (Session->Game().IsPlanning())
	{
		Content = BuildPlanningContent();
	}
	else
	{
		Content = BuildExecutionContent();
	}

	ChildSlot
	[
		IronStyle::MakePanel(Content, false, FMargin(14.0f))
	];
}

TSharedRef<SWidget> SIronCommandPanel::MakeOrderButton(IronSim::EOrderType Type)
{
	TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;
	return IronStyle::MakeButton(IronStrategy::OrderName(Type), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleOrder, Type), TAttribute<bool>::CreateLambda([SessionRef, City]()
	{
		return SessionRef.IsValid() && SessionRef->HasGame() && SessionRef->Game().IsPlanning() && SessionRef->Game().IsPlayerCity(City) && !SessionRef->Game().IdleOfficers(City).empty();
	}), IronStrategy::OrderIcon(Type), 150.0f);
}

TSharedRef<SWidget> SIronCommandPanel::MakeActionButton(const FText& Label, const FString& Icon, FOnClicked OnClicked, const TAttribute<bool>& EnabledAttr)
{
	return IronStyle::MakeButton(Label, OnClicked, EnabledAttr, Icon, 150.0f);
}

TSharedRef<SWidget> SIronCommandPanel::BuildTabBar()
{
	struct FTabInfo
	{
		ETab Tab;
		FText Label;
	};
	const FTabInfo Tabs[] = {
		{ETab::Domestic, IronUI::Loc("ui.strategy.tabDomestic", "Domestic")},
		{ETab::Military, IronUI::Loc("ui.strategy.tabMilitary", "Military")},
		{ETab::Personnel, IronUI::Loc("ui.strategy.tabPersonnel", "Personnel")},
		{ETab::Diplomacy, IronUI::Loc("ui.strategy.tabDiplomacy", "Diplomacy")},
		{ETab::Town, IronUI::Loc("ui.strategy.tabTown", "Town")}};

	TSharedRef<SUniformGridPanel> Bar = SNew(SUniformGridPanel).SlotPadding(FMargin(1.0f, 0.0f));
	int32 Column = 0;
	for (const FTabInfo& Info : Tabs)
	{
		const bool bActive = Info.Tab == ActiveTab;
		Bar->AddSlot(Column, 0)
		[
			SNew(SButton)
			.ButtonStyle(&IronStyle::Tab(bActive))
			.IsFocusable(false)
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			.ContentPadding(FMargin(4.0f, 6.0f))
			.OnClicked(FOnClicked::CreateSP(this, &SIronCommandPanel::HandleTab, Info.Tab))
			[
				SNew(STextBlock)
				.Text(Info.Label)
				.Font(bActive ? IronStyle::BodyBold(13.0f) : IronStyle::Body(13.0f))
				.ColorAndOpacity(bActive ? IronStyle::Gold() : IronStyle::TextLight())
			]
		];
		++Column;
	}
	return Bar;
}

TSharedRef<SWidget> SIronCommandPanel::BuildPage()
{
	switch (ActiveTab)
	{
	case ETab::Domestic: return BuildDomesticPage();
	case ETab::Military: return BuildMilitaryPage();
	case ETab::Personnel: return BuildPersonnelPage();
	case ETab::Diplomacy: return BuildDiplomacyPage();
	case ETab::Town: return BuildTownPage();
	}
	return BuildDomesticPage();
}

TSharedRef<SWidget> SIronCommandPanel::BuildDomesticPage()
{
	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.domesticHint", "Develop the city. Each officer may take one order per month."))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SUniformGridPanel)
			.SlotPadding(FMargin(3.0f))
			+ SUniformGridPanel::Slot(0, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Farm)
			]
			+ SUniformGridPanel::Slot(1, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Commerce)
			]
			+ SUniformGridPanel::Slot(0, 1)
			[
				MakeOrderButton(IronSim::EOrderType::Walls)
			]
			+ SUniformGridPanel::Slot(1, 1)
			[
				MakeOrderButton(IronSim::EOrderType::Patrol)
			]
			+ SUniformGridPanel::Slot(0, 2)
			[
				MakeOrderButton(IronSim::EOrderType::Train)
			]
			+ SUniformGridPanel::Slot(1, 2)
			[
				MakeOrderButton(IronSim::EOrderType::Draft)
			]
		];
}

TSharedRef<SWidget> SIronCommandPanel::BuildArmyLine(int32 ArmyId, bool bAllowDisband)
{
	TSharedPtr<FIronSession> SessionRef = Session;
	TSharedRef<SHorizontalBox> Line = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text_Lambda([SessionRef, ArmyId]()
				{
					if (!SessionRef.IsValid() || !SessionRef->HasGame())
					{
						return FText::GetEmpty();
					}
					const IronSim::FGameState& LiveState = SessionRef->State();
					const IronSim::FArmy* Army = LiveState.FindArmy(ArmyId);
					if (!Army || Army->Units.empty())
					{
						return FText::GetEmpty();
					}
					return IronUI::LocF("ui.strategy.armyLine", "{commander}: {troops} troops", {{"commander", IronUI::ToStd(IronStrategy::OfficerName(LiveState, Army->Units[0].Officer).ToString())}, {"troops", IronUI::ToStd(IronStrategy::Num(Army->TotalTroops()).ToString())}});
				})
				.Font(IronStyle::BodyBold(14.0f))
				.ColorAndOpacity(IronStyle::Ink())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text_Lambda([SessionRef, ArmyId]()
				{
					if (!SessionRef.IsValid() || !SessionRef->HasGame())
					{
						return FText::GetEmpty();
					}
					const IronSim::FGameState& LiveState = SessionRef->State();
					const IronSim::FArmy* Army = LiveState.FindArmy(ArmyId);
					if (!Army)
					{
						return FText::GetEmpty();
					}
					const int32 Daily = FMath::Max(1, SessionRef->Game().ArmyDailyFood(Army->TotalTroops()));
					const std::string Target = IronUI::ToStd(IronStrategy::CityName(LiveState, Army->Target).ToString());
					if (Army->State == IronSim::EArmyState::Returning)
					{
						return IronUI::LocF("ui.strategy.armyReturningLine", "Returning to {city} - food for {days} days", {{"city", Target}, {"days", IronSim::ToText(Army->Food / Daily)}});
					}
					return IronUI::LocF("ui.strategy.armyMarchingLine", "Marching on {city} - food for {days} days", {{"city", Target}, {"days", IronSim::ToText(Army->Food / Daily)}});
				})
				.Font(IronStyle::Body(12.0f))
				.ColorAndOpacity(IronStyle::InkSoft())
			]
		];
	if (bAllowDisband)
	{
		Line->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(6.0f, 0.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.disband", "Disband"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleDisband, ArmyId), TAttribute<bool>::CreateLambda([SessionRef]()
			{
				return SessionRef.IsValid() && SessionRef->HasGame() && SessionRef->Game().IsPlanning();
			}), TEXT("Undo"), 0.0f)
		];
	}
	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.35f))
		.Padding(FMargin(6.0f, 4.0f))
		[
			Line
		];
}

TSharedRef<SWidget> SIronCommandPanel::BuildMilitaryPage()
{
	TSharedRef<SVerticalBox> Page = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.militaryHint", "Form armies of up to five officers and send them against a neighbouring city, or move supplies between your cities."))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SUniformGridPanel)
			.SlotPadding(FMargin(3.0f))
			+ SUniformGridPanel::Slot(0, 0)
			[
				MakeActionButton(IronUI::Loc("ui.strategy.march", "March"), TEXT("March"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleMarch), TAttribute<bool>::CreateSP(this, &SIronCommandPanel::HasIdleOfficers))
			]
			+ SUniformGridPanel::Slot(1, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Transport)
			]
		];

	const IronSim::FGameState& GameState = Session->State();
	bool bAnyNew = false;
	bool bAnyField = false;
	for (const IronSim::FArmy& Army : GameState.Armies)
	{
		if (Army.Faction != GameState.PlayerFaction)
		{
			continue;
		}
		if (Army.bNew && Army.Home == CityIndex)
		{
			bAnyNew = true;
		}
		else
		{
			bAnyField = true;
		}
	}
	if (bAnyNew)
	{
		Page->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.newArmies", "Armies leaving this month"), 15.0f)
		];
		for (const IronSim::FArmy& Army : GameState.Armies)
		{
			if (Army.Faction == GameState.PlayerFaction && Army.bNew && Army.Home == CityIndex)
			{
				Page->AddSlot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 1.0f))
				[
					BuildArmyLine(Army.Id, true)
				];
			}
		}
	}
	if (bAnyField)
	{
		Page->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.fieldArmies", "Our armies in the field"), 15.0f)
		];
		for (const IronSim::FArmy& Army : GameState.Armies)
		{
			if (Army.Faction == GameState.PlayerFaction && !(Army.bNew && Army.Home == CityIndex))
			{
				Page->AddSlot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 1.0f))
				[
					BuildArmyLine(Army.Id, false)
				];
			}
		}
	}
	return Page;
}

TSharedRef<SWidget> SIronCommandPanel::BuildPersonnelPage()
{
	const IronSim::FGameState& GameState = Session->State();
	int32 HeldPrisoners = 0;
	for (const int Prisoner : GameState.PrisonersInCity(CityIndex))
	{
		const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Prisoner);
		if (Data && (Data->Captor < 0 || Data->Captor == GameState.PlayerFaction))
		{
			++HeldPrisoners;
		}
	}
	TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.personnelHint", "Seek out talent, persuade heroes, move officers and keep them loyal."))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SUniformGridPanel)
			.SlotPadding(FMargin(3.0f))
			+ SUniformGridPanel::Slot(0, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Search)
			]
			+ SUniformGridPanel::Slot(1, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Recruit)
			]
			+ SUniformGridPanel::Slot(0, 1)
			[
				MakeOrderButton(IronSim::EOrderType::Move)
			]
			+ SUniformGridPanel::Slot(1, 1)
			[
				MakeActionButton(IronUI::Loc("ui.strategy.reward", "Reward"), TEXT("Loyalty"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleReward), TAttribute<bool>::CreateSP(this, &SIronCommandPanel::CanCommand))
			]
			+ SUniformGridPanel::Slot(0, 2)
			[
				MakeActionButton(IronUI::LocF("ui.strategy.prisonersButton", "Prisoners ({count})", {{"count", IronSim::ToText(HeldPrisoners)}}), TEXT("Prisoner"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandlePrisoners), TAttribute<bool>::CreateLambda([SessionRef, City, HeldPrisoners]()
				{
					return HeldPrisoners > 0 && SessionRef.IsValid() && SessionRef->HasGame() && SessionRef->Game().IsPlanning() && SessionRef->Game().IsPlayerCity(City);
				}))
			]
		];
}

TSharedRef<SWidget> SIronCommandPanel::BuildDiplomacyPage()
{
	TSharedRef<SVerticalBox> Page = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.diplomacyHint", "Send an envoy. Trust decides whether other rulers listen."))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SUniformGridPanel)
			.SlotPadding(FMargin(3.0f))
			+ SUniformGridPanel::Slot(0, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Alliance)
			]
			+ SUniformGridPanel::Slot(1, 0)
			[
				MakeOrderButton(IronSim::EOrderType::Truce)
			]
			+ SUniformGridPanel::Slot(0, 1)
			[
				MakeOrderButton(IronSim::EOrderType::Gift)
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.relations", "Relations"), 15.0f)
		];

	const IronSim::FGameState& GameState = Session->State();
	for (const int Faction : Session->Game().DiplomacyTargets())
	{
		const IronSim::FRelation& Relation = GameState.Relation(GameState.PlayerFaction, Faction);
		FText Status;
		if (Relation.AllianceMonths > 0)
		{
			Status = IronUI::LocF("ui.strategy.allied", "Allied ({months} months)", {{"months", IronSim::ToText(Relation.AllianceMonths)}});
		}
		else if (Relation.TruceMonths > 0)
		{
			Status = IronUI::LocF("ui.strategy.truce", "Truce ({months} months)", {{"months", IronSim::ToText(Relation.TruceMonths)}});
		}
		else
		{
			Status = IronUI::Loc("ui.strategy.hostile", "Hostile");
		}
		const float TrustFraction = FMath::Clamp(static_cast<float>(Relation.Trust) / 100.0f, 0.0f, 1.0f);
		Page->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.0f, 0.0f, 6.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(10.0f)
				.HeightOverride(28.0f)
				[
					SNew(SImage)
					.Image(IronStyle::WhiteBrush())
					.ColorAndOpacity(IronStyle::FactionColor(Faction))
				]
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
					.FillWidth(1.0f)
					[
						SNew(STextBlock)
						.Text(IronStrategy::FactionName(GameState, Faction))
						.Font(IronStyle::BodyBold(14.0f))
						.ColorAndOpacity(IronStyle::Ink())
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					[
						SNew(STextBlock)
						.Text(Status)
						.Font(IronStyle::Body(12.0f))
						.ColorAndOpacity(Relation.AllianceMonths > 0 ? IronStyle::Jade() : (Relation.TruceMonths > 0 ? IronStyle::Indigo() : IronStyle::Lacquer()))
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 2.0f, 0.0f, 0.0f))
				[
					IronStyle::MakeBar(TrustFraction, IronStyle::Jade(), 5.0f)
				]
			]
		];
	}
	return Page;
}

TSharedRef<SWidget> SIronCommandPanel::BuildTownPage()
{
	TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;
	const bool bHasSect = !Session->Game().SectsNear(CityIndex).empty();
	const int32 Wanderers = static_cast<int32>(Session->State().FreeOfficersInCity(CityIndex).size());

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.townHint", "Trade grain at the market, listen for rumours at the tavern and court the martial sects."))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SUniformGridPanel)
			.SlotPadding(FMargin(3.0f))
			+ SUniformGridPanel::Slot(0, 0)
			[
				MakeActionButton(IronUI::Loc("ui.strategy.market", "Market"), TEXT("Market"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleMarket), TAttribute<bool>::CreateSP(this, &SIronCommandPanel::CanCommand))
			]
			+ SUniformGridPanel::Slot(1, 0)
			[
				MakeActionButton(IronUI::LocF("ui.strategy.tavernButton", "Tavern ({count})", {{"count", IronSim::ToText(Wanderers)}}), TEXT("Tavern"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleTavern), TAttribute<bool>::CreateSP(this, &SIronCommandPanel::CanCommand))
			]
			+ SUniformGridPanel::Slot(0, 1)
			[
				MakeActionButton(IronUI::Loc("ui.strategy.sect", "Sect"), TEXT("SectTraining"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleSect), TAttribute<bool>::CreateLambda([SessionRef, City, bHasSect]()
				{
					return bHasSect && SessionRef.IsValid() && SessionRef->HasGame() && SessionRef->Game().IsPlanning() && SessionRef->Game().IsPlayerCity(City);
				}))
			]
			+ SUniformGridPanel::Slot(1, 1)
			[
				MakeOrderButton(IronSim::EOrderType::SectTraining)
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 0.0f))
		[
			IronStrategy::MakeWrappedText(TAttribute<FText>::CreateLambda([SessionRef]()
			{
				if (!SessionRef.IsValid() || !SessionRef->HasGame())
				{
					return FText::GetEmpty();
				}
				return IronUI::LocF("ui.strategy.foodPrices", "Grain this month: buy {buy}, sell {sell} gold per 100.", {{"buy", IronSim::ToText(SessionRef->Game().FoodBuyPrice())}, {"sell", IronSim::ToText(SessionRef->Game().FoodSellPrice())}});
			}), 13.0f, IronStyle::InkSoft())
		];
}

TSharedRef<SWidget> SIronCommandPanel::BuildOrdersList()
{
	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	const IronSim::FGameState& GameState = Session->State();
	int32 Count = 0;
	for (const IronSim::FOrder& Order : Session->Game().PlayerOrders())
	{
		if (Order.City != CityIndex)
		{
			continue;
		}
		++Count;
		const int32 Officer = Order.Officer;
		List->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 1.0f))
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.35f))
			.Padding(FMargin(4.0f, 2.0f))
			[
				SNew(SHorizontalBox)
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.0f, 0.0f, 6.0f, 0.0f))
				[
					SNew(SBox)
					.WidthOverride(24.0f)
					.HeightOverride(24.0f)
					[
						SNew(SImage)
						.Image(FIronAssets::Get().Icon(IronStrategy::OrderIcon(Order.Type)))
					]
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
						.Text(IronStrategy::OfficerName(GameState, Officer))
						.Font(IronStyle::BodyBold(13.0f))
						.ColorAndOpacity(IronStyle::Ink())
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					[
						SNew(STextBlock)
						.Text(IronStrategy::OrderSummary(GameState, Order))
						.Font(IronStyle::Body(12.0f))
						.ColorAndOpacity(IronStyle::Indigo())
					]
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					IronStyle::MakeButton(IronUI::Loc("ui.strategy.cancelOrder", "Cancel"), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleCancelOrder, Officer), TAttribute<bool>::CreateSP(this, &SIronCommandPanel::CanCommand), TEXT("Undo"), 0.0f)
				]
			]
		];
	}
	if (Count == 0)
	{
		List->AddSlot()
		.AutoHeight()
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.noOrdersYet", "No orders have been given in this city yet."))
		];
	}
	return List;
}

TSharedRef<SWidget> SIronCommandPanel::BuildPlanningContent()
{
	TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.strategy.commands", "Commands"), 22.0f, false)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			SNew(STextBlock)
			.Text_Lambda([SessionRef, City]()
			{
				if (!SessionRef.IsValid() || !SessionRef->HasGame())
				{
					return FText::GetEmpty();
				}
				return IronUI::LocF("ui.strategy.idleOfficers", "{city}: {count} officers awaiting orders", {{"city", IronUI::ToStd(IronStrategy::CityName(SessionRef->State(), City).ToString())}, {"count", IronSim::ToText(static_cast<int>(SessionRef->Game().IdleOfficers(City).size()))}});
			})
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			BuildTabBar()
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				BuildPage()
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 6.0f))
		[
			SNew(SBox)
			.HeightOverride(10.0f)
			[
				SNew(SImage)
				.Image(IronStyle::Divider())
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeButton(TAttribute<FText>::CreateLambda([SessionRef, City]()
			{
				const IronSim::FCity* Data = (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::GetCity(SessionRef->State(), City) : nullptr;
				return (Data && Data->bDelegated) ? IronUI::Loc("ui.strategy.delegateOn", "Delegated to a governor") : IronUI::Loc("ui.strategy.delegateOff", "Delegate this city");
			}), FOnClicked::CreateSP(this, &SIronCommandPanel::HandleDelegate), TAttribute<bool>::CreateSP(this, &SIronCommandPanel::CanCommand), TEXT("Delegate"), 0.0f)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 10.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.ordersThisMonth", "Orders this month"), 15.0f)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SBox)
			.MaxDesiredHeight(230.0f)
			[
				SNew(SScrollBox)
				+ SScrollBox::Slot()
				[
					BuildOrdersList()
				]
			]
		];
}

TSharedRef<SWidget> SIronCommandPanel::BuildExecutionContent()
{
	TSharedRef<SVerticalBox> Armies = SNew(SVerticalBox);
	const IronSim::FGameState& GameState = Session->State();
	int32 Count = 0;
	for (const IronSim::FArmy& Army : GameState.Armies)
	{
		if (Army.Faction == GameState.PlayerFaction)
		{
			++Count;
			Armies->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 1.0f))
			[
				BuildArmyLine(Army.Id, false)
			];
		}
	}
	if (Count == 0)
	{
		Armies->AddSlot()
		.AutoHeight()
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.noArmies", "None of our armies are in the field."))
		];
	}

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.strategy.monthUnderWay", "The Month Unfolds"), 22.0f, false)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f, 0.0f, 8.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.executionHint", "Your officers carry out their orders and the armies march. New orders can be given when the next month begins."))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.fieldArmies", "Our armies in the field"), 15.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				Armies
			]
		];
}

TSharedRef<SWidget> SIronCommandPanel::BuildForeignContent()
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FCity& Data = GameState.Cities[static_cast<size_t>(CityIndex)];
	TSharedRef<SVerticalBox> Box = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronStrategy::FactionName(GameState, Data.Owner), 22.0f, false)
		];
	if (Data.Owner >= 0)
	{
		const IronSim::FFaction* Owner = IronStrategy::GetFaction(GameState, Data.Owner);
		const IronSim::FRelation& Relation = GameState.Relation(GameState.PlayerFaction, Data.Owner);
		Box->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f))
		[
			IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Owner ? Owner->Ruler : -1), 140.0f)
		];
		Box->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Text(IronUI::LocF("ui.strategy.rulerLine", "Ruler: {name}", {{"name", IronUI::ToStd(IronStrategy::OfficerName(GameState, Owner ? Owner->Ruler : -1).ToString())}}))
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(IronStyle::Ink())
		];
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 8.0f, 0.0f, 2.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::LocF("ui.strategy.trustLine", "Trust toward us: {trust}", {{"trust", IronSim::ToText(Relation.Trust)}}))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(IronStyle::Ink())
		];
		Box->AddSlot()
		.AutoHeight()
		[
			IronStyle::MakeBar(FMath::Clamp(static_cast<float>(Relation.Trust) / 100.0f, 0.0f, 1.0f), IronStyle::Jade(), 6.0f)
		];
		FText Status = IronUI::Loc("ui.strategy.hostile", "Hostile");
		if (Relation.AllianceMonths > 0)
		{
			Status = IronUI::LocF("ui.strategy.allied", "Allied ({months} months)", {{"months", IronSim::ToText(Relation.AllianceMonths)}});
		}
		else if (Relation.TruceMonths > 0)
		{
			Status = IronUI::LocF("ui.strategy.truce", "Truce ({months} months)", {{"months", IronSim::ToText(Relation.TruceMonths)}});
		}
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f))
		[
			SNew(STextBlock)
			.Text(Status)
			.Font(IronStyle::BodyBold(14.0f))
			.ColorAndOpacity(Relation.AllianceMonths > 0 ? IronStyle::Jade() : IronStyle::Lacquer())
		];
		Box->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f))
		[
			IronCommandPanelDetail::MakeCaption(IronUI::LocF("ui.strategy.foreignStats", "{cities} cities, {officers} officers", {{"cities", IronSim::ToText(Session->Game().CityCount(Data.Owner))}, {"officers", IronSim::ToText(static_cast<int>(GameState.FactionOfficers(Data.Owner).size()))}}))
		];
	}
	Box->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
	[
		IronCommandPanelDetail::MakeCaption(IronUI::Loc("ui.strategy.foreignHint", "To attack this city, select one of your neighbouring cities and use March in the Military tab. Envoys are sent from the Diplomacy tab."))
	];
	return Box;
}

FReply SIronCommandPanel::HandleTab(ETab NewTab)
{
	if (ActiveTab != NewTab)
	{
		ActiveTab = NewTab;
		Rebuild();
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleOrder(IronSim::EOrderType Type)
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanCommand())
	{
		RootPtr->PushModal(SNew(SIronOrderDialog).Session(Session).Root(Root).City(CityIndex).OrderType(Type));
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleMarch()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanCommand())
	{
		RootPtr->PushModal(SNew(SIronArmyDialog).Session(Session).Root(Root).City(CityIndex));
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleReward()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanCommand())
	{
		RootPtr->PushModal(SNew(SIronRewardDialog).Session(Session).Root(Root).City(CityIndex));
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandlePrisoners()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid() || !CanCommand())
	{
		return FReply::Handled();
	}
	TWeakPtr<SIronCommandPanel> WeakSelf = SharedThis(this);
	RootPtr->PushModal(SNew(SIronPrisonerListDialog).Session(Session).Root(Root).City(CityIndex).OnDecide([WeakSelf](int32 Prisoner)
	{
		if (TSharedPtr<SIronCommandPanel> Self = WeakSelf.Pin())
		{
			Self->OpenPrisonerDecision(Prisoner);
		}
	}));
	return FReply::Handled();
}

void SIronCommandPanel::OpenPrisonerDecision(int32 Prisoner)
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (!RootPtr.IsValid())
	{
		return;
	}
	// Replace the prisoner list with the decision dialog.
	RootPtr->PopModal();
	const TWeakPtr<SIronRoot> WeakRoot = Root;
	const TSharedPtr<FIronSession> SessionRef = Session;
	RootPtr->PushModal(SNew(SIronPrisonerDialog).Session(Session).Prisoner(Prisoner).OnDecided([WeakRoot, SessionRef](int32 Decided, const FText& Message)
	{
		TSharedPtr<SIronRoot> Pinned = WeakRoot.Pin();
		if (!Pinned.IsValid())
		{
			return;
		}
		Pinned->PopModal();
		if (SessionRef.IsValid())
		{
			SessionRef->NotifyStateChanged();
		}
		const FText Title = (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::OfficerName(SessionRef->State(), Decided) : IronUI::Loc("ui.strategy.prisonerTitle", "Prisoner");
		if (!Message.IsEmpty())
		{
			Pinned->ShowMessage(Title, Message);
		}
	}));
}

FReply SIronCommandPanel::HandleMarket()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanCommand())
	{
		RootPtr->PushModal(SNew(SIronMarketDialog).Session(Session).Root(Root).City(CityIndex));
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleTavern()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanCommand())
	{
		RootPtr->PushModal(SNew(SIronTavernDialog).Session(Session).Root(Root).City(CityIndex));
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleSect()
{
	TSharedPtr<SIronRoot> RootPtr = Root.Pin();
	if (RootPtr.IsValid() && CanCommand())
	{
		RootPtr->PushModal(SNew(SIronSectDialog).Session(Session).Root(Root).City(CityIndex));
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleDelegate()
{
	if (!CanCommand())
	{
		return FReply::Handled();
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	if (Data)
	{
		const bool bNewValue = !Data->bDelegated;
		Session->Game().SetDelegated(CityIndex, bNewValue);
		Session->NotifyStateChanged();
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleCancelOrder(int32 Officer)
{
	if (CanCommand() && Session->Game().CancelOrder(Officer))
	{
		Session->NotifyStateChanged();
	}
	return FReply::Handled();
}

FReply SIronCommandPanel::HandleDisband(int32 ArmyId)
{
	if (Session.IsValid() && Session->HasGame() && Session->Game().IsPlanning() && Session->Game().DisbandArmy(ArmyId))
	{
		Session->NotifyStateChanged();
	}
	return FReply::Handled();
}
