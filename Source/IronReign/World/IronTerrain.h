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
};

/**
 * The strategy map terrain, built at runtime from Content/Data/Art3D/Terrain (DESIGN.md 12.2):
 *  - the heightmap as a grid of procedural mesh chunks (8 x 5, shared edges, smooth normals from the heightfield,
 *    tangents along +X, UV0 = (x / width, y / height), UV1 = map metres / 50 for detail tiling) with a dynamic
 *    instance of MI_IronTerrain / M_IronTerrain (fallback: tinted BasicShapeMaterial),
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

	/** Starts the asynchronous build. MeshStride 1 = full 2 m grid (Epic), 2 = 4 m grid (default). Call once. */
	void BeginBuild(int32 MeshStride = 2);

	/** SampleHeight / TraceSurface are valid (the heightmap was decoded). */
	bool IsHeightReady() const { return bHeightReady; }
	/** Every terrain chunk, the sea and the trees exist. */
	bool IsBuildComplete() const { return bBuildComplete; }
	/** Loading failed (missing or corrupt data); the 3D map cannot be shown. */
	bool HasFailed() const { return bFailed; }

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
	void HandleBuildResult(const TSharedPtr<FIronTerrainBuildResult>& Result);
	void CreatePendingComponents();
	void CreateSea();
	void CreateTrees(int32 TreeType);
	UProceduralMeshComponent* NewMeshComponent();

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UProceduralMeshComponent>> Chunks;

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
	int32 NextSection = 0;
	int32 NextTreeType = 0;
	bool bBuildStarted = false;
	bool bHeightReady = false;
	bool bBuildComplete = false;
	bool bFailed = false;
};
