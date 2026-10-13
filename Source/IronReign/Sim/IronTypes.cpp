#include "Sim/IronTypes.h"

#include "Sim/IronLocale.h"

namespace IronSim
{
	namespace TypeNames
	{
		template <typename EnumType, int N>
		const char* NameOf(EnumType Value, const char* const (&Names)[N])
		{
			const int Index = static_cast<int>(Value);
			return (Index >= 0 && Index < N) ? Names[Index] : "unknown";
		}

		template <typename EnumType, int N>
		bool ParseOf(const std::string& Text, EnumType& Out, const char* const (&Names)[N])
		{
			for (int Index = 0; Index < N; ++Index)
			{
				if (Text == Names[Index])
				{
					Out = static_cast<EnumType>(Index);
					return true;
				}
			}
			return false;
		}

		const char* const Stats[] = {"martial", "command", "strategy", "politics", "charm"};
		const char* const TroopTypes[] = {"infantry", "cavalry", "archer"};
		const char* const Genders[] = {"m", "f"};
		const char* const OfficerStatuses[] = {"serving", "free", "hidden", "prisoner", "dead", "unborn"};
		const char* const Terrains[] = {"plains", "forest", "hills", "river", "mountains", "coast"};
		const char* const RoadKinds[] = {"road", "pass", "river"};
		const char* const Phases[] = {"planning", "execution", "gameover"};
		const char* const Outcomes[] = {"none", "victory", "defeat"};
		const char* const Difficulties[] = {"easy", "normal", "hard"};
		const char* const OrderTypes[] = {"farm", "commerce", "walls", "patrol", "draft", "train", "search", "recruit", "move", "transport", "sectTraining", "alliance", "truce", "gift"};
		const char* const DuelMoves[] = {"strike", "guard", "feint"};
		const char* const ArmyStates[] = {"marching", "returning"};
		const char* const BattleKinds[] = {"field", "siege"};
		const char* const PrisonerDecisions[] = {"recruit", "release", "execute", "imprison"};
		const char* const EffectTypes[] = {"gold", "food", "troops", "order", "farm", "commerce", "defense", "population", "training", "loyalty", "loyaltyAll", "stat", "joinOfficer", "revealOfficer", "trust", "alliance", "truce", "sectFavor", "learnTechnique", "message"};

	}

	const char* EnumName(EStat Value) { return TypeNames::NameOf(Value, TypeNames::Stats); }
	const char* EnumName(ETroopType Value) { return TypeNames::NameOf(Value, TypeNames::TroopTypes); }
	const char* EnumName(EGender Value) { return TypeNames::NameOf(Value, TypeNames::Genders); }
	const char* EnumName(EOfficerStatus Value) { return TypeNames::NameOf(Value, TypeNames::OfficerStatuses); }
	const char* EnumName(ETerrain Value) { return TypeNames::NameOf(Value, TypeNames::Terrains); }
	const char* EnumName(ERoadKind Value) { return TypeNames::NameOf(Value, TypeNames::RoadKinds); }
	const char* EnumName(EPhase Value) { return TypeNames::NameOf(Value, TypeNames::Phases); }
	const char* EnumName(EOutcome Value) { return TypeNames::NameOf(Value, TypeNames::Outcomes); }
	const char* EnumName(EDifficulty Value) { return TypeNames::NameOf(Value, TypeNames::Difficulties); }
	const char* EnumName(EOrderType Value) { return TypeNames::NameOf(Value, TypeNames::OrderTypes); }
	const char* EnumName(EDuelMove Value) { return TypeNames::NameOf(Value, TypeNames::DuelMoves); }
	const char* EnumName(EArmyState Value) { return TypeNames::NameOf(Value, TypeNames::ArmyStates); }
	const char* EnumName(EBattleKind Value) { return TypeNames::NameOf(Value, TypeNames::BattleKinds); }
	const char* EnumName(EPrisonerDecision Value) { return TypeNames::NameOf(Value, TypeNames::PrisonerDecisions); }
	const char* EnumName(EEffectType Value) { return TypeNames::NameOf(Value, TypeNames::EffectTypes); }

	bool EnumParse(const std::string& Text, EStat& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::Stats); }
	bool EnumParse(const std::string& Text, ETroopType& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::TroopTypes); }
	bool EnumParse(const std::string& Text, EGender& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::Genders); }
	bool EnumParse(const std::string& Text, EOfficerStatus& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::OfficerStatuses); }
	bool EnumParse(const std::string& Text, ETerrain& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::Terrains); }
	bool EnumParse(const std::string& Text, ERoadKind& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::RoadKinds); }
	bool EnumParse(const std::string& Text, EPhase& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::Phases); }
	bool EnumParse(const std::string& Text, EOutcome& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::Outcomes); }
	bool EnumParse(const std::string& Text, EDifficulty& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::Difficulties); }
	bool EnumParse(const std::string& Text, EOrderType& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::OrderTypes); }
	bool EnumParse(const std::string& Text, EDuelMove& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::DuelMoves); }
	bool EnumParse(const std::string& Text, EArmyState& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::ArmyStates); }
	bool EnumParse(const std::string& Text, EBattleKind& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::BattleKinds); }
	bool EnumParse(const std::string& Text, EPrisonerDecision& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::PrisonerDecisions); }
	bool EnumParse(const std::string& Text, EEffectType& Out) { return TypeNames::ParseOf(Text, Out, TypeNames::EffectTypes); }

	std::string DisplayName(EStat Value)
	{
		switch (Value)
		{
		case EStat::Martial: return Loc("stat.martial", "Martial");
		case EStat::Command: return Loc("stat.command", "Command");
		case EStat::Strategy: return Loc("stat.strategy", "Strategy");
		case EStat::Politics: return Loc("stat.politics", "Politics");
		case EStat::Charm: return Loc("stat.charm", "Charm");
		}
		return std::string();
	}

	std::string ShortName(EStat Value)
	{
		switch (Value)
		{
		case EStat::Martial: return Loc("stat.martial.short", "MAR");
		case EStat::Command: return Loc("stat.command.short", "CMD");
		case EStat::Strategy: return Loc("stat.strategy.short", "STR");
		case EStat::Politics: return Loc("stat.politics.short", "POL");
		case EStat::Charm: return Loc("stat.charm.short", "CHA");
		}
		return std::string();
	}

	std::string DisplayName(ETroopType Value)
	{
		switch (Value)
		{
		case ETroopType::Infantry: return Loc("troop.infantry", "Infantry");
		case ETroopType::Cavalry: return Loc("troop.cavalry", "Cavalry");
		case ETroopType::Archer: return Loc("troop.archer", "Archers");
		}
		return std::string();
	}

	std::string DisplayName(EOrderType Value)
	{
		switch (Value)
		{
		case EOrderType::Farm: return Loc("order.farm", "Develop Farmland");
		case EOrderType::Commerce: return Loc("order.commerce", "Develop Commerce");
		case EOrderType::Walls: return Loc("order.walls", "Repair Walls");
		case EOrderType::Patrol: return Loc("order.patrol", "Patrol");
		case EOrderType::Draft: return Loc("order.draft", "Draft Troops");
		case EOrderType::Train: return Loc("order.train", "Train Troops");
		case EOrderType::Search: return Loc("order.search", "Search");
		case EOrderType::Recruit: return Loc("order.recruit", "Recruit");
		case EOrderType::Move: return Loc("order.move", "Move");
		case EOrderType::Transport: return Loc("order.transport", "Transport");
		case EOrderType::SectTraining: return Loc("order.sectTraining", "Sect Training");
		case EOrderType::Alliance: return Loc("order.alliance", "Propose Alliance");
		case EOrderType::Truce: return Loc("order.truce", "Propose Truce");
		case EOrderType::Gift: return Loc("order.gift", "Send Gift");
		case EOrderType::Count: break;
		}
		return std::string();
	}

	std::string DisplayName(ETerrain Value)
	{
		switch (Value)
		{
		case ETerrain::Plains: return Loc("terrain.plains", "Plains");
		case ETerrain::Forest: return Loc("terrain.forest", "Forest");
		case ETerrain::Hills: return Loc("terrain.hills", "Hills");
		case ETerrain::River: return Loc("terrain.river", "River");
		case ETerrain::Mountains: return Loc("terrain.mountains", "Mountains");
		case ETerrain::Coast: return Loc("terrain.coast", "Coast");
		}
		return std::string();
	}

	std::string DisplayName(EDuelMove Value)
	{
		switch (Value)
		{
		case EDuelMove::Strike: return Loc("duel.strike", "Strike");
		case EDuelMove::Guard: return Loc("duel.guard", "Guard");
		case EDuelMove::Feint: return Loc("duel.feint", "Feint");
		}
		return std::string();
	}

	std::string DisplayName(EDifficulty Value)
	{
		switch (Value)
		{
		case EDifficulty::Easy: return Loc("difficulty.easy", "Easy");
		case EDifficulty::Normal: return Loc("difficulty.normal", "Normal");
		case EDifficulty::Hard: return Loc("difficulty.hard", "Hard");
		}
		return std::string();
	}

	std::string SeasonName(int Month)
	{
		switch ((ClampInt(Month, 1, 12) - 1) / 3)
		{
		case 0: return Loc("season.spring", "Spring");
		case 1: return Loc("season.summer", "Summer");
		case 2: return Loc("season.autumn", "Autumn");
		default: return Loc("season.winter", "Winter");
		}
	}
}
