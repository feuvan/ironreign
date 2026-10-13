#include "UI/SIronMapView.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronStrategyCommon.h"

#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Input/CursorReply.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Templates/Function.h"

namespace IronMapViewDetail
{
	struct FRoadStyle
	{
		FLinearColor Color = FLinearColor::Black;
		float Dash = 8.0f;
		float Gap = 6.0f;
		float Thickness = 2.0f;
	};

	/** Works with FVector2D, FVector2f and Slate's deprecation wrapper types (anything with X and Y). */
	template <typename VectorType>
	FVector2f ToVec2f(const VectorType& Value)
	{
		return FVector2f(static_cast<float>(Value.X), static_cast<float>(Value.Y));
	}

	FVector2f CityMapPos(const IronSim::FCity& City)
	{
		return FVector2f(City.Position.X, City.Position.Y);
	}

	float TextScaleFor(float MapScale)
	{
		return FMath::Clamp(MapScale, 0.75f, 1.2f);
	}

	FVector2f MeasureText(const FString& Text, const FSlateFontInfo& Font)
	{
		if (Text.IsEmpty() || !FSlateApplication::IsInitialized() || FSlateApplication::Get().GetRenderer() == nullptr)
		{
			return FVector2f(static_cast<float>(Text.Len()) * 7.0f, 14.0f);
		}
		const TSharedRef<FSlateFontMeasure> FontMeasure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
		return ToVec2f(FontMeasure->Measure(Text, Font));
	}

	void AddRect(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
	{
		FSlateDrawElement::MakeBox(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), FIronAssets::Get().White(), ESlateDrawEffect::None, Color);
	}

	void AddImage(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FSlateBrush* Brush, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
	{
		if (Brush == nullptr)
		{
			return;
		}
		FSlateDrawElement::MakeBox(Out, Layer, Geo.ToPaintGeometry(Size, FSlateLayoutTransform(Pos)), Brush, ESlateDrawEffect::None, Color);
	}

	void AddText(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FString& Text, const FSlateFontInfo& Font, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color)
	{
		if (Text.IsEmpty())
		{
			return;
		}
		const FVector2f SafeSize(FMath::Max(Size.X, 1.0f), FMath::Max(Size.Y, 1.0f));
		FSlateDrawElement::MakeText(Out, Layer, Geo.ToPaintGeometry(SafeSize, FSlateLayoutTransform(Pos)), Text, Font, ESlateDrawEffect::None, Color);
	}

	void AddPolyline(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, TArray<FVector2f> Points, const FLinearColor& Color, float Thickness)
	{
		if (Points.Num() < 2)
		{
			return;
		}
		FSlateDrawElement::MakeLines(Out, Layer, Geo.ToPaintGeometry(), MoveTemp(Points), ESlateDrawEffect::None, Color, true, Thickness);
	}

	void AddOutline(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Pos, const FVector2f& Size, const FLinearColor& Color, float Thickness)
	{
		TArray<FVector2f> Points;
		Points.Add(Pos);
		Points.Add(FVector2f(Pos.X + Size.X, Pos.Y));
		Points.Add(FVector2f(Pos.X + Size.X, Pos.Y + Size.Y));
		Points.Add(FVector2f(Pos.X, Pos.Y + Size.Y));
		Points.Add(Pos);
		AddPolyline(Out, Layer, Geo, MoveTemp(Points), Color, Thickness);
	}

	void AddEllipse(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const FVector2f& Center, float RadiusX, float RadiusY, const FLinearColor& Color, float Thickness)
	{
		const int32 Segments = 40;
		TArray<FVector2f> Points;
		Points.Reserve(Segments + 1);
		for (int32 Index = 0; Index <= Segments; ++Index)
		{
			const float Angle = 6.2831853f * static_cast<float>(Index) / static_cast<float>(Segments);
			Points.Add(FVector2f(Center.X + FMath::Cos(Angle) * RadiusX, Center.Y + FMath::Sin(Angle) * RadiusY));
		}
		AddPolyline(Out, Layer, Geo, MoveTemp(Points), Color, Thickness);
	}

	/** Splits a polyline into dashes and calls Emit for each dash (which may bend around corners). */
	void EmitDashes(const TArray<FVector2f>& Poly, float Dash, float Gap, TFunctionRef<void(TArray<FVector2f>&)> Emit)
	{
		const float DashLength = FMath::Max(Dash, 0.5f);
		const float GapLength = FMath::Max(Gap, 0.5f);
		TArray<FVector2f> Current;
		bool bOn = true;
		float Remaining = DashLength;
		for (int32 Index = 1; Index < Poly.Num(); ++Index)
		{
			FVector2f From = Poly[Index - 1];
			const FVector2f To = Poly[Index];
			float SegmentLeft = (To - From).Size();
			if (SegmentLeft <= 0.0001f)
			{
				continue;
			}
			const FVector2f Direction = (To - From) / SegmentLeft;
			if (bOn && Current.Num() == 0)
			{
				Current.Add(From);
			}
			while (SegmentLeft > 0.0f)
			{
				const float Advance = FMath::Min(Remaining, SegmentLeft);
				const FVector2f Next = From + Direction * Advance;
				if (bOn)
				{
					Current.Add(Next);
				}
				From = Next;
				SegmentLeft -= Advance;
				Remaining -= Advance;
				if (Remaining <= 0.001f)
				{
					if (bOn && Current.Num() >= 2)
					{
						Emit(Current);
					}
					Current.Reset();
					bOn = !bOn;
					Remaining = bOn ? DashLength : GapLength;
					if (bOn)
					{
						Current.Add(From);
					}
				}
			}
		}
		if (bOn && Current.Num() >= 2)
		{
			Emit(Current);
		}
	}

	FRoadStyle RoadStyleFor(IronSim::ERoadKind Kind)
	{
		FRoadStyle Style;
		switch (Kind)
		{
		case IronSim::ERoadKind::Pass:
			Style.Color = IronStyle::Ink().CopyWithNewOpacity(0.85f);
			Style.Dash = 2.5f;
			Style.Gap = 5.0f;
			Style.Thickness = 2.6f;
			break;
		case IronSim::ERoadKind::River:
			Style.Color = IronUI::ColorFromRGB(0x3A6EA5, 0.9f);
			Style.Dash = 12.0f;
			Style.Gap = 5.0f;
			Style.Thickness = 2.6f;
			break;
		case IronSim::ERoadKind::Road:
		default:
			Style.Color = IronStyle::Ink().CopyWithNewOpacity(0.75f);
			Style.Dash = 9.0f;
			Style.Gap = 6.0f;
			Style.Thickness = 2.0f;
			break;
		}
		return Style;
	}

	/** Appends the road between two cities (waypoints oriented from FromCity) and the destination city. */
	void AppendLeg(const IronSim::FGameState& State, int32 FromCity, int32 ToCity, TArray<FVector2f>& InOutMapPath)
	{
		const IronSim::FCity* Destination = IronStrategy::GetCity(State, ToCity);
		if (!Destination)
		{
			return;
		}
		const int32 RoadIndex = State.RoadBetween(FromCity, ToCity);
		if (RoadIndex >= 0 && RoadIndex < static_cast<int32>(State.Roads.size()))
		{
			const IronSim::FRoad& Road = State.Roads[static_cast<size_t>(RoadIndex)];
			const int32 Count = static_cast<int32>(Road.Points.size());
			for (int32 Step = 0; Step < Count; ++Step)
			{
				const int32 PointIndex = Road.A == FromCity ? Step : Count - 1 - Step;
				const IronSim::FPoint& Point = Road.Points[static_cast<size_t>(PointIndex)];
				InOutMapPath.Add(FVector2f(Point.X, Point.Y));
			}
		}
		InOutMapPath.Add(CityMapPos(*Destination));
	}
}

void SIronMapView::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	FractionalDayAttr = InArgs._FractionalDay;
	SelectedCityAttr = InArgs._SelectedCity;
	OnCityClicked = InArgs._OnCityClicked;

	SetClipping(EWidgetClipping::ClipToBounds);
	LoadArtInfo();

	ViewCenter = MapSize() * 0.5f;
	if (Session.IsValid() && Session->HasGame())
	{
		const IronSim::FGameState& GameState = Session->State();
		const IronSim::FFaction* Player = IronStrategy::GetFaction(GameState, GameState.PlayerFaction);
		if (Player && Player->Capital >= 0)
		{
			CenterOnCity(Player->Capital);
		}
	}
}

void SIronMapView::LoadArtInfo()
{
	FIronAssets& Assets = FIronAssets::Get();
	MapImage = TEXT("Art/Map/WorldMap.png");
	if (Session.IsValid() && Session->HasGame() && !Session->State().Map.Image.empty())
	{
		MapImage = IronUI::ToFString(Session->State().Map.Image);
	}
	bHasMapArt = Assets.Exists(MapImage);
	for (int32 Index = 0; Index < 3; ++Index)
	{
		bHasCityArt[Index] = Assets.Exists(FString::Printf(TEXT("Art/Map/City_%d.png"), Index + 1));
	}
	bHasFlagArt = Assets.Exists(TEXT("Art/Map/Flag.png"));
	bHasSectArt = Assets.Exists(TEXT("Art/Map/Sect.png"));
	bHasBannerArt = Assets.Exists(TEXT("Art/Map/Banner.png"));
	if (bHasBannerArt)
	{
		const FVector2D ArtSize = Assets.ImageSize(TEXT("Art/Map/Banner.png"));
		if (ArtSize.X > 1.0 && ArtSize.Y > 1.0)
		{
			BannerArtSize = IronMapViewDetail::ToVec2f(ArtSize);
		}
	}

	FString AreaText;
	const FString AreaPath = FIronSession::DataDir() / TEXT("Art/Map/BannerGlyphArea.txt");
	if (FPaths::FileExists(AreaPath) && FFileHelper::LoadFileToString(AreaText, *AreaPath))
	{
		TArray<FString> Parts;
		AreaText.ParseIntoArrayWS(Parts);
		if (Parts.Num() >= 4)
		{
			const float ParsedW = FCString::Atof(*Parts[2]);
			const float ParsedH = FCString::Atof(*Parts[3]);
			if (ParsedW > 0.0f && ParsedH > 0.0f)
			{
				GlyphAreaX = FCString::Atof(*Parts[0]);
				GlyphAreaY = FCString::Atof(*Parts[1]);
				GlyphAreaW = ParsedW;
				GlyphAreaH = ParsedH;
			}
		}
	}
}

FVector2f SIronMapView::MapSize() const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return FVector2f(2400.0f, 1500.0f);
	}
	const IronSim::FMapDef& Map = Session->State().Map;
	return FVector2f(static_cast<float>(FMath::Max(Map.Width, 1)), static_cast<float>(FMath::Max(Map.Height, 1)));
}

SIronMapView::FMapFrame SIronMapView::MakeFrame(const FVector2f& InViewSize) const
{
	FMapFrame Frame;
	Frame.ViewSize = FVector2f(FMath::Max(InViewSize.X, 1.0f), FMath::Max(InViewSize.Y, 1.0f));
	const FVector2f Extent = MapSize();
	const float MinScale = FMath::Max3(0.5f, Frame.ViewSize.X / Extent.X, Frame.ViewSize.Y / Extent.Y);
	Frame.Scale = FMath::Clamp(Zoom, MinScale, FMath::Max(2.5f, MinScale));
	const float HalfW = Frame.ViewSize.X * 0.5f / Frame.Scale;
	const float HalfH = Frame.ViewSize.Y * 0.5f / Frame.Scale;
	Frame.Center.X = HalfW * 2.0f >= Extent.X ? Extent.X * 0.5f : FMath::Clamp(ViewCenter.X, HalfW, Extent.X - HalfW);
	Frame.Center.Y = HalfH * 2.0f >= Extent.Y ? Extent.Y * 0.5f : FMath::Clamp(ViewCenter.Y, HalfH, Extent.Y - HalfH);
	return Frame;
}

void SIronMapView::ClampView(const FVector2f& InViewSize)
{
	if (InViewSize.X < 2.0f || InViewSize.Y < 2.0f)
	{
		return;
	}
	const FMapFrame Frame = MakeFrame(InViewSize);
	ViewCenter = Frame.Center;
	Zoom = Frame.Scale;
}

void SIronMapView::CenterOnCity(int32 InCity)
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	const IronSim::FCity* Data = IronStrategy::GetCity(Session->State(), InCity);
	if (!Data)
	{
		return;
	}
	ViewCenter = IronMapViewDetail::CityMapPos(*Data);
	ClampView(LastViewSize);
}

void SIronMapView::SetView(const FVector2f& InCenter, float InZoom)
{
	ViewCenter = InCenter;
	Zoom = FMath::Clamp(InZoom, 0.5f, 2.5f);
	ClampView(LastViewSize);
}

float SIronMapView::CityIconSize(int32 CitySize, float Scale) const
{
	const float Base = CitySize <= 1 ? 46.0f : (CitySize == 2 ? 58.0f : 74.0f);
	return Base * FMath::Clamp(Scale, 0.55f, 1.35f);
}

float SIronMapView::BannerHeight(float Scale) const
{
	return 50.0f * FMath::Clamp(Scale, 0.6f, 1.3f);
}

void SIronMapView::CollectArmies(const FMapFrame& Frame, float Fraction, TArray<FArmyPlacement>& OutPlacements) const
{
	OutPlacements.Reset();
	if (!Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	const IronSim::FGameState& GameState = Session->State();
	const float Spread = BannerHeight(Frame.Scale) * 0.45f;
	for (const IronSim::FArmy& Army : GameState.Armies)
	{
		if (Army.Units.empty())
		{
			continue;
		}
		const IronSim::FPoint Point = GameState.ArmyPosition(Army, Fraction);
		FArmyPlacement Placement;
		Placement.ArmyId = Army.Id;
		Placement.Faction = Army.Faction;
		Placement.Troops = Army.TotalTroops();
		Placement.Local = Frame.ToLocal(FVector2f(Point.X, Point.Y));
		if (Army.Next < 0 || Army.Road < 0)
		{
			// Waiting in a city: stand beside the city icon instead of on top of it.
			Placement.Local.X += CityIconSize(2, Frame.Scale) * 0.55f;
		}
		for (const FArmyPlacement& Other : OutPlacements)
		{
			if ((Other.Local - Placement.Local).SizeSquared() < Spread * Spread)
			{
				Placement.Local.X += Spread;
			}
		}
		OutPlacements.Add(Placement);
	}
}

int32 SIronMapView::HitTestCity(const FMapFrame& Frame, const FVector2f& LocalPos) const
{
	if (!Session.IsValid() || !Session->HasGame())
	{
		return -1;
	}
	const IronSim::FGameState& GameState = Session->State();
	const float Below = 20.0f * IronMapViewDetail::TextScaleFor(Frame.Scale);
	int32 Best = -1;
	float BestDistance = TNumericLimits<float>::Max();
	for (int32 Index = 0; Index < static_cast<int32>(GameState.Cities.size()); ++Index)
	{
		const IronSim::FCity& Data = GameState.Cities[static_cast<size_t>(Index)];
		const FVector2f Anchor = Frame.ToLocal(IronMapViewDetail::CityMapPos(Data));
		const float IconSize = CityIconSize(Data.Size, Frame.Scale);
		if (LocalPos.X < Anchor.X - IconSize * 0.5f || LocalPos.X > Anchor.X + IconSize * 0.5f || LocalPos.Y < Anchor.Y - IconSize || LocalPos.Y > Anchor.Y + Below)
		{
			continue;
		}
		const float Distance = (LocalPos - FVector2f(Anchor.X, Anchor.Y - IconSize * 0.4f)).SizeSquared();
		if (Distance < BestDistance)
		{
			BestDistance = Distance;
			Best = Index;
		}
	}
	return Best;
}

int32 SIronMapView::HitTestArmy(const FMapFrame& Frame, const FVector2f& LocalPos) const
{
	TArray<FArmyPlacement> Placements;
	CollectArmies(Frame, FMath::Clamp(FractionalDayAttr.Get(), 0.0f, 1.0f), Placements);
	const float BannerH = BannerHeight(Frame.Scale);
	const float BannerW = BannerH * BannerArtSize.X / FMath::Max(BannerArtSize.Y, 1.0f);
	for (int32 Index = Placements.Num() - 1; Index >= 0; --Index)
	{
		const FArmyPlacement& Placement = Placements[Index];
		if (LocalPos.X >= Placement.Local.X - BannerW * 0.5f && LocalPos.X <= Placement.Local.X + BannerW * 0.5f
			&& LocalPos.Y >= Placement.Local.Y - BannerH && LocalPos.Y <= Placement.Local.Y + 14.0f)
		{
			return Placement.ArmyId;
		}
	}
	return -1;
}

void SIronMapView::UpdateHover(const FVector2f& LocalPos)
{
	HoverLocal = LocalPos;
	HoverArmyId = -1;
	HoverCity = -1;
	if (!Session.IsValid() || !Session->HasGame() || LastViewSize.X < 2.0f)
	{
		return;
	}
	const FMapFrame Frame = MakeFrame(LastViewSize);
	HoverArmyId = HitTestArmy(Frame, LocalPos);
	if (HoverArmyId < 0)
	{
		HoverCity = HitTestCity(Frame, LocalPos);
	}
}

FVector2D SIronMapView::ComputeDesiredSize(float LayoutScaleMultiplier) const
{
	return FVector2D(800.0, 600.0);
}

int32 SIronMapView::OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const
{
	LastViewSize = IronMapViewDetail::ToVec2f(AllottedGeometry.GetLocalSize());

	int32 Layer = LayerId;
	IronMapViewDetail::AddRect(OutDrawElements, Layer, AllottedGeometry, FVector2f(0.0f, 0.0f), LastViewSize, IronStyle::Night());
	if (!Session.IsValid() || !Session->HasGame())
	{
		return Layer;
	}

	const IronSim::FGameState& GameState = Session->State();
	const FMapFrame Frame = MakeFrame(LastViewSize);

	// Painted world map.
	++Layer;
	const FVector2f TopLeft = Frame.ToLocal(FVector2f(0.0f, 0.0f));
	const FVector2f Extent = MapSize() * Frame.Scale;
	if (bHasMapArt)
	{
		IronMapViewDetail::AddImage(OutDrawElements, Layer, AllottedGeometry, FIronAssets::Get().Image(MapImage), TopLeft, Extent, InWidgetStyle.GetColorAndOpacityTint());
	}
	else
	{
		// Fallback: parchment sea with the land outlines from the scenario.
		IronMapViewDetail::AddRect(OutDrawElements, Layer, AllottedGeometry, TopLeft, Extent, IronStyle::Indigo().CopyWithNewOpacity(0.55f));
		for (const std::vector<IronSim::FPoint>& Polygon : GameState.Map.Land)
		{
			TArray<FVector2f> Points;
			for (const IronSim::FPoint& Point : Polygon)
			{
				Points.Add(Frame.ToLocal(FVector2f(Point.X, Point.Y)));
			}
			if (Points.Num() > 1)
			{
				Points.Add(Points[0]);
			}
			IronMapViewDetail::AddPolyline(OutDrawElements, Layer + 1, AllottedGeometry, MoveTemp(Points), IronStyle::Paper(), 3.0f);
		}
		++Layer;
	}

	const float Fraction = FMath::Clamp(FractionalDayAttr.Get(), 0.0f, 1.0f);
	Layer = PaintRoads(Frame, AllottedGeometry, OutDrawElements, Layer + 1);
	Layer = PaintLabels(Frame, AllottedGeometry, OutDrawElements, Layer + 1);
	Layer = PaintMarchRoutes(Frame, AllottedGeometry, OutDrawElements, Layer + 1, Fraction);
	Layer = PaintCities(Frame, AllottedGeometry, OutDrawElements, Layer + 1);
	Layer = PaintArmies(Frame, AllottedGeometry, OutDrawElements, Layer + 1, Fraction);
	Layer = PaintTooltip(Frame, AllottedGeometry, OutDrawElements, Layer + 1);
	return Layer;
}

int32 SIronMapView::PaintRoads(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	const IronSim::FGameState& GameState = Session->State();
	const float DashScale = FMath::Clamp(Frame.Scale, 0.6f, 1.6f);
	const FLinearColor Underlay = IronStyle::Paper().CopyWithNewOpacity(0.35f);
	for (const IronSim::FRoad& Road : GameState.Roads)
	{
		const IronSim::FCity* CityA = IronStrategy::GetCity(GameState, Road.A);
		const IronSim::FCity* CityB = IronStrategy::GetCity(GameState, Road.B);
		if (!CityA || !CityB)
		{
			continue;
		}
		TArray<FVector2f> Poly;
		Poly.Add(Frame.ToLocal(IronMapViewDetail::CityMapPos(*CityA)));
		for (const IronSim::FPoint& Point : Road.Points)
		{
			Poly.Add(Frame.ToLocal(FVector2f(Point.X, Point.Y)));
		}
		Poly.Add(Frame.ToLocal(IronMapViewDetail::CityMapPos(*CityB)));

		// Skip roads entirely outside the view.
		FVector2f Low = Poly[0];
		FVector2f High = Poly[0];
		for (const FVector2f& Point : Poly)
		{
			Low = FVector2f(FMath::Min(Low.X, Point.X), FMath::Min(Low.Y, Point.Y));
			High = FVector2f(FMath::Max(High.X, Point.X), FMath::Max(High.Y, Point.Y));
		}
		if (High.X < -20.0f || High.Y < -20.0f || Low.X > Frame.ViewSize.X + 20.0f || Low.Y > Frame.ViewSize.Y + 20.0f)
		{
			continue;
		}

		const IronMapViewDetail::FRoadStyle Style = IronMapViewDetail::RoadStyleFor(Road.Kind);
		IronMapViewDetail::AddPolyline(OutDrawElements, Layer, Geo, Poly, Underlay, Style.Thickness + 3.0f);
		IronMapViewDetail::EmitDashes(Poly, Style.Dash * DashScale, Style.Gap * DashScale, [&](TArray<FVector2f>& DashPoints)
		{
			IronMapViewDetail::AddPolyline(OutDrawElements, Layer + 1, Geo, DashPoints, Style.Color, Style.Thickness);
		});
	}
	return Layer + 1;
}

int32 SIronMapView::PaintLabels(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	const IronSim::FGameState& GameState = Session->State();
	const FLinearColor LabelColor = IronStyle::Ink().CopyWithNewOpacity(0.42f);
	for (int32 Index = 0; Index < static_cast<int32>(GameState.Map.Labels.size()); ++Index)
	{
		const IronSim::FMapLabel& Label = GameState.Map.Labels[static_cast<size_t>(Index)];
		const FString LabelText = IronUI::ToFString(IronSim::MapLabelOf(GameState, Index));
		FSlateFontInfo LabelFont = IronStyle::Heading(FMath::Max(8.0f, 24.0f * Label.Size * Frame.Scale));
		LabelFont.LetterSpacing = 180;
		const FVector2f TextSize = IronMapViewDetail::MeasureText(LabelText, LabelFont);
		const FVector2f LabelCenter = Frame.ToLocal(FVector2f(Label.Position.X, Label.Position.Y));
		IronMapViewDetail::AddText(OutDrawElements, Layer, Geo, LabelText, LabelFont, LabelCenter - TextSize * 0.5f, TextSize, LabelColor);
	}
	return Layer;
}

int32 SIronMapView::PaintMarchRoutes(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer, float Fraction) const
{
	const IronSim::FGameState& GameState = Session->State();
	if (GameState.PlayerFaction < 0)
	{
		return Layer;
	}
	const float DashScale = FMath::Clamp(Frame.Scale, 0.7f, 1.5f);
	for (const IronSim::FArmy& Army : GameState.Armies)
	{
		if (Army.Faction != GameState.PlayerFaction || Army.Target < 0 || Army.Units.empty())
		{
			continue;
		}
		TArray<FVector2f> MapPath;
		const IronSim::FPoint Start = GameState.ArmyPosition(Army, Fraction);
		MapPath.Add(FVector2f(Start.X, Start.Y));
		int32 From = Army.Node;
		if (Army.Next >= 0)
		{
			if (const IronSim::FCity* NextCity = IronStrategy::GetCity(GameState, Army.Next))
			{
				MapPath.Add(IronMapViewDetail::CityMapPos(*NextCity));
			}
			From = Army.Next;
		}
		for (const int Stop : Army.Route)
		{
			if (Stop == From)
			{
				continue;
			}
			IronMapViewDetail::AppendLeg(GameState, From, Stop, MapPath);
			From = Stop;
		}
		if (From != Army.Target)
		{
			IronMapViewDetail::AppendLeg(GameState, From, Army.Target, MapPath);
		}
		if (MapPath.Num() < 2)
		{
			continue;
		}

		TArray<FVector2f> Path;
		Path.Reserve(MapPath.Num());
		for (const FVector2f& MapPoint : MapPath)
		{
			Path.Add(Frame.ToLocal(MapPoint));
		}

		const bool bReturning = Army.State == IronSim::EArmyState::Returning;
		const FLinearColor RouteColor = bReturning ? IronStyle::InkSoft().CopyWithNewOpacity(0.75f) : IronStyle::Lacquer().CopyWithNewOpacity(0.9f);
		IronMapViewDetail::EmitDashes(Path, 14.0f * DashScale, 6.0f * DashScale, [&](TArray<FVector2f>& DashPoints)
		{
			IronMapViewDetail::AddPolyline(OutDrawElements, Layer, Geo, DashPoints, RouteColor, 3.0f);
		});

		// Arrow head at the destination.
		const FVector2f Tip = Path.Last();
		FVector2f Previous = Path[Path.Num() - 2];
		for (int32 Index = Path.Num() - 2; Index >= 0; --Index)
		{
			Previous = Path[Index];
			if ((Tip - Previous).SizeSquared() > 4.0f)
			{
				break;
			}
		}
		const FVector2f Direction = (Tip - Previous).GetSafeNormal();
		if (!Direction.IsNearlyZero())
		{
			const FVector2f Side(-Direction.Y, Direction.X);
			const float HeadLength = 14.0f * DashScale;
			const float HeadWidth = 8.0f * DashScale;
			TArray<FVector2f> Head;
			Head.Add(Tip - Direction * HeadLength + Side * HeadWidth);
			Head.Add(Tip);
			Head.Add(Tip - Direction * HeadLength - Side * HeadWidth);
			IronMapViewDetail::AddPolyline(OutDrawElements, Layer, Geo, MoveTemp(Head), RouteColor, 3.5f);
		}
	}
	return Layer;
}

int32 SIronMapView::PaintCities(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	const IronSim::FGameState& GameState = Session->State();
	FIronAssets& Assets = FIronAssets::Get();
	const int32 Selected = SelectedCityAttr.Get();
	const float TextScale = IronMapViewDetail::TextScaleFor(Frame.Scale);
	const bool bShowZh = IronStrategy::IsEnglishCulture() && Frame.Scale >= 0.7f;
	const bool bShowTroops = Frame.Scale >= 0.6f;
	const FSlateFontInfo NameFont = IronStyle::BodyBold(13.0f * TextScale);
	const FSlateFontInfo ZhFont = IronStyle::Brush(15.0f * TextScale);
	const FSlateFontInfo SmallFont = IronStyle::Body(11.5f * TextScale);
	const FSlateBrush* TroopIcon = Assets.Icon(TEXT("Troops"));

	const int32 LayerRing = Layer;
	const int32 LayerIcon = Layer + 1;
	const int32 LayerFlag = Layer + 2;
	const int32 LayerPlaque = Layer + 3;
	const int32 LayerText = Layer + 4;

	for (int32 Index = 0; Index < static_cast<int32>(GameState.Cities.size()); ++Index)
	{
		const IronSim::FCity& Data = GameState.Cities[static_cast<size_t>(Index)];
		const FVector2f Anchor = Frame.ToLocal(IronMapViewDetail::CityMapPos(Data));
		const float IconSize = CityIconSize(Data.Size, Frame.Scale);
		if (Anchor.X < -IconSize - 120.0f || Anchor.Y < -IconSize - 40.0f || Anchor.X > Frame.ViewSize.X + IconSize + 120.0f || Anchor.Y > Frame.ViewSize.Y + IconSize + 40.0f)
		{
			continue;
		}
		const bool bSelected = Index == Selected;
		const bool bHovered = Index == HoverCity;
		const FLinearColor OwnerColor = IronStyle::FactionColor(Data.Owner);

		// Selection ring / hover highlight on the ground.
		if (bSelected)
		{
			IronMapViewDetail::AddEllipse(OutDrawElements, LayerRing, Geo, Anchor, IconSize * 0.62f, IconSize * 0.26f, IronStyle::Gold(), 3.0f);
			IronMapViewDetail::AddEllipse(OutDrawElements, LayerRing, Geo, Anchor, IconSize * 0.72f, IconSize * 0.32f, IronStyle::Lacquer().CopyWithNewOpacity(0.7f), 1.5f);
		}
		else if (bHovered)
		{
			IronMapViewDetail::AddEllipse(OutDrawElements, LayerRing, Geo, Anchor, IconSize * 0.58f, IconSize * 0.24f, IronStyle::Paper().CopyWithNewOpacity(0.9f), 2.0f);
		}

		// City icon, anchored bottom-centre.
		const int32 SizeIndex = FMath::Clamp(Data.Size, 1, 3) - 1;
		const FVector2f IconPos(Anchor.X - IconSize * 0.5f, Anchor.Y - IconSize);
		if (bHasCityArt[SizeIndex])
		{
			const FLinearColor IconTint = bHovered ? FLinearColor(1.0f, 0.97f, 0.88f, 1.0f) : FLinearColor::White;
			IronMapViewDetail::AddImage(OutDrawElements, LayerIcon, Geo, Assets.Image(FString::Printf(TEXT("Art/Map/City_%d.png"), SizeIndex + 1)), IconPos, FVector2f(IconSize, IconSize), IconTint);
		}
		else
		{
			const float Block = IconSize * (0.35f + 0.1f * static_cast<float>(SizeIndex));
			const FVector2f BlockPos(Anchor.X - Block * 0.5f, Anchor.Y - Block);
			IronMapViewDetail::AddRect(OutDrawElements, LayerIcon, Geo, BlockPos, FVector2f(Block, Block), IronStyle::PaperDark());
			IronMapViewDetail::AddOutline(OutDrawElements, LayerIcon, Geo, BlockPos, FVector2f(Block, Block), IronStyle::Ink(), 2.0f);
		}

		// Owner pennant above the roofs.
		const float FlagH = IconSize * 0.42f;
		const float FlagW = FlagH * (32.0f / 48.0f);
		const FVector2f FlagPos(Anchor.X + IconSize * 0.08f, Anchor.Y - IconSize - FlagH * 0.45f);
		if (bHasFlagArt)
		{
			IronMapViewDetail::AddImage(OutDrawElements, LayerFlag, Geo, Assets.Image(TEXT("Art/Map/Flag.png")), FlagPos, FVector2f(FlagW, FlagH), OwnerColor);
		}
		else
		{
			IronMapViewDetail::AddRect(OutDrawElements, LayerFlag, Geo, FlagPos, FVector2f(2.0f, FlagH), IronStyle::Ink());
			IronMapViewDetail::AddRect(OutDrawElements, LayerFlag, Geo, FlagPos + FVector2f(2.0f, 0.0f), FVector2f(FlagW, FlagH * 0.5f), OwnerColor);
		}

		// Name plaque.
		const FString CityLabel = IronUI::ToFString(IronSim::NameOf(Data));
		const FVector2f NameSize = IronMapViewDetail::MeasureText(CityLabel, NameFont);
		FString ZhLabel;
		FVector2f ZhSize(0.0f, 0.0f);
		if (bShowZh && !Data.NameZh.empty())
		{
			ZhLabel = IronUI::ToFString(Data.NameZh);
			ZhSize = IronMapViewDetail::MeasureText(ZhLabel, ZhFont);
		}
		const float PadX = 6.0f * TextScale;
		const float PlaqueW = NameSize.X + (ZhLabel.IsEmpty() ? 0.0f : ZhSize.X + PadX) + PadX * 2.0f;
		const float PlaqueH = FMath::Max(NameSize.Y, ZhSize.Y) + 3.0f * TextScale;
		const FVector2f PlaquePos(Anchor.X - PlaqueW * 0.5f, Anchor.Y + 1.0f);
		const FLinearColor PlaqueColor = bSelected ? IronStyle::Lacquer().CopyWithNewOpacity(0.92f) : IronStyle::Night().CopyWithNewOpacity(0.8f);
		IronMapViewDetail::AddRect(OutDrawElements, LayerPlaque, Geo, PlaquePos, FVector2f(PlaqueW, PlaqueH), PlaqueColor);
		IronMapViewDetail::AddRect(OutDrawElements, LayerPlaque, Geo, FVector2f(PlaquePos.X, PlaquePos.Y + PlaqueH - 2.5f), FVector2f(PlaqueW, 2.5f), OwnerColor);
		IronMapViewDetail::AddText(OutDrawElements, LayerText, Geo, CityLabel, NameFont, FVector2f(PlaquePos.X + PadX, PlaquePos.Y + (PlaqueH - NameSize.Y) * 0.5f - 1.0f), NameSize, IronStyle::TextLight());
		if (!ZhLabel.IsEmpty())
		{
			IronMapViewDetail::AddText(OutDrawElements, LayerText, Geo, ZhLabel, ZhFont, FVector2f(PlaquePos.X + PadX * 2.0f + NameSize.X, PlaquePos.Y + (PlaqueH - ZhSize.Y) * 0.5f - 1.0f), ZhSize, IronStyle::Gold());
		}

		// Garrison.
		if (bShowTroops)
		{
			const bool bOwn = GameState.PlayerFaction >= 0 && Data.Owner == GameState.PlayerFaction;
			const FString TroopText = (bOwn ? IronStrategy::Num(Data.Troops) : IronStrategy::ApproxNum(Data.Troops)).ToString();
			const FVector2f TroopSize = IronMapViewDetail::MeasureText(TroopText, SmallFont);
			const float TroopIconSize = TroopSize.Y;
			const float RowWidth = TroopIconSize + 3.0f + TroopSize.X;
			const FVector2f RowPos(Anchor.X - RowWidth * 0.5f, PlaquePos.Y + PlaqueH + 1.0f);
			IronMapViewDetail::AddRect(OutDrawElements, LayerPlaque, Geo, RowPos - FVector2f(4.0f, 0.0f), FVector2f(RowWidth + 8.0f, TroopSize.Y), IronStyle::Night().CopyWithNewOpacity(0.55f));
			IronMapViewDetail::AddImage(OutDrawElements, LayerText, Geo, TroopIcon, RowPos, FVector2f(TroopIconSize, TroopIconSize), FLinearColor::White);
			IronMapViewDetail::AddText(OutDrawElements, LayerText, Geo, TroopText, SmallFont, FVector2f(RowPos.X + TroopIconSize + 3.0f, RowPos.Y), TroopSize, IronStyle::Paper());
		}
	}

	// Sect markers next to their cities.
	const FSlateBrush* SectBrush = bHasSectArt ? Assets.Image(TEXT("Art/Map/Sect.png")) : nullptr;
	for (const IronSim::FSect& Sect : GameState.Sects)
	{
		const IronSim::FCity* Host = IronStrategy::GetCity(GameState, Sect.City);
		if (!Host)
		{
			continue;
		}
		const FVector2f Anchor = Frame.ToLocal(IronMapViewDetail::CityMapPos(*Host));
		const float IconSize = CityIconSize(Host->Size, Frame.Scale);
		const float MarkerSize = IconSize * 0.48f;
		const FVector2f MarkerPos(Anchor.X - IconSize * 0.5f - MarkerSize * 0.55f, Anchor.Y - MarkerSize * 1.05f);
		if (SectBrush)
		{
			IronMapViewDetail::AddImage(OutDrawElements, LayerFlag, Geo, SectBrush, MarkerPos, FVector2f(MarkerSize, MarkerSize), FLinearColor::White);
		}
		else
		{
			IronMapViewDetail::AddRect(OutDrawElements, LayerFlag, Geo, MarkerPos + FVector2f(MarkerSize * 0.25f, MarkerSize * 0.25f), FVector2f(MarkerSize * 0.5f, MarkerSize * 0.5f), IronStyle::Jade());
		}
	}
	return LayerText;
}

int32 SIronMapView::PaintArmies(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer, float Fraction) const
{
	const IronSim::FGameState& GameState = Session->State();
	TArray<FArmyPlacement> Placements;
	CollectArmies(Frame, Fraction, Placements);
	if (Placements.Num() == 0)
	{
		return Layer;
	}
	FIronAssets& Assets = FIronAssets::Get();
	const FSlateBrush* BannerBrush = bHasBannerArt ? Assets.Image(TEXT("Art/Map/Banner.png")) : nullptr;
	const float TextScale = IronMapViewDetail::TextScaleFor(Frame.Scale);
	const float BannerH = BannerHeight(Frame.Scale);
	const float ArtW = FMath::Max(BannerArtSize.X, 1.0f);
	const float ArtH = FMath::Max(BannerArtSize.Y, 1.0f);
	const float BannerW = BannerH * ArtW / ArtH;
	const FVector2f GlyphOffset(GlyphAreaX / ArtW * BannerW, GlyphAreaY / ArtH * BannerH);
	const FVector2f GlyphBox(GlyphAreaW / ArtW * BannerW, GlyphAreaH / ArtH * BannerH);
	const FSlateFontInfo GlyphFont = IronStyle::Brush(FMath::Max(8.0f, FMath::Min(GlyphBox.X, GlyphBox.Y) * 0.78f));
	const FSlateFontInfo CountFont = IronStyle::BodyBold(11.0f * TextScale);

	for (const FArmyPlacement& Placement : Placements)
	{
		if (Placement.Local.X < -BannerW * 2.0f || Placement.Local.Y < -20.0f || Placement.Local.X > Frame.ViewSize.X + BannerW * 2.0f || Placement.Local.Y > Frame.ViewSize.Y + BannerH + 20.0f)
		{
			continue;
		}
		const FLinearColor Tint = IronStyle::FactionColor(Placement.Faction);
		const FVector2f TopLeft(Placement.Local.X - BannerW * 0.5f, Placement.Local.Y - BannerH);
		const bool bHovered = Placement.ArmyId == HoverArmyId;

		IronMapViewDetail::AddEllipse(OutDrawElements, Layer, Geo, Placement.Local, BannerW * 0.38f, BannerW * 0.13f, IronStyle::Ink().CopyWithNewOpacity(0.55f), 2.0f);
		if (BannerBrush)
		{
			IronMapViewDetail::AddImage(OutDrawElements, Layer + 1, Geo, BannerBrush, TopLeft, FVector2f(BannerW, BannerH), Tint);
		}
		else
		{
			IronMapViewDetail::AddRect(OutDrawElements, Layer + 1, Geo, FVector2f(TopLeft.X + BannerW * 0.12f, TopLeft.Y), FVector2f(2.5f, BannerH), IronStyle::Ink());
			IronMapViewDetail::AddRect(OutDrawElements, Layer + 1, Geo, TopLeft + GlyphOffset, GlyphBox, Tint);
		}
		if (bHovered)
		{
			IronMapViewDetail::AddOutline(OutDrawElements, Layer + 2, Geo, TopLeft - FVector2f(2.0f, 2.0f), FVector2f(BannerW + 4.0f, BannerH + 4.0f), IronStyle::Gold(), 2.0f);
		}

		const FString Glyph = IronStrategy::FactionGlyph(GameState, Placement.Faction);
		if (!Glyph.IsEmpty())
		{
			const FVector2f GlyphSize = IronMapViewDetail::MeasureText(Glyph, GlyphFont);
			const FVector2f GlyphPos = TopLeft + GlyphOffset + (GlyphBox - GlyphSize) * 0.5f;
			IronMapViewDetail::AddText(OutDrawElements, Layer + 2, Geo, Glyph, GlyphFont, GlyphPos, GlyphSize, IronStyle::Paper());
		}

		const bool bOwn = GameState.PlayerFaction >= 0 && Placement.Faction == GameState.PlayerFaction;
		const FString CountText = (bOwn ? IronStrategy::Num(Placement.Troops) : IronStrategy::ApproxNum(Placement.Troops)).ToString();
		const FVector2f CountSize = IronMapViewDetail::MeasureText(CountText, CountFont);
		const FVector2f CountPos(Placement.Local.X - CountSize.X * 0.5f, Placement.Local.Y + 2.0f);
		IronMapViewDetail::AddRect(OutDrawElements, Layer + 1, Geo, CountPos - FVector2f(4.0f, 0.0f), FVector2f(CountSize.X + 8.0f, CountSize.Y), Tint * FLinearColor(0.45f, 0.45f, 0.45f, 0.9f));
		IronMapViewDetail::AddText(OutDrawElements, Layer + 2, Geo, CountText, CountFont, CountPos, CountSize, IronStyle::Paper());
	}
	return Layer + 2;
}

int32 SIronMapView::PaintTooltip(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	if (bDragging || (HoverCity < 0 && HoverArmyId < 0))
	{
		return Layer;
	}
	const IronSim::FGameState& GameState = Session->State();
	const bool bHasPlayer = GameState.PlayerFaction >= 0;
	FString Title;
	TArray<FString> Lines;

	if (HoverArmyId >= 0)
	{
		const IronSim::FArmy* Army = GameState.FindArmy(HoverArmyId);
		if (Army && !Army->Units.empty())
		{
			const bool bOwn = bHasPlayer && Army->Faction == GameState.PlayerFaction;
			const int32 Troops = Army->TotalTroops();
			Title = IronUI::LocF("ui.strategy.tipArmyTitle", "{faction} Army", {{"faction", IronUI::ToStd(IronStrategy::FactionName(GameState, Army->Faction).ToString())}}).ToString();
			Lines.Add(IronUI::LocF("ui.strategy.tipCommander", "Commander: {name}", {{"name", IronUI::ToStd(IronStrategy::OfficerName(GameState, Army->Units[0].Officer).ToString())}}).ToString());
			Lines.Add(IronUI::LocF("ui.strategy.tipUnits", "Units: {count}", {{"count", IronSim::ToText(static_cast<int>(Army->Units.size()))}}).ToString());
			Lines.Add(IronUI::LocF("ui.strategy.tipTroops", "Troops: {troops}", {{"troops", IronUI::ToStd((bOwn ? IronStrategy::Num(Troops) : IronStrategy::ApproxNum(Troops)).ToString())}}).ToString());
			if (Army->Target >= 0)
			{
				const std::string TargetName = IronUI::ToStd(IronStrategy::CityName(GameState, Army->Target).ToString());
				if (Army->State == IronSim::EArmyState::Returning)
				{
					Lines.Add(IronUI::LocF("ui.strategy.tipReturning", "Returning to {city}", {{"city", TargetName}}).ToString());
				}
				else
				{
					Lines.Add(IronUI::LocF("ui.strategy.tipTarget", "Target: {city}", {{"city", TargetName}}).ToString());
				}
			}
			if (bOwn)
			{
				const int32 Daily = FMath::Max(1, Session->Game().ArmyDailyFood(Troops));
				Lines.Add(IronUI::LocF("ui.strategy.tipArmyFood", "Food: {food} ({days} days)", {{"food", IronUI::ToStd(IronStrategy::Num(Army->Food).ToString())}, {"days", IronSim::ToText(Army->Food / Daily)}}).ToString());
				Lines.Add(IronUI::LocF("ui.strategy.tipMorale", "Morale: {morale}", {{"morale", IronSim::ToText(Army->Morale)}}).ToString());
			}
		}
	}
	else if (const IronSim::FCity* Data = IronStrategy::GetCity(GameState, HoverCity))
	{
		const bool bOwn = bHasPlayer && Data->Owner == GameState.PlayerFaction;
		Title = IronUI::ToFString(IronSim::NameOf(*Data));
		if (IronStrategy::IsEnglishCulture() && !Data->NameZh.empty())
		{
			Title += TEXT("  ");
			Title += IronUI::ToFString(Data->NameZh);
		}
		Lines.Add(IronUI::LocF("ui.strategy.tipOwner", "Ruled by: {faction}", {{"faction", IronUI::ToStd(IronStrategy::FactionName(GameState, Data->Owner).ToString())}}).ToString());
		Lines.Add(IronUI::LocF("ui.strategy.tipSizeTerrain", "{size}, {terrain}", {{"size", IronUI::ToStd(IronStrategy::CitySizeName(Data->Size).ToString())}, {"terrain", IronSim::DisplayName(Data->Terrain)}}).ToString());
		Lines.Add(IronUI::LocF("ui.strategy.tipTroops", "Troops: {troops}", {{"troops", IronUI::ToStd((bOwn ? IronStrategy::Num(Data->Troops) : IronStrategy::ApproxNum(Data->Troops)).ToString())}}).ToString());
		Lines.Add(IronUI::LocF("ui.strategy.tipDefense", "Defense: {value} / {max}", {{"value", IronSim::ToText(Data->Defense)}, {"max", IronSim::ToText(Data->DefenseMax)}}).ToString());
		if (bOwn)
		{
			Lines.Add(IronUI::LocF("ui.strategy.tipGoldFood", "Gold: {gold}   Food: {food}", {{"gold", IronUI::ToStd(IronStrategy::Num(Data->Gold).ToString())}, {"food", IronUI::ToStd(IronStrategy::Num(Data->Food).ToString())}}).ToString());
		}
		Lines.Add(IronUI::LocF("ui.strategy.tipOfficers", "Officers: {count}", {{"count", IronSim::ToText(static_cast<int>(GameState.CityOfficers(HoverCity).size()))}}).ToString());
		const int32 SectIndex = GameState.SectInCity(HoverCity);
		if (SectIndex >= 0)
		{
			Lines.Add(IronUI::LocF("ui.strategy.tipSect", "Sect: {sect}", {{"sect", IronUI::ToStd(IronStrategy::SectName(GameState, SectIndex).ToString())}}).ToString());
		}
	}

	if (Title.IsEmpty())
	{
		return Layer;
	}

	const FSlateFontInfo TitleFont = IronStyle::BodyBold(15.0f);
	const FSlateFontInfo LineFont = IronStyle::Body(13.0f);
	const FVector2f TitleSize = IronMapViewDetail::MeasureText(Title, TitleFont);
	TArray<FVector2f> LineSizes;
	float Width = TitleSize.X;
	float Height = TitleSize.Y + 4.0f;
	for (const FString& Line : Lines)
	{
		const FVector2f LineSize = IronMapViewDetail::MeasureText(Line, LineFont);
		LineSizes.Add(LineSize);
		Width = FMath::Max(Width, LineSize.X);
		Height += LineSize.Y + 1.0f;
	}
	const FVector2f BoxPadding(10.0f, 8.0f);
	const FVector2f BoxSize(Width + BoxPadding.X * 2.0f, Height + BoxPadding.Y * 2.0f);
	FVector2f BoxPos = HoverLocal + FVector2f(18.0f, 18.0f);
	if (BoxPos.X + BoxSize.X > Frame.ViewSize.X - 4.0f)
	{
		BoxPos.X = HoverLocal.X - BoxSize.X - 12.0f;
	}
	if (BoxPos.Y + BoxSize.Y > Frame.ViewSize.Y - 4.0f)
	{
		BoxPos.Y = HoverLocal.Y - BoxSize.Y - 12.0f;
	}
	BoxPos.X = FMath::Max(BoxPos.X, 4.0f);
	BoxPos.Y = FMath::Max(BoxPos.Y, 4.0f);

	IronMapViewDetail::AddRect(OutDrawElements, Layer, Geo, BoxPos, BoxSize, IronStyle::Night().CopyWithNewOpacity(0.93f));
	IronMapViewDetail::AddOutline(OutDrawElements, Layer + 1, Geo, BoxPos, BoxSize, IronStyle::Gold(), 1.5f);
	FVector2f TextPos = BoxPos + BoxPadding;
	IronMapViewDetail::AddText(OutDrawElements, Layer + 1, Geo, Title, TitleFont, TextPos, TitleSize, IronStyle::Gold());
	TextPos.Y += TitleSize.Y + 4.0f;
	for (int32 Index = 0; Index < Lines.Num(); ++Index)
	{
		IronMapViewDetail::AddText(OutDrawElements, Layer + 1, Geo, Lines[Index], LineFont, TextPos, LineSizes[Index], IronStyle::TextLight());
		TextPos.Y += LineSizes[Index].Y + 1.0f;
	}
	return Layer + 1;
}

FReply SIronMapView::OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	const FKey Pressed = MouseEvent.GetEffectingButton();
	if (Pressed != EKeys::LeftMouseButton && Pressed != EKeys::RightMouseButton)
	{
		return FReply::Unhandled();
	}
	LastViewSize = IronMapViewDetail::ToVec2f(MyGeometry.GetLocalSize());
	bMouseDown = true;
	bDragging = false;
	PressLocal = IronMapViewDetail::ToVec2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	LastMouseLocal = PressLocal;
	return FReply::Handled().CaptureMouse(SharedThis(this)).SetUserFocus(SharedThis(this), EFocusCause::Mouse);
}

FReply SIronMapView::OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (!bMouseDown)
	{
		return FReply::Unhandled();
	}
	const FVector2f Local = IronMapViewDetail::ToVec2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	const bool bWasDragging = bDragging;
	bMouseDown = false;
	bDragging = false;
	if (!bWasDragging && MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton && Session.IsValid() && Session->HasGame())
	{
		const int32 Clicked = HitTestCity(MakeFrame(LastViewSize), Local);
		if (Clicked >= 0)
		{
			OnCityClicked.ExecuteIfBound(Clicked);
		}
	}
	UpdateHover(Local);
	return FReply::Handled().ReleaseMouseCapture();
}

FReply SIronMapView::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	const FVector2f Local = IronMapViewDetail::ToVec2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	LastViewSize = IronMapViewDetail::ToVec2f(MyGeometry.GetLocalSize());
	if (bMouseDown && HasMouseCapture())
	{
		if (!bDragging && (Local - PressLocal).Size() > 4.0f)
		{
			bDragging = true;
			HoverCity = -1;
			HoverArmyId = -1;
		}
		if (bDragging)
		{
			const FMapFrame Frame = MakeFrame(LastViewSize);
			ViewCenter = Frame.Center - (Local - LastMouseLocal) / Frame.Scale;
			Zoom = Frame.Scale;
			ClampView(LastViewSize);
		}
		LastMouseLocal = Local;
		return FReply::Handled();
	}
	UpdateHover(Local);
	return FReply::Unhandled();
}

FReply SIronMapView::OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	const FVector2f Local = IronMapViewDetail::ToVec2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	LastViewSize = IronMapViewDetail::ToVec2f(MyGeometry.GetLocalSize());
	const float Wheel = MouseEvent.GetWheelDelta();
	if (FMath::IsNearlyZero(Wheel))
	{
		return FReply::Unhandled();
	}
	const FMapFrame Before = MakeFrame(LastViewSize);
	const FVector2f MapUnderCursor = Before.ToMap(Local);
	Zoom = FMath::Clamp(Before.Scale * (Wheel > 0.0f ? 1.15f : 1.0f / 1.15f), 0.5f, 2.5f);
	const FMapFrame After = MakeFrame(LastViewSize);
	ViewCenter = MapUnderCursor - (Local - LastViewSize * 0.5f) / After.Scale;
	ClampView(LastViewSize);
	UpdateHover(Local);
	return FReply::Handled();
}

void SIronMapView::OnMouseLeave(const FPointerEvent& MouseEvent)
{
	SLeafWidget::OnMouseLeave(MouseEvent);
	if (!bDragging)
	{
		HoverCity = -1;
		HoverArmyId = -1;
	}
}

FReply SIronMapView::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	const FKey Key = InKeyEvent.GetKey();
	const float Step = 120.0f / FMath::Max(Zoom, 0.1f);
	FVector2f Pan(0.0f, 0.0f);
	if (Key == EKeys::Left || Key == EKeys::A)
	{
		Pan.X = -Step;
	}
	else if (Key == EKeys::Right || Key == EKeys::D)
	{
		Pan.X = Step;
	}
	else if (Key == EKeys::Up || Key == EKeys::W)
	{
		Pan.Y = -Step;
	}
	else if (Key == EKeys::Down || Key == EKeys::S)
	{
		Pan.Y = Step;
	}
	else if (Key == EKeys::Add || Key == EKeys::Equals)
	{
		Zoom = FMath::Clamp(Zoom * 1.15f, 0.5f, 2.5f);
		ClampView(LastViewSize);
		return FReply::Handled();
	}
	else if (Key == EKeys::Subtract || Key == EKeys::Hyphen)
	{
		Zoom = FMath::Clamp(Zoom / 1.15f, 0.5f, 2.5f);
		ClampView(LastViewSize);
		return FReply::Handled();
	}
	else
	{
		return FReply::Unhandled();
	}
	ViewCenter += Pan;
	ClampView(LastViewSize);
	return FReply::Handled();
}

FCursorReply SIronMapView::OnCursorQuery(const FGeometry& MyGeometry, const FPointerEvent& CursorEvent) const
{
	if (bDragging)
	{
		return FCursorReply::Cursor(EMouseCursor::GrabHandClosed);
	}
	if (HoverCity >= 0)
	{
		return FCursorReply::Cursor(EMouseCursor::Hand);
	}
	return FCursorReply::Cursor(EMouseCursor::Default);
}
