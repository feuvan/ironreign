#pragma once

#include "CoreMinimal.h"
#include "Sim/IronBattle.h"
#include "UI/SIronRoot.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

#include <vector>

class FIronSession;
class SBox;
class SIronHexView;
class SScrollBox;
class SVerticalBox;

/** What a click on an enemy / ally does for the selected unit. */
enum class EIronBattleMode : uint8
{
	None,  // Click a blue hex to move, a red enemy to attack.
	Attack,
	Fire,
	Confuse,
	Rally,
	Duel
};

/** Buttons of the selected-unit panel. */
enum class EIronBattleAction : uint8
{
	Attack,
	Fire,
	Confuse,
	Rally,
	Duel,
	AttackGate,
	Wait,
	Undo
};

/**
 * Tactical battle screen (DESIGN.md sections 4 and 9). Owns the IronSim::FBattle built from Setup, shows the hex board,
 * the selected unit panel, the battle log and the turn controls, runs the AI turns with animation, handles duel
 * challenges and the duel minigame, and reports the result once through OnFinished.
 */
class SIronBattleScreen : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronBattleScreen) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(IronSim::FBattleSetup, Setup)
		SLATE_EVENT(FOnIronBattleFinished, OnFinished)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	virtual ~SIronBattleScreen() override;

	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;

private:
	// Layout.
	TSharedRef<SWidget> BuildLayout();
	TSharedRef<SWidget> BuildTopBar();
	TSharedRef<SWidget> BuildSideHeader(int32 Side);
	TSharedRef<SWidget> BuildUnitPanel();
	TSharedRef<SWidget> BuildActionButton(EIronBattleAction Action, const FText& Label, const FString& IconName);
	TSharedRef<SWidget> BuildBottomBar();
	TSharedRef<SWidget> MakeModalFrame(const TSharedRef<SWidget>& Content, float Width) const;
	void OnCultureChanged();

	// Turn flow.
	EActiveTimerReturnType OnDriverTick(double InCurrentTime, float InDeltaTime);
	float StepSeconds() const;
	void ConsumeEvents(bool bAnimate);
	void HandleStall();
	void AnnouncePlayerTurn();
	bool IsHumanTurn() const;

	// Refresh.
	void RefreshAll();
	void RefreshActionCache();
	void RefreshHighlights();
	void RefreshLog(bool bForce);
	void RefreshTechniques(bool bForce);

	// Modals.
	bool IsAnyModalOpen() const;
	void PushScreenModal(const TSharedRef<SWidget>& Widget);
	void PopScreenModal();
	void ShowChallenge();
	FReply OnChallengeAccept();
	FReply OnChallengeDecline();
	void AnswerChallenge(bool bAccept);
	void OpenDuel();
	void OnDuelClosed();
	void ShowResult();
	FReply OnResultContinue();
	void ShowDelegatePrompt();
	FReply OnDelegateWatch();
	FReply OnDelegateSkip();
	FReply OnDelegateCancel();

	// Input.
	void OnHexClicked(IronSim::FHex Hex);
	bool CancelAction();
	void SelectUnit(int32 UnitId);
	void AfterPlayerAction(bool bSucceeded);
	FReply OnActionClicked(EIronBattleAction Action);
	FReply OnEndTurnClicked();
	FReply OnDelegateClicked();

	// Queries.
	bool IsValidUnitId(int32 UnitId) const;
	const IronSim::FBattleUnit* GetPanelUnit() const;
	bool IsActionEnabled(EIronBattleAction Action) const;
	bool ReachableContains(IronSim::FHex Hex) const;
	int32 SideTroops(int32 Side, bool bStartTroops) const;
	std::string UnitNameOf(int32 UnitId) const;
	std::string SideNameOf(int32 Side) const;

	// Attribute getters.
	FText GetDayText() const;
	FText GetTurnText() const;
	FText GetSideTroopsText(int32 Side) const;
	float GetSideTroopsFraction(int32 Side) const;
	FText GetGateText() const;
	float GetGateFraction() const;
	EVisibility GetGateVisibility() const;
	FText GetUnitNameText() const;
	FText GetUnitSideText() const;
	FSlateColor GetUnitSideColor() const;
	FText GetUnitTypeText() const;
	FText GetUnitTroopsText() const;
	float GetUnitTroopsFraction() const;
	FText GetUnitMoraleText() const;
	float GetUnitMoraleFraction() const;
	FText GetUnitStatusText() const;
	FText GetStatValueText(int32 StatIndex) const;
	float GetStatFraction(int32 StatIndex) const;
	FString GetUnitPortrait() const;
	EVisibility GetUnitVisibility() const;
	EVisibility GetNoUnitVisibility() const;
	FText GetModeHintText() const;
	bool IsEndTurnEnabled() const;
	bool IsDelegateEnabled() const;
	FText GetDelegateLabel() const;
	EVisibility GetGateActionVisibility() const;
	EVisibility GetLocalModalVisibility() const;

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	FOnIronBattleFinished FinishedDelegate;
	TSharedPtr<IronSim::FBattle> Battle;
	/** Index of the side with FBattleSideSetup::bPlayer, or -1 when both sides are AI. */
	int32 PlayerSide = -1;

	TSharedPtr<SIronHexView> HexView;
	TSharedPtr<SScrollBox> LogBox;
	TSharedPtr<SVerticalBox> TechniqueBox;
	/** Fallback modal host used only when the root is gone. */
	TSharedPtr<SBox> LocalModalHost;
	TArray<TSharedRef<SWidget>> LocalModals;
	FDelegateHandle CultureChangedHandle;

	int32 SelectedUnit = -1;
	EIronBattleMode Mode = EIronBattleMode::None;

	// Cached queries for the selected unit (refreshed after every change).
	bool bCanCommand = false;
	bool bCanAttackGate = false;
	std::vector<IronSim::FReachableHex> CachedReachable;
	std::vector<int> CachedAttackTargets;
	std::vector<int> CachedTacticTargets[3];
	std::vector<int> CachedDuelTargets;

	int32 ShownLogCount = -1;
	int32 ShownTechniqueUnit = -2;
	int32 AnnouncedTurnKey = -1;
	int32 StallCount = 0;
	bool bDelegated = false;
	bool bFinishedFired = false;
	bool bFocusRequested = false;
	double NextStepTime = 0.0;
	double OverSince = -1.0;
};
