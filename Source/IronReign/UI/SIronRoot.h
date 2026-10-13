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
		/** Called by RequestQuit (the player controller quits through UKismetSystemLibrary so PIE ends cleanly). */
		SLATE_EVENT(FSimpleDelegate, OnQuitRequested)
	SLATE_END_ARGS()

	/** Which screen the root is showing. */
	enum class EScreen : uint8
	{
		None,
		Title,
		NewGame,
		Strategy,
		Battle
	};

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

	// ----- Additions (UE framework engineer) -----
	/**
	 * Like PushModal, but Escape calls OnEscape instead of simply popping the modal. OnEscape is responsible for
	 * popping (e.g. it answers "Cancel"). Pass nullptr to make the modal ignore Escape (decisions that must be made).
	 */
	void PushModalWithEscape(const TSharedRef<SWidget>& Widget, TFunction<void()> OnEscape);
	/** Removes every modal. */
	void ClearModals();
	/** In-game system menu (Escape on the strategy screen): resume, save, load, settings, title, quit. */
	void ShowGameMenu();
	/** Quits the game (through OnQuitRequested when bound). */
	void RequestQuit();
	EScreen GetCurrentScreen() const { return CurrentScreen; }

private:
	void SetScreen(const TSharedRef<SWidget>& Screen);

	// ----- Additions (UE framework engineer) -----
	struct FModalInfo
	{
		/** Escape pops the modal when no handler is set. */
		bool bPopOnEscape = true;
		TFunction<void()> OnEscape;
	};

	void PushModalInternal(const TSharedRef<SWidget>& Widget, bool bPopOnEscape, TFunction<void()> OnEscape);
	void HandleCultureChanged();
	void FocusRoot();
	TSharedRef<SWidget> MakeTitleScreen();
	TSharedRef<SWidget> MakeNewGameScreen();

	TSharedPtr<FIronSession> Session;
	TSharedPtr<SBorder> ScreenHost;
	TSharedPtr<SOverlay> ModalLayer;
	TArray<TSharedRef<SWidget>> ModalStack;
	TSharedPtr<SWidget> StrategyScreen;

	/** Parallel to ModalStack. */
	TArray<FModalInfo> ModalInfos;
	FSimpleDelegate QuitRequested;
	EScreen CurrentScreen = EScreen::None;
};
