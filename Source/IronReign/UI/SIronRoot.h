#pragma once

#include "CoreMinimal.h"
#include "Sim/IronBattle.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SBorder;
class SOverlay;

DECLARE_DELEGATE_OneParam(FOnIronBattleFinished, const IronSim::FBattleResult& /*Result*/);

/**
 * Top-level widget added to the game viewport. Switches between screens (title, new game, strategy, battle)
 * and hosts a modal stack drawn over a dimmed background.
 *
 * Screen widgets receive the session and a weak pointer back to the root:
 *   SNew(SIronStrategyScreen).Session(Session).Root(WeakRoot)
 *   SNew(SIronBattleScreen).Session(Session).Root(WeakRoot).Setup(Setup).OnFinished(Delegate)
 */
class IRONREIGN_API SIronRoot : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronRoot) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	TSharedPtr<FIronSession> GetSession() const { return Session; }

	void ShowTitle();
	void ShowNewGame();
	/** Shows the campaign map, creating the strategy screen on first use (recreated after new game/load). */
	void ShowStrategy();
	/** Drops the cached strategy screen (after starting or loading a game). */
	void ResetStrategy();
	/** Opens the tactical battle screen. OnFinished fires once with the result; the caller decides what to show next. */
	void ShowBattle(const IronSim::FBattleSetup& Setup, FOnIronBattleFinished OnFinished);

	/** Pushes a modal widget centred over a dim layer; input below is blocked. */
	void PushModal(const TSharedRef<SWidget>& Widget);
	void PopModal();
	bool HasModal() const;

	/** Convenience modals. */
	void ShowMessage(const FText& Title, const FText& Message, TFunction<void()> OnClose = nullptr);
	void ShowConfirm(const FText& Title, const FText& Message, TFunction<void(bool)> OnResult);
	/** Save (bSave) or load dialog with FIronSession::SaveSlotCount slots. */
	void ShowSaveLoad(bool bSave);
	/** Language and speed options. */
	void ShowSettings();

	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;

private:
	void SetScreen(const TSharedRef<SWidget>& Screen);

	TSharedPtr<FIronSession> Session;
	TSharedPtr<SBorder> ScreenHost;
	TSharedPtr<SOverlay> ModalLayer;
	TArray<TSharedRef<SWidget>> ModalStack;
	TSharedPtr<SWidget> StrategyScreen;
};
