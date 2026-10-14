#include "UI/SIronSettingsDialog.h"

#include "Sim/IronLocale.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronRoot.h"

#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronSettingsDetail
{
	constexpr float ChoiceSpacing = 8.0f;
	constexpr float VolumeLabelWidth = 200.0f;
	constexpr float VolumeValueWidth = 64.0f;

	TSharedRef<SWidget> MakeSectionLabel(const FText& Text)
	{
		return SNew(STextBlock)
			.Text(Text)
			.Font(IronStyle::BodyBold(18.0f))
			.ColorAndOpacity(IronStyle::Lacquer());
	}

	TSharedRef<SWidget> MakeHint(const FText& Text)
	{
		return SNew(STextBlock)
			.Text(Text)
			.Font(IronStyle::Body(14.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
			.AutoWrapText(true);
	}
}

void SIronSettingsDialog::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;

	ChildSlot
	[
		SAssignNew(ContentHost, SBox)
		.WidthOverride(760.0f)
	];

	if (Session.IsValid())
	{
		// Rebuilt in the new language when the culture changes (also when changed from this dialog).
		Session->OnCultureChanged.AddSP(this, &SIronSettingsDialog::Rebuild);
	}
	Rebuild();
}

SIronSettingsDialog::~SIronSettingsDialog()
{
	if (bVolumeDirty)
	{
		CommitVolumes(false);
	}
}

void SIronSettingsDialog::Rebuild()
{
	if (!ContentHost.IsValid())
	{
		return;
	}
	const float SavedScrollOffset = ScrollBox.IsValid() ? ScrollBox->GetScrollOffset() : 0.0f;

	ContentHost->SetContent(IronStyle::MakePanel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.settings.title", "Settings"), 28.0f)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			// Scrolls only when the window is too short for every section.
			SAssignNew(ScrollBox, SScrollBox)
			+ SScrollBox::Slot()
			[
				SNew(SVerticalBox)
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 16.0f, 0.0f, 8.0f))
				[
					IronSettingsDetail::MakeSectionLabel(IronUI::Loc("ui.settings.language", "Language"))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					MakeLanguageRow()
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 20.0f, 0.0f, 8.0f))
				[
					IronSettingsDetail::MakeSectionLabel(IronUI::Loc("ui.settings.sound", "Sound"))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
				[
					MakeVolumeRow(IronUI::Loc("ui.settings.musicVolume", "Music volume"), true)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					MakeVolumeRow(IronUI::Loc("ui.settings.sfxVolume", "Effects volume"), false)
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 20.0f, 0.0f, 4.0f))
				[
					IronSettingsDetail::MakeSectionLabel(IronUI::Loc("ui.settings.graphics", "Graphics"))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					MakeGraphicsSection()
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 20.0f, 0.0f, 4.0f))
				[
					IronSettingsDetail::MakeSectionLabel(IronUI::Loc("ui.settings.mapSpeed", "Campaign map speed"))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 0.0f, 0.0f, 8.0f))
				[
					IronSettingsDetail::MakeHint(IronUI::Loc("ui.settings.mapSpeedHint", "How many days pass each second while the month plays out."))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					MakeMapSpeedRow()
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 20.0f, 0.0f, 4.0f))
				[
					IronSettingsDetail::MakeSectionLabel(IronUI::Loc("ui.settings.battleSpeed", "Battle animation speed"))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				.Padding(FMargin(0.0f, 0.0f, 0.0f, 8.0f))
				[
					IronSettingsDetail::MakeHint(IronUI::Loc("ui.settings.battleSpeedHint", "How quickly enemy moves are shown on the battlefield."))
				]
				+ SVerticalBox::Slot()
				.AutoHeight()
				[
					MakeBattleSpeedRow()
				]
			]
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Right)
		.Padding(FMargin(0.0f, 26.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.common.close", "Close"), FOnClicked::CreateSP(this, &SIronSettingsDialog::OnClose), true, FString(), 150.0f)
		],
		false,
		FMargin(34.0f, 28.0f)));

	if (ScrollBox.IsValid() && SavedScrollOffset > 0.0f)
	{
		ScrollBox->SetScrollOffset(SavedScrollOffset);
	}
}

TSharedRef<SWidget> SIronSettingsDialog::MakeLanguageRow()
{
	const FString Current = Session.IsValid() ? Session->GetCulture() : FString(TEXT("en"));
	TSharedRef<SHorizontalBox> Choices = SNew(SHorizontalBox);
	for (const FString& CultureName : FIronSession::SupportedCultures())
	{
		Choices->AddSlot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, IronSettingsDetail::ChoiceSpacing, 0.0f))
			[
				IronStyle::MakeChoiceButton(
					FIronSession::CultureDisplayName(CultureName),
					CultureName.Equals(Current, ESearchCase::IgnoreCase),
					FOnClicked::CreateSP(this, &SIronSettingsDialog::OnLanguage, CultureName),
					IronStyle::FontForCulture(CultureName, IronStyle::EFont::BodyBold, 16.0f))
			];
	}
	return Choices;
}

TSharedRef<SWidget> SIronSettingsDialog::MakeVolumeRow(const FText& Label, bool bMusic)
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(IronSettingsDetail::VolumeLabelWidth)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(IronStyle::Body(16.0f))
				.ColorAndOpacity(IronStyle::Ink())
			]
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		.Padding(FMargin(8.0f, 0.0f))
		[
			SNew(SSlider)
			.MinValue(0.0f)
			.MaxValue(1.0f)
			.StepSize(0.05f)
			.Value(TAttribute<float>::CreateLambda([this, bMusic]() { return GetVolume(bMusic); }))
			.SliderBarColor(IronStyle::InkSoft())
			.SliderHandleColor(IronStyle::Lacquer())
			.OnValueChanged(FOnFloatValueChanged::CreateSP(this, &SIronSettingsDialog::OnVolumeChanged, bMusic))
			// Preview the effects volume when a drag ends; music is heard while dragging.
			.OnMouseCaptureEnd(FSimpleDelegate::CreateSP(this, &SIronSettingsDialog::CommitVolumes, !bMusic))
			.OnControllerCaptureEnd(FSimpleDelegate::CreateSP(this, &SIronSettingsDialog::CommitVolumes, !bMusic))
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(IronSettingsDetail::VolumeValueWidth)
			[
				SNew(STextBlock)
				.Text(TAttribute<FText>::CreateLambda([this, bMusic]() { return GetVolumeText(bMusic); }))
				.Font(IronStyle::BodyBold(15.0f))
				.ColorAndOpacity(IronStyle::Ink())
				.Justification(ETextJustify::Right)
			]
		];
}

TSharedRef<SWidget> SIronSettingsDialog::MakeMapSpeedRow()
{
	const float Current = Session.IsValid() ? Session->GetDaysPerSecond() : 6.0f;
	const float Presets[] = {2.0f, 4.0f, 6.0f, 10.0f, 15.0f, 30.0f};
	TSharedRef<SHorizontalBox> Choices = SNew(SHorizontalBox);
	for (const float Preset : Presets)
	{
		const FText Label = IronUI::LocF("ui.settings.daysPerSecond", "{days} days/s", {{"days", IronSim::ToText(FMath::RoundToInt(Preset))}});
		Choices->AddSlot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, IronSettingsDetail::ChoiceSpacing, 0.0f))
			[
				IronStyle::MakeChoiceButton(
					Label,
					FMath::IsNearlyEqual(Current, Preset, 0.05f),
					FOnClicked::CreateSP(this, &SIronSettingsDialog::OnMapSpeed, Preset),
					IronStyle::BodyBold(15.0f))
			];
	}
	return Choices;
}

TSharedRef<SWidget> SIronSettingsDialog::MakeBattleSpeedRow()
{
	const float Current = Session.IsValid() ? Session->GetBattleStepSeconds() : 0.35f;
	struct FPreset
	{
		float Seconds;
		FText Label;
	};
	const FPreset Presets[] = {
		{0.6f, IronUI::Loc("ui.settings.speedSlow", "Slow")},
		{0.35f, IronUI::Loc("ui.settings.speedNormal", "Normal")},
		{0.18f, IronUI::Loc("ui.settings.speedFast", "Fast")},
		{0.06f, IronUI::Loc("ui.settings.speedVeryFast", "Very fast")}};

	TSharedRef<SHorizontalBox> Choices = SNew(SHorizontalBox);
	for (const FPreset& Preset : Presets)
	{
		Choices->AddSlot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, IronSettingsDetail::ChoiceSpacing, 0.0f))
			[
				IronStyle::MakeChoiceButton(
					Preset.Label,
					FMath::IsNearlyEqual(Current, Preset.Seconds, 0.01f),
					FOnClicked::CreateSP(this, &SIronSettingsDialog::OnBattleSpeed, Preset.Seconds),
					IronStyle::BodyBold(15.0f))
			];
	}
	return Choices;
}

FReply SIronSettingsDialog::OnLanguage(FString CultureName)
{
	if (Session.IsValid())
	{
		// Broadcasts OnCultureChanged, which rebuilds this dialog and the current screen.
		Session->SetCulture(CultureName);
	}
	return FReply::Handled();
}

TSharedRef<SWidget> SIronSettingsDialog::MakeOptionRow(const FText& Label, const TSharedRef<SWidget>& Choices)
{
	return SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(IronSettingsDetail::VolumeLabelWidth)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(IronStyle::Body(16.0f))
				.ColorAndOpacity(IronStyle::Ink())
			]
		]
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		.Padding(FMargin(8.0f, 0.0f, 0.0f, 0.0f))
		[
			Choices
		];
}

TSharedRef<SWidget> SIronSettingsDialog::MakeGraphicsSection()
{
	const EIronPresentationMode CurrentMode = Session.IsValid() ? Session->GetPresentationMode() : EIronPresentationMode::Auto;
	const int32 CurrentQuality = Session.IsValid() ? Session->GetGraphicsQuality() : 2;
	// Without a session the painted look's defaults (FIronSession: ink outlines on, tilt-shift off). There is no look
	// choice: the 3D scenes are always painted in the gongbi style of all the art (docs/DESIGN.md 8 and 12.6).
	const bool bTiltShiftOn = Session.IsValid() && Session->IsTiltShiftEnabled();
	const bool bInkOn = !Session.IsValid() || Session->IsInkOutlinesEnabled();
	const FSlateFontInfo ChoiceFont = IronStyle::BodyBold(15.0f);

	struct FModeChoice
	{
		EIronPresentationMode Value;
		FText Label;
	};
	const FModeChoice ModeChoices[] = {
		{EIronPresentationMode::Auto, IronUI::Loc("ui.settings.presentationAuto", "Auto")},
		{EIronPresentationMode::ThreeD, IronUI::Loc("ui.settings.presentation3d", "3D")},
		{EIronPresentationMode::TwoD, IronUI::Loc("ui.settings.presentation2d", "2D")}};
	TSharedRef<SHorizontalBox> ModeRow = SNew(SHorizontalBox);
	for (const FModeChoice& Choice : ModeChoices)
	{
		ModeRow->AddSlot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, IronSettingsDetail::ChoiceSpacing, 0.0f))
			[
				IronStyle::MakeChoiceButton(Choice.Label, Choice.Value == CurrentMode, FOnClicked::CreateSP(this, &SIronSettingsDialog::OnPresentation, Choice.Value), ChoiceFont)
			];
	}

	// Quality levels 0..3 of the 3D scenes (AIronEnvironment::SetQuality).
	const FText QualityLabels[] = {
		IronUI::Loc("ui.settings.qualityLow", "Low"),
		IronUI::Loc("ui.settings.qualityMedium", "Medium"),
		IronUI::Loc("ui.settings.qualityHigh", "High"),
		IronUI::Loc("ui.settings.qualityEpic", "Epic")};
	TSharedRef<SHorizontalBox> QualityRow = SNew(SHorizontalBox);
	for (int32 Level = 0; Level < 4; ++Level)
	{
		QualityRow->AddSlot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, IronSettingsDetail::ChoiceSpacing, 0.0f))
			[
				IronStyle::MakeChoiceButton(QualityLabels[Level], Level == CurrentQuality, FOnClicked::CreateSP(this, &SIronSettingsDialog::OnQuality, Level), ChoiceFont)
			];
	}

	const FText OnLabel = IronUI::Loc("ui.settings.on", "On");
	const FText OffLabel = IronUI::Loc("ui.settings.off", "Off");
	const auto MakeToggleRow = [this, &OnLabel, &OffLabel, &ChoiceFont](bool bCurrent, FReply (SIronSettingsDialog::*Handler)(bool)) -> TSharedRef<SWidget>
	{
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.Padding(FMargin(0.0f, 0.0f, IronSettingsDetail::ChoiceSpacing, 0.0f))
			[
				IronStyle::MakeChoiceButton(OnLabel, bCurrent, FOnClicked::CreateSP(this, Handler, true), ChoiceFont)
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			[
				IronStyle::MakeChoiceButton(OffLabel, !bCurrent, FOnClicked::CreateSP(this, Handler, false), ChoiceFont)
			];
	};

	return SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 8.0f))
		[
			IronSettingsDetail::MakeHint(GetGraphicsStatus())
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			MakeOptionRow(IronUI::Loc("ui.settings.presentation", "Map and battles"), ModeRow)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			MakeOptionRow(IronUI::Loc("ui.settings.quality", "3D quality"), QualityRow)
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			MakeOptionRow(IronUI::Loc("ui.settings.tiltShift", "Tilt-shift blur"), MakeToggleRow(bTiltShiftOn, &SIronSettingsDialog::OnTiltShift))
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			MakeOptionRow(IronUI::Loc("ui.settings.inkOutlines", "Ink outlines"), MakeToggleRow(bInkOn, &SIronSettingsDialog::OnInkOutlines))
		];
}

FText SIronSettingsDialog::GetGraphicsStatus() const
{
	if (!Session.IsValid())
	{
		return FText::GetEmpty();
	}
	if (!Session->Allows3D())
	{
		return IronUI::Loc("ui.settings.graphicsStatus2d", "The painted 2D map and battle board are shown.");
	}
	if (!Session->Is3DMapAvailable())
	{
		return IronUI::Loc("ui.settings.graphicsStatusMissing", "The 3D scenery is not installed, so the painted 2D map and battle board are shown.");
	}
	return IronUI::Loc("ui.settings.graphicsStatus3d", "The campaign map and battles are shown in real-time 3D. Quality, blur and outlines apply at once.");
}

FReply SIronSettingsDialog::OnPresentation(EIronPresentationMode Mode)
{
	if (Session.IsValid())
	{
		// Applied by the player controller and the strategy screen on their next frame.
		Session->SetPresentationMode(Mode);
	}
	Rebuild();
	return FReply::Handled();
}

FReply SIronSettingsDialog::OnQuality(int32 Level)
{
	if (Session.IsValid())
	{
		Session->SetGraphicsQuality(Level);
	}
	Rebuild();
	return FReply::Handled();
}

FReply SIronSettingsDialog::OnTiltShift(bool bEnabled)
{
	if (Session.IsValid())
	{
		Session->SetTiltShiftEnabled(bEnabled);
	}
	Rebuild();
	return FReply::Handled();
}

FReply SIronSettingsDialog::OnInkOutlines(bool bEnabled)
{
	if (Session.IsValid())
	{
		Session->SetInkOutlinesEnabled(bEnabled);
	}
	Rebuild();
	return FReply::Handled();
}

FReply SIronSettingsDialog::OnMapSpeed(float DaysPerSecond)
{
	if (Session.IsValid())
	{
		Session->SetDaysPerSecond(DaysPerSecond);
	}
	Rebuild();
	return FReply::Handled();
}

FReply SIronSettingsDialog::OnBattleSpeed(float StepSeconds)
{
	if (Session.IsValid())
	{
		Session->SetBattleStepSeconds(StepSeconds);
	}
	Rebuild();
	return FReply::Handled();
}

float SIronSettingsDialog::GetVolume(bool bMusic) const
{
	if (!Session.IsValid())
	{
		return bMusic ? FIronAudio::Get().GetMusicVolume() : FIronAudio::Get().GetSfxVolume();
	}
	return bMusic ? Session->GetMusicVolume() : Session->GetSfxVolume();
}

FText SIronSettingsDialog::GetVolumeText(bool bMusic) const
{
	return IronUI::LocF("ui.settings.volumePercent", "{percent}%", {{"percent", IronSim::ToText(FMath::RoundToInt(GetVolume(bMusic) * 100.0f))}});
}

void SIronSettingsDialog::OnVolumeChanged(float NewValue, bool bMusic)
{
	if (Session.IsValid())
	{
		if (bMusic)
		{
			Session->SetMusicVolume(NewValue, false);
		}
		else
		{
			Session->SetSfxVolume(NewValue, false);
		}
	}
	else if (bMusic)
	{
		FIronAudio::Get().SetMusicVolume(NewValue);
	}
	else
	{
		FIronAudio::Get().SetSfxVolume(NewValue);
	}
	bVolumeDirty = true;
}

void SIronSettingsDialog::CommitVolumes(bool bPreviewSfx)
{
	if (bVolumeDirty && Session.IsValid())
	{
		// Settings.json holds every option: persisting through one setter saves both volumes.
		Session->SetSfxVolume(Session->GetSfxVolume(), true);
	}
	bVolumeDirty = false;
	if (bPreviewSfx)
	{
		FIronAudio::Get().PlaySfx(TEXT("Click"));
	}
}

FReply SIronSettingsDialog::OnClose()
{
	if (bVolumeDirty)
	{
		CommitVolumes(false);
	}
	if (const TSharedPtr<SIronRoot> PinnedRoot = Root.Pin())
	{
		PinnedRoot->PopModal();
	}
	return FReply::Handled();
}
