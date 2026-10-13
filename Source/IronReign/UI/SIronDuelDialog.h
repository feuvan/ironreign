#pragma once

#include "CoreMinimal.h"
#include "Sim/IronBattle.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

#include <string>

class FIronSession;
class SHorizontalBox;
class SScrollBox;

/**
 * Wuxia duel minigame shown as a modal over the battle screen (SIronRoot::PushModalWithEscape: Escape cannot close it).
 * Plays FBattle::ActiveDuel() round by round: the player picks Strike / Guard / Feint or one of their unused techniques
 * (FDuel::PlayVersusAI). When no duelist belongs to the player the duel plays itself, one round at a time.
 * Once the duel is over a Close button fires OnClosed exactly once; the owner then calls FBattle::FinishDuel() and pops
 * the modal.
 */
class SIronDuelDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronDuelDialog)
		: _PlayerSide(-1)
		{}
		SLATE_ARGUMENT(TSharedPtr<IronSim::FBattle>, Battle)
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		/** Duel side (0 or 1) controlled by the player, or -1 to let the AI play both sides. */
		SLATE_ARGUMENT(int32, PlayerSide)
		SLATE_EVENT(FSimpleDelegate, OnClosed)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	const IronSim::FDuel& GetDuel() const;
	bool HasDuel() const { return Battle.IsValid(); }
	bool IsDuelOver() const;
	bool CanPlay() const;

	std::string DuelistName(int32 DuelSide) const;
	std::string MoveLabel(IronSim::EDuelMove Move, int32 TechniqueIndex) const;
	std::string RoundSummary(const IronSim::FDuelRound& Round) const;

	TSharedRef<SWidget> MakeDuelistColumn(int32 DuelSide);
	void RebuildTechniques();
	void RebuildHistory();
	void AfterRound(const IronSim::FDuelRound& Round);

	FReply OnMoveClicked(IronSim::EDuelMove Move, int32 TechniqueSlot);
	FReply OnCloseClicked();
	EActiveTimerReturnType OnDuelTick(double InCurrentTime, float InDeltaTime);

	FText GetRoundText() const;
	FText GetLastMovesText() const { return LastMovesText; }
	FText GetLastRoundText() const { return LastRoundText; }
	FText GetOutcomeText() const;
	EVisibility GetControlsVisibility() const;
	EVisibility GetOutcomeVisibility() const;
	FText GetHpText(int32 DuelSide) const;
	float GetHpFraction(int32 DuelSide) const;
	float GetFlashAlpha(int32 DuelSide) const;

	TSharedPtr<IronSim::FBattle> Battle;
	TSharedPtr<FIronSession> Session;
	int32 PlayerSide = -1;
	FSimpleDelegate OnClosedDelegate;
	bool bClosed = false;
	bool bTechniquesDirty = false;

	TSharedPtr<SHorizontalBox> TechniqueRow;
	TSharedPtr<SScrollBox> HistoryBox;
	FText LastMovesText;
	FText LastRoundText;
	double FlashStart[2] = {-100.0, -100.0};
	int32 FlashDamage[2] = {0, 0};
	double NextAutoRound = 0.0;
};
