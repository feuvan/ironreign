#pragma once

#include "CoreMinimal.h"
#include "Sim/IronBattle.h"
#include "Templates/Function.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;

/** Callback types for the strategy modals (aliases keep commas out of the SLATE_ARGUMENT macros). */
using FIronSimpleCallback = TFunction<void()>;
using FIronIndexCallback = TFunction<void(int32)>;
using FIronPrisonerDecided = TFunction<void(int32, const FText&)>;

/**
 * Event dialog for IronSim::FGame::CurrentEvent(): unrolled scroll backdrop, illustration, speaker portrait
 * (officer or advisor), title, text and one button per choice (disabled when the choice cannot be afforded).
 * OnChoose receives the choice index; the caller applies it and closes the modal.
 */
class IRONREIGN_API SIronEventDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronEventDialog) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(FIronIndexCallback, OnChoose)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	FReply HandleChoice(int32 ChoiceIndex);

	TSharedPtr<FIronSession> Session;
	FIronIndexCallback OnChoose;
	bool bAnswered = false;
};

/**
 * Decision on a captured officer: Recruit (with chance), Release, Execute or Imprison.
 * Applies FGame::DecidePrisoner itself and reports the resulting message through OnDecided.
 */
class IRONREIGN_API SIronPrisonerDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronPrisonerDialog)
		: _Prisoner(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(int32, Prisoner)
		SLATE_ARGUMENT(FIronPrisonerDecided, OnDecided)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	FReply HandleDecision(IronSim::EPrisonerDecision Decision);

	TSharedPtr<FIronSession> Session;
	FIronPrisonerDecided OnDecided;
	int32 PrisonerIndex = -1;
	bool bAnswered = false;
};

/** "Battle at <place>!" prompt: attacker vs defender summary with Command / Delegate buttons. */
class IRONREIGN_API SIronBattlePrompt : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronBattlePrompt)
		: _City(-1)
		, _PlayerAttacker(false)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(IronSim::FBattleSetup, Setup)
		/** Besieged city (-1 for field battles). */
		SLATE_ARGUMENT(int32, City)
		SLATE_ARGUMENT(bool, PlayerAttacker)
		SLATE_ARGUMENT(FIronSimpleCallback, OnCommand)
		SLATE_ARGUMENT(FIronSimpleCallback, OnDelegate)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TSharedRef<SWidget> BuildSide(const IronSim::FBattleSideSetup& Side, bool bAttacker) const;

	TSharedPtr<FIronSession> Session;
	FIronSimpleCallback OnCommand;
	FIronSimpleCallback OnDelegate;
	bool bAnswered = false;
};

/** Victory or defeat. */
class IRONREIGN_API SIronGameOverDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronGameOverDialog) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(FIronSimpleCallback, OnReturn)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	FIronSimpleCallback OnReturn;
};
