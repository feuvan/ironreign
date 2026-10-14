#include "World/IronEnvironment.h"

#include "World/IronWorldAssets.h"
#include "World/IronWorldMath.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/PostProcessComponent.h"
#include "Components/SceneComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"
#include "Components/VolumetricCloudComponent.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Materials/MaterialParameterCollectionInstance.h"

namespace IronEnvironmentDetail
{
	// Per month, index 0 = month 1. Seasons: 1-3 spring, 4-6 summer, 7-9 autumn, 10-12 winter.
	// Late-afternoon sun: low enough for long soft shadows, higher in summer.
	constexpr float MonthSunElevation[12] = {22.0f, 26.0f, 30.0f, 35.0f, 39.0f, 41.0f, 39.0f, 34.0f, 29.0f, 25.0f, 21.0f, 19.0f};
	constexpr float MonthSunLux[12] = {7.0f, 7.4f, 7.9f, 8.4f, 8.8f, 9.0f, 9.0f, 8.6f, 8.1f, 7.6f, 7.1f, 6.8f};
	// Snow and autumn colour stay inside the seasons IronSim::SeasonName prints (month 1 = "Spring" keeps only a late
	// dusting of snow, month 10 = "Winter" is already more snow than leaves).
	constexpr float MonthSnow[12] = {0.15f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.45f, 0.75f, 0.9f};
	constexpr float MonthAutumn[12] = {0.0f, 0.0f, 0.0f, 0.0f, 0.0f, 0.05f, 0.35f, 0.75f, 1.0f, 0.3f, 0.1f, 0.0f};
	constexpr float MonthWetness[12] = {0.2f, 0.3f, 0.45f, 0.4f, 0.5f, 0.65f, 0.4f, 0.2f, 0.15f, 0.15f, 0.2f, 0.2f};
	constexpr float MonthFogDensity[12] = {0.0032f, 0.003f, 0.0028f, 0.0022f, 0.0018f, 0.0019f, 0.0016f, 0.0018f, 0.0022f, 0.0026f, 0.003f, 0.0034f};
	constexpr float MonthCloudCoverage[12] = {0.55f, 0.5f, 0.45f, 0.4f, 0.38f, 0.45f, 0.35f, 0.3f, 0.32f, 0.4f, 0.5f, 0.58f};
	constexpr float MonthMieScale[12] = {0.006f, 0.0055f, 0.005f, 0.0045f, 0.004f, 0.0042f, 0.004f, 0.004f, 0.0045f, 0.005f, 0.0055f, 0.006f};

	struct FSeasonPalette
	{
		float Sun[3];
		float Fog[3];
		float Gain[3];
		float Saturation;
		float Contrast;
		float WhiteTemp;
		float SkyLight;
	};

	constexpr FSeasonPalette SeasonPalettes[4] = {
		// Spring: fresh, light haze.
		{{1.0f, 0.94f, 0.85f}, {0.34f, 0.37f, 0.40f}, {1.0f, 1.01f, 0.98f}, 1.05f, 1.04f, 6600.0f, 1.0f},
		// Summer: saturated, clear.
		{{1.0f, 0.95f, 0.88f}, {0.33f, 0.37f, 0.42f}, {1.0f, 1.0f, 0.98f}, 1.08f, 1.06f, 6700.0f, 1.0f},
		// Autumn: golden.
		{{1.0f, 0.84f, 0.64f}, {0.38f, 0.35f, 0.30f}, {1.04f, 1.0f, 0.93f}, 1.06f, 1.05f, 7000.0f, 0.95f},
		// Winter: pale and cool, snow bounce.
		{{0.96f, 0.91f, 0.85f}, {0.36f, 0.38f, 0.42f}, {0.98f, 1.0f, 1.03f}, 0.9f, 1.0f, 6200.0f, 1.1f},
	};

	/**
	 * Height-fog colour of the painted look per season (linear): the pale silk haze of a blue-green landscape
	 * painting, where bare silk serves as mist and distance (docs/DESIGN.md sections 8 and 12.6).
	 */
	constexpr float PaintedFog[4][3] = {
		{0.48f, 0.45f, 0.35f},
		{0.47f, 0.45f, 0.36f},
		{0.52f, 0.45f, 0.31f},
		{0.50f, 0.48f, 0.42f},
	};
	/** Painted key light: from the top-left of the north-facing view, high and warm. */
	constexpr float PaintedSunBearingDegrees = 305.0f;
	constexpr float PaintedSunColor[3] = {1.0f, 0.95f, 0.87f};
	/** Realistic key light (the bearing of the first 3D version). */
	constexpr float RealisticSunBearingDegrees = 235.0f;

	constexpr float SeasonBlendSeconds = 2.5f;
	/** Target circle of confusion at infinity, as a fraction of the image width, at tilt-shift strength 1. */
	constexpr double TiltShiftInfinityCoc = 0.022;
	constexpr double SensorWidthMm = 24.576;

	FLinearColor ColorOf(const float (&Rgb)[3])
	{
		return FLinearColor(Rgb[0], Rgb[1], Rgb[2], 1.0f);
	}

	FVector4 Uniform4(float Value)
	{
		return FVector4(Value, Value, Value, 1.0f);
	}

	/** Scalar of M_IronInk / M_IronSilk that scales the pass (Content/Python/ironreign_import.py). */
	FName PassStrengthParameter()
	{
		return FName(TEXT("Strength"));
	}

	/** MPC_IronSeason scalar of the look (1 painted .. 0 realistic) read by every imported material. */
	FName PaintedParameter()
	{
		return FName(TEXT("Painted"));
	}

	/** The painted version of a realistic month look (SeasonIndex 0 spring .. 3 winter). */
	FIronSeasonLook ToPainted(const FIronSeasonLook& Real, int32 SeasonIndex)
	{
		FIronSeasonLook Look = Real;
		// A gentle key from the top-left, high in the sky: short, soft shadows that model the forms without drama.
		Look.SunBearingDegrees = PaintedSunBearingDegrees;
		Look.SunElevationDegrees = FMath::Clamp(Real.SunElevationDegrees + 16.0f, 40.0f, 56.0f);
		Look.SunIntensityLux = Real.SunIntensityLux * 0.6f;
		Look.SunColor = FMath::Lerp(Real.SunColor, ColorOf(PaintedSunColor), 0.6f);
		Look.SunSourceAngleDegrees = 8.0f;
		// A high sky-light fill keeps the shading low in contrast, like a flat mineral wash.
		Look.SkyLightIntensity = Real.SkyLightIntensity * 2.4f;
		// A pale silk haze instead of a saturated blue sky: little Rayleigh, more Mie, a warm sky; silk mist in valleys.
		Look.RayleighScatteringScale = 0.012f;
		Look.MieScatteringScale = Real.MieScatteringScale * 2.2f;
		Look.SkyLuminance = FLinearColor(1.12f, 1.02f, 0.82f, 1.0f);
		Look.FogDensity = Real.FogDensity * 1.5f;
		Look.FogColor = ColorOf(PaintedFog[FMath::Clamp(SeasonIndex, 0, 3)]);
		Look.FogMaxOpacity = 0.92f;
		// Grading toward the mineral palette; M_IronSilk adds the silk itself after tonemapping.
		Look.Saturation = Real.Saturation * 0.84f;
		Look.Contrast = 0.9f;
		Look.Gain = FLinearColor(Real.Gain.R * 1.02f, Real.Gain.G, Real.Gain.B * 0.94f, 1.0f);
		Look.WhiteTemp = Real.WhiteTemp + 300.0f;
		Look.BloomIntensity = 0.0f;
		Look.VignetteIntensity = 0.15f;
		Look.DepthOfFieldScale = 0.6f;
		Look.Painted = 1.0f;
		return Look;
	}

	/**
	 * Writes Value to a component property when it differs by more than Tolerance; true when it changed (the caller
	 * then marks the component's render state dirty once).
	 */
	bool ChangeFloat(float& Property, float Value, float Tolerance)
	{
		if (FMath::IsNearlyEqual(Property, Value, Tolerance))
		{
			return false;
		}
		Property = Value;
		return true;
	}

	/** Cloud coverage under the parameter names the cloud materials may use (unknown names are ignored). */
	void SetCloudCoverage(UMaterialInstanceDynamic* Material, float Coverage)
	{
		if (Material != nullptr)
		{
			Material->SetScalarParameterValue(FName(TEXT("Coverage")), Coverage);
			Material->SetScalarParameterValue(FName(TEXT("CloudCoverage")), Coverage);
		}
	}
}

FIronSeasonLook FIronSeasonLook::ForMonth(int32 Month)
{
	using namespace IronEnvironmentDetail;
	const int32 Index = FMath::Clamp(Month, 1, 12) - 1;
	const FSeasonPalette& Palette = SeasonPalettes[Index / 3];

	FIronSeasonLook Look;
	Look.SunElevationDegrees = MonthSunElevation[Index];
	Look.SunBearingDegrees = RealisticSunBearingDegrees;
	Look.SunIntensityLux = MonthSunLux[Index];
	Look.SunColor = ColorOf(Palette.Sun);
	Look.SkyLightIntensity = Palette.SkyLight;
	Look.FogDensity = MonthFogDensity[Index];
	Look.FogColor = ColorOf(Palette.Fog);
	Look.CloudCoverage = MonthCloudCoverage[Index];
	Look.MieScatteringScale = MonthMieScale[Index];
	Look.Snow = MonthSnow[Index];
	Look.Autumn = MonthAutumn[Index];
	Look.Wetness = MonthWetness[Index];
	Look.Saturation = Palette.Saturation;
	Look.Contrast = Palette.Contrast;
	Look.Gain = ColorOf(Palette.Gain);
	Look.WhiteTemp = Palette.WhiteTemp;
	return Look;
}

FIronSeasonLook FIronSeasonLook::ForMonth(int32 Month, EIronLook Look)
{
	const FIronSeasonLook Realistic = ForMonth(Month);
	if (Look == EIronLook::Realistic)
	{
		return Realistic;
	}
	return IronEnvironmentDetail::ToPainted(Realistic, (FMath::Clamp(Month, 1, 12) - 1) / 3);
}

FIronSeasonLook FIronSeasonLook::Blend(const FIronSeasonLook& From, const FIronSeasonLook& To, float Alpha)
{
	const float T = FMath::Clamp(Alpha, 0.0f, 1.0f);
	FIronSeasonLook Look;
	Look.SunElevationDegrees = FMath::Lerp(From.SunElevationDegrees, To.SunElevationDegrees, T);
	// Bearings stay within 0..360 and the looks' bearings are 70 degrees apart: a plain lerp takes the short way.
	Look.SunBearingDegrees = FMath::Lerp(From.SunBearingDegrees, To.SunBearingDegrees, T);
	Look.SunIntensityLux = FMath::Lerp(From.SunIntensityLux, To.SunIntensityLux, T);
	Look.SunColor = FMath::Lerp(From.SunColor, To.SunColor, T);
	Look.SunSourceAngleDegrees = FMath::Lerp(From.SunSourceAngleDegrees, To.SunSourceAngleDegrees, T);
	Look.SkyLightIntensity = FMath::Lerp(From.SkyLightIntensity, To.SkyLightIntensity, T);
	Look.FogDensity = FMath::Lerp(From.FogDensity, To.FogDensity, T);
	Look.FogColor = FMath::Lerp(From.FogColor, To.FogColor, T);
	Look.FogMaxOpacity = FMath::Lerp(From.FogMaxOpacity, To.FogMaxOpacity, T);
	Look.CloudCoverage = FMath::Lerp(From.CloudCoverage, To.CloudCoverage, T);
	Look.MieScatteringScale = FMath::Lerp(From.MieScatteringScale, To.MieScatteringScale, T);
	Look.RayleighScatteringScale = FMath::Lerp(From.RayleighScatteringScale, To.RayleighScatteringScale, T);
	Look.SkyLuminance = FMath::Lerp(From.SkyLuminance, To.SkyLuminance, T);
	Look.Snow = FMath::Lerp(From.Snow, To.Snow, T);
	Look.Autumn = FMath::Lerp(From.Autumn, To.Autumn, T);
	Look.Wetness = FMath::Lerp(From.Wetness, To.Wetness, T);
	Look.Saturation = FMath::Lerp(From.Saturation, To.Saturation, T);
	Look.Contrast = FMath::Lerp(From.Contrast, To.Contrast, T);
	Look.Gain = FMath::Lerp(From.Gain, To.Gain, T);
	Look.WhiteTemp = FMath::Lerp(From.WhiteTemp, To.WhiteTemp, T);
	Look.BloomIntensity = FMath::Lerp(From.BloomIntensity, To.BloomIntensity, T);
	Look.VignetteIntensity = FMath::Lerp(From.VignetteIntensity, To.VignetteIntensity, T);
	Look.DepthOfFieldScale = FMath::Lerp(From.DepthOfFieldScale, To.DepthOfFieldScale, T);
	Look.Painted = FMath::Lerp(From.Painted, To.Painted, T);
	return Look;
}

AIronEnvironment::AIronEnvironment()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	SetRootComponent(SceneRoot);

	// Sun: the atmosphere's sun light, soft virtual shadows, cloud shadows. Shadow distances only matter when the
	// project falls back to cascaded shadow maps (VSM covers the whole view on its own).
	Sun = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("Sun"));
	Sun->SetupAttachment(SceneRoot);
	Sun->SetMobility(EComponentMobility::Movable);
	Sun->Intensity = 8.0f;
	Sun->LightColor = FColor(255, 241, 222);
	Sun->LightSourceAngle = 1.0f;
	Sun->CastShadows = true;
	Sun->bAtmosphereSunLight = true;
	Sun->AtmosphereSunLightIndex = 0;
	Sun->bCastCloudShadows = true;
	Sun->CloudShadowStrength = 0.45f;
	Sun->CloudShadowExtent = 12.0f;
	Sun->DynamicShadowDistanceMovableLight = 600000.0f;
	Sun->DynamicShadowCascades = 4;
	Sun->SetRelativeRotation(FRotator(-32.0, -30.0, 0.0));

	SkyAtmosphere = CreateDefaultSubobject<USkyAtmosphereComponent>(TEXT("SkyAtmosphere"));
	SkyAtmosphere->SetupAttachment(SceneRoot);
	// Warm earthy ground bounce for the lower sky hemisphere.
	SkyAtmosphere->GroundAlbedo = FColor(112, 104, 82);
	SkyAtmosphere->MieScatteringScale = 0.0045f;

	SkyLight = CreateDefaultSubobject<USkyLightComponent>(TEXT("SkyLight"));
	SkyLight->SetupAttachment(SceneRoot);
	SkyLight->SetMobility(EComponentMobility::Movable);
	SkyLight->SourceType = ESkyLightSourceType::SLS_CapturedScene;
	SkyLight->bRealTimeCapture = true;
	SkyLight->bLowerHemisphereIsBlack = false;
	SkyLight->Intensity = 1.0f;

	// Faint distance haze: density halves roughly every 350 m of altitude, so valleys stay misty while the camera
	// (250..2600 m away) looks through a light veil. Volumetric fog reaches 4 km to catch sun shafts and cloud shadows.
	HeightFog = CreateDefaultSubobject<UExponentialHeightFogComponent>(TEXT("HeightFog"));
	HeightFog->SetupAttachment(SceneRoot);
	HeightFog->FogDensity = 0.0022f;
	HeightFog->FogHeightFalloff = 0.03f;
	HeightFog->FogMaxOpacity = 0.85f;
	HeightFog->StartDistance = 0.0f;
	HeightFog->bEnableVolumetricFog = true;
	HeightFog->VolumetricFogScatteringDistribution = 0.55f;
	HeightFog->VolumetricFogExtinctionScale = 1.0f;
	HeightFog->VolumetricFogDistance = 400000.0f;

	PostProcess = CreateDefaultSubobject<UPostProcessComponent>(TEXT("PostProcess"));
	PostProcess->SetupAttachment(SceneRoot);
	PostProcess->bUnbound = true;
	PostProcess->Priority = 0.0f;
	InitPostProcess();

	CurrentLook = FIronSeasonLook::ForMonth(SeasonMonth, LookStyle);
	FromLook = CurrentLook;
	TargetLook = CurrentLook;
}

AIronEnvironment* AIronEnvironment::FindOrSpawn(UWorld* World)
{
	if (World == nullptr)
	{
		return nullptr;
	}
	for (TActorIterator<AIronEnvironment> It(World); It; ++It)
	{
		if (IsValid(*It))
		{
			return *It;
		}
	}
	FActorSpawnParameters SpawnParams;
	SpawnParams.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	SpawnParams.ObjectFlags |= RF_Transient;
	return World->SpawnActor<AIronEnvironment>(AIronEnvironment::StaticClass(), FTransform::Identity, SpawnParams);
}

UDirectionalLightComponent* AIronEnvironment::GetSun() const
{
	return Sun.Get();
}

UPostProcessComponent* AIronEnvironment::GetPostProcess() const
{
	return PostProcess.Get();
}

UExponentialHeightFogComponent* AIronEnvironment::GetHeightFog() const
{
	return HeightFog.Get();
}

void AIronEnvironment::InitPostProcess()
{
	FPostProcessSettings& Settings = PostProcess->Settings;

	// Fixed manual exposure tuned for the ~8 lux sun: no eye adaptation pumping while the camera flies over sea and snow.
	Settings.bOverride_AutoExposureMethod = true;
	Settings.AutoExposureMethod = EAutoExposureMethod::AEM_Manual;
	Settings.bOverride_AutoExposureApplyPhysicalCameraExposure = true;
	Settings.AutoExposureApplyPhysicalCameraExposure = false;
	Settings.bOverride_AutoExposureBias = true;
	Settings.AutoExposureBias = ExposureBias;

	Settings.bOverride_BloomIntensity = true;
	Settings.BloomIntensity = 0.45f;
	Settings.bOverride_VignetteIntensity = true;
	Settings.VignetteIntensity = 0.35f;
	Settings.bOverride_MotionBlurAmount = true;
	Settings.MotionBlurAmount = 0.0f;
	Settings.bOverride_LensFlareIntensity = true;
	Settings.LensFlareIntensity = 0.0f;
	Settings.bOverride_SceneFringeIntensity = true;
	Settings.SceneFringeIntensity = 0.0f;

	// Filmic grading (warm); values are refreshed per season by ApplyLook.
	Settings.bOverride_ColorSaturation = true;
	Settings.bOverride_ColorContrast = true;
	Settings.bOverride_ColorGain = true;
	Settings.bOverride_WhiteTemp = true;

	// Lumen GI + reflections. The diorama is seen from 250..2600 m, far beyond the default Lumen scene range.
	Settings.bOverride_DynamicGlobalIlluminationMethod = true;
	Settings.bOverride_ReflectionMethod = true;
	Settings.bOverride_LumenSceneViewDistance = true;
	Settings.LumenSceneViewDistance = 500000.0f;
	Settings.bOverride_LumenMaxTraceDistance = true;
	Settings.LumenMaxTraceDistance = 100000.0f;
	Settings.bOverride_LumenFinalGatherQuality = true;
	Settings.bOverride_LumenSceneLightingQuality = true;
	Settings.bOverride_LumenReflectionQuality = true;

	// Tilt-shift depth of field (cinematic/diaphragm DOF). Focus and aperture follow the camera (SetTiltShift).
	Settings.bOverride_DepthOfFieldFocalDistance = true;
	Settings.DepthOfFieldFocalDistance = 0.0f;
	Settings.bOverride_DepthOfFieldFstop = true;
	Settings.DepthOfFieldFstop = 4.0f;
	Settings.bOverride_DepthOfFieldMinFstop = true;
	Settings.DepthOfFieldMinFstop = 0.0f;
	Settings.bOverride_DepthOfFieldBladeCount = true;
	Settings.DepthOfFieldBladeCount = 12;
	Settings.bOverride_DepthOfFieldSensorWidth = true;
	Settings.DepthOfFieldSensorWidth = static_cast<float>(IronEnvironmentDetail::SensorWidthMm);
	Settings.bOverride_DepthOfFieldFocalRegion = true;
	Settings.DepthOfFieldFocalRegion = 0.0f;
}

void AIronEnvironment::BeginPlay()
{
	Super::BeginPlay();

	CloudBaseMaterial = IronWorld::LoadMaterial(TEXT("MI_IronClouds"));
	if (CloudBaseMaterial == nullptr)
	{
		CloudBaseMaterial = IronWorld::LoadEngineMaterial(IronWorld::EngineCloudMaterialPath);
	}
	if (CloudBaseMaterial == nullptr)
	{
		UE_LOG(LogIronWorld, Log, TEXT("No volumetric cloud material (MI_IronClouds); the realistic sky stays clear."));
	}

	SeasonCollection = IronWorld::LoadSeasonCollection();
	InkMaterial = IronWorld::LoadMaterial(TEXT("M_IronInk"));
	if (InkMaterial != nullptr)
	{
		InkInstance = AddBlendable(InkMaterial.Get());
		if (InkInstance != nullptr)
		{
			const float MaterialStrength = InkInstance->K2_GetScalarParameterValue(IronEnvironmentDetail::PassStrengthParameter());
			if (MaterialStrength > 0.0f)
			{
				InkBaseStrength = MaterialStrength;
			}
		}
		ApplyInk();
	}
	SilkMaterial = IronWorld::LoadMaterial(TEXT("M_IronSilk"));
	if (SilkMaterial != nullptr)
	{
		SilkInstance = AddBlendable(SilkMaterial.Get());
	}
	else
	{
		UE_LOG(LogIronWorld, Log, TEXT("M_IronSilk was not imported (run the asset import): the painted look has no silk grade."));
	}

	ApplyQuality();
	SetSeason(SeasonMonth, true);
}

UMaterialInstanceDynamic* AIronEnvironment::AddBlendable(UMaterialInterface* Material)
{
	if (Material == nullptr)
	{
		return nullptr;
	}
	UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(Material, this);
	UObject* Blendable = Instance != nullptr ? static_cast<UObject*>(Instance) : static_cast<UObject*>(Material);
	PostProcess->Settings.WeightedBlendables.Array.Add(FWeightedBlendable(0.0f, Blendable));
	return Instance;
}

void AIronEnvironment::SetBlendableWeight(const UObject* Blendable, float Weight)
{
	for (FWeightedBlendable& Entry : PostProcess->Settings.WeightedBlendables.Array)
	{
		const UObject* EntryObject = Entry.Object;
		if (EntryObject == Blendable)
		{
			Entry.Weight = Weight;
		}
	}
}

void AIronEnvironment::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	if (TransitionAlpha < 1.0f)
	{
		TransitionAlpha = FMath::Min(1.0f, TransitionAlpha + DeltaSeconds / IronEnvironmentDetail::SeasonBlendSeconds);
		const float Eased = static_cast<float>(IronWorld::EaseInOut(static_cast<double>(TransitionAlpha)));
		CurrentLook = FIronSeasonLook::Blend(FromLook, TargetLook, Eased);
		ApplyLook(CurrentLook);
	}
}

void AIronEnvironment::SetSeason(int32 Month, bool bInstant)
{
	const int32 NewMonth = FMath::Clamp(Month, 1, 12);
	if (NewMonth == SeasonMonth && bLookApplied && !bInstant)
	{
		return;
	}
	SeasonMonth = NewMonth;
	StartLookTransition(bInstant);
}

void AIronEnvironment::SetLook(EIronLook InLook, bool bInstant)
{
	if (InLook == LookStyle && !bInstant)
	{
		return;
	}
	LookStyle = InLook;
	// Clouds and volumetric fog belong to the realistic look only: switch them now, the rest blends.
	if (HasActorBegunPlay())
	{
		ApplyQuality();
	}
	StartLookTransition(bInstant);
}

void AIronEnvironment::StartLookTransition(bool bInstant)
{
	TargetLook = FIronSeasonLook::ForMonth(SeasonMonth, LookStyle);
	if (bInstant || !bLookApplied)
	{
		CurrentLook = TargetLook;
		FromLook = TargetLook;
		TransitionAlpha = 1.0f;
		ApplyLook(CurrentLook);
		bLookApplied = true;
		return;
	}
	FromLook = CurrentLook;
	TransitionAlpha = 0.0f;
}

void AIronEnvironment::ApplyLook(const FIronSeasonLook& Look)
{
	using IronEnvironmentDetail::ChangeFloat;
	UpdateSunRotation(Look.SunElevationDegrees, Look.SunBearingDegrees);
	Sun->SetIntensity(Look.SunIntensityLux);
	Sun->SetLightColor(Look.SunColor, false);
	if (ChangeFloat(Sun->LightSourceAngle, Look.SunSourceAngleDegrees, 0.01f))
	{
		Sun->MarkRenderStateDirty();
	}
	SkyLight->SetIntensity(Look.SkyLightIntensity);
	HeightFog->SetFogDensity(Look.FogDensity);
	HeightFog->SetFogInscatteringColor(Look.FogColor);
	HeightFog->SetFogMaxOpacity(Look.FogMaxOpacity);

	bool bSkyChanged = ChangeFloat(SkyAtmosphere->MieScatteringScale, Look.MieScatteringScale, 1.0e-5f);
	bSkyChanged |= ChangeFloat(SkyAtmosphere->RayleighScatteringScale, Look.RayleighScatteringScale, 1.0e-5f);
	if (!SkyAtmosphere->SkyLuminanceFactor.Equals(Look.SkyLuminance, 1.0e-3f))
	{
		SkyAtmosphere->SkyLuminanceFactor = Look.SkyLuminance;
		bSkyChanged = true;
	}
	if (bSkyChanged)
	{
		SkyAtmosphere->MarkRenderStateDirty();
	}

	IronEnvironmentDetail::SetCloudCoverage(CloudMaterial.Get(), Look.CloudCoverage);

	UWorld* GameWorld = GetWorld();
	if (SeasonCollection != nullptr && GameWorld != nullptr)
	{
		if (UMaterialParameterCollectionInstance* Season = GameWorld->GetParameterCollectionInstance(SeasonCollection.Get()))
		{
			Season->SetScalarParameterValue(FName(TEXT("Snow")), Look.Snow);
			Season->SetScalarParameterValue(FName(TEXT("Autumn")), Look.Autumn);
			Season->SetScalarParameterValue(FName(TEXT("Wetness")), Look.Wetness);
			// Collections imported before the painted look have no "Painted": their materials stay realistic.
			Season->SetScalarParameterValue(IronEnvironmentDetail::PaintedParameter(), Look.Painted);
		}
	}

	for (int32 Index = SeasonMaterials.Num() - 1; Index >= 0; --Index)
	{
		UMaterialInstanceDynamic* Material = SeasonMaterials[Index].Get();
		if (Material == nullptr)
		{
			SeasonMaterials.RemoveAtSwap(Index);
			continue;
		}
		Material->SetScalarParameterValue(FName(TEXT("Snow")), Look.Snow);
		Material->SetScalarParameterValue(FName(TEXT("Autumn")), Look.Autumn);
		Material->SetScalarParameterValue(FName(TEXT("Wetness")), Look.Wetness);
	}

	FPostProcessSettings& Settings = PostProcess->Settings;
	Settings.ColorSaturation = IronEnvironmentDetail::Uniform4(Look.Saturation);
	Settings.ColorContrast = IronEnvironmentDetail::Uniform4(Look.Contrast);
	Settings.ColorGain = FVector4(Look.Gain.R, Look.Gain.G, Look.Gain.B, 1.0f);
	Settings.WhiteTemp = Look.WhiteTemp;
	Settings.BloomIntensity = Look.BloomIntensity;
	Settings.VignetteIntensity = Look.VignetteIntensity;

	ApplySilk(Look.Painted);
	// The look scales the tilt-shift (CurrentLook is what the depth of field reads).
	ApplyDepthOfField();
}

void AIronEnvironment::UpdateSunRotation(float ElevationDegrees, float LookBearingDegrees)
{
	// Bearing B is where the light comes from (0 = north = -Y, 90 = east = +X); the light travels the other way.
	const float Bearing = SunBearingOverride >= 0.0f ? SunBearingOverride : LookBearingDegrees;
	const double BearingRadians = FMath::DegreesToRadians(static_cast<double>(Bearing));
	const double TowardSunX = FMath::Sin(BearingRadians);
	const double TowardSunY = -FMath::Cos(BearingRadians);
	const double LightYaw = FMath::RadiansToDegrees(FMath::Atan2(-TowardSunY, -TowardSunX));
	Sun->SetWorldRotation(FRotator(-static_cast<double>(ElevationDegrees), LightYaw, 0.0));
}

void AIronEnvironment::SetQuality(int32 Level)
{
	QualityLevel = FMath::Clamp(Level, 0, 3);
	if (HasActorBegunPlay())
	{
		ApplyQuality();
	}
}

void AIronEnvironment::ApplyQuality()
{
	const bool bLumen = QualityLevel >= 1;
	const bool bRealistic = LookStyle == EIronLook::Realistic;
	FPostProcessSettings& Settings = PostProcess->Settings;
	Settings.DynamicGlobalIlluminationMethod = bLumen ? EDynamicGlobalIlluminationMethod::Lumen : EDynamicGlobalIlluminationMethod::None;
	Settings.ReflectionMethod = bLumen ? EReflectionMethod::Lumen : EReflectionMethod::ScreenSpace;
	Settings.LumenFinalGatherQuality = QualityLevel >= 3 ? 2.0f : 1.0f;
	Settings.LumenSceneLightingQuality = QualityLevel >= 3 ? 2.0f : 1.0f;
	Settings.LumenReflectionQuality = QualityLevel >= 3 ? 2.0f : 1.0f;

	// The painted sky is bare silk: no clouds (nor their shadows) and no volumetric light shafts, at any quality.
	if (QualityLevel >= 1 && bRealistic)
	{
		EnsureClouds();
	}
	else
	{
		RemoveClouds();
	}
	HeightFog->SetVolumetricFog(QualityLevel >= 2 && bRealistic);
	ApplyDepthOfField();
}

void AIronEnvironment::EnsureClouds()
{
	if (Clouds != nullptr || CloudBaseMaterial == nullptr)
	{
		return;
	}
	// A thin layer at 3.0-4.6 km: above the highest camera (~2.6 km), so clouds never block the view; they show up
	// as drifting shadows on the map, in the sky light and in reflections.
	UVolumetricCloudComponent* NewClouds = NewObject<UVolumetricCloudComponent>(this);
	NewClouds->SetupAttachment(SceneRoot);
	NewClouds->SetLayerBottomAltitude(3.0f);
	NewClouds->SetLayerHeight(1.6f);
	CloudMaterial = UMaterialInstanceDynamic::Create(CloudBaseMaterial.Get(), this);
	if (CloudMaterial != nullptr)
	{
		IronEnvironmentDetail::SetCloudCoverage(CloudMaterial.Get(), CurrentLook.CloudCoverage);
		NewClouds->SetMaterial(CloudMaterial.Get());
	}
	else
	{
		NewClouds->SetMaterial(CloudBaseMaterial.Get());
	}
	NewClouds->RegisterComponent();
	Clouds = NewClouds;
}

void AIronEnvironment::RemoveClouds()
{
	if (Clouds != nullptr)
	{
		Clouds->DestroyComponent();
		Clouds = nullptr;
	}
	CloudMaterial = nullptr;
}

void AIronEnvironment::SetTiltShift(float InFocusDistanceCm, float HorizontalFovDegrees)
{
	FocusDistanceCm = FMath::Max(0.0f, InFocusDistanceCm);
	FocusFovDegrees = FMath::Clamp(HorizontalFovDegrees, 5.0f, 170.0f);
	ApplyDepthOfField();
}

void AIronEnvironment::SetTiltShiftStrength(float Strength)
{
	TiltShiftStrength = FMath::Clamp(Strength, 0.0f, 2.0f);
	ApplyDepthOfField();
}

float AIronEnvironment::GetEffectiveTiltShiftStrength() const
{
	return TiltShiftStrength * FMath::Max(0.0f, CurrentLook.DepthOfFieldScale);
}

void AIronEnvironment::ApplyDepthOfField()
{
	FPostProcessSettings& Settings = PostProcess->Settings;
	const float Strength = GetEffectiveTiltShiftStrength();
	const bool bEnabled = QualityLevel >= 1 && Strength > 0.001f && FocusDistanceCm > 100.0f;
	if (!bEnabled)
	{
		// A focal distance of 0 turns depth of field off.
		Settings.DepthOfFieldFocalDistance = 0.0f;
		return;
	}

	// A real lens focused hundreds of metres away has almost no depth of field. To fake a miniature, solve the thin-lens
	// circle of confusion at infinity, CoC = 0.5 * (f / N) * f / (s - f), for the aperture N that gives a fixed blur
	// fraction of the image: the band around the focus stays sharp, the near and far map soften like a tilt-shift photo.
	const double SensorMm = IronEnvironmentDetail::SensorWidthMm;
	const double HalfFovRadians = FMath::DegreesToRadians(static_cast<double>(FocusFovDegrees) * 0.5);
	const double FocalLengthMm = 0.5 * SensorMm / FMath::Tan(HalfFovRadians);
	const double FocusMm = static_cast<double>(FocusDistanceCm) * 10.0;
	const double CocFraction = IronEnvironmentDetail::TiltShiftInfinityCoc * static_cast<double>(Strength);
	const double Fstop = 0.5 * FocalLengthMm * FocalLengthMm / (FMath::Max(1.0, FocusMm - FocalLengthMm) * SensorMm * CocFraction);

	Settings.DepthOfFieldFocalDistance = FocusDistanceCm;
	Settings.DepthOfFieldFstop = static_cast<float>(FMath::Clamp(Fstop, 0.0001, 32.0));
	Settings.DepthOfFieldSensorWidth = static_cast<float>(SensorMm);
	// Only the mobile/Gaussian DOF reads the focal region; a small in-focus band matches the desktop look.
	Settings.DepthOfFieldFocalRegion = FocusDistanceCm * 0.08f;
}

void AIronEnvironment::SetInkStrength(float Strength)
{
	InkStrength = FMath::Clamp(Strength, 0.0f, 1.0f);
	ApplyInk();
}

void AIronEnvironment::ApplyInk()
{
	if (InkMaterial == nullptr)
	{
		return;
	}
	// The renderer applies a material blendable fully whenever its weight is above 0 (a weight below 1 only blends
	// an instance's parameters toward its parent's), so the weight switches the pass and "Strength" fades it.
	const bool bInkOn = InkStrength > 0.001f;
	if (InkInstance != nullptr)
	{
		InkInstance->SetScalarParameterValue(IronEnvironmentDetail::PassStrengthParameter(), InkBaseStrength * InkStrength);
	}
	const UObject* InkObject = InkInstance != nullptr ? static_cast<const UObject*>(InkInstance.Get()) : static_cast<const UObject*>(InkMaterial.Get());
	SetBlendableWeight(InkObject, bInkOn ? 1.0f : 0.0f);
}

void AIronEnvironment::ApplySilk(float Strength)
{
	if (SilkMaterial == nullptr)
	{
		return;
	}
	const float Clamped = FMath::Clamp(Strength, 0.0f, 1.0f);
	if (FMath::IsNearlyEqual(Clamped, AppliedSilkStrength, 1.0e-3f))
	{
		return;
	}
	AppliedSilkStrength = Clamped;
	if (SilkInstance != nullptr)
	{
		SilkInstance->SetScalarParameterValue(IronEnvironmentDetail::PassStrengthParameter(), Clamped);
	}
	else if (Clamped < 0.999f && Clamped > 0.001f)
	{
		// Without a dynamic instance the pass can only be fully on or off.
		return;
	}
	const UObject* SilkObject = SilkInstance != nullptr ? static_cast<const UObject*>(SilkInstance.Get()) : static_cast<const UObject*>(SilkMaterial.Get());
	SetBlendableWeight(SilkObject, Clamped > 0.001f ? 1.0f : 0.0f);
}

void AIronEnvironment::SetExposureBias(float Bias)
{
	ExposureBias = FMath::Clamp(Bias, -6.0f, 6.0f);
	PostProcess->Settings.AutoExposureBias = ExposureBias;
}

void AIronEnvironment::SetSunBearing(float BearingDegrees)
{
	SunBearingOverride = BearingDegrees >= 0.0f ? FMath::Fmod(BearingDegrees, 360.0f) : -1.0f;
	RefreshSun();
}

void AIronEnvironment::RefreshSun()
{
	UpdateSunRotation(CurrentLook.SunElevationDegrees, CurrentLook.SunBearingDegrees);
}

void AIronEnvironment::RegisterSeasonMaterial(UMaterialInstanceDynamic* Material)
{
	if (Material == nullptr)
	{
		return;
	}
	for (const TWeakObjectPtr<UMaterialInstanceDynamic>& Existing : SeasonMaterials)
	{
		if (Existing.Get() == Material)
		{
			return;
		}
	}
	SeasonMaterials.Add(Material);
	Material->SetScalarParameterValue(FName(TEXT("Snow")), CurrentLook.Snow);
	Material->SetScalarParameterValue(FName(TEXT("Autumn")), CurrentLook.Autumn);
	Material->SetScalarParameterValue(FName(TEXT("Wetness")), CurrentLook.Wetness);
}
