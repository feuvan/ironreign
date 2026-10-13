#include "UI/SIronDialogTown.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronDialogOrder.h"
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

namespace IronDialogTownDetail
{
	void PopModal(const TWeakPtr<SIronRoot>& WeakRoot)
	{
		if (TSharedPtr<SIronRoot> RootPtr = WeakRoot.Pin())
		{
			RootPtr->PopModal();
		}
	}

	/** Replaces the current modal with an order dialog. */
	void OpenOrderDialog(const TSharedPtr<FIronSession>& Session, const TWeakPtr<SIronRoot>& WeakRoot, int32 City, IronSim::EOrderType Type, int32 PresetTarget)
	{
		TSharedPtr<SIronRoot> RootPtr = WeakRoot.Pin();
		if (!RootPtr.IsValid())
		{
			return;
		}
		RootPtr->PopModal();
		RootPtr->PushModal(SNew(SIronOrderDialog).Session(Session).Root(WeakRoot).City(City).OrderType(Type).PresetTarget(PresetTarget));
	}

	TSharedRef<SWidget> MakeFooter(const TSharedRef<SWidget>& Buttons)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			[
				SNew(SSpacer)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				Buttons
			];
	}

	TSharedRef<SWidget> MakeResultLine(TAttribute<FText> Text, TAttribute<FSlateColor> Color)
	{
		return SNew(STextBlock)
			.Text(Text)
			.ColorAndOpacity(Color)
			.Font(IronStyle::BodyBold(14.0f))
			.AutoWrapText(true);
	}

	bool CanAct(const TSharedPtr<FIronSession>& Session, int32 City)
	{
		return Session.IsValid() && Session->HasGame() && Session->Game().IsPlanning() && Session->Game().IsPlayerCity(City);
	}
}

// -------------------------------------------------------------------------------------------------
// Market
// -------------------------------------------------------------------------------------------------

void SIronMarketDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;
	AmountValue = FMath::Min(1000, MaxTradable());

	const FText CityLabel = (Session.IsValid() && Session->HasGame()) ? IronStrategy::CityName(Session->State(), CityIndex) : FText::GetEmpty();

	const TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(TAttribute<FText>::CreateLambda([this]()
			{
				if (!Session.IsValid() || !Session->HasGame())
				{
					return FText::GetEmpty();
				}
				return IronUI::LocF("ui.strategy.marketPrices", "The merchants buy at {sell} and sell at {buy} gold per 100 food this month.", {{"sell", IronSim::ToText(Session->Game().FoodSellPrice())}, {"buy", IronSim::ToText(Session->Game().FoodBuyPrice())}});
			}), 15.0f, IronStyle::Ink())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 8.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, 24.0f, 0.0f))
			[
				IronStyle::MakeIconValue(TEXT("Gold"), TAttribute<FText>::CreateLambda([this]()
				{
					const IronSim::FCity* Data = (Session.IsValid() && Session->HasGame()) ? IronStrategy::GetCity(Session->State(), CityIndex) : nullptr;
					return IronStrategy::Num(Data ? Data->Gold : 0);
				}), 26.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				IronStyle::MakeIconValue(TEXT("Food"), TAttribute<FText>::CreateLambda([this]()
				{
					const IronSim::FCity* Data = (Session.IsValid() && Session->HasGame()) ? IronStrategy::GetCity(Session->State(), CityIndex) : nullptr;
					return IronStrategy::Num(Data ? Data->Food : 0);
				}), 26.0f)
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f))
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.marketAmount", "Food to trade"), [this]() { return MaxTradable(); }, &AmountValue, 100)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f))
		[
			IronStrategy::MakeWrappedText(TAttribute<FText>::CreateLambda([this]()
			{
				return IronUI::LocF("ui.strategy.marketPreview", "Buying {amount} food costs {cost} gold. Selling it earns {gain} gold.", {{"amount", IronUI::ToStd(IronStrategy::Num(AmountValue).ToString())}, {"cost", IronUI::ToStd(IronStrategy::Num(BuyCost()).ToString())}, {"gain", IronUI::ToStd(IronStrategy::Num(SellGain()).ToString())}});
			}), 14.0f, IronStyle::InkSoft())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
		[
			IronDialogTownDetail::MakeResultLine(TAttribute<FText>::CreateLambda([this]() { return ResultText; }), TAttribute<FSlateColor>::CreateLambda([this]()
			{
				return FSlateColor(bResultError ? IronStyle::Danger() : IronStyle::Jade());
			}))
		];

	const TSharedRef<SWidget> Buttons = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.buyFood", "Buy"), FOnClicked::CreateSP(this, &SIronMarketDialog::HandleTrade, true), TAttribute<bool>::CreateLambda([this]()
			{
				const IronSim::FCity* Data = (Session.IsValid() && Session->HasGame()) ? IronStrategy::GetCity(Session->State(), CityIndex) : nullptr;
				return Data && AmountValue > 0 && BuyCost() <= Data->Gold && IronDialogTownDetail::CanAct(Session, CityIndex);
			}), TEXT("Market"), 150.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.sellFood", "Sell"), FOnClicked::CreateSP(this, &SIronMarketDialog::HandleTrade, false), TAttribute<bool>::CreateLambda([this]()
			{
				const IronSim::FCity* Data = (Session.IsValid() && Session->HasGame()) ? IronStrategy::GetCity(Session->State(), CityIndex) : nullptr;
				return Data && AmountValue > 0 && AmountValue <= Data->Food && IronDialogTownDetail::CanAct(Session, CityIndex);
			}), TEXT("Food"), 150.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronMarketDialog::HandleClose), true, FString(), 130.0f)
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::LocF("ui.strategy.marketTitle", "Market of {city}", {{"city", IronUI::ToStd(CityLabel.ToString())}}), Body, IronDialogTownDetail::MakeFooter(Buttons), 760.0f, 0.0f)
	];
}

int32 SIronMarketDialog::BuyCost() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const int64 Price = Session->Game().FoodBuyPrice();
	return static_cast<int32>((static_cast<int64>(AmountValue) * Price + 99) / 100);
}

int32 SIronMarketDialog::SellGain() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const int64 Price = Session->Game().FoodSellPrice();
	return static_cast<int32>((static_cast<int64>(AmountValue) * Price) / 100);
}

int32 SIronMarketDialog::MaxTradable() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	if (!Data)
	{
		return 0;
	}
	const int32 Price = FMath::Max(1, Session->Game().FoodBuyPrice());
	const int64 Affordable = static_cast<int64>(Data->Gold) * 100 / Price;
	return FMath::Max(Data->Food, static_cast<int32>(FMath::Min<int64>(Affordable, 10000000)));
}

FReply SIronMarketDialog::HandleTrade(bool bBuy)
{
	if (!Session.IsValid() || !Session->HasGame() || AmountValue <= 0)
	{
		return FReply::Handled();
	}
	const int32 Traded = AmountValue;
	const int32 GoldAmount = bBuy ? BuyCost() : SellGain();
	std::string Error;
	if (Session->Game().TradeFood(CityIndex, bBuy ? Traded : -Traded, Error))
	{
		bResultError = false;
		ResultText = bBuy
			? IronUI::LocF("ui.strategy.boughtFood", "Bought {amount} food for {gold} gold.", {{"amount", IronUI::ToStd(IronStrategy::Num(Traded).ToString())}, {"gold", IronUI::ToStd(IronStrategy::Num(GoldAmount).ToString())}})
			: IronUI::LocF("ui.strategy.soldFood", "Sold {amount} food for {gold} gold.", {{"amount", IronUI::ToStd(IronStrategy::Num(Traded).ToString())}, {"gold", IronUI::ToStd(IronStrategy::Num(GoldAmount).ToString())}});
		AmountValue = FMath::Min(AmountValue, MaxTradable());
		Session->NotifyStateChanged();
	}
	else
	{
		bResultError = true;
		ResultText = Error.empty() ? IronUI::Loc("ui.strategy.tradeFailed", "The merchants refused the deal.") : IronUI::ToText(Error);
	}
	return FReply::Handled();
}

FReply SIronMarketDialog::HandleClose()
{
	IronDialogTownDetail::PopModal(Root);
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Tavern
// -------------------------------------------------------------------------------------------------

void SIronTavernDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;

	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	const FText CityLabel = bValid ? IronStrategy::CityName(Session->State(), CityIndex) : FText::GetEmpty();
	const FText Rumor = bValid ? IronUI::ToText(Session->Game().TavernRumor(CityIndex)) : FText::GetEmpty();

	TSharedRef<SVerticalBox> Heroes = SNew(SVerticalBox);
	if (bValid)
	{
		const std::vector<int> FreeOfficers = Session->State().FreeOfficersInCity(CityIndex);
		if (FreeOfficers.empty())
		{
			Heroes->AddSlot()
			.AutoHeight()
			[
				IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noWanderers", "No wandering heroes are staying at the tavern."), 15.0f, IronStyle::InkSoft())
			];
		}
		for (const int Officer : FreeOfficers)
		{
			Heroes->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 3.0f))
			[
				BuildHeroRow(Officer)
			];
		}
	}

	const TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.5f))
			.Padding(FMargin(12.0f, 8.0f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(IronUI::Loc("ui.strategy.innkeeper", "The innkeeper leans closer and lowers his voice:"))
					.Font(IronStyle::BodyBold(14.0f))
					.ColorAndOpacity(IronStyle::InkSoft())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 4.0f, 0.0f, 0.0f))
				[
					IronStrategy::MakeWrappedText(Rumor.IsEmpty() ? IronUI::Loc("ui.strategy.noRumor", "\"Quiet times, my lord. Nothing worth your silver.\"") : Rumor, 15.0f, IronStyle::Ink())
				]
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 12.0f, 0.0f, 4.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.wanderers", "Wandering heroes"))
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				Heroes
			]
		];

	const TSharedRef<SWidget> Buttons = IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronTavernDialog::HandleClose), true, FString(), 130.0f);

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::LocF("ui.strategy.tavernDialogTitle", "Tavern of {city}", {{"city", IronUI::ToStd(CityLabel.ToString())}}), Body, IronDialogTownDetail::MakeFooter(Buttons), 860.0f, 640.0f)
	];
}

TSharedRef<SWidget> SIronTavernDialog::BuildHeroRow(int32 Officer)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	const std::string Epithet = IronSim::EpithetOf(*Data);
	const std::string Rumor = IronSim::RumorOf(*Data);
	const FText Name = Epithet.empty() ? IronUI::ToText(IronSim::NameOf(*Data)) : IronUI::LocF("ui.strategy.nameWithEpithet", "{name}, {epithet}", {{"name", IronSim::NameOf(*Data)}, {"epithet", Epithet}});
	const TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;

	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.3f))
		.Padding(FMargin(6.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(0.0f, 0.0f, 10.0f, 0.0f))
			[
				IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Officer), 90.0f)
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
					.Font(IronStyle::BodyBold(16.0f))
					.ColorAndOpacity(IronStyle::Ink())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					IronStrategy::MakeStatsRow(*Data, -1, 13.0f)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(IronUI::LocF("ui.strategy.heroSubline", "{troop}, age {age}", {{"troop", IronSim::DisplayName(Data->Specialty)}, {"age", IronSim::ToText(GameState.OfficerAge(Officer))}}))
					.Font(IronStyle::Body(12.0f))
					.ColorAndOpacity(IronStyle::InkSoft())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 3.0f, 0.0f, 0.0f))
				[
					IronStrategy::MakeWrappedText(IronUI::ToText(Rumor), 13.0f, IronStyle::Indigo())
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.recruitEllipsis", "Recruit..."), FOnClicked::CreateSP(this, &SIronTavernDialog::HandleRecruit, Officer), TAttribute<bool>::CreateLambda([SessionRef, City]()
				{
					return IronDialogTownDetail::CanAct(SessionRef, City) && !SessionRef->Game().IdleOfficers(City).empty();
				}), TEXT("Recruit"), 150.0f)
			]
		];
}

FReply SIronTavernDialog::HandleRecruit(int32 Officer)
{
	IronDialogTownDetail::OpenOrderDialog(Session, Root, CityIndex, IronSim::EOrderType::Recruit, Officer);
	return FReply::Handled();
}

FReply SIronTavernDialog::HandleClose()
{
	IronDialogTownDetail::PopModal(Root);
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Sect
// -------------------------------------------------------------------------------------------------

void SIronSectDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;
	DonationValue = FMath::Min(200, CityGold());

	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	TSharedRef<SVerticalBox> Cards = SNew(SVerticalBox);
	if (bValid)
	{
		const std::vector<int> Sects = Session->Game().SectsNear(CityIndex);
		if (Sects.empty())
		{
			Cards->AddSlot()
			.AutoHeight()
			[
				IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noSectsNear", "No martial sect has a hall in or near this city."), 15.0f, IronStyle::InkSoft())
			];
		}
		for (const int Sect : Sects)
		{
			Cards->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 3.0f))
			[
				BuildSectCard(Sect)
			];
		}
	}

	const TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.donation", "Donation (gold)"), [this]() { return CityGold(); }, &DonationValue, 50)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 4.0f))
		[
			IronDialogTownDetail::MakeResultLine(TAttribute<FText>::CreateLambda([this]() { return ResultText; }), TAttribute<FSlateColor>::CreateLambda([this]()
			{
				return FSlateColor(bResultError ? IronStyle::Danger() : IronStyle::Jade());
			}))
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				Cards
			]
		];

	const TSharedRef<SWidget> Buttons = IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronSectDialog::HandleClose), true, FString(), 130.0f);

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.sectDialogTitle", "Martial Sects"), Body, IronDialogTownDetail::MakeFooter(Buttons), 900.0f, 660.0f)
	];
}

int32 SIronSectDialog::CityGold() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Gold : 0;
}

TSharedRef<SWidget> SIronSectDialog::BuildSectCard(int32 Sect)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FSect* Data = IronStrategy::GetSect(GameState, Sect);
	if (!Data)
	{
		return SNew(SBox);
	}
	std::string TechniqueNames;
	const std::string Separator = IronSim::Loc("ui.strategy.listSeparator", ", ");
	for (const int Technique : Data->Techniques)
	{
		if (const IronSim::FTechnique* Tech = IronStrategy::GetTechnique(GameState, Technique))
		{
			if (!TechniqueNames.empty())
			{
				TechniqueNames += Separator;
			}
			TechniqueNames += IronSim::NameOf(*Tech);
		}
	}
	const TSharedPtr<FIronSession> SessionRef = Session;
	const int32 City = CityIndex;

	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.3f))
		.Padding(FMargin(8.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(0.0f, 0.0f, 10.0f, 0.0f))
			[
				IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Data->Master), 100.0f)
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(IronUI::LocF("ui.strategy.sectHeading", "{sect} ({city})", {{"sect", IronSim::NameOf(*Data)}, {"city", IronUI::ToStd(IronStrategy::CityName(GameState, Data->City).ToString())}}))
					.Font(IronStyle::Heading(20.0f))
					.ColorAndOpacity(IronStyle::Lacquer())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					IronStrategy::MakeWrappedText(IronUI::ToText(IronSim::DescriptionOf(*Data)), 13.0f, IronStyle::InkSoft())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 3.0f))
				[
					SNew(STextBlock)
					.Text_Lambda([SessionRef, Sect]()
					{
						if (!SessionRef.IsValid() || !SessionRef->HasGame())
						{
							return FText::GetEmpty();
						}
						const IronSim::FGameState& LiveState = SessionRef->State();
						const IronSim::FSect* Live = IronStrategy::GetSect(LiveState, Sect);
						const int32 Player = LiveState.PlayerFaction;
						const int32 Favor = (Live && Player >= 0 && Player < static_cast<int32>(Live->Favor.size())) ? Live->Favor[static_cast<size_t>(Player)] : 0;
						return IronUI::LocF("ui.strategy.sectMasterFavor", "Master: {master}   Favor toward us: {favor}", {{"master", IronUI::ToStd(IronStrategy::OfficerName(LiveState, Live ? Live->Master : -1).ToString())}, {"favor", IronSim::ToText(Favor)}});
					})
					.Font(IronStyle::BodyBold(14.0f))
					.ColorAndOpacity(IronStyle::Ink())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					IronStrategy::MakeWrappedText(IronUI::LocF("ui.strategy.sectTechniques", "Techniques taught: {list}", {{"list", TechniqueNames.empty() ? IronSim::Loc("ui.strategy.noTechniques", "-") : TechniqueNames}}), 13.0f, IronStyle::Ink())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
					[
						IronStyle::MakeButton(IronUI::Loc("ui.strategy.donate", "Donate"), FOnClicked::CreateSP(this, &SIronSectDialog::HandleDonate, Sect), TAttribute<bool>::CreateLambda([this]()
						{
							return DonationValue > 0 && DonationValue <= CityGold() && IronDialogTownDetail::CanAct(Session, CityIndex);
						}), TEXT("Gift"), 150.0f)
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					[
						IronStyle::MakeButton(IronUI::Loc("ui.strategy.sectTrainingEllipsis", "Sect Training..."), FOnClicked::CreateSP(this, &SIronSectDialog::HandleTraining, Sect), TAttribute<bool>::CreateLambda([SessionRef, City]()
						{
							return IronDialogTownDetail::CanAct(SessionRef, City) && !SessionRef->Game().IdleOfficers(City).empty();
						}), TEXT("SectTraining"), 200.0f)
					]
				]
			]
		];
}

FReply SIronSectDialog::HandleDonate(int32 Sect)
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return FReply::Handled();
	}
	const int32 Amount = DonationValue;
	std::string Error;
	if (Session->Game().DonateToSect(CityIndex, Sect, Amount, Error))
	{
		bResultError = false;
		ResultText = IronUI::LocF("ui.strategy.donated", "The {sect} accepts {gold} gold with gratitude.", {{"sect", IronUI::ToStd(IronStrategy::SectName(Session->State(), Sect).ToString())}, {"gold", IronUI::ToStd(IronStrategy::Num(Amount).ToString())}});
		DonationValue = FMath::Min(DonationValue, CityGold());
		Session->NotifyStateChanged();
	}
	else
	{
		bResultError = true;
		ResultText = Error.empty() ? IronUI::Loc("ui.strategy.donationFailed", "The donation could not be made.") : IronUI::ToText(Error);
	}
	return FReply::Handled();
}

FReply SIronSectDialog::HandleTraining(int32 Sect)
{
	IronDialogTownDetail::OpenOrderDialog(Session, Root, CityIndex, IronSim::EOrderType::SectTraining, Sect);
	return FReply::Handled();
}

FReply SIronSectDialog::HandleClose()
{
	IronDialogTownDetail::PopModal(Root);
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Reward
// -------------------------------------------------------------------------------------------------

void SIronRewardDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	CityIndex = InArgs._City;
	GoldValue = FMath::Min(100, CityGold());

	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	if (bValid)
	{
		const IronSim::FGameState& GameState = Session->State();
		for (const int Officer : GameState.CityOfficers(CityIndex))
		{
			if (!GameState.IsRuler(Officer))
			{
				Officers.Add(Officer);
			}
		}
		const TSharedPtr<FIronSession> SessionRef = Session;
		Officers.Sort([SessionRef](const int32& Left, const int32& Right)
		{
			const IronSim::FOfficer* LeftData = IronStrategy::GetOfficer(SessionRef->State(), Left);
			const IronSim::FOfficer* RightData = IronStrategy::GetOfficer(SessionRef->State(), Right);
			return (LeftData ? LeftData->Loyalty : 0) < (RightData ? RightData->Loyalty : 0);
		});
	}
	SelectedOfficer = Officers.Num() > 0 ? Officers[0] : -1;
	if (Officers.Num() == 0)
	{
		List->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noRewardable", "There is no officer here to reward."), 15.0f, IronStyle::InkSoft())
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

	const TSharedRef<SWidget> Body = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				List
			]
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(16.0f, 0.0f, 0.0f, 0.0f))
		[
			SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.rewardHint", "A gift of gold from your own hand raises an officer's loyalty. The ruler needs no reward."), 14.0f, IronStyle::InkSoft())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 10.0f))
			[
				IronStrategy::MakeAmountEditor(IronUI::Loc("ui.strategy.rewardGold", "Gold"), [this]() { return CityGold(); }, &GoldValue, 50)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				IronDialogTownDetail::MakeResultLine(TAttribute<FText>::CreateLambda([this]() { return ResultText; }), TAttribute<FSlateColor>::CreateLambda([this]()
				{
					return FSlateColor(bResultError ? IronStyle::Danger() : IronStyle::Jade());
				}))
			]
		];

	const TSharedRef<SWidget> Buttons = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.rewardButton", "Reward"), FOnClicked::CreateSP(this, &SIronRewardDialog::HandleReward), TAttribute<bool>::CreateLambda([this]()
			{
				return SelectedOfficer >= 0 && GoldValue > 0 && GoldValue <= CityGold() && IronDialogTownDetail::CanAct(Session, CityIndex);
			}), TEXT("Gift"), 160.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronRewardDialog::HandleClose), true, FString(), 130.0f)
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.rewardTitle", "Reward an Officer"), Body, IronDialogTownDetail::MakeFooter(Buttons), 900.0f, 600.0f)
	];
}

int32 SIronRewardDialog::CityGold() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return 0;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), CityIndex);
	return Data ? Data->Gold : 0;
}

TSharedRef<SWidget> SIronRewardDialog::BuildOfficerRow(int32 Officer)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	const FText Name = IronUI::ToText(IronSim::NameOf(*Data));
	const TSharedPtr<FIronSession> SessionRef = Session;

	return SNew(SButton)
		.ButtonStyle(&IronStyle::RowButton())
		.IsFocusable(false)
		.ContentPadding(FMargin(1.0f))
		.OnClicked_Lambda([this, Officer]()
		{
			SelectedOfficer = Officer;
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
					IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Officer), 52.0f)
				]
				+ SHorizontalBox::Slot()
				.FillWidth(1.0f)
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text(Name)
					.Font(IronStyle::BodyBold(15.0f))
					.ColorAndOpacity(IronStyle::Ink())
				]
				+ SHorizontalBox::Slot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				[
					SNew(STextBlock)
					.Text_Lambda([SessionRef, Officer]()
					{
						const IronSim::FOfficer* Live = (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::GetOfficer(SessionRef->State(), Officer) : nullptr;
						return IronUI::LocF("ui.strategy.loyaltyValue", "Loyalty {value}", {{"value", IronSim::ToText(Live ? Live->Loyalty : 0)}});
					})
					.ColorAndOpacity_Lambda([SessionRef, Officer]()
					{
						const IronSim::FOfficer* Live = (SessionRef.IsValid() && SessionRef->HasGame()) ? IronStrategy::GetOfficer(SessionRef->State(), Officer) : nullptr;
						return FSlateColor(IronStrategy::LoyaltyColor(Live ? Live->Loyalty : 0));
					})
					.Font(IronStyle::BodyBold(14.0f))
				]
			]
		];
}

FReply SIronRewardDialog::HandleReward()
{
	if (!Session.IsValid() || !Session->HasGame() || SelectedOfficer < 0)
	{
		return FReply::Handled();
	}
	std::string Error;
	if (Session->Game().RewardOfficer(SelectedOfficer, GoldValue, Error))
	{
		const IronSim::FOfficer* Data = IronStrategy::GetOfficer(Session->State(), SelectedOfficer);
		bResultError = false;
		ResultText = IronUI::LocF("ui.strategy.rewarded", "{name} is grateful. Loyalty is now {loyalty}.", {{"name", IronUI::ToStd(IronStrategy::OfficerName(Session->State(), SelectedOfficer).ToString())}, {"loyalty", IronSim::ToText(Data ? Data->Loyalty : 0)}});
		GoldValue = FMath::Min(GoldValue, CityGold());
		Session->NotifyStateChanged();
	}
	else
	{
		bResultError = true;
		ResultText = Error.empty() ? IronUI::Loc("ui.strategy.rewardFailed", "The reward could not be given.") : IronUI::ToText(Error);
	}
	return FReply::Handled();
}

FReply SIronRewardDialog::HandleClose()
{
	IronDialogTownDetail::PopModal(Root);
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Prisoner list
// -------------------------------------------------------------------------------------------------

void SIronPrisonerListDialog::Construct(const FArguments& InArgs)
{
	Root = InArgs._Root;
	OnDecide = InArgs._OnDecide;
	const TSharedPtr<FIronSession> SessionRef = InArgs._Session;

	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	int32 Count = 0;
	if (SessionRef.IsValid() && SessionRef->HasGame())
	{
		const IronSim::FGameState& GameState = SessionRef->State();
		for (const int Prisoner : GameState.PrisonersInCity(InArgs._City))
		{
			const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Prisoner);
			if (!Data || (Data->Captor >= 0 && Data->Captor != GameState.PlayerFaction))
			{
				continue;
			}
			++Count;
			const int32 PrisonerIndex = Prisoner;
			TWeakPtr<SIronPrisonerListDialog> WeakSelf = SharedThis(this);
			List->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 2.0f))
			[
				SNew(SBorder)
				.BorderImage(IronStyle::WhiteBrush())
				.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.3f))
				.Padding(FMargin(6.0f))
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
					[
						IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Prisoner), 64.0f)
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
							.Text(IronUI::ToText(IronSim::NameOf(*Data)))
							.Font(IronStyle::BodyBold(15.0f))
							.ColorAndOpacity(IronStyle::Ink())
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							IronStrategy::MakeStatsRow(*Data, -1, 12.0f)
						]
						+ SVerticalBox::Slot()
						.AutoHeight()
						[
							SNew(STextBlock)
							.Text(IronUI::LocF("ui.strategy.formerlyOf", "Formerly of {faction}", {{"faction", IronUI::ToStd(IronStrategy::FactionName(GameState, Data->Faction).ToString())}}))
							.Font(IronStyle::Body(12.0f))
							.ColorAndOpacity(IronStyle::InkSoft())
						]
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					[
						IronStyle::MakeButton(IronUI::Loc("ui.strategy.decideEllipsis", "Decide..."), FOnClicked::CreateLambda([WeakSelf, PrisonerIndex]()
						{
							TSharedPtr<SIronPrisonerListDialog> Self = WeakSelf.Pin();
							if (Self.IsValid() && Self->OnDecide)
							{
								const FIronIndexCallback Callback = Self->OnDecide;
								Callback(PrisonerIndex);
							}
							return FReply::Handled();
						}), TAttribute<bool>::CreateLambda([SessionRef]()
						{
							return SessionRef.IsValid() && SessionRef->HasGame() && SessionRef->Game().IsPlanning();
						}), TEXT("Prisoner"), 150.0f)
					]
				]
			];
		}
	}
	if (Count == 0)
	{
		List->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noPrisoners", "No prisoners are held in this city."), 15.0f, IronStyle::InkSoft())
		];
	}

	const TSharedRef<SWidget> Body = SNew(SScrollBox)
		+ SScrollBox::Slot()
		[
			List
		];
	const TSharedRef<SWidget> Buttons = IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronPrisonerListDialog::HandleClose), true, FString(), 130.0f);

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.prisonersTitle", "Prisoners"), Body, IronDialogTownDetail::MakeFooter(Buttons), 760.0f, 560.0f)
	];
}

FReply SIronPrisonerListDialog::HandleClose()
{
	IronDialogTownDetail::PopModal(Root);
	return FReply::Handled();
}
