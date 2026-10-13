#include "UI/SIronDuelDialog.h"

#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronHexView.h"

#include "HAL/PlatformTime.h"
#include "Styling/SlateColor.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

namespace IronDuelDialogDetail
{
	constexpr double FlashSeconds = 0.9;
	constexpr double AutoRoundSeconds = 0.9;
	const TCHAR* const BackgroundPath = TEXT("Art/Duel/Background.png");
}

void SIronDuelDialog::Construct(const FArguments& InArgs)
{
	Battle = InArgs._Battle;
	Session = InArgs._Session;
	PlayerSide = (InArgs._PlayerSide == 0 || InArgs._PlayerSide == 1) ? InArgs._PlayerSide : -1;
	OnClosedDelegate = InArgs._OnClosed;
	NextAutoRound = FPlatformTime::Seconds() + 1.0;

	FIronAssets& Assets = FIronAssets::Get();
	const FSlateBrush* BackgroundBrush = Assets.Exists(IronDuelDialogDetail::BackgroundPath) ? Assets.Image(IronDuelDialogDetail::BackgroundPath) : IronStyle::PanelDark();
	const FLinearColor Light = IronStyle::TextLight();

	const auto MakeMoveButton = [this](IronSim::EDuelMove Move, const FString& IconName) -> TSharedRef<SWidget>
	{
		return SNew(SBox)
			.Padding(FMargin(4.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::ToText(IronSim::DisplayName(Move)), FOnClicked::CreateSP(this, &SIronDuelDialog::OnMoveClicked, Move, -1), TAttribute<bool>::CreateSP(this, &SIronDuelDialog::CanPlay), IconName, 150.0f)
			];
	};

	ChildSlot
	[
		SNew(SBox)
		.WidthOverride(1120.0f)
		.HeightOverride(680.0f)
		[
			SNew(SOverlay)
			+ SOverlay::Slot()
			[
				SNew(SImage)
				.Image(BackgroundBrush)
			]
			+ SOverlay::Slot()
			[
				SNew(SBorder)
				.BorderImage(IronStyle::WhiteBrush())
				.BorderBackgroundColor(FLinearColor(0.0f, 0.0f, 0.0f, 0.3f))
			]
			+ SOverlay::Slot()
			.Padding(FMargin(28.0f, 20.0f))
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					IronStyle::MakeHeader(IronUI::Loc("ui.battle.duel.title", "Single Combat"), 30.0f, true)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 2.0f, 0.0f, 10.0f))
				[
					SNew(STextBlock)
					.Text(TAttribute<FText>::CreateSP(this, &SIronDuelDialog::GetRoundText))
					.Font(IronStyle::Heading(20.0f))
					.ColorAndOpacity(IronStyle::Gold())
				]
				+ SVerticalBox::Slot()
				.FillHeight(1.0f)
				[
					SNew(SHorizontalBox)
					+ SHorizontalBox::Slot()
					.AutoWidth()
					[
						MakeDuelistColumn(0)
					]
					+ SHorizontalBox::Slot()
					.FillWidth(1.0f)
					.Padding(FMargin(16.0f, 0.0f))
					[
						IronStyle::MakePanel(
							SNew(SVerticalBox)
							+ SVerticalBox::Slot()
							.AutoHeight()
							.HAlign(HAlign_Center)
							[
								SNew(STextBlock)
								.Text(IronUI::Loc("ui.battle.duel.versus", "VS"))
								.Font(IronStyle::Heading(40.0f))
								.ColorAndOpacity(IronStyle::Gold())
							]
							+ SVerticalBox::Slot()
							.AutoHeight()
							.Padding(FMargin(0.0f, 6.0f))
							[
								SNew(STextBlock)
								.Text(TAttribute<FText>::CreateSP(this, &SIronDuelDialog::GetLastMovesText))
								.Font(IronStyle::BodyBold(16.0f))
								.ColorAndOpacity(IronStyle::Gold())
								.Justification(ETextJustify::Center)
								.AutoWrapText(true)
							]
							+ SVerticalBox::Slot()
							.AutoHeight()
							.Padding(FMargin(0.0f, 2.0f, 0.0f, 8.0f))
							[
								SNew(STextBlock)
								.Text(TAttribute<FText>::CreateSP(this, &SIronDuelDialog::GetLastRoundText))
								.Font(IronStyle::Body(16.0f))
								.ColorAndOpacity(Light)
								.Justification(ETextJustify::Center)
								.AutoWrapText(true)
							]
							+ SVerticalBox::Slot()
							.AutoHeight()
							[
								SNew(SBox)
								.HeightOverride(12.0f)
								[
									SNew(SImage)
									.Image(IronStyle::Divider())
								]
							]
							+ SVerticalBox::Slot()
							.FillHeight(1.0f)
							.Padding(FMargin(0.0f, 6.0f, 0.0f, 0.0f))
							[
								SAssignNew(HistoryBox, SScrollBox)
							],
							true, FMargin(18.0f))
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					[
						MakeDuelistColumn(1)
					]
				]
				// Player controls.
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
				[
					SNew(SVerticalBox)
					.Visibility(TAttribute<EVisibility>::CreateSP(this, &SIronDuelDialog::GetControlsVisibility))
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					.Padding(FMargin(0.0f, 0.0f, 0.0f, 8.0f))
					[
						SNew(STextBlock)
						.Text(IronUI::Loc("ui.battle.duel.hint", "Strike beats Feint, Feint beats Guard, Guard beats Strike. A technique empowers its move and wins ties."))
						.Font(IronStyle::Body(15.0f))
						.ColorAndOpacity(Light)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					[
						SNew(SHorizontalBox)
						+ SHorizontalBox::Slot()
						.AutoWidth()
						[
							MakeMoveButton(IronSim::EDuelMove::Strike, TEXT("Attack"))
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						[
							MakeMoveButton(IronSim::EDuelMove::Guard, TEXT("Defense"))
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						[
							MakeMoveButton(IronSim::EDuelMove::Feint, TEXT("Confuse"))
						]
						+ SHorizontalBox::Slot()
						.AutoWidth()
						.Padding(FMargin(12.0f, 0.0f, 0.0f, 0.0f))
						[
							SAssignNew(TechniqueRow, SHorizontalBox)
						]
					]
				]
				// Outcome.
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
				[
					SNew(SHorizontalBox)
					.Visibility(TAttribute<EVisibility>::CreateSP(this, &SIronDuelDialog::GetOutcomeVisibility))
					+ SHorizontalBox::Slot()
					.FillWidth(1.0f)
					.VAlign(VAlign_Center)
					.HAlign(HAlign_Center)
					[
						SNew(STextBlock)
						.Text(TAttribute<FText>::CreateSP(this, &SIronDuelDialog::GetOutcomeText))
						.Font(IronStyle::Heading(26.0f))
						.ColorAndOpacity(IronStyle::Gold())
					]
					+ SHorizontalBox::Slot()
					.AutoWidth()
					.VAlign(VAlign_Center)
					[
						IronStyle::MakeButton(IronUI::Loc("ui.battle.duel.close", "Close"), FOnClicked::CreateSP(this, &SIronDuelDialog::OnCloseClicked), true, FString(), 180.0f)
					]
				]
			]
		]
	];

	if (HasDuel() && GetDuel().Round() > 0)
	{
		const IronSim::FDuelRound& Latest = GetDuel().Rounds().back();
		LastMovesText = IronUI::ToText(RoundSummary(Latest));
		LastRoundText = IronUI::ToText(Latest.Text);
	}
	else
	{
		LastRoundText = IronUI::Loc("ui.battle.duel.start", "The two warriors face each other. Choose your move.");
	}
	RebuildTechniques();
	RebuildHistory();
	RegisterActiveTimer(0.0f, FWidgetActiveTimerDelegate::CreateSP(this, &SIronDuelDialog::OnDuelTick));
}

const IronSim::FDuel& SIronDuelDialog::GetDuel() const
{
	const IronSim::FBattle& ConstBattle = *Battle;
	return ConstBattle.ActiveDuel();
}

bool SIronDuelDialog::IsDuelOver() const
{
	return !HasDuel() || GetDuel().IsOver();
}

bool SIronDuelDialog::CanPlay() const
{
	return !bClosed && PlayerSide >= 0 && !IsDuelOver();
}

std::string SIronDuelDialog::DuelistName(int32 DuelSide) const
{
	if (!HasDuel())
	{
		return std::string();
	}
	const IronSim::FDuelist& Duelist = GetDuel().Side(DuelSide);
	return IronBattleUI::OfficerName(Session.Get(), Duelist.Officer, Duelist.Name);
}

std::string SIronDuelDialog::MoveLabel(IronSim::EDuelMove Move, int32 TechniqueIndex) const
{
	const std::string MoveName = IronSim::DisplayName(Move);
	if (TechniqueIndex >= 0 && HasDuel())
	{
		if (const IronSim::FTechnique* Info = GetDuel().TechniqueInfo(TechniqueIndex))
		{
			return IronSim::LocF("ui.battle.duel.moveWithTechnique", "{move} with {technique}", {{"move", MoveName}, {"technique", IronSim::NameOf(*Info)}});
		}
	}
	return MoveName;
}

std::string SIronDuelDialog::RoundSummary(const IronSim::FDuelRound& Round) const
{
	return IronSim::LocF("ui.battle.duel.moves", "{nameA}: {moveA}  -  {nameB}: {moveB}", {{"nameA", DuelistName(0)}, {"moveA", MoveLabel(Round.Moves[0], Round.Techniques[0])}, {"nameB", DuelistName(1)}, {"moveB", MoveLabel(Round.Moves[1], Round.Techniques[1])}});
}

TSharedRef<SWidget> SIronDuelDialog::MakeDuelistColumn(int32 DuelSide)
{
	FString PortraitId;
	FText NameText;
	int32 Martial = 0;
	if (HasDuel())
	{
		const IronSim::FDuelist& Duelist = GetDuel().Side(DuelSide);
		PortraitId = IronUI::ToFString(Duelist.Portrait);
		NameText = IronUI::ToText(DuelistName(DuelSide));
		Martial = Duelist.Martial;
	}
	const FText RoleText = DuelSide == PlayerSide ? IronUI::Loc("ui.battle.duel.you", "Your champion") : IronUI::Loc("ui.battle.duel.opponent", "Opponent");
	const FLinearColor Light = IronStyle::TextLight();

	return SNew(SBox)
		.WidthOverride(260.0f)
		[
			IronStyle::MakePanel(
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					SNew(SOverlay)
					+ SOverlay::Slot()
					[
						IronStyle::MakePortrait(PortraitId, 230.0f)
					]
					+ SOverlay::Slot()
					[
						SNew(SImage)
						.Image(IronStyle::WhiteBrush())
						.ColorAndOpacity(TAttribute<FSlateColor>::CreateLambda([this, DuelSide]()
						{
							return FSlateColor(FLinearColor(0.9f, 0.08f, 0.04f, 0.45f * GetFlashAlpha(DuelSide)));
						}))
					]
					+ SOverlay::Slot()
					.HAlign(HAlign_Center)
					.VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Text(TAttribute<FText>::CreateLambda([this, DuelSide]()
						{
							return FText::FromString(FString::Printf(TEXT("-%d"), FlashDamage[DuelSide == 0 ? 0 : 1]));
						}))
						.Font(IronStyle::Heading(46.0f))
						.ColorAndOpacity(TAttribute<FSlateColor>::CreateLambda([this, DuelSide]()
						{
							return FSlateColor(FLinearColor(1.0f, 0.85f, 0.6f, GetFlashAlpha(DuelSide)));
						}))
						.ShadowOffset(FVector2D(2.0, 2.0))
						.ShadowColorAndOpacity(TAttribute<FLinearColor>::CreateLambda([this, DuelSide]()
						{
							return FLinearColor(0.0f, 0.0f, 0.0f, 0.9f * GetFlashAlpha(DuelSide));
						}))
					]
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				.Padding(FMargin(0.0f, 8.0f, 0.0f, 0.0f))
				[
					SNew(STextBlock)
					.Text(NameText)
					.Font(IronStyle::Heading(22.0f))
					.ColorAndOpacity(Light)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					SNew(STextBlock)
					.Text(RoleText)
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(IronStyle::Gold())
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 10.0f, 0.0f, 2.0f))
				[
					IronStyle::MakeBar(TAttribute<float>::CreateLambda([this, DuelSide]() { return GetHpFraction(DuelSide); }), DuelSide == PlayerSide ? IronStyle::Jade() : IronStyle::Danger(), 12.0f)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					SNew(STextBlock)
					.Text(TAttribute<FText>::CreateLambda([this, DuelSide]() { return GetHpText(DuelSide); }))
					.Font(IronStyle::BodyBold(15.0f))
					.ColorAndOpacity(Light)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.HAlign(HAlign_Center)
				[
					SNew(STextBlock)
					.Text(IronUI::LocF("ui.battle.duel.martial", "Martial {value}", {{"value", IronSim::ToText(Martial)}}))
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(Light)
				],
				true, FMargin(14.0f))
		];
}

void SIronDuelDialog::RebuildTechniques()
{
	if (!TechniqueRow.IsValid())
	{
		return;
	}
	TechniqueRow->ClearChildren();
	if (PlayerSide < 0 || !HasDuel() || IsDuelOver())
	{
		return;
	}
	const IronSim::FDuel& Duel = GetDuel();
	const IronSim::FDuelist& Duelist = Duel.Side(PlayerSide);
	for (int32 SlotIndex = 0; SlotIndex < static_cast<int32>(Duelist.Techniques.size()); ++SlotIndex)
	{
		const bool bUsed = SlotIndex < static_cast<int32>(Duelist.TechniqueUsed.size()) && Duelist.TechniqueUsed[static_cast<size_t>(SlotIndex)];
		if (bUsed)
		{
			continue;
		}
		const IronSim::FTechnique* Info = Duel.TechniqueInfo(Duelist.Techniques[static_cast<size_t>(SlotIndex)]);
		if (Info == nullptr)
		{
			continue;
		}
		const FText Label = IronUI::LocF("ui.battle.techniqueLabel", "{technique} ({move})", {{"technique", IronSim::NameOf(*Info)}, {"move", IronSim::DisplayName(Info->Kind)}});
		const IronSim::EDuelMove TechniqueMove = Info->Kind;
		TechniqueRow->AddSlot()
		.AutoWidth()
		.Padding(FMargin(4.0f, 0.0f))
		[
			IronStyle::MakeButton(Label, FOnClicked::CreateSP(this, &SIronDuelDialog::OnMoveClicked, TechniqueMove, SlotIndex), TAttribute<bool>::CreateLambda([this, SlotIndex]()
			{
				return CanPlay() && GetDuel().CanUseTechnique(PlayerSide, SlotIndex);
			}), FString(), 0.0f)
		];
	}
}

void SIronDuelDialog::RebuildHistory()
{
	if (!HistoryBox.IsValid() || !HasDuel())
	{
		return;
	}
	HistoryBox->ClearChildren();
	const std::vector<IronSim::FDuelRound>& Played = GetDuel().Rounds();
	for (int32 RoundIndex = static_cast<int32>(Played.size()) - 1; RoundIndex >= 0; --RoundIndex)
	{
		const IronSim::FDuelRound& Entry = Played[static_cast<size_t>(RoundIndex)];
		const std::string Body = Entry.Text.empty() ? RoundSummary(Entry) : Entry.Text;
		HistoryBox->AddSlot()
		.Padding(FMargin(0.0f, 2.0f))
		[
			SNew(STextBlock)
			.Text(IronUI::LocF("ui.battle.duel.historyLine", "{round}. {text}", {{"round", IronSim::ToText(RoundIndex + 1)}, {"text", Body}}))
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(RoundIndex + 1 == static_cast<int32>(Played.size()) ? IronStyle::TextLight() : IronStyle::PaperDark())
			.AutoWrapText(true)
		];
	}
}

void SIronDuelDialog::AfterRound(const IronSim::FDuelRound& Round)
{
	// Blades clash, unless the player raised a guard.
	const bool bPlayerGuarded = PlayerSide >= 0 && Round.Moves[PlayerSide] == IronSim::EDuelMove::Guard;
	FIronAudio::Get().PlaySfx(bPlayerGuarded ? TEXT("Guard") : TEXT("Sword"));

	const double Now = FPlatformTime::Seconds();
	for (int32 DuelSide = 0; DuelSide < 2; ++DuelSide)
	{
		if (Round.Damage[DuelSide] > 0)
		{
			FlashStart[DuelSide] = Now;
			FlashDamage[DuelSide] = Round.Damage[DuelSide];
		}
	}
	LastMovesText = IronUI::ToText(RoundSummary(Round));
	LastRoundText = Round.Text.empty()
		? IronUI::LocF("ui.battle.duel.damage", "{nameA} loses {damageA} HP, {nameB} loses {damageB} HP.", {{"nameA", DuelistName(0)}, {"damageA", IronSim::ToText(Round.Damage[0])}, {"nameB", DuelistName(1)}, {"damageB", IronSim::ToText(Round.Damage[1])}})
		: IronUI::ToText(Round.Text);
	// Rebuilt on the next tick: the clicked technique button must not be destroyed inside its own click handler.
	bTechniquesDirty = true;
	RebuildHistory();
}

FReply SIronDuelDialog::OnMoveClicked(IronSim::EDuelMove Move, int32 TechniqueSlot)
{
	if (!CanPlay())
	{
		return FReply::Handled();
	}
	IronSim::FDuel& Duel = Battle->ActiveDuel();
	const int32 UsedSlot = (TechniqueSlot >= 0 && Duel.CanUseTechnique(PlayerSide, TechniqueSlot)) ? TechniqueSlot : -1;
	const IronSim::FDuelRound& Round = Duel.PlayVersusAI(PlayerSide, Move, UsedSlot);
	AfterRound(Round);
	return FReply::Handled();
}

FReply SIronDuelDialog::OnCloseClicked()
{
	if (bClosed || !IsDuelOver())
	{
		return FReply::Handled();
	}
	bClosed = true;
	// The owner pops this modal from the callback; stay alive until the handler returns.
	const TSharedRef<SIronDuelDialog> KeepAlive = SharedThis(this);
	OnClosedDelegate.ExecuteIfBound();
	return FReply::Handled();
}

EActiveTimerReturnType SIronDuelDialog::OnDuelTick(double /*InCurrentTime*/, float /*InDeltaTime*/)
{
	if (bClosed)
	{
		return EActiveTimerReturnType::Stop;
	}
	if (bTechniquesDirty)
	{
		bTechniquesDirty = false;
		RebuildTechniques();
	}
	const double Now = FPlatformTime::Seconds();
	if (PlayerSide < 0 && HasDuel() && !IsDuelOver() && Now >= NextAutoRound)
	{
		IronSim::FDuel& Duel = Battle->ActiveDuel();
		IronSim::EDuelMove MoveA = IronSim::EDuelMove::Strike;
		IronSim::EDuelMove MoveB = IronSim::EDuelMove::Strike;
		int32 SlotA = -1;
		int32 SlotB = -1;
		Duel.ChooseAI(0, MoveA, SlotA);
		Duel.ChooseAI(1, MoveB, SlotB);
		const IronSim::FDuelRound& Round = Duel.PlayRound(MoveA, SlotA, MoveB, SlotB);
		AfterRound(Round);
		NextAutoRound = Now + IronDuelDialogDetail::AutoRoundSeconds;
	}
	return EActiveTimerReturnType::Continue;
}

FText SIronDuelDialog::GetRoundText() const
{
	if (!HasDuel())
	{
		return FText::GetEmpty();
	}
	const IronSim::FDuel& Duel = GetDuel();
	const int32 Shown = Duel.IsOver() ? Duel.Round() : FMath::Min(Duel.Round() + 1, Duel.MaxRounds());
	return IronUI::LocF("ui.battle.duel.round", "Round {round}/{max}", {{"round", IronSim::ToText(Shown)}, {"max", IronSim::ToText(Duel.MaxRounds())}});
}

FText SIronDuelDialog::GetOutcomeText() const
{
	if (!HasDuel() || !GetDuel().IsOver())
	{
		return FText::GetEmpty();
	}
	const int32 Winner = GetDuel().Winner();
	if (Winner != 0 && Winner != 1)
	{
		return IronUI::Loc("ui.battle.duel.draw", "Neither warrior yields: the duel ends in a draw.");
	}
	return IronUI::LocF("ui.battle.duel.winner", "{name} wins the duel!", {{"name", DuelistName(Winner)}});
}

EVisibility SIronDuelDialog::GetControlsVisibility() const
{
	return (PlayerSide >= 0 && !IsDuelOver()) ? EVisibility::Visible : EVisibility::Collapsed;
}

EVisibility SIronDuelDialog::GetOutcomeVisibility() const
{
	return IsDuelOver() ? EVisibility::Visible : EVisibility::Collapsed;
}

FText SIronDuelDialog::GetHpText(int32 DuelSide) const
{
	if (!HasDuel())
	{
		return FText::GetEmpty();
	}
	const IronSim::FDuelist& Duelist = GetDuel().Side(DuelSide);
	return IronUI::LocF("ui.battle.duel.hp", "HP {hp} / {max}", {{"hp", IronSim::ToText(FMath::Max(0, Duelist.Hp))}, {"max", IronSim::ToText(Duelist.MaxHp)}});
}

float SIronDuelDialog::GetHpFraction(int32 DuelSide) const
{
	if (!HasDuel())
	{
		return 0.0f;
	}
	const IronSim::FDuelist& Duelist = GetDuel().Side(DuelSide);
	return Duelist.MaxHp > 0 ? FMath::Clamp(static_cast<float>(Duelist.Hp) / static_cast<float>(Duelist.MaxHp), 0.0f, 1.0f) : 0.0f;
}

float SIronDuelDialog::GetFlashAlpha(int32 DuelSide) const
{
	const double Age = FPlatformTime::Seconds() - FlashStart[DuelSide == 0 ? 0 : 1];
	if (Age < 0.0 || Age > IronDuelDialogDetail::FlashSeconds)
	{
		return 0.0f;
	}
	return static_cast<float>(1.0 - Age / IronDuelDialogDetail::FlashSeconds);
}
