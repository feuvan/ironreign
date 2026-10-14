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

/** Overall style of the 3D scenes (docs/DESIGN.md section 12.6). */
enum class EIronLook : uint8
{
	/**
	 * The default: classical ink-and-colour painting on aged silk (gongbi, blue-green landscape). A gentle key light
	 * from the top-left, a high sky-light fill and soft shadows, no clouds, bloom or volumetric fog, a pale silk haze
	 * instead of a blue sky, matte materials and pale azurite water (MPC_IronSeason "Painted"), ink outlines
	 * (M_IronInk) and the aged-silk grade (M_IronSilk).
	 */
	Painted,
	/** The physically based "living diorama": blue sky, clouds and cloud shadows, filmic grade, bloom. */
	Realistic
};

/**
 * Lighting, weather and grading of one calendar month in one look; AIronEnvironment blends between them (season
 * changes and look switches alike).
 */
struct FIronSeasonLook
{
	/** Sun elevation above the horizon (late-afternoon sun, higher in summer; high and soft when painted). */
	float SunElevationDegrees = 32.0f;
	/**
	 * Compass bearing the sunlight comes from (0 = north, 90 = east): 235 (south-west) realistic, 305 painted (the
	 * top-left of the default north-facing view, the light of the painted 2D art).
	 */
	float SunBearingDegrees = 235.0f;
	/** Physically based sun illuminance (lux) with the fixed manual exposure of the post-process. */
	float SunIntensityLux = 8.0f;
	/** Linear sun tint (the sky atmosphere adds its own transmittance on top). */
	FLinearColor SunColor = FLinearColor(1.0f, 0.94f, 0.85f);
	/** Angular diameter of the sun in degrees: larger gives softer shadow edges (virtual shadow maps). */
	float SunSourceAngleDegrees = 1.0f;
	float SkyLightIntensity = 1.0f;
	float FogDensity = 0.0022f;
	FLinearColor FogColor = FLinearColor(0.34f, 0.37f, 0.40f);
	float FogMaxOpacity = 0.85f;
	/** Scalar "Coverage" of the cloud material (0 clear .. 1 overcast; the painted look has no clouds). */
	float CloudCoverage = 0.4f;
	/** Sky atmosphere Mie (haze) scattering scale; the engine default is ~0.004. */
	float MieScatteringScale = 0.0045f;
	/** Sky atmosphere Rayleigh (blue sky) scattering scale; the engine default is 0.0331. */
	float RayleighScatteringScale = 0.0331f;
	/** Sky atmosphere SkyLuminanceFactor: tints the sky and the sky light captured from it. */
	FLinearColor SkyLuminance = FLinearColor::White;
	/** Terrain material scalars (DESIGN.md 12.5). */
	float Snow = 0.0f;
	float Autumn = 0.0f;
	float Wetness = 0.0f;
	/** Filmic grading. */
	float Saturation = 1.05f;
	float Contrast = 1.04f;
	FLinearColor Gain = FLinearColor(1.0f, 1.0f, 0.98f);
	float WhiteTemp = 6600.0f;
	float BloomIntensity = 0.45f;
	float VignetteIntensity = 0.35f;
	/** Scale of the tilt-shift blur on top of the player's strength (AIronEnvironment::GetEffectiveTiltShiftStrength). */
	float DepthOfFieldScale = 1.0f;
	/**
	 * 0 realistic .. 1 painted: MPC_IronSeason "Painted" (matte materials, painted water) and the strength of the
	 * M_IronSilk grade. Fractional only while a look switch blends.
	 */
	float Painted = 0.0f;

	/** Realistic look of a month 1..12 (1-3 spring, 4-6 summer, 7-9 autumn, 10-12 winter). */
	static FIronSeasonLook ForMonth(int32 Month);
	/** Look of a month 1..12 in the given style (the seasonal Snow / Autumn / Wetness are the same in both). */
	static FIronSeasonLook ForMonth(int32 Month, EIronLook Look);
	static FIronSeasonLook Blend(const FIronSeasonLook& From, const FIronSeasonLook& To, float Alpha);
};

/**
 * The shared outdoor environment of the 3D scenes: sun (atmosphere sun light, virtual shadow maps, cloud shadows),
 * sky atmosphere, real-time captured sky light, volumetric clouds, exponential height fog with volumetric fog and an
 * unbound post-process (fixed manual exposure, Lumen GI + reflections, grading, tilt-shift depth of field, and the
 * M_IronInk / M_IronSilk blendables).
 *
 * Two looks (SetLook, docs/DESIGN.md 12.6): Painted (the default; gongbi ink and colour on aged silk) and Realistic.
 * The look and the season of the month are one FIronSeasonLook; switching either blends over ~2.5 s.
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
	 * scalars of MPC_IronSeason (read by every imported model material; its "Painted" scalar follows the look) and of
	 * every registered season material. Blends over ~2.5 s unless bInstant.
	 */
	void SetSeason(int32 Month, bool bInstant = false);
	int32 GetSeasonMonth() const { return SeasonMonth; }
	/** The look on screen now (season and style, mid-blend while either changes). */
	const FIronSeasonLook& GetCurrentLook() const { return CurrentLook; }

	/**
	 * Painted (default) or Realistic (docs/DESIGN.md 12.6). Blends over ~2.5 s unless bInstant; the painted look
	 * drops clouds and volumetric fog at once (cheaper), the realistic one brings them back as the quality allows.
	 * Both scenes follow: the strategy map through this actor, the battle board reads GetPaintedAmount for its ground
	 * and its moving sun. Nothing has to be rebuilt.
	 */
	void SetLook(EIronLook InLook, bool bInstant = false);
	EIronLook GetLook() const { return LookStyle; }
	/** 0 realistic .. 1 painted, as shown now (blends with SetLook). */
	float GetPaintedAmount() const { return CurrentLook.Painted; }

	/**
	 * 0 Low: no Lumen (sky light + screen-space reflections), no clouds, no volumetric fog, no depth of field.
	 * 1 Medium: Lumen, clouds, no volumetric fog. 2 High (default): everything. 3 Epic: higher Lumen quality.
	 * The painted look never has clouds or volumetric fog; its post-process (ink, silk) is the same at every level.
	 */
	void SetQuality(int32 Level);
	int32 GetQuality() const { return QualityLevel; }

	/**
	 * Tilt-shift depth of field focused at FocusDistanceCm (the camera-to-target distance). The aperture is derived
	 * from the focus distance and field of view so the miniature blur looks the same at every zoom. 0 disables DOF.
	 */
	void SetTiltShift(float InFocusDistanceCm, float HorizontalFovDegrees = 40.0f);
	/**
	 * The player's scale of the tilt-shift blur, 0..2 (default 1; 0 turns depth of field off). It applies to every 3D
	 * scene: the strategy map's focus here, and the battle board's own camera (it reads
	 * GetEffectiveTiltShiftStrength every frame).
	 */
	void SetTiltShiftStrength(float Strength);
	float GetTiltShiftStrength() const { return TiltShiftStrength; }
	/** What the depth of field uses: the player's strength x the look's scale (painted 0.6, realistic 1). */
	float GetEffectiveTiltShiftStrength() const;
	/**
	 * 0..1 strength of the M_IronInk outline pass (default 1: the painted look draws ink outlines; no-op when the
	 * material was not imported). A material blendable's weight does not fade it, so this scales the instance's
	 * "Strength" parameter; 0 removes the pass. Independent of the look: the realistic look may have ink too, and the
	 * painted look without ink keeps its silk grade.
	 */
	void SetInkStrength(float Strength);
	float GetInkStrength() const { return InkStrength; }
	/** Manual exposure compensation in EV (default 0.3). */
	void SetExposureBias(float Bias);
	/**
	 * Overrides the compass bearing the sunlight comes from (0 = north, 90 = east); by default the look's bearing is
	 * used (235 = south-west realistic, 305 = north-west painted). A negative value returns to the look's bearing.
	 */
	void SetSunBearing(float BearingDegrees);
	/**
	 * Puts the sun back where the current look and season want it, after a scene turned it (the battle board moves
	 * the shared sun through the battle's days and calls this when it deactivates).
	 */
	void RefreshSun();

	/** Receives the scalars Snow / Autumn / Wetness on every season change (e.g. the terrain material). Weakly held. */
	void RegisterSeasonMaterial(UMaterialInstanceDynamic* Material);

	UDirectionalLightComponent* GetSun() const;
	UPostProcessComponent* GetPostProcess() const;
	UExponentialHeightFogComponent* GetHeightFog() const;

protected:
	virtual void BeginPlay() override;

private:
	/** Blends (or jumps) to the look of SeasonMonth in LookStyle. */
	void StartLookTransition(bool bInstant);
	void ApplyLook(const FIronSeasonLook& Look);
	void ApplyQuality();
	void ApplyDepthOfField();
	void UpdateSunRotation(float ElevationDegrees, float LookBearingDegrees);
	void EnsureClouds();
	void RemoveClouds();
	void InitPostProcess();
	void ApplyInk();
	/** M_IronSilk at Strength (the painted amount); its blendable is off at 0. */
	void ApplySilk(float Strength);
	/** Adds Material as a post-process blendable (weight 0) through a dynamic instance; returns the instance. */
	UMaterialInstanceDynamic* AddBlendable(UMaterialInterface* Material);
	void SetBlendableWeight(const UObject* Blendable, float Weight);

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

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> SilkMaterial;

	/** Dynamic instance of M_IronSilk used as the blendable (its "Strength" follows the painted amount). */
	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> SilkInstance;

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
	EIronLook LookStyle = EIronLook::Painted;
	/** SetSunBearing override; negative = the look's bearing. */
	float SunBearingOverride = -1.0f;
	float ExposureBias = 0.3f;
	float InkStrength = 1.0f;
	/** M_IronInk's own "Strength" (the look at SetInkStrength(1)). */
	float InkBaseStrength = 0.9f;
	float TiltShiftStrength = 1.0f;
	float FocusDistanceCm = 0.0f;
	float FocusFovDegrees = 40.0f;
	/** M_IronSilk "Strength" last applied (-1 = never). */
	float AppliedSilkStrength = -1.0f;
	bool bLookApplied = false;
};
