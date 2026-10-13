#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "Input/Reply.h"
#include "Styling/SlateTypes.h"
#include "Widgets/Input/SButton.h"

class FIronSession;
class SButton;
class SWidget;

/**
 * Look and feel shared by all Iron Reign screens: palette (DESIGN.md section 8), culture-aware fonts,
 * button styles built from the generated 9-slice art, and small widget factories so every screen looks alike.
 */
namespace IronStyle
{
	/** Loads fonts and styles for the active culture. Called by FIronSession on startup and culture change. */
	IRONREIGN_API void Initialize(const FString& Culture);
	IRONREIGN_API void Shutdown();

	// Palette (linear colours).
	IRONREIGN_API FLinearColor Paper();
	IRONREIGN_API FLinearColor PaperDark();
	IRONREIGN_API FLinearColor Ink();
	IRONREIGN_API FLinearColor InkSoft();
	IRONREIGN_API FLinearColor Lacquer();
	IRONREIGN_API FLinearColor LacquerDark();
	IRONREIGN_API FLinearColor Gold();
	IRONREIGN_API FLinearColor Jade();
	IRONREIGN_API FLinearColor Indigo();
	IRONREIGN_API FLinearColor Night();
	/** Light text on dark panels/buttons. */
	IRONREIGN_API FLinearColor TextLight();
	IRONREIGN_API FLinearColor Danger();
	/** Faction colour or the independent grey for -1. */
	IRONREIGN_API FLinearColor FactionColor(int32 FactionIndex);

	enum class EFont : uint8
	{
		Body,
		BodyBold,
		Heading,
		/** Brush calligraphy for CJK glyphs (banners, decorative names). */
		Brush
	};

	/** Composite font for the active culture (Latin + CJK fallback). */
	IRONREIGN_API FSlateFontInfo Font(EFont Kind, float Size);
	IRONREIGN_API FSlateFontInfo Body(float Size = 15.0f);
	IRONREIGN_API FSlateFontInfo BodyBold(float Size = 15.0f);
	IRONREIGN_API FSlateFontInfo Heading(float Size = 24.0f);
	IRONREIGN_API FSlateFontInfo Brush(float Size = 24.0f);

	// Brushes and widget styles.
	IRONREIGN_API const FSlateBrush* Panel();
	IRONREIGN_API const FSlateBrush* PanelDark();
	IRONREIGN_API const FSlateBrush* Divider();
	IRONREIGN_API const FSlateBrush* WhiteBrush();
	IRONREIGN_API const FButtonStyle& Button();
	IRONREIGN_API const FButtonStyle& Tab(bool bActive);
	/** Transparent button that highlights on hover, for clickable list rows. */
	IRONREIGN_API const FButtonStyle& RowButton();
	IRONREIGN_API const FTextBlockStyle& BodyText();
	IRONREIGN_API const FTableRowStyle& TableRow();

	// Widget factories.
	IRONREIGN_API TSharedRef<SWidget> MakePanel(const TSharedRef<SWidget>& Content, bool bDark = false, const FMargin& Padding = FMargin(18.0f));
	/** Lacquer button with light text and an optional icon (Art/UI/Icon_<IconName>.png). */
	IRONREIGN_API TSharedRef<SButton> MakeButton(const TAttribute<FText>& Label, FOnClicked OnClicked, const TAttribute<bool>& IsEnabled = true, const FString& IconName = FString(), float MinWidth = 0.0f);
	IRONREIGN_API TSharedRef<SWidget> MakeHeader(const TAttribute<FText>& Text, float Size = 24.0f, bool bOnDark = false);
	IRONREIGN_API TSharedRef<SWidget> MakeLabel(const TAttribute<FText>& Text, float Size = 15.0f, const FLinearColor& Color = FLinearColor(0.02f, 0.015f, 0.01f), bool bBold = false);
	/** Horizontal value bar, Fraction 0..1. */
	IRONREIGN_API TSharedRef<SWidget> MakeBar(const TAttribute<float>& Fraction, const FLinearColor& Color, float Height = 8.0f);
	/** Portrait (Art/Portraits/<Id>.png) inside the ornamental frame, scaled to Height. */
	IRONREIGN_API TSharedRef<SWidget> MakePortrait(const TAttribute<FString>& PortraitId, float Height = 120.0f);
	/** Small icon followed by a value, e.g. gold 1200. */
	IRONREIGN_API TSharedRef<SWidget> MakeIconValue(const FString& IconName, const TAttribute<FText>& Value, float IconSize = 24.0f, const FLinearColor& TextColor = FLinearColor(0.02f, 0.015f, 0.01f));
	/** Faction banner: tinted Art/Map/Banner.png with the faction glyph in the brush font. */
	IRONREIGN_API TSharedRef<SWidget> MakeBanner(int32 FactionIndex, float Height = 64.0f);

	// ----- Additions (UE framework engineer) -----
	/** Session whose game provides faction colours and glyphs (set by FIronSession::Initialize; weakly held). */
	IRONREIGN_API void SetSession(const TSharedPtr<FIronSession>& Session);
	/** Font of a specific culture regardless of the active one (e.g. each entry of a language menu in its own script). */
	IRONREIGN_API FSlateFontInfo FontForCulture(const FString& Culture, EFont Kind, float Size);
	/** Banner for an explicit colour and glyph, e.g. scenario factions on the New Game screen before a game exists. */
	IRONREIGN_API TSharedRef<SWidget> MakeBannerFor(const FLinearColor& Color, const FText& Glyph, float Height = 64.0f);
	/** Localized banner glyph ("faction.<key>.glyph"), falling back to DefaultGlyph. */
	IRONREIGN_API FText FactionGlyph(const FString& FactionKey, const FString& DefaultGlyph);
	/** Ornamental horizontal rule (Art/UI/Divider.png, or a thin gold line when the art is missing). */
	IRONREIGN_API TSharedRef<SWidget> MakeDivider(float Height = 12.0f);
	/** Selectable pill for option rows on parchment (language, speeds): gold when bActive, ink text in LabelFont. */
	IRONREIGN_API TSharedRef<SButton> MakeChoiceButton(const FText& Label, bool bActive, FOnClicked OnClicked, const FSlateFontInfo& LabelFont);
}
