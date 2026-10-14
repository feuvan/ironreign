#pragma once

#include "CoreMinimal.h"
#include "Input/Reply.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;
class SBox;
class SIronRoot;
class SScrollBox;
enum class EIronPresentationMode : uint8;

/**
 * Modal options: language (live relabel), music and effect volumes, graphics (presentation mode Auto / 3D / 2D, quality,
 * tilt-shift, ink outlines; applied live by AIronReignPlayerController and the screens; the 3D scenes always use the
 * painted gongbi look, so no look is offered), campaign map playback speed and battle animation speed. The content
 * scrolls when the window is too short for it.
 */
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
	TSharedRef<SWidget> MakeGraphicsSection();
	/** Label column plus a row of choice buttons (graphics options). */
	TSharedRef<SWidget> MakeOptionRow(const FText& Label, const TSharedRef<SWidget>& Choices);
	/** Whether the 3D scenes are shown, or why not. */
	FText GetGraphicsStatus() const;

	FReply OnLanguage(FString CultureName);
	FReply OnPresentation(EIronPresentationMode Mode);
	FReply OnQuality(int32 Level);
	FReply OnTiltShift(bool bEnabled);
	FReply OnInkOutlines(bool bEnabled);
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
	/** Kept across rebuilds so a choice further down does not jump the list back to the top. */
	TSharedPtr<SScrollBox> ScrollBox;
	bool bVolumeDirty = false;
};
