#pragma once

#include "Sim/IronJson.h"

#include <initializer_list>
#include <string>
#include <unordered_map>

namespace IronSim
{
	struct FGameState;
	struct FOfficer;
	struct FCity;
	struct FFaction;
	struct FSect;
	struct FTechnique;
	struct FEventDef;

	/** Named argument for LocF: {"city", "Luojing"} replaces "{city}". */
	struct FLocArg
	{
		const char* Name;
		std::string Value;
	};

	/**
	 * Runtime string tables shared by the rules engine and the UI.
	 *
	 * Supported cultures: "en", "zh-Hans", "zh-Hant", "ja", "ko".
	 * Player-visible text is written in code with an English default:
	 *     Loc("order.farm", "Develop Farmland")
	 *     LocF("log.order.farm", "Farmland in {city} rose by {amount}.", {{"city", NameOf(City)}, {"amount", ToText(Gain)}})
	 * Keep the key and the default as plain string literals on one line: Tools/Localization/extract_strings.py scans
	 * the sources for Loc/LocF/IronLoc calls to build Content/Data/Localization/en/Strings.json.
	 * Scenario data stays English in the game state; its display text is looked up with conventional keys
	 * ("officer.<key>.name", "city.<key>.name", ...) through the NameOf/BioOf/... helpers below, so save games
	 * are language neutral and switching language re-labels everything.
	 */
	class FLocale
	{
	public:
		/** The process-wide active locale. */
		static FLocale& Active();

		/** Drops all strings and sets the culture name. */
		void Reset(const std::string& InCulture);
		/** Merges a flat {"key": "text"} JSON object (later tables override earlier ones). */
		void AddStrings(const FJson& Table);
		void SetString(const std::string& Key, const std::string& Text);
		const std::string& Culture() const { return CultureName; }
		bool IsCjk() const;

		/** Translation for Key, or nullptr when missing. */
		const std::string* Find(const std::string& Key) const;

	private:
		std::string CultureName = "en";
		std::unordered_map<std::string, std::string> Strings;
	};

	/** Translated text for Key, or Default when the active table has no entry. */
	std::string Loc(const char* Key, const char* Default);
	/** Loc + named placeholder substitution. */
	std::string LocF(const char* Key, const char* Default, std::initializer_list<FLocArg> Args);
	/** Replaces {name} placeholders in Pattern. Unknown placeholders are left untouched. */
	std::string FormatText(const std::string& Pattern, std::initializer_list<FLocArg> Args);
	/** Plain decimal formatting (no grouping), e.g. 12345 -> "12345". */
	std::string ToText(int Value);

	// Display text for scenario data. Fall back to the English field stored in the state.
	std::string NameOf(const FOfficer& Officer);
	std::string EpithetOf(const FOfficer& Officer);
	std::string BioOf(const FOfficer& Officer);
	std::string RumorOf(const FOfficer& Officer);
	std::string NameOf(const FCity& City);
	std::string DescriptionOf(const FCity& City);
	std::string NameOf(const FFaction& Faction);
	std::string NameOf(const FSect& Sect);
	std::string DescriptionOf(const FSect& Sect);
	std::string NameOf(const FTechnique& Technique);
	std::string DescriptionOf(const FTechnique& Technique);
	std::string TitleOf(const FEventDef& Event);
	std::string TextOf(const FEventDef& Event);
	std::string ChoiceLabelOf(const FEventDef& Event, int ChoiceIndex);
	std::string ScenarioNameOf(const FGameState& State);
	std::string ScenarioDescriptionOf(const FGameState& State);
	std::string MapLabelOf(const FGameState& State, int LabelIndex);

	/** Builds the English source table for a scenario's data using the conventional keys above. */
	FJson ExtractScenarioStrings(const FGameState& State);
}
