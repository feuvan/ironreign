#include "Sim/IronState.h"

#include "Sim/IronLocale.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <unordered_map>

namespace IronSim
{
	namespace StateDetail
	{
		using FKeyMap = std::unordered_map<std::string, int>;

		template <typename EntityType>
		int FindByKey(const std::vector<EntityType>& Entities, const std::string& Key)
		{
			for (size_t Index = 0; Index < Entities.size(); ++Index)
			{
				if (Entities[Index].Key == Key)
				{
					return static_cast<int>(Index);
				}
			}
			return -1;
		}

		FPoint ReadPoint(const FJson& Value)
		{
			FPoint Point;
			Point.X = static_cast<float>(Value.At(0).AsNumber());
			Point.Y = static_cast<float>(Value.At(1).AsNumber());
			return Point;
		}

		std::vector<FPoint> ReadPoints(const FJson& Value)
		{
			std::vector<FPoint> Points;
			for (const FJson& Item : Value.Items())
			{
				Points.push_back(ReadPoint(Item));
			}
			return Points;
		}

		FJson WritePoints(const std::vector<FPoint>& Points)
		{
			FJson Array = FJson::MakeArray();
			for (const FPoint& Point : Points)
			{
				FJson Pair = FJson::MakeArray();
				Pair.Push(FJson::MakeNumber(Point.X));
				Pair.Push(FJson::MakeNumber(Point.Y));
				Array.Push(Pair);
			}
			return Array;
		}

		std::vector<FMapStroke> ReadStrokes(const FJson& Value)
		{
			std::vector<FMapStroke> Strokes;
			for (const FJson& Item : Value.Items())
			{
				FMapStroke Stroke;
				Stroke.Points = ReadPoints(Item.Get("points"));
				Stroke.Width = static_cast<float>(Item.GetNumber("width", 10.0));
				Strokes.push_back(Stroke);
			}
			return Strokes;
		}

		FJson WriteStrokes(const std::vector<FMapStroke>& Strokes)
		{
			FJson Array = FJson::MakeArray();
			for (const FMapStroke& Stroke : Strokes)
			{
				FJson Item = FJson::MakeObject();
				Item.Set("points", WritePoints(Stroke.Points));
				Item.SetNumber("width", Stroke.Width);
				Array.Push(Item);
			}
			return Array;
		}

		std::vector<FMapCircle> ReadCircles(const FJson& Value)
		{
			std::vector<FMapCircle> Circles;
			for (const FJson& Item : Value.Items())
			{
				FMapCircle Circle;
				Circle.Center.X = static_cast<float>(Item.GetNumber("x"));
				Circle.Center.Y = static_cast<float>(Item.GetNumber("y"));
				Circle.Radius = static_cast<float>(Item.GetNumber("r", 50.0));
				Circles.push_back(Circle);
			}
			return Circles;
		}

		FJson WriteCircles(const std::vector<FMapCircle>& Circles)
		{
			FJson Array = FJson::MakeArray();
			for (const FMapCircle& Circle : Circles)
			{
				FJson Item = FJson::MakeObject();
				Item.SetNumber("x", Circle.Center.X);
				Item.SetNumber("y", Circle.Center.Y);
				Item.SetNumber("r", Circle.Radius);
				Array.Push(Item);
			}
			return Array;
		}

		std::string ToHex64(uint64_t Value)
		{
			char Buffer[32];
			std::snprintf(Buffer, sizeof(Buffer), "%016llx", static_cast<unsigned long long>(Value));
			return Buffer;
		}

		uint64_t FromHex64(const std::string& Text, uint64_t Default)
		{
			if (Text.empty())
			{
				return Default;
			}
			uint64_t Value = 0;
			for (const char C : Text)
			{
				Value <<= 4;
				if (C >= '0' && C <= '9')
				{
					Value |= static_cast<uint64_t>(C - '0');
				}
				else if (C >= 'a' && C <= 'f')
				{
					Value |= static_cast<uint64_t>(C - 'a' + 10);
				}
				else if (C >= 'A' && C <= 'F')
				{
					Value |= static_cast<uint64_t>(C - 'A' + 10);
				}
				else
				{
					return Default;
				}
			}
			return Value;
		}

		/** Resolves key references while loading and collects the first error. */
		class FLoader
		{
		public:
			explicit FLoader(FGameState& InState)
				: State(InState)
			{
			}

			bool Load(const FJson& Root, std::string& OutError);

		private:
			bool Fail(const std::string& Message)
			{
				if (Error.empty())
				{
					Error = Message;
				}
				return false;
			}

			template <typename EnumType>
			EnumType ReadEnum(const FJson& Object, const char* Field, EnumType Default, const std::string& Context)
			{
				const FJson& Value = Object.Get(Field);
				if (Value.IsNull())
				{
					return Default;
				}
				EnumType Result = Default;
				if (!Value.IsString() || !EnumParse(Value.AsString(), Result))
				{
					Fail(Context + ": invalid " + Field + " '" + Value.AsString() + "'");
				}
				return Result;
			}

			/** Reads an optional key reference. Missing/null -> -1. Unknown key -> error. */
			int ReadRef(const FKeyMap& Map, const FJson& Object, const char* Field, const char* Kind, const std::string& Context)
			{
				const FJson& Value = Object.Get(Field);
				if (Value.IsNull())
				{
					return -1;
				}
				return ResolveKey(Map, Value, Kind, Context);
			}

			int ResolveKey(const FKeyMap& Map, const FJson& Value, const char* Kind, const std::string& Context)
			{
				if (Value.IsNull())
				{
					return -1;
				}
				if (!Value.IsString())
				{
					Fail(Context + ": expected " + Kind + " key");
					return -1;
				}
				if (Value.AsString().empty())
				{
					return -1;
				}
				const auto Found = Map.find(Value.AsString());
				if (Found == Map.end())
				{
					Fail(Context + ": unknown " + Kind + " '" + Value.AsString() + "'");
					return -1;
				}
				return Found->second;
			}

			std::vector<int> ReadRefList(const FKeyMap& Map, const FJson& Value, const char* Kind, const std::string& Context)
			{
				std::vector<int> Result;
				for (const FJson& Item : Value.Items())
				{
					const int Index = ResolveKey(Map, Item, Kind, Context);
					if (Index >= 0)
					{
						Result.push_back(Index);
					}
				}
				return Result;
			}

			int ReadCitySelector(const FJson& Value, const std::string& Context)
			{
				if (Value.IsNull())
				{
					return RefNone;
				}
				if (Value.AsString() == "context")
				{
					return RefContext;
				}
				if (Value.AsString() == "capital")
				{
					return RefCapital;
				}
				return ResolveKey(Cities, Value, "city", Context);
			}

			int ReadOfficerSelector(const FJson& Value, const std::string& Context)
			{
				if (Value.IsNull())
				{
					return RefNone;
				}
				if (Value.AsString() == "context")
				{
					return RefContext;
				}
				if (Value.AsString() == "ruler")
				{
					return RefRuler;
				}
				return ResolveKey(Officers, Value, "officer", Context);
			}

			int ReadFactionSelector(const FJson& Value, const std::string& Context)
			{
				if (Value.IsNull())
				{
					return RefNone;
				}
				if (Value.AsString() == "context")
				{
					return RefContext;
				}
				if (Value.AsString() == "player")
				{
					return RefPlayer;
				}
				return ResolveKey(Factions, Value, "faction", Context);
			}

			bool BuildKeyMap(const FJson& Array, const char* Kind, FKeyMap& OutMap)
			{
				int Index = 0;
				for (const FJson& Item : Array.Items())
				{
					const std::string Key = Item.GetString("key");
					if (Key.empty())
					{
						return Fail(std::string(Kind) + " #" + std::to_string(Index) + " has no key");
					}
					if (!OutMap.emplace(Key, Index).second)
					{
						return Fail(std::string("duplicate ") + Kind + " key '" + Key + "'");
					}
					++Index;
				}
				return true;
			}

			void LoadMap(const FJson& Map);
			void LoadTechniques(const FJson& Array);
			void LoadFactions(const FJson& Array);
			void LoadCities(const FJson& Array);
			void LoadRoads(const FJson& Array);
			void LoadOfficers(const FJson& Array);
			void LoadSects(const FJson& Array);
			void LoadRelations(const FJson& Array);
			void LoadEvents(const FJson& Array);
			FEffect LoadEffect(const FJson& Object, const std::string& Context);
			std::vector<FEventChoice> LoadChoices(const FJson& Array, const std::string& Context);
			void LoadSession(const FJson& Root);
			void Validate();

			FGameState& State;
			std::string Error;
			FKeyMap Techniques;
			FKeyMap Factions;
			FKeyMap Cities;
			FKeyMap Officers;
			FKeyMap Sects;
			FKeyMap Events;
		};

		bool FLoader::Load(const FJson& Root, std::string& OutError)
		{
			if (!Root.IsObject())
			{
				OutError = "scenario root must be an object";
				return false;
			}
			State = FGameState();
			State.ScenarioKey = Root.GetString("key", "scenario");
			State.ScenarioName = Root.GetString("name", State.ScenarioKey);
			State.ScenarioDescription = Root.GetString("description");
			State.StartYear = Root.GetInt("startYear", 212);
			State.Year = State.StartYear;
			State.Month = ClampInt(Root.GetInt("startMonth", 1), 1, 12);

			BuildKeyMap(Root.Get("techniques"), "technique", Techniques);
			BuildKeyMap(Root.Get("factions"), "faction", Factions);
			BuildKeyMap(Root.Get("cities"), "city", Cities);
			BuildKeyMap(Root.Get("officers"), "officer", Officers);
			BuildKeyMap(Root.Get("sects"), "sect", Sects);
			BuildKeyMap(Root.Get("events"), "event", Events);

			LoadMap(Root.Get("map"));
			LoadTechniques(Root.Get("techniques"));
			LoadFactions(Root.Get("factions"));
			LoadCities(Root.Get("cities"));
			LoadRoads(Root.Get("roads"));
			LoadOfficers(Root.Get("officers"));
			LoadSects(Root.Get("sects"));
			LoadRelations(Root.Get("relations"));
			LoadEvents(Root.Get("events"));
			LoadSession(Root);
			if (Error.empty())
			{
				Validate();
			}
			OutError = Error;
			return Error.empty();
		}

		void FLoader::LoadMap(const FJson& Map)
		{
			FMapDef& Def = State.Map;
			Def.Width = Map.GetInt("width", 2400);
			Def.Height = Map.GetInt("height", 1500);
			Def.Image = Map.GetString("image", "Art/Map/WorldMap.png");
			for (const FJson& Polygon : Map.Get("land").Items())
			{
				Def.Land.push_back(ReadPoints(Polygon));
			}
			for (const FJson& Polygon : Map.Get("lakes").Items())
			{
				Def.Lakes.push_back(ReadPoints(Polygon));
			}
			Def.Mountains = ReadStrokes(Map.Get("mountains"));
			Def.Hills = ReadStrokes(Map.Get("hills"));
			Def.Rivers = ReadStrokes(Map.Get("rivers"));
			Def.Forests = ReadCircles(Map.Get("forests"));
			Def.Deserts = ReadCircles(Map.Get("deserts"));
			for (const FJson& Item : Map.Get("labels").Items())
			{
				FMapLabel Label;
				Label.Text = Item.GetString("text");
				Label.Position.X = static_cast<float>(Item.GetNumber("x"));
				Label.Position.Y = static_cast<float>(Item.GetNumber("y"));
				Label.Size = static_cast<float>(Item.GetNumber("size", 1.0));
				Def.Labels.push_back(Label);
			}
		}

		void FLoader::LoadTechniques(const FJson& Array)
		{
			for (const FJson& Item : Array.Items())
			{
				FTechnique Technique;
				Technique.Key = Item.GetString("key");
				const std::string Context = "technique '" + Technique.Key + "'";
				Technique.Name = Item.GetString("name", Technique.Key);
				Technique.NameZh = Item.GetString("nameZh");
				Technique.Description = Item.GetString("description");
				Technique.Kind = ReadEnum(Item, "kind", EDuelMove::Strike, Context);
				Technique.Power = ClampInt(Item.GetInt("power", 150), 100, 400);
				Technique.MinMartial = ClampInt(Item.GetInt("minMartial", 60), 1, 100);
				State.Techniques.push_back(Technique);
			}
		}

		void FLoader::LoadFactions(const FJson& Array)
		{
			for (const FJson& Item : Array.Items())
			{
				FFaction Faction;
				Faction.Key = Item.GetString("key");
				Faction.Name = Item.GetString("name", Faction.Key);
				Faction.NameZh = Item.GetString("nameZh");
				Faction.Glyph = Item.GetString("glyph");
				Faction.Color = ColorFromHex(Item.GetString("color"), 0x808080);
				Faction.bAlive = Item.GetBool("alive", true);
				State.Factions.push_back(Faction);
			}
		}

		void FLoader::LoadCities(const FJson& Array)
		{
			for (const FJson& Item : Array.Items())
			{
				FCity City;
				City.Key = Item.GetString("key");
				const std::string Context = "city '" + City.Key + "'";
				City.Name = Item.GetString("name", City.Key);
				City.NameZh = Item.GetString("nameZh");
				City.Description = Item.GetString("description");
				City.Position.X = static_cast<float>(Item.GetNumber("x"));
				City.Position.Y = static_cast<float>(Item.GetNumber("y"));
				City.Size = ClampInt(Item.GetInt("size", 2), 1, 3);
				City.Terrain = ReadEnum(Item, "terrain", ETerrain::Plains, Context);
				City.Owner = ReadRef(Factions, Item, "owner", "faction", Context);
				City.Population = std::max(0, Item.GetInt("population", City.Population));
				City.PopulationMax = std::max(City.Population, Item.GetInt("populationMax", City.PopulationMax));
				City.FarmMax = std::max(1, Item.GetInt("farmMax", City.FarmMax));
				City.Farm = ClampInt(Item.GetInt("farm", City.Farm), 0, City.FarmMax);
				City.CommerceMax = std::max(1, Item.GetInt("commerceMax", City.CommerceMax));
				City.Commerce = ClampInt(Item.GetInt("commerce", City.Commerce), 0, City.CommerceMax);
				City.DefenseMax = std::max(1, Item.GetInt("defenseMax", City.DefenseMax));
				City.Defense = ClampInt(Item.GetInt("defense", City.Defense), 0, City.DefenseMax);
				City.Order = ClampInt(Item.GetInt("order", City.Order), 0, 100);
				City.Troops = std::max(0, Item.GetInt("troops", City.Troops));
				City.Training = ClampInt(Item.GetInt("training", City.Training), 0, 100);
				City.Gold = std::max(0, Item.GetInt("gold", City.Gold));
				City.Food = std::max(0, Item.GetInt("food", City.Food));
				City.bDelegated = Item.GetBool("delegated", false);
				State.Cities.push_back(City);
			}
		}

		void FLoader::LoadRoads(const FJson& Array)
		{
			int Index = 0;
			for (const FJson& Item : Array.Items())
			{
				FRoad Road;
				const std::string Context = "road #" + std::to_string(Index++);
				Road.A = ReadRef(Cities, Item, "a", "city", Context);
				Road.B = ReadRef(Cities, Item, "b", "city", Context);
				Road.Days = ClampInt(Item.GetInt("days", 10), 1, 60);
				Road.Kind = ReadEnum(Item, "kind", ERoadKind::Road, Context);
				Road.Points = ReadPoints(Item.Get("points"));
				if (Road.A < 0 || Road.B < 0 || Road.A == Road.B)
				{
					Fail(Context + ": needs two different cities");
				}
				State.Roads.push_back(Road);
			}
		}

		void FLoader::LoadOfficers(const FJson& Array)
		{
			static const char* const StatFields[StatCount] = {"martial", "command", "strategy", "politics", "charm"};
			for (const FJson& Item : Array.Items())
			{
				FOfficer Officer;
				Officer.Key = Item.GetString("key");
				const std::string Context = "officer '" + Officer.Key + "'";
				Officer.Name = Item.GetString("name", Officer.Key);
				Officer.NameZh = Item.GetString("nameZh");
				Officer.Epithet = Item.GetString("epithet");
				Officer.Bio = Item.GetString("bio");
				Officer.Rumor = Item.GetString("rumor");
				Officer.Portrait = Item.GetString("portrait", "unknown");
				Officer.Gender = ReadEnum(Item, "gender", EGender::Male, Context);
				for (int Stat = 0; Stat < StatCount; ++Stat)
				{
					Officer.Stats[Stat] = ClampInt(Item.GetInt(StatFields[Stat], 50), 1, MaxStatValue);
					Officer.StatExp[Stat] = ClampInt(Item.Get("exp").At(static_cast<size_t>(Stat)).AsInt(0), 0, 99);
				}
				Officer.BirthYear = Item.GetInt("birth", State.StartYear - 30);
				Officer.AppearYear = Item.GetInt("appear", 0);
				Officer.Affinity = ClampInt(Item.GetInt("affinity", 75), 0, 149);
				Officer.Ambition = ClampInt(Item.GetInt("ambition", 50), 0, 100);
				Officer.Bravery = ClampInt(Item.GetInt("bravery", 50), 0, 100);
				Officer.Specialty = ReadEnum(Item, "specialty", ETroopType::Infantry, Context);
				Officer.Status = ReadEnum(Item, "status", EOfficerStatus::Free, Context);
				Officer.Faction = ReadRef(Factions, Item, "faction", "faction", Context);
				Officer.Captor = ReadRef(Factions, Item, "captor", "faction", Context);
				Officer.City = ReadRef(Cities, Item, "city", "city", Context);
				Officer.Army = Item.GetInt("army", -1);
				Officer.Loyalty = ClampInt(Item.GetInt("loyalty", Officer.Status == EOfficerStatus::Serving ? 75 : 50), 0, 100);
				Officer.Merit = std::max(0, Item.GetInt("merit", 0));
				Officer.Sect = ReadRef(Sects, Item, "sect", "sect", Context);
				Officer.Techniques = ReadRefList(Techniques, Item.Get("techniques"), "technique", Context);
				State.Officers.push_back(Officer);
			}
		}

		void FLoader::LoadSects(const FJson& Array)
		{
			for (const FJson& Item : Array.Items())
			{
				FSect Sect;
				Sect.Key = Item.GetString("key");
				const std::string Context = "sect '" + Sect.Key + "'";
				Sect.Name = Item.GetString("name", Sect.Key);
				Sect.NameZh = Item.GetString("nameZh");
				Sect.Description = Item.GetString("description");
				Sect.City = ReadRef(Cities, Item, "city", "city", Context);
				Sect.Master = ReadRef(Officers, Item, "master", "officer", Context);
				Sect.Techniques = ReadRefList(Techniques, Item.Get("techniques"), "technique", Context);
				Sect.Favor.assign(State.Factions.size(), 0);
				for (const std::pair<std::string, FJson>& Member : Item.Get("favor").Members())
				{
					const auto Found = Factions.find(Member.first);
					if (Found == Factions.end())
					{
						Fail(Context + ": unknown faction '" + Member.first + "' in favor");
						continue;
					}
					Sect.Favor[static_cast<size_t>(Found->second)] = ClampInt(Member.second.AsInt(0), 0, 100);
				}
				State.Sects.push_back(Sect);
			}
		}

		void FLoader::LoadRelations(const FJson& Array)
		{
			const size_t Count = State.Factions.size();
			State.Relations.assign(Count * Count, FRelation());
			int Index = 0;
			for (const FJson& Item : Array.Items())
			{
				const std::string Context = "relation #" + std::to_string(Index++);
				const int A = ReadRef(Factions, Item, "a", "faction", Context);
				const int B = ReadRef(Factions, Item, "b", "faction", Context);
				if (A < 0 || B < 0 || A == B)
				{
					Fail(Context + ": needs two different factions");
					continue;
				}
				FRelation& Relation = State.Relation(A, B);
				Relation.Trust = ClampInt(Item.GetInt("trust", 50), 0, 100);
				Relation.AllianceMonths = std::max(0, Item.GetInt("alliance", 0));
				Relation.TruceMonths = std::max(0, Item.GetInt("truce", 0));
			}
		}

		FEffect FLoader::LoadEffect(const FJson& Object, const std::string& Context)
		{
			FEffect Effect;
			Effect.Type = ReadEnum(Object, "type", EEffectType::Message, Context);
			Effect.Amount = Object.GetInt("amount", 0);
			Effect.City = ReadCitySelector(Object.Get("city"), Context);
			Effect.Officer = ReadOfficerSelector(Object.Get("officer"), Context);
			Effect.Faction = ReadFactionSelector(Object.Get("faction"), Context);
			Effect.Sect = ReadRef(Sects, Object, "sect", "sect", Context);
			Effect.Technique = ReadRef(Techniques, Object, "technique", "technique", Context);
			Effect.Stat = ReadEnum(Object, "stat", EStat::Martial, Context);
			Effect.Text = Object.GetString("text");
			return Effect;
		}

		std::vector<FEventChoice> FLoader::LoadChoices(const FJson& Array, const std::string& Context)
		{
			std::vector<FEventChoice> Choices;
			for (const FJson& Item : Array.Items())
			{
				FEventChoice Choice;
				Choice.Label = Item.GetString("label");
				Choice.RequireGold = std::max(0, Item.GetInt("gold", 0));
				for (const FJson& EffectJson : Item.Get("effects").Items())
				{
					Choice.Effects.push_back(LoadEffect(EffectJson, Context));
				}
				Choices.push_back(Choice);
			}
			return Choices;
		}

		void FLoader::LoadEvents(const FJson& Array)
		{
			for (const FJson& Item : Array.Items())
			{
				FEventDef Event;
				Event.Key = Item.GetString("key");
				const std::string Context = "event '" + Event.Key + "'";
				Event.Title = Item.GetString("title");
				Event.Text = Item.GetString("text");
				Event.Image = Item.GetString("image");
				const std::string Speaker = Item.GetString("speaker", "advisor");
				Event.Speaker = Speaker == "advisor" ? -1 : ResolveKey(Officers, Item.Get("speaker"), "officer", Context);
				Event.bWorld = Item.GetBool("world", false);
				Event.bOnce = Item.GetBool("once", true);
				Event.TimesFired = std::max(0, Item.GetInt("fired", 0));

				const std::string ContextText = Item.GetString("context", Event.bWorld ? "random_city" : "random_player_city");
				if (ContextText == "random_player_city")
				{
					Event.Context = EEventContext::RandomPlayerCity;
				}
				else if (ContextText == "capital")
				{
					Event.Context = EEventContext::Capital;
				}
				else if (ContextText == "random_city")
				{
					Event.Context = EEventContext::RandomCity;
				}
				else
				{
					Event.Context = EEventContext::FixedCity;
					Event.ContextCity = ResolveKey(Cities, Item.Get("context"), "city", Context);
				}

				const FJson& When = Item.Get("when");
				FEventCondition& Condition = Event.Condition;
				Condition.MinYear = When.GetInt("minYear", 0);
				Condition.MaxYear = When.GetInt("maxYear", 99999);
				for (const FJson& Month : When.Get("months").Items())
				{
					Condition.Months.push_back(ClampInt(Month.AsInt(1), 1, 12));
				}
				Condition.Chance = ClampInt(When.GetInt("chance", 100), 0, 100);
				Condition.OwnsCity = ReadRef(Cities, When, "ownsCity", "city", Context);
				Condition.HasOfficer = ReadRef(Officers, When, "hasOfficer", "officer", Context);
				Condition.Faction = ReadRef(Factions, When, "faction", "faction", Context);
				Condition.MinCities = When.GetInt("minCities", 0);
				Condition.MaxCities = When.GetInt("maxCities", 9999);

				for (const FJson& EffectJson : Item.Get("effects").Items())
				{
					Event.Effects.push_back(LoadEffect(EffectJson, Context));
				}
				Event.Choices = LoadChoices(Item.Get("choices"), Context);
				State.Events.push_back(Event);
			}
		}

		void FLoader::LoadSession(const FJson& Root)
		{
			// Faction leaders and capitals.
			int Index = 0;
			for (const FJson& Item : Root.Get("factions").Items())
			{
				FFaction& Faction = State.Factions[static_cast<size_t>(Index++)];
				const std::string Context = "faction '" + Faction.Key + "'";
				Faction.Ruler = ReadRef(Officers, Item, "ruler", "officer", Context);
				Faction.Capital = ReadRef(Cities, Item, "capital", "city", Context);
			}

			const FJson& Session = Root.Get("session");
			if (Session.IsObject())
			{
				State.Year = Session.GetInt("year", State.Year);
				State.Month = ClampInt(Session.GetInt("month", State.Month), 1, 12);
				State.Day = ClampInt(Session.GetInt("day", 0), 0, DaysPerMonth);
				State.Phase = ReadEnum(Session, "phase", EPhase::Planning, "session");
				State.Outcome = ReadEnum(Session, "outcome", EOutcome::None, "session");
				State.Difficulty = ReadEnum(Session, "difficulty", EDifficulty::Normal, "session");
				State.PlayerFaction = ReadRef(Factions, Session, "player", "faction", "session");
				State.Rng.SetState(FromHex64(Session.GetString("rng"), State.Rng.GetState()));
				State.NextArmyId = std::max(1, Session.GetInt("nextArmyId", 1));
				State.bDayInProgress = Session.GetBool("dayInProgress", false);
			}

			for (const FJson& Item : Root.Get("armies").Items())
			{
				FArmy Army;
				Army.Id = Item.GetInt("id");
				const std::string Context = "army " + std::to_string(Army.Id);
				Army.Faction = ReadRef(Factions, Item, "faction", "faction", Context);
				for (const FJson& UnitJson : Item.Get("units").Items())
				{
					FArmyUnit Unit;
					Unit.Officer = ReadRef(Officers, UnitJson, "officer", "officer", Context);
					Unit.Troops = std::max(0, UnitJson.GetInt("troops"));
					Unit.Type = ReadEnum(UnitJson, "type", ETroopType::Infantry, Context);
					Army.Units.push_back(Unit);
				}
				Army.Food = std::max(0, Item.GetInt("food"));
				Army.Training = ClampInt(Item.GetInt("training", 50), 0, 100);
				Army.Morale = ClampInt(Item.GetInt("morale", 70), 0, 100);
				Army.Home = ReadRef(Cities, Item, "home", "city", Context);
				Army.Target = ReadRef(Cities, Item, "target", "city", Context);
				Army.State = ReadEnum(Item, "state", EArmyState::Marching, Context);
				Army.Node = ReadRef(Cities, Item, "node", "city", Context);
				Army.Next = ReadRef(Cities, Item, "next", "city", Context);
				Army.Road = Item.GetInt("road", -1);
				if (Army.Road >= static_cast<int>(State.Roads.size()))
				{
					Fail(Context + ": invalid road index");
				}
				Army.Progress = std::max(0, Item.GetInt("progress"));
				Army.Route = ReadRefList(Cities, Item.Get("route"), "city", Context);
				Army.bNew = Item.GetBool("new", false);
				State.Armies.push_back(Army);
			}

			for (const FJson& Item : Root.Get("orders").Items())
			{
				FOrder Order;
				const std::string Context = "order";
				Order.Type = ReadEnum(Item, "type", EOrderType::Farm, Context);
				Order.Officer = ReadRef(Officers, Item, "officer", "officer", Context);
				Order.City = ReadRef(Cities, Item, "city", "city", Context);
				Order.TargetCity = ReadRef(Cities, Item, "targetCity", "city", Context);
				Order.TargetOfficer = ReadRef(Officers, Item, "targetOfficer", "officer", Context);
				Order.TargetFaction = ReadRef(Factions, Item, "targetFaction", "faction", Context);
				Order.TargetSect = ReadRef(Sects, Item, "targetSect", "sect", Context);
				Order.Amount = Item.GetInt("amount");
				Order.Gold = Item.GetInt("gold");
				Order.Food = Item.GetInt("food");
				Order.Troops = Item.GetInt("troops");
				Order.Cost = Item.GetInt("cost");
				State.Orders.push_back(Order);
			}

			for (const FJson& Item : Root.Get("pendingEvents").Items())
			{
				FPendingEvent Pending;
				const std::string Context = "pending event";
				Pending.Def = ReadRef(Events, Item, "def", "event", Context);
				Pending.Title = Item.GetString("title");
				Pending.Text = Item.GetString("text");
				Pending.Image = Item.GetString("image");
				Pending.Speaker = ReadRef(Officers, Item, "speaker", "officer", Context);
				Pending.City = ReadRef(Cities, Item, "city", "city", Context);
				Pending.Faction = ReadRef(Factions, Item, "faction", "faction", Context);
				Pending.Officer = ReadRef(Officers, Item, "officer", "officer", Context);
				Pending.Choices = LoadChoices(Item.Get("choices"), Context);
				State.PendingEvents.push_back(Pending);
			}

			State.PendingPrisoners = ReadRefList(Officers, Root.Get("pendingPrisoners"), "officer", "pending prisoners");

			for (const FJson& Item : Root.Get("battleQueue").Items())
			{
				FPendingBattle Battle;
				Battle.Kind = ReadEnum(Item, "kind", EBattleKind::Siege, "battle queue");
				Battle.Attacker = Item.GetInt("attacker");
				Battle.Defender = Item.GetInt("defender");
				Battle.City = ReadRef(Cities, Item, "city", "city", "battle queue");
				State.BattleQueue.push_back(Battle);
			}

			for (const FJson& Item : Root.Get("log").Items())
			{
				FLogEntry Entry;
				Entry.Year = Item.GetInt("y");
				Entry.Month = Item.GetInt("m");
				Entry.Day = Item.GetInt("d");
				Entry.Faction = ReadRef(Factions, Item, "f", "faction", "log");
				Entry.bImportant = Item.GetBool("i", false);
				Entry.Text = Item.GetString("t");
				State.Log.push_back(Entry);
			}
		}

		void FLoader::Validate()
		{
			const int CityCount = static_cast<int>(State.Cities.size());
			if (CityCount == 0)
			{
				Fail("scenario has no cities");
				return;
			}
			for (const FFaction& Faction : State.Factions)
			{
				if (Faction.bAlive && (Faction.Capital < 0 || Faction.Capital >= CityCount))
				{
					Fail("faction '" + Faction.Key + "' has no capital");
				}
			}
			for (const FOfficer& Officer : State.Officers)
			{
				const std::string Context = "officer '" + Officer.Key + "'";
				switch (Officer.Status)
				{
				case EOfficerStatus::Serving:
					if (Officer.Faction < 0)
					{
						Fail(Context + ": serving officers need a faction");
					}
					if (Officer.City < 0 && Officer.Army < 0)
					{
						Fail(Context + ": serving officers need a city or an army");
					}
					break;
				case EOfficerStatus::Prisoner:
					if (Officer.Captor < 0 || Officer.City < 0)
					{
						Fail(Context + ": prisoners need a captor and a city");
					}
					break;
				case EOfficerStatus::Free:
				case EOfficerStatus::Hidden:
				case EOfficerStatus::Unborn:
					if (Officer.City < 0)
					{
						Fail(Context + ": needs a city");
					}
					break;
				case EOfficerStatus::Dead:
					break;
				}
			}
		}
	}

	// ---------------------------------------------------------------------------------------------
	// FGameState helpers
	// ---------------------------------------------------------------------------------------------

	int FGameState::FindTechnique(const std::string& Key) const { return StateDetail::FindByKey(Techniques, Key); }
	int FGameState::FindFaction(const std::string& Key) const { return StateDetail::FindByKey(Factions, Key); }
	int FGameState::FindCity(const std::string& Key) const { return StateDetail::FindByKey(Cities, Key); }
	int FGameState::FindOfficer(const std::string& Key) const { return StateDetail::FindByKey(Officers, Key); }
	int FGameState::FindSect(const std::string& Key) const { return StateDetail::FindByKey(Sects, Key); }
	int FGameState::FindEvent(const std::string& Key) const { return StateDetail::FindByKey(Events, Key); }

	FRelation& FGameState::Relation(int FactionA, int FactionB)
	{
		static FRelation Scratch;
		const int Count = static_cast<int>(Factions.size());
		if (FactionA < 0 || FactionB < 0 || FactionA >= Count || FactionB >= Count || FactionA == FactionB)
		{
			Scratch = FRelation();
			return Scratch;
		}
		if (Relations.size() != static_cast<size_t>(Count * Count))
		{
			Relations.resize(static_cast<size_t>(Count * Count));
		}
		const int Low = std::min(FactionA, FactionB);
		const int High = std::max(FactionA, FactionB);
		return Relations[static_cast<size_t>(Low * Count + High)];
	}

	const FRelation& FGameState::Relation(int FactionA, int FactionB) const
	{
		static const FRelation Default;
		const int Count = static_cast<int>(Factions.size());
		if (FactionA < 0 || FactionB < 0 || FactionA >= Count || FactionB >= Count || FactionA == FactionB
			|| Relations.size() != static_cast<size_t>(Count * Count))
		{
			return Default;
		}
		const int Low = std::min(FactionA, FactionB);
		const int High = std::max(FactionA, FactionB);
		return Relations[static_cast<size_t>(Low * Count + High)];
	}

	bool FGameState::AreAllied(int FactionA, int FactionB) const
	{
		return FactionA >= 0 && FactionB >= 0 && FactionA != FactionB && Relation(FactionA, FactionB).AllianceMonths > 0;
	}

	bool FGameState::HaveTruce(int FactionA, int FactionB) const
	{
		return FactionA >= 0 && FactionB >= 0 && FactionA != FactionB && Relation(FactionA, FactionB).TruceMonths > 0;
	}

	bool FGameState::AreHostile(int FactionA, int FactionB) const
	{
		if (FactionA == FactionB)
		{
			return false;
		}
		if (FactionA < 0 || FactionB < 0)
		{
			return true;
		}
		return !AreAllied(FactionA, FactionB) && !HaveTruce(FactionA, FactionB);
	}

	std::vector<int> FGameState::CityOfficers(int City) const
	{
		std::vector<int> Result;
		if (City < 0 || City >= static_cast<int>(Cities.size()))
		{
			return Result;
		}
		const int Owner = Cities[static_cast<size_t>(City)].Owner;
		for (size_t Index = 0; Index < Officers.size(); ++Index)
		{
			const FOfficer& Officer = Officers[Index];
			if (Officer.Status == EOfficerStatus::Serving && Officer.City == City && Officer.Army < 0 && Officer.Faction == Owner)
			{
				Result.push_back(static_cast<int>(Index));
			}
		}
		return Result;
	}

	std::vector<int> FGameState::FreeOfficersInCity(int City) const
	{
		std::vector<int> Result;
		for (size_t Index = 0; Index < Officers.size(); ++Index)
		{
			if (Officers[Index].Status == EOfficerStatus::Free && Officers[Index].City == City)
			{
				Result.push_back(static_cast<int>(Index));
			}
		}
		return Result;
	}

	std::vector<int> FGameState::PrisonersInCity(int City) const
	{
		std::vector<int> Result;
		for (size_t Index = 0; Index < Officers.size(); ++Index)
		{
			if (Officers[Index].Status == EOfficerStatus::Prisoner && Officers[Index].City == City)
			{
				Result.push_back(static_cast<int>(Index));
			}
		}
		return Result;
	}

	std::vector<int> FGameState::FactionCities(int Faction) const
	{
		std::vector<int> Result;
		for (size_t Index = 0; Index < Cities.size(); ++Index)
		{
			if (Faction >= 0 && Cities[Index].Owner == Faction)
			{
				Result.push_back(static_cast<int>(Index));
			}
		}
		return Result;
	}

	std::vector<int> FGameState::FactionOfficers(int Faction) const
	{
		std::vector<int> Result;
		for (size_t Index = 0; Index < Officers.size(); ++Index)
		{
			if (Faction >= 0 && Officers[Index].Status == EOfficerStatus::Serving && Officers[Index].Faction == Faction)
			{
				Result.push_back(static_cast<int>(Index));
			}
		}
		return Result;
	}

	std::vector<int> FGameState::Neighbors(int City) const
	{
		std::vector<int> Result;
		for (const FRoad& Road : Roads)
		{
			if (Road.A == City)
			{
				Result.push_back(Road.B);
			}
			else if (Road.B == City)
			{
				Result.push_back(Road.A);
			}
		}
		return Result;
	}

	int FGameState::RoadBetween(int CityA, int CityB) const
	{
		for (size_t Index = 0; Index < Roads.size(); ++Index)
		{
			const FRoad& Road = Roads[Index];
			if ((Road.A == CityA && Road.B == CityB) || (Road.A == CityB && Road.B == CityA))
			{
				return static_cast<int>(Index);
			}
		}
		return -1;
	}

	int FGameState::SectInCity(int City) const
	{
		for (size_t Index = 0; Index < Sects.size(); ++Index)
		{
			if (Sects[Index].City == City)
			{
				return static_cast<int>(Index);
			}
		}
		return -1;
	}

	FArmy* FGameState::FindArmy(int ArmyId)
	{
		for (FArmy& Army : Armies)
		{
			if (Army.Id == ArmyId)
			{
				return &Army;
			}
		}
		return nullptr;
	}

	const FArmy* FGameState::FindArmy(int ArmyId) const
	{
		for (const FArmy& Army : Armies)
		{
			if (Army.Id == ArmyId)
			{
				return &Army;
			}
		}
		return nullptr;
	}

	const FOrder* FGameState::OfficerOrder(int Officer) const
	{
		for (const FOrder& Order : Orders)
		{
			if (Order.Officer == Officer)
			{
				return &Order;
			}
		}
		return nullptr;
	}

	bool FGameState::IsOfficerIdle(int Officer) const
	{
		if (Officer < 0 || Officer >= static_cast<int>(Officers.size()))
		{
			return false;
		}
		const FOfficer& Data = Officers[static_cast<size_t>(Officer)];
		return Data.Status == EOfficerStatus::Serving && Data.City >= 0 && Data.Army < 0 && OfficerOrder(Officer) == nullptr;
	}

	bool FGameState::IsRuler(int Officer) const
	{
		if (Officer < 0)
		{
			return false;
		}
		for (const FFaction& Faction : Factions)
		{
			if (Faction.bAlive && Faction.Ruler == Officer)
			{
				return true;
			}
		}
		return false;
	}

	int FGameState::OfficerAge(int Officer) const
	{
		if (Officer < 0 || Officer >= static_cast<int>(Officers.size()))
		{
			return 0;
		}
		return Year - Officers[static_cast<size_t>(Officer)].BirthYear;
	}

	FPoint FGameState::RoadPoint(int Road, int FromCity, float T) const
	{
		FPoint Result;
		if (Road < 0 || Road >= static_cast<int>(Roads.size()))
		{
			return Result;
		}
		const FRoad& Data = Roads[static_cast<size_t>(Road)];
		std::vector<FPoint> Path;
		Path.push_back(Cities[static_cast<size_t>(Data.A)].Position);
		Path.insert(Path.end(), Data.Points.begin(), Data.Points.end());
		Path.push_back(Cities[static_cast<size_t>(Data.B)].Position);
		if (FromCity == Data.B)
		{
			std::reverse(Path.begin(), Path.end());
		}

		float Total = 0.0f;
		for (size_t Index = 1; Index < Path.size(); ++Index)
		{
			Total += std::hypot(Path[Index].X - Path[Index - 1].X, Path[Index].Y - Path[Index - 1].Y);
		}
		float Remaining = std::clamp(T, 0.0f, 1.0f) * Total;
		for (size_t Index = 1; Index < Path.size(); ++Index)
		{
			const float Segment = std::hypot(Path[Index].X - Path[Index - 1].X, Path[Index].Y - Path[Index - 1].Y);
			if (Remaining <= Segment || Index + 1 == Path.size())
			{
				const float Alpha = Segment > 0.0f ? std::clamp(Remaining / Segment, 0.0f, 1.0f) : 0.0f;
				Result.X = Path[Index - 1].X + (Path[Index].X - Path[Index - 1].X) * Alpha;
				Result.Y = Path[Index - 1].Y + (Path[Index].Y - Path[Index - 1].Y) * Alpha;
				return Result;
			}
			Remaining -= Segment;
		}
		return Path.back();
	}

	int FGameState::RoadLength(int Road) const
	{
		if (Road < 0 || Road >= static_cast<int>(Roads.size()))
		{
			return 10;
		}
		return std::max(1, Roads[static_cast<size_t>(Road)].Days) * 10;
	}

	int FGameState::ArmySpeed(const FArmy& Army) const
	{
		int Cavalry = 0;
		const int Total = Army.TotalTroops();
		for (const FArmyUnit& Unit : Army.Units)
		{
			if (Unit.Type == ETroopType::Cavalry)
			{
				Cavalry += Unit.Troops;
			}
		}
		return (Total > 0 && Cavalry * 10 >= Total * 6) ? 13 : 10;
	}

	FPoint FGameState::ArmyPosition(const FArmy& Army, float FractionalDay) const
	{
		if (Army.Next < 0 || Army.Road < 0)
		{
			if (Army.Node >= 0 && Army.Node < static_cast<int>(Cities.size()))
			{
				return Cities[static_cast<size_t>(Army.Node)].Position;
			}
			return FPoint();
		}
		const float Length = static_cast<float>(RoadLength(Army.Road));
		const float Travelled = static_cast<float>(Army.Progress) + std::clamp(FractionalDay, 0.0f, 1.0f) * static_cast<float>(ArmySpeed(Army));
		return RoadPoint(Army.Road, Army.Node, std::min(1.0f, Travelled / Length));
	}

	int FGameState::FactionTotalTroops(int Faction) const
	{
		int Total = 0;
		for (const FCity& City : Cities)
		{
			if (City.Owner == Faction)
			{
				Total += City.Troops;
			}
		}
		for (const FArmy& Army : Armies)
		{
			if (Army.Faction == Faction)
			{
				Total += Army.TotalTroops();
			}
		}
		return Total;
	}

	int FGameState::FactionTotalGold(int Faction) const
	{
		int Total = 0;
		for (const FCity& City : Cities)
		{
			if (City.Owner == Faction)
			{
				Total += City.Gold;
			}
		}
		return Total;
	}

	int FGameState::FactionTotalFood(int Faction) const
	{
		int Total = 0;
		for (const FCity& City : Cities)
		{
			if (City.Owner == Faction)
			{
				Total += City.Food;
			}
		}
		for (const FArmy& Army : Armies)
		{
			if (Army.Faction == Faction)
			{
				Total += Army.Food;
			}
		}
		return Total;
	}

	void FGameState::AddLog(int Faction, bool bImportant, const std::string& Text)
	{
		FLogEntry Entry;
		Entry.Year = Year;
		Entry.Month = Month;
		Entry.Day = Day;
		Entry.Faction = Faction;
		Entry.bImportant = bImportant;
		Entry.Text = Text;
		Log.push_back(Entry);
		if (Log.size() > static_cast<size_t>(MaxLogEntries))
		{
			Log.erase(Log.begin(), Log.begin() + static_cast<std::ptrdiff_t>(Log.size() - MaxLogEntries));
		}
	}

	// ---------------------------------------------------------------------------------------------
	// Load / save
	// ---------------------------------------------------------------------------------------------

	bool LoadGameState(const FJson& Root, FGameState& OutState, std::string& OutError)
	{
		FGameState Loaded;
		StateDetail::FLoader Loader(Loaded);
		if (!Loader.Load(Root, OutError))
		{
			return false;
		}
		OutState = std::move(Loaded);
		return true;
	}

	namespace StateDetail
	{
		class FWriter
		{
		public:
			explicit FWriter(const FGameState& InState)
				: State(InState)
			{
			}

			FJson Write() const;

		private:
			template <typename EntityType>
			static void SetRef(FJson& Object, const char* Field, const std::vector<EntityType>& Entities, int Index)
			{
				if (Index >= 0 && Index < static_cast<int>(Entities.size()))
				{
					Object.SetString(Field, Entities[static_cast<size_t>(Index)].Key);
				}
			}

			template <typename EntityType>
			static FJson RefList(const std::vector<EntityType>& Entities, const std::vector<int>& Indices)
			{
				FJson Array = FJson::MakeArray();
				for (const int Index : Indices)
				{
					if (Index >= 0 && Index < static_cast<int>(Entities.size()))
					{
						Array.PushString(Entities[static_cast<size_t>(Index)].Key);
					}
				}
				return Array;
			}

			void SetSelector(FJson& Object, const char* Field, int Value, const char* SpecialName, int SpecialValue, const std::string& Key) const
			{
				if (Value == RefContext)
				{
					Object.SetString(Field, "context");
				}
				else if (Value == SpecialValue)
				{
					Object.SetString(Field, SpecialName);
				}
				else if (Value >= 0)
				{
					Object.SetString(Field, Key);
				}
			}

			FJson WriteEffect(const FEffect& Effect) const;
			FJson WriteChoices(const std::vector<FEventChoice>& Choices) const;

			const FGameState& State;
		};

		FJson FWriter::WriteEffect(const FEffect& Effect) const
		{
			FJson Object = FJson::MakeObject();
			Object.SetString("type", EnumName(Effect.Type));
			if (Effect.Amount != 0)
			{
				Object.SetInt("amount", Effect.Amount);
			}
			SetSelector(Object, "city", Effect.City, "capital", RefCapital, Effect.City >= 0 ? State.Cities[static_cast<size_t>(Effect.City)].Key : std::string());
			SetSelector(Object, "officer", Effect.Officer, "ruler", RefRuler, Effect.Officer >= 0 ? State.Officers[static_cast<size_t>(Effect.Officer)].Key : std::string());
			SetSelector(Object, "faction", Effect.Faction, "player", RefPlayer, Effect.Faction >= 0 ? State.Factions[static_cast<size_t>(Effect.Faction)].Key : std::string());
			SetRef(Object, "sect", State.Sects, Effect.Sect);
			SetRef(Object, "technique", State.Techniques, Effect.Technique);
			if (Effect.Type == EEffectType::Stat)
			{
				Object.SetString("stat", EnumName(Effect.Stat));
			}
			if (!Effect.Text.empty())
			{
				Object.SetString("text", Effect.Text);
			}
			return Object;
		}

		FJson FWriter::WriteChoices(const std::vector<FEventChoice>& Choices) const
		{
			FJson Array = FJson::MakeArray();
			for (const FEventChoice& Choice : Choices)
			{
				FJson Object = FJson::MakeObject();
				Object.SetString("label", Choice.Label);
				if (Choice.RequireGold > 0)
				{
					Object.SetInt("gold", Choice.RequireGold);
				}
				FJson Effects = FJson::MakeArray();
				for (const FEffect& Effect : Choice.Effects)
				{
					Effects.Push(WriteEffect(Effect));
				}
				Object.Set("effects", Effects);
				Array.Push(Object);
			}
			return Array;
		}

		FJson FWriter::Write() const
		{
			FJson Root = FJson::MakeObject();
			Root.SetString("format", "ironreign");
			Root.SetInt("version", 1);
			Root.SetString("key", State.ScenarioKey);
			Root.SetString("name", State.ScenarioName);
			Root.SetString("description", State.ScenarioDescription);
			Root.SetInt("startYear", State.StartYear);

			// Map.
			{
				const FMapDef& Def = State.Map;
				FJson Map = FJson::MakeObject();
				Map.SetInt("width", Def.Width);
				Map.SetInt("height", Def.Height);
				Map.SetString("image", Def.Image);
				FJson Land = FJson::MakeArray();
				for (const std::vector<FPoint>& Polygon : Def.Land)
				{
					Land.Push(WritePoints(Polygon));
				}
				Map.Set("land", Land);
				FJson Lakes = FJson::MakeArray();
				for (const std::vector<FPoint>& Polygon : Def.Lakes)
				{
					Lakes.Push(WritePoints(Polygon));
				}
				Map.Set("lakes", Lakes);
				Map.Set("mountains", WriteStrokes(Def.Mountains));
				Map.Set("hills", WriteStrokes(Def.Hills));
				Map.Set("rivers", WriteStrokes(Def.Rivers));
				Map.Set("forests", WriteCircles(Def.Forests));
				Map.Set("deserts", WriteCircles(Def.Deserts));
				FJson Labels = FJson::MakeArray();
				for (const FMapLabel& Label : Def.Labels)
				{
					FJson Item = FJson::MakeObject();
					Item.SetString("text", Label.Text);
					Item.SetNumber("x", Label.Position.X);
					Item.SetNumber("y", Label.Position.Y);
					Item.SetNumber("size", Label.Size);
					Labels.Push(Item);
				}
				Map.Set("labels", Labels);
				Root.Set("map", Map);
			}

			FJson TechniquesJson = FJson::MakeArray();
			for (const FTechnique& Technique : State.Techniques)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("key", Technique.Key);
				Item.SetString("name", Technique.Name);
				Item.SetString("nameZh", Technique.NameZh);
				Item.SetString("description", Technique.Description);
				Item.SetString("kind", EnumName(Technique.Kind));
				Item.SetInt("power", Technique.Power);
				Item.SetInt("minMartial", Technique.MinMartial);
				TechniquesJson.Push(Item);
			}
			Root.Set("techniques", TechniquesJson);

			FJson FactionsJson = FJson::MakeArray();
			for (const FFaction& Faction : State.Factions)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("key", Faction.Key);
				Item.SetString("name", Faction.Name);
				Item.SetString("nameZh", Faction.NameZh);
				Item.SetString("glyph", Faction.Glyph);
				Item.SetString("color", ColorToHex(Faction.Color));
				SetRef(Item, "ruler", State.Officers, Faction.Ruler);
				SetRef(Item, "capital", State.Cities, Faction.Capital);
				Item.SetBool("alive", Faction.bAlive);
				FactionsJson.Push(Item);
			}
			Root.Set("factions", FactionsJson);

			FJson CitiesJson = FJson::MakeArray();
			for (const FCity& City : State.Cities)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("key", City.Key);
				Item.SetString("name", City.Name);
				Item.SetString("nameZh", City.NameZh);
				Item.SetString("description", City.Description);
				Item.SetNumber("x", City.Position.X);
				Item.SetNumber("y", City.Position.Y);
				Item.SetInt("size", City.Size);
				Item.SetString("terrain", EnumName(City.Terrain));
				SetRef(Item, "owner", State.Factions, City.Owner);
				Item.SetInt("population", City.Population);
				Item.SetInt("populationMax", City.PopulationMax);
				Item.SetInt("farm", City.Farm);
				Item.SetInt("farmMax", City.FarmMax);
				Item.SetInt("commerce", City.Commerce);
				Item.SetInt("commerceMax", City.CommerceMax);
				Item.SetInt("defense", City.Defense);
				Item.SetInt("defenseMax", City.DefenseMax);
				Item.SetInt("order", City.Order);
				Item.SetInt("troops", City.Troops);
				Item.SetInt("training", City.Training);
				Item.SetInt("gold", City.Gold);
				Item.SetInt("food", City.Food);
				if (City.bDelegated)
				{
					Item.SetBool("delegated", true);
				}
				CitiesJson.Push(Item);
			}
			Root.Set("cities", CitiesJson);

			FJson RoadsJson = FJson::MakeArray();
			for (const FRoad& Road : State.Roads)
			{
				FJson Item = FJson::MakeObject();
				SetRef(Item, "a", State.Cities, Road.A);
				SetRef(Item, "b", State.Cities, Road.B);
				Item.SetInt("days", Road.Days);
				Item.SetString("kind", EnumName(Road.Kind));
				if (!Road.Points.empty())
				{
					Item.Set("points", WritePoints(Road.Points));
				}
				RoadsJson.Push(Item);
			}
			Root.Set("roads", RoadsJson);

			FJson OfficersJson = FJson::MakeArray();
			static const char* const StatFields[StatCount] = {"martial", "command", "strategy", "politics", "charm"};
			for (const FOfficer& Officer : State.Officers)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("key", Officer.Key);
				Item.SetString("name", Officer.Name);
				Item.SetString("nameZh", Officer.NameZh);
				Item.SetString("epithet", Officer.Epithet);
				Item.SetString("bio", Officer.Bio);
				if (!Officer.Rumor.empty())
				{
					Item.SetString("rumor", Officer.Rumor);
				}
				Item.SetString("portrait", Officer.Portrait);
				Item.SetString("gender", EnumName(Officer.Gender));
				Item.SetInt("birth", Officer.BirthYear);
				if (Officer.AppearYear != 0)
				{
					Item.SetInt("appear", Officer.AppearYear);
				}
				FJson Exp = FJson::MakeArray();
				for (int Stat = 0; Stat < StatCount; ++Stat)
				{
					Item.SetInt(StatFields[Stat], Officer.Stats[Stat]);
					Exp.PushInt(Officer.StatExp[Stat]);
				}
				Item.Set("exp", Exp);
				Item.SetInt("affinity", Officer.Affinity);
				Item.SetInt("ambition", Officer.Ambition);
				Item.SetInt("bravery", Officer.Bravery);
				Item.SetString("specialty", EnumName(Officer.Specialty));
				Item.SetString("status", EnumName(Officer.Status));
				SetRef(Item, "faction", State.Factions, Officer.Faction);
				SetRef(Item, "captor", State.Factions, Officer.Captor);
				SetRef(Item, "city", State.Cities, Officer.City);
				if (Officer.Army >= 0)
				{
					Item.SetInt("army", Officer.Army);
				}
				Item.SetInt("loyalty", Officer.Loyalty);
				Item.SetInt("merit", Officer.Merit);
				SetRef(Item, "sect", State.Sects, Officer.Sect);
				Item.Set("techniques", RefList(State.Techniques, Officer.Techniques));
				OfficersJson.Push(Item);
			}
			Root.Set("officers", OfficersJson);

			FJson SectsJson = FJson::MakeArray();
			for (const FSect& Sect : State.Sects)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("key", Sect.Key);
				Item.SetString("name", Sect.Name);
				Item.SetString("nameZh", Sect.NameZh);
				Item.SetString("description", Sect.Description);
				SetRef(Item, "city", State.Cities, Sect.City);
				SetRef(Item, "master", State.Officers, Sect.Master);
				Item.Set("techniques", RefList(State.Techniques, Sect.Techniques));
				FJson Favor = FJson::MakeObject();
				for (size_t Faction = 0; Faction < Sect.Favor.size() && Faction < State.Factions.size(); ++Faction)
				{
					Favor.SetInt(State.Factions[Faction].Key, Sect.Favor[Faction]);
				}
				Item.Set("favor", Favor);
				SectsJson.Push(Item);
			}
			Root.Set("sects", SectsJson);

			FJson RelationsJson = FJson::MakeArray();
			for (size_t A = 0; A < State.Factions.size(); ++A)
			{
				for (size_t B = A + 1; B < State.Factions.size(); ++B)
				{
					const FRelation& Relation = State.Relation(static_cast<int>(A), static_cast<int>(B));
					FJson Item = FJson::MakeObject();
					Item.SetString("a", State.Factions[A].Key);
					Item.SetString("b", State.Factions[B].Key);
					Item.SetInt("trust", Relation.Trust);
					Item.SetInt("alliance", Relation.AllianceMonths);
					Item.SetInt("truce", Relation.TruceMonths);
					RelationsJson.Push(Item);
				}
			}
			Root.Set("relations", RelationsJson);

			FJson EventsJson = FJson::MakeArray();
			for (const FEventDef& Event : State.Events)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("key", Event.Key);
				Item.SetString("title", Event.Title);
				Item.SetString("text", Event.Text);
				if (!Event.Image.empty())
				{
					Item.SetString("image", Event.Image);
				}
				if (Event.Speaker >= 0)
				{
					SetRef(Item, "speaker", State.Officers, Event.Speaker);
				}
				else
				{
					Item.SetString("speaker", "advisor");
				}
				Item.SetBool("world", Event.bWorld);
				Item.SetBool("once", Event.bOnce);
				if (Event.TimesFired > 0)
				{
					Item.SetInt("fired", Event.TimesFired);
				}
				switch (Event.Context)
				{
				case EEventContext::RandomPlayerCity: Item.SetString("context", "random_player_city"); break;
				case EEventContext::Capital: Item.SetString("context", "capital"); break;
				case EEventContext::RandomCity: Item.SetString("context", "random_city"); break;
				case EEventContext::FixedCity: SetRef(Item, "context", State.Cities, Event.ContextCity); break;
				}
				FJson When = FJson::MakeObject();
				const FEventCondition& Condition = Event.Condition;
				if (Condition.MinYear != 0)
				{
					When.SetInt("minYear", Condition.MinYear);
				}
				if (Condition.MaxYear != 99999)
				{
					When.SetInt("maxYear", Condition.MaxYear);
				}
				if (!Condition.Months.empty())
				{
					FJson Months = FJson::MakeArray();
					for (const int Month : Condition.Months)
					{
						Months.PushInt(Month);
					}
					When.Set("months", Months);
				}
				When.SetInt("chance", Condition.Chance);
				SetRef(When, "ownsCity", State.Cities, Condition.OwnsCity);
				SetRef(When, "hasOfficer", State.Officers, Condition.HasOfficer);
				SetRef(When, "faction", State.Factions, Condition.Faction);
				if (Condition.MinCities != 0)
				{
					When.SetInt("minCities", Condition.MinCities);
				}
				if (Condition.MaxCities != 9999)
				{
					When.SetInt("maxCities", Condition.MaxCities);
				}
				Item.Set("when", When);
				FJson Effects = FJson::MakeArray();
				for (const FEffect& Effect : Event.Effects)
				{
					Effects.Push(WriteEffect(Effect));
				}
				Item.Set("effects", Effects);
				Item.Set("choices", WriteChoices(Event.Choices));
				EventsJson.Push(Item);
			}
			Root.Set("events", EventsJson);

			// Session.
			FJson Session = FJson::MakeObject();
			Session.SetInt("year", State.Year);
			Session.SetInt("month", State.Month);
			Session.SetInt("day", State.Day);
			Session.SetString("phase", EnumName(State.Phase));
			Session.SetString("outcome", EnumName(State.Outcome));
			Session.SetString("difficulty", EnumName(State.Difficulty));
			SetRef(Session, "player", State.Factions, State.PlayerFaction);
			Session.SetString("rng", ToHex64(State.Rng.GetState()));
			Session.SetInt("nextArmyId", State.NextArmyId);
			Session.SetBool("dayInProgress", State.bDayInProgress);
			Root.Set("session", Session);

			FJson ArmiesJson = FJson::MakeArray();
			for (const FArmy& Army : State.Armies)
			{
				FJson Item = FJson::MakeObject();
				Item.SetInt("id", Army.Id);
				SetRef(Item, "faction", State.Factions, Army.Faction);
				FJson Units = FJson::MakeArray();
				for (const FArmyUnit& Unit : Army.Units)
				{
					FJson UnitJson = FJson::MakeObject();
					SetRef(UnitJson, "officer", State.Officers, Unit.Officer);
					UnitJson.SetInt("troops", Unit.Troops);
					UnitJson.SetString("type", EnumName(Unit.Type));
					Units.Push(UnitJson);
				}
				Item.Set("units", Units);
				Item.SetInt("food", Army.Food);
				Item.SetInt("training", Army.Training);
				Item.SetInt("morale", Army.Morale);
				SetRef(Item, "home", State.Cities, Army.Home);
				SetRef(Item, "target", State.Cities, Army.Target);
				Item.SetString("state", EnumName(Army.State));
				SetRef(Item, "node", State.Cities, Army.Node);
				SetRef(Item, "next", State.Cities, Army.Next);
				Item.SetInt("road", Army.Road);
				Item.SetInt("progress", Army.Progress);
				Item.Set("route", RefList(State.Cities, Army.Route));
				Item.SetBool("new", Army.bNew);
				ArmiesJson.Push(Item);
			}
			Root.Set("armies", ArmiesJson);

			FJson OrdersJson = FJson::MakeArray();
			for (const FOrder& Order : State.Orders)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("type", EnumName(Order.Type));
				SetRef(Item, "officer", State.Officers, Order.Officer);
				SetRef(Item, "city", State.Cities, Order.City);
				SetRef(Item, "targetCity", State.Cities, Order.TargetCity);
				SetRef(Item, "targetOfficer", State.Officers, Order.TargetOfficer);
				SetRef(Item, "targetFaction", State.Factions, Order.TargetFaction);
				SetRef(Item, "targetSect", State.Sects, Order.TargetSect);
				Item.SetInt("amount", Order.Amount);
				Item.SetInt("gold", Order.Gold);
				Item.SetInt("food", Order.Food);
				Item.SetInt("troops", Order.Troops);
				Item.SetInt("cost", Order.Cost);
				OrdersJson.Push(Item);
			}
			Root.Set("orders", OrdersJson);

			FJson PendingJson = FJson::MakeArray();
			for (const FPendingEvent& Pending : State.PendingEvents)
			{
				FJson Item = FJson::MakeObject();
				SetRef(Item, "def", State.Events, Pending.Def);
				Item.SetString("title", Pending.Title);
				Item.SetString("text", Pending.Text);
				Item.SetString("image", Pending.Image);
				SetRef(Item, "speaker", State.Officers, Pending.Speaker);
				SetRef(Item, "city", State.Cities, Pending.City);
				SetRef(Item, "faction", State.Factions, Pending.Faction);
				SetRef(Item, "officer", State.Officers, Pending.Officer);
				Item.Set("choices", WriteChoices(Pending.Choices));
				PendingJson.Push(Item);
			}
			Root.Set("pendingEvents", PendingJson);
			Root.Set("pendingPrisoners", RefList(State.Officers, State.PendingPrisoners));

			FJson BattlesJson = FJson::MakeArray();
			for (const FPendingBattle& Battle : State.BattleQueue)
			{
				FJson Item = FJson::MakeObject();
				Item.SetString("kind", EnumName(Battle.Kind));
				Item.SetInt("attacker", Battle.Attacker);
				Item.SetInt("defender", Battle.Defender);
				SetRef(Item, "city", State.Cities, Battle.City);
				BattlesJson.Push(Item);
			}
			Root.Set("battleQueue", BattlesJson);

			FJson LogJson = FJson::MakeArray();
			for (const FLogEntry& Entry : State.Log)
			{
				FJson Item = FJson::MakeObject();
				Item.SetInt("y", Entry.Year);
				Item.SetInt("m", Entry.Month);
				Item.SetInt("d", Entry.Day);
				SetRef(Item, "f", State.Factions, Entry.Faction);
				if (Entry.bImportant)
				{
					Item.SetBool("i", true);
				}
				Item.SetString("t", Entry.Text);
				LogJson.Push(Item);
			}
			Root.Set("log", LogJson);
			return Root;
		}
	}

	FJson SaveGameState(const FGameState& State)
	{
		StateDetail::FWriter Writer(State);
		return Writer.Write();
	}

	bool ReadScenarioInfo(const FJson& Root, FScenarioInfo& OutInfo)
	{
		FGameState State;
		std::string Error;
		if (!LoadGameState(Root, State, Error))
		{
			return false;
		}
		OutInfo = FScenarioInfo();
		OutInfo.Key = State.ScenarioKey;
		OutInfo.Name = ScenarioNameOf(State);
		OutInfo.Description = ScenarioDescriptionOf(State);
		OutInfo.StartYear = State.StartYear;
		for (size_t Index = 0; Index < State.Factions.size(); ++Index)
		{
			const FFaction& Faction = State.Factions[Index];
			FScenarioInfo::FFactionInfo Info;
			Info.Key = Faction.Key;
			Info.Name = NameOf(Faction);
			Info.NameZh = Faction.NameZh;
			Info.Glyph = Faction.Glyph;
			Info.Color = Faction.Color;
			if (Faction.Ruler >= 0)
			{
				Info.RulerName = NameOf(State.Officers[static_cast<size_t>(Faction.Ruler)]);
				Info.RulerPortrait = State.Officers[static_cast<size_t>(Faction.Ruler)].Portrait;
			}
			Info.Cities = static_cast<int>(State.FactionCities(static_cast<int>(Index)).size());
			Info.Officers = static_cast<int>(State.FactionOfficers(static_cast<int>(Index)).size());
			Info.Troops = State.FactionTotalTroops(static_cast<int>(Index));
			OutInfo.Factions.push_back(Info);
		}
		return true;
	}

	std::string ColorToHex(uint32_t Color)
	{
		char Buffer[16];
		std::snprintf(Buffer, sizeof(Buffer), "#%06X", static_cast<unsigned int>(Color & 0xFFFFFF));
		return Buffer;
	}

	uint32_t ColorFromHex(const std::string& Text, uint32_t Default)
	{
		std::string Digits = Text;
		if (!Digits.empty() && Digits[0] == '#')
		{
			Digits.erase(0, 1);
		}
		if (Digits.size() != 6)
		{
			return Default;
		}
		const uint64_t Value = StateDetail::FromHex64(Digits, 0xFFFFFFFFFFFFFFFFull);
		return Value > 0xFFFFFF ? Default : static_cast<uint32_t>(Value);
	}
}
