#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SBox;
class SIronRoot;

/** Modal options: language (live relabel), campaign map playback speed and battle animation speed. */
class SIronSettingsDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronSettingsDialog) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	void Rebuild();
	TSharedRef<SWidget> MakeLanguageRow();
	TSharedRef<SWidget> MakeMapSpeedRow();
	TSharedRef<SWidget> MakeBattleSpeedRow();

	FReply OnLanguage(FString CultureName);
	FReply OnMapSpeed(float DaysPerSecond);
	FReply OnBattleSpeed(float StepSeconds);
	FReply OnClose();

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	TSharedPtr<SBox> ContentHost;
};
