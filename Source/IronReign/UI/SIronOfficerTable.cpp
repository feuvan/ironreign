#include "UI/SIronOfficerTable.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronRoot.h"
#include "UI/SIronStrategyCommon.h"

#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/Layout/SSpacer.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Text/STextBlock.h"

namespace IronOfficerTableDetail
{
	/** Portrait column in front of the sortable columns. */
	constexpr float PortraitWidth = 48.0f;

	int32 StatColumnIndex(int32 ColumnValue)
	{
		// EColumn::Martial .. EColumn::Charm map to stat indices 0..4.
		return ColumnValue - 2;
	}
}

void SIronOfficerTable::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	Root = InArgs._Root;
	OnShowCity = InArgs._OnShowCity;

	if (Session.IsValid() && Session->HasGame())
	{
		const IronSim::FGameState& GameState = Session->State();
		for (const int Officer : GameState.FactionOfficers(GameState.PlayerFaction))
		{
			Rows.Add(Officer);
		}
	}
	SortRows();

	TSharedPtr<FIronSession> SessionRef = Session;
	const TSharedRef<SWidget> Summary = SNew(STextBlock)
		.Text_Lambda([SessionRef]()
		{
			if (!SessionRef.IsValid() || !SessionRef->HasGame())
			{
				return FText::GetEmpty();
			}
			const IronSim::FGameState& LiveState = SessionRef->State();
			const std::vector<int> Officers = LiveState.FactionOfficers(LiveState.PlayerFaction);
			int32 Total = 0;
			int32 Idle = 0;
			for (const int Officer : Officers)
			{
				if (const IronSim::FOfficer* Data = IronStrategy::GetOfficer(LiveState, Officer))
				{
					Total += Data->Loyalty;
				}
				if (LiveState.IsOfficerIdle(Officer))
				{
					++Idle;
				}
			}
			const int32 Count = static_cast<int32>(Officers.size());
			const int32 Average = Count > 0 ? Total / Count : 0;
			return IronUI::LocF("ui.strategy.officerSummary", "{count} officers serve us. Average loyalty {loyalty}. {idle} are awaiting orders.", {{"count", IronSim::ToText(Count)}, {"loyalty", IronSim::ToText(Average)}, {"idle", IronSim::ToText(Idle)}});
		})
		.Font(IronStyle::Body(14.0f))
		.ColorAndOpacity(IronStyle::InkSoft());

	const TSharedRef<SWidget> Body = SNew(SVerticalBox)
		+ SVerticalBox::Slot()
		.AutoHeight()
		.Padding(FMargin(0.0f, 0.0f, 0.0f, 6.0f))
		[
			Summary
		]
		+ SVerticalBox::Slot()
		.AutoHeight()
		[
			SAssignNew(HeaderBox, SVerticalBox)
		]
		+ SVerticalBox::Slot()
		.FillHeight(1.0f)
		[
			SNew(SScrollBox)
			+ SScrollBox::Slot()
			[
				SAssignNew(RowBox, SVerticalBox)
			]
		];

	const TSharedRef<SWidget> Footer = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.FillWidth(1.0f)
		.VAlign(VAlign_Center)
		[
			SNew(STextBlock)
			.Text(IronUI::Loc("ui.strategy.officerTableHint", "Click a column to sort. Click an officer to show their city."))
			.Font(IronStyle::Body(13.0f))
			.ColorAndOpacity(IronStyle::InkSoft())
		]
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			IronStyle::MakeButton(IronUI::Loc("ui.strategy.close", "Close"), FOnClicked::CreateSP(this, &SIronOfficerTable::HandleClose), true, FString(), 140.0f)
		];

	ChildSlot
	[
		IronStrategy::MakeDialogFrame(IronUI::Loc("ui.strategy.officersTitle", "Officers"), Body, Footer, 1400.0f, 800.0f)
	];

	RebuildHeader();
	RebuildRows();
}

float SIronOfficerTable::ColumnWidth(EColumn Column) const
{
	switch (Column)
	{
	case EColumn::Name: return 210.0f;
	case EColumn::Age: return 52.0f;
	case EColumn::Martial:
	case EColumn::Command:
	case EColumn::Strategy:
	case EColumn::Politics:
	case EColumn::Charm:
		return 56.0f;
	case EColumn::Loyalty: return 72.0f;
	case EColumn::Location: return 170.0f;
	case EColumn::Activity: return 250.0f;
	case EColumn::Techniques: return 230.0f;
	}
	return 80.0f;
}

FText SIronOfficerTable::ColumnLabel(EColumn Column) const
{
	switch (Column)
	{
	case EColumn::Name: return IronUI::Loc("ui.strategy.colName", "Name");
	case EColumn::Age: return IronUI::Loc("ui.strategy.colAge", "Age");
	case EColumn::Martial:
	case EColumn::Command:
	case EColumn::Strategy:
	case EColumn::Politics:
	case EColumn::Charm:
		return IronStrategy::StatShort(IronOfficerTableDetail::StatColumnIndex(static_cast<int32>(Column)));
	case EColumn::Loyalty: return IronUI::Loc("ui.strategy.colLoyalty", "Loyalty");
	case EColumn::Location: return IronUI::Loc("ui.strategy.colLocation", "Location");
	case EColumn::Activity: return IronUI::Loc("ui.strategy.colOrder", "Order");
	case EColumn::Techniques: return IronUI::Loc("ui.strategy.colTechniques", "Techniques");
	}
	return FText::GetEmpty();
}

int32 SIronOfficerTable::CompareOfficers(int32 Left, int32 Right) const
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* LeftData = IronStrategy::GetOfficer(GameState, Left);
	const IronSim::FOfficer* RightData = IronStrategy::GetOfficer(GameState, Right);
	if (!LeftData || !RightData)
	{
		return (LeftData ? 1 : 0) - (RightData ? 1 : 0);
	}
	switch (SortColumn)
	{
	case EColumn::Name:
		return IronStrategy::OfficerName(GameState, Left).CompareTo(IronStrategy::OfficerName(GameState, Right));
	case EColumn::Age:
		return GameState.OfficerAge(Left) - GameState.OfficerAge(Right);
	case EColumn::Martial:
	case EColumn::Command:
	case EColumn::Strategy:
	case EColumn::Politics:
	case EColumn::Charm:
	{
		const int32 Stat = IronOfficerTableDetail::StatColumnIndex(static_cast<int32>(SortColumn));
		return LeftData->Stats[Stat] - RightData->Stats[Stat];
	}
	case EColumn::Loyalty:
		return LeftData->Loyalty - RightData->Loyalty;
	case EColumn::Location:
		return IronStrategy::CityName(GameState, LeftData->City).CompareTo(IronStrategy::CityName(GameState, RightData->City));
	case EColumn::Activity:
		return IronStrategy::OfficerActivity(GameState, Left).CompareTo(IronStrategy::OfficerActivity(GameState, Right));
	case EColumn::Techniques:
		return static_cast<int32>(LeftData->Techniques.size()) - static_cast<int32>(RightData->Techniques.size());
	}
	return 0;
}

void SIronOfficerTable::SortRows()
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	Rows.Sort([this](const int32& Left, const int32& Right)
	{
		int32 Order = CompareOfficers(Left, Right);
		if (Order == 0)
		{
			Order = Left - Right;
		}
		return bAscending ? Order < 0 : Order > 0;
	});
}

void SIronOfficerTable::RebuildHeader()
{
	if (!HeaderBox.IsValid())
	{
		return;
	}
	TSharedRef<SHorizontalBox> Header = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		[
			SNew(SSpacer)
			.Size(FVector2D(IronOfficerTableDetail::PortraitWidth, 1.0))
		];
	for (int32 Index = 0; Index < ColumnCount; ++Index)
	{
		const EColumn Column = static_cast<EColumn>(Index);
		const bool bActive = Column == SortColumn;
		FText Label = ColumnLabel(Column);
		if (bActive)
		{
			Label = bAscending
				? IronUI::LocF("ui.strategy.sortAscending", "{column} ^", {{"column", IronUI::ToStd(Label.ToString())}})
				: IronUI::LocF("ui.strategy.sortDescending", "{column} v", {{"column", IronUI::ToStd(Label.ToString())}});
		}
		Header->AddSlot()
		.AutoWidth()
		[
			SNew(SBox)
			.WidthOverride(ColumnWidth(Column))
			[
				SNew(SButton)
				.ButtonStyle(&IronStyle::RowButton())
				.IsFocusable(false)
				.ContentPadding(FMargin(4.0f, 3.0f))
				.OnClicked(FOnClicked::CreateSP(this, &SIronOfficerTable::HandleSort, Column))
				[
					SNew(STextBlock)
					.Text(Label)
					.Font(IronStyle::BodyBold(13.0f))
					.ColorAndOpacity(bActive ? IronStyle::Lacquer() : IronStyle::InkSoft())
				]
			]
		];
	}

	HeaderBox->ClearChildren();
	HeaderBox->AddSlot()
	.AutoHeight()
	[
		Header
	];
	HeaderBox->AddSlot()
	.AutoHeight()
	[
		SNew(SBox)
		.HeightOverride(2.0f)
		[
			SNew(SImage)
			.Image(IronStyle::WhiteBrush())
			.ColorAndOpacity(IronStyle::Gold().CopyWithNewOpacity(0.8f))
		]
	];
}

void SIronOfficerTable::RebuildRows()
{
	if (!RowBox.IsValid())
	{
		return;
	}
	RowBox->ClearChildren();
	if (Rows.Num() == 0)
	{
		RowBox->AddSlot()
		.AutoHeight()
		[
			IronStrategy::MakeWrappedText(IronUI::Loc("ui.strategy.noOfficersServing", "No officers serve us."), 15.0f, IronStyle::InkSoft())
		];
		return;
	}
	for (int32 Index = 0; Index < Rows.Num(); ++Index)
	{
		RowBox->AddSlot()
		.AutoHeight()
		[
			BuildRow(Rows[Index], Index)
		];
	}
}

TSharedRef<SWidget> SIronOfficerTable::BuildRow(int32 Officer, int32 RowIndex)
{
	const IronSim::FGameState& GameState = Session->State();
	const IronSim::FOfficer* Data = IronStrategy::GetOfficer(GameState, Officer);
	if (!Data)
	{
		return SNew(SBox);
	}
	const bool bRuler = GameState.IsRuler(Officer);
	FText Location = IronStrategy::CityName(GameState, Data->City);
	if (Data->Army >= 0)
	{
		Location = IronUI::Loc("ui.strategy.inTheField", "In the field");
	}

	TSharedRef<SHorizontalBox> Line = SNew(SHorizontalBox)
		+ SHorizontalBox::Slot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(IronOfficerTableDetail::PortraitWidth)
			.HAlign(HAlign_Center)
			[
				IronStyle::MakePortrait(IronStrategy::OfficerPortrait(GameState, Officer), 44.0f)
			]
		];

	for (int32 Index = 0; Index < ColumnCount; ++Index)
	{
		const EColumn Column = static_cast<EColumn>(Index);
		FText CellText;
		FLinearColor CellColor = IronStyle::Ink();
		FSlateFontInfo CellFont = IronStyle::Body(14.0f);
		switch (Column)
		{
		case EColumn::Name:
			CellText = IronUI::ToText(IronSim::NameOf(*Data));
			CellFont = IronStyle::BodyBold(15.0f);
			CellColor = bRuler ? IronStyle::Lacquer() : IronStyle::Ink();
			break;
		case EColumn::Age:
			CellText = FText::AsNumber(GameState.OfficerAge(Officer));
			break;
		case EColumn::Martial:
		case EColumn::Command:
		case EColumn::Strategy:
		case EColumn::Politics:
		case EColumn::Charm:
		{
			const int32 Value = Data->Stats[IronOfficerTableDetail::StatColumnIndex(Index)];
			CellText = FText::AsNumber(Value);
			CellColor = IronStrategy::StatColor(Value);
			CellFont = IronStyle::BodyBold(14.0f);
			break;
		}
		case EColumn::Loyalty:
			CellText = FText::AsNumber(Data->Loyalty);
			CellColor = IronStrategy::LoyaltyColor(Data->Loyalty);
			CellFont = IronStyle::BodyBold(14.0f);
			break;
		case EColumn::Location:
			CellText = Location;
			break;
		case EColumn::Activity:
			CellText = IronStrategy::OfficerActivity(GameState, Officer);
			CellColor = IronStyle::Indigo();
			CellFont = IronStyle::Body(13.0f);
			break;
		case EColumn::Techniques:
			CellText = IronStrategy::TechniqueList(GameState, Officer);
			CellFont = IronStyle::Body(13.0f);
			break;
		}
		Line->AddSlot()
		.AutoWidth()
		.VAlign(VAlign_Center)
		[
			SNew(SBox)
			.WidthOverride(ColumnWidth(Column))
			.Padding(FMargin(4.0f, 0.0f))
			[
				SNew(STextBlock)
				.Text(CellText)
				.Font(CellFont)
				.ColorAndOpacity(CellColor)
				.AutoWrapText(Column == EColumn::Activity || Column == EColumn::Techniques)
			]
		];
	}

	const FLinearColor Background = (RowIndex % 2 == 0) ? IronStyle::PaperDark().CopyWithNewOpacity(0.3f) : IronStyle::Paper().CopyWithNewOpacity(0.0f);
	return SNew(SButton)
		.ButtonStyle(&IronStyle::RowButton())
		.IsFocusable(false)
		.ContentPadding(FMargin(0.0f))
		.OnClicked(FOnClicked::CreateSP(this, &SIronOfficerTable::HandleRowClicked, Officer))
		[
			SNew(SBorder)
			.BorderImage(IronStyle::WhiteBrush())
			.BorderBackgroundColor(Background)
			.Padding(FMargin(0.0f, 2.0f))
			[
				Line
			]
		];
}

FReply SIronOfficerTable::HandleSort(EColumn Column)
{
	if (Column == SortColumn)
	{
		bAscending = !bAscending;
	}
	else
	{
		SortColumn = Column;
		bAscending = Column == EColumn::Name || Column == EColumn::Location || Column == EColumn::Activity;
	}
	SortRows();
	RebuildHeader();
	RebuildRows();
	return FReply::Handled();
}

FReply SIronOfficerTable::HandleRowClicked(int32 Officer)
{
	int32 City = -1;
	if (Session.IsValid() && Session->HasGame())
	{
		if (const IronSim::FOfficer* Data = IronStrategy::GetOfficer(Session->State(), Officer))
		{
			City = Data->City;
			if (City < 0 && Data->Army >= 0)
			{
				if (const IronSim::FArmy* Army = Session->State().FindArmy(Data->Army))
				{
					City = Army->Node;
				}
			}
		}
	}
	const FIronIndexCallback Callback = OnShowCity;
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->PopModal();
	}
	if (Callback && City >= 0)
	{
		Callback(City);
	}
	return FReply::Handled();
}

FReply SIronOfficerTable::HandleClose()
{
	if (TSharedPtr<SIronRoot> RootPtr = Root.Pin())
	{
		RootPtr->PopModal();
	}
	return FReply::Handled();
}
