#include "UI/SIronStrategyCommon.h"

#include "Sim/IronLocale.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"

#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Input/SSlider.h"
#include "Widgets/Input/SSpinBox.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronStrategy
{
	const IronSim::FOfficer* GetOfficer(const IronSim::FGameState& State, int32 Officer)
	{
		if (Officer < 0 || Officer >= static_cast<int32>(State.Officers.size()))
		{
			return nullptr;
		}
		return &State.Officers[static_cast<size_t>(Officer)];
	}

	const IronSim::FCity* GetCity(const IronSim::FGameState& State, int32 City)
	{
		if (City < 0 || City >= static_cast<int32>(State.Cities.size()))
		{
			return nullptr;
		}
		return &State.Cities[static_cast<size_t>(City)];
	}

	const IronSim::FFaction* GetFaction(const IronSim::FGameState& State, int32 Faction)
	{
		if (Faction < 0 || Faction >= static_cast<int32>(State.Factions.size()))
		{
			return nullptr;
		}
		return &State.Factions[static_cast<size_t>(Faction)];
	}

	const IronSim::FSect* GetSect(const IronSim::FGameState& State, int32 Sect)
	{
		if (Sect < 0 || Sect >= static_cast<int32>(State.Sects.size()))
		{
			return nullptr;
		}
		return &State.Sects[static_cast<size_t>(Sect)];
	}

	const IronSim::FTechnique* GetTechnique(const IronSim::FGameState& State, int32 Technique)
	{
		if (Technique < 0 || Technique >= static_cast<int32>(State.Techniques.size()))
		{
			return nullptr;
		}
		return &State.Techniques[static_cast<size_t>(Technique)];
	}

	FText OfficerName(const IronSim::FGameState& State, int32 Officer)
	{
		const IronSim::FOfficer* Data = GetOfficer(State, Officer);
		return Data ? IronUI::ToText(IronSim::NameOf(*Data)) : IronUI::Loc("ui.strategy.nobody", "-");
	}

	FText CityName(const IronSim::FGameState& State, int32 City)
	{
		const IronSim::FCity* Data = GetCity(State, City);
		return Data ? IronUI::ToText(IronSim::NameOf(*Data)) : IronUI::Loc("ui.strategy.noCity", "-");
	}

	FText FactionName(const IronSim::FGameState& State, int32 Faction)
	{
		const IronSim::FFaction* Data = GetFaction(State, Faction);
		return Data ? IronUI::ToText(IronSim::NameOf(*Data)) : IronUI::Loc("ui.strategy.independent", "Independent");
	}

	FText SectName(const IronSim::FGameState& State, int32 Sect)
	{
		const IronSim::FSect* Data = GetSect(State, Sect);
		return Data ? IronUI::ToText(IronSim::NameOf(*Data)) : IronUI::Loc("ui.strategy.noSect", "-");
	}

	FString FactionGlyph(const IronSim::FGameState& State, int32 Faction)
	{
		const IronSim::FFaction* Data = GetFaction(State, Faction);
		if (!Data)
		{
			return FString();
		}
		const std::string Key = "faction." + Data->Key + ".glyph";
		const std::string* Found = IronSim::FLocale::Active().Find(Key);
		return IronUI::ToFString(Found ? *Found : Data->Glyph);
	}

	FString OfficerPortrait(const IronSim::FGameState& State, int32 Officer)
	{
		const IronSim::FOfficer* Data = GetOfficer(State, Officer);
		if (!Data || Data->Portrait.empty())
		{
			return TEXT("unknown");
		}
		return IronUI::ToFString(Data->Portrait);
	}

	FText TechniqueList(const IronSim::FGameState& State, int32 Officer)
	{
		const IronSim::FOfficer* Data = GetOfficer(State, Officer);
		if (!Data || Data->Techniques.empty())
		{
			return IronUI::Loc("ui.strategy.noTechniques", "-");
		}
		std::string Joined;
		const std::string Separator = IronSim::Loc("ui.strategy.listSeparator", ", ");
		for (const int Technique : Data->Techniques)
		{
			const IronSim::FTechnique* Tech = GetTechnique(State, Technique);
			if (!Tech)
			{
				continue;
			}
			if (!Joined.empty())
			{
				Joined += Separator;
			}
			Joined += IronSim::NameOf(*Tech);
		}
		return IronUI::ToText(Joined);
	}

	FText StatShort(int32 StatIndex)
	{
		const int32 Clamped = FMath::Clamp(StatIndex, 0, IronSim::StatCount - 1);
		return IronUI::ToText(IronSim::ShortName(static_cast<IronSim::EStat>(Clamped)));
	}

	FText StatLong(int32 StatIndex)
	{
		const int32 Clamped = FMath::Clamp(StatIndex, 0, IronSim::StatCount - 1);
		return IronUI::ToText(IronSim::DisplayName(static_cast<IronSim::EStat>(Clamped)));
	}

	FText OrderName(IronSim::EOrderType Type)
	{
		return IronUI::ToText(IronSim::DisplayName(Type));
	}

	FText TroopTypeName(IronSim::ETroopType Type)
	{
		return IronUI::ToText(IronSim::DisplayName(Type));
	}

	FText CitySizeName(int32 Size)
	{
		switch (Size)
		{
		case 1:
			return IronUI::Loc("ui.strategy.citySize1", "Town");
		case 3:
			return IronUI::Loc("ui.strategy.citySize3", "Great City");
		default:
			return IronUI::Loc("ui.strategy.citySize2", "Walled City");
		}
	}

	FString OrderIcon(IronSim::EOrderType Type)
	{
		switch (Type)
		{
		case IronSim::EOrderType::Farm: return TEXT("Farm");
		case IronSim::EOrderType::Commerce: return TEXT("Commerce");
		case IronSim::EOrderType::Walls: return TEXT("Walls");
		case IronSim::EOrderType::Patrol: return TEXT("Patrol");
		case IronSim::EOrderType::Draft: return TEXT("Draft");
		case IronSim::EOrderType::Train: return TEXT("Train");
		case IronSim::EOrderType::Search: return TEXT("Search");
		case IronSim::EOrderType::Recruit: return TEXT("Recruit");
		case IronSim::EOrderType::Move: return TEXT("Move");
		case IronSim::EOrderType::Transport: return TEXT("Transport");
		case IronSim::EOrderType::SectTraining: return TEXT("SectTraining");
		case IronSim::EOrderType::Alliance: return TEXT("Alliance");
		case IronSim::EOrderType::Truce: return TEXT("Truce");
		case IronSim::EOrderType::Gift: return TEXT("Gift");
		case IronSim::EOrderType::Count: break;
		}
		return FString();
	}

	int32 GoverningStat(IronSim::EOrderType Type)
	{
		switch (Type)
		{
		case IronSim::EOrderType::Farm:
		case IronSim::EOrderType::Commerce:
		case IronSim::EOrderType::Walls:
		case IronSim::EOrderType::Alliance:
		case IronSim::EOrderType::Truce:
		case IronSim::EOrderType::Gift:
			return IronSim::StatIndex(IronSim::EStat::Politics);
		case IronSim::EOrderType::Patrol:
		case IronSim::EOrderType::SectTraining:
			return IronSim::StatIndex(IronSim::EStat::Martial);
		case IronSim::EOrderType::Train:
		case IronSim::EOrderType::Transport:
			return IronSim::StatIndex(IronSim::EStat::Command);
		case IronSim::EOrderType::Draft:
		case IronSim::EOrderType::Search:
		case IronSim::EOrderType::Recruit:
			return IronSim::StatIndex(IronSim::EStat::Charm);
		case IronSim::EOrderType::Move:
		case IronSim::EOrderType::Count:
			break;
		}
		return -1;
	}

	FText OrderSummary(const IronSim::FGameState& State, const IronSim::FOrder& Order)
	{
		const std::string OrderText = IronSim::DisplayName(Order.Type);
		std::string Target;
		switch (Order.Type)
		{
		case IronSim::EOrderType::Recruit:
			Target = IronUI::ToStd(OfficerName(State, Order.TargetOfficer).ToString());
			break;
		case IronSim::EOrderType::Move:
		case IronSim::EOrderType::Transport:
			Target = IronUI::ToStd(CityName(State, Order.TargetCity).ToString());
			break;
		case IronSim::EOrderType::SectTraining:
			Target = IronUI::ToStd(SectName(State, Order.TargetSect).ToString());
			break;
		case IronSim::EOrderType::Alliance:
		case IronSim::EOrderType::Truce:
		case IronSim::EOrderType::Gift:
			Target = IronUI::ToStd(FactionName(State, Order.TargetFaction).ToString());
			break;
		case IronSim::EOrderType::Draft:
			Target = IronSim::ToText(Order.Amount);
			break;
		default:
			break;
		}
		if (Target.empty())
		{
			return IronUI::ToText(OrderText);
		}
		return IronUI::LocF("ui.strategy.orderWithTarget", "{order}: {target}", {{"order", OrderText}, {"target", Target}});
	}

	FText OfficerActivity(const IronSim::FGameState& State, int32 Officer)
	{
		const IronSim::FOfficer* Data = GetOfficer(State, Officer);
		if (!Data)
		{
			return FText::GetEmpty();
		}
		switch (Data->Status)
		{
		case IronSim::EOfficerStatus::Prisoner:
			return IronUI::Loc("ui.strategy.activityPrisoner", "Prisoner");
		case IronSim::EOfficerStatus::Free:
			return IronUI::Loc("ui.strategy.activityFree", "Wandering");
		case IronSim::EOfficerStatus::Dead:
			return IronUI::Loc("ui.strategy.activityDead", "Deceased");
		case IronSim::EOfficerStatus::Hidden:
		case IronSim::EOfficerStatus::Unborn:
			return IronUI::Loc("ui.strategy.activityUnknown", "Unknown");
		case IronSim::EOfficerStatus::Serving:
			break;
		}
		if (Data->Army >= 0)
		{
			const IronSim::FArmy* Army = State.FindArmy(Data->Army);
			if (Army && Army->Target >= 0)
			{
				const std::string Target = IronUI::ToStd(CityName(State, Army->Target).ToString());
				if (Army->State == IronSim::EArmyState::Returning)
				{
					return IronUI::LocF("ui.strategy.activityReturning", "Returning to {city}", {{"city", Target}});
				}
				return IronUI::LocF("ui.strategy.activityMarching", "Marching to {city}", {{"city", Target}});
			}
			return IronUI::Loc("ui.strategy.activityArmy", "With an army");
		}
		if (const IronSim::FOrder* Order = State.OfficerOrder(Officer))
		{
			return OrderSummary(State, *Order);
		}
		return IronUI::Loc("ui.strategy.activityIdle", "Idle");
	}

	FText Num(int32 Value)
	{
		return FText::AsNumber(Value);
	}

	FText ApproxNum(int32 Value)
	{
		int32 Rounded = Value;
		if (Value >= 10000)
		{
			Rounded = ((Value + 500) / 1000) * 1000;
		}
		else if (Value >= 1000)
		{
			Rounded = ((Value + 50) / 100) * 100;
		}
		return IronUI::LocF("ui.strategy.approx", "~{value}", {{"value", IronUI::ToStd(FText::AsNumber(Rounded).ToString())}});
	}

	FLinearColor StatColor(int32 Value)
	{
		if (Value >= 90)
		{
			return IronStyle::Lacquer();
		}
		if (Value >= 75)
		{
			return IronStyle::Indigo();
		}
		if (Value < 40)
		{
			return IronStyle::InkSoft();
		}
		return IronStyle::Ink();
	}

	FLinearColor LoyaltyColor(int32 Loyalty)
	{
		if (Loyalty >= 80)
		{
			return IronStyle::Jade();
		}
		if (Loyalty < 60)
		{
			return IronStyle::Danger();
		}
		return IronStyle::Ink();
	}

	bool IsEnglishCulture()
	{
		return !IronSim::FLocale::Active().IsCjk();
	}

	int32 PlayerAdvisor(const IronSim::FGameState& State)
	{
		int32 Best = -1;
		int32 BestValue = -1;
		for (const int Officer : State.FactionOfficers(State.PlayerFaction))
		{
			const IronSim::FOfficer* Data = GetOfficer(State, Officer);
			if (!Data || State.IsRuler(Officer))
			{
				continue;
			}
			const int32 Value = Data->GetStat(IronSim::EStat::Strategy);
			if (Value > BestValue)
			{
				BestValue = Value;
				Best = Officer;
			}
		}
		if (Best < 0)
		{
			const IronSim::FFaction* Faction = GetFaction(State, State.PlayerFaction);
			Best = Faction ? Faction->Ruler : -1;
		}
		return Best;
	}

	TSharedRef<SWidget> MakeStatsRow(const IronSim::FOfficer& Officer, int32 HighlightStat, float FontSize)
	{
		TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
		for (int32 Index = 0; Index < IronSim::StatCount; ++Index)
		{
			const bool bHighlight = Index == HighlightStat;
			const int32 Value = Officer.Stats[Index];
			Row->AddSlot()
			.AutoWidth()
			.Padding(FMargin(1.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(FontSize * 2.6f)
				[
					SNew(SBorder)
					.BorderImage(IronStyle::WhiteBrush())
					.BorderBackgroundColor(bHighlight ? IronStyle::Gold().CopyWithNewOpacity(0.55f) : FLinearColor::Transparent)
					.HAlign(HAlign_Center)
					.Padding(FMargin(2.0f, 1.0f))
					[
						SNew(STextBlock)
						.Text(FText::AsNumber(Value))
						.Font(bHighlight ? IronStyle::BodyBold(FontSize) : IronStyle::Body(FontSize))
						.ColorAndOpacity(StatColor(Value))
					]
				]
			];
		}
		return Row;
	}

	TSharedRef<SWidget> MakeStatsHeader(int32 HighlightStat, float FontSize)
	{
		TSharedRef<SHorizontalBox> Row = SNew(SHorizontalBox);
		const float CellWidth = (FontSize + 2.0f) * 2.6f;
		for (int32 Index = 0; Index < IronSim::StatCount; ++Index)
		{
			const bool bHighlight = Index == HighlightStat;
			Row->AddSlot()
			.AutoWidth()
			.Padding(FMargin(1.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(CellWidth)
				.HAlign(HAlign_Center)
				[
					SNew(STextBlock)
					.Text(StatShort(Index))
					.Font(bHighlight ? IronStyle::BodyBold(FontSize) : IronStyle::Body(FontSize))
					.ColorAndOpacity(bHighlight ? IronStyle::Lacquer() : IronStyle::InkSoft())
				]
			];
		}
		return Row;
	}

	TSharedRef<SWidget> MakeSectionTitle(const TAttribute<FText>& Text, float Size)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(Text)
				.Font(IronStyle::Heading(Size))
				.ColorAndOpacity(IronStyle::Lacquer())
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 1.0f, 0.0f, 4.0f))
			[
				SNew(SBox)
				.HeightOverride(2.0f)
				[
					SNew(SImage)
					.Image(IronStyle::WhiteBrush())
					.ColorAndOpacity(IronStyle::Gold().CopyWithNewOpacity(0.7f))
				]
			];
	}

	TSharedRef<SWidget> MakeDialogFrame(const TAttribute<FText>& Title, const TSharedRef<SWidget>& Body, const TSharedRef<SWidget>& Footer, float Width, float Height)
	{
		return SNew(SBox)
			.WidthOverride(Width > 0.0f ? FOptionalSize(Width) : FOptionalSize())
			.HeightOverride(Height > 0.0f ? FOptionalSize(Height) : FOptionalSize())
			[
				IronStyle::MakePanel(
					SNew(SVerticalBox)
					+ SVerticalBox::Slot()
					.AutoHeight()
					.HAlign(HAlign_Center)
					[
						IronStyle::MakeHeader(Title, 26.0f, false)
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 4.0f, 0.0f, 10.0f))
					[
						SNew(SBox)
						.HeightOverride(12.0f)
						[
							SNew(SImage)
							.Image(IronStyle::Divider())
						]
					]
					+ SVerticalBox::Slot()
					.FillHeight(1.0f)
					[
						Body
					]
					+ SVerticalBox::Slot()
					.AutoHeight()
					.Padding(FMargin(0.0f, 12.0f, 0.0f, 0.0f))
					[
						Footer
					],
					false,
					FMargin(28.0f, 22.0f))
			];
	}

	TSharedRef<SWidget> MakeAmountEditor(const FText& Label, TFunction<int32()> GetMax, int32* ValuePtr, int32 Step, TFunction<void()> OnChanged)
	{
		const int32 SafeStep = FMath::Max(1, Step);
		auto SetValue = [GetMax, ValuePtr, OnChanged](int32 RequestedValue)
		{
			if (ValuePtr == nullptr)
			{
				return;
			}
			const int32 Max = GetMax ? FMath::Max(0, GetMax()) : 0;
			*ValuePtr = FMath::Clamp(RequestedValue, 0, Max);
			if (OnChanged)
			{
				OnChanged();
			}
		};
		auto ReadMax = [GetMax]() -> int32
		{
			return GetMax ? FMath::Max(0, GetMax()) : 0;
		};

		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(130.0f)
				[
					SNew(STextBlock)
					.Text(Label)
					.Font(IronStyle::Body(14.0f))
					.ColorAndOpacity(IronStyle::Ink())
					.AutoWrapText(true)
				]
			]
			+ SHorizontalBox::Slot()
			.FillWidth(1.0f)
			.VAlign(VAlign_Center)
			.Padding(FMargin(6.0f, 0.0f))
			[
				SNew(SSlider)
				.Value_Lambda([ReadMax, ValuePtr]()
				{
					const int32 Max = ReadMax();
					return (Max > 0 && ValuePtr != nullptr) ? FMath::Clamp(static_cast<float>(*ValuePtr) / static_cast<float>(Max), 0.0f, 1.0f) : 0.0f;
				})
				.OnValueChanged_Lambda([ReadMax, SetValue, SafeStep](float SliderFraction)
				{
					const int32 Max = ReadMax();
					int32 Raw = FMath::RoundToInt(SliderFraction * static_cast<float>(Max));
					if (Raw < Max)
					{
						Raw = (Raw / SafeStep) * SafeStep;
					}
					SetValue(Raw);
				})
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.WidthOverride(110.0f)
				[
					SNew(SSpinBox<int32>)
					.MinValue(0)
					.MaxValue_Lambda([ReadMax]() -> TOptional<int32> { return ReadMax(); })
					.MinSliderValue(0)
					.MaxSliderValue_Lambda([ReadMax]() -> TOptional<int32> { return ReadMax(); })
					.Delta(SafeStep)
					.Value_Lambda([ValuePtr]() { return ValuePtr != nullptr ? *ValuePtr : 0; })
					.OnValueChanged_Lambda([SetValue](int32 SpinValue) { SetValue(SpinValue); })
					.OnValueCommitted_Lambda([SetValue](int32 CommittedValue, ETextCommit::Type) { SetValue(CommittedValue); })
					.Font(IronStyle::Body(14.0f))
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(6.0f, 0.0f, 0.0f, 0.0f))
			[
				IronStyle::MakeButton(IronUI::Loc("ui.strategy.max", "Max"), FOnClicked::CreateLambda([ReadMax, SetValue]()
				{
					SetValue(ReadMax());
					return FReply::Handled();
				}))
			];
	}

	TSharedRef<SWidget> MakeWrappedText(const TAttribute<FText>& Text, float Size, const FLinearColor& Color)
	{
		return SNew(STextBlock)
			.Text(Text)
			.Font(IronStyle::Body(Size))
			.ColorAndOpacity(Color)
			.AutoWrapText(true);
	}
}
