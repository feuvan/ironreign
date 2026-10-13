#pragma once

#include "CoreMinimal.h"
#include "Sim/IronLocale.h"

#include <string>

/** Small conversion helpers between the std-based rules engine and Unreal text types. */
namespace IronUI
{
	inline FString ToFString(const std::string& Utf8)
	{
		return FString(UTF8_TO_TCHAR(Utf8.c_str()));
	}

	inline FText ToText(const std::string& Utf8)
	{
		return FText::FromString(ToFString(Utf8));
	}

	inline std::string ToStd(const FString& Value)
	{
		return std::string(TCHAR_TO_UTF8(*Value));
	}

	/**
	 * Translated UI text. Same tables and key conventions as IronSim::Loc (see IronLocale.h);
	 * keep the key and English default as literals on one line so Tools/Localization/extract_strings.py finds them.
	 */
	inline FText Loc(const char* Key, const char* Default)
	{
		return ToText(IronSim::Loc(Key, Default));
	}

	inline FText LocF(const char* Key, const char* Default, std::initializer_list<IronSim::FLocArg> Args)
	{
		return ToText(IronSim::LocF(Key, Default, Args));
	}

	inline FText Number(int32 Value)
	{
		return FText::FromString(FString::FromInt(Value));
	}

	/** 0xRRGGBB (sRGB) to a linear Slate colour. */
	inline FLinearColor ColorFromRGB(uint32 RGB, float Alpha = 1.0f)
	{
		FLinearColor Color = FLinearColor(FColor(static_cast<uint8>((RGB >> 16) & 0xFF), static_cast<uint8>((RGB >> 8) & 0xFF), static_cast<uint8>(RGB & 0xFF)));
		Color.A = Alpha;
		return Color;
	}
}
