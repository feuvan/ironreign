#include "UI/SIronStrategyDialogs.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronStrategyCommon.h"

#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronStrategyDialogsDetail
{
	/** Player-facing names used for {placeholders} in translated event text. */
	std::string RulerNameOf(const IronSim::FGameState& State, int32 Faction)
	{
		const IronSim::FFaction* Data = IronStrategy::GetFaction(State, Faction);
		if (!Data)
		{
			return std::string();
		}
		return IronUI::ToStd(IronStrategy::OfficerName(State, Data->Ruler).ToString());
	}

	std::string FormatEventText(const IronSim::FGameState& State, const IronSim::FPendingEvent& Pending, const std::string& Pattern)
	{
		const int32 Faction = Pending.Faction >= 0 ? Pending.Faction : State.PlayerFaction;
		return IronSim::FormatText(Pattern, {
			{"city", IronUI::ToStd(IronStrategy::CityName(State, Pending.City).ToString())},
			{"ruler", RulerNameOf(State, State.PlayerFaction)},
			{"faction", IronUI::ToStd(IronStrategy::FactionName(State, Faction).ToString())},
			{"officer", IronUI::ToStd(IronStrategy::OfficerName(State, Pending.Officer).ToString())}});
	}

	const IronSim::FEventDef* EventDefOf(const IronSim::FGameState& State, const IronSim::FPendingEvent& Pending)
	{
		if (Pending.Def < 0 || Pending.Def >= static_cast<int32>(State.Events.size()))
		{
			return nullptr;
		}
		return &State.Events[static_cast<size_t>(Pending.Def)];
	}

	/**
	 * The rules engine resolves placeholders when the event fires. When a translation exists for the active culture
	 * we format the translated pattern ourselves so the event follows the language setting.
	 */
	FText EventTitle(const IronSim::FGameState& State, const IronSim::FPendingEvent& Pending)
	{
		const IronSim::FEventDef* Def = EventDefOf(State, Pending);
		if (Def)
		{
			const std::string Localized = IronSim::TitleOf(*Def);
			if ((!Localized.empty() && Localized != Def->Title) || Pending.Title.empty())
			{
				return IronUI::ToText(FormatEventText(State, Pending, Localized));
			}
		}
		return IronUI::ToText(Pending.Title);
	}

	FText EventBody(const IronSim::FGameState& State, const IronSim::FPendingEvent& Pending)
	{
		const IronSim::FEventDef* Def = EventDefOf(State, Pending);
		if (Def)
		{
			const std::string Localized = IronSim::TextOf(*Def);
			if ((!Localized.empty() && Localized != Def->Text) || Pending.Text.empty())
			{
				return IronUI::ToText(FormatEventText(State, Pending, Localized));
			}
		}
		return IronUI::ToText(Pending.Text);
	}

	FText ChoiceLabel(const IronSim::FGameState& State, const IronSim::FPendingEvent& Pending, int32 ChoiceIndex)
	{
		const std::string& Resolved = Pending.Choices[static_cast<size_t>(ChoiceIndex)].Label;
		const IronSim::FEventDef* Def = EventDefOf(State, Pending);
		if (Def && Def->Choices.size() == Pending.Choices.size())
		{
			const std::string Localized = IronSim::ChoiceLabelOf(*Def, ChoiceIndex);
			if ((!Localized.empty() && Localized != Def->Choices[static_cast<size_t>(ChoiceIndex)].Label) || Resolved.empty())
			{
				return IronUI::ToText(FormatEventText(State, Pending, Localized));
			}
		}
		if (Resolved.empty())
		{
			return IronUI::LocF("ui.strategy.choiceN", "Option {n}", {{"n", IronSim::ToText(ChoiceIndex + 1)}});
		}
		return IronUI::ToText(Resolved);
	}

	TSharedRef<SWidget> MakeKeyValue(const FText& Key, const FText& Value, float Size)
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, 6.0f, 0.0f))
			[
				SNew(STextBlock)
				.Text(Key)
				.Font(IronStyle::Body(Size))
				.ColorAndOpacity(IronStyle::InkSoft())
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				SNew(STextBlock)
				.Text(Value)
				.Font(IronStyle::BodyBold(Size))
				.ColorAndOpacity(IronStyle::Ink())
			];
	}
}

// -------------------------------------------------------------------------------------------------
// Event dialog
// -------------------------------------------------------------------------------------------------

void SIronEventDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	OnChoose = InArgs._OnChoose;

	const IronSim::FPendingEvent* Current = (Session.IsValid() && Session->HasGame()) ? Session->Game().CurrentEvent() : nullptr;
	if (!Current)
	{
		ChildSlot
		[
			IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.eventTitle", "Report"), IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noEvent", "Nothing requires your attention."), 15.0f), IronStyle::MakeButton(IronUI::Loc("ui.strategy.continue", "Continue"), FOnClicked::CreateSP(this, &SIronEventDialog::HandleChoice, 0)), 520.0f, 0.0f)
		];
		return;
	}

	// Copy everything we need now: the pending event is owned by the game state.
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FPendingEvent Pending = *Current;
	const FText Title = IronStrategyDialogsDetail::EventTitle(GameState, Pending);
	const FText Body = IronStrategyDialogsDetail::EventBody(GameState, Pending);

	FString ImagePath;
	if (!Pending.Image.empty())
	{
		ImagePath = FString(TEXT("Art/")) + IronUI::ToFString(Pending.Image);
	}
	const bool bHasImage = !ImagePath.IsEmpty() && FIronAssets::Get().Exists(ImagePath);

	const bool bAdvisor = Pending.Speaker < 0;
	const int32 Speaker = bAdvisor ? IronStrategy::PlayerAdvisor(GameState) : Pending.Speaker;
	FText SpeakerName = IronStrategy::OfficerName(GameState, Speaker);
	if (bAdvisor)
	{
		SpeakerName = IronUI::LocF("ui.strategy.advisorName", "Advisor {name}", {{"name", IronUI::ToStd(SpeakerName.ToString())}});
	}

	TSharedRef<SHorizontalBox> Visuals = SNew(SHorizontalBox);
	if (bHasImage)
	{
		Visuals->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.0f, 0.0f, 18.0f, 0.0f))
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(IronStyle::Ink())
			.Padding(FMargin(3.0f))
			[
				SNew(SBox)
				.WidthOverride(448.0f)
				.HeightOverride(252.0f)
				[
					SNew(SImage)
					.Image(FIronAssets::Get().Image(ImagePath))
				]
			]
		];
	}
	Visuals->AddSlot()
	.FillWidth(1.0f)
	.VAlign(VAlign_Top)
	[
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Speaker), bHasImage ? 170.0f : 200.0f)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
		[
			SNew(STextBlock)
			.Text(SpeakerName)
			.Font(IronStyle::BodyBold(15.0f))
			.ColorAndOpacity(IronStyle::Ink())
		]
	];

	TSharedRef<SVerticalBox> Choices = SNew(SVerticalBox);
	TSharedPtr<FIronSession> SessionRef = Session;
	for (int32 Index = 0; Index < static_cast<int32>(Pending.Choices.size()); ++Index)
	{
		const IronSim::FEventChoice& Choice = Pending.Choices[static_cast<size_t>(Index)];
		FText Label = IronStrategyDialogsDetail::ChoiceLabel(GameState, Pending, Index);
		if (Choice.RequireGold > 0)
		{
			Label = IronUI::LocF("ui.strategy.choiceWithGold", "{label} ({gold} gold)", {{"label", IronUI::ToStd(Label.ToString())}, {"gold", IronSim::ToText(Choice.RequireGold)}});
		}
		const int32 ChoiceIndex = Index;
		Choices->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		.Padding(FMargin(0.0f, 3.0f))
		[
			IronStyle::MakeButton(Label, FOnClicked::CreateSP(this, &SIronEventDialog::HandleChoice, ChoiceIndex), TAttribute<bool>::CreateLambda([SessionRef, ChoiceIndex]()
			{
				return SessionRef.IsValid() && SessionRef->HasGame() && SessionRef->Game().CanChoose(ChoiceIndex);
			}), FString(), 420.0f)
		];
	}
	if (Pending.Choices.empty())
	{
		Choices->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.continue", "Continue"), FOnClicked::CreateSP(this, &SIronEventDialog::HandleChoice, 0), true, FString(), 260.0f)
		];
	}

	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(1040.0f)
		[
			SNew(SBorder)
			.BorderImage(FIronAssets::Get().Box(TEXT("Art/UI/Scroll.png"), FMargin(80.0f)))
			.Padding(FMargin(100.0f, 60.0f, 100.0f, 56.0f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					SNew(STextBlock)
					.Text(Title)
					.Font(IronStyle::Heading(30.0f))
					.ColorAndOpacity(IronStyle::Lacquer())
					.Justification(ETextJustify::Center)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 4.0f, 0.0f, 12.0f))
				[
					SNew(SBox)
					.HeightOverride(12.0f)
					[
						SNew(SImage)
						.Image(IronStyle::Divider())
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					Visuals
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 14.0f, 0.0f, 12.0f))
				[
					SNew(SBox)
					.MaxDesiredHeight(170.0f)
					[
						SNew(SScrollBox)
						+ SScrollBox::Slot()
						[
							IronStrategy::MakeWrappedText(Body, 17.0f, IronStyle::Ink())
						]
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					Choices
				]
			]
		]
	];
}

FReply SIronEventDialog::HandleChoice(int32 ChoiceIndex)
{
	if (bAnswered)
	{
		return FReply::Handled();
	}
	bAnswered = true;
	if (OnChoose)
	{
		OnChoose(ChoiceIndex);
	}
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Prisoner dialog
// -------------------------------------------------------------------------------------------------

void SIronPrisonerDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	OnDecided = InArgs._OnDecided;
	PrisonerIndex = InArgs._Prisoner;

	const bool bValid = Session.IsValid() && Session->HasGame() && IronStrategy::GetOfficer(Session->State(), PrisonerIndex) != nullptr;
	if (!bValid)
	{
		ChildSlot
		[
			IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.prisonerTitle", "Prisoner"), IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.prisonerGone", "The prisoner is no longer here."), 15.0f), IronStyle::MakeButton(IronUI::Loc("ui.strategy.continue", "Continue"), FOnClicked::CreateSP(this, &SIronPrisonerDialog::HandleDecision, IronSim::EPrisonerDecision::Imprison)), 520.0f, 0.0f)
		];
		return;
	}

	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer& Data = GameState.Officers[static_cast<size_t>(PrisonerIndex)];
	const int32 Chance = Session->Game().PrisonerRecruitChance(PrisonerIndex);
	const std::string Epithet = IronSim::EpithetOf(Data);
	const std::string Bio = IronSim::BioOf(Data);

	TSharedRef<SVerticalBox> Info = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(IronUI::ToText(IronSim::NameOf(Data)))
			.Font(IronStyle::Heading(28.0f))
			.ColorAndOpacity(IronStyle::Ink())
		];
	if (!Epithet.empty())
	{
		Info->AddSlot()
		.AutoHeight()
		[
			SNew(STextBlock)
			.Text(IronUI::ToText(Epithet))
			.Font(IronStyle::Body(15.0f))
			.ColorAndOpacity(IronStyle::Lacquer())
		];
	}
	Info->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
	[
		IronStrategyDialogsDetail::MakeKeyValue(IronUI::Loc("ui.strategy.formerFaction", "Served:"), IronStrategy::FactionName(GameState, Data.Faction), 15.0f)
	];
	Info->AddSlot()
	.AutoHeight()
	[
		IronStrategyDialogsDetail::MakeKeyValue(IronUI::Loc("ui.strategy.ageLabel", "Age:"), FText::AsNumber(GameState.OfficerAge(PrisonerIndex)), 15.0f)
	];
	Info->AddSlot()
	.AutoHeight()
	[
		IronStrategyDialogsDetail::MakeKeyValue(IronUI::Loc("ui.strategy.specialtyLabel", "Specialty:"), IronStrategy::TroopTypeName(Data.Specialty), 15.0f)
	];
	Info->AddSlot()
	.AutoHeight()
	[
		IronStrategyDialogsDetail::MakeKeyValue(IronUI::Loc("ui.strategy.techniquesLabel", "Techniques:"), IronStrategy::TechniqueList(GameState, PrisonerIndex), 15.0f)
	];
	Info->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
	[
		IronStrategy::MakeStatsHeader(-1, 13.0f)
	];
	Info->AddSlot()
	.AutoHeight()
	[
		IronStrategy::MakeStatsRow(Data, -1, 15.0f)
	];
	if (!Bio.empty())
	{
		Info->AddSlot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
		[
			IronStrategy::MakeWrappedText(IronUI::ToText(Bio), 13.0f, IronStyle::InkSoft())
		];
	}
	Info->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 10.0f, 0.0f, 0.0f))
	[
		SNew(STextBlock)
		.Text(IronUI::LocF("ui.strategy.recruitChance", "Chance to win them over: {chance}%", {{"chance", IronSim::ToText(Chance)}}))
		.Font(IronStyle::BodyBold(16.0f))
		.ColorAndOpacity(Chance >= 50 ? IronStyle::Jade() : IronStyle::Lacquer())
	];

	const TSharedRef<SWidget> Body = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Top)
		.Padding(FMargin(0.0f, 0.0f, 18.0f, 0.0f))
		[
			IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, PrisonerIndex), 220.0f)
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		[
			Info
		];

	const TSharedRef<SWidget> Buttons = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.prisonerRecruit", "Recruit"), FOnClicked::CreateSP(this, &SIronPrisonerDialog::HandleDecision, IronSim::EPrisonerDecision::Recruit), true, TEXT("Recruit"))
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.prisonerRelease", "Release"), FOnClicked::CreateSP(this, &SIronPrisonerDialog::HandleDecision, IronSim::EPrisonerDecision::Release), true, TEXT("Move"))
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.prisonerExecute", "Execute"), FOnClicked::CreateSP(this, &SIronPrisonerDialog::HandleDecision, IronSim::EPrisonerDecision::Execute), true, TEXT("Attack"))
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.prisonerImprison", "Imprison"), FOnClicked::CreateSP(this, &SIronPrisonerDialog::HandleDecision, IronSim::EPrisonerDecision::Imprison), true, TEXT("Prisoner"))
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.prisonerTitle", "Prisoner"), Body, Buttons, 860.0f, 0.0f)
	];
}

FReply SIronPrisonerDialog::HandleDecision(IronSim::EPrisonerDecision Decision)
{
	if (bAnswered)
	{
		return FReply::Handled();
	}
	bAnswered = true;
	FText Message;
	if (Session.IsValid() && Session->HasGame() && IronStrategy::GetOfficer(Session->State(), PrisonerIndex) != nullptr)
	{
		std::string Result;
		const bool bApplied = Session->Game().DecidePrisoner(PrisonerIndex, Decision, Result);
		if (!Result.empty())
		{
			Message = IronUI::ToText(Result);
		}
		else if (!bApplied)
		{
			Message = IronUI::Loc("ui.strategy.prisonerFailed", "The decision could not be carried out.");
		}
	}
	if (OnDecided)
	{
		OnDecided(PrisonerIndex, Message);
	}
	return FReply::Handled();
}

// -------------------------------------------------------------------------------------------------
// Battle prompt
// -------------------------------------------------------------------------------------------------

TSharedRef<SWidget> SIronBattlePrompt::BuildSide(const IronSim::FBattleSideSetup& Side, bool bAttacker) const
{
	int32 Total = 0;
	for (const IronSim::FBattleUnitSetup& Unit : Side.Units)
	{
		Total += Unit.Troops;
	}
	FString CommanderPortrait = TEXT("unknown");
	FText CommanderName = IronUI::Loc("ui.strategy.garrisonCommander", "Garrison captain");
	if (!Side.Units.empty())
	{
		const IronSim::FBattleUnitSetup& Lead = Side.Units[0];
		if (!Lead.Portrait.empty())
		{
			CommanderPortrait = IronUI::ToFString(Lead.Portrait);
		}
		if (Session.IsValid() && Session->HasGame() && Lead.Officer >= 0)
		{
			CommanderName = IronStrategy::OfficerName(Session->State(), Lead.Officer);
		}
		else if (!Lead.Name.empty())
		{
			CommanderName = IronUI::ToText(Lead.Name);
		}
	}
	FText SideName = IronUI::ToText(Side.Name);
	if (Session.IsValid() && Session->HasGame() && Side.Faction >= 0)
	{
		SideName = IronStrategy::FactionName(Session->State(), Side.Faction);
	}

	TSharedRef<SVerticalBox> Card = SNew(SVerticalBox);
	if (Side.Faction >= 0)
	{
		Card->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			IronStyle::MakeBanner(Side.Faction, 72.0f)
		];
	}
	Card->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	[
		SNew(STextBlock)
		.Text(SideName)
		.Font(IronStyle::Heading(22.0f))
		.ColorAndOpacity(IronStyle::Ink())
	];
	Card->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	[
		SNew(STextBlock)
		.Text(bAttacker ? IronUI::Loc("ui.strategy.attacker", "Attacker") : IronUI::Loc("ui.strategy.defender", "Defender"))
		.Font(IronStyle::BodyBold(14.0f))
		.ColorAndOpacity(Side.bPlayer ? IronStyle::Jade() : IronStyle::Lacquer())
	];
	Card->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	.Padding(FMargin(0.0f, 8.0f))
	[
		IronStyle::MakePortrait(CommanderPortrait, 130.0f)
	];
	Card->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	[
		SNew(STextBlock)
		.Text(CommanderName)
		.Font(IronStyle::BodyBold(16.0f))
		.ColorAndOpacity(IronStyle::Ink())
	];
	Card->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
	[
		IronStyle::MakeIconValue(TEXT("Troops"), IronUI::LocF("ui.strategy.battleTroops", "{troops} troops in {units} units", {{"troops", IronUI::ToStd(IronStrategy::Num(Total).ToString())}, {"units", IronSim::ToText(static_cast<int>(Side.Units.size()))}}), 22.0f)
	];
	Card->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	[
		SNew(STextBlock)
		.Text(IronUI::LocF("ui.strategy.battleMorale", "Morale {morale}   Training {training}", {{"morale", IronSim::ToText(Side.Morale)}, {"training", IronSim::ToText(Side.Training)}}))
		.Font(IronStyle::Body(14.0f))
		.ColorAndOpacity(IronStyle::InkSoft())
	];
	if (bAttacker && Side.FoodDays < 999)
	{
		Card->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Text(IronUI::LocF("ui.strategy.battleFood", "Food for {days} days", {{"days", IronSim::ToText(Side.FoodDays)}}))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		];
	}

	return SNew(SBorder)
		.BorderImage(IronStyle::WhiteBrush())
		.BorderBackgroundColor(IronStyle::PaperDark().CopyWithNewOpacity(0.45f))
		.Padding(FMargin(14.0f, 10.0f))
		[
			Card
		];
}

void SIronBattlePrompt::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	OnCommand = InArgs._OnCommand;
	OnDelegate = InArgs._OnDelegate;
	const IronSim::FBattleSetup& Setup = InArgs._Setup;

	FText Place = IronUI::ToText(Setup.Location);
	if (InArgs._City >= 0 && Session.IsValid() && Session->HasGame())
	{
		Place = IronStrategy::CityName(Session->State(), InArgs._City);
	}
	const FText Heading = IronUI::LocF("ui.strategy.battleAt", "Battle at {place}!", {{"place", IronUI::ToStd(Place.ToString())}});
	const FText KindText = Setup.Kind == IronSim::EBattleKind::Siege
		? IronUI::LocF("ui.strategy.siegeKind", "Siege ({terrain}). The gate holds {hp} strength.", {{"terrain", IronSim::DisplayName(Setup.Terrain)}, {"hp", IronSim::ToText(Setup.GateHp)}})
		: IronUI::LocF("ui.strategy.fieldKind", "Field battle ({terrain}).", {{"terrain", IronSim::DisplayName(Setup.Terrain)}});
	const FText RoleText = InArgs._PlayerAttacker
		? IronUI::Loc("ui.strategy.weAttack", "Our army is attacking. Will you take command in the field, or leave the battle to your generals?")
		: IronUI::Loc("ui.strategy.weDefend", "We are under attack! Will you take command of the defense, or leave the battle to your generals?");

	TSharedRef<SVerticalBox> Body = SNew(SVerticalBox);
	if (!Setup.Location.empty())
	{
		Body->AddSlot()
		.AutoHeight()
		.HAlign(HAlign_Center)
		[
			SNew(STextBlock)
			.Text(IronUI::ToText(Setup.Location))
			.Font(IronStyle::Heading(18.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		];
	}
	Body->AddSlot()
	.AutoHeight()
	.HAlign(HAlign_Center)
	.Padding(FMargin(0.0f, 2.0f, 0.0f, 10.0f))
	[
		SNew(STextBlock)
		.Text(KindText)
		.Font(IronStyle::Body(14.0f))
		.ColorAndOpacity(IronStyle::InkSoft())
	];
	Body->AddSlot()
	.AutoHeight()
	[
		SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		[
			BuildSide(Setup.Sides[0], true)
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		.Padding(FMargin(16.0f, 0.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.strategy.versus", "VS"))
			.Font(IronStyle::Brush(44.0f))
			.ColorAndOpacity(IronStyle::Lacquer())
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		[
			BuildSide(Setup.Sides[1], false)
		]
	];
	Body->AddSlot()
	.AutoHeight()
	.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
	[
		IronStrategy::MakeWrappedText(RoleText, 15.0f, IronStyle::Ink())
	];

	TWeakPtr<SIronBattlePrompt> WeakSelf = SharedThis(this);
	const TSharedRef<SWidget> Buttons = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(6.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.command", "Command"), FOnClicked::CreateLambda([WeakSelf]()
			{
				TSharedPtr<SIronBattlePrompt> Self = WeakSelf.Pin();
				if (Self.IsValid() && !Self->bAnswered && Self->OnCommand)
				{
					Self->bAnswered = true;
					Self->OnCommand();
				}
				return FReply::Handled();
			}), true, TEXT("Attack"), 220.0f)
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.Padding(FMargin(6.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.delegate", "Delegate"), FOnClicked::CreateLambda([WeakSelf]()
			{
				TSharedPtr<SIronBattlePrompt> Self = WeakSelf.Pin();
				if (Self.IsValid() && !Self->bAnswered && Self->OnDelegate)
				{
					Self->bAnswered = true;
					Self->OnDelegate();
				}
				return FReply::Handled();
			}), true, TEXT("Delegate"), 220.0f)
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(Heading, Body, Buttons, 900.0f, 0.0f)
	];
}

// -------------------------------------------------------------------------------------------------
// Game over
// -------------------------------------------------------------------------------------------------

void SIronGameOverDialog::Construct(const FArguments& InArgs)
{
	OnReturn = InArgs._OnReturn;
	TSharedPtr<FIronSession> SessionRef = InArgs._Session;

	bool bVictory = false;
	FString Portrait = TEXT("unknown");
	FText FactionText = FText::GetEmpty();
	FText DateText = FText::GetEmpty();
	if (SessionRef.IsValid() && SessionRef->HasGame())
	{
		const IronSim::FGameState& GameState = SessionRef->State();
		bVictory = GameState.Outcome == IronSim::EOutcome::Victory;
		FactionText = IronStrategy::FactionName(GameState, GameState.PlayerFaction);
		DateText = IronUI::ToText(SessionRef->Game().DateText());
		if (const IronSim::FFaction* Player = IronStrategy::GetFaction(GameState, GameState.PlayerFaction))
		{
			Portrait = IronStrategy::OfficerPortrait(GameState, Player->Ruler);
		}
	}

	const FText Title = bVictory ? IronUI::Loc("ui.strategy.victoryTitle", "The Realm Is United") : IronUI::Loc("ui.strategy.defeatTitle", "The Banner Falls");
	const FText Message = bVictory
		? IronUI::LocF("ui.strategy.victoryText", "Every rival has fallen. The {faction} rules the Nine Provinces under a new Mandate. ({date})", {{"faction", IronUI::ToStd(FactionText.ToString())}, {"date", IronUI::ToStd(DateText.ToString())}})
		: IronUI::LocF("ui.strategy.defeatText", "The {faction} has been destroyed. Others will write the history of this age. ({date})", {{"faction", IronUI::ToStd(FactionText.ToString())}, {"date", IronUI::ToStd(DateText.ToString())}});

	const TSharedRef<SWidget> Body = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.Padding(FMargin(0.0f, 0.0f, 18.0f, 0.0f))
		[
			IronStyle::MakePortrait(Portrait, 200.0f)
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			IronStrategy::MakeWrappedText(Message, 18.0f, bVictory ? IronStyle::Ink() : IronStyle::LacquerDark())
		];

	TWeakPtr<SIronGameOverDialog> WeakSelf = SharedThis(this);
	const TSharedRef<SWidget> Buttons = SNew(SBox)
		.HAlign(HAlign_Center)
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.returnToTitle", "Return to Title"), FOnClicked::CreateLambda([WeakSelf]()
			{
				TSharedPtr<SIronGameOverDialog> Self = WeakSelf.Pin();
				if (Self.IsValid() && Self->OnReturn)
				{
					const FIronSimpleCallback Callback = Self->OnReturn;
					Callback();
				}
				return FReply::Handled();
			}), true, FString(), 260.0f)
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(Title, Body, Buttons, 820.0f, 0.0f)
	];
}
