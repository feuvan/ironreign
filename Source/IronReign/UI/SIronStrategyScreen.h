#pragma once

#include "CoreMinimal.h"
#include "Sim/IronBattle.h"
#include "UObject/WeakObjectPtr.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

#include <string>

class AIronWorldMap3D;
class FIronSession;
class SIronRoot;
class SIronMapView;
class SIronCityPanel;
class SIronCommandPanel;
class SVerticalBox;

/** Where the strategy screen is in the monthly loop. */
enum class EIronStrategyFlow : uint8
{
	/** Month planning: orders, events and prisoner decisions. */
	Planning,
	/** Days are ticking (FGame::Step on an active timer). */
	Running,
	/** A player battle is waiting for Command / Delegate. */
	BattlePrompt,
	/** The tactical battle screen is open. */
	InBattle,
	/** Showing the result of a delegated battle. */
	BattleReport,
	/** Victory or defeat. */
	GameOver
};

/**
 * The campaign map screen (DESIGN.md section 9): top bar (date, phase, player banner, treasury, menu buttons,
 * End Turn / speed controls), city panel (left), painted map (centre), command panel (right) and the chronicle
 * (bottom). Drives the turn flow: End Turn -> FGame::EndPlanning -> FGame::Step at the session's days-per-second,
 * player battles (Command opens the tactical screen through SIronRoot::ShowBattle, Delegate auto-resolves), month end
 * (autosave, events, prisoners) and game over.
 *
 * Real-time 3D map (DESIGN.md section 12): when the session presents the map in 3D (FIronSession::Uses3DMap) and the
 * AIronWorldMap3D spawned by AIronReignPlayerController has its scene ready, the screen activates it and the map view
 * becomes a transparent overlay over the centre: the screen's backdrop turns transparent there (the panels keep their
 * own backdrops, so the 3D scene only shows through the map area), and every frame the screen feeds the map the day
 * fraction, the month's season and the march targets (the map view pushes hover and selection). Until the scene is
 * ready, without assets or in 2D mode the painted 2D map is shown exactly as before. Opening a player battle hides the
 * map (the battle screen shows its own scene or the 2D board); coming back re-activates it.
 */
class IRONREIGN_API SIronStrategyScreen : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronStrategyScreen) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
	SLATE_END_ARGS()

	virtual ~SIronStrategyScreen() override;

	void Construct(const FArguments& InArgs);

	/** Selects a city in the side panels (does not move the map). */
	void SelectCity(int32 InCity);
	int32 GetSelectedCity() const { return SelectedCity; }

	// SWidget interface
	virtual bool SupportsKeyboardFocus() const override { return true; }
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual FReply OnPreviewKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;

private:
	/** Snapshot of the chronicle used to find the entries a delegated battle added. */
	struct FLogMark
	{
		int32 Size = 0;
		std::string LastText;
	};

	// Layout
	void BuildLayout();
	TSharedRef<SWidget> BuildTopBar();
	TSharedRef<SWidget> BuildPlanningControls();
	TSharedRef<SWidget> BuildExecutionControls();
	TSharedRef<SWidget> BuildSpeedButton(int32 Index, const FText& Label);
	TSharedRef<SWidget> BuildLogPanel();
	void RebuildLog();
	uint32 ComputeLogSignature() const;

	// Session events
	void HandleStateChanged();
	void HandleCultureChanged();
	void HandleCityClicked(int32 InCity);
	void HandleArmyClicked(int32 ArmyId);
	EActiveTimerReturnType HandleTick(double InCurrentTime, float InDeltaTime);

	// Real-time 3D map
	/** Activates the 3D map once its scene is ready, hands it to the map view and feeds it the game state. */
	void UpdateWorldMap();
	/** The world's AIronWorldMap3D when the session presents the map in 3D (it may still be loading), else nullptr. */
	AIronWorldMap3D* FindWorldMap();
	/** Hides the 3D map (before the battle screen opens); the next frame on this screen shows it again. */
	void HideWorldMap();

	// Turn flow
	void SyncFlowWithGame();
	void WatchFlow();
	void EnsureFocus();
	void AdvanceExecution(float DeltaSeconds);
	void StepDay();
	void OnMonthEnded();
	void PumpPlanningModals();
	int32 NextPendingPrisoner() const;
	void ShowEventModal();
	void HandleEventChoice(int32 ChoiceIndex);
	void ShowPrisonerModal(int32 Prisoner);
	void HandlePrisonerDecided(int32 Prisoner, const FText& Message);
	void ShowBattlePrompt();
	void StartPlayerBattle();
	void DelegatePlayerBattle();
	void HandleBattleFinished(const IronSim::FBattleResult& Result);
	void ShowGameOver();
	FLogMark MarkLog() const;
	FText CollectNewLog(const FLogMark& Mark, int32 MaxLines) const;
	bool IsRootModalOpen() const;

	// Top bar buttons
	FReply HandleEndTurn();
	FReply HandleSpeed(int32 NewSpeedIndex);
	FReply HandleOfficers();
	FReply HandleFactions();
	FReply HandleSave();
	FReply HandleLoad();
	FReply HandleSettings();
	bool HandleSpaceKey();
	bool CanEndTurn() const;
	bool CanUseMenus() const;
	float GetFractionalDay() const;
	float SpeedMultiplier() const;

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	TSharedPtr<SIronMapView> MapView;
	TSharedPtr<SIronCityPanel> CityPanel;
	TSharedPtr<SIronCommandPanel> CommandPanel;
	TSharedPtr<SVerticalBox> LogBox;
	TSharedPtr<FActiveTimerHandle> TickHandle;
	FDelegateHandle StateChangedHandle;
	FDelegateHandle CultureChangedHandle;

	/** The 3D campaign map (spawned and destroyed by AIronReignPlayerController). */
	TWeakObjectPtr<AIronWorldMap3D> WorldMap;
	/** The 3D map is active and the map view is its overlay (the backdrop behind the map area is transparent). */
	bool bWorldMapShown = false;
	/** Month whose season the 3D map shows, and the march target cities last sent to it. */
	int32 WorldMapMonth = 0;
	TArray<int32> WorldMapTargets;

	int32 SelectedCity = -1;
	/** FArmy::Id selected on the 3D map (-1 for none). */
	int32 SelectedArmyId = -1;
	EIronStrategyFlow Flow = EIronStrategyFlow::Planning;
	/** 0 = paused, 1 = 1x, 2 = 2x, 3 = 4x. */
	int32 SpeedIndex = 1;
	int32 ResumeSpeedIndex = 1;
	/** Progress toward the next day (0..1), also used to interpolate marching armies. */
	float DayFraction = 0.0f;
	float WatchSeconds = 0.0f;
	float InBattleSeconds = 0.0f;
	uint32 LastLogSignature = 0;
	/** Prisoners already decided this month (guards against re-prompting if the rules keep them pending). */
	TSet<int32> HandledPrisoners;
	int32 HandledPrisonersMonth = -1;
};
