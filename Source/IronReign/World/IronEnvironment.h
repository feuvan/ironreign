#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "IronEnvironment.generated.h"

class UDirectionalLightComponent;
class UExponentialHeightFogComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UMaterialParameterCollection;
class UPostProcessComponent;
class USceneComponent;
class USkyAtmosphereComponent;
class USkyLightComponent;
class UVolumetricCloudComponent;

/** Lighting, weather and grading of one calendar month; AIronEnvironment blends between looks. */
struct FIronSeasonLook
{
	/** Sun elevation above the horizon (late-afternoon sun, higher in summer). */
	float SunElevationDegrees = 32.0f;
	/** Physically based sun illuminance (lux) with the fixed manual exposure of the post-process. */
	float SunIntensityLux = 8.0f;
	/** Linear sun tint (the sky atmosphere adds its own transmittance on top). */
	FLinearColor SunColor = FLinearColor(1.0f, 0.94f, 0.85f);
	float SkyLightIntensity = 1.0f;
	float FogDensity = 0.0022f;
	FLinearColor FogColor = FLinearColor(0.34f, 0.37f, 0.40f);
	/** Scalar "Coverage" of the cloud material (0 clear .. 1 overcast). */
	float CloudCoverage = 0.4f;
	/** Sky atmosphere Mie (haze) scattering scale; the engine default is ~0.004. */
	float MieScatteringScale = 0.0045f;
	/** Terrain material scalars (DESIGN.md 12.5). */
	float Snow = 0.0f;
	float Autumn = 0.0f;
	float Wetness = 0.0f;
	/** Filmic grading. */
	float Saturation = 1.05f;
	float Contrast = 1.04f;
	FLinearColor Gain = FLinearColor(1.0f, 1.0f, 0.98f);
	float WhiteTemp = 6600.0f;

	/** Look of a month 1..12 (1-3 spring, 4-6 summer, 7-9 autumn, 10-12 winter). */
	static FIronSeasonLook ForMonth(int32 Month);
	static FIronSeasonLook Blend(const FIronSeasonLook& From, const FIronSeasonLook& To, float Alpha);
};

/**
 * The shared outdoor environment of the 3D scenes: sun (atmosphere sun light, virtual shadow maps, cloud shadows),
 * sky atmosphere, real-time captured sky light, volumetric clouds, exponential height fog with volumetric fog and an
 * unbound post-process (fixed manual exposure, Lumen GI + reflections, warm filmic grading, tilt-shift depth of field,
 * optional M_IronInk blendable).
 *
 * One per world (FindOrSpawn): the strategy map and the battle board both use it, so neither hides or destroys it.
 * All components are movable; nothing needs baked lighting.
 */
UCLASS(NotBlueprintable)
class IRONREIGN_API AIronEnvironment : public AActor
{
	GENERATED_BODY()

public:
	AIronEnvironment();

	/** The world's environment, spawned (transient) on first use. */
	static AIronEnvironment* FindOrSpawn(UWorld* World);

	virtual void Tick(float DeltaSeconds) override;

	/**
	 * Month 1..12: sun elevation/colour, sky haze, fog density, cloud coverage, grading, and the Snow/Autumn/Wetness
	 * scalars of MPC_IronSeason (read by every imported model material) and of every registered season material.
	 * Blends over ~2.5 s unless bInstant.
	 */
	void SetSeason(int32 Month, bool bInstant = false);
	int32 GetSeasonMonth() const { return SeasonMonth; }
	const FIronSeasonLook& GetCurrentLook() const { return CurrentLook; }

	/**
	 * 0 Low: no Lumen (sky light + screen-space reflections), no clouds, no volumetric fog, no depth of field.
	 * 1 Medium: Lumen, clouds, no volumetric fog. 2 High (default): everything. 3 Epic: higher Lumen quality.
	 */
	void SetQuality(int32 Level);
	int32 GetQuality() const { return QualityLevel; }

	/**
	 * Tilt-shift depth of field focused at FocusDistanceCm (the camera-to-target distance). The aperture is derived
	 * from the focus distance and field of view so the miniature blur looks the same at every zoom. 0 disables DOF.
	 */
	void SetTiltShift(float InFocusDistanceCm, float HorizontalFovDegrees = 40.0f);
	/**
	 * Scale of the tilt-shift blur, 0..2 (default 1; 0 turns depth of field off). It applies to every 3D scene: the
	 * strategy map's focus here, and the battle board's own camera (AIronBattleBoard3D reads GetTiltShiftStrength).
	 */
	void SetTiltShiftStrength(float Strength);
	float GetTiltShiftStrength() const { return TiltShiftStrength; }
	/**
	 * 0..1 strength of the M_IronInk outline pass (no-op when the material was not imported). A material blendable's
	 * weight does not fade it, so this scales the instance's "Strength" parameter; 0 removes the pass.
	 */
	void SetInkStrength(float Strength);
	/** Manual exposure compensation in EV (default 0.3). */
	void SetExposureBias(float Bias);
	/** Compass bearing the sunlight comes from (0 = north, 90 = east, default 235 = south-west). */
	void SetSunBearing(float BearingDegrees);

	/** Receives the scalars Snow / Autumn / Wetness on every season change (e.g. the terrain material). Weakly held. */
	void RegisterSeasonMaterial(UMaterialInstanceDynamic* Material);

	UDirectionalLightComponent* GetSun() const;
	UPostProcessComponent* GetPostProcess() const;
	UExponentialHeightFogComponent* GetHeightFog() const;

protected:
	virtual void BeginPlay() override;

private:
	void ApplyLook(const FIronSeasonLook& Look);
	void ApplyQuality();
	void ApplyDepthOfField();
	void UpdateSunRotation(float ElevationDegrees);
	void EnsureClouds();
	void RemoveClouds();
	void InitPostProcess();
	void ApplyInk();

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USceneComponent> SceneRoot;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<UDirectionalLightComponent> Sun;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USkyAtmosphereComponent> SkyAtmosphere;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<USkyLightComponent> SkyLight;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<UExponentialHeightFogComponent> HeightFog;

	UPROPERTY(VisibleAnywhere, Category = "Iron Reign")
	TObjectPtr<UPostProcessComponent> PostProcess;

	/** Created at runtime when a cloud material exists and the quality allows clouds. */
	UPROPERTY(Transient)
	TObjectPtr<UVolumetricCloudComponent> Clouds;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> CloudBaseMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> CloudMaterial;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> InkMaterial;

	/** Dynamic instance of M_IronInk used as the blendable (its "Strength" follows SetInkStrength). */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> InkInstance;

	/** MPC_IronSeason from the import, when present. */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialParameterCollection> SeasonCollection;

	TArray<TWeakObjectPtr<UMaterialInstanceDynamic>> SeasonMaterials;

	FIronSeasonLook FromLook;
	FIronSeasonLook TargetLook;
	FIronSeasonLook CurrentLook;
	/** 0..1 progress of the season blend; 1 = settled. */
	float TransitionAlpha = 1.0f;
	int32 SeasonMonth = 4;
	int32 QualityLevel = 2;
	float SunBearingDegrees = 235.0f;
	float ExposureBias = 0.3f;
	float InkStrength = 0.0f;
	/** M_IronInk's own "Strength" (the look at SetInkStrength(1)). */
	float InkBaseStrength = 0.6f;
	float TiltShiftStrength = 1.0f;
	float FocusDistanceCm = 0.0f;
	float FocusFovDegrees = 40.0f;
	bool bLookApplied = false;
};
