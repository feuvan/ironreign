#include "IronTest.h"

#include "Sim/IronDuel.h"

#include <string>
#include <vector>

using IronSim::EDuelMove;
using IronSim::FDuel;
using IronSim::FDuelist;
using IronSim::FDuelRound;
using IronSim::FTechnique;

namespace DuelTestUtil
{
	FDuelist MakeDuelist(const char* Name, int Martial, const std::vector<int>& Techniques = std::vector<int>())
	{
		FDuelist Duelist;
		Duelist.Name = Name;
		Duelist.Martial = Martial;
		Duelist.Techniques = Techniques;
		return Duelist;
	}

	/** [0] Strike x2.0, [1] Guard x1.6, [2] Feint x1.5. */
	std::vector<FTechnique> Techniques()
	{
		std::vector<FTechnique> Table(3);
		Table[0].Key = "dragon_fang";
		Table[0].Name = "Dragon Fang";
		Table[0].Kind = EDuelMove::Strike;
		Table[0].Power = 200;
		Table[1].Key = "iron_wall";
		Table[1].Name = "Iron Wall";
		Table[1].Kind = EDuelMove::Guard;
		Table[1].Power = 160;
		Table[2].Key = "shadow_step";
		Table[2].Name = "Shadow Step";
		Table[2].Kind = EDuelMove::Feint;
		Table[2].Power = 150;
		return Table;
	}

	FDuel MakeDuel(int MartialA, int MartialB, uint64_t Seed, int MaxRounds = 10, const std::vector<int>& TechniquesA = std::vector<int>())
	{
		FDuel Duel;
		Duel.Setup(MakeDuelist("Alpha", MartialA, TechniquesA), MakeDuelist("Beta", MartialB), Techniques(), Seed, MaxRounds);
		return Duel;
	}
}

IRON_TEST(DuelHpComesFromMartial)
{
	const FDuel Duel = DuelTestUtil::MakeDuel(90, 60, 1);
	IRON_EXPECT(Duel.Side(0).MaxHp > Duel.Side(1).MaxHp);
	IRON_EXPECT_EQ(Duel.Side(0).Hp, Duel.Side(0).MaxHp);
	IRON_EXPECT_EQ(Duel.Side(1).Hp, Duel.Side(1).MaxHp);
	IRON_EXPECT_EQ(Duel.Round(), 0);
	IRON_EXPECT(!Duel.IsOver());
	IRON_EXPECT_EQ(Duel.MaxRounds(), 10);
}

IRON_TEST(DuelMovesFollowStrikeGuardFeint)
{
	struct FCase
	{
		EDuelMove A;
		EDuelMove B;
		bool bAHurt;
		bool bBHurt;
	};
	const FCase Cases[] = {
		{EDuelMove::Strike, EDuelMove::Feint, false, true},
		{EDuelMove::Feint, EDuelMove::Guard, false, true},
		{EDuelMove::Guard, EDuelMove::Strike, false, true},
		{EDuelMove::Feint, EDuelMove::Strike, true, false},
		{EDuelMove::Guard, EDuelMove::Feint, true, false},
		{EDuelMove::Strike, EDuelMove::Guard, true, false},
		{EDuelMove::Strike, EDuelMove::Strike, true, true},
		{EDuelMove::Guard, EDuelMove::Guard, false, false},
		{EDuelMove::Feint, EDuelMove::Feint, false, false},
	};
	for (const FCase& Case : Cases)
	{
		FDuel Duel = DuelTestUtil::MakeDuel(70, 70, 7);
		const FDuelRound& Round = Duel.PlayRound(Case.A, -1, Case.B, -1);
		IRON_EXPECT((Round.Damage[0] > 0) == Case.bAHurt);
		IRON_EXPECT((Round.Damage[1] > 0) == Case.bBHurt);
		IRON_EXPECT_EQ(Duel.Side(0).Hp, Duel.Side(0).MaxHp - Round.Damage[0]);
		IRON_EXPECT_EQ(Duel.Side(1).Hp, Duel.Side(1).MaxHp - Round.Damage[1]);
		IRON_EXPECT(!Round.Text.empty());
		IRON_EXPECT_EQ(Duel.Round(), 1);
	}
}

IRON_TEST(DuelTechniquesAreOneUseMultipliersThatWinTies)
{
	FDuel Duel = DuelTestUtil::MakeDuel(70, 70, 3, 10, {0, 1});
	IRON_EXPECT(Duel.CanUseTechnique(0, 0));
	IRON_EXPECT(Duel.CanUseTechnique(0, 1));
	IRON_EXPECT(!Duel.CanUseTechnique(0, 2));
	IRON_EXPECT(!Duel.CanUseTechnique(1, 0));
	IRON_EXPECT(Duel.TechniqueInfo(0) != nullptr && Duel.TechniqueInfo(0)->Power == 200);
	IRON_EXPECT(Duel.TechniqueInfo(5) == nullptr);

	// A Strike technique wins a Strike-vs-Strike tie outright.
	const FDuelRound First = Duel.PlayRound(EDuelMove::Strike, 0, EDuelMove::Strike, -1);
	IRON_EXPECT_EQ(First.Techniques[0], 0);
	IRON_EXPECT_EQ(First.Techniques[1], -1);
	IRON_EXPECT_EQ(First.Damage[0], 0);
	IRON_EXPECT(First.Damage[1] > 0);
	IRON_EXPECT(!Duel.CanUseTechnique(0, 0));

	// Used up: the slot is ignored and the tie is an ordinary clash.
	const FDuelRound Second = Duel.PlayRound(EDuelMove::Strike, 0, EDuelMove::Strike, -1);
	IRON_EXPECT_EQ(Second.Techniques[0], -1);
	IRON_EXPECT(Second.Damage[0] > 0 && Second.Damage[1] > 0);

	// A technique is performed with its own move whatever move was passed.
	const FDuelRound Third = Duel.PlayRound(EDuelMove::Strike, 1, EDuelMove::Feint, -1);
	IRON_EXPECT(Third.Moves[0] == EDuelMove::Guard);
	IRON_EXPECT(Third.Damage[0] > 0);

	// Power multiplies damage: compare the same winning exchange with and without the x2.0 technique.
	FDuel Plain = DuelTestUtil::MakeDuel(70, 70, 11, 10, {0});
	const int PlainDamage = Plain.PlayRound(EDuelMove::Strike, -1, EDuelMove::Feint, -1).Damage[1];
	FDuel Empowered = DuelTestUtil::MakeDuel(70, 70, 11, 10, {0});
	const int EmpoweredDamage = Empowered.PlayRound(EDuelMove::Strike, 0, EDuelMove::Feint, -1).Damage[1];
	IRON_EXPECT_MSG(EmpoweredDamage * 10 > PlainDamage * 15, std::to_string(EmpoweredDamage) + " vs " + std::to_string(PlainDamage));
}

IRON_TEST(DuelEndsInDrawAtRoundLimit)
{
	FDuel Duel = DuelTestUtil::MakeDuel(70, 70, 5, 4);
	for (int Round = 0; Round < 4; ++Round)
	{
		IRON_EXPECT(!Duel.IsOver());
		Duel.PlayRound(EDuelMove::Guard, -1, EDuelMove::Guard, -1);
	}
	IRON_EXPECT(Duel.IsOver());
	IRON_EXPECT_EQ(Duel.Winner(), -1);
	IRON_EXPECT_EQ(Duel.Round(), 4);
	Duel.PlayRound(EDuelMove::Strike, -1, EDuelMove::Feint, -1);
	IRON_EXPECT_EQ(Duel.Round(), 4);
	IRON_EXPECT_EQ(Duel.Side(1).Hp, Duel.Side(1).MaxHp);
}

IRON_TEST(DuelKnockoutDecidesTheWinner)
{
	FDuel Duel = DuelTestUtil::MakeDuel(90, 30, 9, 20);
	int Guard = 0;
	while (!Duel.IsOver() && Guard < 20)
	{
		Duel.PlayRound(EDuelMove::Strike, -1, EDuelMove::Feint, -1);
		++Guard;
	}
	IRON_EXPECT(Duel.IsOver());
	IRON_EXPECT_EQ(Duel.Winner(), 0);
	IRON_EXPECT_EQ(Duel.Side(1).Hp, 0);
	IRON_EXPECT(Duel.Side(0).Hp == Duel.Side(0).MaxHp);
	IRON_EXPECT(Duel.Round() < 20);
}

IRON_TEST(DuelStrongerOfficerWinsMostButNotAll)
{
	int Wins[2] = {0, 0};
	int Draws = 0;
	const int Count = 400;
	for (int Seed = 0; Seed < Count; ++Seed)
	{
		FDuel Duel = DuelTestUtil::MakeDuel(90, 60, static_cast<uint64_t>(Seed) * 7919 + 1);
		Duel.AutoPlay();
		IRON_EXPECT(Duel.IsOver());
		const int Winner = Duel.Winner();
		if (Winner < 0)
		{
			++Draws;
		}
		else
		{
			++Wins[Winner];
		}
	}
	const std::string Summary = std::to_string(Wins[0]) + "/" + std::to_string(Wins[1]) + "/" + std::to_string(Draws);
	IRON_EXPECT_MSG(Wins[0] >= Count * 60 / 100, Summary);
	IRON_EXPECT_MSG(Wins[0] <= Count * 97 / 100, Summary);
	IRON_EXPECT_MSG(Wins[1] >= 4, Summary);
}

IRON_TEST(DuelEqualOfficersAreEven)
{
	int Wins[2] = {0, 0};
	for (int Seed = 0; Seed < 400; ++Seed)
	{
		FDuel Duel = DuelTestUtil::MakeDuel(70, 70, static_cast<uint64_t>(Seed) * 104729 + 3);
		Duel.AutoPlay();
		if (Duel.Winner() >= 0)
		{
			++Wins[Duel.Winner()];
		}
	}
	const int Decided = Wins[0] + Wins[1];
	IRON_EXPECT(Decided > 200);
	IRON_EXPECT_MSG(Wins[0] * 100 >= Decided * 38 && Wins[0] * 100 <= Decided * 62, std::to_string(Wins[0]) + " of " + std::to_string(Decided));
}

IRON_TEST(DuelIsDeterministic)
{
	FDuel First = DuelTestUtil::MakeDuel(80, 75, 42, 10, {0, 2});
	FDuel Second = DuelTestUtil::MakeDuel(80, 75, 42, 10, {0, 2});
	First.AutoPlay();
	Second.AutoPlay();
	IRON_EXPECT_EQ(First.Round(), Second.Round());
	IRON_EXPECT_EQ(First.Winner(), Second.Winner());
	for (int Index = 0; Index < First.Round() && Index < Second.Round(); ++Index)
	{
		const FDuelRound& A = First.Rounds()[static_cast<size_t>(Index)];
		const FDuelRound& B = Second.Rounds()[static_cast<size_t>(Index)];
		IRON_EXPECT(A.Moves[0] == B.Moves[0] && A.Moves[1] == B.Moves[1]);
		IRON_EXPECT(A.Damage[0] == B.Damage[0] && A.Damage[1] == B.Damage[1]);
		IRON_EXPECT(A.Text == B.Text);
	}
}

IRON_TEST(DuelAIReadsTheOpponentsHabits)
{
	// Against an opponent who always strikes, the AI should learn to guard.
	int Guards = 0;
	int Choices = 0;
	for (int Seed = 0; Seed < 200; ++Seed)
	{
		FDuel Duel = DuelTestUtil::MakeDuel(70, 70, static_cast<uint64_t>(Seed) + 100, 10);
		for (int Round = 0; Round < 6 && !Duel.IsOver(); ++Round)
		{
			EDuelMove Move = EDuelMove::Strike;
			int Slot = -1;
			Duel.ChooseAI(0, Move, Slot);
			if (Round >= 2)
			{
				++Choices;
				Guards += Move == EDuelMove::Guard ? 1 : 0;
			}
			Duel.PlayRound(Move, Slot, EDuelMove::Strike, -1);
		}
	}
	IRON_EXPECT(Choices > 0);
	IRON_EXPECT_MSG(Guards * 100 > Choices * 45, std::to_string(Guards) + " of " + std::to_string(Choices));
}

IRON_TEST(DuelPlayVersusAIKeepsThePlayersMove)
{
	FDuel Duel = DuelTestUtil::MakeDuel(70, 70, 77);
	const FDuelRound& AsSideOne = Duel.PlayVersusAI(1, EDuelMove::Feint, -1);
	IRON_EXPECT(AsSideOne.Moves[1] == EDuelMove::Feint);
	const FDuelRound& AsSideZero = Duel.PlayVersusAI(0, EDuelMove::Guard, -1);
	IRON_EXPECT(AsSideZero.Moves[0] == EDuelMove::Guard);
	IRON_EXPECT_EQ(Duel.Round(), 2);
	IRON_EXPECT_EQ(static_cast<int>(Duel.Rounds().size()), 2);
}
