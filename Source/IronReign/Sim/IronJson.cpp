#include "Sim/IronJson.h"

#include <cmath>
#include <cstdio>

namespace IronSim
{
	namespace JsonDetail
	{
		const FJson& NullValue()
		{
			static const FJson Null;
			return Null;
		}

		const std::string& EmptyString()
		{
			static const std::string Empty;
			return Empty;
		}

		class FParser
		{
		public:
			FParser(const std::string& InText, std::string& InError)
				: Text(InText)
				, Error(InError)
			{
			}

			bool ParseDocument(FJson& Out)
			{
				SkipWhitespace();
				if (!ParseValue(Out, 0))
				{
					return false;
				}
				SkipWhitespace();
				if (Pos != Text.size())
				{
					return Fail("unexpected trailing characters");
				}
				return true;
			}

		private:
			bool Fail(const char* Message)
			{
				int Line = 1;
				for (size_t Index = 0; Index < Pos && Index < Text.size(); ++Index)
				{
					if (Text[Index] == '\n')
					{
						++Line;
					}
				}
				Error = std::string(Message) + " (line " + std::to_string(Line) + ")";
				return false;
			}

			void SkipWhitespace()
			{
				while (Pos < Text.size())
				{
					const char C = Text[Pos];
					if (C == ' ' || C == '\t' || C == '\n' || C == '\r')
					{
						++Pos;
					}
					else if (C == '/' && Pos + 1 < Text.size() && Text[Pos + 1] == '/')
					{
						while (Pos < Text.size() && Text[Pos] != '\n')
						{
							++Pos;
						}
					}
					else
					{
						break;
					}
				}
			}

			bool Match(const char* Literal)
			{
				size_t Length = 0;
				while (Literal[Length] != '\0')
				{
					++Length;
				}
				if (Text.compare(Pos, Length, Literal) == 0)
				{
					Pos += Length;
					return true;
				}
				return false;
			}

			bool ParseValue(FJson& Out, int Depth)
			{
				if (Depth > 64)
				{
					return Fail("nesting too deep");
				}
				if (Pos >= Text.size())
				{
					return Fail("unexpected end of input");
				}
				const char C = Text[Pos];
				if (C == '{')
				{
					return ParseObject(Out, Depth);
				}
				if (C == '[')
				{
					return ParseArray(Out, Depth);
				}
				if (C == '"')
				{
					std::string Value;
					if (!ParseString(Value))
					{
						return false;
					}
					Out = FJson::MakeString(std::move(Value));
					return true;
				}
				if (C == '-' || (C >= '0' && C <= '9'))
				{
					return ParseNumber(Out);
				}
				if (Match("true"))
				{
					Out = FJson::MakeBool(true);
					return true;
				}
				if (Match("false"))
				{
					Out = FJson::MakeBool(false);
					return true;
				}
				if (Match("null"))
				{
					Out = FJson();
					return true;
				}
				return Fail("unexpected character");
			}

			bool ParseObject(FJson& Out, int Depth)
			{
				Out = FJson::MakeObject();
				++Pos;
				SkipWhitespace();
				if (Pos < Text.size() && Text[Pos] == '}')
				{
					++Pos;
					return true;
				}
				while (true)
				{
					SkipWhitespace();
					if (Pos >= Text.size() || Text[Pos] != '"')
					{
						return Fail("expected object key");
					}
					std::string Key;
					if (!ParseString(Key))
					{
						return false;
					}
					SkipWhitespace();
					if (Pos >= Text.size() || Text[Pos] != ':')
					{
						return Fail("expected ':'");
					}
					++Pos;
					SkipWhitespace();
					FJson Value;
					if (!ParseValue(Value, Depth + 1))
					{
						return false;
					}
					Out.Set(Key, std::move(Value));
					SkipWhitespace();
					if (Pos < Text.size() && Text[Pos] == ',')
					{
						++Pos;
						continue;
					}
					if (Pos < Text.size() && Text[Pos] == '}')
					{
						++Pos;
						return true;
					}
					return Fail("expected ',' or '}'");
				}
			}

			bool ParseArray(FJson& Out, int Depth)
			{
				Out = FJson::MakeArray();
				++Pos;
				SkipWhitespace();
				if (Pos < Text.size() && Text[Pos] == ']')
				{
					++Pos;
					return true;
				}
				while (true)
				{
					SkipWhitespace();
					FJson Value;
					if (!ParseValue(Value, Depth + 1))
					{
						return false;
					}
					Out.Push(std::move(Value));
					SkipWhitespace();
					if (Pos < Text.size() && Text[Pos] == ',')
					{
						++Pos;
						continue;
					}
					if (Pos < Text.size() && Text[Pos] == ']')
					{
						++Pos;
						return true;
					}
					return Fail("expected ',' or ']'");
				}
			}

			static void AppendUtf8(std::string& Out, uint32_t CodePoint)
			{
				if (CodePoint < 0x80)
				{
					Out.push_back(static_cast<char>(CodePoint));
				}
				else if (CodePoint < 0x800)
				{
					Out.push_back(static_cast<char>(0xC0 | (CodePoint >> 6)));
					Out.push_back(static_cast<char>(0x80 | (CodePoint & 0x3F)));
				}
				else if (CodePoint < 0x10000)
				{
					Out.push_back(static_cast<char>(0xE0 | (CodePoint >> 12)));
					Out.push_back(static_cast<char>(0x80 | ((CodePoint >> 6) & 0x3F)));
					Out.push_back(static_cast<char>(0x80 | (CodePoint & 0x3F)));
				}
				else
				{
					Out.push_back(static_cast<char>(0xF0 | (CodePoint >> 18)));
					Out.push_back(static_cast<char>(0x80 | ((CodePoint >> 12) & 0x3F)));
					Out.push_back(static_cast<char>(0x80 | ((CodePoint >> 6) & 0x3F)));
					Out.push_back(static_cast<char>(0x80 | (CodePoint & 0x3F)));
				}
			}

			bool ParseHex4(uint32_t& OutValue)
			{
				if (Pos + 4 > Text.size())
				{
					return Fail("truncated unicode escape");
				}
				OutValue = 0;
				for (int Index = 0; Index < 4; ++Index)
				{
					const char C = Text[Pos++];
					OutValue <<= 4;
					if (C >= '0' && C <= '9')
					{
						OutValue |= static_cast<uint32_t>(C - '0');
					}
					else if (C >= 'a' && C <= 'f')
					{
						OutValue |= static_cast<uint32_t>(C - 'a' + 10);
					}
					else if (C >= 'A' && C <= 'F')
					{
						OutValue |= static_cast<uint32_t>(C - 'A' + 10);
					}
					else
					{
						return Fail("invalid unicode escape");
					}
				}
				return true;
			}

			bool ParseString(std::string& Out)
			{
				++Pos;
				while (Pos < Text.size())
				{
					const char C = Text[Pos++];
					if (C == '"')
					{
						return true;
					}
					if (C != '\\')
					{
						Out.push_back(C);
						continue;
					}
					if (Pos >= Text.size())
					{
						break;
					}
					const char Escape = Text[Pos++];
					switch (Escape)
					{
					case '"': Out.push_back('"'); break;
					case '\\': Out.push_back('\\'); break;
					case '/': Out.push_back('/'); break;
					case 'b': Out.push_back('\b'); break;
					case 'f': Out.push_back('\f'); break;
					case 'n': Out.push_back('\n'); break;
					case 'r': Out.push_back('\r'); break;
					case 't': Out.push_back('\t'); break;
					case 'u':
					{
						uint32_t CodePoint = 0;
						if (!ParseHex4(CodePoint))
						{
							return false;
						}
						if (CodePoint >= 0xD800 && CodePoint <= 0xDBFF && Pos + 6 <= Text.size() && Text[Pos] == '\\' && Text[Pos + 1] == 'u')
						{
							Pos += 2;
							uint32_t Low = 0;
							if (!ParseHex4(Low))
							{
								return false;
							}
							CodePoint = 0x10000 + ((CodePoint - 0xD800) << 10) + (Low - 0xDC00);
						}
						AppendUtf8(Out, CodePoint);
						break;
					}
					default:
						return Fail("invalid escape sequence");
					}
				}
				return Fail("unterminated string");
			}

			bool ParseNumber(FJson& Out)
			{
				bool bNegative = false;
				if (Text[Pos] == '-')
				{
					bNegative = true;
					++Pos;
				}
				double Value = 0.0;
				bool bDigits = false;
				while (Pos < Text.size() && Text[Pos] >= '0' && Text[Pos] <= '9')
				{
					Value = Value * 10.0 + (Text[Pos] - '0');
					++Pos;
					bDigits = true;
				}
				if (Pos < Text.size() && Text[Pos] == '.')
				{
					++Pos;
					double Scale = 0.1;
					while (Pos < Text.size() && Text[Pos] >= '0' && Text[Pos] <= '9')
					{
						Value += (Text[Pos] - '0') * Scale;
						Scale *= 0.1;
						++Pos;
						bDigits = true;
					}
				}
				if (!bDigits)
				{
					return Fail("invalid number");
				}
				if (Pos < Text.size() && (Text[Pos] == 'e' || Text[Pos] == 'E'))
				{
					++Pos;
					bool bNegativeExponent = false;
					if (Pos < Text.size() && (Text[Pos] == '+' || Text[Pos] == '-'))
					{
						bNegativeExponent = Text[Pos] == '-';
						++Pos;
					}
					int Exponent = 0;
					while (Pos < Text.size() && Text[Pos] >= '0' && Text[Pos] <= '9')
					{
						Exponent = Exponent * 10 + (Text[Pos] - '0');
						if (Exponent > 400)
						{
							Exponent = 400;
						}
						++Pos;
					}
					Value *= std::pow(10.0, bNegativeExponent ? -Exponent : Exponent);
				}
				Out = FJson::MakeNumber(bNegative ? -Value : Value);
				return true;
			}

			const std::string& Text;
			std::string& Error;
			size_t Pos = 0;
		};

		void WriteEscaped(std::string& Out, const std::string& Value)
		{
			Out.push_back('"');
			for (const char C : Value)
			{
				switch (C)
				{
				case '"': Out += "\\\""; break;
				case '\\': Out += "\\\\"; break;
				case '\n': Out += "\\n"; break;
				case '\r': Out += "\\r"; break;
				case '\t': Out += "\\t"; break;
				default:
					if (static_cast<unsigned char>(C) < 0x20)
					{
						char Buffer[8];
						std::snprintf(Buffer, sizeof(Buffer), "\\u%04x", static_cast<unsigned int>(static_cast<unsigned char>(C)));
						Out += Buffer;
					}
					else
					{
						Out.push_back(C);
					}
				}
			}
			Out.push_back('"');
		}

		void WriteNumber(std::string& Out, double Value)
		{
			if (!std::isfinite(Value))
			{
				Out += "0";
				return;
			}
			const double Rounded = std::floor(Value);
			if (Rounded == Value && std::fabs(Value) < 1e15)
			{
				Out += std::to_string(static_cast<long long>(Value));
				return;
			}
			// Fixed notation with an explicit '.' keeps output independent from the C locale.
			const bool bNegative = Value < 0.0;
			const double Magnitude = bNegative ? -Value : Value;
			const long long Whole = static_cast<long long>(std::floor(Magnitude));
			long long Fraction = static_cast<long long>(std::llround((Magnitude - static_cast<double>(Whole)) * 1000000.0));
			long long WholePart = Whole;
			if (Fraction >= 1000000)
			{
				Fraction -= 1000000;
				++WholePart;
			}
			char Buffer[64];
			std::snprintf(Buffer, sizeof(Buffer), "%s%lld.%06lld", bNegative ? "-" : "", WholePart, Fraction);
			std::string Text = Buffer;
			while (!Text.empty() && Text.back() == '0')
			{
				Text.pop_back();
			}
			if (!Text.empty() && Text.back() == '.')
			{
				Text.push_back('0');
			}
			Out += Text;
		}

		void WriteIndent(std::string& Out, int Indent)
		{
			Out.append(static_cast<size_t>(Indent) * 2, ' ');
		}
	}

	FJson FJson::MakeBool(bool bValue)
	{
		FJson Result;
		Result.Type = EJsonType::Bool;
		Result.bBoolValue = bValue;
		return Result;
	}

	FJson FJson::MakeNumber(double Value)
	{
		FJson Result;
		Result.Type = EJsonType::Number;
		Result.NumberValue = Value;
		return Result;
	}

	FJson FJson::MakeString(std::string Value)
	{
		FJson Result;
		Result.Type = EJsonType::String;
		Result.StringValue = std::move(Value);
		return Result;
	}

	FJson FJson::MakeArray()
	{
		FJson Result;
		Result.Type = EJsonType::Array;
		return Result;
	}

	FJson FJson::MakeObject()
	{
		FJson Result;
		Result.Type = EJsonType::Object;
		return Result;
	}

	bool FJson::AsBool(bool bDefault) const
	{
		if (Type == EJsonType::Bool)
		{
			return bBoolValue;
		}
		if (Type == EJsonType::Number)
		{
			return NumberValue != 0.0;
		}
		return bDefault;
	}

	double FJson::AsNumber(double Default) const
	{
		return Type == EJsonType::Number ? NumberValue : Default;
	}

	int FJson::AsInt(int Default) const
	{
		if (Type != EJsonType::Number)
		{
			return Default;
		}
		const double Rounded = std::floor(NumberValue + 0.5);
		if (Rounded > 2147483647.0)
		{
			return 2147483647;
		}
		if (Rounded < -2147483647.0)
		{
			return -2147483647;
		}
		return static_cast<int>(Rounded);
	}

	const std::string& FJson::AsString() const
	{
		return Type == EJsonType::String ? StringValue : JsonDetail::EmptyString();
	}

	size_t FJson::Size() const
	{
		if (Type == EJsonType::Array)
		{
			return ArrayValue.size();
		}
		if (Type == EJsonType::Object)
		{
			return ObjectValue.size();
		}
		return 0;
	}

	const FJson& FJson::At(size_t Index) const
	{
		if (Type == EJsonType::Array && Index < ArrayValue.size())
		{
			return ArrayValue[Index];
		}
		return JsonDetail::NullValue();
	}

	FJson& FJson::Push(FJson Value)
	{
		if (Type != EJsonType::Array)
		{
			*this = MakeArray();
		}
		ArrayValue.push_back(std::move(Value));
		return ArrayValue.back();
	}

	FJson& FJson::PushInt(int Value)
	{
		return Push(MakeNumber(Value));
	}

	FJson& FJson::PushString(const std::string& Value)
	{
		return Push(MakeString(Value));
	}

	bool FJson::Has(const std::string& Key) const
	{
		if (Type != EJsonType::Object)
		{
			return false;
		}
		for (const std::pair<std::string, FJson>& Member : ObjectValue)
		{
			if (Member.first == Key)
			{
				return true;
			}
		}
		return false;
	}

	const FJson& FJson::Get(const std::string& Key) const
	{
		if (Type == EJsonType::Object)
		{
			for (const std::pair<std::string, FJson>& Member : ObjectValue)
			{
				if (Member.first == Key)
				{
					return Member.second;
				}
			}
		}
		return JsonDetail::NullValue();
	}

	FJson& FJson::Set(const std::string& Key, FJson Value)
	{
		if (Type != EJsonType::Object)
		{
			*this = MakeObject();
		}
		for (std::pair<std::string, FJson>& Member : ObjectValue)
		{
			if (Member.first == Key)
			{
				Member.second = std::move(Value);
				return Member.second;
			}
		}
		ObjectValue.emplace_back(Key, std::move(Value));
		return ObjectValue.back().second;
	}

	FJson& FJson::SetInt(const std::string& Key, int Value)
	{
		return Set(Key, MakeNumber(Value));
	}

	FJson& FJson::SetNumber(const std::string& Key, double Value)
	{
		return Set(Key, MakeNumber(Value));
	}

	FJson& FJson::SetBool(const std::string& Key, bool bValue)
	{
		return Set(Key, MakeBool(bValue));
	}

	FJson& FJson::SetString(const std::string& Key, const std::string& Value)
	{
		return Set(Key, MakeString(Value));
	}

	int FJson::GetInt(const std::string& Key, int Default) const
	{
		return Get(Key).AsInt(Default);
	}

	double FJson::GetNumber(const std::string& Key, double Default) const
	{
		return Get(Key).AsNumber(Default);
	}

	bool FJson::GetBool(const std::string& Key, bool bDefault) const
	{
		return Get(Key).AsBool(bDefault);
	}

	std::string FJson::GetString(const std::string& Key, const std::string& Default) const
	{
		const FJson& Value = Get(Key);
		return Value.IsString() ? Value.AsString() : Default;
	}

	bool FJson::Parse(const std::string& Text, FJson& OutValue, std::string& OutError)
	{
		OutError.clear();
		JsonDetail::FParser Parser(Text, OutError);
		FJson Result;
		if (!Parser.ParseDocument(Result))
		{
			return false;
		}
		OutValue = std::move(Result);
		return true;
	}

	std::string FJson::Write(bool bPretty) const
	{
		std::string Out;
		WriteTo(Out, bPretty, 0);
		if (bPretty)
		{
			Out.push_back('\n');
		}
		return Out;
	}

	void FJson::WriteTo(std::string& Out, bool bPretty, int Indent) const
	{
		switch (Type)
		{
		case EJsonType::Null:
			Out += "null";
			break;
		case EJsonType::Bool:
			Out += bBoolValue ? "true" : "false";
			break;
		case EJsonType::Number:
			JsonDetail::WriteNumber(Out, NumberValue);
			break;
		case EJsonType::String:
			JsonDetail::WriteEscaped(Out, StringValue);
			break;
		case EJsonType::Array:
		{
			if (ArrayValue.empty())
			{
				Out += "[]";
				break;
			}
			// Scalar lists and lists of small scalar tuples (map points) stay on one line.
			bool bAllScalars = true;
			bool bAllSmallTuples = true;
			for (const FJson& Item : ArrayValue)
			{
				if (Item.IsArray() || Item.IsObject())
				{
					bAllScalars = false;
				}
				bool bSmallTuple = Item.IsArray() && Item.ArrayValue.size() <= 4;
				for (const FJson& Inner : Item.ArrayValue)
				{
					bSmallTuple = bSmallTuple && !Inner.IsArray() && !Inner.IsObject();
				}
				bAllSmallTuples = bAllSmallTuples && bSmallTuple;
			}
			const bool bInline = !bPretty || bAllScalars || bAllSmallTuples;
			Out.push_back('[');
			for (size_t Index = 0; Index < ArrayValue.size(); ++Index)
			{
				if (Index > 0)
				{
					Out.push_back(',');
					if (bPretty && bInline)
					{
						Out.push_back(' ');
					}
				}
				if (!bInline)
				{
					Out.push_back('\n');
					JsonDetail::WriteIndent(Out, Indent + 1);
				}
				ArrayValue[Index].WriteTo(Out, bPretty, Indent + 1);
			}
			if (!bInline)
			{
				Out.push_back('\n');
				JsonDetail::WriteIndent(Out, Indent);
			}
			Out.push_back(']');
			break;
		}
		case EJsonType::Object:
		{
			if (ObjectValue.empty())
			{
				Out += "{}";
				break;
			}
			Out.push_back('{');
			for (size_t Index = 0; Index < ObjectValue.size(); ++Index)
			{
				if (Index > 0)
				{
					Out.push_back(',');
				}
				if (bPretty)
				{
					Out.push_back('\n');
					JsonDetail::WriteIndent(Out, Indent + 1);
				}
				JsonDetail::WriteEscaped(Out, ObjectValue[Index].first);
				Out += bPretty ? ": " : ":";
				ObjectValue[Index].second.WriteTo(Out, bPretty, Indent + 1);
			}
			if (bPretty)
			{
				Out.push_back('\n');
				JsonDetail::WriteIndent(Out, Indent);
			}
			Out.push_back('}');
			break;
		}
		}
	}
}
