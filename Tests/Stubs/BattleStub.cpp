// Temporary stand-in used by Tests/CMakeLists.txt only while Sim/IronBattle.cpp does not exist yet.
#include "Sim/IronBattle.h"

namespace IronSim
{
	FBattleResult ResolveBattleAuto(const FBattleSetup& Setup)
	{
		FBattleResult Result;
		int Troops[2] = {0, 0};
		for (int Side = 0; Side < 2; ++Side)
		{
			for (const FBattleUnitSetup& Unit : Setup.Sides[Side].Units)
			{
				Troops[Side] += Unit.Troops;
			}
		}
		Result.bFinished = true;
		Result.Days = 5;
		Result.Winner = Troops[0] > Troops[1] * 3 / 2 ? 0 : 1;
		for (int Side = 0; Side < 2; ++Side)
		{
			for (const FBattleUnitSetup& Unit : Setup.Sides[Side].Units)
			{
				FUnitOutcome Outcome;
				Outcome.Side = Side;
				Outcome.Officer = Unit.Officer;
				Outcome.Troops = Unit.Troops * (Side == Result.Winner ? 80 : 40) / 100;
				Outcome.Status = Side == Result.Winner ? EUnitStatus::Active : EUnitStatus::Routed;
				Result.Units.push_back(Outcome);
			}
		}
		return Result;
	}
}
