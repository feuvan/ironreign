#pragma once

#include "CoreMinimal.h"
#include "UI/SIronStrategyDialogs.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;

/** Market: buy or sell food at FGame::FoodBuyPrice / FoodSellPrice (gold per 100 food). Stays open for repeated trades. */
class IRONREIGN_API SIronMarketDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronMarketDialog)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	int32 BuyCost() const;
	int32 SellGain() const;
	int32 MaxTradable() const;
	FReply HandleTrade(bool bBuy);
	FReply HandleClose();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
	int32 AmountValue = 1000;
	FText ResultText;
	bool bResultError = false;
};

/** Tavern: wandering heroes in the city with their rumours, plus FGame::TavernRumor. "Recruit" opens the Recruit order. */
class IRONREIGN_API SIronTavernDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronTavernDialog)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TSharedRef<SWidget> BuildHeroRow(int32 Officer);
	FReply HandleRecruit(int32 Officer);
	FReply HandleClose();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
};

/** Martial sects reachable from the city: favor, master, techniques, donations and the Sect Training order. */
class IRONREIGN_API SIronSectDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronSectDialog)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TSharedRef<SWidget> BuildSectCard(int32 Sect);
	FReply HandleDonate(int32 Sect);
	FReply HandleTraining(int32 Sect);
	FReply HandleClose();
	int32 CityGold() const;

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
	int32 DonationValue = 200;
	FText ResultText;
	bool bResultError = false;
};

/** Reward an officer with gold to raise loyalty (immediate). */
class IRONREIGN_API SIronRewardDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronRewardDialog)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TSharedRef<SWidget> BuildOfficerRow(int32 Officer);
	int32 CityGold() const;
	FReply HandleReward();
	FReply HandleClose();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	int32 CityIndex = -1;
	TArray<int32> Officers;
	int32 SelectedOfficer = -1;
	int32 GoldValue = 100;
	FText ResultText;
	bool bResultError = false;
};

/** Prisoners held in a city; OnDecide opens the decision dialog for one of them. */
class IRONREIGN_API SIronPrisonerListDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronPrisonerListDialog)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
		SLATE_ARGUMENT(int32, City)
		SLATE_ARGUMENT(FIronIndexCallback, OnDecide)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	FReply HandleClose();

	TWeakPtr<SIronRoot> Root;
	FIronIndexCallback OnDecide;
};
