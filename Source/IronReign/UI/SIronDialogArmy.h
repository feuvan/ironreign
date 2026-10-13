#pragma once

#include "CoreMinimal.h"
#include "Sim/IronGame.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;

/**
 * March dialog: choose a commander and up to four deputies among the city's idle officers, the troops
 * (bounded by FGame::MaxUnitTroops of each officer and the garrison), food (shown in days of supply via
 * FGame::ArmyDailyFood) and a target from FGame::MarchTargets with its march time. FGame::CheckArmy previews
 * the plan; "March" calls FGame::FormArmy.
 */
class IRONREIGN_API SIronArmyDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronArmyDialog)
		: _City(-1)
		, _PresetTarget(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
		SLATE_ARGUMENT(int32, PresetTarget)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	IronSim::FArmyPlan MakePlan() const;
	IronSim::FOrderCheck CheckPlan() const;
	int32 TroopCapacity() const;
	int32 CityTroops() const;
	int32 CityFood() const;
	int32 DailyFood() const;
	void ToggleOfficer(int32 Officer);
	void MakeCommander(int32 Officer);
	void SuggestTroops();
	void SuggestFood();
	void SelectTarget(int32 Target);

	TSharedRef<SWidget> BuildOfficerRow(int32 Officer);
	TSharedRef<SWidget> BuildTargetRow(int32 Target);
	FText SummaryText() const;

	FReply HandleMarch();
	FReply HandleCancel();
	void CloseDialog();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
	TArray<int32> Candidates;
	/** Chosen officers in order; [0] commands. */
	TArray<int32> Chosen;
	TArray<int32> Targets;
	int32 SelectedTarget = -1;
	int32 TroopsValue = 0;
	int32 FoodValue = 0;
	FText ErrorText;
};
