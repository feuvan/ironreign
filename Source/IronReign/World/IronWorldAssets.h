#pragma once

#include "CoreMinimal.h"
#include "Logging/LogMacros.h"

class UMaterialInstanceDynamic;
class UMaterialInterface;
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
 *   /Game/IronReign/Materials/<Name>        M_IronTerrain / MI_IronTerrain, M_IronWater, M_IronTint, M_IronHighlight,
 *                                           M_IronInk, MI_IronClouds
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
	inline const TCHAR* const EngineCylinderPath = TEXT("/Engine/BasicShapes/Cylinder.Cylinder");
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

	/** Reads a UTF-8 JSON file (BOM tolerated) with the rules engine's parser. Thread-safe. */
	bool ReadJsonFile(const FString& Path, IronSim::FJson& OutJson, FString& OutError);

	/** Models.json, loaded once (defaults when missing). Game thread. */
	const FModelParams& GetModelParams();

	/** Faction colour (linear) from the game state, or the independent grey for -1 / unknown factions. */
	FLinearColor FactionColor(const IronSim::FGameState& State, int32 FactionIndex);

	/**
	 * Gives every material slot whose name starts with "Tint" a dynamic instance with the vector parameter Tint = Color.
	 * The instance derives from TintBase (M_IronTint) when given, else from the slot's own material. Pass the instance
	 * returned by an earlier call as Existing to just update the colour. Returns nullptr when the mesh has no Tint slot.
	 */
	UMaterialInstanceDynamic* ApplyTint(UStaticMeshComponent* Component, const FLinearColor& Color, UMaterialInstanceDynamic* Existing, UMaterialInterface* TintBase);

	/** Dynamic instance of Base with the vector parameter "Color" (BasicShapeMaterial, M_IronHighlight). */
	UMaterialInstanceDynamic* MakeColoredMaterial(UMaterialInterface* Base, UObject* Outer, const FLinearColor& Color);
}
