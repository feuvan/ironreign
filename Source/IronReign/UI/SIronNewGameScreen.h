#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Sim/IronTypes.h"
#include "UI/IronSession.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class SBox;
class SIronRoot;
class SScrollBox;

/**
 * New campaign setup: scenario list (left), faction cards with ruler portrait, banner, cities, officers and troops
 * (right), difficulty selector and Start / Back (bottom).
 */
class SIronNewGameScreen : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronNewGameScreen) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	const FIronScenarioEntry* SelectedEntry() const;
	void RebuildScenarioList();
	void RebuildFactionGrid();
	void RebuildDifficulty();
	TSharedRef<SWidget> MakeFactionCard(int32 FactionIndex);
	TSharedRef<SWidget> MakeDifficultyRow();
	FText DescriptionText() const;
	FText DifficultyHint() const;
	bool CanStart() const;

	FReply OnScenarioClicked(int32 ScenarioIndex);
	FReply OnFactionClicked(int32 FactionIndex);
	FReply OnDifficultyClicked(IronSim::EDifficulty Level);
	FReply OnStart();
	FReply OnBack();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	TArray<FIronScenarioEntry> Scenarios;
	int32 SelectedScenario = INDEX_NONE;
	int32 SelectedFaction = INDEX_NONE;
	IronSim::EDifficulty Difficulty = IronSim::EDifficulty::Normal;

	TSharedPtr<SScrollBox> ScenarioList;
	TSharedPtr<SBox> FactionHost;
	TSharedPtr<SBox> DifficultyHost;
};
