#pragma once

#include "CoreMinimal.h"
#include "UI/SIronStrategyDialogs.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;
class SVerticalBox;

/**
 * Modal "Officers" screen: sortable table of every officer serving the player (name, age, the five stats, loyalty,
 * location, current order, techniques). Click a column header to sort; click a row to show the officer's city.
 */
class IRONREIGN_API SIronOfficerTable : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronOfficerTable) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		/** Called with the city of a clicked officer (after the table closes). */
		SLATE_ARGUMENT(FIronIndexCallback, OnShowCity)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	enum class EColumn : uint8
	{
		Name,
		Age,
		Martial,
		Command,
		Strategy,
		Politics,
		Charm,
		Loyalty,
		Location,
		Activity,
		Techniques
	};

	static constexpr int32 ColumnCount = 11;

	float ColumnWidth(EColumn Column) const;
	FText ColumnLabel(EColumn Column) const;
	int32 CompareOfficers(int32 Left, int32 Right) const;
	void SortRows();
	void RebuildHeader();
	void RebuildRows();
	TSharedRef<SWidget> BuildRow(int32 Officer, int32 RowIndex);
	FReply HandleSort(EColumn Column);
	FReply HandleRowClicked(int32 Officer);
	FReply HandleClose();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	FIronIndexCallback OnShowCity;
	TArray<int32> Rows;
	EColumn SortColumn = EColumn::Name;
	bool bAscending = true;
	TSharedPtr<SVerticalBox> HeaderBox;
	TSharedPtr<SVerticalBox> RowBox;
};
