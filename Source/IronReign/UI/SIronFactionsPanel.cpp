#include "UI/SIronFactionsPanel.h"

#include "Sim/IronGame.h"
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
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

void SIronFactionsPanel::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;

	TSharedRef<SVerticalBox> List = SNew(SVerticalBox);
	if (Session.IsValid() && Session->HasGame())
	{
		const IronSim::FGameState& GameState = Session->State();
		// The player's faction first, then every other living faction.
		if (GameState.PlayerFaction >= 0 && GameState.PlayerFaction < static_cast<int32>(GameState.Factions.size()))
		{
			List->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 3.0f))
			[
				BuildFactionRow(GameState.PlayerFaction)
			];
		}
		for (int32 Index = 0; Index < static_cast<int32>(GameState.Factions.size()); ++Index)
		{
			if (Index == GameState.PlayerFaction || !GameState.Factions[static_cast<size_t>(Index)].bAlive)
			{
				continue;
			}
			List->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 3.0f))
			[
				BuildFactionRow(Index)
			];
		}
		int32 Independent = 0;
		for (const IronSim::FCity& City : GameState.Cities)
		{
			if (City.Owner < 0)
			{
				++Independent;
			}
		}
		if (Independent > 0)
		{
			List->AddSlot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
			[
				IronStrategy::MakeWrappedText(IronUI::LocF("ui.strategy.independentCities", "{count} cities answer to no lord.", {{"count", IronSim::ToText(Independent)}}), 14.0f, IronStyle::InkSoft())
			];
		}
	}

	const TSharedRef<SWidget> Body = SNew(SScrollBox)
		+ SScrollBox::Slot()
		[
			List
		];
	const TSharedRef<SWidget> Footer = SNew(SBox)
		.HAlign(HAlign_Right)
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronFactionsPanel::HandleClose), true, FString(), 140.0f)
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.factionsTitle", "Factions of the Nine Provinces"), Body, Footer, 1100.0f, 780.0f)
	];
}

TSharedRef<SWidget> SIronFactionsPanel::BuildFactionRow(int32 Faction)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FFaction* Data = IronStrategy::GetFaction(GameState, Faction);
	if (!Data)
	{
		return SNew(SBox);
	}
	const bool bPlayer = Faction == GameState.PlayerFaction;
	const int32 Cities = Session->Game().CityCount(Faction);
	const int32 OfficerCount = static_cast<int32>(GameState.FactionOfficers(Faction).size());
	const int32 Troops = GameState.FactionTotalTroops(Faction);
	const FText Name = IronUI::ToText(IronSim::NameOf(*Data));
	const FString NameZh = (IronStrategy::IsEnglishCulture() && !Data->NameZh.empty()) ? IronUI::ToFString(Data->NameZh) : FString();

	TSharedRef<SHorizontalBox> TitleRow = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Bottom)
		[
			SNew(STextBlock)
			.Text(Name)
			.Font(IronStyle::Heading(24.0f))
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
	if (bPlayer)
	{
		TitleRow->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Bottom)
		.Padding(FMargin(10.0f, 0.0f, 0.0f, 3.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.strategy.ourFaction", "(our house)"))
			.Font(IronStyle::BodyBold(14.0f))
			.ColorAndOpacity(IronStyle::Jade())
		];
	}

	const FText RulerLine = IronUI::LocF("ui.strategy.rulerAndCapital", "Ruler {ruler} - capital {capital}", {{"ruler", IronUI::ToStd(IronStrategy::OfficerName(GameState, Data->Ruler).ToString())}, {"capital", IronUI::ToStd(IronStrategy::CityName(GameState, Data->Capital).ToString())}});
	const FText TroopsText = bPlayer ? IronStrategy::Num(Troops) : IronStrategy::ApproxNum(Troops);

	TSharedRef<SHorizontalBox> Figures = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(0.0f, 0.0f, 18.0f, 0.0f))
		[
			IronStyle::MakeIconValue(TEXT("Walls"), IronUI::LocF("ui.strategy.citiesCount", "{count} cities", {{"count", IronSim::ToText(Cities)}}), 22.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(0.0f, 0.0f, 18.0f, 0.0f))
		[
			IronStyle::MakeIconValue(TEXT("Officers"), IronUI::LocF("ui.strategy.officersCountShort", "{count} officers", {{"count", IronSim::ToText(OfficerCount)}}), 22.0f)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			IronStyle::MakeIconValue(TEXT("Troops"), TroopsText, 22.0f)
		];
	if (bPlayer)
	{
		Figures->AddSlot()
		.AutoWidth()
		.Padding(FMargin(18.0f, 0.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeIconValue(TEXT("Gold"), IronStrategy::Num(GameState.FactionTotalGold(Faction)), 22.0f)
		];
		Figures->AddSlot()
		.AutoWidth()
		.Padding(FMargin(18.0f, 0.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeIconValue(TEXT("Food"), IronStrategy::Num(GameState.FactionTotalFood(Faction)), 22.0f)
		];
	}

	TSharedRef<SWidget> RelationBox = SNew(SBox);
	if (!bPlayer && GameState.PlayerFaction >= 0)
	{
		const IronSim::FRelation& Relation = GameState.Relation(GameState.PlayerFaction, Faction);
		FText Status = IronUI::Loc("ui.strategy.hostile", "Hostile");
		FLinearColor StatusColor = IronStyle::Lacquer();
		if (Relation.AllianceMonths > 0)
		{
			Status = IronUI::LocF("ui.strategy.allied", "Allied ({months} months)", {{"months", IronSim::ToText(Relation.AllianceMonths)}});
			StatusColor = IronStyle::Jade();
		}
		else if (Relation.TruceMonths > 0)
		{
			Status = IronUI::LocF("ui.strategy.truce", "Truce ({months} months)", {{"months", IronSim::ToText(Relation.TruceMonths)}});
			StatusColor = IronStyle::Indigo();
		}
		RelationBox = SNew(SBox)
			.WidthOverride(230.0f)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(Status)
					.Font(IronStyle::BodyBold(15.0f))
					.ColorAndOpacity(StatusColor)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 4.0f, 0.0f, 2.0f))
				[
					SNew(STextBlock)
					.Text(IronUI::LocF("ui.strategy.trustLine", "Trust toward us: {trust}", {{"trust", IronSim::ToText(Relation.Trust)}}))
					.Font(IronStyle::Body(13.0f))
					.ColorAndOpacity(IronStyle::Ink())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					IronStyle::MakeBar(FMath::Clamp(static_cast<float>(Relation.Trust) / 100.0f, 0.0f, 1.0f), IronStyle::Jade(), 7.0f)
				]
			];
	}

	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(bPlayer ? IronStyle::Gold().CopyWithNewOpacity(0.25f) : IronStyle::PaperDark().CopyWithNewOpacity(0.3f))
		.Padding(FMargin(8.0f))
		[
			SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.0f, 0.0f, 10.0f, 0.0f))
			[
				IronStyle::MakeBanner(Faction, 84.0f)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.0f, 0.0f, 12.0f, 0.0f))
			[
				IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Data->Ruler), 100.0f)
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					TitleRow
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					SNew(STextBlock)
					.Text(RulerLine)
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(IronStyle::InkSoft())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
				[
					Figures
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				RelationBox
			]
		];
}

FReply SIronFactionsPanel::HandleClose()
{
	FIronAudio::Get().PlaySfx(TEXT("Cancel"));
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->PopModal();
	}
	return FReply::Handled();
}
