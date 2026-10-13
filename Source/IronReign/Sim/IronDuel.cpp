#include "Sim/IronDuel.h"

#include "Sim/IronLocale.h"

#include <algorithm>
#include <cmath>

namespace IronSim
{
	namespace DuelDetail
	{
		/** Damage multiplier of the move that wins an exchange. */
		constexpr double StrikeWin = 1.2;
		constexpr double GuardWin = 0.9;
		constexpr double FeintWin = 1.0;
		/** Strike against Strike: both land a glancing blow. */
		constexpr double ClashFactor = 0.5;

		int MoveIndex(EDuelMove Move)
		{
			return static_cast<int>(Move);
		}

		EDuelMove MoveOf(int Index)
		{
			return static_cast<EDuelMove>(ClampInt(Index, 0, 2));
		}

		/** 1 when A beats B, -1 when B beats A, 0 on the same move. Strike > Feint > Guard > Strike. */
		int CompareMoves(EDuelMove A, EDuelMove B)
		{
			if (A == B)
			{
				return 0;
			}
			const bool bAWins = (A == EDuelMove::Strike && B == EDuelMove::Feint) || (A == EDuelMove::Feint && B == EDuelMove::Guard) || (A == EDuelMove::Guard && B == EDuelMove::Strike);
			return bAWins ? 1 : -1;
		}

		/** The move that beats Move. */
		EDuelMove CounterOf(EDuelMove Move)
		{
			switch (Move)
			{
			case EDuelMove::Strike: return EDuelMove::Guard;
			case EDuelMove::Guard: return EDuelMove::Feint;
			case EDuelMove::Feint: return EDuelMove::Strike;
			}
			return EDuelMove::Strike;
		}

		double WinMultiplier(EDuelMove Move)
		{
			switch (Move)
			{
			case EDuelMove::Strike: return StrikeWin;
			case EDuelMove::Guard: return GuardWin;
			case EDuelMove::Feint: return FeintWin;
			}
			return 1.0;
		}

		int MaxHpFor(int Martial)
		{
			return 80 + ClampInt(Martial, 0, 120) / 2;
		}

		/** Damage of a clean hit before the move multiplier, technique power and randomness. */
		double BaseDamage(int Martial, int OpponentMartial)
		{
			const double Value = (20.0 + Martial / 4.0) * (1.0 + (Martial - OpponentMartial) / 200.0);
			return std::max(4.0, Value);
		}
	}

	void FDuel::Setup(const FDuelist& SideA, const FDuelist& SideB, const std::vector<FTechnique>& InTechniques, uint64_t Seed, int InMaxRounds)
	{
		Duelists[0] = SideA;
		Duelists[1] = SideB;
		Techniques = InTechniques;
		History.clear();
		Rng = FRng(Seed ^ 0xD0E1D0E1C0FFEE11ull);
		Rng.Next();
		RoundLimit = std::max(1, InMaxRounds);
		for (FDuelist& Duelist : Duelists)
		{
			Duelist.MaxHp = DuelDetail::MaxHpFor(Duelist.Martial);
			Duelist.Hp = Duelist.MaxHp;
			std::vector<int> Valid;
			for (const int Index : Duelist.Techniques)
			{
				if (Index >= 0 && Index < static_cast<int>(Techniques.size()) && std::find(Valid.begin(), Valid.end(), Index) == Valid.end())
				{
					Valid.push_back(Index);
				}
			}
			Duelist.Techniques = Valid;
			Duelist.TechniqueUsed.assign(Valid.size(), false);
		}
	}

	bool FDuel::IsOver() const
	{
		return Duelists[0].Hp <= 0 || Duelists[1].Hp <= 0 || Round() >= RoundLimit;
	}

	int FDuel::Winner() const
	{
		if (Duelists[1].Hp <= 0 && Duelists[0].Hp > 0)
		{
			return 0;
		}
		if (Duelists[0].Hp <= 0 && Duelists[1].Hp > 0)
		{
			return 1;
		}
		return -1;
	}

	const FTechnique* FDuel::TechniqueInfo(int TechniqueIndex) const
	{
		if (TechniqueIndex < 0 || TechniqueIndex >= static_cast<int>(Techniques.size()))
		{
			return nullptr;
		}
		return &Techniques[static_cast<size_t>(TechniqueIndex)];
	}

	bool FDuel::CanUseTechnique(int SideIndex, int TechniqueSlot) const
	{
		const FDuelist& Duelist = Side(SideIndex);
		if (TechniqueSlot < 0 || TechniqueSlot >= static_cast<int>(Duelist.Techniques.size()))
		{
			return false;
		}
		if (TechniqueSlot < static_cast<int>(Duelist.TechniqueUsed.size()) && Duelist.TechniqueUsed[static_cast<size_t>(TechniqueSlot)])
		{
			return false;
		}
		return TechniqueInfo(Duelist.Techniques[static_cast<size_t>(TechniqueSlot)]) != nullptr;
	}

	void FDuel::ChooseAI(int SideIndex, EDuelMove& OutMove, int& OutTechniqueSlot)
	{
		const int Me = SideIndex == 0 ? 0 : 1;
		const int Them = 1 - Me;
		const FDuelist& Self = Duelists[Me];
		const FDuelist& Opponent = Duelists[Them];

		// Read the opponent: move frequencies (recent rounds weigh more) plus a habit of countering our last move.
		double Predicted[3] = {1.0, 1.0, 1.0};
		const int Played = static_cast<int>(History.size());
		for (int Index = 0; Index < Played; ++Index)
		{
			const double Weight = 1.0 + 0.5 * Index;
			Predicted[DuelDetail::MoveIndex(History[static_cast<size_t>(Index)].Moves[Them])] += Weight;
		}
		if (Played > 0)
		{
			const EDuelMove MyLast = History.back().Moves[Me];
			Predicted[DuelDetail::MoveIndex(DuelDetail::CounterOf(MyLast))] += 0.4 * (1.0 + 0.5 * (Played - 1));
		}
		const double PredictedTotal = Predicted[0] + Predicted[1] + Predicted[2];
		for (double& Value : Predicted)
		{
			Value /= PredictedTotal;
		}

		// Expected HP swing of each move, as fractions of the remaining HP (finishing blows matter more).
		const double MyHit = DuelDetail::BaseDamage(Self.Martial, Opponent.Martial);
		const double TheirHit = DuelDetail::BaseDamage(Opponent.Martial, Self.Martial);
		const double TheirHp = std::max(1, Opponent.Hp);
		const double MyHp = std::max(1, Self.Hp);
		double Expected[3] = {0.0, 0.0, 0.0};
		for (int Mine = 0; Mine < 3; ++Mine)
		{
			for (int Theirs = 0; Theirs < 3; ++Theirs)
			{
				const EDuelMove MyMove = DuelDetail::MoveOf(Mine);
				const EDuelMove TheirMove = DuelDetail::MoveOf(Theirs);
				const int Result = DuelDetail::CompareMoves(MyMove, TheirMove);
				double Swing = 0.0;
				if (Result > 0)
				{
					Swing = std::min(1.0, MyHit * DuelDetail::WinMultiplier(MyMove) / TheirHp);
				}
				else if (Result < 0)
				{
					Swing = -std::min(1.0, TheirHit * DuelDetail::WinMultiplier(TheirMove) / MyHp);
				}
				else if (MyMove == EDuelMove::Strike)
				{
					Swing = std::min(1.0, MyHit * DuelDetail::ClashFactor / TheirHp) - std::min(1.0, TheirHit * DuelDetail::ClashFactor / MyHp);
				}
				Expected[Mine] += Predicted[Theirs] * Swing;
			}
		}

		// Mixed strategy: soft preference for the best expected move, blended with a uniform share so the AI
		// cannot be read perfectly.
		double Weights[3];
		double WeightTotal = 0.0;
		for (int Index = 0; Index < 3; ++Index)
		{
			Weights[Index] = std::exp(3.0 * Expected[Index]);
			WeightTotal += Weights[Index];
		}
		const double Roll = Rng.Unit();
		double Accumulated = 0.0;
		int Choice = 2;
		for (int Index = 0; Index < 3; ++Index)
		{
			Accumulated += 0.75 * Weights[Index] / WeightTotal + 0.25 / 3.0;
			if (Roll < Accumulated)
			{
				Choice = Index;
				break;
			}
		}
		OutMove = DuelDetail::MoveOf(Choice);

		// Techniques: strongest unused one matching the move, saved for finishing blows, emergencies, the final
		// rounds, or used now and then.
		OutTechniqueSlot = -1;
		int BestPower = 0;
		for (int Slot = 0; Slot < static_cast<int>(Self.Techniques.size()); ++Slot)
		{
			if (!CanUseTechnique(Me, Slot))
			{
				continue;
			}
			const FTechnique* Info = TechniqueInfo(Self.Techniques[static_cast<size_t>(Slot)]);
			if (Info && Info->Kind == OutMove && Info->Power > BestPower)
			{
				BestPower = Info->Power;
				OutTechniqueSlot = Slot;
			}
		}
		if (OutTechniqueSlot >= 0)
		{
			const bool bFinisher = MyHit * DuelDetail::WinMultiplier(OutMove) * BestPower / 100.0 >= Opponent.Hp;
			const bool bDesperate = Self.Hp * 100 < Self.MaxHp * 45;
			const bool bLate = Round() >= RoundLimit - 3;
			if (!(bFinisher || bDesperate || bLate || Rng.Chance(30)))
			{
				OutTechniqueSlot = -1;
			}
		}
	}

	const FDuelRound& FDuel::PlayRound(EDuelMove MoveA, int TechniqueSlotA, EDuelMove MoveB, int TechniqueSlotB)
	{
		static const FDuelRound NoRound;
		if (IsOver())
		{
			return History.empty() ? NoRound : History.back();
		}

		FDuelRound ThisRound;
		EDuelMove Moves[2] = {MoveA, MoveB};
		const int Slots[2] = {TechniqueSlotA, TechniqueSlotB};
		int Power[2] = {100, 100};
		bool bTechnique[2] = {false, false};
		std::string TechniqueNames[2];
		for (int Index = 0; Index < 2; ++Index)
		{
			ThisRound.Techniques[Index] = -1;
			if (CanUseTechnique(Index, Slots[Index]))
			{
				FDuelist& Duelist = Duelists[Index];
				const int TechniqueIndex = Duelist.Techniques[static_cast<size_t>(Slots[Index])];
				const FTechnique& Info = Techniques[static_cast<size_t>(TechniqueIndex)];
				// A technique is performed with its own move.
				Moves[Index] = Info.Kind;
				Power[Index] = std::max(50, Info.Power);
				bTechnique[Index] = true;
				TechniqueNames[Index] = NameOf(Info);
				Duelist.TechniqueUsed[static_cast<size_t>(Slots[Index])] = true;
				ThisRound.Techniques[Index] = TechniqueIndex;
			}
			ThisRound.Moves[Index] = Moves[Index];
		}

		int Result = DuelDetail::CompareMoves(Moves[0], Moves[1]);
		bool bTechniqueTie = false;
		if (Result == 0 && (bTechnique[0] || bTechnique[1]))
		{
			// Techniques win ties against the same move; the stronger technique wins if both used one.
			const int Edge0 = bTechnique[0] ? Power[0] : 0;
			const int Edge1 = bTechnique[1] ? Power[1] : 0;
			if (Edge0 != Edge1)
			{
				Result = Edge0 > Edge1 ? 1 : -1;
				bTechniqueTie = true;
			}
		}

		double Dealt[2] = {0.0, 0.0};
		if (Result != 0)
		{
			const int WinnerSide = Result > 0 ? 0 : 1;
			Dealt[WinnerSide] = DuelDetail::BaseDamage(Duelists[WinnerSide].Martial, Duelists[1 - WinnerSide].Martial) * DuelDetail::WinMultiplier(Moves[WinnerSide]) * Power[WinnerSide] / 100.0 * Rng.Uniform(0.9, 1.1);
		}
		else if (Moves[0] == EDuelMove::Strike)
		{
			for (int Index = 0; Index < 2; ++Index)
			{
				Dealt[Index] = DuelDetail::BaseDamage(Duelists[Index].Martial, Duelists[1 - Index].Martial) * DuelDetail::ClashFactor * Power[Index] / 100.0 * Rng.Uniform(0.9, 1.1);
			}
		}

		// Damage[i] is taken by side i.
		ThisRound.Damage[0] = static_cast<int>(std::lround(Dealt[1]));
		ThisRound.Damage[1] = static_cast<int>(std::lround(Dealt[0]));
		if (Result != 0)
		{
			const int LoserSide = Result > 0 ? 1 : 0;
			ThisRound.Damage[LoserSide] = std::max(1, ThisRound.Damage[LoserSide]);
		}
		int NewHp[2] = {Duelists[0].Hp - ThisRound.Damage[0], Duelists[1].Hp - ThisRound.Damage[1]};
		if (NewHp[0] <= 0 && NewHp[1] <= 0)
		{
			// Both would fall in a clash: the one left with more vitality keeps standing.
			if (NewHp[0] > NewHp[1])
			{
				NewHp[0] = 1;
			}
			else if (NewHp[1] > NewHp[0])
			{
				NewHp[1] = 1;
			}
			else
			{
				NewHp[0] = 1;
				NewHp[1] = 1;
			}
		}
		Duelists[0].Hp = std::max(0, NewHp[0]);
		Duelists[1].Hp = std::max(0, NewHp[1]);

		// Narration.
		std::string Text;
		for (int Index = 0; Index < 2; ++Index)
		{
			if (bTechnique[Index])
			{
				Text += LocF("duel.round.technique", "{name} unleashes {technique}!", {{"name", Duelists[Index].Name}, {"technique", TechniqueNames[Index]}});
				Text += ' ';
			}
		}
		if (Result != 0)
		{
			const int WinnerSide = Result > 0 ? 0 : 1;
			const int LoserSide = 1 - WinnerSide;
			const std::string& WinnerName = Duelists[WinnerSide].Name;
			const std::string& LoserName = Duelists[LoserSide].Name;
			const std::string Damage = ToText(ThisRound.Damage[LoserSide]);
			if (bTechniqueTie)
			{
				Text += LocF("duel.round.techniqueTie", "{winner} overpowers {loser}'s {move} and deals {damage}.", {{"winner", WinnerName}, {"loser", LoserName}, {"move", DisplayName(Moves[LoserSide])}, {"damage", Damage}});
			}
			else if (Moves[WinnerSide] == EDuelMove::Strike)
			{
				Text += LocF("duel.round.strikeBeatsFeint", "{winner} sees through {loser}'s feint and strikes for {damage}.", {{"winner", WinnerName}, {"loser", LoserName}, {"damage", Damage}});
			}
			else if (Moves[WinnerSide] == EDuelMove::Guard)
			{
				Text += LocF("duel.round.guardBeatsStrike", "{winner} parries {loser}'s strike and counters for {damage}.", {{"winner", WinnerName}, {"loser", LoserName}, {"damage", Damage}});
			}
			else
			{
				Text += LocF("duel.round.feintBeatsGuard", "{winner} feints past {loser}'s guard and cuts for {damage}.", {{"winner", WinnerName}, {"loser", LoserName}, {"damage", Damage}});
			}
		}
		else if (Moves[0] == EDuelMove::Strike)
		{
			Text += LocF("duel.round.clash", "{a} and {b} trade blows: {a} takes {damageA}, {b} takes {damageB}.", {{"a", Duelists[0].Name}, {"b", Duelists[1].Name}, {"damageA", ToText(ThisRound.Damage[0])}, {"damageB", ToText(ThisRound.Damage[1])}});
		}
		else if (Moves[0] == EDuelMove::Guard)
		{
			Text += LocF("duel.round.guardGuard", "{a} and {b} circle each other warily.", {{"a", Duelists[0].Name}, {"b", Duelists[1].Name}});
		}
		else
		{
			Text += LocF("duel.round.feintFeint", "{a} and {b} both feint and find only air.", {{"a", Duelists[0].Name}, {"b", Duelists[1].Name}});
		}
		for (int Index = 0; Index < 2; ++Index)
		{
			if (Duelists[Index].Hp <= 0)
			{
				Text += ' ';
				Text += LocF("duel.round.fallen", "{name} can fight no more!", {{"name", Duelists[Index].Name}});
			}
		}
		ThisRound.Text = Text;
		History.push_back(ThisRound);
		return History.back();
	}

	const FDuelRound& FDuel::PlayVersusAI(int PlayerSide, EDuelMove Move, int TechniqueSlot)
	{
		const int AISide = PlayerSide == 0 ? 1 : 0;
		EDuelMove AIMove = EDuelMove::Strike;
		int AISlot = -1;
		if (!IsOver())
		{
			// The AI commits before seeing the player's move; it only reads the history.
			ChooseAI(AISide, AIMove, AISlot);
		}
		if (AISide == 1)
		{
			return PlayRound(Move, TechniqueSlot, AIMove, AISlot);
		}
		return PlayRound(AIMove, AISlot, Move, TechniqueSlot);
	}

	void FDuel::AutoPlay()
	{
		int Guard = 0;
		while (!IsOver() && Guard < 1000)
		{
			EDuelMove MoveA = EDuelMove::Strike;
			EDuelMove MoveB = EDuelMove::Strike;
			int SlotA = -1;
			int SlotB = -1;
			ChooseAI(0, MoveA, SlotA);
			ChooseAI(1, MoveB, SlotB);
			PlayRound(MoveA, SlotA, MoveB, SlotB);
			++Guard;
		}
	}
}
