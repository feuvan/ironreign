#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SIronRoot;

/** Title screen: painted background, logo, main menu (New Game / Load Game / Settings / Quit) and a language picker. */
class SIronTitleScreen : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronTitleScreen) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

private:
	TSharedRef<SWidget> MakeMenu();
	TSharedRef<SWidget> MakeLanguagePicker();

	FReply OnNewGame();
	FReply OnLoadGame();
	FReply OnSettings();
	FReply OnQuit();
	FReply OnLanguage(FString CultureName);

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
};
