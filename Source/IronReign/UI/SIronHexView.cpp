#include "UI/SIronHexView.h"

#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"
#include "World/IronBattleBoard3D.h"
#include "World/IronViewProjection.h"
#include "World/IronWorldMath.h"

#include "Engine/GameViewportClient.h"
#include "Engine/World.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "HAL/PlatformTime.h"
#include "InputCoreTypes.h"
#include "Input/CursorReply.h"
#include "Input/Events.h"
#include "Input/Reply.h"
#include "Layout/Geometry.h"
#include "Rendering/DrawElements.h"
#include "Rendering/SlateRenderer.h"
#include "Styling/SlateBrush.h"

namespace IronHexViewDetail
{
	/** Art is authored for a hex radius of 64 px: 128 x 111 tiles. */
	constexpr float HexRadius = 64.0f;
	constexpr float HexHeight = 110.85125f;  // sqrt(3) * 64
	constexpr float MoveSeconds = 0.25f;
	constexpr float FxSeconds = 0.6f;
	constexpr float BannerSeconds = 1.6f;

	// 3D board overlay.
	/** Floating texts rise from this height above the board (metres), or this far above a gate's top. */
	constexpr float BoardFloatHeightM = 4.0f;
	constexpr float BoardFloatAboveGateM = 1.0f;
	/** Gate bars float this far above the drawn gatehouse (or its rubble), unit plates above the unit model (metres). */
	constexpr float BoardGateBarAboveTopM = 0.8f;
	constexpr float BoardPlateAboveModelM = 0.5f;
	/** On-screen hex size (corner to corner, Slate units) at which plates are drawn at their nominal size. */
	constexpr float BoardNominalHexSize = 110.0f;
	/** Cursor travel (Slate units) after which a press on the board pans instead of clicking. */
	constexpr float BoardDragThreshold = 6.0f;

	/** Converts any Slate 2D vector type (FVector2D, FVector2f, deprecation wrappers) to FVector2f. */
	template <typename VectorType>
	FVector2f HexVec(const VectorType& Value)
	{
		return FVector2f(static_cast<float>(Value.X), static_cast<float>(Value.Y));
	}

	float HexSmoothStep(float Alpha)
	{
		const float Clamped = FMath::Clamp(Alpha, 0.0f, 1.0f);
		return Clamped * Clamped * (3.0f - 2.0f * Clamped);
	}

	FLinearColor HexWithAlpha(const FLinearColor& Color, float Alpha)
	{
		FLinearColor Result = Color;
		Result.A = Alpha;
		return Result;
	}

	/** Used when a terrain tile PNG is missing. */
	FLinearColor FallbackTerrainColor(IronSim::EHexTerrain Terrain)
	{
		switch (Terrain)
		{
		case IronSim::EHexTerrain::Forest: return FLinearColor(0.06f, 0.18f, 0.06f);
		case IronSim::EHexTerrain::Hill: return FLinearColor(0.35f, 0.28f, 0.12f);
		case IronSim::EHexTerrain::Mountain: return FLinearColor(0.18f, 0.16f, 0.14f);
		case IronSim::EHexTerrain::Water: return FLinearColor(0.05f, 0.12f, 0.3f);
		case IronSim::EHexTerrain::Ford: return FLinearColor(0.15f, 0.3f, 0.45f);
		case IronSim::EHexTerrain::Bridge: return FLinearColor(0.35f, 0.22f, 0.1f);
		case IronSim::EHexTerrain::Road: return FLinearColor(0.55f, 0.45f, 0.28f);
		case IronSim::EHexTerrain::Wall: return FLinearColor(0.25f, 0.24f, 0.22f);
		case IronSim::EHexTerrain::Gate: return FLinearColor(0.3f, 0.12f, 0.06f);
		case IronSim::EHexTerrain::Town: return FLinearColor(0.5f, 0.42f, 0.32f);
		case IronSim::EHexTerrain::Castle: return FLinearColor(0.45f, 0.1f, 0.08f);
		case IronSim::EHexTerrain::Rubble: return FLinearColor(0.32f, 0.3f, 0.28f);
		default: return FLinearColor(0.42f, 0.4f, 0.2f);
		}
	}

	FLinearColor TroopBarColor(float Fraction)
	{
		if (Fraction > 0.5f)
		{
			return IronStyle::Jade();
		}
		return Fraction > 0.25f ? IronStyle::Gold() : IronStyle::Danger();
	}

	std::string SignedPercent(int32 Value)
	{
		return Value > 0 ? std::string("+") + IronSim::ToText(Value) : IronSim::ToText(Value);
	}
}

// -------------------------------------------------------------------------------------------------
// Shared display helpers
// -------------------------------------------------------------------------------------------------

namespace IronBattleUI
{
	std::string OfficerName(const FIronSession* Session, int32 Officer, const std::string& Fallback)
	{
		if (Session != nullptr && Session->HasGame() && Officer >= 0 && Officer < static_cast<int32>(Session->State().Officers.size()))
		{
			return IronSim::NameOf(Session->State().Officers[static_cast<size_t>(Officer)]);
		}
		if (!Fallback.empty())
		{
			return Fallback;
		}
		return IronSim::Loc("ui.battle.garrison", "Garrison");
	}

	std::string UnitName(const FIronSession* Session, const IronSim::FBattleUnit& Unit)
	{
		return OfficerName(Session, Unit.Setup.Officer, Unit.Setup.Name);
	}

	std::string SideName(const FIronSession* Session, const IronSim::FBattleSetup& Setup, int32 Side)
	{
		const int32 SideIndex = Side == 0 ? 0 : 1;
		const IronSim::FBattleSideSetup& SideSetup = Setup.Sides[SideIndex];
		if (Session != nullptr && Session->HasGame() && SideSetup.Faction >= 0 && SideSetup.Faction < static_cast<int32>(Session->State().Factions.size()))
		{
			return IronSim::NameOf(Session->State().Factions[static_cast<size_t>(SideSetup.Faction)]);
		}
		if (!SideSetup.Name.empty())
		{
			return SideSetup.Name;
		}
		return SideIndex == 0 ? IronSim::Loc("ui.battle.attacker", "Attacker") : IronSim::Loc("ui.battle.defender", "Defender");
	}

	FLinearColor SideColor(const IronSim::FBattleSetup& Setup, int32 Side)
	{
		return IronUI::ColorFromRGB(Setup.Sides[Side == 0 ? 0 : 1].Color);
	}

	bool IsImpassableTerrain(IronSim::EHexTerrain Terrain)
	{
		return Terrain == IronSim::EHexTerrain::Mountain || Terrain == IronSim::EHexTerrain::Water || Terrain == IronSim::EHexTerrain::Wall;
	}

	FText UnitStatusName(IronSim::EUnitStatus Status)
	{
		switch (Status)
		{
		case IronSim::EUnitStatus::Active:
			return IronUI::Loc("ui.battle.status.active", "Survived");
		case IronSim::EUnitStatus::Routed:
			return IronUI::Loc("ui.battle.status.routed", "Routed");
		case IronSim::EUnitStatus::Destroyed:
			return IronUI::Loc("ui.battle.status.destroyed", "Destroyed");
		case IronSim::EUnitStatus::Captured:
			return IronUI::Loc("ui.battle.status.captured", "Captured");
		case IronSim::EUnitStatus::Killed:
			return IronUI::Loc("ui.battle.status.killed", "Killed");
		default:
			break;
		}
		return FText::GetEmpty();
	}
}

// -------------------------------------------------------------------------------------------------
// SIronHexView
// -------------------------------------------------------------------------------------------------

void SIronHexView::Construct(const FArguments& InArgs)
{
	Battle = InArgs._Battle;
	Session = InArgs._Session;
	Board = InArgs._Board;
	// Fixed for the view's life: the battle screen builds a new view when it falls back to the 2D board.
	bBoardTimeline = Board.IsValid();
	OnHexClickedDelegate = InArgs._OnHexClicked;
	OnCancelDelegate = InArgs._OnCancel;

	SetClipping(EWidgetClipping::ClipToBounds);

	BackgroundArt = MakeArt(TEXT("Art/Battle/Background.png"));
	for (int32 TerrainIndex = 0; TerrainIndex < static_cast<int32>(IronSim::EHexTerrain::Count); ++TerrainIndex)
	{
		const IronSim::EHexTerrain Terrain = static_cast<IronSim::EHexTerrain>(TerrainIndex);
		TerrainArt[TerrainIndex] = MakeArt(FString(TEXT("Art/Battle/Hex_")) + IronUI::ToFString(std::string(IronSim::AssetName(Terrain))) + TEXT(".png"));
	}
	FillArt = MakeArt(TEXT("Art/Battle/Hex_Fill.png"));
	OutlineArt = MakeArt(TEXT("Art/Battle/Hex_Outline.png"));
	UnitBaseArt = MakeArt(TEXT("Art/Battle/Unit_Base.png"));
	UnitArt[0] = MakeArt(TEXT("Art/Battle/Unit_Infantry.png"));
	UnitArt[1] = MakeArt(TEXT("Art/Battle/Unit_Cavalry.png"));
	UnitArt[2] = MakeArt(TEXT("Art/Battle/Unit_Archer.png"));
	FireArt = MakeArt(TEXT("Art/Battle/Fx_Fire.png"));
	ConfuseArt = MakeArt(TEXT("Art/Battle/Fx_Confuse.png"));
	RallyArt = MakeArt(TEXT("Art/Battle/Fx_Rally.png"));
	HitArt = MakeArt(TEXT("Art/Battle/Fx_Hit.png"));

	// Board extent from the hex centres (robust to the origin convention of HexMath::ToPixel).
	if (Battle.IsValid() && Battle->Cols() > 0 && Battle->Rows() > 0)
	{
		FVector2f MinCenter(0.0f, 0.0f);
		FVector2f MaxCenter(0.0f, 0.0f);
		bool bFirst = true;
		for (int32 Row = 0; Row < Battle->Rows(); ++Row)
		{
			for (int32 Col = 0; Col < Battle->Cols(); ++Col)
			{
				const FVector2f Center = HexCenter(IronSim::FHex{Col, Row});
				if (bFirst)
				{
					MinCenter = Center;
					MaxCenter = Center;
					bFirst = false;
				}
				else
				{
					MinCenter.X = FMath::Min(MinCenter.X, Center.X);
					MinCenter.Y = FMath::Min(MinCenter.Y, Center.Y);
					MaxCenter.X = FMath::Max(MaxCenter.X, Center.X);
					MaxCenter.Y = FMath::Max(MaxCenter.Y, Center.Y);
				}
			}
		}
		const FVector2f HalfHex(IronHexViewDetail::HexRadius, IronHexViewDetail::HexHeight * 0.5f);
		BoardMin = MinCenter - HalfHex;
		BoardExtent = (MaxCenter - MinCenter) + HalfHex * 2.0f;
	}

	// Over the 3D board the plates follow the animated models: repaint every frame.
	RegisterActiveTimer(Board.IsValid() ? 0.0f : 1.0f / 60.0f, FWidgetActiveTimerDelegate::CreateSP(this, &SIronHexView::OnAnimationTick));
	PushBoardHighlights();
}

SIronHexView::FArtRef SIronHexView::MakeArt(const FString& RelativePath)
{
	FArtRef Art;
	Art.Path = RelativePath;
	Art.bExists = FIronAssets::Get().Exists(RelativePath);
	return Art;
}

const FSlateBrush* SIronHexView::ArtBrush(const FArtRef& Art)
{
	return Art.bExists ? FIronAssets::Get().Image(Art.Path) : nullptr;
}

bool SIronHexView::IsValidUnit(int32 UnitId) const
{
	return Battle.IsValid() && UnitId >= 0 && UnitId < static_cast<int32>(Battle->Units().size());
}

FVector2f SIronHexView::HexCenter(IronSim::FHex Hex) const
{
	float PixelX = 0.0f;
	float PixelY = 0.0f;
	IronSim::HexMath::ToPixel(Hex, IronHexViewDetail::HexRadius, PixelX, PixelY);
	return FVector2f(PixelX, PixelY);
}

SIronHexView::FBoardLayout SIronHexView::ComputeLayout(const FVector2f& LocalSize) const
{
	constexpr float Margin = 8.0f;
	FBoardLayout Layout;
	const float AvailableX = FMath::Max(LocalSize.X - Margin * 2.0f, 1.0f);
	const float AvailableY = FMath::Max(LocalSize.Y - Margin * 2.0f, 1.0f);
	const float ExtentX = FMath::Max(BoardExtent.X, 1.0f);
	const float ExtentY = FMath::Max(BoardExtent.Y, 1.0f);
	Layout.Scale = FMath::Max(FMath::Min(AvailableX / ExtentX, AvailableY / ExtentY), 0.05f);
	Layout.Origin = BoardMin;
	Layout.Offset = (LocalSize - FVector2f(ExtentX, ExtentY) * Layout.Scale) * 0.5f;
	return Layout;
}

IronSim::FHex SIronHexView::PickHex(const FVector2f& LocalPos, const FBoardLayout& Layout) const
{
	const IronSim::FHex NoHex = {-1, -1};
	if (!Battle.IsValid())
	{
		return NoHex;
	}
	const FVector2f BoardPos = Layout.ToBoard(LocalPos);
	const IronSim::FHex Guess = IronSim::HexMath::FromPixel(BoardPos.X, BoardPos.Y, IronHexViewDetail::HexRadius);
	if (Battle->InBounds(Guess) && (HexCenter(Guess) - BoardPos).Size() <= IronHexViewDetail::HexRadius)
	{
		return Guess;
	}
	// Fallback: the nearest hex centre is the hex containing the point.
	IronSim::FHex Best = NoHex;
	float BestDistance = IronHexViewDetail::HexRadius;
	for (int32 Row = 0; Row < Battle->Rows(); ++Row)
	{
		for (int32 Col = 0; Col < Battle->Cols(); ++Col)
		{
			const IronSim::FHex Candidate = {Col, Row};
			const float Distance = (HexCenter(Candidate) - BoardPos).Size();
			if (Distance < BestDistance)
			{
				BestDistance = Distance;
				Best = Candidate;
			}
		}
	}
	return Best;
}

FVector2f SIronHexView::UnitBoardPos(int32 UnitId, double Now) const
{
	const IronSim::FBattleUnit& BattleUnit = Battle->Unit(UnitId);
	for (const FMoveAnim& Anim : MoveAnims)
	{
		if (Anim.Unit != UnitId)
		{
			continue;
		}
		const float Alpha = static_cast<float>((Now - Anim.Start) / IronHexViewDetail::MoveSeconds);
		if (Alpha < 1.0f)
		{
			const FVector2f FromPos = HexCenter(Anim.From);
			const FVector2f ToPos = HexCenter(Anim.To);
			return FromPos + (ToPos - FromPos) * IronHexViewDetail::HexSmoothStep(Alpha);
		}
	}
	return HexCenter(BattleUnit.Pos);
}

IronSim::FHex SIronHexView::UnitHexOr(int32 UnitId, IronSim::FHex Fallback) const
{
	return IsValidUnit(UnitId) ? Battle->Unit(UnitId).Pos : Fallback;
}

int32 SIronHexView::GateIndexAt(IronSim::FHex Hex) const
{
	if (!Battle.IsValid() || !Battle->InBounds(Hex))
	{
		return -1;
	}
	for (int32 GateIndex = 0; GateIndex < Battle->GateCount(); ++GateIndex)
	{
		if (Battle->GateHexAt(GateIndex) == Hex)
		{
			return GateIndex;
		}
	}
	return -1;
}

int32 SIronHexView::TooltipDefenseSide() const
{
	const IronSim::FBattleSetup& BattleSetup = Battle->GetSetup();
	if (BattleSetup.Sides[0].bPlayer)
	{
		return 0;
	}
	return 1;
}

void SIronHexView::SetHighlights(const FIronHexHighlights& InHighlights)
{
	Highlights = InHighlights;
	PushBoardHighlights();
	Invalidate(EInvalidateWidgetReason::Paint);
}

double SIronHexView::TimelineNow() const
{
	if (!bBoardTimeline)
	{
		return FPlatformTime::Seconds();
	}
	// The board's own clock (it advances only while the board is active). Kept when the board goes away, so queued
	// texts and sounds simply wait until the screen rebuilds this view for the 2D board.
	if (const AIronBattleBoard3D* BoardActor = Board.Get())
	{
		LastBoardClock = BoardActor->GetAnimationClock();
	}
	return LastBoardClock;
}

void SIronHexView::ShowBanner(const FText& Text)
{
	BannerText = Text;
	BannerStart = FMath::Max(TimelineNow(), GetBusyUntil());
	Invalidate(EInvalidateWidgetReason::Paint);
}

void SIronHexView::ClearAnimations()
{
	MoveAnims.Reset();
	ActiveFx.Reset();
	FloatingTexts.Reset();
	QueuedSounds.Reset();
	AnimCursor = 0.0;
	if (AIronBattleBoard3D* ActiveBoard = GetActiveBoard())
	{
		ActiveBoard->FinishAnimations();
	}
	Invalidate(EInvalidateWidgetReason::Paint);
}

double SIronHexView::GetBusyUntil() const
{
	if (const AIronBattleBoard3D* ActiveBoard = GetActiveBoard())
	{
		return TimelineNow() + static_cast<double>(ActiveBoard->GetRemainingAnimationSeconds());
	}
	return AnimCursor;
}

bool SIronHexView::IsAnimating() const
{
	if (const AIronBattleBoard3D* ActiveBoard = GetActiveBoard())
	{
		return ActiveBoard->IsAnimating();
	}
	return TimelineNow() < AnimCursor;
}

void SIronHexView::SyncBoard(bool bFinishAnimations)
{
	AIronBattleBoard3D* ActiveBoard = GetActiveBoard();
	if (ActiveBoard == nullptr || !Battle.IsValid())
	{
		return;
	}
	ActiveBoard->SyncFromBattle(*Battle);
	if (bFinishAnimations)
	{
		ActiveBoard->FinishAnimations();
	}
}

bool SIronHexView::IsBoardMode() const
{
	return GetActiveBoard() != nullptr;
}

void SIronHexView::SetCoveredInsets(const FMargin& InInsets)
{
	CoveredInsets = InInsets;
}

void SIronHexView::AddFx(EFxKind Kind, IronSim::FHex Hex, double Start, float Duration)
{
	// The 3D board draws its own hit, fire and tactic effects.
	if (!Battle.IsValid() || !Battle->InBounds(Hex) || IsBoardMode())
	{
		return;
	}
	FHexFx NewFx;
	NewFx.Kind = Kind;
	NewFx.BoardPos = HexCenter(Hex);
	NewFx.Start = Start;
	NewFx.Duration = Duration;
	ActiveFx.Add(NewFx);
}

void SIronHexView::AddFloat(IronSim::FHex Hex, const FString& Text, const FLinearColor& Color, double Start, float FontSize)
{
	if (!Battle.IsValid() || !Battle->InBounds(Hex) || Text.IsEmpty())
	{
		return;
	}
	const FVector2f BasePos = HexCenter(Hex);
	// Stack texts that pop on the same hex at about the same time.
	int32 Stacked = 0;
	for (const FFloatText& Existing : FloatingTexts)
	{
		if ((Existing.BoardPos - BasePos).Size() < IronHexViewDetail::HexHeight && FMath::Abs(Existing.Start - Start) < 0.5)
		{
			++Stacked;
		}
	}
	FFloatText NewText;
	NewText.BoardPos = BasePos - FVector2f(0.0f, 24.0f * static_cast<float>(Stacked));
	NewText.Hex = Hex;
	NewText.Stack = Stacked;
	NewText.Text = Text;
	NewText.Color = Color;
	NewText.Start = Start;
	NewText.Duration = 1.1f;
	NewText.FontSize = FontSize;
	FloatingTexts.Add(NewText);
}

void SIronHexView::AddSound(const TCHAR* SfxName, double Start)
{
	if (Start <= TimelineNow())
	{
		FIronAudio::Get().PlaySfx(SfxName);
		return;
	}
	FQueuedSound NewSound;
	NewSound.Name = SfxName;
	NewSound.Start = Start;
	QueuedSounds.Add(MoveTemp(NewSound));
}

void SIronHexView::PlayDueSounds(double Now)
{
	for (int32 SoundIndex = 0; SoundIndex < QueuedSounds.Num();)
	{
		if (Now >= QueuedSounds[SoundIndex].Start)
		{
			const FString DueName = QueuedSounds[SoundIndex].Name;
			QueuedSounds.RemoveAt(SoundIndex);
			FIronAudio::Get().PlaySfx(DueName);
		}
		else
		{
			++SoundIndex;
		}
	}
}

void SIronHexView::PlayEvent(const IronSim::FBattleEvent& Event)
{
	if (!Battle.IsValid())
	{
		return;
	}
	using EEvent = IronSim::EBattleEventType;
	AIronBattleBoard3D* ActiveBoard = GetActiveBoard();
	const bool bOnBoard = ActiveBoard != nullptr;
	// Timeline seconds (TimelineNow) where the event's animation starts and where its result shows (the blow lands,
	// the gate falls, the tactic strikes). 2D: effects start once the queued moves finished, with the event. 3D: the
	// board queues the event after its running animations and reports both moments on its animation clock.
	const double Now = TimelineNow();
	double EventTime = FMath::Max(Now, AnimCursor);
	double ImpactTime = EventTime;
	if (bOnBoard)
	{
		const FIronBoardEventTiming Timing = ActiveBoard->PlayEvent(Event);
		EventTime = Now + static_cast<double>(Timing.StartSeconds);
		ImpactTime = Now + static_cast<double>(Timing.ImpactSeconds);
		// Action the player cannot see (the camera is zoomed in elsewhere): the camera glides there.
		const bool bFollow = Event.Type == EEvent::Move || Event.Type == EEvent::Attack || Event.Type == EEvent::GateHit || Event.Type == EEvent::Tactic;
		if (bFollow && Battle->InBounds(Event.To))
		{
			ActiveBoard->FocusHex(Event.To, true);
		}
	}
	const FLinearColor DamageColor(1.0f, 0.32f, 0.2f, 1.0f);
	const FLinearColor GoodColor(0.45f, 0.95f, 0.55f, 1.0f);
	const FLinearColor MutedColor(0.8f, 0.78f, 0.72f, 1.0f);
	const FLinearColor TacticColor(0.8f, 0.55f, 1.0f, 1.0f);

	switch (Event.Type)
	{
	case EEvent::DayStart:
		ShowBanner(IronUI::LocF("ui.battle.banner.day", "Day {day}", {{"day", IronSim::ToText(Battle->Day())}}));
		break;
	case EEvent::Move:
		// The 3D board walks the unit along its path itself.
		if (!bOnBoard && IsValidUnit(Event.Unit) && Event.From != Event.To)
		{
			const int32 MovingUnit = Event.Unit;
			MoveAnims.RemoveAll([MovingUnit](const FMoveAnim& Existing) { return Existing.Unit == MovingUnit; });
			FMoveAnim NewAnim;
			NewAnim.Unit = MovingUnit;
			NewAnim.From = Event.From;
			NewAnim.To = Event.To;
			NewAnim.Start = EventTime;
			MoveAnims.Add(NewAnim);
			AnimCursor = EventTime + IronHexViewDetail::MoveSeconds;
		}
		break;
	case EEvent::Attack:
	case EEvent::Counter:
	{
		// 3D: the lunge or volley lands (a counter follows its attack on the board's timeline). 2D: a counter a beat later.
		const double HitTime = bOnBoard ? ImpactTime : EventTime + (Event.Type == EEvent::Counter ? 0.2 : 0.0);
		const IronSim::FHex TargetHex = UnitHexOr(Event.Target, Event.To);
		AddFx(EFxKind::Hit, TargetHex, HitTime, IronHexViewDetail::FxSeconds);
		if (Event.Value > 0)
		{
			AddFloat(TargetHex, FString::Printf(TEXT("-%d"), Event.Value), DamageColor, HitTime);
		}
		// Unit is the one striking (the defender for a Counter).
		const bool bArcher = IsValidUnit(Event.Unit) && Battle->Unit(Event.Unit).Setup.Type == IronSim::ETroopType::Archer;
		AddSound(bArcher ? TEXT("Arrow") : TEXT("Attack"), HitTime);
		break;
	}
	case EEvent::GateHit:
	{
		// To is the gate that was hit: great cities have two gates.
		AddFx(EFxKind::Hit, Event.To, ImpactTime, IronHexViewDetail::FxSeconds);
		if (Event.Value > 0)
		{
			AddFloat(Event.To, FString::Printf(TEXT("-%d"), Event.Value), DamageColor, ImpactTime);
		}
		AddSound(TEXT("GateHit"), ImpactTime);
		break;
	}
	case EEvent::GateBroken:
	{
		// 3D: the moment the gatehouse collapses into rubble.
		AddFx(EFxKind::Hit, Event.To, ImpactTime, 1.0f);
		AddFloat(Event.To, IronUI::Loc("ui.battle.fx.gateBroken", "The gate is broken!").ToString(), IronStyle::Gold(), ImpactTime, 22.0f);
		AddSound(TEXT("GateHit"), ImpactTime);
		break;
	}
	case EEvent::Tactic:
	{
		const IronSim::FHex TargetHex = UnitHexOr(Event.Target, Event.To);
		if (Event.Tactic == static_cast<int32>(IronSim::ETactic::Fire))
		{
			AddFx(EFxKind::Fire, TargetHex, ImpactTime, 0.9f);
			if (Event.Value > 0)
			{
				AddFloat(TargetHex, FString::Printf(TEXT("-%d"), Event.Value), DamageColor, ImpactTime);
			}
			AddSound(TEXT("Fire"), ImpactTime);
		}
		else if (Event.Tactic == static_cast<int32>(IronSim::ETactic::Confuse))
		{
			AddFx(EFxKind::Confuse, TargetHex, ImpactTime, 0.9f);
			AddFloat(TargetHex, IronUI::Loc("ui.battle.fx.confused", "Confused!").ToString(), TacticColor, ImpactTime);
			AddSound(TEXT("Confuse"), ImpactTime);
		}
		else if (Event.Tactic == static_cast<int32>(IronSim::ETactic::Rally))
		{
			AddFx(EFxKind::Rally, TargetHex, ImpactTime, 0.9f);
			if (Event.Value > 0)
			{
				AddFloat(TargetHex, FString::Printf(TEXT("+%d"), Event.Value), GoodColor, ImpactTime);
			}
			AddSound(TEXT("Rally"), ImpactTime);
		}
		break;
	}
	case EEvent::TacticFailed:
		AddFloat(UnitHexOr(Event.Target, Event.To), IronUI::Loc("ui.battle.fx.failed", "Failed").ToString(), MutedColor, ImpactTime);
		break;
	case EEvent::Burn:
	{
		const IronSim::FHex BurnHex = UnitHexOr(Event.Unit, Event.To);
		AddFx(EFxKind::Fire, BurnHex, ImpactTime, 0.8f);
		if (Event.Value > 0)
		{
			AddFloat(BurnHex, FString::Printf(TEXT("-%d"), Event.Value), DamageColor, ImpactTime);
		}
		AddSound(TEXT("Fire"), ImpactTime);
		break;
	}
	case EEvent::DuelChallenge:
		AddFloat(UnitHexOr(Event.Unit, Event.From), IronUI::Loc("ui.battle.fx.challenge", "Duel!").ToString(), IronStyle::Gold(), ImpactTime, 20.0f);
		break;
	case EEvent::DuelDeclined:
		AddFloat(UnitHexOr(Event.Target, Event.To), IronUI::Loc("ui.battle.fx.declined", "Declined").ToString(), MutedColor, ImpactTime);
		break;
	case EEvent::DuelResult:
		// Value is the winning unit id (-1 for a draw).
		if (IsValidUnit(Event.Value) && (Event.Value == Event.Unit || Event.Value == Event.Target))
		{
			const int32 LoserId = Event.Value == Event.Unit ? Event.Target : Event.Unit;
			AddFx(EFxKind::Hit, UnitHexOr(LoserId, Event.To), ImpactTime, IronHexViewDetail::FxSeconds);
			AddFloat(UnitHexOr(Event.Value, Event.From), IronUI::Loc("ui.battle.fx.duelWon", "Victorious!").ToString(), IronStyle::Gold(), ImpactTime, 20.0f);
		}
		break;
	case EEvent::Routed:
		AddFloat(UnitHexOr(Event.Unit, Event.To), IronUI::Loc("ui.battle.fx.routed", "Routed!").ToString(), FLinearColor(1.0f, 0.6f, 0.2f, 1.0f), ImpactTime, 20.0f);
		break;
	case EEvent::Destroyed:
		AddFloat(UnitHexOr(Event.Unit, Event.To), IronUI::Loc("ui.battle.fx.destroyed", "Destroyed!").ToString(), DamageColor, ImpactTime, 20.0f);
		break;
	case EEvent::Captured:
		AddFloat(UnitHexOr(Event.Unit, Event.To), IronUI::Loc("ui.battle.fx.captured", "Captured!").ToString(), DamageColor, ImpactTime, 20.0f);
		break;
	case EEvent::Message:
		// Narration. An officer slain names the unit on its own hex (From == To); a challenge accepted names two hexes.
		if (IsValidUnit(Event.Unit) && Event.From == Event.To && Battle->Unit(Event.Unit).Status == IronSim::EUnitStatus::Killed)
		{
			AddFloat(Event.To, IronUI::Loc("ui.battle.fx.slain", "Slain!").ToString(), DamageColor, ImpactTime, 20.0f);
		}
		break;
	case EEvent::Victory:
	default:
		break;
	}
	Invalidate(EInvalidateWidgetReason::Paint);
}

EActiveTimerReturnType SIronHexView::OnAnimationTick(double /*InCurrentTime*/, float /*InDeltaTime*/)
{
	const double Now = TimelineNow();
	PlayDueSounds(Now);
	MoveAnims.RemoveAll([Now](const FMoveAnim& Anim) { return Now > Anim.Start + IronHexViewDetail::MoveSeconds; });
	ActiveFx.RemoveAll([Now](const FHexFx& Effect) { return Now > Effect.Start + Effect.Duration; });
	FloatingTexts.RemoveAll([Now](const FFloatText& Floating) { return Now > Floating.Start + Floating.Duration; });
	if (IsBoardMode())
	{
		// The camera glides and units walk under a still cursor.
		UpdateBoardHover(IronHexViewDetail::HexVec(GetTickSpaceGeometry().GetLocalSize()));
	}
	// Burning hexes flicker, confusion swirls bob and highlights pulse: keep repainting.
	Invalidate(EInvalidateWidgetReason::Paint);
	return EActiveTimerReturnType::Continue;
}

FVector2D SIronHexView::ComputeDesiredSize(float /*LayoutScaleMultiplier*/) const
{
	return FVector2D(640.0, 420.0);
}

// -------------------------------------------------------------------------------------------------
// Input
// -------------------------------------------------------------------------------------------------

FReply SIronHexView::OnMouseButtonDown(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	if (MouseEvent.GetEffectingButton() == EKeys::RightMouseButton)
	{
		if (OnCancelDelegate.IsBound())
		{
			OnCancelDelegate.Execute();
		}
		return FReply::Handled().SetUserFocus(AsShared(), EFocusCause::Mouse);
	}
	if (IsBoardMode() && (MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton || MouseEvent.GetEffectingButton() == EKeys::MiddleMouseButton))
	{
		// 3D: a left press clicks on release unless the cursor travels (then it pans); a middle drag always pans.
		PressLocal = IronHexViewDetail::HexVec(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
		LastDragLocal = PressLocal;
		MouseLocal = PressLocal;
		bPanButtonDown = true;
		bClickPending = MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton;
		bDragging = false;
		return FReply::Handled().CaptureMouse(AsShared()).SetUserFocus(AsShared(), EFocusCause::Mouse);
	}
	if (MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton)
	{
		const FVector2f LocalPos = IronHexViewDetail::HexVec(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
		const FVector2f LocalSize = IronHexViewDetail::HexVec(MyGeometry.GetLocalSize());
		const IronSim::FHex Hex = PickHex(LocalPos, ComputeLayout(LocalSize));
		if (Hex.Col >= 0 && OnHexClickedDelegate.IsBound())
		{
			OnHexClickedDelegate.Execute(Hex);
		}
		return FReply::Handled().SetUserFocus(AsShared(), EFocusCause::Mouse);
	}
	return FReply::Unhandled();
}

FReply SIronHexView::OnMouseButtonDoubleClick(const FGeometry& InMyGeometry, const FPointerEvent& InMouseEvent)
{
	// Slate sends the second press of a quick double click here: on the 3D board it is an ordinary press.
	if (IsBoardMode())
	{
		return OnMouseButtonDown(InMyGeometry, InMouseEvent);
	}
	return SLeafWidget::OnMouseButtonDoubleClick(InMyGeometry, InMouseEvent);
}

FReply SIronHexView::OnMouseButtonUp(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	const bool bPanButton = MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton || MouseEvent.GetEffectingButton() == EKeys::MiddleMouseButton;
	if (!bPanButtonDown || !bPanButton)
	{
		return SLeafWidget::OnMouseButtonUp(MyGeometry, MouseEvent);
	}
	const bool bClick = bClickPending && !bDragging && MouseEvent.GetEffectingButton() == EKeys::LeftMouseButton;
	ResetPointerState();
	if (bClick && IsBoardMode())
	{
		const IronSim::FHex Hex = PickBoardHex(PressLocal, IronHexViewDetail::HexVec(MyGeometry.GetLocalSize()));
		if (Hex.Col >= 0 && OnHexClickedDelegate.IsBound())
		{
			OnHexClickedDelegate.Execute(Hex);
		}
	}
	return FReply::Handled().ReleaseMouseCapture();
}

FReply SIronHexView::OnMouseMove(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	MouseLocal = IronHexViewDetail::HexVec(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	bMouseInside = true;
	const FVector2f LocalSize = IronHexViewDetail::HexVec(MyGeometry.GetLocalSize());
	if (AIronBattleBoard3D* ActiveBoard = GetActiveBoard())
	{
		if (bPanButtonDown && HasMouseCapture())
		{
			if (!bDragging && (MouseLocal - PressLocal).Size() > IronHexViewDetail::BoardDragThreshold)
			{
				bDragging = true;
				bClickPending = false;
				PushBoardHighlights();
			}
			if (bDragging)
			{
				const FVector2f PixelsPerLocal = ViewportPixelsPerLocal(LocalSize);
				const FVector2f DeltaPixels = (MouseLocal - LastDragLocal) * PixelsPerLocal;
				ActiveBoard->Pan(FVector2D(DeltaPixels.X, DeltaPixels.Y), FVector2D(LocalSize.X * PixelsPerLocal.X, LocalSize.Y * PixelsPerLocal.Y));
				LastDragLocal = MouseLocal;
				Invalidate(EInvalidateWidgetReason::Paint);
				return FReply::Handled();
			}
		}
		UpdateBoardHover(LocalSize);
		Invalidate(EInvalidateWidgetReason::Paint);
		return FReply::Unhandled();
	}
	HoveredHex = PickHex(MouseLocal, ComputeLayout(LocalSize));
	Invalidate(EInvalidateWidgetReason::Paint);
	return FReply::Unhandled();
}

FReply SIronHexView::OnMouseWheel(const FGeometry& MyGeometry, const FPointerEvent& MouseEvent)
{
	AIronBattleBoard3D* ActiveBoard = GetActiveBoard();
	if (ActiveBoard == nullptr)
	{
		return SLeafWidget::OnMouseWheel(MyGeometry, MouseEvent);
	}
	const FVector2f LocalPos = IronHexViewDetail::HexVec(MyGeometry.AbsoluteToLocal(MouseEvent.GetScreenSpacePosition()));
	const FVector2f CursorPixel = LocalPos * ViewportPixelsPerLocal(IronHexViewDetail::HexVec(MyGeometry.GetLocalSize()));
	ActiveBoard->Zoom(MouseEvent.GetWheelDelta(), FVector2D(CursorPixel.X, CursorPixel.Y));
	return FReply::Handled();
}

void SIronHexView::OnMouseLeave(const FPointerEvent& MouseEvent)
{
	SLeafWidget::OnMouseLeave(MouseEvent);
	bMouseInside = false;
	HoveredHex = IronSim::FHex{-1, -1};
	PushBoardHighlights();
	Invalidate(EInvalidateWidgetReason::Paint);
}

void SIronHexView::OnMouseCaptureLost(const FCaptureLostEvent& CaptureLostEvent)
{
	SLeafWidget::OnMouseCaptureLost(CaptureLostEvent);
	ResetPointerState();
}

FCursorReply SIronHexView::OnCursorQuery(const FGeometry& MyGeometry, const FPointerEvent& CursorEvent) const
{
	if (bDragging)
	{
		return FCursorReply::Cursor(EMouseCursor::GrabHandClosed);
	}
	return SLeafWidget::OnCursorQuery(MyGeometry, CursorEvent);
}

FReply SIronHexView::OnKeyDown(const FGeometry& MyGeometry, const FKeyEvent& InKeyEvent)
{
	if (InKeyEvent.GetKey() == EKeys::Escape && OnCancelDelegate.IsBound() && OnCancelDelegate.Execute())
	{
		return FReply::Handled();
	}
	if (InKeyEvent.GetKey() == EKeys::Home || InKeyEvent.GetKey() == EKeys::R)
	{
		if (AIronBattleBoard3D* ActiveBoard = GetActiveBoard())
		{
			// Back to the whole-board framing.
			ActiveBoard->ResetView(false);
			return FReply::Handled();
		}
	}
	return SLeafWidget::OnKeyDown(MyGeometry, InKeyEvent);
}

void SIronHexView::ResetPointerState()
{
	const bool bWasDragging = bDragging;
	bPanButtonDown = false;
	bClickPending = false;
	bDragging = false;
	if (bWasDragging)
	{
		PushBoardHighlights();
	}
}

// -------------------------------------------------------------------------------------------------
// 3D board
// -------------------------------------------------------------------------------------------------

AIronBattleBoard3D* SIronHexView::GetActiveBoard() const
{
	AIronBattleBoard3D* ActiveBoard = Board.Get();
	return (ActiveBoard != nullptr && ActiveBoard->IsBoardActive() && ActiveBoard->IsBuilt()) ? ActiveBoard : nullptr;
}

FVector2f SIronHexView::ViewportPixelsPerLocal(const FVector2f& LocalSize) const
{
	// The overlay covers the game viewport (SIronRoot fills it), so local (0, 0) is viewport pixel (0, 0) and the two
	// differ only by the DPI scale.
	const AIronBattleBoard3D* BoardActor = Board.Get();
	UWorld* BoardWorld = BoardActor != nullptr ? BoardActor->GetWorld() : nullptr;
	UGameViewportClient* GameViewport = BoardWorld != nullptr ? BoardWorld->GetGameViewport() : nullptr;
	FVector2D ViewportSize = FVector2D::ZeroVector;
	if (GameViewport != nullptr)
	{
		GameViewport->GetViewportSize(ViewportSize);
	}
	if (ViewportSize.X < 1.0 || ViewportSize.Y < 1.0 || LocalSize.X < 1.0f || LocalSize.Y < 1.0f)
	{
		return FVector2f(1.0f, 1.0f);
	}
	return FVector2f(static_cast<float>(ViewportSize.X) / LocalSize.X, static_cast<float>(ViewportSize.Y) / LocalSize.Y);
}

IronSim::FHex SIronHexView::PickBoardHex(const FVector2f& LocalPos, const FVector2f& LocalSize) const
{
	const IronSim::FHex NoHex = {-1, -1};
	const AIronBattleBoard3D* ActiveBoard = GetActiveBoard();
	if (ActiveBoard == nullptr || !Battle.IsValid())
	{
		return NoHex;
	}
	const FVector2f Pixel = LocalPos * ViewportPixelsPerLocal(LocalSize);
	IronSim::FHex Picked = NoHex;
	if (!ActiveBoard->PickHex(FVector2D(Pixel.X, Pixel.Y), Picked) || !Battle->InBounds(Picked))
	{
		return NoHex;
	}
	return Picked;
}

void SIronHexView::UpdateBoardHover(const FVector2f& LocalSize)
{
	AIronBattleBoard3D* ActiveBoard = GetActiveBoard();
	if (ActiveBoard == nullptr)
	{
		return;
	}
	const IronSim::FHex NewHover = (bMouseInside && !bDragging) ? PickBoardHex(MouseLocal, LocalSize) : IronSim::FHex{-1, -1};
	if (NewHover != HoveredHex)
	{
		HoveredHex = NewHover;
		ActiveBoard->SetHoveredHex(HoveredHex);
	}
}

void SIronHexView::PushBoardHighlights()
{
	AIronBattleBoard3D* ActiveBoard = GetActiveBoard();
	if (ActiveBoard == nullptr)
	{
		return;
	}
	FIronBoardHighlights BoardHighlights;
	BoardHighlights.Reachable = Highlights.Reachable;
	BoardHighlights.AttackTargets = Highlights.AttackTargets;
	BoardHighlights.TacticTargets = Highlights.TacticTargets;
	BoardHighlights.DuelTargets = Highlights.DuelTargets;
	BoardHighlights.SelectedUnit = Highlights.SelectedUnit;
	BoardHighlights.HoveredHex = (bMouseInside && !bDragging && Battle.IsValid() && Battle->InBounds(HoveredHex)) ? HoveredHex : IronSim::FHex{-1, -1};
	ActiveBoard->SetHighlights(BoardHighlights);
}

void SIronHexView::GetFreeArea(const FVector2f& LocalSize, FVector2f& OutMin, FVector2f& OutMax) const
{
	OutMin = FVector2f(0.0f, 0.0f);
	OutMax = LocalSize;
	if (!IsBoardMode())
	{
		return;
	}
	const FVector2f FreeMin(LocalSize.X * CoveredInsets.Left, LocalSize.Y * CoveredInsets.Top);
	const FVector2f FreeMax(LocalSize.X * (1.0f - CoveredInsets.Right), LocalSize.Y * (1.0f - CoveredInsets.Bottom));
	// Panels covering nearly everything (a tiny window): use the whole widget.
	if (FreeMax.X - FreeMin.X >= 240.0f && FreeMax.Y - FreeMin.Y >= 160.0f)
	{
		OutMin = FreeMin;
		OutMax = FreeMax;
	}
}

// -------------------------------------------------------------------------------------------------
// Painting
// -------------------------------------------------------------------------------------------------

void SIronHexView::DrawImage(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FSlateBrush* Brush, const FVector2f& Center, const FVector2f& Size, const FLinearColor& Tint) const
{
	if (Brush == nullptr)
	{
		return;
	}
	FSlateDrawElement::MakeBox(OutDrawElements, Layer, Geometry.ToPaintGeometry(Size, FSlateLayoutTransform(Center - Size * 0.5f)), Brush, ESlateDrawEffect::None, Tint);
}

void SIronHexView::DrawRect(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& TopLeft, const FVector2f& Size, const FLinearColor& Color) const
{
	if (Size.X <= 0.0f || Size.Y <= 0.0f)
	{
		return;
	}
	FSlateDrawElement::MakeBox(OutDrawElements, Layer, Geometry.ToPaintGeometry(Size, FSlateLayoutTransform(TopLeft)), FIronAssets::Get().White(), ESlateDrawEffect::None, Color);
}

void SIronHexView::DrawHexOutline(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& Center, float Radius, const FLinearColor& Color, float Thickness) const
{
	TArray<FVector2f> Points;
	Points.Reserve(7);
	for (int32 Corner = 0; Corner <= 6; ++Corner)
	{
		const float Angle = FMath::DegreesToRadians(60.0f * static_cast<float>(Corner % 6));
		Points.Add(Center + FVector2f(FMath::Cos(Angle) * Radius, FMath::Sin(Angle) * Radius));
	}
	FSlateDrawElement::MakeLines(OutDrawElements, Layer, Geometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, Color, true, Thickness);
}

void SIronHexView::DrawStar(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& Center, float Radius) const
{
	TArray<FVector2f> Points;
	Points.Reserve(11);
	for (int32 Corner = 0; Corner <= 10; ++Corner)
	{
		const float Angle = FMath::DegreesToRadians(-90.0f + 36.0f * static_cast<float>(Corner % 10));
		const float Distance = (Corner % 2 == 0) ? Radius : Radius * 0.45f;
		Points.Add(Center + FVector2f(FMath::Cos(Angle) * Distance, FMath::Sin(Angle) * Distance));
	}
	FSlateDrawElement::MakeLines(OutDrawElements, Layer, Geometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, FLinearColor(0.02f, 0.015f, 0.01f, 0.9f), true, FMath::Max(2.5f, Radius * 0.45f));
	FSlateDrawElement::MakeLines(OutDrawElements, Layer + 1, Geometry.ToPaintGeometry(), Points, ESlateDrawEffect::None, IronStyle::Gold(), true, FMath::Max(1.5f, Radius * 0.22f));
}

void SIronHexView::DrawBar(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& Center, const FVector2f& Size, float Fraction, const FLinearColor& FillColor) const
{
	const FVector2f TopLeft = Center - Size * 0.5f;
	DrawRect(OutDrawElements, Layer, Geometry, TopLeft - FVector2f(1.0f, 1.0f), Size + FVector2f(2.0f, 2.0f), FLinearColor(0.0f, 0.0f, 0.0f, 0.8f));
	const float Clamped = FMath::Clamp(Fraction, 0.0f, 1.0f);
	DrawRect(OutDrawElements, Layer + 1, Geometry, TopLeft, FVector2f(Size.X * Clamped, Size.Y), FillColor);
}

void SIronHexView::DrawCenteredText(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FString& Text, const FSlateFontInfo& Font, const FVector2f& Center, const FLinearColor& Color) const
{
	if (Text.IsEmpty() || !FSlateApplication::IsInitialized())
	{
		return;
	}
	const TSharedRef<FSlateFontMeasure> FontMeasure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
	const FVector2f TextSize = IronHexViewDetail::HexVec(FontMeasure->Measure(Text, Font));
	const FVector2f TopLeft = Center - TextSize * 0.5f;
	const FLinearColor ShadowColor(0.0f, 0.0f, 0.0f, Color.A * 0.85f);
	FSlateDrawElement::MakeText(OutDrawElements, Layer, Geometry.ToPaintGeometry(TextSize, FSlateLayoutTransform(TopLeft + FVector2f(1.5f, 1.5f))), Text, Font, ESlateDrawEffect::None, ShadowColor);
	FSlateDrawElement::MakeText(OutDrawElements, Layer + 1, Geometry.ToPaintGeometry(TextSize, FSlateLayoutTransform(TopLeft)), Text, Font, ESlateDrawEffect::None, Color);
}

void SIronHexView::DrawBanner(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& AreaMin, const FVector2f& AreaMax, double Now) const
{
	namespace Detail = IronHexViewDetail;
	const float BannerAge = static_cast<float>(Now - BannerStart);
	if (BannerText.IsEmpty() || BannerAge < 0.0f || BannerAge >= Detail::BannerSeconds)
	{
		return;
	}
	const float FadeIn = FMath::Clamp(BannerAge / 0.15f, 0.0f, 1.0f);
	const float FadeOut = FMath::Clamp((Detail::BannerSeconds - BannerAge) / 0.5f, 0.0f, 1.0f);
	const float BannerAlpha = FMath::Min(FadeIn, FadeOut);
	const float BandHeight = 64.0f;
	const float BandWidth = AreaMax.X - AreaMin.X;
	const float BandCenterY = AreaMin.Y + (AreaMax.Y - AreaMin.Y) * 0.42f;
	const FVector2f BandPos(AreaMin.X, BandCenterY - BandHeight * 0.5f);
	DrawRect(OutDrawElements, Layer, Geometry, BandPos, FVector2f(BandWidth, BandHeight), Detail::HexWithAlpha(IronStyle::Night(), 0.7f * BannerAlpha));
	DrawRect(OutDrawElements, Layer, Geometry, BandPos, FVector2f(BandWidth, 2.0f), Detail::HexWithAlpha(IronStyle::Gold(), BannerAlpha));
	DrawRect(OutDrawElements, Layer, Geometry, BandPos + FVector2f(0.0f, BandHeight - 2.0f), FVector2f(BandWidth, 2.0f), Detail::HexWithAlpha(IronStyle::Gold(), BannerAlpha));
	DrawCenteredText(OutDrawElements, Layer + 1, Geometry, BannerText.ToString(), IronStyle::Heading(34.0f), FVector2f(AreaMin.X + BandWidth * 0.5f, BandCenterY), Detail::HexWithAlpha(IronStyle::Gold(), BannerAlpha));
}

void SIronHexView::BuildTooltipLines(TArray<FTipLine>& OutLines) const
{
	const FLinearColor Light = IronStyle::TextLight();
	const IronSim::FBattleSetup& BattleSetup = Battle->GetSetup();
	const FIronSession* SessionPtr = Session.Get();

	const int32 UnitId = Battle->UnitAt(HoveredHex);
	if (IsValidUnit(UnitId) && Battle->Unit(UnitId).IsActive())
	{
		const IronSim::FBattleUnit& HoverUnit = Battle->Unit(UnitId);
		OutLines.Add({IronUI::ToFString(IronBattleUI::UnitName(SessionPtr, HoverUnit)), IronStyle::Gold(), true});
		OutLines.Add({IronUI::LocF("ui.battle.tip.sideType", "{type} ({side})", {{"type", IronSim::DisplayName(HoverUnit.Setup.Type)}, {"side", IronBattleUI::SideName(SessionPtr, BattleSetup, HoverUnit.Side)}}).ToString(), Light, false});
		OutLines.Add({IronUI::LocF("ui.battle.tip.troops", "Troops {troops} / {max}", {{"troops", IronSim::ToText(HoverUnit.Troops)}, {"max", IronSim::ToText(HoverUnit.StartTroops)}}).ToString(), Light, false});
		OutLines.Add({IronUI::LocF("ui.battle.tip.morale", "Morale {morale}", {{"morale", IronSim::ToText(HoverUnit.Morale)}}).ToString(), Light, false});
		if (HoverUnit.bCommander)
		{
			OutLines.Add({IronUI::Loc("ui.battle.tip.commander", "Commander").ToString(), IronStyle::Gold(), false});
		}
		if (HoverUnit.ConfusedDays > 0)
		{
			OutLines.Add({IronUI::LocF("ui.battle.tip.confused", "Confused ({days})", {{"days", IronSim::ToText(HoverUnit.ConfusedDays)}}).ToString(), FLinearColor(0.8f, 0.55f, 1.0f, 1.0f), false});
		}
		const int32 Acting = Highlights.ActingUnit;
		if (IsValidUnit(Acting) && (Highlights.bTacticPreview || Acting != UnitId))
		{
			if (Highlights.bTacticPreview && Highlights.TacticTargets.Contains(HoveredHex))
			{
				const int32 Chance = Battle->TacticChance(Acting, Highlights.PreviewTactic, UnitId);
				OutLines.Add({IronUI::LocF("ui.battle.tip.chance", "{tactic}: {chance}% chance", {{"tactic", IronSim::DisplayName(Highlights.PreviewTactic)}, {"chance", IronSim::ToText(Chance)}}).ToString(), FLinearColor(0.8f, 0.55f, 1.0f, 1.0f), true});
			}
			else if (!Highlights.bTacticPreview && Highlights.AttackTargets.Contains(HoveredHex))
			{
				const int32 Damage = Battle->PreviewDamage(Acting, UnitId);
				OutLines.Add({IronUI::LocF("ui.battle.tip.expected", "Attack: about {damage} enemy losses", {{"damage", IronSim::ToText(Damage)}}).ToString(), FLinearColor(1.0f, 0.45f, 0.35f, 1.0f), true});
			}
		}
	}

	const IronSim::EHexTerrain Terrain = Battle->TerrainAt(HoveredHex);
	const int32 DefenseSide = (IsValidUnit(UnitId) && Battle->Unit(UnitId).IsActive()) ? Battle->Unit(UnitId).Side : TooltipDefenseSide();
	const int32 Defense = Battle->TerrainDefenseBonus(HoveredHex, DefenseSide);
	if (IronBattleUI::IsImpassableTerrain(Terrain))
	{
		OutLines.Add({IronUI::LocF("ui.battle.tip.terrainImpassable", "{terrain}: impassable", {{"terrain", IronSim::DisplayName(Terrain)}}).ToString(), Light, false});
	}
	else
	{
		OutLines.Add({IronUI::LocF("ui.battle.tip.terrain", "{terrain}: defense {defense}%", {{"terrain", IronSim::DisplayName(Terrain)}, {"defense", IronHexViewDetail::SignedPercent(Defense)}}).ToString(), Light, false});
	}
	const int32 BurnDays = Battle->BurningAt(HoveredHex);
	if (BurnDays > 0)
	{
		OutLines.Add({IronUI::LocF("ui.battle.tip.burning", "Burning ({days} days)", {{"days", IronSim::ToText(BurnDays)}}).ToString(), FLinearColor(1.0f, 0.55f, 0.2f, 1.0f), false});
	}
	const int32 HoveredGate = GateIndexAt(HoveredHex);
	if (HoveredGate >= 0 && Battle->GateMaxHp() > 0)
	{
		OutLines.Add({IronUI::LocF("ui.battle.tip.gate", "Gate {hp} / {max}", {{"hp", IronSim::ToText(Battle->GateHpAt(HoveredGate))}, {"max", IronSim::ToText(Battle->GateMaxHp())}}).ToString(), IronStyle::Gold(), false});
	}
}

int32 SIronHexView::DrawTooltip(FSlateWindowElementList& OutDrawElements, int32 Layer, const FGeometry& Geometry, const FVector2f& AreaMin, const FVector2f& AreaMax) const
{
	if (!bMouseInside || bDragging || !Battle->InBounds(HoveredHex) || !FSlateApplication::IsInitialized())
	{
		return Layer;
	}
	TArray<FTipLine> Lines;
	BuildTooltipLines(Lines);
	if (Lines.Num() == 0)
	{
		return Layer;
	}

	const TSharedRef<FSlateFontMeasure> FontMeasure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
	const FSlateFontInfo RegularFont = IronStyle::Body(14.0f);
	const FSlateFontInfo BoldFont = IronStyle::BodyBold(15.0f);
	constexpr float Padding = 10.0f;
	constexpr float LineGap = 2.0f;

	TArray<FVector2f> LineSizes;
	LineSizes.Reserve(Lines.Num());
	float Width = 0.0f;
	float Height = 0.0f;
	for (const FTipLine& Line : Lines)
	{
		const FVector2f LineSize = IronHexViewDetail::HexVec(FontMeasure->Measure(Line.Text, Line.bBold ? BoldFont : RegularFont));
		LineSizes.Add(LineSize);
		Width = FMath::Max(Width, LineSize.X);
		Height += LineSize.Y + LineGap;
	}
	const FVector2f BoxSize(Width + Padding * 2.0f, Height - LineGap + Padding * 2.0f);
	FVector2f BoxPos = MouseLocal + FVector2f(22.0f, 22.0f);
	if (BoxPos.X + BoxSize.X > AreaMax.X - 4.0f)
	{
		BoxPos.X = MouseLocal.X - BoxSize.X - 12.0f;
	}
	if (BoxPos.Y + BoxSize.Y > AreaMax.Y - 4.0f)
	{
		BoxPos.Y = AreaMax.Y - BoxSize.Y - 4.0f;
	}
	BoxPos.X = FMath::Max(BoxPos.X, AreaMin.X + 4.0f);
	BoxPos.Y = FMath::Max(BoxPos.Y, AreaMin.Y + 4.0f);

	DrawRect(OutDrawElements, Layer, Geometry, BoxPos, BoxSize, IronHexViewDetail::HexWithAlpha(IronStyle::Night(), 0.94f));
	TArray<FVector2f> Border;
	Border.Add(BoxPos);
	Border.Add(BoxPos + FVector2f(BoxSize.X, 0.0f));
	Border.Add(BoxPos + BoxSize);
	Border.Add(BoxPos + FVector2f(0.0f, BoxSize.Y));
	Border.Add(BoxPos);
	FSlateDrawElement::MakeLines(OutDrawElements, Layer + 1, Geometry.ToPaintGeometry(), Border, ESlateDrawEffect::None, IronStyle::Gold(), true, 1.5f);

	float CursorY = BoxPos.Y + Padding;
	for (int32 LineIndex = 0; LineIndex < Lines.Num(); ++LineIndex)
	{
		const FTipLine& Line = Lines[LineIndex];
		const FVector2f& LineSize = LineSizes[LineIndex];
		FSlateDrawElement::MakeText(OutDrawElements, Layer + 1, Geometry.ToPaintGeometry(LineSize, FSlateLayoutTransform(FVector2f(BoxPos.X + Padding, CursorY))), Line.Text, Line.bBold ? BoldFont : RegularFont, ESlateDrawEffect::None, Line.Color);
		CursorY += LineSize.Y + LineGap;
	}
	return Layer + 1;
}

int32 SIronHexView::OnPaint(const FPaintArgs& /*Args*/, const FGeometry& AllottedGeometry, const FSlateRect& /*MyCullingRect*/, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FWidgetStyle& /*InWidgetStyle*/, bool /*bParentEnabled*/) const
{
	namespace Detail = IronHexViewDetail;
	const double Now = TimelineNow();
	if (const AIronBattleBoard3D* ActiveBoard = GetActiveBoard())
	{
		// The 3D board draws the terrain, highlights, units and effects: this widget only adds the overlay.
		return PaintBoardOverlay(*ActiveBoard, OutDrawElements, LayerId, AllottedGeometry, Now);
	}
	const FVector2f LocalSize = Detail::HexVec(AllottedGeometry.GetLocalSize());
	const float Time = static_cast<float>(FMath::Fmod(Now, 3600.0));

	const int32 BackgroundLayer = LayerId;
	const int32 TerrainLayer = LayerId + 1;
	const int32 OverlayLayer = LayerId + 2;
	const int32 HighlightLayer = LayerId + 3;
	const int32 RingLayer = LayerId + 4;
	const int32 BaseLayer = LayerId + 6;
	const int32 FigureLayer = LayerId + 7;
	const int32 MarkLayer = LayerId + 8;
	const int32 FxLayer = LayerId + 11;
	const int32 TextLayer = LayerId + 12;
	const int32 BannerLayer = LayerId + 14;
	const int32 TooltipLayer = LayerId + 17;

	// War-table background, scaled to cover the widget.
	if (const FSlateBrush* BackgroundBrush = ArtBrush(BackgroundArt))
	{
		FVector2f ImageSize = Detail::HexVec(FIronAssets::Get().ImageSize(BackgroundArt.Path));
		if (ImageSize.X < 1.0f || ImageSize.Y < 1.0f)
		{
			ImageSize = FVector2f(1920.0f, 1080.0f);
		}
		const float Cover = FMath::Max(LocalSize.X / ImageSize.X, LocalSize.Y / ImageSize.Y);
		DrawImage(OutDrawElements, BackgroundLayer, AllottedGeometry, BackgroundBrush, LocalSize * 0.5f, ImageSize * Cover, FLinearColor::White);
	}
	else
	{
		DrawRect(OutDrawElements, BackgroundLayer, AllottedGeometry, FVector2f(0.0f, 0.0f), LocalSize, IronStyle::Night());
	}

	if (!Battle.IsValid() || Battle->Cols() <= 0 || Battle->Rows() <= 0)
	{
		return BackgroundLayer;
	}

	const IronSim::FBattleSetup& BattleSetup = Battle->GetSetup();
	const FBoardLayout Layout = ComputeLayout(LocalSize);
	const float HexW = Detail::HexRadius * 2.0f * Layout.Scale;
	const float HexH = Detail::HexHeight * Layout.Scale;
	const FVector2f TileSize(HexW + 0.5f, HexH + 0.5f);
	const FSlateBrush* FillBrush = ArtBrush(FillArt);
	const FSlateBrush* OutlineBrush = ArtBrush(OutlineArt);

	// Terrain tiles and burning overlays.
	const FSlateBrush* FireBrush = ArtBrush(FireArt);
	for (int32 Row = 0; Row < Battle->Rows(); ++Row)
	{
		for (int32 Col = 0; Col < Battle->Cols(); ++Col)
		{
			const IronSim::FHex Hex = {Col, Row};
			const FVector2f Center = Layout.ToLocal(HexCenter(Hex));
			const IronSim::EHexTerrain Terrain = Battle->TerrainAt(Hex);
			const int32 TerrainIndex = static_cast<int32>(Terrain);
			const FSlateBrush* TileBrush = (TerrainIndex >= 0 && TerrainIndex < static_cast<int32>(IronSim::EHexTerrain::Count)) ? ArtBrush(TerrainArt[TerrainIndex]) : nullptr;
			if (TileBrush != nullptr)
			{
				DrawImage(OutDrawElements, TerrainLayer, AllottedGeometry, TileBrush, Center, TileSize, FLinearColor::White);
			}
			else
			{
				const FVector2f InnerSize(HexW * 0.5f, HexH);
				DrawRect(OutDrawElements, TerrainLayer, AllottedGeometry, Center - InnerSize * 0.5f, InnerSize, Detail::FallbackTerrainColor(Terrain));
				DrawHexOutline(OutDrawElements, TerrainLayer, AllottedGeometry, Center, HexW * 0.5f, Detail::FallbackTerrainColor(Terrain), FMath::Max(1.0f, HexW * 0.2f));
			}

			if (Battle->BurningAt(Hex) > 0)
			{
				const float Flicker = 0.75f + 0.25f * FMath::Sin(Time * 9.0f + static_cast<float>(Col * 3 + Row * 7));
				if (FireBrush != nullptr)
				{
					DrawImage(OutDrawElements, OverlayLayer, AllottedGeometry, FireBrush, Center, FVector2f(HexH * 0.85f, HexH * 0.85f), FLinearColor(1.0f, 1.0f, 1.0f, Flicker));
				}
				else
				{
					DrawHexOutline(OutDrawElements, OverlayLayer, AllottedGeometry, Center, HexW * 0.42f, FLinearColor(1.0f, 0.4f, 0.05f, Flicker), 3.0f);
				}
			}
		}
	}

	// Highlights.
	const float Pulse = 0.85f + 0.15f * FMath::Sin(Time * 4.0f);
	const auto DrawHexSet = [&](const TArray<IronSim::FHex>& HexSet, const FLinearColor& SetColor)
	{
		for (const IronSim::FHex& SetHex : HexSet)
		{
			if (!Battle->InBounds(SetHex))
			{
				continue;
			}
			const FVector2f SetCenter = Layout.ToLocal(HexCenter(SetHex));
			FLinearColor Tint = SetColor;
			Tint.A = SetColor.A * Pulse * (SetHex == HoveredHex ? 1.5f : 1.0f);
			if (FillBrush != nullptr)
			{
				DrawImage(OutDrawElements, HighlightLayer, AllottedGeometry, FillBrush, SetCenter, TileSize, Tint);
			}
			else
			{
				const FVector2f InnerSize(HexW * 0.5f, HexH * 0.9f);
				DrawRect(OutDrawElements, HighlightLayer, AllottedGeometry, SetCenter - InnerSize * 0.5f, InnerSize, Tint);
			}
		}
	};
	DrawHexSet(Highlights.Reachable, FLinearColor(0.25f, 0.55f, 1.0f, 0.35f));
	DrawHexSet(Highlights.AttackTargets, FLinearColor(0.95f, 0.15f, 0.1f, 0.42f));
	DrawHexSet(Highlights.TacticTargets, FLinearColor(0.62f, 0.3f, 0.9f, 0.42f));
	DrawHexSet(Highlights.DuelTargets, FLinearColor(1.0f, 0.55f, 0.1f, 0.42f));

	// Hover and selection rings.
	if (bMouseInside && Battle->InBounds(HoveredHex))
	{
		const FVector2f HoverCenter = Layout.ToLocal(HexCenter(HoveredHex));
		if (OutlineBrush != nullptr)
		{
			DrawImage(OutDrawElements, RingLayer, AllottedGeometry, OutlineBrush, HoverCenter, TileSize, FLinearColor(1.0f, 1.0f, 1.0f, 0.45f));
		}
		else
		{
			DrawHexOutline(OutDrawElements, RingLayer, AllottedGeometry, HoverCenter, HexW * 0.48f, FLinearColor(1.0f, 1.0f, 1.0f, 0.45f), 2.0f);
		}
	}
	if (IsValidUnit(Highlights.SelectedUnit) && Battle->Unit(Highlights.SelectedUnit).IsActive())
	{
		const FVector2f SelectedCenter = Layout.ToLocal(UnitBoardPos(Highlights.SelectedUnit, Now));
		const FLinearColor RingColor = Detail::HexWithAlpha(IronStyle::Gold(), 0.75f + 0.25f * Pulse);
		if (OutlineBrush != nullptr)
		{
			DrawImage(OutDrawElements, RingLayer + 1, AllottedGeometry, OutlineBrush, SelectedCenter, TileSize, RingColor);
		}
		else
		{
			DrawHexOutline(OutDrawElements, RingLayer + 1, AllottedGeometry, SelectedCenter, HexW * 0.48f, RingColor, 3.0f);
		}
	}

	// Gate hit points (great cities have two gates).
	for (int32 GateIndex = 0; GateIndex < Battle->GateCount() && Battle->GateMaxHp() > 0; ++GateIndex)
	{
		const IronSim::FHex GatePos = Battle->GateHexAt(GateIndex);
		const int32 GateHitPoints = Battle->GateHpAt(GateIndex);
		if (GateHitPoints <= 0 || !Battle->InBounds(GatePos))
		{
			continue;
		}
		const float GateFraction = static_cast<float>(GateHitPoints) / static_cast<float>(Battle->GateMaxHp());
		const FVector2f BarCenter = Layout.ToLocal(HexCenter(GatePos)) + FVector2f(0.0f, -HexH * 0.38f);
		DrawBar(OutDrawElements, RingLayer, AllottedGeometry, BarCenter, FVector2f(HexW * 0.6f, FMath::Max(4.0f, HexH * 0.07f)), GateFraction, GateFraction > 0.3f ? IronStyle::Gold() : IronStyle::Danger());
	}

	// Units.
	const std::vector<IronSim::FBattleUnit>& AllUnits = Battle->Units();
	const float UnitSize = HexH * 0.86f;
	const FSlateBrush* BaseBrush = ArtBrush(UnitBaseArt);
	const FSlateBrush* ConfuseBrush = ArtBrush(ConfuseArt);
	const FSlateFontInfo SmallFont = IronStyle::BodyBold(FMath::Clamp(11.0f * Layout.Scale * 1.2f, 8.0f, 13.0f));
	for (int32 UnitIndex = 0; UnitIndex < static_cast<int32>(AllUnits.size()); ++UnitIndex)
	{
		const IronSim::FBattleUnit& BoardUnit = AllUnits[static_cast<size_t>(UnitIndex)];
		if (!BoardUnit.IsActive())
		{
			continue;
		}
		const FVector2f Center = Layout.ToLocal(UnitBoardPos(UnitIndex, Now));
		const bool bDimmed = BoardUnit.bActed && BoardUnit.Side == Battle->ActiveSide() && !Battle->IsOver();
		const FLinearColor Grey(0.45f, 0.45f, 0.45f, 1.0f);
		FLinearColor BaseTint = IronBattleUI::SideColor(BattleSetup, BoardUnit.Side);
		if (bDimmed)
		{
			BaseTint = BaseTint * 0.35f + Grey * 0.65f;
		}
		const FVector2f BaseCenter = Center + FVector2f(0.0f, UnitSize * 0.05f);
		if (BaseBrush != nullptr)
		{
			DrawImage(OutDrawElements, BaseLayer, AllottedGeometry, BaseBrush, BaseCenter, FVector2f(UnitSize, UnitSize), BaseTint);
		}
		else
		{
			const FVector2f DiscSize(UnitSize * 0.7f, UnitSize * 0.7f);
			DrawRect(OutDrawElements, BaseLayer, AllottedGeometry, BaseCenter - DiscSize * 0.5f, DiscSize, BaseTint);
		}

		const int32 TypeIndex = FMath::Clamp(static_cast<int32>(BoardUnit.Setup.Type), 0, 2);
		if (const FSlateBrush* FigureBrush = ArtBrush(UnitArt[TypeIndex]))
		{
			DrawImage(OutDrawElements, FigureLayer, AllottedGeometry, FigureBrush, Center - FVector2f(0.0f, UnitSize * 0.04f), FVector2f(UnitSize, UnitSize), bDimmed ? Grey : FLinearColor::White);
		}
		else
		{
			DrawCenteredText(OutDrawElements, FigureLayer, AllottedGeometry, IronUI::ToFString(IronSim::DisplayName(BoardUnit.Setup.Type)).Left(1), IronStyle::Heading(FMath::Max(10.0f, UnitSize * 0.4f)), Center, bDimmed ? Grey : FLinearColor::White);
		}

		if (BoardUnit.bCommander)
		{
			DrawStar(OutDrawElements, MarkLayer, AllottedGeometry, Center + FVector2f(-UnitSize * 0.36f, -UnitSize * 0.34f), FMath::Max(5.0f, UnitSize * 0.13f));
		}

		const float TroopFraction = BoardUnit.StartTroops > 0 ? static_cast<float>(BoardUnit.Troops) / static_cast<float>(BoardUnit.StartTroops) : 0.0f;
		const FVector2f BarSize(HexW * 0.5f, FMath::Max(3.0f, HexH * 0.06f));
		const FVector2f BarCenter = Center + FVector2f(0.0f, HexH * 0.37f);
		DrawBar(OutDrawElements, MarkLayer, AllottedGeometry, BarCenter, BarSize, TroopFraction, Detail::TroopBarColor(TroopFraction));
		if (Layout.Scale >= 0.7f)
		{
			DrawCenteredText(OutDrawElements, MarkLayer, AllottedGeometry, FString::FromInt(BoardUnit.Troops), SmallFont, BarCenter - FVector2f(0.0f, BarSize.Y + 7.0f), FLinearColor::White);
		}

		if (BoardUnit.ConfusedDays > 0)
		{
			const float Bob = FMath::Sin(Time * 3.0f + static_cast<float>(UnitIndex)) * 3.0f * Layout.Scale;
			const FVector2f SwirlCenter = Center + FVector2f(0.0f, -UnitSize * 0.42f + Bob);
			if (ConfuseBrush != nullptr)
			{
				DrawImage(OutDrawElements, MarkLayer + 2, AllottedGeometry, ConfuseBrush, SwirlCenter, FVector2f(UnitSize * 0.5f, UnitSize * 0.5f), FLinearColor(1.0f, 1.0f, 1.0f, 0.92f));
			}
			else
			{
				DrawCenteredText(OutDrawElements, MarkLayer + 2, AllottedGeometry, TEXT("?"), IronStyle::Heading(FMath::Max(12.0f, UnitSize * 0.35f)), SwirlCenter, FLinearColor(0.8f, 0.55f, 1.0f, 1.0f));
			}
		}
	}

	// Effects.
	for (const FHexFx& Effect : ActiveFx)
	{
		const float Alpha = static_cast<float>((Now - Effect.Start) / FMath::Max(0.05f, Effect.Duration));
		if (Alpha < 0.0f || Alpha > 1.0f)
		{
			continue;
		}
		const FVector2f Center = Layout.ToLocal(Effect.BoardPos);
		const float EffectSize = HexH * (0.75f + 0.35f * Alpha);
		const FLinearColor Tint(1.0f, 1.0f, 1.0f, 1.0f - Alpha * Alpha);
		const FSlateBrush* EffectBrush = nullptr;
		switch (Effect.Kind)
		{
		case EFxKind::Hit:
			EffectBrush = ArtBrush(HitArt);
			break;
		case EFxKind::Fire:
			EffectBrush = FireBrush;
			break;
		case EFxKind::Confuse:
			EffectBrush = ConfuseBrush;
			break;
		case EFxKind::Rally:
			EffectBrush = ArtBrush(RallyArt);
			break;
		}
		if (EffectBrush != nullptr)
		{
			DrawImage(OutDrawElements, FxLayer, AllottedGeometry, EffectBrush, Center, FVector2f(EffectSize, EffectSize), Tint);
		}
		else
		{
			DrawHexOutline(OutDrawElements, FxLayer, AllottedGeometry, Center, EffectSize * 0.5f, FLinearColor(1.0f, 0.85f, 0.4f, Tint.A), 3.0f);
		}
	}

	// Floating numbers.
	for (const FFloatText& Floating : FloatingTexts)
	{
		const float Alpha = static_cast<float>((Now - Floating.Start) / FMath::Max(0.05f, Floating.Duration));
		if (Alpha < 0.0f || Alpha > 1.0f)
		{
			continue;
		}
		const FVector2f Center = Layout.ToLocal(Floating.BoardPos) + FVector2f(0.0f, -HexH * 0.3f - Alpha * HexH * 0.45f);
		const FLinearColor TextColor = Detail::HexWithAlpha(Floating.Color, Floating.Color.A * (1.0f - Alpha * Alpha * Alpha));
		const FSlateFontInfo FloatFont = IronStyle::BodyBold(FMath::Max(11.0f, Floating.FontSize * FMath::Clamp(Layout.Scale * 1.3f, 0.7f, 1.4f)));
		DrawCenteredText(OutDrawElements, TextLayer, AllottedGeometry, Floating.Text, FloatFont, Center, TextColor);
	}

	// Day banner.
	DrawBanner(OutDrawElements, BannerLayer, AllottedGeometry, FVector2f(0.0f, 0.0f), LocalSize, Now);

	return DrawTooltip(OutDrawElements, TooltipLayer, AllottedGeometry, FVector2f(0.0f, 0.0f), LocalSize);
}

int32 SIronHexView::PaintBoardOverlay(const AIronBattleBoard3D& ActiveBoard, FSlateWindowElementList& OutDrawElements, int32 LayerId, const FGeometry& Geometry, double Now) const
{
	namespace Detail = IronHexViewDetail;
	const FVector2f LocalSize = Detail::HexVec(Geometry.GetLocalSize());
	const int32 PlateLayer = LayerId;
	const int32 FloatLayer = LayerId + 5;
	const int32 BannerLayer = LayerId + 7;
	const int32 TooltipLayer = LayerId + 10;
	FVector2f AreaMin(0.0f, 0.0f);
	FVector2f AreaMax = LocalSize;
	GetFreeArea(LocalSize, AreaMin, AreaMax);
	if (!Battle.IsValid() || Battle->Cols() <= 0 || Battle->Rows() <= 0)
	{
		return LayerId;
	}

	// Every anchor is projected with the board's view of this frame (one snapshot, game viewport pixels).
	const FIronViewProjection& View = ActiveBoard.GetViewProjection();
	const FVector2f PixelsPerLocal = ViewportPixelsPerLocal(LocalSize);
	const auto ViewportToLocal = [&PixelsPerLocal](const FVector2D& ViewportPixel)
	{
		return FVector2f(static_cast<float>(ViewportPixel.X) / PixelsPerLocal.X, static_cast<float>(ViewportPixel.Y) / PixelsPerLocal.Y);
	};
	float HexSize = ActiveBoard.GetHexPixelSize() / PixelsPerLocal.X;
	if (HexSize < 8.0f)
	{
		HexSize = Detail::BoardNominalHexSize;
	}
	const float PlateScale = FMath::Clamp(HexSize / Detail::BoardNominalHexSize, 0.6f, 1.4f);

	// Gate hit points (great cities have two gates), just above the gatehouse as drawn (it shakes with the blows).
	for (int32 GateIndex = 0; GateIndex < Battle->GateCount() && Battle->GateMaxHp() > 0; ++GateIndex)
	{
		const IronSim::FHex GatePos = Battle->GateHexAt(GateIndex);
		const int32 GateHitPoints = Battle->GateHpAt(GateIndex);
		FVector GateTopCm = FVector::ZeroVector;
		FVector2D GatePixel = FVector2D::ZeroVector;
		if (GateHitPoints <= 0 || !Battle->InBounds(GatePos) || !ActiveBoard.GetGateTopWorldLocation(GatePos, GateTopCm)
			|| !View.Project(GateTopCm + FVector(0.0, 0.0, static_cast<double>(Detail::BoardGateBarAboveTopM) * IronWorld::CmPerMetre), GatePixel))
		{
			continue;
		}
		const float GateFraction = static_cast<float>(GateHitPoints) / static_cast<float>(Battle->GateMaxHp());
		const FVector2f GateBarSize(FMath::Max(40.0f, HexSize * 0.55f), FMath::Max(4.0f, 6.0f * PlateScale));
		DrawBar(OutDrawElements, PlateLayer + 1, Geometry, ViewportToLocal(GatePixel), GateBarSize, GateFraction, GateFraction > 0.3f ? IronStyle::Gold() : IronStyle::Danger());
	}

	// Unit plates above the animated models (ProjectUnitToViewport uses the same view snapshot): name, troop bar on a
	// side-coloured rim, troop count, commander star.
	const IronSim::FBattleSetup& BattleSetup = Battle->GetSetup();
	const float NameSize = FMath::Clamp(12.0f * PlateScale, 9.0f, 15.0f);
	const FSlateFontInfo NameFont = IronStyle::BodyBold(NameSize);
	const FSlateFontInfo CountFont = IronStyle::BodyBold(FMath::Clamp(10.5f * PlateScale, 8.0f, 13.0f));
	TSharedPtr<FSlateFontMeasure> CountMeasure;
	if (FSlateApplication::IsInitialized())
	{
		CountMeasure = FSlateApplication::Get().GetRenderer()->GetFontMeasureService();
	}
	const std::vector<IronSim::FBattleUnit>& AllUnits = Battle->Units();
	for (int32 UnitIndex = 0; UnitIndex < static_cast<int32>(AllUnits.size()); ++UnitIndex)
	{
		const IronSim::FBattleUnit& BoardUnit = AllUnits[static_cast<size_t>(UnitIndex)];
		FVector2D PlatePixel = FVector2D::ZeroVector;
		if (!BoardUnit.IsActive() || !ActiveBoard.ProjectUnitToViewport(UnitIndex, PlatePixel, Detail::BoardPlateAboveModelM))
		{
			continue;
		}
		const FVector2f Anchor = ViewportToLocal(PlatePixel);
		if (Anchor.X < -120.0f || Anchor.Y < -120.0f || Anchor.X > LocalSize.X + 120.0f || Anchor.Y > LocalSize.Y + 120.0f)
		{
			continue;
		}
		// Units that already acted this turn are dimmed, like the greyed figures of the 2D board.
		const bool bDimmed = BoardUnit.bActed && BoardUnit.Side == Battle->ActiveSide() && !Battle->IsOver();
		const float PlateAlpha = bDimmed ? 0.55f : 1.0f;
		const float TroopFraction = BoardUnit.StartTroops > 0 ? static_cast<float>(BoardUnit.Troops) / static_cast<float>(BoardUnit.StartTroops) : 0.0f;
		const FVector2f BarSize(FMath::Max(34.0f, HexSize * 0.42f), FMath::Max(4.0f, 5.0f * PlateScale));
		const FVector2f Rim(3.0f, 3.0f);
		DrawRect(OutDrawElements, PlateLayer, Geometry, Anchor - BarSize * 0.5f - Rim, BarSize + Rim * 2.0f, Detail::HexWithAlpha(IronBattleUI::SideColor(BattleSetup, BoardUnit.Side), 0.95f * PlateAlpha));
		DrawBar(OutDrawElements, PlateLayer + 1, Geometry, Anchor, BarSize, TroopFraction, Detail::HexWithAlpha(Detail::TroopBarColor(TroopFraction), PlateAlpha));

		const bool bSelected = UnitIndex == Highlights.SelectedUnit;
		const FLinearColor NameColor = Detail::HexWithAlpha(bSelected ? IronStyle::Gold() : FLinearColor::White, PlateAlpha);
		const FVector2f NameCenter = Anchor - FVector2f(0.0f, BarSize.Y * 0.5f + Rim.Y + 2.0f + NameSize * 0.75f);
		DrawCenteredText(OutDrawElements, PlateLayer + 3, Geometry, IronUI::ToFString(IronBattleUI::UnitName(Session.Get(), BoardUnit)), NameFont, NameCenter, NameColor);
		if (CountMeasure.IsValid() && PlateScale >= 0.75f)
		{
			const FString CountText = FString::FromInt(BoardUnit.Troops);
			const FVector2f CountSize = Detail::HexVec(CountMeasure->Measure(CountText, CountFont));
			DrawCenteredText(OutDrawElements, PlateLayer + 3, Geometry, CountText, CountFont, Anchor + FVector2f(BarSize.X * 0.5f + Rim.X + 3.0f + CountSize.X * 0.5f, 0.0f), Detail::HexWithAlpha(FLinearColor::White, PlateAlpha));
		}
		if (BoardUnit.bCommander)
		{
			const float StarRadius = FMath::Max(5.0f, 7.0f * PlateScale);
			DrawStar(OutDrawElements, PlateLayer + 3, Geometry, Anchor - FVector2f(BarSize.X * 0.5f + Rim.X + 3.0f + StarRadius, 0.0f), StarRadius);
		}
	}

	// Floating numbers and words, rising over their hexes (over a gate: from above the gatehouse or its rubble).
	for (const FFloatText& Floating : FloatingTexts)
	{
		const float Alpha = static_cast<float>((Now - Floating.Start) / FMath::Max(0.05f, Floating.Duration));
		if (Alpha < 0.0f || Alpha > 1.0f || !Battle->InBounds(Floating.Hex))
		{
			continue;
		}
		const float FloatHeightM = FMath::Max(Detail::BoardFloatHeightM, ActiveBoard.GetGateTopHeightM(Floating.Hex) + Detail::BoardFloatAboveGateM);
		FVector2D FloatPixel = FVector2D::ZeroVector;
		if (!View.Project(ActiveBoard.HexToWorldLocation(Floating.Hex, FloatHeightM), FloatPixel))
		{
			continue;
		}
		const float Rise = 22.0f * PlateScale * static_cast<float>(Floating.Stack) + Alpha * HexSize * 0.35f;
		const FVector2f Center = ViewportToLocal(FloatPixel) - FVector2f(0.0f, Rise);
		const FLinearColor TextColor = Detail::HexWithAlpha(Floating.Color, Floating.Color.A * (1.0f - Alpha * Alpha * Alpha));
		const FSlateFontInfo FloatFont = IronStyle::BodyBold(FMath::Max(11.0f, Floating.FontSize * FMath::Clamp(PlateScale * 1.15f, 0.75f, 1.4f)));
		DrawCenteredText(OutDrawElements, FloatLayer, Geometry, Floating.Text, FloatFont, Center, TextColor);
	}

	// Day banner and tooltip inside the part of the screen the panels leave free.
	DrawBanner(OutDrawElements, BannerLayer, Geometry, AreaMin, AreaMax, Now);
	return DrawTooltip(OutDrawElements, TooltipLayer, Geometry, AreaMin, AreaMax);
}
