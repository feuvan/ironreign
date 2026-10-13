#include "Sim/IronLocale.h"

#include "Sim/IronState.h"

namespace IronSim
{
	namespace LocaleDetail
	{
		std::string Lookup(const std::string& Key, const std::string& Fallback)
		{
			const std::string* Found = FLocale::Active().Find(Key);
			return Found ? *Found : Fallback;
		}

		std::string EntityKey(const char* Kind, const std::string& Key, const char* Field)
		{
			std::string Result = Kind;
			Result += '.';
			Result += Key;
			Result += '.';
			Result += Field;
			return Result;
		}

		void AddIfSet(FJson& Table, const std::string& Key, const std::string& Text)
		{
			if (!Text.empty())
			{
				Table.SetString(Key, Text);
			}
		}
	}

	FLocale& FLocale::Active()
	{
		static FLocale Instance;
		return Instance;
	}

	void FLocale::Reset(const std::string& InCulture)
	{
		CultureName = InCulture;
		Strings.clear();
	}

	void FLocale::AddStrings(const FJson& Table)
	{
		for (const std::pair<std::string, FJson>& Member : Table.Members())
		{
			if (Member.second.IsString())
			{
				Strings[Member.first] = Member.second.AsString();
			}
		}
	}

	void FLocale::SetString(const std::string& Key, const std::string& Text)
	{
		Strings[Key] = Text;
	}

	bool FLocale::IsCjk() const
	{
		return CultureName == "zh-Hans" || CultureName == "zh-Hant" || CultureName == "ja" || CultureName == "ko";
	}

	const std::string* FLocale::Find(const std::string& Key) const
	{
		const auto Found = Strings.find(Key);
		return Found == Strings.end() ? nullptr : &Found->second;
	}

	std::string Loc(const char* Key, const char* Default)
	{
		const std::string* Found = FLocale::Active().Find(Key);
		return Found ? *Found : std::string(Default);
	}

	std::string LocF(const char* Key, const char* Default, std::initializer_list<FLocArg> Args)
	{
		return FormatText(Loc(Key, Default), Args);
	}

	std::string FormatText(const std::string& Pattern, std::initializer_list<FLocArg> Args)
	{
		std::string Result;
		Result.reserve(Pattern.size() + 32);
		size_t Pos = 0;
		while (Pos < Pattern.size())
		{
			const char C = Pattern[Pos];
			if (C == '{')
			{
				const size_t Close = Pattern.find('}', Pos + 1);
				if (Close != std::string::npos)
				{
					const std::string Name = Pattern.substr(Pos + 1, Close - Pos - 1);
					bool bReplaced = false;
					for (const FLocArg& Arg : Args)
					{
						if (Name == Arg.Name)
						{
							Result += Arg.Value;
							bReplaced = true;
							break;
						}
					}
					if (bReplaced)
					{
						Pos = Close + 1;
						continue;
					}
				}
			}
			Result.push_back(C);
			++Pos;
		}
		return Result;
	}

	std::string ToText(int Value)
	{
		return std::to_string(Value);
	}

	std::string NameOf(const FOfficer& Officer) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("officer", Officer.Key, "name"), Officer.Name); }
	std::string EpithetOf(const FOfficer& Officer) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("officer", Officer.Key, "epithet"), Officer.Epithet); }
	std::string BioOf(const FOfficer& Officer) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("officer", Officer.Key, "bio"), Officer.Bio); }
	std::string RumorOf(const FOfficer& Officer) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("officer", Officer.Key, "rumor"), Officer.Rumor); }
	std::string NameOf(const FCity& City) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("city", City.Key, "name"), City.Name); }
	std::string DescriptionOf(const FCity& City) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("city", City.Key, "description"), City.Description); }
	std::string NameOf(const FFaction& Faction) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("faction", Faction.Key, "name"), Faction.Name); }
	std::string NameOf(const FSect& Sect) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("sect", Sect.Key, "name"), Sect.Name); }
	std::string DescriptionOf(const FSect& Sect) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("sect", Sect.Key, "description"), Sect.Description); }
	std::string NameOf(const FTechnique& Technique) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("technique", Technique.Key, "name"), Technique.Name); }
	std::string DescriptionOf(const FTechnique& Technique) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("technique", Technique.Key, "description"), Technique.Description); }
	std::string TitleOf(const FEventDef& Event) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("event", Event.Key, "title"), Event.Title); }
	std::string TextOf(const FEventDef& Event) { return LocaleDetail::Lookup(LocaleDetail::EntityKey("event", Event.Key, "text"), Event.Text); }

	std::string ChoiceLabelOf(const FEventDef& Event, int ChoiceIndex)
	{
		if (ChoiceIndex < 0 || ChoiceIndex >= static_cast<int>(Event.Choices.size()))
		{
			return std::string();
		}
		const std::string Field = "choice." + std::to_string(ChoiceIndex);
		return LocaleDetail::Lookup(LocaleDetail::EntityKey("event", Event.Key, Field.c_str()), Event.Choices[static_cast<size_t>(ChoiceIndex)].Label);
	}

	std::string EffectTextOf(const FEventDef& Event, int ChoiceIndex, int EffectIndex)
	{
		const std::vector<FEffect>* Effects = &Event.Effects;
		std::string Field;
		if (ChoiceIndex >= 0)
		{
			if (ChoiceIndex >= static_cast<int>(Event.Choices.size()))
			{
				return std::string();
			}
			Effects = &Event.Choices[static_cast<size_t>(ChoiceIndex)].Effects;
			Field = "choice." + std::to_string(ChoiceIndex) + ".";
		}
		if (EffectIndex < 0 || EffectIndex >= static_cast<int>(Effects->size()))
		{
			return std::string();
		}
		Field += "effect." + std::to_string(EffectIndex);
		return LocaleDetail::Lookup(LocaleDetail::EntityKey("event", Event.Key, Field.c_str()), (*Effects)[static_cast<size_t>(EffectIndex)].Text);
	}

	std::string ScenarioNameOf(const FGameState& State) { return LocaleDetail::Lookup("scenario." + State.ScenarioKey + ".name", State.ScenarioName); }
	std::string ScenarioDescriptionOf(const FGameState& State) { return LocaleDetail::Lookup("scenario." + State.ScenarioKey + ".description", State.ScenarioDescription); }

	std::string MapLabelOf(const FGameState& State, int LabelIndex)
	{
		if (LabelIndex < 0 || LabelIndex >= static_cast<int>(State.Map.Labels.size()))
		{
			return std::string();
		}
		return LocaleDetail::Lookup("scenario." + State.ScenarioKey + ".label." + std::to_string(LabelIndex), State.Map.Labels[static_cast<size_t>(LabelIndex)].Text);
	}

	FJson ExtractScenarioStrings(const FGameState& State)
	{
		using LocaleDetail::AddIfSet;
		using LocaleDetail::EntityKey;
		FJson Table = FJson::MakeObject();
		AddIfSet(Table, "scenario." + State.ScenarioKey + ".name", State.ScenarioName);
		AddIfSet(Table, "scenario." + State.ScenarioKey + ".description", State.ScenarioDescription);
		for (size_t Index = 0; Index < State.Map.Labels.size(); ++Index)
		{
			AddIfSet(Table, "scenario." + State.ScenarioKey + ".label." + std::to_string(Index), State.Map.Labels[Index].Text);
		}
		for (const FFaction& Faction : State.Factions)
		{
			AddIfSet(Table, EntityKey("faction", Faction.Key, "name"), Faction.Name);
		}
		for (const FCity& City : State.Cities)
		{
			AddIfSet(Table, EntityKey("city", City.Key, "name"), City.Name);
			AddIfSet(Table, EntityKey("city", City.Key, "description"), City.Description);
		}
		for (const FOfficer& Officer : State.Officers)
		{
			AddIfSet(Table, EntityKey("officer", Officer.Key, "name"), Officer.Name);
			AddIfSet(Table, EntityKey("officer", Officer.Key, "epithet"), Officer.Epithet);
			AddIfSet(Table, EntityKey("officer", Officer.Key, "bio"), Officer.Bio);
			AddIfSet(Table, EntityKey("officer", Officer.Key, "rumor"), Officer.Rumor);
		}
		for (const FTechnique& Technique : State.Techniques)
		{
			AddIfSet(Table, EntityKey("technique", Technique.Key, "name"), Technique.Name);
			AddIfSet(Table, EntityKey("technique", Technique.Key, "description"), Technique.Description);
		}
		for (const FSect& Sect : State.Sects)
		{
			AddIfSet(Table, EntityKey("sect", Sect.Key, "name"), Sect.Name);
			AddIfSet(Table, EntityKey("sect", Sect.Key, "description"), Sect.Description);
		}
		for (const FEventDef& Event : State.Events)
		{
			AddIfSet(Table, EntityKey("event", Event.Key, "title"), Event.Title);
			AddIfSet(Table, EntityKey("event", Event.Key, "text"), Event.Text);
			for (size_t Effect = 0; Effect < Event.Effects.size(); ++Effect)
			{
				const std::string Field = "effect." + std::to_string(Effect);
				AddIfSet(Table, EntityKey("event", Event.Key, Field.c_str()), Event.Effects[Effect].Text);
			}
			for (size_t Choice = 0; Choice < Event.Choices.size(); ++Choice)
			{
				const std::string Field = "choice." + std::to_string(Choice);
				AddIfSet(Table, EntityKey("event", Event.Key, Field.c_str()), Event.Choices[Choice].Label);
				for (size_t Effect = 0; Effect < Event.Choices[Choice].Effects.size(); ++Effect)
				{
					const std::string EffectField = Field + ".effect." + std::to_string(Effect);
					AddIfSet(Table, EntityKey("event", Event.Key, EffectField.c_str()), Event.Choices[Choice].Effects[Effect].Text);
				}
			}
		}
		return Table;
	}
}
