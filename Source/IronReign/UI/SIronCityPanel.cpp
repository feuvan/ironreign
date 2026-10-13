#include "UI/SIronCityPanel.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronStrategyCommon.h"

#include "Templates/TypeHash.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronCityPanelDetail
{
	uint32 Mix(uint32 Hash, int32 Value)
	{
		return HashCombine(Hash, GetTypeHash(Value));
	}

	FString FieldIcon(int32 FieldIndex)
	{
		static const TCHAR* Icons[] = {TEXT("Population"), TEXT("Farm"), TEXT("Commerce"), TEXT("Defense"), TEXT("Order"), TEXT("Troops"), TEXT("Training"), TEXT("Gold"), TEXT("Food")};
		return (FieldIndex >= 0 && FieldIndex < 9) ? FString(Icons[FieldIndex]) : FString();
	}
}

void SIronCityPanel::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	CityIndex = InArgs._City;
	Rebuild();
}

void SIronCityPanel::SetCity(int32 InCity)
{
	if (InCity == CityIndex)
	{
		Refresh();
		return;
	}
	CityIndex = InCity;
	Rebuild();
}

void SIronCityPanel::Refresh()
{
	if (ComputeSignature() != Signature)
	{
		Rebuild();
	}
}

uint32 SIronCityPanel::ComputeSignature() const
{
	uint32 Hash = GetTypeHash(CityIndex);
	if (!Session.IsValid() || !Session->HasGame())
	{
		return Hash;
	}
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FCity* Data = IronStrategy::GetCity(GameState, CityIndex);
	if (!Data)
	{
		return Hash;
	}
	Hash = IronCityPanelDetail::Mix(Hash, GameState.PlayerFaction);
	Hash = IronCityPanelDetail::Mix(Hash, Data->Owner);
	Hash = IronCityPanelDetail::Mix(Hash, Data->bDelegated ? 1 : 0);
	Hash = IronCityPanelDetail::Mix(Hash, GameState.Year * 12 + GameState.Month);
	Hash = IronCityPanelDetail::Mix(Hash, static_cast<int32>(GameState.Phase));
	Hash = IronCityPanelDetail::Mix(Hash, static_cast<int32>(GameState.Orders.size()));
	for (const int Officer : GameState.CityOfficers(CityIndex))
	{
		Hash = IronCityPanelDetail::Mix(Hash, Officer);
		const IronSim::FOrder* Order = GameState.OfficerOrder(Officer);
		Hash = IronCityPanelDetail::Mix(Hash, Order ? static_cast<int32>(Order->Type) : -1);
		if (const IronSim::FOfficer* OfficerData = IronStrategy::GetOfficer(GameState, Officer))
		{
			Hash = IronCityPanelDetail::Mix(Hash, OfficerData->Loyalty);
		}
	}
	Hash = IronCityPanelDetail::Mix(Hash, 7777);
	for (const int Officer : GameState.FreeOfficersInCity(CityIndex))
	{
		Hash = IronCityPanelDetail::Mix(Hash, Officer);
	}
	Hash = IronCityPanelDetail::Mix(Hash, 8888);
	for (const int Officer : GameState.PrisonersInCity(CityIndex))
	{
		Hash = IronCityPanelDetail::Mix(Hash, Officer);
	}
	Hash = IronCityPanelDetail::Mix(Hash, GameState.SectInCity(CityIndex));
	return Hash;
}

int32 SIronCityPanel::FieldValue(EField Field) const
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
	switch (Field)
	{
	case EField::Population: return Data->Population;
	case EField::Farm: return Data->Farm;
	case EField::Commerce: return Data->Commerce;
	case EField::Defense: return Data->Defense;
	case EField::Order: return Data->Order;
	case EField::Troops: return Data->Troops;
	case EField::Training: return Data->Training;
	case EField::Gold: return Data->Gold;
	case EField::Food: return Data->Food;
	}
	return 0;
}

int32 SIronCityPanel::FieldMax(EField Field) const
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
	switch (Field)
	{
	case EField::Population: return Data->PopulationMax;
	case EField::Farm: return Data->FarmMax;
	case EField::Commerce: return Data->CommerceMax;
	case EField::Defense: return Data->DefenseMax;
	case EField::Order:
	case EField::Training:
		return 100;
	case EField::Troops:
	case EField::Gold:
	case EField::Food:
		return 0;
	}
	return 0;
}

FText SIronCityPanel::FieldText(EField Field, bool bExact) const
{
	const int32 Value = FieldValue(Field);
	const int32 Max = FieldMax(Field);
	const FText ValueText = bExact ? IronStrategy::Num(Value) : IronStrategy::ApproxNum(Value);
	if (Max > 0 && Field != EField::Order && Field != EField::Training)
	{
		return IronUI::LocF("ui.strategy.valueOfMax", "{value} / {max}", {{"value", IronUI::ToStd(ValueText.ToString())}, {"max", IronUI::ToStd(IronStrategy::Num(Max).ToString())}});
	}
	return ValueText;
}

float SIronCityPanel::FieldFraction(EField Field) const
{
	const int32 Max = FieldMax(Field);
	if (Max <= 0)
	{
		return 0.0f;
	}
	return FMath::Clamp(static_cast<float>(FieldValue(Field)) / static_cast<float>(Max), 0.0f, 1.0f);
}

TSharedRef<SWidget> SIronCityPanel::BuildStatLine(EField Field, bool bExact) const
{
	FText Label;
	FLinearColor BarColor = IronStyle::Jade();
	switch (Field)
	{
	case EField::Population: Label = IronUI::Loc("ui.strategy.population", "Population"); BarColor = IronStyle::Indigo(); break;
	case EField::Farm: Label = IronUI::Loc("ui.strategy.farm", "Farmland"); break;
	case EField::Commerce: Label = IronUI::Loc("ui.strategy.commerce", "Commerce"); BarColor = IronStyle::Gold(); break;
	case EField::Defense: Label = IronUI::Loc("ui.strategy.defense", "Defense"); BarColor = IronStyle::InkSoft(); break;
	case EField::Order: Label = IronUI::Loc("ui.strategy.order", "Public Order"); BarColor = IronStyle::Indigo(); break;
	case EField::Troops: Label = IronUI::Loc("ui.strategy.troops", "Troops"); break;
	case EField::Training: Label = IronUI::Loc("ui.strategy.training", "Training"); BarColor = IronStyle::Lacquer(); break;
	case EField::Gold: Label = IronUI::Loc("ui.strategy.gold", "Gold"); break;
	case EField::Food: Label = IronUI::Loc("ui.strategy.food", "Food"); break;
	}
	const bool bHasBar = FieldMax(Field) > 0;

	TSharedRef<SVerticalBox> Line = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.0f, 0.0f, 6.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(20.0f)
				.HeightOverride(20.0f)
				[
					SNew(SImage)
					.Image(FIronAssets::Get().Icon(IronCityPanelDetail::FieldIcon(static_cast<int32>(Field))))
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(IronStyle::Body(14.0f))
				.ColorAndOpacity(IronStyle::InkSoft())
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text_Lambda([this, Field, bExact]() { return FieldText(Field, bExact); })
				.Font(IronStyle::BodyBold(14.0f))
				.ColorAndOpacity(IronStyle::Ink())
			]
		];
	if (bHasBar)
	{
		Line->AddSlot()
		.AutoHeight()
		.Padding(FMargin(26.0f, 2.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeBar(TAttribute<float>::CreateLambda([this, Field]() { return FieldFraction(Field); }), BarColor, 6.0f)
		];
	}
	return Line;
}

TSharedRef<SWidget> SIronCityPanel::BuildHeader() const
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FCity& Data = GameState.Cities[static_cast<size_t>(CityIndex)];
	const FText Name = IronUI::ToText(IronSim::NameOf(Data));
	const FString NameZh = (IronStrategy::IsEnglishCulture() && !Data.NameZh.empty()) ? IronUI::ToFString(Data.NameZh) : FString();
	const IronSim::FFaction* Owner = IronStrategy::GetFaction(GameState, Data.Owner);
	const bool bCapital = Owner && Owner->Capital == CityIndex;

	FText OwnerLine = IronStrategy::FactionName(GameState, Data.Owner);
	if (bCapital)
	{
		OwnerLine = IronUI::LocF("ui.strategy.capitalOf", "Capital of {faction}", {{"faction", IronUI::ToStd(OwnerLine.ToString())}});
	}
	const FText SizeLine = IronUI::LocF("ui.strategy.sizeTerrain", "{size}, {terrain}", {{"size", IronUI::ToStd(IronStrategy::CitySizeName(Data.Size).ToString())}, {"terrain", IronSim::DisplayName(Data.Terrain)}});

	TSharedRef<SHorizontalBox> TitleRow = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Bottom)
		[
			SNew(STextBlock)
			.Text(Name)
			.Font(IronStyle::Heading(26.0f))
			.ColorAndOpacity(IronStyle::Ink())
		];
	if (!NameZh.IsEmpty())
	{
		TitleRow->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(8.0f, 0.0f, 0.0f, 2.0f))
		[
			SNew(STextBlock)
			.Text(FText::FromString(NameZh))
			.Font(IronStyle::Brush(22.0f))
			.ColorAndOpacity(IronStyle::Lacquer())
		];
	}

	TSharedRef<SVerticalBox> Info = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			TitleRow
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(OwnerLine)
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(IronStyle::FactionColor(Data.Owner) * FLinearColor(0.75f, 0.75f, 0.75f, 1.0f))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(SizeLine)
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		];
	if (Data.bDelegated && Data.Owner == GameState.PlayerFaction)
	{
		Info->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeIconValue(TEXT("Delegate"), IronUI::Loc("ui.strategy.delegatedTag", "Governed by a delegate"), 18.0f, IronStyle::Indigo())
		];
	}

	TSharedRef<SHorizontalBox> Header = SNew(SHorizontalBox);
	if (Data.Owner >= 0)
	{
		Header->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.0f, 0.0f, 10.0f, 0.0f))
		[
			IronStyle::MakeBanner(Data.Owner, 64.0f)
		];
	}
	Header->AddSlot()
	.FillWidth(1.0f)
	.VAlign(VAlign_Center)
	[
		Info
	];
	return Header;
}

TSharedRef<SWidget> SIronCityPanel::BuildOfficerRow(int32 Officer, bool bDetailed) const
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	const bool bRuler = GameState.IsRuler(Officer);
	FText Name = IronUI::ToText(IronSim::NameOf(*Data));
	if (bRuler)
	{
		Name = IronUI::LocF("ui.strategy.rulerName", "{name} (Ruler)", {{"name", IronSim::NameOf(*Data)}});
	}
	TSharedPtr<FIronSession> SessionRef = Session;

	TSharedRef<SVerticalBox> Details = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Name)
				.Font(IronStyle::BodyBold(15.0f))
				.ColorAndOpacity(bRuler ? IronStyle::Lacquer() : IronStyle::Ink())
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				IronStyle::MakeIconValue(TEXT("Loyalty"), FText::AsNumber(Data->Loyalty), 18.0f, IronStrategy::LoyaltyColor(Data->Loyalty))
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f))
		[
			IronStrategy::MakeStatsRow(*Data, -1, 12.0f)
		];
	if (bDetailed)
	{
		Details->AddSlot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text_Lambda([SessionRef, Officer]()
			{
				if (!SessionRef.IsValid() || !SessionRef->HasGame())
				{
					return FText::GetEmpty();
				}
				return IronStrategy::OfficerActivity(SessionRef->State(), Officer);
			})
			.Font(IronStyle::Body(12.0f))
			.ColorAndOpacity(IronStyle::Indigo())
		];
	}

	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.35f))
		.Padding(FMargin(4.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Top)
			.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
			[
				IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Officer), 64.0f)
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				Details
			]
		];
}

TSharedRef<SWidget> SIronCityPanel::BuildCompactOfficerRow(int32 Officer, const FText& Note) const
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(0.0f, 0.0f, 6.0f, 0.0f))
		[
			IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Officer), 44.0f)
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
				.Font(IronStyle::BodyBold(14.0f))
				.ColorAndOpacity(IronStyle::Ink())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				IronStrategy::MakeStatsRow(*Data, -1, 11.0f)
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(Note)
				.Font(IronStyle::Body(12.0f))
				.ColorAndOpacity(IronStyle::InkSoft())
			]
		];
}

void SIronCityPanel::Rebuild()
{
	Signature = ComputeSignature();

	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetCity(Session->State(), CityIndex) != nullptr;
	if (!bValid)
	{
		ChildSlot
		[
			IronStyle::MakePanel(
				SNew(SBox)
				.VAlign(VAlign_Center)
				.HAlign(HAlign_Center)
				[
					IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.selectCity", "Select a city on the map."), 15.0f, IronStyle::InkSoft())
				],
				false,
				FMargin(18.0f))
		];
		return;
	}

	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FCity& Data = GameState.Cities[static_cast<size_t>(CityIndex)];
	const bool bOwn = GameState.PlayerFaction >= 0 && Data.Owner == GameState.PlayerFaction;
	const bool bAllied = !bOwn && GameState.AreAllied(GameState.PlayerFaction, Data.Owner);
	const bool bFull = bOwn || bAllied;

	TSharedRef<SVerticalBox> Body = SNew(SVerticalBox);
	Body->AddSlot()
	.AutoHeight()
	[
		BuildHeader()
	];
	const std::string Description = IronSim::DescriptionOf(Data);
	if (!Description.empty())
	{
		Body->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
		[
			IronStrategy::MakeWrappedText(IronUI::ToText(Description), 13.0f, IronStyle::InkSoft())
		];
	}
	Body->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 8.0f, 0.0f, 6.0f))
	[
		SNew(SBox)
		.HeightOverride(10.0f)
		[
			SNew(SImage)
			.Image(IronStyle::Divider())
		]
	];

	// Development and garrison.
	TArray<EField> Fields;
	if (bFull)
	{
		Fields = {EField::Population, EField::Farm, EField::Commerce, EField::Defense, EField::Order, EField::Troops, EField::Training, EField::Gold, EField::Food};
	}
	else
	{
		Fields = {EField::Population, EField::Defense, EField::Troops};
	}
	for (const EField Field : Fields)
	{
		const bool bExact = bFull || Field == EField::Defense;
		Body->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f))
		[
			BuildStatLine(Field, bExact)
		];
	}

	// Officers stationed in the city.
	const std::vector<int> Stationed = GameState.CityOfficers(CityIndex);
	Body->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 12.0f, 0.0f, 2.0f))
	[
		IronStrategy::MakeSectionTitle(IronUI::LocF("ui.strategy.officersCount", "Officers ({count})", {{"count", IronSim::ToText(static_cast<int>(Stationed.size()))}}))
	];
	if (bFull)
	{
		if (Stationed.empty())
		{
			Body->AddSlot()
			.AutoHeight()
			[
				IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noOfficers", "No officers are stationed here."), 13.0f, IronStyle::InkSoft())
			];
		}
		for (const int Officer : Stationed)
		{
			Body->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 2.0f))
			[
				BuildOfficerRow(Officer, bOwn)
			];
		}
	}
	else
	{
		Body->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.foreignOfficers", "Our scouts cannot tell more about the officers in this city."), 13.0f, IronStyle::InkSoft())
		];
	}

	// Tavern wanderers and prisoners (own cities only).
	if (bOwn)
	{
		const std::vector<int> FreeOfficers = GameState.FreeOfficersInCity(CityIndex);
		if (!FreeOfficers.empty())
		{
			Body->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 12.0f, 0.0f, 2.0f))
			[
				IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.tavernTitle", "In the Tavern"))
			];
			for (const int Officer : FreeOfficers)
			{
				Body->AddSlot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 2.0f))
				[
					BuildCompactOfficerRow(Officer, IronUI::Loc("ui.strategy.freeOfficer", "Wandering hero"))
				];
			}
		}

		const std::vector<int> Prisoners = GameState.PrisonersInCity(CityIndex);
		if (!Prisoners.empty())
		{
			Body->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 12.0f, 0.0f, 2.0f))
			[
				IronStrategy::MakeSectionTitle(IronUI::Loc("ui.strategy.prisonersTitle", "Prisoners"))
			];
			for (const int Officer : Prisoners)
			{
				const IronSim::FOfficer* Prisoner = IronStrategy::GetOfficer(GameState, Officer);
				const FText Note = IronUI::LocF("ui.strategy.formerlyOf", "Formerly of {faction}", {{"faction", IronUI::ToStd(IronStrategy::FactionName(GameState, Prisoner ? Prisoner->Faction : -1).ToString())}});
				Body->AddSlot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 2.0f))
				[
					BuildCompactOfficerRow(Officer, Note)
				];
			}
		}
	}

	// Martial sect.
	const int32 SectIndex = GameState.SectInCity(CityIndex);
	if (const IronSim::FSect* Sect = IronStrategy::GetSect(GameState, SectIndex))
	{
		const int32 Favor = (GameState.PlayerFaction >= 0 && GameState.PlayerFaction < static_cast<int32>(Sect->Favor.size())) ? Sect->Favor[static_cast<size_t>(GameState.PlayerFaction)] : 0;
		Body->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 12.0f, 0.0f, 2.0f))
		[
			IronStrategy::MakeSectionTitle(IronUI::LocF("ui.strategy.sectTitle", "Sect: {sect}", {{"sect", IronSim::NameOf(*Sect)}}))
		];
		Body->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::ToText(IronSim::DescriptionOf(*Sect)), 13.0f, IronStyle::InkSoft())
		];
		Body->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 2.0f))
		[
			IronStrategy::MakeWrappedText(IronUI::LocF("ui.strategy.sectMasterFavor", "Master: {master}   Favor toward us: {favor}", {{"master", IronUI::ToStd(IronStrategy::OfficerName(GameState, Sect->Master).ToString())}, {"favor", IronSim::ToText(Favor)}}), 13.0f, IronStyle::Ink())
		];
	}

	ChildSlot
	[
		IronStyle::MakePanel(
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				Body
			],
			false,
			FMargin(16.0f))
	];
}
