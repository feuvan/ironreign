#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "IronAssetManifest.generated.h"

/**
 * Version marker of the editor-imported 3D assets (docs/DESIGN.md section 12).
 *
 * Content/Python/ironreign_import.py writes it last, at /Game/IronReign/IronReignAssetVersion
 * (object path "/Game/IronReign/IronReignAssetVersion.IronReignAssetVersion"), and deletes it when a rebuild starts:
 * when it loads, the import of that ArtSource version completed. The editor compares ArtVersion/PipelineVersion
 * with ArtSource/manifest.json to decide whether to re-import. Runtime code may load it (LoadObject, null-checked)
 * to tell "3D assets present" from "fall back to 2D" without probing every asset.
 */
UCLASS(BlueprintType)
class IRONREIGN_API UIronAssetManifest : public UDataAsset
{
	GENERATED_BODY()

public:
	/** "version" of ArtSource/manifest.json the assets were built from. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	int32 ArtVersion = 0;

	/** PIPELINE_VERSION of ironreign_import.py that built them. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	int32 PipelineVersion = 0;

	/** UTC build time (ISO 8601). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	FString BuiltAtUtc;

	/** Engine version of the editor that ran the import. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	FString EngineVersion;

	/** Imported model names: each one exists as /Game/IronReign/Models/SM_<Name> (e.g. "City_2", "Hex_Ford"). */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	TArray<FString> Models;

	/**
	 * FIronHeightField::SourceHash ("<crc32 hex>-<byte count>") of the Content/Data/Art3D/Terrain/Height.png the import
	 * saw (empty without one). The editor re-imports when the file changes; the game uses the terrain chunks only when
	 * the Height.png it loads has this hash.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	FString TerrainHeightHash;

	/**
	 * Heightmap pixel stride of the static terrain chunks /Game/IronReign/Models/SM_Terrain_<cx>_<cy> (8 x 5, cut from
	 * that Height.png like AIronTerrain's runtime mesh); 0 = they were not built.
	 */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Iron Reign")
	int32 TerrainMeshStride = 0;

	bool HasModel(const FString& ModelName) const
	{
		return Models.Contains(ModelName);
	}
};
