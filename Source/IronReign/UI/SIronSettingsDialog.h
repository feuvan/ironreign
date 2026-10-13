#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SBox;
class SIronRoot;

/** Modal options: language (live relabel), music and effect volumes, campaign map playback speed and battle animation speed. */
class SIronSettingsDialog : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronSettingsDialog) {}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(TWeakPtr<SIronRoot>, Root)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);
	/** Saves a volume changed without a drag end (keyboard / gamepad on the slider) when the dialog goes away. */
	virtual ~SIronSettingsDialog() override;

private:
	void Rebuild();
	TSharedRef<SWidget> MakeLanguageRow();
	TSharedRef<SWidget> MakeVolumeRow(const FText& Label, bool bMusic);
	TSharedRef<SWidget> MakeMapSpeedRow();
	TSharedRef<SWidget> MakeBattleSpeedRow();

	FReply OnLanguage(FString CultureName);
	FReply OnMapSpeed(float DaysPerSecond);
	FReply OnBattleSpeed(float StepSeconds);
	FReply OnClose();

	float GetVolume(bool bMusic) const;
	FText GetVolumeText(bool bMusic) const;
	/** Slider moved: applied to the audio at once, written to Settings.json by CommitVolumes. */
	void OnVolumeChanged(float NewValue, bool bMusic);
	/** Writes changed volumes to Settings.json; bPreviewSfx plays a sample effect at the new effects volume. */
	void CommitVolumes(bool bPreviewSfx);

	TSharedPtr<FIronSession> Session;
	TWeakPtr<SIronRoot> Root;
	TSharedPtr<SBox> ContentHost;
	bool bVolumeDirty = false;
};
