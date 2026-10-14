#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"
#include "GameFramework/Actor.h"
#include "IronTerrain.generated.h"

class IImageWrapper;
class UHierarchicalInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UProceduralMeshComponent;
class USceneComponent;
class UStaticMesh;
class UStaticMeshComponent;
struct FIronTerrainBuildResult;

/** Content/Data/Art3D/Terrain/Terrain.json (docs/DESIGN.md 12.2). Extents in metres. */
struct FIronTerrainInfo
{
	double MapWidthM = 2400.0;
	double MapHeightM = 1500.0;
	/** Map metres between two heightmap pixels. */
	double GridStepM = 2.0;
	double MinElevationM = -40.0;
	double MaxElevationM = 180.0;
	double SeaLevelM = 0.0;
};

/**
 * The decoded heightmap plus the vertex grid of the rendered mesh. Sample() interpolates on the same triangles the
 * mesh draws (two per cell, diagonal from the top-right to the bottom-left corner), so objects placed with it sit
 * exactly on the visible ground. Plain data: safe to build on a worker thread.
 */
struct IRONREIGN_API FIronHeightField
{
	FIronTerrainInfo Info;
	int32 SamplesX = 0;
	int32 SamplesY = 0;
	/** Elevation in metres per heightmap pixel, row-major (SamplesX per row); pixel (i, j) = map (i, j) * GridStepM. */
	TArray<float> Heights;
	/** Heightmap columns/rows that carry mesh vertices: every Stride-th pixel plus the last one. */
	TArray<int32> MeshColumns;
	TArray<int32> MeshRows;
	int32 Stride = 1;
	/**
	 * Identity of the decoded Height.png: "<crc32 hex>-<byte count>" (standard CRC-32, as Python's zlib.crc32). The
	 * asset import records the same value for the SM_Terrain_* chunks it cut from the heightmap.
	 */
	FString SourceHash;

	bool IsValid() const;
	float At(int32 PixelX, int32 PixelY) const { return Heights[PixelY * SamplesX + PixelX]; }
	/** Chooses the mesh vertex grid (Stride 1 = every heightmap pixel). */
	void BuildMeshGrid(int32 InStride);
	/** Elevation (m) of the rendered terrain at a map point (metres); clamps to the map edge. */
	float Sample(double XM, double YM) const;
	/** Rendered surface = max(terrain, sea level). */
	float SampleSurface(double XM, double YM) const;
	/**
	 * Ray against the rendered surface (terrain or sea). Origin in world cm, any non-zero direction.
	 * Marches one mesh cell at a time between the top and bottom of the height range, then bisects.
	 */
	bool Trace(const FVector& OriginCm, const FVector& Direction, FVector& OutHitCm, double MaxDistanceCm = 1.0e7) const;

	/**
	 * Reads Terrain.json and decodes Height.png (16-bit greyscale; 8-bit tolerated) from Content/Data/Art3D/Terrain.
	 * PngWrapper must be a PNG IImageWrapper created on the game thread; the call itself is thread-safe.
	 */
	static bool Load(const TSharedPtr<IImageWrapper>& PngWrapper, FIronHeightField& OutField, FString& OutError);
	/** Creates the PNG decoder (game thread). */
	static TSharedPtr<IImageWrapper> CreatePngWrapper();
	/**
	 * SourceHash of a file's bytes: "<crc32 hex>-<byte count>" with the standard (zlib) CRC-32. Must equal
	 * source_hash() in Content/Python/ironreign_terrain.py. Thread-safe.
	 */
	static FString HashSourceBytes(const TArray<uint8>& Bytes);
};

/**
 * The strategy map terrain, built at runtime from Content/Data/Art3D/Terrain (DESIGN.md 12.2):
 *  - the heightmap as a grid of 8 x 5 chunks with a dynamic instance of MI_IronTerrain / M_IronTerrain (fallback:
 *    tinted BasicShapeMaterial). Preferably the static meshes SM_Terrain_<cx>_<cy> the asset import cut from the same
 *    Height.png (Nanite, mesh distance fields and Lumen cards: the ground is part of the Lumen scene, so it bounces
 *    light, occludes the sky in valleys and shows in the sea's reflections). They are used only when all 40 load and
 *    the import recorded this Height.png's SourceHash; otherwise procedural mesh chunks are built at runtime (shared
 *    edges, smooth normals from the heightfield, tangents along +X, UV0 = (x / width, y / height), UV1 = map metres /
 *    50), which software Lumen only sees through screen traces. Both are the exact triangles FIronHeightField samples,
 *  - the sea: a flat grid at seaLevel reaching 8 km beyond the map (M_IronWater; UV0 = metres / 100, UV1 = map UV)
 *    over a dark sea floor,
 *  - trees from Trees.json as one hierarchical instanced mesh per type (SM_Tree_Pine / Broad / Bamboo).
 *
 * Loading, decoding and the vertex math run on a thread-pool worker; the game thread only turns the finished
 * sections into components, a few per frame, so the build never hitches for long.
 */
UCLASS(NotBlueprintable)
class IRONREIGN_API AIronTerrain : public AActor
{
	GENERATED_BODY()

public:
	AIronTerrain();

	/** Terrain.json and Height.png exist under Content/Data/Art3D/Terrain. */
	static bool AreDataFilesPresent();

	/**
	 * Starts the asynchronous build. MeshStride is the vertex spacing of the runtime (procedural) mesh: 1 = full 2 m
	 * grid (Epic), 2 = 4 m grid (default); the imported static chunks keep the grid they were cut with. Call once.
	 */
	void BeginBuild(int32 MeshStride = 2);

	/**
	 * Tree-free discs, X / Y = map metres, Z = radius in metres (city footprints, army camps): Trees.json entries inside
	 * them are skipped. Call before BeginBuild (the worker filters them); a later call clears them like ClearTrees.
	 */
	void SetTreeExclusions(const TArray<FVector>& InDiscsM);
	/** Removes trees inside the discs (same layout) at any time: planted ones now, pending ones when they are planted. */
	void ClearTrees(const TArray<FVector>& DiscsM);

	/** SampleHeight / TraceSurface are valid (the heightmap was decoded). */
	bool IsHeightReady() const { return bHeightReady; }
	/** Every terrain chunk, the sea and the trees exist. */
	bool IsBuildComplete() const { return bBuildComplete; }
	/** Loading failed (missing or corrupt data); the 3D map cannot be shown. */
	bool HasFailed() const { return bFailed; }
	/** The ground is drawn by the imported SM_Terrain_* static meshes (valid once the heightmap is ready). */
	bool UsesStaticChunks() const { return bStaticChunks; }

	/** Rendered terrain elevation (m) at a map point (m); sea level before the heightmap is ready. */
	float SampleHeight(const FVector2D& MapPointM) const;
	/** max(SampleHeight, sea level): where things stand. */
	float SampleSurface(const FVector2D& MapPointM) const;
	/** Ray (world cm) against terrain and sea; false when it misses or before the heightmap is ready. */
	bool TraceSurface(const FVector& OriginCm, const FVector& Direction, FVector& OutHitCm) const;

	const FIronTerrainInfo& GetInfo() const { return HeightField.Info; }
	FVector2D GetMapSizeM() const { return FVector2D(HeightField.Info.MapWidthM, HeightField.Info.MapHeightM); }
	float GetSeaLevelM() const { return static_cast<float>(HeightField.Info.SeaLevelM); }
	const FIronHeightField& GetHeightField() const { return HeightField; }

	/** The terrain material instance (season scalars Snow / Autumn / Wetness); created by BeginBuild. */
	UMaterialInstanceDynamic* GetTerrainMaterial() const;

	/** Broadcast once when SampleHeight becomes valid. */
	FSimpleMulticastDelegate OnHeightReady;
	/** Broadcast once when every component exists. */
	FSimpleMulticastDelegate OnBuildComplete;

	virtual void Tick(float DeltaSeconds) override;

private:
	void CreateTerrainMaterial();
	/** Loads every SM_Terrain_<cx>_<cy> into StaticChunkMeshes (all or none) and reads the import's source hash. */
	bool LoadStaticChunks(FString& OutSourceHash, int32& OutStride);
	void HandleBuildResult(const TSharedPtr<FIronTerrainBuildResult>& Result);
	void CreatePendingComponents();
	void CreateSea();
	void CreateTrees(int32 TreeType);
	UProceduralMeshComponent* NewMeshComponent();
	UStaticMeshComponent* NewStaticChunk(UStaticMesh* ChunkMesh);

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UProceduralMeshComponent>> Chunks;

	/** The imported chunk meshes, row-major (8 x 5); emptied when the runtime mesh is used instead. */
	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMesh>> StaticChunkMeshes;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> StaticChunks;

	UPROPERTY(Transient)
	TObjectPtr<UProceduralMeshComponent> SeaMesh;

	UPROPERTY(Transient)
	TObjectPtr<UProceduralMeshComponent> SeaFloorMesh;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UHierarchicalInstancedStaticMeshComponent>> TreeComponents;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> TerrainMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> WaterMaterial;

	FIronHeightField HeightField;
	TFuture<TSharedPtr<FIronTerrainBuildResult>> BuildFuture;
	/** Finished worker output whose sections / trees are still being turned into components. */
	TSharedPtr<FIronTerrainBuildResult> PendingResult;
	/** SetTreeExclusions before the build (filtered by the worker). */
	TArray<FVector> TreeExclusionDiscs;
	/** ClearTrees discs (filtered on the game thread when the trees are planted). */
	TArray<FVector> TreeClearings;
	int32 NextSection = 0;
	int32 NextTreeType = 0;
	bool bStaticChunks = false;
	bool bBuildStarted = false;
	bool bHeightReady = false;
	bool bBuildComplete = false;
	bool bFailed = false;
};
