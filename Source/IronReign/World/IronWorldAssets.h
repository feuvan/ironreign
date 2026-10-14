#pragma once

#include "CoreMinimal.h"
#include "Logging/LogMacros.h"

class UIronAssetManifest;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UMaterialParameterCollection;
class UObject;
class UStaticMesh;
class UStaticMeshComponent;

namespace IronSim
{
	class FJson;
	struct FGameState;
}

/** Log category of the 3D world presentation (Source/IronReign/World). */
DECLARE_LOG_CATEGORY_EXTERN(LogIronWorld, Log, All);

/**
 * Soft asset access for the 3D presentation. Every asset is looked up by path at runtime and may be missing (the
 * import into /Game/IronReign has not run, or a cooked build left it out); callers must handle nullptr.
 *
 * Paths (docs/DESIGN.md 12.3 / 12.5):
 *   /Game/IronReign/Models/SM_<Name>        imported models (City_1..3, Sect, Banner, Flag, Tree_*, Unit_*, Hex_*)
 *   /Game/IronReign/Materials/<Name>        M_IronTerrain / MI_IronTerrain, M_IronWater / MI_IronWater, M_IronTint,
 *                                           M_IronHighlight, M_IronInk, MI_IronClouds, MPC_IronSeason
 *   (all created by Content/Python/ironreign_import.py)
 *   Content/Data/Art3D/                     runtime JSON + heightmap (read with FFileHelper)
 */
namespace IronWorld
{
	/** Runtime model parameters from Content/Data/Art3D/Models.json: {"frontYaw": 90, "models": {"City_2": {"scale": 1.0}}}. */
	struct FModelParams
	{
		/** Yaw (degrees) that turns an imported model's front towards UE +Y. */
		double FrontYawDegrees = 90.0;
		/** Uniform scale per model name ("City_2", "Unit_Cavalry"...); 1 when absent. */
		TMap<FString, double> Scales;

		double ScaleOf(const FString& ModelName) const
		{
			const double* Found = Scales.Find(ModelName);
			return Found != nullptr ? *Found : 1.0;
		}
	};

	/** Material parameter names shared with the import script. */
	inline const TCHAR* const TintParameter = TEXT("Tint");
	inline const TCHAR* const ColorParameter = TEXT("Color");

	/** Engine content used as fallbacks (present in editor builds; cooked only when referenced). */
	inline const TCHAR* const EngineBasicShapeMaterialPath = TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial");
	inline const TCHAR* const EnginePlanePath = TEXT("/Engine/BasicShapes/Plane.Plane");
	inline const TCHAR* const EngineCubePath = TEXT("/Engine/BasicShapes/Cube.Cube");
	inline const TCHAR* const EngineCloudMaterialPath = TEXT("/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst.m_SimpleVolumetricCloud_Inst");

	/** Content/Data/Art3D (relative like FIronSession::DataDir so it also resolves inside .pak files). */
	FString Art3DDir();
	/** "/Game/IronReign/Models/SM_City_2.SM_City_2" for "City_2". */
	FString ModelObjectPath(const FString& ModelName);
	/** "/Game/IronReign/Materials/M_IronTint.M_IronTint" for "M_IronTint". */
	FString MaterialObjectPath(const FString& MaterialName);

	/** Game thread. Quiet when the asset does not exist. */
	UStaticMesh* LoadModel(const FString& ModelName);
	UMaterialInterface* LoadMaterial(const FString& MaterialName);
	UStaticMesh* LoadEngineMesh(const TCHAR* ObjectPath);
	UMaterialInterface* LoadEngineMaterial(const TCHAR* ObjectPath);
	/** MPC_IronSeason (scalars Snow / Autumn / Wetness read by every imported model material). */
	UMaterialParameterCollection* LoadSeasonCollection();
	/** 1 m plane with 0..1 UVs: SM_IronPlane (cooked with the game), else the engine's basic plane. */
	UStaticMesh* LoadPlaneMesh();
	/**
	 * 1 m cube: SM_IronCube (cooked with the game), else the engine's basic cube. A closed static mesh with a distance
	 * field and Lumen cards, for large flat surfaces that must be part of the Lumen scene (scaled into thick slabs).
	 */
	UStaticMesh* LoadCubeMesh();
	/** /Game/IronReign/IronReignAssetVersion (UIronAssetManifest), written last by the import; nullptr without it. */
	UIronAssetManifest* LoadAssetManifest();

	/** Reads a UTF-8 JSON file (BOM tolerated) with the rules engine's parser. Thread-safe. */
	bool ReadJsonFile(const FString& Path, IronSim::FJson& OutJson, FString& OutError);

	/** Models.json, loaded once (defaults when missing). Game thread. */
	const FModelParams& GetModelParams();

	/** Faction colour (linear) from the game state, or the independent grey for -1 / unknown factions. */
	FLinearColor FactionColor(const IronSim::FGameState& State, int32 FactionIndex);

	/**
	 * Gives every "Tint" material slot (slot name starting with "Tint", or a material derived from M_IronTint) a
	 * dynamic instance with the vector parameter Tint = Color. Each instance derives from the slot's own material (the
	 * importer's M_IronTint instance carrying that slot's base texture), or from TintBase when the slot is empty; slots
	 * sharing a material share one instance. Returns the first instance (nullptr when the mesh has no Tint slot): pass
	 * it back as Existing to just update the colour of every Tint slot.
	 */
	UMaterialInstanceDynamic* ApplyTint(UStaticMeshComponent* Component, const FLinearColor& Color, UMaterialInstanceDynamic* Existing, UMaterialInterface* TintBase);

	/** Dynamic instance of Base with the vector parameter "Color" (BasicShapeMaterial, M_IronHighlight). */
	UMaterialInstanceDynamic* MakeColoredMaterial(UMaterialInterface* Base, UObject* Outer, const FLinearColor& Color);

	/**
	 * Remembered answer of an AreAssetsAvailable probe (AIronWorldMap3D, AIronBattleBoard3D). A positive answer is kept
	 * until Invalidate(); a negative one is probed again once RetrySeconds have passed, so an asset import finishing
	 * while the game runs is picked up without probing (loading) the assets every frame. Game thread only.
	 */
	struct FAssetCheckCache
	{
		static constexpr double RetrySeconds = 30.0;

		/** The remembered answer may be used at NowSeconds (FPlatformTime::Seconds). */
		bool IsFresh(double NowSeconds) const
		{
			return bChecked && (bAvailable || NowSeconds - CheckedAtSeconds < RetrySeconds);
		}

		/** Remembers a probe (Missing empty = available). True when the outcome differs from the last one reported. */
		bool Store(const FString& Missing, double NowSeconds)
		{
			bChecked = true;
			bAvailable = Missing.IsEmpty();
			CheckedAtSeconds = NowSeconds;
			if (Missing == ReportedMissing)
			{
				return false;
			}
			ReportedMissing = Missing;
			return true;
		}

		void Invalidate()
		{
			bChecked = false;
		}

		bool bChecked = false;
		bool bAvailable = false;
		double CheckedAtSeconds = 0.0;
		/** What the last reported probe missed (empty: nothing, or nothing reported yet). */
		FString ReportedMissing;
	};
}
