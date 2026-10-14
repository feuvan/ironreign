#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Sim/IronBattle.h"
#include "World/IronBattleBoard3D.h"
#include "World/IronWorldMath.h"

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronBattleBoardMathTest, "IronReign.World.BattleBoard", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronBattleBoardMathTest::RunTest(const FString& Parameters)
{
	// Board-local metres agree with the rules engine's hex pixels (radius 4 m), shifted so hex (0,0) is the origin.
	for (int32 Col = 0; Col < 18; ++Col)
	{
		for (int32 Row = 0; Row < 12; ++Row)
		{
			const IronSim::FHex Hex = {Col, Row};
			const FVector2D LocalM = AIronBattleBoard3D::HexToLocalM(Hex);
			float PixelX = 0.0f;
			float PixelY = 0.0f;
			IronSim::HexMath::ToPixel(Hex, static_cast<float>(IronWorld::HexRadiusM), PixelX, PixelY);
			const double ShiftX = IronWorld::HexRadiusM;
			const double ShiftY = IronWorld::HexRadiusM * 0.8660254037844386;
			if (!FMath::IsNearlyEqual(LocalM.X, static_cast<double>(PixelX) - ShiftX, 0.01) || !FMath::IsNearlyEqual(LocalM.Y, static_cast<double>(PixelY) - ShiftY, 0.01))
			{
				AddError(FString::Printf(TEXT("Hex (%d,%d) centre (%.3f, %.3f) disagrees with HexMath::ToPixel"), Col, Row, LocalM.X, LocalM.Y));
			}

			// Points inside the hex's inscribed circle (3.46 m) map back to it.
			const FVector2D Offsets[] = {FVector2D(0.0, 0.0), FVector2D(3.0, 0.0), FVector2D(-2.2, 2.2), FVector2D(1.5, -3.0)};
			for (const FVector2D& Offset : Offsets)
			{
				IronSim::FHex Found;
				const bool bOnBoard = AIronBattleBoard3D::LocalMToHex(LocalM + Offset, 18, 12, Found);
				if (!bOnBoard || Found != Hex)
				{
					AddError(FString::Printf(TEXT("LocalMToHex near hex (%d,%d) returned (%d,%d) on board=%d"), Col, Row, Found.Col, Found.Row, bOnBoard ? 1 : 0));
				}
			}
		}
	}

	IronSim::FHex Outside;
	TestFalse(TEXT("Points left of the board are off the board"), AIronBattleBoard3D::LocalMToHex(FVector2D(-9.0, 10.0), 16, 11, Outside));
	TestFalse(TEXT("Points below the last row are off the board"), AIronBattleBoard3D::LocalMToHex(FVector2D(30.0, 11.0 * IronWorld::HexRowSpacingM + 2.0), 16, 11, Outside));
	TestTrue(TEXT("The board origin sits at the DESIGN.md 12.4 location"), FMath::IsNearlyEqual(IronWorld::HexToWorld(0, 0, 0.0).Y, -10000000.0, 0.01));
	return true;
}

#endif
