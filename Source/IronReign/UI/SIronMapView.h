#pragma once

#include "CoreMinimal.h"
#include "InputCoreTypes.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SLeafWidget.h"

class FIronSession;

DECLARE_DELEGATE_OneParam(FOnIronMapCityClicked, int32 /*City*/);

/**
 * The painted campaign map: world image, roads, labels, cities with pennants and name plaques, sect markers,
 * marching army banners (interpolated between day ticks), planned march arrows and hover tooltips.
 * Pan by dragging with the left or right mouse button, zoom with the wheel (0.5x..2.5x, the map always fills the view).
 * All hit testing happens in map coordinates (pixels of the map image).
 */
class IRONREIGN_API SIronMapView : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SIronMapView)
		: _FractionalDay(0.0f)
		, _SelectedCity(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		/** 0..1 progress toward the next day tick, used to interpolate marching armies. */
		SLATE_ATTRIBUTE(float, FractionalDay)
		SLATE_ATTRIBUTE(int32, SelectedCity)
		SLATE_EVENT(FOnIronMapCityClicked, OnCityClicked)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	/** Centers the view on a city, keeping the zoom. */
	void CenterOnCity(int32 InCity);
	FVector2f GetViewCenter() const { return ViewCenter; }
	float GetZoom() const { return Zoom; }
	void SetView(const FVector2f& InCenter, float InZoom);

	// SWidget interface
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual void OnMouseLeave(const FPointerEvent& MouseEvent) override;
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
	int32 PaintTooltip(const FMapFrame& Frame, const FGeometry& Geo, FSlateWindowElementList& OutDrawElements, int32 Layer) const;

	TSharedPtr<FIronSession> Session;
	TAttribute<float> FractionalDayAttr;
	TAttribute<int32> SelectedCityAttr;
	FOnIronMapCityClicked OnCityClicked;

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
};
