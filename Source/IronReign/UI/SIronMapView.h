#pragma once

#include "CoreMinimal.h"
#include "InputCoreTypes.h"
#include "Layout/Geometry.h"
#include "UObject/WeakObjectPtr.h"
#include "UObject/WeakObjectPtrTemplates.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SLeafWidget.h"

class AIronWorldMap3D;
class FIronSession;

DECLARE_DELEGATE_OneParam(FOnIronMapCityClicked, int32 /*City*/);
/** An army was clicked on the 3D map (FArmy::Id), or open ground (-1: clear the army selection). */
DECLARE_DELEGATE_OneParam(FOnIronMapArmyClicked, int32 /*ArmyId*/);

/**
 * The painted campaign map: world image, roads, labels, cities with pennants and name plaques, sect markers,
 * marching army banners (interpolated between day ticks), planned march arrows and hover tooltips.
 * Pan by dragging with the left or right mouse button, zoom with the wheel (0.5x..2.5x, the map always fills the view).
 * All hit testing happens in map coordinates (pixels of the map image).
 *
 * Over the real-time 3D map (SetWorldMap with an active AIronWorldMap3D, docs/DESIGN.md section 12) the widget is a
 * transparent overlay instead: the 3D scene draws the terrain, roads, cities and armies; this widget paints only Slate
 * overlays projected from the scene (map labels, planned march routes, city name plaques with owner colour and
 * garrison, army troop tags, the hover tooltip and a thin frame) and forwards input to the map: left/right drag pans,
 * the wheel zooms toward the cursor, middle drag and Q/E rotate, WASD/arrows pan, +/- zoom, a click selects an army
 * or a city (plaques and tags first, then AIronWorldMap3D::PickCity / PickArmy), a double click flies to it.
 * Slate local coordinates and game viewport pixels are converted through the game viewport widget's geometry (see
 * FViewportMapping), so DPI scaling and Retina backing scales are handled.
 */
class IRONREIGN_API SIronMapView : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SIronMapView)
		: _FractionalDay(0.0f)
		, _SelectedCity(-1)
		, _SelectedArmy(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		/** 0..1 progress toward the next day tick, used to interpolate marching armies. */
		SLATE_ATTRIBUTE(float, FractionalDay)
		SLATE_ATTRIBUTE(int32, SelectedCity)
		/** FArmy::Id of the selected army (3D map only), -1 for none. */
		SLATE_ATTRIBUTE(int32, SelectedArmy)
		SLATE_EVENT(FOnIronMapCityClicked, OnCityClicked)
		SLATE_EVENT(FOnIronMapArmyClicked, OnArmyClicked)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** Centers the view on a city, keeping the zoom (the 3D camera flies there). */
	void CenterOnCity(int32 InCity);
	FVector2f GetViewCenter() const { return ViewCenter; }
	float GetZoom() const { return Zoom; }
	void SetView(const FVector2f& InCenter, float InZoom);

	/**
	 * The 3D map to present, nullptr for the painted 2D map. Set every frame by the strategy screen: only an active map
	 * (AIronWorldMap3D::IsMapActive) turns this widget into the overlay.
	 */
	void SetWorldMap(AIronWorldMap3D* InWorldMap);
	/** True while the widget is the overlay of an active 3D map. */
	bool IsShowingWorldMap() const;
	/** City under the cursor (-1 if none). */
	int32 GetHoveredCity() const { return HoverCity; }

	// SWidget interface
	virtual void Tick(const FGeometry& AllottedGeometry, const double InCurrentTime, const float InDeltaTime) override;
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonDoubleClick(const FGeometry& InMyGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual void OnMouseLeave(const FPointerEvent& MouseEvent) override;
	virtual void OnMouseCaptureLost(const FCaptureLostEvent& CaptureLostEvent) override;
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual FCursorReply OnCursorQuery(const FGeometry& MyGeometry, const FPointerEvent& CursorEvent) const override;
	virtual bool SupportsKeyboardFocus() const override { return true; }

private:
	/** Effective (clamped) view for a given widget size. */
	struct FMapFrame
	{
		FVector2f ViewSize = FVector2f(1.0f, 1.0f);
		FVector2f Center = FVector2f(0.0f, 0.0f);
		float Scale = 1.0f;

		FVector2f ToLocal(const FVector2f& MapPos) const { return (MapPos - Center) * Scale + ViewSize * 0.5f; }
		FVector2f ToMap(const FVector2f& LocalPos) const { return (LocalPos - ViewSize * 0.5f) / Scale + Center; }
	};

	/** Where an army banner is drawn this frame (stacked armies are spread sideways). */
	struct FArmyPlacement
	{
		int32 ArmyId = -1;
		int32 Faction = -1;
		int32 Troops = 0;
		FVector2f Local = FVector2f(0.0f, 0.0f);
	};

	/**
	 * Game viewport pixels (APlayerController::ProjectWorldLocationToScreen / DeprojectScreenPositionToWorld: render
	 * target pixels of the game viewport, origin top-left) for the current frame: the geometry of the game viewport
	 * widget (SViewport) and the viewport's size in pixels. Pixel = ViewportGeometry.AbsoluteToLocal(Absolute) /
	 * ViewportLocalSize * ViewportPixels, the same mapping FSceneViewport uses for the mouse. ViewportGeometry is in
	 * the same absolute space as the FGeometry it is used with: desktop (tick space) for Tick and input events, window
	 * (paint space) for OnPaint.
	 */
	struct FViewportMapping
	{
		FGeometry ViewportGeometry;
		FVector2D ViewportLocalSize = FVector2D(1.0, 1.0);
		FVector2D ViewportPixels = FVector2D(1.0, 1.0);
	};

	/** A plaque or troop tag painted over the 3D map (local rectangle), hit tested before the scene. */
	struct FOverlayHit
	{
		int32 City = -1;
		int32 ArmyId = -1;
		FVector2f Min = FVector2f(0.0f, 0.0f);
		FVector2f Max = FVector2f(0.0f, 0.0f);
	};

	FMapFrame MakeFrame(const FVector2f& InViewSize) const;
	void ClampView(const FVector2f& InViewSize);
	FVector2f MapSize() const;
	float CityIconSize(int32 CitySize, float Scale) const;
	float BannerHeight(float Scale) const;
	void CollectArmies(const FMapFrame& Frame, float Fraction, TArray<FArmyPlacement>& OutPlacements) const;
	int32 HitTestCity(const FMapFrame& Frame, const FVector2f& LocalPos) const;
	int32 HitTestArmy(const FMapFrame& Frame, const FVector2f& LocalPos) const;
	void UpdateHover(const FVector2f& LocalPos);
	void LoadArtInfo();

	int32 PaintRoads(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;
	int32 PaintLabels(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;
	int32 PaintMarchRoutes(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer, float Fraction) const;
	int32 PaintCities(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;
	int32 PaintArmies(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer, float Fraction) const;
	int32 PaintTooltip(const FVector2f& ViewSize, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;

	// ----- 3D map overlay -----
	/** The world map while it is active, else nullptr. */
	AIronWorldMap3D* GetActiveWorldMap() const;
	/** bPaintSpace: the mapping is used with OnPaint's geometry (window space) instead of Tick / event geometry (desktop space). */
	bool MakeViewportMapping(const AIronWorldMap3D& Map, FViewportMapping& OutMapping, bool bPaintSpace = false) const;
	static FVector2D LocalToViewportPixel(const FViewportMapping& Mapping, const FGeometry& Geometry, const FVector2f& LocalPos);
	static FVector2f ViewportPixelToLocal(const FViewportMapping& Mapping, const FGeometry& Geometry, const FVector2D& Pixel);
	/** Map point (metres) at HeightM above the surface (terrain or sea) to local coordinates; false when not on screen. */
	static bool ProjectToLocal(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geometry, const FVector2D& MapPointM, float HeightAboveSurfaceM, FVector2f& OutLocal);
	void UpdateWorldHover(const FGeometry& Geometry, const FVector2f& LocalPos);
	void PushWorldHighlights(AIronWorldMap3D& Map) const;
	FReply HandleWorldKey(AIronWorldMap3D& Map, const FGeometry& Geometry, const FKey& Key);

	int32 PaintWorldOverlay(const AIronWorldMap3D& Map, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 LayerId) const;
	int32 PaintWorldLabels(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;
	int32 PaintWorldRoutes(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer, float Fraction) const;
	int32 PaintWorldCities(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;
	int32 PaintWorldArmies(const AIronWorldMap3D& Map, const FViewportMapping& Mapping, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;

	TSharedPtr<FIronSession> Session;
	TAttribute<float> FractionalDayAttr;
	TAttribute<int32> SelectedCityAttr;
	TAttribute<int32> SelectedArmyAttr;
	FOnIronMapCityClicked OnCityClicked;
	FOnIronMapArmyClicked OnArmyClicked;

	/** Requested view (map pixels at the view centre, map pixel -> slate unit scale). */
	FVector2f ViewCenter = FVector2f(1200.0f, 750.0f);
	float Zoom = 0.8f;
	mutable FVector2f LastViewSize = FVector2f(0.0f, 0.0f);

	bool bMouseDown = false;
	bool bDragging = false;
	FVector2f PressLocal = FVector2f(0.0f, 0.0f);
	FVector2f LastMouseLocal = FVector2f(0.0f, 0.0f);

	int32 HoverCity = -1;
	int32 HoverArmyId = -1;
	FVector2f HoverLocal = FVector2f(0.0f, 0.0f);

	/** Cloth area of Art/Map/Banner.png (x, y, w, h in source pixels) for the faction glyph. */
	float GlyphAreaX = 14.0f;
	float GlyphAreaY = 8.0f;
	float GlyphAreaW = 42.0f;
	float GlyphAreaH = 42.0f;
	FVector2f BannerArtSize = FVector2f(64.0f, 96.0f);
	/** State.Map.Image (relative to Content/Data). */
	FString MapImage;
	bool bHasMapArt = false;
	bool bHasCityArt[3] = {false, false, false};
	bool bHasBannerArt = false;
	bool bHasFlagArt = false;
	bool bHasSectArt = false;

	// ----- 3D map overlay -----
	TWeakObjectPtr<AIronWorldMap3D> WorldMap;
	/** Mouse button that started the current press (a middle drag rotates the 3D camera instead of panning). */
	FKey PressButton;
	/** The cursor is over the widget: the 3D hover is re-picked every frame while the scene moves under it. */
	bool bCursorInside = false;
	FVector2D LastCursorAbsolute = FVector2D::ZeroVector;
	float HoverRepickSeconds = 0.0f;
	/** Plaques and tags of the last 3D paint, in paint order (the last one is on top). */
	mutable TArray<FOverlayHit> OverlayHits;
};
