#pragma once

#include "Sim/IronRandom.h"
#include "Sim/IronState.h"
#include "Sim/IronTypes.h"

#include <string>
#include <vector>

namespace IronSim
{
	/** One combatant in a one-on-one duel. */
	struct FDuelist
	{
		int Officer = -1;
		std::string Name;
		std::string Portrait;
		int Martial = 50;
		int Bravery = 50;
		int Hp = 100;
		int MaxHp = 100;
		/** Indices into the technique table passed to FDuel::Setup. */
		std::vector<int> Techniques;
		/** Parallel to Techniques: each technique can be used once per duel. */
		std::vector<bool> TechniqueUsed;
		bool bPlayer = false;
	};

	struct FDuelRound
	{
		EDuelMove Moves[2] = {EDuelMove::Strike, EDuelMove::Strike};
		/** Technique index (into the technique table) used by each side, or -1. */
		int Techniques[2] = {-1, -1};
		/** Damage taken by each side this round. */
		int Damage[2] = {0, 0};
		std::string Text;
	};

	/**
	 * Wuxia duel minigame. Each round both sides pick Strike, Guard or Feint
	 * (Strike beats Feint, Feint beats Guard, Guard beats Strike), optionally empowered by a technique
	 * that multiplies damage and wins ties against the same move. Damage scales with Martial.
	 */
	class FDuel
	{
	public:
		void Setup(const FDuelist& SideA, const FDuelist& SideB, const std::vector<FTechnique>& InTechniques, uint64_t Seed, int InMaxRounds = 10);

		const FDuelist& Side(int Index) const { return Duelists[Index == 0 ? 0 : 1]; }
		int Round() const { return static_cast<int>(History.size()); }
		int MaxRounds() const { return RoundLimit; }
		bool IsOver() const;
		/** -1 = draw (round limit reached), otherwise the winning side. Valid when IsOver(). */
		int Winner() const;
		const std::vector<FDuelRound>& Rounds() const { return History; }

		const FTechnique* TechniqueInfo(int TechniqueIndex) const;
		/** TechniqueSlot indexes FDuelist::Techniques. */
		bool CanUseTechnique(int SideIndex, int TechniqueSlot) const;

		/** AI decision for a side. OutTechniqueSlot is -1 or an index into that side's Techniques. */
		void ChooseAI(int SideIndex, EDuelMove& OutMove, int& OutTechniqueSlot);
		/** Resolves one round. Technique slots index each side's Techniques (-1 = none). */
		const FDuelRound& PlayRound(EDuelMove MoveA, int TechniqueSlotA, EDuelMove MoveB, int TechniqueSlotB);
		/** Player picks for PlayerSide, the AI picks for the other side. */
		const FDuelRound& PlayVersusAI(int PlayerSide, EDuelMove Move, int TechniqueSlot);
		/** Plays AI against AI until the duel ends. */
		void AutoPlay();

	private:
		FDuelist Duelists[2];
		std::vector<FTechnique> Techniques;
		std::vector<FDuelRound> History;
		FRng Rng;
		int RoundLimit = 10;
	};
}
