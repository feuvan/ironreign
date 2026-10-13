#pragma once

#include "CoreMinimal.h"
#include "Sim/IronState.h"

/**
 * World-space conventions of the real-time 3D presentation (docs/DESIGN.md sections 12.2 and 12.4).
 *
 * Map units are metres. Unreal units are centimetres: UE X = map x * 100, UE Y = map y * 100, UE Z = height * 100.
 * The map rectangle spans X 0..240000, Y 0..150000 (cm). Map north (y = 0) is -Y; the default camera looks north from
 * the south, so screen-right is +X.
 *
 * Header-only and free of UObject dependencies so the strategy map, the battle board and the UI can share it.
 */
namespace IronWorld
{
	inline constexpr double CmPerMetre = 100.0;
	inline constexpr double MetresPerCm = 0.01;

	/** Default map rectangle in metres (Terrain.json / the scenario map block override it). */
	inline constexpr double DefaultMapWidthM = 2400.0;
	inline constexpr double DefaultMapHeightM = 1500.0;

	/** UE yaw (degrees) of a camera or model looking map-north (-Y). */
	inline constexpr double NorthYawDegrees = -90.0;
	/** UE yaw (degrees) of something facing the default camera (map-south, +Y). */
	inline constexpr double SouthYawDegrees = 90.0;

	// ----- Strategy camera (AIronCameraRig) -----
	inline constexpr double CameraMinDistanceM = 250.0;
	inline constexpr double CameraMaxDistanceM = 2600.0;
	/** Pitch below the horizon at the closest zoom; it steepens to CameraMaxPitchDegrees when zoomed out. */
	inline constexpr double CameraMinPitchDegrees = 45.0;
	inline constexpr double CameraMaxPitchDegrees = 70.0;
	inline constexpr double CameraMaxYawOffsetDegrees = 45.0;
	/** Horizontal field of view: narrow enough for the "diorama" look, wide enough to see most of the map zoomed out. */
	inline constexpr float CameraFieldOfViewDegrees = 40.0f;

	// ----- Battle board (section 12.4) -----
	/** The board sits far from the world map, origin X = 0 m, Y = -100000 m. */
	inline constexpr double BoardOriginXM = 0.0;
	inline constexpr double BoardOriginYM = -100000.0;
	/** Flat-top odd-q hexes: centre = (col * 6, (row + 0.5 * (col & 1)) * 6.928) metres, corner radius 4 m. */
	inline constexpr double HexColumnSpacingM = 6.0;
	inline constexpr double HexRowSpacingM = 6.928;
	inline constexpr double HexRadiusM = 4.0;

	/** Faction colour of independent cities (DESIGN.md section 8). */
	inline constexpr uint32 IndependentRGB = 0x8C8577;

	/** Map point (metres) plus a height (metres) to a UE world location (cm). */
	inline FVector MapToWorld(const FVector2D& MapPointM, double HeightM = 0.0)
	{
		return FVector(MapPointM.X * CmPerMetre, MapPointM.Y * CmPerMetre, HeightM * CmPerMetre);
	}

	/** UE world location (cm) to a map point (metres); Z is dropped. */
	inline FVector2D WorldToMap(const FVector& WorldCm)
	{
		return FVector2D(WorldCm.X * MetresPerCm, WorldCm.Y * MetresPerCm);
	}

	inline double WorldToHeightM(const FVector& WorldCm)
	{
		return WorldCm.Z * MetresPerCm;
	}

	/** Rules-engine map point (map units are metres) to a map point. */
	inline FVector2D FromSim(const IronSim::FPoint& Point)
	{
		return FVector2D(static_cast<double>(Point.X), static_cast<double>(Point.Y));
	}

	/** World location (cm) of the battle board origin (hex 0,0 centre at height 0). */
	inline FVector BoardOrigin()
	{
		return MapToWorld(FVector2D(BoardOriginXM, BoardOriginYM), 0.0);
	}

	/** Hex centre relative to the board origin, in metres. */
	inline FVector2D HexToBoardLocalM(int32 Col, int32 Row)
	{
		const double OddShift = (Col & 1) != 0 ? 0.5 : 0.0;
		return FVector2D(static_cast<double>(Col) * HexColumnSpacingM, (static_cast<double>(Row) + OddShift) * HexRowSpacingM);
	}

	/** World location (cm) of a hex centre on the battle board at HeightM above the board plane. */
	inline FVector HexToWorld(int32 Col, int32 Row, double HeightM = 0.0)
	{
		return BoardOrigin() + MapToWorld(HexToBoardLocalM(Col, Row), HeightM);
	}

	/**
	 * Nearest hex centre to a world location (cm) on the battle board. Returns true when the point lies within the
	 * hex's corner radius (always fills OutCol/OutRow, even off the board; callers check the board size).
	 */
	inline bool WorldToHex(const FVector& WorldCm, int32& OutCol, int32& OutRow)
	{
		const FVector2D LocalM = WorldToMap(WorldCm) - FVector2D(BoardOriginXM, BoardOriginYM);
		const int32 ColGuess = FMath::RoundToInt32(LocalM.X / HexColumnSpacingM);
		double BestDistSq = TNumericLimits<double>::Max();
		OutCol = ColGuess;
		OutRow = 0;
		for (int32 ColStep = -1; ColStep <= 1; ++ColStep)
		{
			const int32 Col = ColGuess + ColStep;
			const double OddShift = (Col & 1) != 0 ? 0.5 : 0.0;
			const int32 RowGuess = FMath::RoundToInt32(LocalM.Y / HexRowSpacingM - OddShift);
			for (int32 RowStep = -1; RowStep <= 1; ++RowStep)
			{
				const int32 Row = RowGuess + RowStep;
				const double DistSq = FVector2D::DistSquared(LocalM, HexToBoardLocalM(Col, Row));
				if (DistSq < BestDistSq)
				{
					BestDistSq = DistSq;
					OutCol = Col;
					OutRow = Row;
				}
			}
		}
		return BestDistSq <= HexRadiusM * HexRadiusM;
	}

	/** UE yaw (degrees) of a horizontal direction given in map/world axes. */
	inline double DirectionToYawDegrees(const FVector2D& Direction)
	{
		return FMath::RadiansToDegrees(FMath::Atan2(Direction.Y, Direction.X));
	}

	/**
	 * Yaw to give an imported model so its front faces FacingYawDegrees. FrontYawDegrees comes from Models.json
	 * ("frontYaw"): the yaw that turns the model's front towards UE +Y (yaw 90).
	 */
	inline double ModelYawDegrees(double FrontYawDegrees, double FacingYawDegrees)
	{
		return FrontYawDegrees + FacingYawDegrees - SouthYawDegrees;
	}

	/** 0xRRGGBB (sRGB) to a linear colour for material parameters. */
	inline FLinearColor ColorFromRGB(uint32 RGB, float Alpha = 1.0f)
	{
		FLinearColor Color(FColor(static_cast<uint8>((RGB >> 16) & 0xFF), static_cast<uint8>((RGB >> 8) & 0xFF), static_cast<uint8>(RGB & 0xFF)));
		Color.A = Alpha;
		return Color;
	}

	/**
	 * Critically damped spring step (smooth-damp): moves Current toward Target, reaching it in roughly SmoothTime
	 * seconds without overshoot. Velocity is the spring state, kept by the caller.
	 */
	inline double SmoothDamp(double Current, double Target, double& Velocity, double SmoothTime, double DeltaTime)
	{
		const double Omega = 2.0 / FMath::Max(0.0001, SmoothTime);
		const double Step = Omega * DeltaTime;
		const double Decay = 1.0 / (1.0 + Step + 0.48 * Step * Step + 0.235 * Step * Step * Step);
		const double Offset = Current - Target;
		const double Impulse = (Velocity + Omega * Offset) * DeltaTime;
		Velocity = (Velocity - Omega * Impulse) * Decay;
		return Target + (Offset + Impulse) * Decay;
	}

	/** Smooth 0..1 ease (smootherstep). */
	inline double EaseInOut(double Alpha)
	{
		const double T = FMath::Clamp(Alpha, 0.0, 1.0);
		return T * T * T * (T * (T * 6.0 - 15.0) + 10.0);
	}
}
