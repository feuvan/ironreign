#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace IronSim
{
	enum class EJsonType : uint8_t
	{
		Null,
		Bool,
		Number,
		String,
		Array,
		Object
	};

	/**
	 * Minimal JSON document used for scenario files and save games.
	 * Object members keep insertion order so written files are stable and diff-friendly.
	 * Parsing is locale-independent and never throws.
	 */
	class FJson
	{
	public:
		FJson() = default;

		static FJson MakeBool(bool bValue);
		static FJson MakeNumber(double Value);
		static FJson MakeString(std::string Value);
		static FJson MakeArray();
		static FJson MakeObject();

		EJsonType GetType() const { return Type; }
		bool IsNull() const { return Type == EJsonType::Null; }
		bool IsBool() const { return Type == EJsonType::Bool; }
		bool IsNumber() const { return Type == EJsonType::Number; }
		bool IsString() const { return Type == EJsonType::String; }
		bool IsArray() const { return Type == EJsonType::Array; }
		bool IsObject() const { return Type == EJsonType::Object; }

		bool AsBool(bool bDefault = false) const;
		double AsNumber(double Default = 0.0) const;
		int AsInt(int Default = 0) const;
		const std::string& AsString() const;

		/** Array element count or object member count. */
		size_t Size() const;
		const FJson& At(size_t Index) const;
		const std::vector<FJson>& Items() const { return ArrayValue; }
		FJson& Push(FJson Value);
		FJson& PushInt(int Value);
		FJson& PushString(const std::string& Value);

		bool Has(const std::string& Key) const;
		const FJson& Get(const std::string& Key) const;
		FJson& Set(const std::string& Key, FJson Value);
		FJson& SetInt(const std::string& Key, int Value);
		FJson& SetNumber(const std::string& Key, double Value);
		FJson& SetBool(const std::string& Key, bool bValue);
		FJson& SetString(const std::string& Key, const std::string& Value);
		const std::vector<std::pair<std::string, FJson>>& Members() const { return ObjectValue; }

		int GetInt(const std::string& Key, int Default = 0) const;
		double GetNumber(const std::string& Key, double Default = 0.0) const;
		bool GetBool(const std::string& Key, bool bDefault = false) const;
		std::string GetString(const std::string& Key, const std::string& Default = std::string()) const;

		/** Parses UTF-8 text. Accepts // line comments, which scenario authors may use. */
		static bool Parse(const std::string& Text, FJson& OutValue, std::string& OutError);
		std::string Write(bool bPretty = true) const;

	private:
		void WriteTo(std::string& Out, bool bPretty, int Indent) const;

		EJsonType Type = EJsonType::Null;
		bool bBoolValue = false;
		double NumberValue = 0.0;
		std::string StringValue;
		std::vector<FJson> ArrayValue;
		std::vector<std::pair<std::string, FJson>> ObjectValue;
	};
}
