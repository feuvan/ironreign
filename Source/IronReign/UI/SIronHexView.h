#pragma once

#include "CoreMinimal.h"
#include "Sim/IronBattle.h"
#include "Fonts/SlateFontInfo.h"
#include "Layout/Margin.h"
#include "UObject/WeakObjectPtr.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SLeafWidget.h"

#include <string>

class AIronBattleBoard3D;
class FIronSession;
struct FSlateBrush;

/** A hex of the board was clicked with the left mouse button. */
DECLARE_DELEGATE_OneParam(FOnIronHexClicked, IronSim::FHex /*Hex*/);
/** Right click or Escape on the board. Return true when something was cancelled (Escape is then consumed). */
DECLARE_DELEGATE_RetVal(bool, FOnIronHexCancel);

/** What the battle screen wants highlighted on the board. */
struct FIronHexHighlights
{
	/** Blue: hexes the selected unit can move to. */
	TArray<IronSim::FHex> Reachable;
	/** Red: enemies the selected unit can attack. */
	TArray<IronSim::FHex> AttackTargets;
	/** Purple: targets of the chosen tactic. */
	TArray<IronSim::FHex> TacticTargets;
	/** Orange: officers that can be challenged to a duel. */
	TArray<IronSim::FHex> DuelTargets;
	/** Gold ring around this unit (-1 = none). */
	int32 SelectedUnit = -1;
	/** Unit whose attack / tactic preview is shown in the hover tooltip (-1 = none). */
	int32 ActingUnit = -1;
	/** When set the tooltip previews PreviewTactic's success chance instead of attack losses. */
	bool bTacticPreview = false;
	IronSim::ETactic PreviewTactic = IronSim::ETactic::Fire;
};

/** Display helpers shared by the battle screen, the hex view and the duel dialog (defined in SIronHexView.cpp). */
namespace IronBattleUI
{
	/** Localized officer name when the unit maps to a campaign officer, else the setup name. UTF-8. */
	std::string UnitName(const FIronSession* Session, const IronSim::FBattleUnit& Unit);
	/** Localized officer name for a campaign officer index, else Fallback. UTF-8. */
	std::string OfficerName(const FIronSession* Session, int32 Officer, const std::string& Fallback);
	/** Localized faction name of a battle side. UTF-8. */
	std::string SideName(const FIronSession* Session, const IronSim::FBattleSetup& Setup, int32 Side);
	FLinearColor SideColor(const IronSim::FBattleSetup& Setup, int32 Side);
	/** Terrain no unit can enter (mountains, water, walls). Gates are shown with their HP instead. */
	bool IsImpassableTerrain(IronSim::EHexTerrain Terrain);
	FText UnitStatusName(IronSim::EUnitStatus Status);
}

/**
 * Leaf widget that renders the tactical hex board: terrain tiles, burning hexes, gate HP, highlights, units with
 * side-coloured bases, troop bars, commander star, status overlays, move interpolation, hit effects, floating numbers,
 * a day banner and a hover tooltip. Plays the battle sound effects in sync with the animations.
 * Game logic lives in SIronBattleScreen; the view reports clicks.
 *
 * With an active AIronBattleBoard3D (argument Board) the widget is a transparent overlay over the real-time 3D board
 * (docs/DESIGN.md 12.4) and must cover the whole game viewport: hover and clicks are picked on the board, left or
 * middle drag pans its camera, the wheel zooms and Home / R reset the view; highlights, the hover ring and every unit,
 * gate and effect animation are drawn by the board (fed from the same FBattleEvent stream); the widget draws the
 * projected unit plates (name, troop bar), gate bars, floating numbers, the day banner and the tooltip, and plays the
 * sounds on the board's animation timeline. Without a board (or when it stops being active) it draws the 2D board.
 */
class SIronHexView : public SLeafWidget
{
public:
	SLATE_BEGIN_ARGS(SIronHexView) {}
		SLATE_ARGUMENT(TSharedPtr<IronSim::FBattle>, Battle)
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		/** The built and active 3D board of this battle, or null for the 2D board. */
		SLATE_ARGUMENT(TWeakObjectPtr<AIronBattleBoard3D>, Board)
		SLATE_EVENT(FOnIronHexClicked, OnHexClicked)
		SLATE_EVENT(FOnIronHexCancel, OnCancel)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void SetHighlights(const FIronHexHighlights& InHighlights);
	/** Queues the animation and sound for one battle event (moves play one after another, effects follow the moves). */
	void PlayEvent(const IronSim::FBattleEvent& Event);
	/** Large centred caption that fades out ("Day 3"). */
	void ShowBanner(const FText& Text);
	/** Drops every running animation and queued sound (e.g. after a fast-forward). */
	void ClearAnimations();
	/** FPlatformTime::Seconds() until which queued animations (2D moves, or the 3D board's blocking animations) play. */
	double GetBusyUntil() const;
	/** True while queued animations should hold back the next AI step or the result dialog. */
	bool IsAnimating() const;
	/**
	 * After the events of a rules change were played: the 3D board takes the new rules state (SyncFromBattle);
	 * bFinishAnimations completes every board animation at once (fast-forward). No-op on the 2D board.
	 */
	void SyncBoard(bool bFinishAnimations);
	/** True while the 3D board shows the battle and this widget is its transparent overlay. */
	bool IsBoardMode() const;
	/**
	 * 3D: fractions of the widget covered by the screen's panels (left, top, right, bottom); the banner and the
	 * tooltip stay inside the rest.
	 */
	void SetCoveredInsets(const FMargin& InInsets);

	// SWidget interface
	virtual int32 OnPaint(const FPaintArgs& Args, const FGeometry& AllottedGeometry, const FSlateRect& MyCullingRect, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& InWidgetStyle, bool bParentEnabled) const override;
	virtual FReply OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseButtonDoubleClick(const FGeometry& InMyGeometry, const FPointerEvent& InMouseEvent) override;
	virtual FReply OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual FReply OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent) override;
	virtual void OnMouseLeave(const FPointerEvent& MouseEvent) override;
	virtual void OnMouseCaptureLost(const FCaptureLostEvent& CaptureLostEvent) override;
	virtual FCursorReply OnCursorQuery(const FGeometry& MyGeometry, const FPointerEvent& CursorEvent) const override;
	virtual FReply OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent) override;
	virtual bool SupportsKeyboardFocus() const override { return true; }

protected:
	virtual FVector2D ComputeDesiredSize(float LayoutScaleMultiplier) const override;

private:
	/** A runtime-loaded image and whether its file exists (checked once). */
	struct FArtRef
	{
		FString Path;
		bool bExists = false;
	};

	/** Board -> widget transform for the current geometry. */
	struct FBoardLayout
	{
		float Scale = 1.0f;
		/** Widget-local position of the board's top-left corner. */
		FVector2f Offset = FVector2f(0.0f, 0.0f);
		/** Board-space top-left corner (minimum of every hex's extent). */
		FVector2f Origin = FVector2f(0.0f, 0.0f);

		FVector2f ToLocal(const FVector2f& BoardPos) const { return Offset + (BoardPos - Origin) * Scale; }
		FVector2f ToBoard(const FVector2f& LocalPos) const { return (LocalPos - Offset) / Scale + Origin; }
	};

	enum class EFxKind : uint8
	{
		Hit,
		Fire,
		Confuse,
		Rally
	};

	struct FMoveAnim
	{
		int32 Unit = -1;
		IronSim::FHex From;
		IronSim::FHex To;
		double Start = 0.0;
	};

	struct FHexFx
	{
		EFxKind Kind = EFxKind::Hit;
		FVector2f BoardPos = FVector2f(0.0f, 0.0f);
		double Start = 0.0;
		float Duration = 0.6f;
	};

	struct FFloatText
	{
		FVector2f BoardPos = FVector2f(0.0f, 0.0f);
		/** Hex the text pops over (the 3D anchor) and how many texts were already stacked there. */
		IronSim::FHex Hex = {-1, -1};
		int32 Stack = 0;
		FString Text;
		FLinearColor Color = FLinearColor::White;
		double Start = 0.0;
		float Duration = 1.1f;
		float FontSize = 18.0f;
	};

	struct FTipLine
	{
		FString Text;
		FLinearColor Color = FLinearColor::White;
		bool bBold = false;
	};

	/** Sound effect (FIronAudio::PlaySfx name) that starts with its animation. */
	struct FQueuedSound
	{
		FString Name;
		double Start = 0.0;
	};

	static FArtRef MakeArt(const FString& RelativePath);
	static const FSlateBrush* ArtBrush(const FArtRef& Art);

	bool HasBattle() const { return Battle.IsValid(); }
	bool IsValidUnit(int32 UnitId) const;
	FVector2f HexCenter(IronSim::FHex Hex) const;
	FBoardLayout ComputeLayout(const FVector2f& LocalSize) const;
	/** Hex under a widget-local point; Col = -1 when outside the board. */
	IronSim::FHex PickHex(const FVector2f& LocalPos, const FBoardLayout& Layout) const;
	FVector2f UnitBoardPos(int32 UnitId, double Now) const;
	IronSim::FHex UnitHexOr(int32 UnitId, IronSim::FHex Fallback) const;
	/** Gate index (0/1) standing on Hex, or -1. */
	int32 GateIndexAt(IronSim::FHex Hex) const;
	/** Side whose terrain bonus the tooltip shows for an empty hex: the player's side, else the defender. */
	int32 TooltipDefenseSide() const;

	void AddFx(EFxKind Kind, IronSim::FHex Hex, double Start, float Duration);
	void AddFloat(IronSim::FHex Hex, const FString& Text, const FLinearColor& Color, double Start, float FontSize = 18.0f);
	/** Plays SfxName now, or when Start is reached if the event's animation is still queued behind a move. */
	void AddSound(const TCHAR* SfxName, double Start);
	void PlayDueSounds(double Now);
	EActiveTimerReturnType OnAnimationTick(double InCurrentTime, float InDeltaTime);

	void DrawImage(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FSlateBrush* Brush, const FVector2f& Center, const FVector2f& Size, const FLinearColor& Tint) const;
	void DrawRect(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& TopLeft, const FVector2f& Size, const FLinearColor& Color) const;
	void DrawHexOutline(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& Center, float Radius, const FLinearColor& Color, float Thickness) const;
	void DrawStar(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& Center, float Radius) const;
	void DrawBar(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& Center, const FVector2f& Size, float Fraction, const FLinearColor& FillColor) const;
	/** Text centred on Center with a dark drop shadow (uses two layers: Layer and Layer + 1). */
	void DrawCenteredText(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FString& Text, const FSlateFontInfo& Font, const FVector2f& Center, const FLinearColor& Color) const;
	/** Day banner across the area AreaMin..AreaMax (uses Layer .. Layer + 2). */
	void DrawBanner(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& AreaMin, const FVector2f& AreaMax, double Now) const;
	/** Hover tooltip next to the cursor, kept inside AreaMin..AreaMax. */
	int32 DrawTooltip(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& AreaMin, const FVector2f& AreaMax) const;
	void BuildTooltipLines(TArray<FTipLine>& OutLines) const;

	// 3D board overlay.
	/** The board while it shows this battle (built and active), else null. */
	AIronBattleBoard3D* GetActiveBoard() const;
	/** Game viewport render pixels per widget-local unit (the board projects into viewport pixels). */
	FVector2f ViewportPixelsPerLocal(const FVector2f& LocalSize) const;
	/** Hex of the 3D board under a widget-local point; Col = -1 when off the board. */
	IronSim::FHex PickBoardHex(const FVector2f& LocalPos, const FVector2f& LocalSize) const;
	/** Re-picks the hovered hex (the camera and the units move under a still cursor) and shows it on the board. */
	void UpdateBoardHover(const FVector2f& LocalSize);
	/** Hands the highlights and the hovered hex to the board. */
	void PushBoardHighlights();
	void ResetPointerState();
	/** Widget-local area not covered by the screen's panels (the whole widget on the 2D board). */
	void GetFreeArea(const FVector2f& LocalSize, FVector2f& OutMin, FVector2f& OutMax) const;
	/** Unit plates, gate bars, floating texts, banner and tooltip over the 3D board. */
	int32 PaintBoardOverlay(const AIronBattleBoard3D& ActiveBoard, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FGeometry& Geometry, double Now) const;

	TSharedPtr<IronSim::FBattle> Battle;
	TSharedPtr<FIronSession> Session;
	TWeakObjectPtr<AIronBattleBoard3D> Board;
	FOnIronHexClicked OnHexClickedDelegate;
	FOnIronHexCancel OnCancelDelegate;

	/** 3D: fractions of the widget covered by the screen's panels. */
	FMargin CoveredInsets = FMargin(0.0f);
	/** 3D pointer: a left press becomes a click on release unless it turns into a drag; left or middle drag pans. */
	FVector2f PressLocal = FVector2f(0.0f, 0.0f);
	FVector2f LastDragLocal = FVector2f(0.0f, 0.0f);
	bool bPanButtonDown = false;
	bool bClickPending = false;
	bool bDragging = false;

	FIronHexHighlights Highlights;
	IronSim::FHex HoveredHex = {-1, -1};
	FVector2f MouseLocal = FVector2f(0.0f, 0.0f);
	bool bMouseInside = false;

	/** Board-space extent of the whole grid (computed once in Construct). */
	FVector2f BoardMin = FVector2f(0.0f, 0.0f);
	FVector2f BoardExtent = FVector2f(1.0f, 1.0f);

	TArray<FMoveAnim> MoveAnims;
	TArray<FHexFx> ActiveFx;
	TArray<FFloatText> FloatingTexts;
	TArray<FQueuedSound> QueuedSounds;
	/** Moves play back to back; effects of later events start once earlier moves finished. */
	double AnimCursor = 0.0;
	FText BannerText;
	double BannerStart = -100.0;

	FArtRef BackgroundArt;
	FArtRef TerrainArt[static_cast<int32>(IronSim::EHexTerrain::Count)];
	FArtRef FillArt;
	FArtRef OutlineArt;
	FArtRef UnitBaseArt;
	FArtRef UnitArt[3];
	FArtRef FireArt;
	FArtRef ConfuseArt;
	FArtRef RallyArt;
	FArtRef HitArt;
};
