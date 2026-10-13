#pragma once

#include "CoreMinimal.h"
#include "Sim/IronGame.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;

/**
 * Dialog for one monthly officer order (Farm, Commerce, Walls, Patrol, Train, Draft, Search, Recruit, Move,
 * Transport, Sect Training, Alliance, Truce, Gift).
 * Left: idle officers of the city with portrait and the five stats (the governing stat highlighted) and, for each,
 * the FGame::CheckOrder preview, cost and success chance. Right: the target picker and amount editors the order needs.
 * "Issue Order" calls FGame::IssueOrder and closes the modal, or shows the error.
 */
class IRONREIGN_API SIronOrderDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronOrderDialog)
		: _City(-1)
		, _OrderType(IronSim::EOrderType::Farm)
		, _PresetTarget(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
		SLATE_ARGUMENT(IronSim::EOrderType, OrderType)
		/** Optional preselected target (officer, city, faction or sect index depending on the order). */
		SLATE_ARGUMENT(int32, PresetTarget)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	enum class ETargetKind : uint8
	{
		None,
		City,
		Officer,
		Faction,
		Sect
	};

	ETargetKind GetTargetKind() const;
	bool HasAmounts() const;
	IronSim::FOrder MakeOrder(int32 Officer) const;
	IronSim::FOrderCheck CheckFor(int32 Officer) const;
	int32 CityGold() const;
	int32 CityFood() const;
	int32 CityTroops() const;

	TSharedRef<SWidget> BuildOfficerList();
	TSharedRef<SWidget> BuildOfficerRow(int32 Officer);
	TSharedRef<SWidget> BuildTargetList();
	TSharedRef<SWidget> BuildTargetRow(int32 Target);
	TSharedRef<SWidget> BuildAmounts();
	FText TargetTitle(int32 Target) const;
	FText TargetDetail(int32 Target) const;
	FText SummaryText() const;
	FSlateColor SummaryColor() const;

	FReply HandleIssue();
	FReply HandleCancel();
	void CloseDialog();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
	IronSim::EOrderType OrderKind = IronSim::EOrderType::Farm;
	int32 Governing = -1;

	TArray<int32> Officers;
	TArray<int32> Targets;
	int32 SelectedOfficer = -1;
	int32 SelectedTarget = -1;

	int32 AmountValue = 0;
	int32 GoldValue = 0;
	int32 FoodValue = 0;
	int32 TroopsValue = 0;
	FText ErrorText;
};
