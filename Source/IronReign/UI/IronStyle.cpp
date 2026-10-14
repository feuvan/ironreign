#include "UI/IronStyle.h"

#include "IronReignLog.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronAudio.h"
#include "UI/IronSession.h"
#include "UI/IronUI.h"

#include "Brushes/SlateColorBrush.h"
#include "Brushes/SlateNoResource.h"
#include "Fonts/CompositeFont.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Styling/CoreStyle.h"
#include "Widgets/Images/SImage.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Notifications/SProgressBar.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/SOverlay.h"
#include "Widgets/Text/STextBlock.h"

#include <string>
#include <utility>

namespace IronStyleDetail
{
	constexpr int32 FontKindCount = 4;

	/** Composite fonts of one culture, indexed by IronStyle::EFont. Null entries use the engine font. */
	struct FFontSet
	{
		TSharedPtr<const FCompositeFont> Fonts[FontKindCount];
	};

	/** 9-slice margins in source pixels (DESIGN.md section 8, overridable by Art/UI/NineSlice.json). */
	struct FNineSliceMargins
	{
		FMargin Panel = FMargin(24.0f);
		FMargin PanelDark = FMargin(24.0f);
		FMargin Button = FMargin(20.0f, 16.0f);
		FMargin Tab = FMargin(16.0f, 14.0f, 16.0f, 8.0f);
	};

	struct FStyleState
	{
		bool bInitialized = false;
		FString Culture = TEXT("en");
		TMap<FString, FFontSet> FontSets;
		/** Copy of FontSets[Culture] for fast per-frame font lookups. */
		FFontSet ActiveFonts;
		TWeakPtr<FIronSession> Session;
		FNineSliceMargins Margins;

		// Everything below is referenced by pointer from live widgets: it is updated in place, never reallocated.
		FSlateBrush PanelBrush;
		FSlateBrush PanelDarkBrush;
		FSlateBrush DividerBrush;
		FButtonStyle ButtonStyle;
		FButtonStyle TabStyles[2];
		FButtonStyle RowStyle;
		FButtonStyle ChoiceStyles[2];
		FTextBlockStyle BodyTextStyle;
		FTableRowStyle TableRowStyle;
		FProgressBarStyle BarStyle;

		/** Cloth area of Art/Map/Banner.png (64x96) used for the glyph. */
		float GlyphX = 16.0f;
		float GlyphY = 10.0f;
		float GlyphW = 40.0f;
		float GlyphH = 44.0f;
	};

	FStyleState& StyleState()
	{
		// Intentionally leaked: Slate widgets keep pointers to the styles until the very end of the process.
		static FStyleState* Instance = new FStyleState();
		return *Instance;
	}

	FStyleState& ReadyState()
	{
		FStyleState& State = StyleState();
		if (!State.bInitialized)
		{
			IronStyle::Initialize(IronUI::ToFString(IronSim::FLocale::Active().Culture()));
		}
		return State;
	}

	FString NormalizedCulture(const FString& InCulture)
	{
		const FString Normalized = FIronSession::NormalizeCulture(InCulture);
		return Normalized.IsEmpty() ? FString(TEXT("en")) : Normalized;
	}

	// ---------------------------------------------------------------------------------------------
	// Fonts
	// ---------------------------------------------------------------------------------------------

	FString FontFile(const FString& FileName)
	{
		return FIronSession::DataDir() / TEXT("Fonts") / FileName;
	}

	FString CjkFontFile(const FString& Script, bool bBold)
	{
		return FontFile(FString::Printf(TEXT("CJK-%s-%s.ttf"), *Script, bBold ? TEXT("Bold") : TEXT("Regular")));
	}

	FString EngineCjkFallback()
	{
		return FPaths::EngineContentDir() / TEXT("Slate/Fonts/DroidSansFallback.ttf");
	}

	FString FirstExisting(const TArray<FString>& Candidates)
	{
		for (const FString& Candidate : Candidates)
		{
			if (!Candidate.IsEmpty() && FPaths::FileExists(Candidate))
			{
				return Candidate;
			}
		}
		return FString();
	}

	/** "SC", "TC", "JP", "KR": the CJK font family of a culture (English uses Simplified Chinese as its fallback). */
	FString CjkScript(const FString& InCulture)
	{
		if (InCulture == TEXT("zh-Hant"))
		{
			return TEXT("TC");
		}
		if (InCulture == TEXT("ja"))
		{
			return TEXT("JP");
		}
		if (InCulture == TEXT("ko"))
		{
			return TEXT("KR");
		}
		return TEXT("SC");
	}

	/** Fonts that can stand in for a culture's own CJK font while it has not been generated yet. */
	TArray<FString> CjkStandIns(const FString& InCulture, bool bBold)
	{
		const FString Script = CjkScript(InCulture);
		TArray<FString> Result;
		Result.Add(CjkFontFile(Script, bBold));
		Result.Add(CjkFontFile(Script, false));
		if (Script == TEXT("KR"))
		{
			// Hangul only exists in the Korean font and the engine's fallback font.
			Result.Add(EngineCjkFallback());
			return Result;
		}
		const TCHAR* Others[] = {TEXT("SC"), TEXT("TC"), TEXT("JP")};
		for (const TCHAR* Other : Others)
		{
			if (Script != Other)
			{
				Result.Add(CjkFontFile(Other, false));
			}
		}
		if (Script == TEXT("JP"))
		{
			// Kana are missing from the brush font.
			Result.Add(EngineCjkFallback());
			Result.Add(FontFile(TEXT("Brush.ttf")));
		}
		else
		{
			Result.Add(FontFile(TEXT("Brush.ttf")));
			Result.Add(EngineCjkFallback());
		}
		return Result;
	}

	TSharedPtr<const FCompositeFont> MakeComposite(const FName& Typeface, const FString& Primary, const FString& Fallback)
	{
		FString MainFile = Primary;
		FString BackupFile = Fallback;
		if (MainFile.IsEmpty())
		{
			MainFile = BackupFile;
			BackupFile.Empty();
		}
		if (MainFile.IsEmpty())
		{
			return nullptr;
		}
		TSharedRef<FStandaloneCompositeFont> Composite = MakeShared<FStandaloneCompositeFont>();
		Composite->DefaultTypeface.AppendFont(Typeface, MainFile, EFontHinting::Default, EFontLoadingPolicy::LazyLoad);
		if (!BackupFile.IsEmpty() && BackupFile != MainFile)
		{
			Composite->FallbackTypeface.Typeface.AppendFont(Typeface, BackupFile, EFontHinting::Default, EFontLoadingPolicy::LazyLoad);
		}
		return Composite;
	}

	FName TypefaceName(IronStyle::EFont Kind)
	{
		switch (Kind)
		{
		case IronStyle::EFont::BodyBold:
		case IronStyle::EFont::Heading:
			return FName(TEXT("Bold"));
		case IronStyle::EFont::Body:
		case IronStyle::EFont::Brush:
			return FName(TEXT("Regular"));
		}
		return FName(TEXT("Regular"));
	}

	int32 FontIndex(IronStyle::EFont Kind)
	{
		return FMath::Clamp(static_cast<int32>(Kind), 0, FontKindCount - 1);
	}

	FFontSet BuildFontSet(const FString& InCulture)
	{
		const bool bCjkCulture = InCulture != TEXT("en");
		const FString Script = CjkScript(InCulture);

		const FString LatinRegular = FirstExisting({FontFile(TEXT("Body-Regular.ttf"))});
		const FString LatinBold = FirstExisting({FontFile(TEXT("Body-Bold.ttf")), LatinRegular});
		const FString LatinHeading = FirstExisting({FontFile(TEXT("Heading.ttf")), LatinBold});
		const FString BrushFile = FirstExisting({FontFile(TEXT("Brush.ttf"))});
		const FString OwnCjkRegular = FirstExisting({CjkFontFile(Script, false)});
		const FString OwnCjkBold = FirstExisting({CjkFontFile(Script, true), OwnCjkRegular});

		FFontSet Set;
		const int32 BodyIndex = FontIndex(IronStyle::EFont::Body);
		const int32 BoldIndex = FontIndex(IronStyle::EFont::BodyBold);
		const int32 HeadingIndex = FontIndex(IronStyle::EFont::Heading);
		const int32 BrushIndex = FontIndex(IronStyle::EFont::Brush);
		const FName Regular = TypefaceName(IronStyle::EFont::Body);
		const FName Bold = TypefaceName(IronStyle::EFont::BodyBold);

		if (bCjkCulture && !OwnCjkRegular.IsEmpty())
		{
			// CJK cultures: the culture's font is the default typeface (it includes Latin), Latin fonts back it up.
			Set.Fonts[BodyIndex] = MakeComposite(Regular, OwnCjkRegular, LatinRegular);
			Set.Fonts[BoldIndex] = MakeComposite(Bold, OwnCjkBold, LatinBold);
			Set.Fonts[HeadingIndex] = MakeComposite(Bold, OwnCjkBold, LatinHeading);
		}
		else
		{
			// English (or a CJK culture whose font is not generated yet): Latin fonts with a CJK fallback.
			const FString CjkRegularFallback = bCjkCulture
				? FirstExisting(CjkStandIns(InCulture, false))
				: FirstExisting({CjkFontFile(TEXT("SC"), false), BrushFile, EngineCjkFallback()});
			const FString CjkBoldFallback = bCjkCulture
				? FirstExisting(CjkStandIns(InCulture, true))
				: FirstExisting({CjkFontFile(TEXT("SC"), true), CjkFontFile(TEXT("SC"), false), BrushFile, EngineCjkFallback()});
			Set.Fonts[BodyIndex] = MakeComposite(Regular, LatinRegular, CjkRegularFallback);
			Set.Fonts[BoldIndex] = MakeComposite(Bold, LatinBold, CjkBoldFallback);
			Set.Fonts[HeadingIndex] = MakeComposite(Bold, LatinHeading, CjkBoldFallback);
		}

		// Brush calligraphy (Chinese glyphs); the culture's own script backs it up for kana/Hangul/Latin.
		const FString BrushBackup = bCjkCulture
			? FirstExisting({OwnCjkRegular, FirstExisting(CjkStandIns(InCulture, false)), LatinRegular})
			: FirstExisting({CjkFontFile(TEXT("SC"), false), LatinRegular});
		Set.Fonts[BrushIndex] = MakeComposite(Regular, BrushFile, BrushBackup);
		return Set;
	}

	const FFontSet& FontSetFor(const FString& InCulture)
	{
		FStyleState& State = StyleState();
		const FString Key = NormalizedCulture(InCulture);
		if (const FFontSet* Found = State.FontSets.Find(Key))
		{
			return *Found;
		}
		return State.FontSets.Add(Key, BuildFontSet(Key));
	}

	FSlateFontInfo MakeFontInfo(const FFontSet& Set, IronStyle::EFont Kind, float Size)
	{
		const TSharedPtr<const FCompositeFont>& Composite = Set.Fonts[FontIndex(Kind)];
		const FName Typeface = TypefaceName(Kind);
		if (Composite.IsValid())
		{
			return FSlateFontInfo(Composite, Size, Typeface);
		}
		return FCoreStyle::GetDefaultFontStyle(Typeface, Size);
	}

	// ---------------------------------------------------------------------------------------------
	// Art configuration
	// ---------------------------------------------------------------------------------------------

	bool ParseMargin(const IronSim::FJson& Value, FMargin& OutMargin)
	{
		if (Value.IsNumber())
		{
			OutMargin = FMargin(static_cast<float>(Value.AsNumber()));
			return true;
		}
		if (Value.IsArray())
		{
			const size_t Count = Value.Size();
			if (Count == 1)
			{
				OutMargin = FMargin(static_cast<float>(Value.At(0).AsNumber()));
				return true;
			}
			if (Count == 2)
			{
				OutMargin = FMargin(static_cast<float>(Value.At(0).AsNumber()), static_cast<float>(Value.At(1).AsNumber()));
				return true;
			}
			if (Count == 4)
			{
				OutMargin = FMargin(static_cast<float>(Value.At(0).AsNumber()), static_cast<float>(Value.At(1).AsNumber()), static_cast<float>(Value.At(2).AsNumber()), static_cast<float>(Value.At(3).AsNumber()));
				return true;
			}
			return false;
		}
		if (Value.IsObject())
		{
			OutMargin = FMargin(
				static_cast<float>(Value.GetNumber("left", 0.0)),
				static_cast<float>(Value.GetNumber("top", 0.0)),
				static_cast<float>(Value.GetNumber("right", 0.0)),
				static_cast<float>(Value.GetNumber("bottom", 0.0)));
			return true;
		}
		return false;
	}

	/**
	 * Optional Content/Data/Art/UI/NineSlice.json written by the UI artist, e.g.
	 * {"Panel.png": 24, "Button": [20, 16], "Tab.png": [16, 14, 16, 8], "PanelDark": {"left": 24, ...}}
	 * (number = uniform, [h, v], [l, t, r, b] or an object; names with or without ".png").
	 */
	void LoadNineSlice(FNineSliceMargins& OutMargins)
	{
		OutMargins = FNineSliceMargins();
		const FString Path = FIronSession::DataDir() / TEXT("Art/UI/NineSlice.json");
		if (!FPaths::FileExists(Path))
		{
			return;
		}
		IronSim::FJson Json;
		FText Error;
		if (!FIronSession::LoadJsonFile(Path, Json, Error) || !Json.IsObject())
		{
			UE_LOG(LogIronReign, Warning, TEXT("Ignoring NineSlice.json: %s"), *Error.ToString());
			return;
		}
		for (const std::pair<std::string, IronSim::FJson>& Member : Json.Members())
		{
			FString Name = IronUI::ToFString(Member.first);
			Name.RemoveFromEnd(TEXT(".png"));
			FMargin Parsed;
			if (!ParseMargin(Member.second, Parsed))
			{
				continue;
			}
			if (Name == TEXT("Panel"))
			{
				OutMargins.Panel = Parsed;
			}
			else if (Name == TEXT("PanelDark"))
			{
				OutMargins.PanelDark = Parsed;
			}
			else if (Name.StartsWith(TEXT("Button")))
			{
				OutMargins.Button = Parsed;
			}
			else if (Name.StartsWith(TEXT("Tab")))
			{
				OutMargins.Tab = Parsed;
			}
		}
	}

	/** Optional Art/Map/BannerGlyphArea.txt: "x y w h" of the cloth in the 64x96 banner image. */
	void LoadGlyphArea(FStyleState& State)
	{
		const FString Path = FIronSession::DataDir() / TEXT("Art/Map/BannerGlyphArea.txt");
		FString Text;
		if (!FPaths::FileExists(Path) || !FFileHelper::LoadFileToString(Text, *Path))
		{
			return;
		}
		TArray<FString> Parts;
		Text.ParseIntoArrayWS(Parts, TEXT(","));
		if (Parts.Num() < 4)
		{
			return;
		}
		const float AreaX = FCString::Atof(*Parts[0]);
		const float AreaY = FCString::Atof(*Parts[1]);
		const float AreaW = FCString::Atof(*Parts[2]);
		const float AreaH = FCString::Atof(*Parts[3]);
		if (AreaW > 1.0f && AreaH > 1.0f)
		{
			State.GlyphX = AreaX;
			State.GlyphY = AreaY;
			State.GlyphW = AreaW;
			State.GlyphH = AreaH;
		}
	}

	FSlateBrush ColorBrush(const FLinearColor& Color)
	{
		FSlateBrush Result = FSlateColorBrush(Color);
		return Result;
	}

	FSlateBrush NoBrush()
	{
		FSlateBrush Result = FSlateNoResource();
		return Result;
	}

	FSlateBrush Tinted(const FSlateBrush& Source, const FLinearColor& Tint)
	{
		FSlateBrush Result = Source;
		Result.TintColor = FSlateColor(Tint);
		return Result;
	}

	/** 9-slice art brush, or a flat colour when the file is missing (keeps screens readable before art lands). */
	FSlateBrush ArtBox(const TCHAR* RelativePath, const FMargin& PixelMargin, const FLinearColor& FallbackColor)
	{
		FIronAssets& Assets = FIronAssets::Get();
		if (Assets.Exists(RelativePath))
		{
			return *Assets.Box(RelativePath, PixelMargin);
		}
		return ColorBrush(FallbackColor);
	}

	void RebuildStyles(FStyleState& State)
	{
		const FNineSliceMargins& Margins = State.Margins;
		const FLinearColor LacquerColor = IronStyle::Lacquer();
		const FLinearColor GoldColor = IronStyle::Gold();

		State.PanelBrush = ArtBox(TEXT("Art/UI/Panel.png"), Margins.Panel, IronStyle::Paper());
		State.PanelDarkBrush = ArtBox(TEXT("Art/UI/PanelDark.png"), Margins.PanelDark, IronStyle::Night());

		FIronAssets& Assets = FIronAssets::Get();
		if (Assets.Exists(TEXT("Art/UI/Divider.png")))
		{
			State.DividerBrush = *Assets.Image(TEXT("Art/UI/Divider.png"));
		}
		else
		{
			State.DividerBrush = ColorBrush(GoldColor);
		}

		// Lacquer buttons (dedicated art for every state).
		const FSlateBrush ButtonNormal = ArtBox(TEXT("Art/UI/Button.png"), Margins.Button, LacquerColor);
		const FSlateBrush ButtonHovered = ArtBox(TEXT("Art/UI/Button_Hover.png"), Margins.Button, IronUI::ColorFromRGB(0x972C22));
		const FSlateBrush ButtonPressed = ArtBox(TEXT("Art/UI/Button_Pressed.png"), Margins.Button, IronStyle::LacquerDark());
		const FSlateBrush ButtonDisabled = ArtBox(TEXT("Art/UI/Button_Disabled.png"), Margins.Button, IronUI::ColorFromRGB(0x534640));
		State.ButtonStyle = FButtonStyle()
			.SetNormal(ButtonNormal)
			.SetHovered(ButtonHovered)
			.SetPressed(ButtonPressed)
			.SetDisabled(ButtonDisabled)
			.SetNormalPadding(FMargin(18.0f, 8.0f, 18.0f, 10.0f))
			.SetPressedPadding(FMargin(18.0f, 10.0f, 18.0f, 8.0f));

		// Tabs: slate tints cannot brighten, so inactive tabs are dimmed and light up on hover.
		const FSlateBrush TabBrush = ArtBox(TEXT("Art/UI/Tab.png"), Margins.Tab, IronUI::ColorFromRGB(0x3C2B21));
		const FSlateBrush TabActiveBrush = ArtBox(TEXT("Art/UI/Tab_Active.png"), Margins.Tab, LacquerColor);
		const FLinearColor Dim(0.78f, 0.78f, 0.78f, 1.0f);
		State.TabStyles[0] = FButtonStyle()
			.SetNormal(Tinted(TabBrush, Dim))
			.SetHovered(TabBrush)
			.SetPressed(TabActiveBrush)
			.SetDisabled(Tinted(TabBrush, FLinearColor(0.55f, 0.55f, 0.55f, 0.8f)))
			.SetNormalPadding(FMargin(16.0f, 6.0f, 16.0f, 6.0f))
			.SetPressedPadding(FMargin(16.0f, 7.0f, 16.0f, 5.0f));
		State.TabStyles[1] = FButtonStyle()
			.SetNormal(TabActiveBrush)
			.SetHovered(TabActiveBrush)
			.SetPressed(Tinted(TabActiveBrush, FLinearColor(0.85f, 0.85f, 0.85f, 1.0f)))
			.SetDisabled(Tinted(TabActiveBrush, FLinearColor(0.6f, 0.6f, 0.6f, 0.8f)))
			.SetNormalPadding(FMargin(16.0f, 6.0f, 16.0f, 6.0f))
			.SetPressedPadding(FMargin(16.0f, 7.0f, 16.0f, 5.0f));

		// Choice pills on parchment: transparent until hovered, gold when active.
		const FSlateBrush ChoiceIdle = ColorBrush(IronStyle::PaperDark().CopyWithNewOpacity(0.55f));
		const FSlateBrush ChoiceHover = ColorBrush(GoldColor.CopyWithNewOpacity(0.45f));
		const FSlateBrush ChoiceActive = ColorBrush(GoldColor);
		State.ChoiceStyles[0] = FButtonStyle()
			.SetNormal(ChoiceIdle)
			.SetHovered(ChoiceHover)
			.SetPressed(ChoiceActive)
			.SetDisabled(ColorBrush(IronStyle::PaperDark().CopyWithNewOpacity(0.25f)))
			.SetNormalPadding(FMargin(14.0f, 6.0f))
			.SetPressedPadding(FMargin(14.0f, 7.0f, 14.0f, 5.0f));
		State.ChoiceStyles[1] = FButtonStyle()
			.SetNormal(ChoiceActive)
			.SetHovered(ChoiceActive)
			.SetPressed(ChoiceActive)
			.SetDisabled(ColorBrush(GoldColor.CopyWithNewOpacity(0.5f)))
			.SetNormalPadding(FMargin(14.0f, 6.0f))
			.SetPressedPadding(FMargin(14.0f, 7.0f, 14.0f, 5.0f));

		// Clickable list rows.
		State.RowStyle = FButtonStyle()
			.SetNormal(NoBrush())
			.SetHovered(ColorBrush(GoldColor.CopyWithNewOpacity(0.22f)))
			.SetPressed(ColorBrush(GoldColor.CopyWithNewOpacity(0.38f)))
			.SetDisabled(NoBrush())
			.SetNormalPadding(FMargin(0.0f))
			.SetPressedPadding(FMargin(0.0f));

		State.BodyTextStyle = FTextBlockStyle()
			.SetFont(MakeFontInfo(State.ActiveFonts, IronStyle::EFont::Body, 15.0f))
			.SetColorAndOpacity(FSlateColor(IronStyle::Ink()))
			.SetShadowOffset(FVector2D::ZeroVector)
			.SetShadowColorAndOpacity(FLinearColor::Transparent);

		FTableRowStyle RowStyle = FCoreStyle::Get().GetWidgetStyle<FTableRowStyle>("TableView.Row");
		const FSlateBrush Clear = NoBrush();
		const FSlateBrush OddRow = ColorBrush(IronStyle::PaperDark().CopyWithNewOpacity(0.35f));
		const FSlateBrush HoverRow = ColorBrush(GoldColor.CopyWithNewOpacity(0.25f));
		const FSlateBrush SelectedRow = ColorBrush(GoldColor.CopyWithNewOpacity(0.5f));
		RowStyle
			.SetEvenRowBackgroundBrush(Clear)
			.SetOddRowBackgroundBrush(OddRow)
			.SetEvenRowBackgroundHoveredBrush(HoverRow)
			.SetOddRowBackgroundHoveredBrush(HoverRow)
			.SetActiveBrush(SelectedRow)
			.SetActiveHoveredBrush(SelectedRow)
			.SetInactiveBrush(SelectedRow)
			.SetInactiveHoveredBrush(SelectedRow)
			.SetSelectorFocusedBrush(Clear)
			.SetTextColor(FSlateColor(IronStyle::Ink()))
			.SetSelectedTextColor(FSlateColor(IronStyle::Ink()));
		State.TableRowStyle = RowStyle;

		State.BarStyle = FProgressBarStyle()
			.SetBackgroundImage(ColorBrush(IronStyle::Ink().CopyWithNewOpacity(0.28f)))
			.SetFillImage(ColorBrush(FLinearColor::White))
			.SetMarqueeImage(ColorBrush(FLinearColor::White));
	}
}

namespace IronStyle
{
	void Initialize(const FString& Culture)
	{
		IronStyleDetail::FStyleState& State = IronStyleDetail::StyleState();
		// Set first: anything below that asks for a style must not re-enter Initialize.
		State.bInitialized = true;
		State.Culture = IronStyleDetail::NormalizedCulture(Culture);
		State.ActiveFonts = IronStyleDetail::FontSetFor(State.Culture);
		IronStyleDetail::LoadNineSlice(State.Margins);
		IronStyleDetail::LoadGlyphArea(State);
		IronStyleDetail::RebuildStyles(State);
	}

	void Shutdown()
	{
		IronStyleDetail::FStyleState& State = IronStyleDetail::StyleState();
		// Brushes reference textures owned by FIronAssets; drop them before the textures go away.
		const FSlateBrush Clear = IronStyleDetail::NoBrush();
		State.PanelBrush = Clear;
		State.PanelDarkBrush = Clear;
		State.DividerBrush = Clear;
		State.ButtonStyle = FButtonStyle();
		State.TabStyles[0] = FButtonStyle();
		State.TabStyles[1] = FButtonStyle();
		State.RowStyle = FButtonStyle();
		State.ChoiceStyles[0] = FButtonStyle();
		State.ChoiceStyles[1] = FButtonStyle();
		// Composite fonts are kept: Slate's font cache knows them by address, and they hold no textures.
		State.Session.Reset();
		State.bInitialized = false;
	}

	void SetSession(const TSharedPtr<FIronSession>& Session)
	{
		IronStyleDetail::StyleState().Session = Session;
	}

	// ----- Palette -----

	FLinearColor Paper() { return IronUI::ColorFromRGB(0xE9DCC0); }
	FLinearColor PaperDark() { return IronUI::ColorFromRGB(0xCDB990); }
	FLinearColor Ink() { return IronUI::ColorFromRGB(0x2A2119); }
	FLinearColor InkSoft() { return IronUI::ColorFromRGB(0x5A4A3A); }
	FLinearColor Lacquer() { return IronUI::ColorFromRGB(0x7E1F17); }
	FLinearColor LacquerDark() { return IronUI::ColorFromRGB(0x4A120D); }
	FLinearColor Gold() { return IronUI::ColorFromRGB(0xC9A24A); }
	FLinearColor Jade() { return IronUI::ColorFromRGB(0x3F6E5A); }
	FLinearColor Indigo() { return IronUI::ColorFromRGB(0x2E3F5C); }
	FLinearColor Night() { return IronUI::ColorFromRGB(0x1B1712); }
	FLinearColor TextLight() { return IronUI::ColorFromRGB(0xF3E8CF); }
	FLinearColor Danger() { return IronUI::ColorFromRGB(0xA8261E); }

	FLinearColor FactionColor(int32 FactionIndex)
	{
		if (FactionIndex < 0)
		{
			return IronUI::ColorFromRGB(0x8C8577);
		}
		const TSharedPtr<FIronSession> SessionPtr = IronStyleDetail::StyleState().Session.Pin();
		if (SessionPtr.IsValid() && SessionPtr->HasGame())
		{
			const IronSim::FGameState& GameState = SessionPtr->State();
			if (FactionIndex < static_cast<int32>(GameState.Factions.size()))
			{
				return IronUI::ColorFromRGB(GameState.Factions[static_cast<size_t>(FactionIndex)].Color);
			}
		}
		// DESIGN.md section 8 order: Iron Banner, Wolf Riders, Azure Court, Sea League, Southern Lotus, Black Mountain.
		static const uint32 DefaultColors[6] = {0xB3282D, 0xB07A2A, 0x2F6DB5, 0x1F8F8A, 0x4C9A3C, 0x4A4A55};
		return IronUI::ColorFromRGB(DefaultColors[FactionIndex % 6]);
	}

	// ----- Fonts -----

	FSlateFontInfo Font(EFont Kind, float Size)
	{
		const IronStyleDetail::FStyleState& State = IronStyleDetail::ReadyState();
		return IronStyleDetail::MakeFontInfo(State.ActiveFonts, Kind, Size);
	}

	FSlateFontInfo FontForCulture(const FString& Culture, EFont Kind, float Size)
	{
		return IronStyleDetail::MakeFontInfo(IronStyleDetail::FontSetFor(Culture), Kind, Size);
	}

	FSlateFontInfo Body(float Size) { return Font(EFont::Body, Size); }
	FSlateFontInfo BodyBold(float Size) { return Font(EFont::BodyBold, Size); }
	FSlateFontInfo Heading(float Size) { return Font(EFont::Heading, Size); }
	FSlateFontInfo Brush(float Size) { return Font(EFont::Brush, Size); }

	// ----- Brushes and widget styles -----

	const FSlateBrush* Panel() { return &IronStyleDetail::ReadyState().PanelBrush; }
	const FSlateBrush* PanelDark() { return &IronStyleDetail::ReadyState().PanelDarkBrush; }
	const FSlateBrush* Divider() { return &IronStyleDetail::ReadyState().DividerBrush; }
	const FSlateBrush* WhiteBrush() { return FIronAssets::Get().White(); }
	const FButtonStyle& Button() { return IronStyleDetail::ReadyState().ButtonStyle; }
	const FButtonStyle& Tab(bool bActive) { return IronStyleDetail::ReadyState().TabStyles[bActive ? 1 : 0]; }
	const FButtonStyle& RowButton() { return IronStyleDetail::ReadyState().RowStyle; }
	const FTextBlockStyle& BodyText() { return IronStyleDetail::ReadyState().BodyTextStyle; }
	const FTableRowStyle& TableRow() { return IronStyleDetail::ReadyState().TableRowStyle; }

	// ----- Widget factories -----

	TSharedRef<SWidget> MakePanel(const TSharedRef<SWidget>& Content, bool bDark, const FMargin& Padding)
	{
		return SNew(SBorder)
			.BorderImage(bDark ? PanelDark() : Panel())
			.ForegroundColor(bDark ? TextLight() : Ink())
			.Padding(Padding)
			[
				Content
			];
	}

	TSharedRef<SButton> MakeButton(const TAttribute<FText>& Label, FOnClicked OnClicked, const TAttribute<bool>& IsEnabled, const FString& IconName, float MinWidth)
	{
		TSharedRef<SHorizontalBox> ContentRow = SNew(SHorizontalBox);
		if (!IconName.IsEmpty() && FIronAssets::Get().Exists(FString::Printf(TEXT("Art/UI/Icon_%s.png"), *IconName)))
		{
			ContentRow->AddSlot()
				.AutoWidth()
				.VAlign(VAlign_Center)
				.Padding(FMargin(0.0f, 0.0f, 8.0f, 0.0f))
				[
					SNew(SBox)
					.WidthOverride(26.0f)
					.HeightOverride(26.0f)
					[
						SNew(SImage)
						.Image(FIronAssets::Get().Icon(IconName))
					]
				];
		}
		ContentRow->AddSlot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(BodyBold(16.0f))
				.ColorAndOpacity(TextLight())
				.ShadowOffset(FVector2D(1.0f, 1.0f))
				.ShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.6f))
			];

		return SNew(SButton)
			.ButtonStyle(&Button())
			.IsFocusable(false)
			.OnClicked(WithClickSound(MoveTemp(OnClicked)))
			.IsEnabled(IsEnabled)
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			[
				SNew(SBox)
				.MinDesiredWidth(MinWidth > 0.0f ? FOptionalSize(MinWidth) : FOptionalSize())
				.HAlign(HAlign_Center)
				.VAlign(VAlign_Center)
				[
					ContentRow
				]
			];
	}

	TSharedRef<SWidget> MakeHeader(const TAttribute<FText>& Text, float Size, bool bOnDark)
	{
		return SNew(SVerticalBox)
			+ SVerticalBox::Slot()
			.AutoHeight()
			[
				SNew(STextBlock)
				.Text(Text)
				.Font(Heading(Size))
				.ColorAndOpacity(bOnDark ? Gold() : Lacquer())
				.ShadowOffset(bOnDark ? FVector2D(1.0f, 1.0f) : FVector2D::ZeroVector)
				.ShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.6f))
			]
			+ SVerticalBox::Slot()
			.AutoHeight()
			.Padding(FMargin(0.0f, 4.0f, 0.0f, 0.0f))
			[
				MakeDivider(FMath::Clamp(Size * 0.45f, 8.0f, 16.0f))
			];
	}

	TSharedRef<SWidget> MakeLabel(const TAttribute<FText>& Text, float Size, const FLinearColor& Color, bool bBold)
	{
		return SNew(STextBlock)
			.Text(Text)
			.Font(bBold ? BodyBold(Size) : Body(Size))
			.ColorAndOpacity(Color);
	}

	TSharedRef<SWidget> MakeBar(const TAttribute<float>& Fraction, const FLinearColor& Color, float Height)
	{
		TAttribute<TOptional<float>> Percent;
		if (Fraction.IsBound())
		{
			Percent = TAttribute<TOptional<float>>::CreateLambda([Fraction]()
			{
				return TOptional<float>(FMath::Clamp(Fraction.Get(), 0.0f, 1.0f));
			});
		}
		else
		{
			Percent.Set(TOptional<float>(FMath::Clamp(Fraction.Get(), 0.0f, 1.0f)));
		}

		return SNew(SBox)
			.HeightOverride(Height)
			[
				SNew(SProgressBar)
				.Style(&IronStyleDetail::ReadyState().BarStyle)
				.Percent(Percent)
				.FillColorAndOpacity(Color)
				.BorderPadding(FVector2D::ZeroVector)
			];
	}

	TSharedRef<SWidget> MakePortrait(const TAttribute<FString>& PortraitId, float Height)
	{
		const float Scale = Height / 260.0f;
		const float FrameWidth = 212.0f * Scale;
		const float Inset = 10.0f * Scale;
		FIronAssets& Assets = FIronAssets::Get();

		TAttribute<const FSlateBrush*> PortraitBrush;
		if (PortraitId.IsBound())
		{
			PortraitBrush = TAttribute<const FSlateBrush*>::CreateLambda([PortraitId]()
			{
				return FIronAssets::Get().Portrait(PortraitId.Get());
			});
		}
		else
		{
			PortraitBrush.Set(Assets.Portrait(PortraitId.Get()));
		}

		const bool bFrameArt = Assets.Exists(TEXT("Art/UI/Frame_Portrait.png"));
		TSharedRef<SOverlay> Layers = SNew(SOverlay);
		if (!bFrameArt)
		{
			Layers->AddSlot()
				[
					SNew(SImage)
					.Image(WhiteBrush())
					.ColorAndOpacity(Gold())
				];
		}
		Layers->AddSlot()
			.Padding(FMargin(Inset))
			[
				SNew(SImage)
				.Image(PortraitBrush)
			];
		if (bFrameArt)
		{
			Layers->AddSlot()
				[
					SNew(SImage)
					.Image(Assets.Image(TEXT("Art/UI/Frame_Portrait.png")))
				];
		}

		return SNew(SBox)
			.WidthOverride(FrameWidth)
			.HeightOverride(Height)
			[
				Layers
			];
	}

	TSharedRef<SWidget> MakeIconValue(const FString& IconName, const TAttribute<FText>& Value, float IconSize, const FLinearColor& TextColor)
	{
		const bool bIconArt = FIronAssets::Get().Exists(FString::Printf(TEXT("Art/UI/Icon_%s.png"), *IconName));
		return SNew(SHorizontalBox)
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			.Padding(FMargin(0.0f, 0.0f, 5.0f, 0.0f))
			[
				SNew(SBox)
				.WidthOverride(IconSize)
				.HeightOverride(IconSize)
				.Visibility(bIconArt ? EVisibility::Visible : EVisibility::Collapsed)
				[
					SNew(SImage)
					.Image(bIconArt ? FIronAssets::Get().Icon(IconName) : WhiteBrush())
				]
			]
			+ SHorizontalBox::Slot()
			.AutoWidth()
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Value)
				.Font(BodyBold(15.0f))
				.ColorAndOpacity(TextColor)
			];
	}

	FText FactionGlyph(const FString& FactionKey, const FString& DefaultGlyph)
	{
		const std::string GlyphKey = "faction." + IronUI::ToStd(FactionKey) + ".glyph";
		if (const std::string* Translated = IronSim::FLocale::Active().Find(GlyphKey))
		{
			return IronUI::ToText(*Translated);
		}
		return FText::FromString(DefaultGlyph);
	}

	TSharedRef<SWidget> MakeBanner(int32 FactionIndex, float Height)
	{
		FText Glyph;
		const TSharedPtr<FIronSession> SessionPtr = IronStyleDetail::StyleState().Session.Pin();
		if (FactionIndex >= 0 && SessionPtr.IsValid() && SessionPtr->HasGame())
		{
			const IronSim::FGameState& GameState = SessionPtr->State();
			if (FactionIndex < static_cast<int32>(GameState.Factions.size()))
			{
				const IronSim::FFaction& Faction = GameState.Factions[static_cast<size_t>(FactionIndex)];
				Glyph = FactionGlyph(IronUI::ToFString(Faction.Key), IronUI::ToFString(Faction.Glyph));
			}
		}
		return MakeBannerFor(FactionColor(FactionIndex), Glyph, Height);
	}

	TSharedRef<SWidget> MakeBannerFor(const FLinearColor& Color, const FText& Glyph, float Height)
	{
		const IronStyleDetail::FStyleState& State = IronStyleDetail::ReadyState();
		const float Scale = Height / 96.0f;
		const bool bBannerArt = FIronAssets::Get().Exists(TEXT("Art/Map/Banner.png"));
		const FSlateBrush* ClothBrush = bBannerArt ? FIronAssets::Get().Image(TEXT("Art/Map/Banner.png")) : WhiteBrush();
		const float GlyphFontSize = FMath::Max(6.0f, State.GlyphH * Scale * 0.55f);

		return SNew(SBox)
			.WidthOverride(64.0f * Scale)
			.HeightOverride(Height)
			[
				SNew(SOverlay)
				+ SOverlay::Slot()
				[
					SNew(SImage)
					.Image(ClothBrush)
					.ColorAndOpacity(Color)
				]
				+ SOverlay::Slot()
				.HAlign(HAlign_Left)
				.VAlign(VAlign_Top)
				.Padding(FMargin(State.GlyphX * Scale, State.GlyphY * Scale, 0.0f, 0.0f))
				[
					SNew(SBox)
					.WidthOverride(State.GlyphW * Scale)
					.HeightOverride(State.GlyphH * Scale)
					.HAlign(HAlign_Center)
					.VAlign(VAlign_Center)
					[
						SNew(STextBlock)
						.Text(Glyph)
						.Font(Brush(GlyphFontSize))
						.ColorAndOpacity(TextLight())
						.ShadowOffset(FVector2D(1.0f, 1.0f))
						.ShadowColorAndOpacity(FLinearColor(0.0f, 0.0f, 0.0f, 0.65f))
					]
				]
			];
	}

	TSharedRef<SWidget> MakeDivider(float Height)
	{
		const bool bDividerArt = FIronAssets::Get().Exists(TEXT("Art/UI/Divider.png"));
		return SNew(SBox)
			.HeightOverride(bDividerArt ? Height : 2.0f)
			[
				SNew(SImage)
				.Image(Divider())
			];
	}

	TSharedRef<SButton> MakeChoiceButton(const FText& Label, bool bActive, FOnClicked OnClicked, const FSlateFontInfo& LabelFont)
	{
		const IronStyleDetail::FStyleState& State = IronStyleDetail::ReadyState();
		return SNew(SButton)
			.ButtonStyle(&State.ChoiceStyles[bActive ? 1 : 0])
			.IsFocusable(false)
			.OnClicked(WithClickSound(MoveTemp(OnClicked)))
			.HAlign(HAlign_Center)
			.VAlign(VAlign_Center)
			[
				SNew(STextBlock)
				.Text(Label)
				.Font(LabelFont)
				.ColorAndOpacity(Ink())
			];
	}

	FOnClicked WithClickSound(FOnClicked OnClicked)
	{
		return FOnClicked::CreateLambda([Handler = MoveTemp(OnClicked)]() -> FReply
		{
			FIronAudio& AudioPlayer = FIronAudio::Get();
			const uint32 RequestsBefore = AudioPlayer.GetSfxRequestCount();
			// Same contract as SButton: an unbound (or expired SP) handler simply does nothing.
			const FReply Reply = Handler.IsBound() ? Handler.Execute() : FReply::Handled();
			if (AudioPlayer.GetSfxRequestCount() == RequestsBefore)
			{
				AudioPlayer.PlaySfx(TEXT("Click"));
			}
			return Reply;
		});
	}
}
