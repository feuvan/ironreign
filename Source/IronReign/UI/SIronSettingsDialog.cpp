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

	ContentHost->SetContent(IronStyle::MakePanel(
		SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			IronStyle::MakeHeader(IronUI::Loc("ui.settings.title", "Settings"), 28.0f)
		]
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
		+ SVerticalBox::Slot()
		.AutoHeight()
		.HAlign(HAlign_Right)
		.Padding(FMargin(0.0f, 26.0f, 0.0f, 0.0f))
		[
			IronStyle::MakeButton(IronUI::Loc("ui.common.close", "Close"), FOnClicked::CreateSP(this, &SIronSettingsDialog::OnClose), true, FString(), 150.0f)
		],
		false,
		FMargin(34.0f, 28.0f)));
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
