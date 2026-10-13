#pragma once

#include "CoreMinimal.h"
#include "Framework/SlateDelegates.h"
#include "Sim/IronGame.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;

/**
 * Right panel of the strategy screen. For a player city during planning: tabs Domestic / Military / Personnel /
 * Diplomacy / Town whose buttons open the order dialogs, the Delegate toggle and the list of this month's orders
 * (cancel with refund). During execution it lists the player's armies; for foreign cities it shows relations.
 */
class IRONREIGN_API SIronCommandPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronCommandPanel)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void SetCity(int32 InCity);
	/** Rebuilds when orders, armies, phase or ownership changed. */
	void Refresh();

private:
	enum class ETab : uint8
	{
		Domestic,
		Military,
		Personnel,
		Diplomacy,
		Town
	};

	uint32 ComputeSignature() const;
	void Rebuild();
	bool CanCommand() const;
	bool HasIdleOfficers() const;

	TSharedRef<SWidget> BuildPlanningContent();
	TSharedRef<SWidget> BuildExecutionContent();
	TSharedRef<SWidget> BuildForeignContent();
	TSharedRef<SWidget> BuildTabBar();
	TSharedRef<SWidget> BuildPage();
	TSharedRef<SWidget> BuildDomesticPage();
	TSharedRef<SWidget> BuildMilitaryPage();
	TSharedRef<SWidget> BuildPersonnelPage();
	TSharedRef<SWidget> BuildDiplomacyPage();
	TSharedRef<SWidget> BuildTownPage();
	TSharedRef<SWidget> BuildOrdersList();
	TSharedRef<SWidget> BuildArmyLine(int32 ArmyId, bool bAllowDisband);
	TSharedRef<SWidget> MakeOrderButton(IronSim::EOrderType Type);
	TSharedRef<SWidget> MakeActionButton(const FText& Label, const FString& Icon, FOnClicked OnClicked, const TAttribute<bool>& EnabledAttr);

	FReply HandleTab(ETab NewTab);
	FReply HandleOrder(IronSim::EOrderType Type);
	FReply HandleMarch();
	FReply HandleReward();
	FReply HandlePrisoners();
	FReply HandleMarket();
	FReply HandleTavern();
	FReply HandleSect();
	FReply HandleDelegate();
	FReply HandleCancelOrder(int32 Officer);
	FReply HandleDisband(int32 ArmyId);
	void OpenPrisonerDecision(int32 Prisoner);

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
	ETab ActiveTab = ETab::Domestic;
	uint32 Signature = 0;
};
