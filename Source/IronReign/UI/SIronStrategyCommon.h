#pragma once

#include "CoreMinimal.h"
#include "Sim/IronGame.h"
#include "Templates/Function.h"

class SWidget;

/**
 * Small helpers shared by the strategy screen widgets (map, city panel, command panel, dialogs, tables).
 * Every lookup is bounds checked and returns nullptr / empty text for invalid indices.
 * Never keep the returned pointers across calls that mutate the game (vectors may reallocate).
 */
namespace IronStrategy
{
	const IronSim::FOfficer* GetOfficer(const IronSim::FGameState& State, int32 Officer);
	const IronSim::FCity* GetCity(const IronSim::FGameState& State, int32 City);
	const IronSim::FFaction* GetFaction(const IronSim::FGameState& State, int32 Faction);
	const IronSim::FSect* GetSect(const IronSim::FGameState& State, int32 Sect);
	const IronSim::FTechnique* GetTechnique(const IronSim::FGameState& State, int32 Technique);

	FText OfficerName(const IronSim::FGameState& State, int32 Officer);
	FText CityName(const IronSim::FGameState& State, int32 City);
	/** Faction name, or "Independent" for -1. */
	FText FactionName(const IronSim::FGameState& State, int32 Faction);
	FText SectName(const IronSim::FGameState& State, int32 Sect);
	/** Localized banner glyph ("faction.<key>.glyph", falling back to the scenario glyph). */
	FString FactionGlyph(const IronSim::FGameState& State, int32 Faction);
	/** Portrait id of an officer ("unknown" when missing). */
	FString OfficerPortrait(const IronSim::FGameState& State, int32 Officer);
	/** Comma separated technique names. */
	FText TechniqueList(const IronSim::FGameState& State, int32 Officer);

	FText StatShort(int32 StatIndex);
	FText StatLong(int32 StatIndex);
	FText OrderName(IronSim::EOrderType Type);
	FText TroopTypeName(IronSim::ETroopType Type);
	FText CitySizeName(int32 Size);
	/** Art/UI/Icon_<Name>.png for an order. */
	FString OrderIcon(IronSim::EOrderType Type);
	/** Stat index (0..4) that governs an order, -1 when none. */
	int32 GoverningStat(IronSim::EOrderType Type);

	/** "Develop Farmland", "Recruit: Zhao Lin", "Marching to Luojing", "Idle"... */
	FText OfficerActivity(const IronSim::FGameState& State, int32 Officer);
	FText OrderSummary(const IronSim::FGameState& State, const IronSim::FOrder& Order);

	/** Grouped number ("12,000"). */
	FText Num(int32 Value);
	/** Rounded intelligence figure for foreign cities ("~12,000"). */
	FText ApproxNum(int32 Value);
	FLinearColor StatColor(int32 Value);
	FLinearColor LoyaltyColor(int32 Loyalty);
	/** True when the active culture is English (decorative Chinese names are shown next to English ones). */
	bool IsEnglishCulture();

	/** The player's advisor: the serving officer with the best Strategy (-1 if none). */
	int32 PlayerAdvisor(const IronSim::FGameState& State);

	/** The five stats as small cells; HighlightStat (0..4) gets a gold background. */
	TSharedRef<SWidget> MakeStatsRow(const IronSim::FOfficer& Officer, int32 HighlightStat, float FontSize = 13.0f);
	/** Column captions matching MakeStatsRow. */
	TSharedRef<SWidget> MakeStatsHeader(int32 HighlightStat, float FontSize = 11.0f);
	/** Section caption in heading font with a thin gold rule. */
	TSharedRef<SWidget> MakeSectionTitle(const TAttribute<FText>& Text, float Size = 17.0f);
	/** Standard parchment dialog: title, divider, body (fills), footer. Width/Height <= 0 means "size to content". */
	TSharedRef<SWidget> MakeDialogFrame(const TAttribute<FText>& Title, const TSharedRef<SWidget>& Body, const TSharedRef<SWidget>& Footer, float Width, float Height);
	/**
	 * Amount editor row: label, slider, numeric spin box and a "Max" button, clamped to 0..GetMax() and rounded to Step.
	 * ValuePtr must outlive the widget (point at a member of the owning dialog). OnChanged runs after every edit.
	 */
	TSharedRef<SWidget> MakeAmountEditor(const FText& Label, TFunction<int32()> GetMax, int32* ValuePtr, int32 Step, TFunction<void()> OnChanged = nullptr);
	/** Wrapped body text. */
	TSharedRef<SWidget> MakeWrappedText(const TAttribute<FText>& Text, float Size = 14.0f, const FLinearColor& Color = FLinearColor(0.02f, 0.015f, 0.01f));
}
