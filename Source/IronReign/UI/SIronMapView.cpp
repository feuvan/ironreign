#include "UI/SIronMapView.h"

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "UI/SIronStrategyCommon.h"
#include "World/IronTerrain.h"
#include "World/IronWorldMap3D.h"
#include "World/IronWorldMath.h"

#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "Input/CursorReply.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Templates/Function.h"
#include "Widgets/SViewport.h"

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

	template <typename VectorType>
	FVector2D ToVec2d(const VectorType& Value)
	{
		return FVector2D(static_cast<double>(Value.X), static_cast<double>(Value.Y));
	}

	// ----- 3D map overlay -----
	/** Map labels fade in between these camera distances (metres): they name regions, useful zoomed out. */
	constexpr float WorldLabelFadeStartM = 700.0f;
	constexpr float WorldLabelFadeEndM = 1200.0f;
	/** Labels float this far above the ground (metres). */
	constexpr float WorldLabelLiftM = 40.0f;
	/** Garrison rows and the decorative Chinese names are shown up to these camera distances (metres). */
	constexpr float WorldTroopsMaxDistanceM = 2000.0f;
	constexpr float WorldZhMaxDistanceM = 1300.0f;
	/**
	 * March routes are draped over the ground in steps of this fraction of the camera distance (clamped, metres; each
	 * step is one projection), this far above it (metres).
	 */
	constexpr double WorldRouteStepPerDistance = 0.02;
	constexpr double WorldRouteMinStepM = 12.0;
	constexpr double WorldRouteMaxStepM = 60.0;
	constexpr float WorldRouteLiftM = 3.0f;
	/** A resting cursor re-picks what is under it this often (seconds) while the scene moves. */
	constexpr float WorldHoverRepickSeconds = 0.1f;
	/** Samples of the remaining part of the road an army is on (its route follows the road's bends). */
	constexpr int32 WorldCurrentRoadSamples = 24;
	/** Camera distance (metres) of a double-click fly-to, and the farthest distance CenterOnCity keeps. */
	constexpr float WorldFocusDistanceM = 650.0f;
	constexpr float WorldCenterMaxDistanceM = 1400.0f;
	/** Middle drag across the whole viewport width turns the camera by this much (degrees); Q/E turn by a step. */
	constexpr float WorldRotateDegreesPerWidth = 120.0f;
	constexpr float WorldRotateKeyDegrees = 15.0f;
	/** WASD / arrows pan by this fraction of the viewport. */
	constexpr double WorldPanKeyFraction = 0.1;
	/** The gold frame drawn around the overlay (the 2D map's gold border is transparent over the scene). */
	constexpr float WorldFrameThickness = 2.0f;

	/** A city plaque or army tag to paint over the 3D map: the city / army index and its anchor (local space). */
	struct FWorldAnchor
	{
		int32 Index = -1;
		FVector2f Anchor = FVector2f(0.0f, 0.0f);
	};

	/** Painted far to near (top to bottom of the view) so nearer plaques and tags cover farther ones. */
	void SortFarToNear(TArray<FWorldAnchor>& Anchors)
	{
		Anchors.Sort([](const FWorldAnchor& Lhs, const FWorldAnchor& Rhs) { return Lhs.Anchor.Y < Rhs.Anchor.Y; });
	}

	/** Plaque and tag text scale for a camera distance: 1.2 close up (250 m) .. 0.75 zoomed out (2600 m). */
	float WorldTextScale(float CameraDistanceM)
	{
		const float Alpha = FMath::Clamp((CameraDistanceM - 250.0f) / 2350.0f, 0.0f, 1.0f);
		return FMath::Lerp(1.2f, 0.75f, Alpha);
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

	/**
	 * Planned march of an army in map coordinates: its current position, the next city, the remaining stops and the
	 * target. bFollowCurrentRoad also samples the rest of the road the army is on (the 2D map draws that leg straight).
	 */
	void BuildMarchPath(const IronSim::FGameState& State, const IronSim::FArmy& Army, float Fraction, bool bFollowCurrentRoad, TArray<FVector2f>& OutMapPath)
	{
		OutMapPath.Reset();
		const IronSim::FPoint Start = State.ArmyPosition(Army, Fraction);
		OutMapPath.Add(FVector2f(Start.X, Start.Y));
		int32 From = Army.Node;
		if (Army.Next >= 0)
		{
			if (bFollowCurrentRoad && Army.Road >= 0)
			{
				const float RoadTenths = static_cast<float>(FMath::Max(1, State.RoadLength(Army.Road)));
				const float Travelled = static_cast<float>(Army.Progress) + FMath::Clamp(Fraction, 0.0f, 1.0f) * static_cast<float>(State.ArmySpeed(Army));
				const float StartT = FMath::Min(1.0f, Travelled / RoadTenths);
				for (int32 Step = 1; Step < WorldCurrentRoadSamples; ++Step)
				{
					const float T = FMath::Lerp(StartT, 1.0f, static_cast<float>(Step) / static_cast<float>(WorldCurrentRoadSamples));
					const IronSim::FPoint RoadSample = State.RoadPoint(Army.Road, Army.Node, T);
					OutMapPath.Add(FVector2f(RoadSample.X, RoadSample.Y));
				}
			}
			if (const IronSim::FCity* NextCity = IronStrategy::GetCity(State, Army.Next))
			{
				OutMapPath.Add(CityMapPos(*NextCity));
			}
			From = Army.Next;
		}
		for (const int Stop : Army.Route)
		{
			if (Stop == From)
			{
				continue;
			}
			AppendLeg(State, From, Stop, OutMapPath);
			From = Stop;
		}
		if (From != Army.Target)
		{
			AppendLeg(State, From, Army.Target, OutMapPath);
		}
	}

	FLinearColor MarchRouteColor(const IronSim::FArmy& Army)
	{
		const bool bReturning = Army.State == IronSim::EArmyState::Returning;
		return bReturning ? IronStyle::InkSoft().CopyWithNewOpacity(0.75f) : IronStyle::Lacquer().CopyWithNewOpacity(0.9f);
	}

	/** Arrow head at the end of a (local space) route. */
	void AddArrowHead(FSlateWindowElementList& Out, int32 Layer, const FGeometry& Geo, const TArray<FVector2f>& Path, const FLinearColor& Color, float DashScale)
	{
		if (Path.Num() < 2)
		{
			return;
		}
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
		if (Direction.IsNearlyZero())
		{
			return;
		}
		const FVector2f Side(-Direction.Y, Direction.X);
		const float HeadLength = 14.0f * DashScale;
		const float HeadWidth = 8.0f * DashScale;
		TArray<FVector2f> Head;
		Head.Add(Tip - Direction * HeadLength + Side * HeadWidth);
		Head.Add(Tip);
		Head.Add(Tip - Direction * HeadLength - Side * HeadWidth);
		AddPolyline(Out, Layer, Geo, MoveTemp(Head), Color, 3.5f);
	}
}

void SIronMapView::Construct(const FArguments& InArgs)
{
	Session = InArgs._Session;
	FractionalDayAttr = InArgs._FractionalDay;
	SelectedCityAttr = InArgs._SelectedCity;
	SelectedArmyAttr = InArgs._SelectedArmy;
	OnCityClicked = InArgs._OnCityClicked;
	OnArmyClicked = InArgs._OnArmyClicked;

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
		const int32 PartCount = AreaText.ParseIntoArrayWS(Parts);
		if (PartCount >= 4 && Parts.Num() >= 4)
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
	if (AIronWorldMap3D* Map = GetActiveWorldMap())
	{
		// Keep the zoom, but close enough to make the city out.
		Map->FocusCity(InCity, FMath::Min(Map->GetCameraDistanceM(), IronMapViewDetail::WorldCenterMaxDistanceM));
	}
}

void SIronMapView::SetView(const FVector2f& InCenter, float InZoom)
{
	ViewCenter = InCenter;
	Zoom = FMath::Clamp(InZoom, 0.5f, 2.5f);
	ClampView(LastViewSize);
}

void SIronMapView::SetWorldMap(AIronWorldMap3D* InWorldMap)
{
	if (WorldMap.Get() == InWorldMap)
	{
		return;
	}
	WorldMap = InWorldMap;
	// 2D and 3D hit tests differ: the hover starts afresh (a running drag simply continues in the other mode).
	HoverCity = -1;
	HoverArmyId = -1;
	OverlayHits.Reset();
}

bool SIronMapView::IsShowingWorldMap() const
{
	return GetActiveWorldMap() != nullptr;
}

AIronWorldMap3D* SIronMapView::GetActiveWorldMap() const
{
	AIronWorldMap3D* Map = WorldMap.Get();
	return (Map != nullptr && Map->IsMapActive()) ? Map : nullptr;
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

FVector2D SIronMapView::ComputeDesiredSize(float /*LayoutScaleMultiplier*/) const
{
	return FVector2D(800.0, 600.0);
}

int32 SIronMapView::OnPaint(const FPaintArgs& /*Args*/, const FGeometry& AllottedGeometry, const FSlateRect& /*MyCullingRect*/, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool /*bParentEnabled*/) const
{
	LastViewSize = IronMapViewDetail::ToVec2f(AllottedGeometry.GetLocalSize());
	if (const AIronWorldMap3D* Map = GetActiveWorldMap())
	{
		// The real-time scene is the map: only the Slate overlays are drawn, the rest stays transparent.
		return PaintWorldOverlay(*Map, AllottedGeometry, OutDrawElements, LayerId);
	}

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
	Layer = PaintTooltip(Frame.ViewSize, AllottedGeometry, OutDrawElements, Layer + 1);
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
		IronMapViewDetail::BuildMarchPath(GameState, Army, Fraction, false, MapPath);
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

		const FLinearColor RouteColor = IronMapViewDetail::MarchRouteColor(Army);
		IronMapViewDetail::EmitDashes(Path, 14.0f * DashScale, 6.0f * DashScale, [&](TArray<FVector2f>& DashPoints)
		{
			IronMapViewDetail::AddPolyline(OutDrawElements, Layer, Geo, DashPoints, RouteColor, 3.0f);
		});
		// Arrow head at the destination.
		IronMapViewDetail::AddArrowHead(OutDrawElements, Layer, Geo, Path, RouteColor, DashScale);
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

int32 SIronMapView::PaintTooltip(const FVector2f& ViewSize, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
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
	if (BoxPos.X + BoxSize.X > ViewSize.X - 4.0f)
	{
		BoxPos.X = HoverLocal.X - BoxSize.X - 12.0f;
	}
	if (BoxPos.Y + BoxSize.Y > ViewSize.Y - 4.0f)
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
	// Over the 3D map the middle button rotates the camera.
	const bool bRotateButton = Pressed == EKeys::MiddleMouseButton && GetActiveWorldMap() != nullptr;
	if (Pressed != EKeys::LeftMouseButton && Pressed != EKeys::RightMouseButton && !bRotateButton)
	{
		return FReply::Unhandled();
	}
	LastViewSize = IronMapViewDetail::ToVec2f(MyGeometry.GetLocalSize());
	bMouseDown = true;
	bDragging = false;
	PressButton = Pressed;
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
	if (GetActiveWorldMap() != nullptr)
	{
		// Pick at the release point (plaques and tags first, then the scene).
		UpdateWorldHover(MyGeometry, Local);
		if (!bWasDragging && MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton && Session.IsValid() && Session->HasGame())
		{
			// A click selects an army, a city, or (open ground) clears the army selection.
			if (HoverArmyId >= 0)
			{
				OnArmyClicked.ExecuteIfBound(HoverArmyId);
			}
			else if (HoverCity >= 0)
			{
				OnCityClicked.ExecuteIfBound(HoverCity);
			}
			else
			{
				OnArmyClicked.ExecuteIfBound(-1);
			}
		}
		return FReply::Handled().ReleaseMouseCapture();
	}
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

FReply SIronMapView::OnMouseButtonDoubleClick(const FGeometry& InMyGeometry, const FPointerEvent& InMouseEvent)
{
	AIronWorldMap3D* Map = GetActiveWorldMap();
	if (Map == nullptr || InMouseEvent.GetEffectingButton() != EKeys::LeftMouseButton || !Session.IsValid() || !Session->HasGame())
	{
		// The 2D map does not react to double clicks (unchanged).
		return SLeafWidget::OnMouseButtonDoubleClick(InMyGeometry, InMouseEvent);
	}
	// The first click already selected what is under the cursor; the double click flies the camera there.
	const FVector2f Local = IronMapViewDetail::ToVec2f(InMyGeometry.AbsoluteToLocal(InMouseEvent.GetScreenSpacePosition()));
	UpdateWorldHover(InMyGeometry, Local);
	const float CloseUpM = FMath::Min(Map->GetCameraDistanceM(), IronMapViewDetail::WorldFocusDistanceM);
	const IronSim::FGameState& GameState = Session->State();
	if (HoverArmyId >= 0)
	{
		if (const IronSim::FArmy* Army = GameState.FindArmy(HoverArmyId))
		{
			Map->FocusMapPoint(IronWorld::FromSim(GameState.ArmyPosition(*Army, FMath::Clamp(FractionalDayAttr.Get(), 0.0f, 1.0f))), CloseUpM);
		}
		return FReply::Handled();
	}
	if (HoverCity >= 0)
	{
		Map->FocusCity(HoverCity, CloseUpM);
		return FReply::Handled();
	}
	// Open ground: centre the view there, keeping the zoom.
	FViewportMapping Mapping;
	FVector2D GroundM = FVector2D::ZeroVector;
	if (MakeViewportMapping(*Map, Mapping) && Map->PickMapPoint(LocalToViewportPixel(Mapping, InMyGeometry, Local), GroundM))
	{
		Map->FocusMapPoint(GroundM, Map->GetCameraDistanceM());
	}
	return FReply::Handled();
}

FReply SIronMapView::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	const FVector2f Local = IronMapViewDetail::ToVec2f(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	LastViewSize = IronMapViewDetail::ToVec2f(MyGeometry.GetLocalSize());
	LastCursorAbsolute = IronMapViewDetail::ToVec2d(MouseEvent.GetScreenSpacePosition());
	bCursorInside = true;
	if (AIronWorldMap3D* Map = GetActiveWorldMap())
	{
		if (bMouseDown && HasMouseCapture())
		{
			if (!bDragging && (Local - PressLocal).Size() > 4.0f)
			{
				bDragging = true;
				HoverCity = -1;
				HoverArmyId = -1;
			}
			FViewportMapping Mapping;
			if (bDragging && MakeViewportMapping(*Map, Mapping))
			{
				const FVector2D FromPixel = LocalToViewportPixel(Mapping, MyGeometry, LastMouseLocal);
				const FVector2D ToPixel = LocalToViewportPixel(Mapping, MyGeometry, Local);
				if (PressButton == EKeys::MiddleMouseButton)
				{
					// The scene turns with the cursor (dragging right turns the view left).
					Map->Rotate(-static_cast<float>((ToPixel.X - FromPixel.X) / Mapping.ViewportPixels.X) * IronMapViewDetail::WorldRotateDegreesPerWidth);
				}
				else
				{
					// The ground under the cursor follows it.
					Map->Pan(ToPixel - FromPixel, Mapping.ViewportPixels);
				}
			}
			LastMouseLocal = Local;
			return FReply::Handled();
		}
		UpdateWorldHover(MyGeometry, Local);
		return FReply::Unhandled();
	}
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
	if (AIronWorldMap3D* Map = GetActiveWorldMap())
	{
		// Notches (fractional on trackpads), toward the ground under the cursor.
		FViewportMapping Mapping;
		if (MakeViewportMapping(*Map, Mapping))
		{
			Map->Zoom(Wheel, LocalToViewportPixel(Mapping, MyGeometry, Local));
		}
		UpdateWorldHover(MyGeometry, Local);
		return FReply::Handled();
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
	bCursorInside = false;
	if (!bDragging)
	{
		HoverCity = -1;
		HoverArmyId = -1;
	}
}

void SIronMapView::OnMouseCaptureLost(const FCaptureLostEvent& CaptureLostEvent)
{
	SLeafWidget::OnMouseCaptureLost(CaptureLostEvent);
	// Capture taken away mid-drag (a modal opened, the window lost focus): the next move must not keep panning.
	bMouseDown = false;
	bDragging = false;
}

FReply SIronMapView::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	const FKey Key = InKeyEvent.GetKey();
	if (AIronWorldMap3D* Map = GetActiveWorldMap())
	{
		return HandleWorldKey(*Map, MyGeometry, Key);
	}
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

FCursorReply SIronMapView::OnCursorQuery(const FGeometry& /*MyGeometry*/, const FPointerEvent& /*CursorEvent*/) const
{
	if (bDragging)
	{
		return FCursorReply::Cursor(EMouseCursor::GrabHandClosed);
	}
	// Armies are only clickable on the 3D map.
	if (HoverCity >= 0 || (HoverArmyId >= 0 && GetActiveWorldMap() != nullptr))
	{
		return FCursorReply::Cursor(EMouseCursor::Hand);
	}
	return FCursorReply::Cursor(EMouseCursor::Default);
}

// -------------------------------------------------------------------------------------------------
// 3D map overlay
// -------------------------------------------------------------------------------------------------

void SIronMapView::Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime)
{
	SLeafWidget::Tick(AllottedGeometry, InCurrentTime, InDeltaTime);
	AIronWorldMap3D* Map = GetActiveWorldMap();
	if (Map == nullptr)
	{
		return;
	}
	// The scene moves under a resting cursor (camera flights, marching armies): pick again now and then.
	HoverRepickSeconds += InDeltaTime;
	if (bCursorInside && !bDragging && HoverRepickSeconds >= IronMapViewDetail::WorldHoverRepickSeconds)
	{
		HoverRepickSeconds = 0.0f;
		UpdateWorldHover(AllottedGeometry, IronMapViewDetail::ToVec2f(AllottedGeometry.AbsoluteToLocal(LastCursorAbsolute)));
	}
	PushWorldHighlights(*Map);
}

bool SIronMapView::MakeViewportMapping(const AIronWorldMap3D& Map, FViewportMapping& OutMapping, bool bPaintSpace) const
{
	UWorld* MapWorld = Map.GetWorld();
	UGameViewportClient* ViewportClient = MapWorld != nullptr ? MapWorld->GetGameViewport() : nullptr;
	if (ViewportClient == nullptr)
	{
		return false;
	}
	const TSharedPtr<SViewport> ViewportWidget = ViewportClient->GetGameViewportWidget();
	if (!ViewportWidget.IsValid())
	{
		return false;
	}
	// Render target size of the game viewport (physical pixels on Retina / high-DPI displays).
	FVector2D PixelSize = FVector2D::ZeroVector;
	ViewportClient->GetViewportSize(PixelSize);
	// The viewport widget's geometry in the same absolute space as the geometry the mapping is used with. Tick and
	// input events give desktop space (tick space); OnPaint gives window space (paint space). The SViewport is an
	// ancestor of this widget, so its paint-space geometry was stored earlier in the same frame.
	const FGeometry& WidgetGeometry = bPaintSpace ? ViewportWidget->GetPaintSpaceGeometry() : ViewportWidget->GetTickSpaceGeometry();
	const FVector2D WidgetLocalSize = IronMapViewDetail::ToVec2d(WidgetGeometry.GetLocalSize());
	if (PixelSize.X < 1.0 || PixelSize.Y < 1.0 || WidgetLocalSize.X < 1.0 || WidgetLocalSize.Y < 1.0)
	{
		return false;
	}
	OutMapping.ViewportGeometry = WidgetGeometry;
	OutMapping.ViewportLocalSize = WidgetLocalSize;
	OutMapping.ViewportPixels = PixelSize;
	return true;
}

FVector2D SIronMapView::LocalToViewportPixel(const FViewportMapping& Mapping, const FGeometry& Geometry, const FVector2f& LocalPos)
{
	// Local -> absolute (desktop, or window when painting) -> local of the viewport widget -> normalized -> render pixels.
	const FVector2D Absolute = IronMapViewDetail::ToVec2d(Geometry.LocalToAbsolute(LocalPos));
	const FVector2D ViewportLocal = IronMapViewDetail::ToVec2d(Mapping.ViewportGeometry.AbsoluteToLocal(Absolute));
	return ViewportLocal / Mapping.ViewportLocalSize * Mapping.ViewportPixels;
}

FVector2f SIronMapView::ViewportPixelToLocal(const FViewportMapping& Mapping, const FGeometry& Geometry, const FVector2D& Pixel)
{
	const FVector2D ViewportLocal = Pixel / Mapping.ViewportPixels * Mapping.ViewportLocalSize;
	const FVector2D Absolute = IronMapViewDetail::ToVec2d(Mapping.ViewportGeometry.LocalToAbsolute(ViewportLocal));
	return IronMapViewDetail::ToVec2f(Geometry.AbsoluteToLocal(Absolute));
}

bool SIronMapView::ProjectToLocal(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geometry, const FVector2D& MapPointM, float HeightAboveSurfaceM, FVector2f& OutLocal)
{
	const AIronTerrain* Terrain = Map.GetTerrain();
	const float SurfaceM = Terrain != nullptr ? Terrain->SampleSurface(MapPointM) : 0.0f;
	FVector2D Pixel = FVector2D::ZeroVector;
	if (!Map.ProjectToViewport(MapPointM, SurfaceM + HeightAboveSurfaceM, Pixel))
	{
		return false;
	}
	OutLocal = ViewportPixelToLocal(Mapping, Geometry, Pixel);
	return true;
}

void SIronMapView::UpdateWorldHover(const FGeometry& Geometry, const FVector2f& LocalPos)
{
	HoverLocal = LocalPos;
	HoverCity = -1;
	HoverArmyId = -1;
	AIronWorldMap3D* Map = GetActiveWorldMap();
	if (Map == nullptr || !Session.IsValid() || !Session->HasGame())
	{
		return;
	}
	// Plaques and troop tags first, topmost (last painted) first: they float above the models they name.
	for (int32 Index = OverlayHits.Num() - 1; Index >= 0; --Index)
	{
		const FOverlayHit& Hit = OverlayHits[Index];
		if (LocalPos.X >= Hit.Min.X && LocalPos.X <= Hit.Max.X && LocalPos.Y >= Hit.Min.Y && LocalPos.Y <= Hit.Max.Y)
		{
			HoverCity = Hit.City;
			HoverArmyId = Hit.ArmyId;
			return;
		}
	}
	// Then the scene: cities before armies (an army camps right beside its city; its tag selects it).
	FViewportMapping Mapping;
	if (!MakeViewportMapping(*Map, Mapping))
	{
		return;
	}
	const FVector2D Pixel = LocalToViewportPixel(Mapping, Geometry, LocalPos);
	HoverCity = Map->PickCity(Pixel);
	if (HoverCity < 0)
	{
		HoverArmyId = Map->PickArmy(Pixel);
	}
}

void SIronMapView::PushWorldHighlights(AIronWorldMap3D& Map) const
{
	Map.SetHoveredCity(HoverCity);
	Map.SetSelectedCity(SelectedCityAttr.Get());
	Map.SetSelectedArmy(SelectedArmyAttr.Get());
}

FReply SIronMapView::HandleWorldKey(AIronWorldMap3D& Map, const FGeometry& Geometry, const FKey& Key)
{
	FViewportMapping Mapping;
	if (!MakeViewportMapping(Map, Mapping))
	{
		return FReply::Unhandled();
	}
	if (Key == EKeys::Q || Key == EKeys::E)
	{
		Map.Rotate(Key == EKeys::Q ? -IronMapViewDetail::WorldRotateKeyDegrees : IronMapViewDetail::WorldRotateKeyDegrees);
		return FReply::Handled();
	}
	if (Key == EKeys::Add || Key == EKeys::Equals || Key == EKeys::Subtract || Key == EKeys::Hyphen)
	{
		// Toward the middle of the visible map.
		const bool bZoomIn = Key == EKeys::Add || Key == EKeys::Equals;
		Map.Zoom(bZoomIn ? 1.0f : -1.0f, LocalToViewportPixel(Mapping, Geometry, LastViewSize * 0.5f));
		return FReply::Handled();
	}
	// Pan moves the ground like a drag: the view goes left when the ground moves right.
	const FVector2D Step = Mapping.ViewportPixels * IronMapViewDetail::WorldPanKeyFraction;
	FVector2D Delta = FVector2D::ZeroVector;
	if (Key == EKeys::Left || Key == EKeys::A)
	{
		Delta.X = Step.X;
	}
	else if (Key == EKeys::Right || Key == EKeys::D)
	{
		Delta.X = -Step.X;
	}
	else if (Key == EKeys::Up || Key == EKeys::W)
	{
		Delta.Y = Step.Y;
	}
	else if (Key == EKeys::Down || Key == EKeys::S)
	{
		Delta.Y = -Step.Y;
	}
	else
	{
		return FReply::Unhandled();
	}
	Map.Pan(Delta, Mapping.ViewportPixels);
	return FReply::Handled();
}

int32 SIronMapView::PaintWorldOverlay(const AIronWorldMap3D& Map, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 LayerId) const
{
	OverlayHits.Reset();
	int32 Layer = LayerId;
	FViewportMapping Mapping;
	if (Session.IsValid() && Session->HasGame() && MakeViewportMapping(Map, Mapping, true))
	{
		const float Fraction = FMath::Clamp(FractionalDayAttr.Get(), 0.0f, 1.0f);
		Layer = PaintWorldLabels(Map, Mapping, Geo, OutDrawElements, Layer + 1);
		Layer = PaintWorldRoutes(Map, Mapping, Geo, OutDrawElements, Layer + 1, Fraction);
		Layer = PaintWorldCities(Map, Mapping, Geo, OutDrawElements, Layer + 1);
		Layer = PaintWorldArmies(Map, Mapping, Geo, OutDrawElements, Layer + 1);
		Layer = PaintTooltip(LastViewSize, Geo, OutDrawElements, Layer + 1);
	}

	// The gold frame of the 2D map, drawn inside the overlay (the border around it is transparent over the scene).
	++Layer;
	const FLinearColor FrameColor = IronStyle::Gold().CopyWithNewOpacity(0.8f);
	const float Edge = IronMapViewDetail::WorldFrameThickness;
	const FVector2f OverlaySize(FMath::Max(LastViewSize.X, Edge * 2.0f), FMath::Max(LastViewSize.Y, Edge * 2.0f));
	IronMapViewDetail::AddRect(OutDrawElements, Layer, Geo, FVector2f(0.0f, 0.0f), FVector2f(OverlaySize.X, Edge), FrameColor);
	IronMapViewDetail::AddRect(OutDrawElements, Layer, Geo, FVector2f(0.0f, OverlaySize.Y - Edge), FVector2f(OverlaySize.X, Edge), FrameColor);
	IronMapViewDetail::AddRect(OutDrawElements, Layer, Geo, FVector2f(0.0f, Edge), FVector2f(Edge, OverlaySize.Y - Edge * 2.0f), FrameColor);
	IronMapViewDetail::AddRect(OutDrawElements, Layer, Geo, FVector2f(OverlaySize.X - Edge, Edge), FVector2f(Edge, OverlaySize.Y - Edge * 2.0f), FrameColor);
	return Layer;
}

int32 SIronMapView::PaintWorldLabels(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	// Region names help when zoomed out; close up the terrain speaks for itself.
	const float DistanceM = Map.GetCameraDistanceM();
	const float Alpha = FMath::Clamp((DistanceM - IronMapViewDetail::WorldLabelFadeStartM) / (IronMapViewDetail::WorldLabelFadeEndM - IronMapViewDetail::WorldLabelFadeStartM), 0.0f, 1.0f);
	if (Alpha <= 0.01f)
	{
		return Layer;
	}
	const IronSim::FGameState& GameState = Session->State();
	const float SizeScale = FMath::Clamp(1300.0f / FMath::Max(DistanceM, 1.0f), 0.5f, 1.0f);
	const FLinearColor TextColor = IronStyle::Paper().CopyWithNewOpacity(0.9f * Alpha);
	const FLinearColor ShadowColor = IronStyle::Ink().CopyWithNewOpacity(0.6f * Alpha);
	for (int32 Index = 0; Index < static_cast<int32>(GameState.Map.Labels.size()); ++Index)
	{
		const IronSim::FMapLabel& Label = GameState.Map.Labels[static_cast<size_t>(Index)];
		FVector2f LabelCenter(0.0f, 0.0f);
		if (!ProjectToLocal(Map, Mapping, Geo, IronWorld::FromSim(Label.Position), IronMapViewDetail::WorldLabelLiftM, LabelCenter))
		{
			continue;
		}
		const FString LabelText = IronUI::ToFString(IronSim::MapLabelOf(GameState, Index));
		FSlateFontInfo LabelFont = IronStyle::Heading(FMath::Max(9.0f, 22.0f * Label.Size * SizeScale));
		LabelFont.LetterSpacing = 180;
		const FVector2f TextSize = IronMapViewDetail::MeasureText(LabelText, LabelFont);
		const FVector2f TopLeft = LabelCenter - TextSize * 0.5f;
		if (TopLeft.X + TextSize.X < 0.0f || TopLeft.Y + TextSize.Y < 0.0f || TopLeft.X > LastViewSize.X || TopLeft.Y > LastViewSize.Y)
		{
			continue;
		}
		IronMapViewDetail::AddText(OutDrawElements, Layer, Geo, LabelText, LabelFont, TopLeft + FVector2f(1.5f, 1.5f), TextSize, ShadowColor);
		IronMapViewDetail::AddText(OutDrawElements, Layer + 1, Geo, LabelText, LabelFont, TopLeft, TextSize, TextColor);
	}
	return Layer + 1;
}

int32 SIronMapView::PaintWorldRoutes(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer, float Fraction) const
{
	const IronSim::FGameState& GameState = Session->State();
	if (GameState.PlayerFaction < 0)
	{
		return Layer;
	}
	const double StepM = FMath::Clamp(static_cast<double>(Map.GetCameraDistanceM()) * IronMapViewDetail::WorldRouteStepPerDistance, IronMapViewDetail::WorldRouteMinStepM, IronMapViewDetail::WorldRouteMaxStepM);
	TArray<FVector2f> MapPath;
	TArray<FVector2f> Run;
	for (const IronSim::FArmy& Army : GameState.Armies)
	{
		if (Army.Faction != GameState.PlayerFaction || Army.Target < 0 || Army.Units.empty())
		{
			continue;
		}
		IronMapViewDetail::BuildMarchPath(GameState, Army, Fraction, true, MapPath);
		if (MapPath.Num() < 2)
		{
			continue;
		}
		const FLinearColor RouteColor = IronMapViewDetail::MarchRouteColor(Army);
		const auto EmitRun = [&]()
		{
			if (Run.Num() >= 2)
			{
				IronMapViewDetail::EmitDashes(Run, 14.0f, 6.0f, [&](TArray<FVector2f>& DashPoints)
				{
					IronMapViewDetail::AddPolyline(OutDrawElements, Layer, Geo, DashPoints, RouteColor, 3.0f);
				});
			}
		};

		// Draped over the ground: a point every StepM metres, projected one by one. A stretch that cannot be projected
		// (behind the camera) ends the current run of dashes.
		Run.Reset();
		bool bTipShown = false;
		for (int32 Index = 1; Index < MapPath.Num(); ++Index)
		{
			const FVector2D SegmentStart = IronMapViewDetail::ToVec2d(MapPath[Index - 1]);
			const FVector2D SegmentEnd = IronMapViewDetail::ToVec2d(MapPath[Index]);
			const int32 Steps = FMath::Max(1, FMath::CeilToInt32(FVector2D::Distance(SegmentStart, SegmentEnd) / StepM));
			for (int32 Step = Index == 1 ? 0 : 1; Step <= Steps; ++Step)
			{
				const FVector2D RoutePoint = FMath::Lerp(SegmentStart, SegmentEnd, static_cast<double>(Step) / static_cast<double>(Steps));
				FVector2f RouteLocal(0.0f, 0.0f);
				bTipShown = ProjectToLocal(Map, Mapping, Geo, RoutePoint, IronMapViewDetail::WorldRouteLiftM, RouteLocal);
				if (bTipShown)
				{
					Run.Add(RouteLocal);
				}
				else
				{
					EmitRun();
					Run.Reset();
				}
			}
		}
		EmitRun();
		if (bTipShown)
		{
			IronMapViewDetail::AddArrowHead(OutDrawElements, Layer, Geo, Run, RouteColor, 1.0f);
		}
	}
	return Layer;
}

int32 SIronMapView::PaintWorldCities(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	const IronSim::FGameState& GameState = Session->State();
	FIronAssets& Assets = FIronAssets::Get();
	const int32 Selected = SelectedCityAttr.Get();
	const float DistanceM = Map.GetCameraDistanceM();
	const float TextScale = IronMapViewDetail::WorldTextScale(DistanceM);
	const bool bShowZh = IronStrategy::IsEnglishCulture() && DistanceM <= IronMapViewDetail::WorldZhMaxDistanceM;
	const bool bShowTroops = DistanceM <= IronMapViewDetail::WorldTroopsMaxDistanceM;
	const FSlateFontInfo NameFont = IronStyle::BodyBold(13.0f * TextScale);
	const FSlateFontInfo ZhFont = IronStyle::Brush(15.0f * TextScale);
	const FSlateFontInfo SmallFont = IronStyle::Body(11.5f * TextScale);
	const FSlateBrush* TroopIcon = Assets.Icon(TEXT("Troops"));

	// Anchors just above the city models.
	TArray<IronMapViewDetail::FWorldAnchor> Anchors;
	for (int32 Index = 0; Index < static_cast<int32>(GameState.Cities.size()); ++Index)
	{
		FVector2D Pixel = FVector2D::ZeroVector;
		if (!Map.ProjectCityLabel(Index, Pixel))
		{
			continue;
		}
		const FVector2f Anchor = ViewportPixelToLocal(Mapping, Geo, Pixel);
		if (Anchor.X < -200.0f || Anchor.Y < -20.0f || Anchor.X > LastViewSize.X + 200.0f || Anchor.Y > LastViewSize.Y + 120.0f)
		{
			continue;
		}
		Anchors.Add(IronMapViewDetail::FWorldAnchor{Index, Anchor});
	}
	IronMapViewDetail::SortFarToNear(Anchors);

	int32 CityLayer = Layer;
	for (const IronMapViewDetail::FWorldAnchor& Entry : Anchors)
	{
		const IronSim::FCity& Data = GameState.Cities[static_cast<size_t>(Entry.Index)];
		const bool bSelected = Entry.Index == Selected;
		const bool bHovered = Entry.Index == HoverCity;
		const FLinearColor OwnerColor = IronStyle::FactionColor(Data.Owner);

		// Name plaque (as on the 2D map), with the garrison below it; the whole block stands on the anchor.
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

		FString TroopText;
		FVector2f TroopSize(0.0f, 0.0f);
		float RowWidth = 0.0f;
		if (bShowTroops)
		{
			const bool bOwn = GameState.PlayerFaction >= 0 && Data.Owner == GameState.PlayerFaction;
			TroopText = (bOwn ? IronStrategy::Num(Data.Troops) : IronStrategy::ApproxNum(Data.Troops)).ToString();
			TroopSize = IronMapViewDetail::MeasureText(TroopText, SmallFont);
			RowWidth = TroopSize.Y + 3.0f + TroopSize.X;
		}
		const float RowH = bShowTroops ? TroopSize.Y + 1.0f : 0.0f;
		const FVector2f PlaquePos(Entry.Anchor.X - PlaqueW * 0.5f, Entry.Anchor.Y - PlaqueH - RowH - 2.0f);

		const FLinearColor PlaqueColor = bSelected ? IronStyle::Lacquer().CopyWithNewOpacity(0.92f) : IronStyle::Night().CopyWithNewOpacity(bHovered ? 0.92f : 0.8f);
		IronMapViewDetail::AddRect(OutDrawElements, CityLayer, Geo, PlaquePos, FVector2f(PlaqueW, PlaqueH), PlaqueColor);
		IronMapViewDetail::AddRect(OutDrawElements, CityLayer, Geo, FVector2f(PlaquePos.X, PlaquePos.Y + PlaqueH - 2.5f), FVector2f(PlaqueW, 2.5f), OwnerColor);
		IronMapViewDetail::AddText(OutDrawElements, CityLayer + 1, Geo, CityLabel, NameFont, FVector2f(PlaquePos.X + PadX, PlaquePos.Y + (PlaqueH - NameSize.Y) * 0.5f - 1.0f), NameSize, IronStyle::TextLight());
		if (!ZhLabel.IsEmpty())
		{
			IronMapViewDetail::AddText(OutDrawElements, CityLayer + 1, Geo, ZhLabel, ZhFont, FVector2f(PlaquePos.X + PadX * 2.0f + NameSize.X, PlaquePos.Y + (PlaqueH - ZhSize.Y) * 0.5f - 1.0f), ZhSize, IronStyle::Gold());
		}
		if (bHovered && !bSelected)
		{
			IronMapViewDetail::AddOutline(OutDrawElements, CityLayer + 1, Geo, PlaquePos, FVector2f(PlaqueW, PlaqueH), IronStyle::Gold().CopyWithNewOpacity(0.9f), 1.5f);
		}
		if (bShowTroops)
		{
			const float TroopIconSize = TroopSize.Y;
			const FVector2f RowPos(Entry.Anchor.X - RowWidth * 0.5f, PlaquePos.Y + PlaqueH + 1.0f);
			IronMapViewDetail::AddRect(OutDrawElements, CityLayer, Geo, RowPos - FVector2f(4.0f, 0.0f), FVector2f(RowWidth + 8.0f, TroopSize.Y), IronStyle::Night().CopyWithNewOpacity(0.55f));
			IronMapViewDetail::AddImage(OutDrawElements, CityLayer + 1, Geo, TroopIcon, RowPos, FVector2f(TroopIconSize, TroopIconSize), FLinearColor::White);
			IronMapViewDetail::AddText(OutDrawElements, CityLayer + 1, Geo, TroopText, SmallFont, FVector2f(RowPos.X + TroopIconSize + 3.0f, RowPos.Y), TroopSize, IronStyle::Paper());
		}

		const float HitWidth = FMath::Max(PlaqueW, RowWidth + 8.0f);
		FOverlayHit& Hit = OverlayHits.AddDefaulted_GetRef();
		Hit.City = Entry.Index;
		Hit.Min = FVector2f(Entry.Anchor.X - HitWidth * 0.5f, PlaquePos.Y);
		Hit.Max = FVector2f(Entry.Anchor.X + HitWidth * 0.5f, PlaquePos.Y + PlaqueH + RowH);
		CityLayer += 2;
	}
	return CityLayer;
}

int32 SIronMapView::PaintWorldArmies(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const
{
	const IronSim::FGameState& GameState = Session->State();
	const int32 SelectedArmy = SelectedArmyAttr.Get();
	const float TextScale = IronMapViewDetail::WorldTextScale(Map.GetCameraDistanceM());
	const FSlateFontInfo GlyphFont = IronStyle::Brush(14.0f * TextScale);
	const FSlateFontInfo CountFont = IronStyle::BodyBold(11.0f * TextScale);

	// Tags just above the banners (the 3D banner cloth has no glyph).
	TArray<IronMapViewDetail::FWorldAnchor> Anchors;
	for (int32 Index = 0; Index < static_cast<int32>(GameState.Armies.size()); ++Index)
	{
		const IronSim::FArmy& Army = GameState.Armies[static_cast<size_t>(Index)];
		FVector2D Pixel = FVector2D::ZeroVector;
		if (Army.Units.empty() || !Map.ProjectArmyLabel(Army.Id, Pixel))
		{
			continue;
		}
		const FVector2f Anchor = ViewportPixelToLocal(Mapping, Geo, Pixel);
		if (Anchor.X < -120.0f || Anchor.Y < -10.0f || Anchor.X > LastViewSize.X + 120.0f || Anchor.Y > LastViewSize.Y + 60.0f)
		{
			continue;
		}
		Anchors.Add(IronMapViewDetail::FWorldAnchor{Index, Anchor});
	}
	IronMapViewDetail::SortFarToNear(Anchors);

	int32 ArmyLayer = Layer;
	for (const IronMapViewDetail::FWorldAnchor& Entry : Anchors)
	{
		const IronSim::FArmy& Army = GameState.Armies[static_cast<size_t>(Entry.Index)];
		const bool bOwn = GameState.PlayerFaction >= 0 && Army.Faction == GameState.PlayerFaction;
		const FLinearColor Tint = IronStyle::FactionColor(Army.Faction);
		const FString Glyph = IronStrategy::FactionGlyph(GameState, Army.Faction);
		const int32 Troops = Army.TotalTroops();
		const FString CountText = (bOwn ? IronStrategy::Num(Troops) : IronStrategy::ApproxNum(Troops)).ToString();
		const FVector2f CountSize = IronMapViewDetail::MeasureText(CountText, CountFont);
		const FVector2f GlyphSize = Glyph.IsEmpty() ? FVector2f(0.0f, 0.0f) : IronMapViewDetail::MeasureText(Glyph, GlyphFont);
		const float TagH = FMath::Max(CountSize.Y, GlyphSize.Y) + 2.0f;
		const float GlyphBoxW = Glyph.IsEmpty() ? 0.0f : TagH;
		const float TagW = GlyphBoxW + CountSize.X + 10.0f;
		const FVector2f TagPos(Entry.Anchor.X - TagW * 0.5f, Entry.Anchor.Y - TagH - 2.0f);

		// Faction-tinted tag: the glyph on the full colour, the troop count on a darker shade (as on the 2D banners).
		IronMapViewDetail::AddRect(OutDrawElements, ArmyLayer, Geo, TagPos, FVector2f(TagW, TagH), Tint * FLinearColor(0.45f, 0.45f, 0.45f, 0.9f));
		if (GlyphBoxW > 0.0f)
		{
			IronMapViewDetail::AddRect(OutDrawElements, ArmyLayer, Geo, TagPos, FVector2f(GlyphBoxW, TagH), Tint);
			IronMapViewDetail::AddText(OutDrawElements, ArmyLayer + 1, Geo, Glyph, GlyphFont, TagPos + (FVector2f(GlyphBoxW, TagH) - GlyphSize) * 0.5f, GlyphSize, IronStyle::Paper());
		}
		IronMapViewDetail::AddText(OutDrawElements, ArmyLayer + 1, Geo, CountText, CountFont, FVector2f(TagPos.X + GlyphBoxW + 5.0f, TagPos.Y + (TagH - CountSize.Y) * 0.5f), CountSize, IronStyle::Paper());
		if (Army.Id == SelectedArmy)
		{
			IronMapViewDetail::AddOutline(OutDrawElements, ArmyLayer + 1, Geo, TagPos - FVector2f(2.0f, 2.0f), FVector2f(TagW + 4.0f, TagH + 4.0f), IronStyle::Gold(), 2.0f);
		}
		else if (Army.Id == HoverArmyId)
		{
			IronMapViewDetail::AddOutline(OutDrawElements, ArmyLayer + 1, Geo, TagPos - FVector2f(1.0f, 1.0f), FVector2f(TagW + 2.0f, TagH + 2.0f), IronStyle::Paper().CopyWithNewOpacity(0.9f), 1.5f);
		}

		FOverlayHit& Hit = OverlayHits.AddDefaulted_GetRef();
		Hit.ArmyId = Army.Id;
		Hit.Min = TagPos;
		Hit.Max = TagPos + FVector2f(TagW, TagH);
		ArmyLayer += 2;
	}
	return ArmyLayer;
}
