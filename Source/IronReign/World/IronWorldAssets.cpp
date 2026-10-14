#include "World/IronWorldAssets.h"

#include "Sim/IronJson.h"
#include "Sim/IronState.h"
#include "World/IronAssetManifest.h"
#include "World/IronWorldMath.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/Material.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Materials/MaterialParameterCollection.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "UObject/UObjectGlobals.h"

#include <string>

DEFINE_LOG_CATEGORY(LogIronWorld);

namespace IronWorldAssetsDetail
{
	template <typename AssetType>
	AssetType* LoadQuiet(const FString& ObjectPath)
	{
		return LoadObject<AssetType>(nullptr, *ObjectPath, nullptr, LOAD_NoWarn | LOAD_Quiet);
	}

	/** True for the faction-colour slots of an imported model (DESIGN.md 12.3). */
	bool IsTintSlot(const FStaticMaterial& Slot, UMaterialInterface* SlotMaterial)
	{
		if (Slot.MaterialSlotName.ToString().StartsWith(IronWorld::TintParameter, ESearchCase::IgnoreCase))
		{
			return true;
		}
		const UMaterial* Base = SlotMaterial != nullptr ? SlotMaterial->GetBaseMaterial() : nullptr;
		return Base != nullptr && Base->GetName() == TEXT("M_IronTint");
	}

	IronWorld::FModelParams ReadModelParams()
	{
		IronWorld::FModelParams Params;
		const FString Path = IronWorld::Art3DDir() / TEXT("Models.json");
		if (!FPaths::FileExists(Path))
		{
			UE_LOG(LogIronWorld, Log, TEXT("No %s; using default model parameters."), *Path);
			return Params;
		}
		IronSim::FJson Root;
		FString Error;
		if (!IronWorld::ReadJsonFile(Path, Root, Error))
		{
			UE_LOG(LogIronWorld, Warning, TEXT("Models.json: %s"), *Error);
			return Params;
		}
		Params.FrontYawDegrees = Root.GetNumber("frontYaw", Params.FrontYawDegrees);
		const IronSim::FJson& Models = Root.Get("models");
		if (Models.IsObject())
		{
			for (const std::pair<std::string, IronSim::FJson>& Member : Models.Members())
			{
				const double Scale = Member.second.GetNumber("scale", 1.0);
				Params.Scales.Add(FString(UTF8_TO_TCHAR(Member.first.c_str())), Scale > 0.0 ? Scale : 1.0);
			}
		}
		return Params;
	}
}

namespace IronWorld
{
	FString Art3DDir()
	{
		return FPaths::ProjectContentDir() / TEXT("Data") / TEXT("Art3D");
	}

	FString ModelObjectPath(const FString& ModelName)
	{
		return FString::Printf(TEXT("/Game/IronReign/Models/SM_%s.SM_%s"), *ModelName, *ModelName);
	}

	FString MaterialObjectPath(const FString& MaterialName)
	{
		return FString::Printf(TEXT("/Game/IronReign/Materials/%s.%s"), *MaterialName, *MaterialName);
	}

	UStaticMesh* LoadModel(const FString& ModelName)
	{
		return IronWorldAssetsDetail::LoadQuiet<UStaticMesh>(ModelObjectPath(ModelName));
	}

	UMaterialInterface* LoadMaterial(const FString& MaterialName)
	{
		return IronWorldAssetsDetail::LoadQuiet<UMaterialInterface>(MaterialObjectPath(MaterialName));
	}

	UStaticMesh* LoadEngineMesh(const TCHAR* ObjectPath)
	{
		return IronWorldAssetsDetail::LoadQuiet<UStaticMesh>(FString(ObjectPath));
	}

	UMaterialInterface* LoadEngineMaterial(const TCHAR* ObjectPath)
	{
		return IronWorldAssetsDetail::LoadQuiet<UMaterialInterface>(FString(ObjectPath));
	}

	UMaterialParameterCollection* LoadSeasonCollection()
	{
		return IronWorldAssetsDetail::LoadQuiet<UMaterialParameterCollection>(MaterialObjectPath(TEXT("MPC_IronSeason")));
	}

	UStaticMesh* LoadPlaneMesh()
	{
		UStaticMesh* Plane = LoadModel(TEXT("IronPlane"));
		return Plane != nullptr ? Plane : LoadEngineMesh(EnginePlanePath);
	}

	UStaticMesh* LoadCubeMesh()
	{
		UStaticMesh* Cube = LoadModel(TEXT("IronCube"));
		return Cube != nullptr ? Cube : LoadEngineMesh(EngineCubePath);
	}

	UIronAssetManifest* LoadAssetManifest()
	{
		return IronWorldAssetsDetail::LoadQuiet<UIronAssetManifest>(FString(TEXT("/Game/IronReign/IronReignAssetVersion.IronReignAssetVersion")));
	}

	bool ReadJsonFile(const FString& Path, IronSim::FJson& OutJson, FString& OutError)
	{
		TArray<uint8> Bytes;
		if (!FFileHelper::LoadFileToArray(Bytes, *Path, FILEREAD_Silent))
		{
			OutError = FString::Printf(TEXT("could not read %s"), *Path);
			return false;
		}
		int32 Start = 0;
		if (Bytes.Num() >= 3 && Bytes[0] == 0xEF && Bytes[1] == 0xBB && Bytes[2] == 0xBF)
		{
			Start = 3;
		}
		const std::string Text(reinterpret_cast<const char*>(Bytes.GetData()) + Start, static_cast<size_t>(Bytes.Num() - Start));
		std::string ParseError;
		if (!IronSim::FJson::Parse(Text, OutJson, ParseError))
		{
			OutError = FString::Printf(TEXT("%s is not valid JSON: %s"), *Path, UTF8_TO_TCHAR(ParseError.c_str()));
			return false;
		}
		return true;
	}

	const FModelParams& GetModelParams()
	{
		static FModelParams Cached = IronWorldAssetsDetail::ReadModelParams();
		return Cached;
	}

	FLinearColor FactionColor(const IronSim::FGameState& State, int32 FactionIndex)
	{
		if (FactionIndex >= 0 && FactionIndex < static_cast<int32>(State.Factions.size()))
		{
			return ColorFromRGB(static_cast<uint32>(State.Factions[static_cast<size_t>(FactionIndex)].Color));
		}
		return ColorFromRGB(IndependentRGB);
	}

	UMaterialInstanceDynamic* ApplyTint(UStaticMeshComponent* Component, const FLinearColor& Color, UMaterialInstanceDynamic* Existing, UMaterialInterface* TintBase)
	{
		const FName TintName(TintParameter);
		const UStaticMesh* Mesh = Component != nullptr ? Component->GetStaticMesh() : nullptr;
		if (Existing != nullptr)
		{
			Existing->SetVectorParameterValue(TintName, Color);
			// Tint slots with a base texture of their own got their own instance from the first call.
			const int32 SlotCount = Mesh != nullptr ? Mesh->GetStaticMaterials().Num() : 0;
			for (int32 SlotIndex = 0; SlotIndex < SlotCount; ++SlotIndex)
			{
				UMaterialInstanceDynamic* SlotInstance = Cast<UMaterialInstanceDynamic>(Component->GetMaterial(SlotIndex));
				if (SlotInstance != nullptr && SlotInstance != Existing && IronWorldAssetsDetail::IsTintSlot(Mesh->GetStaticMaterials()[SlotIndex], SlotInstance))
				{
					SlotInstance->SetVectorParameterValue(TintName, Color);
				}
			}
			return Existing;
		}
		if (Mesh == nullptr)
		{
			return nullptr;
		}
		UMaterialInstanceDynamic* FirstInstance = nullptr;
		// One instance per distinct slot material, so every Tint slot keeps its own base texture.
		TMap<UMaterialInterface*, UMaterialInstanceDynamic*> InstanceByParent;
		const TArray<FStaticMaterial>& Slots = Mesh->GetStaticMaterials();
		for (int32 SlotIndex = 0; SlotIndex < Slots.Num(); ++SlotIndex)
		{
			UMaterialInterface* SlotMaterial = Component->GetMaterial(SlotIndex);
			if (!IronWorldAssetsDetail::IsTintSlot(Slots[SlotIndex], SlotMaterial))
			{
				continue;
			}
			UMaterialInterface* Parent = SlotMaterial != nullptr ? SlotMaterial : TintBase;
			if (Parent == nullptr)
			{
				continue;
			}
			UMaterialInstanceDynamic* Instance = nullptr;
			if (UMaterialInstanceDynamic* const* Found = InstanceByParent.Find(Parent))
			{
				Instance = *Found;
			}
			else
			{
				Instance = UMaterialInstanceDynamic::Create(Parent, Component);
				if (Instance == nullptr)
				{
					continue;
				}
				Instance->SetVectorParameterValue(TintName, Color);
				InstanceByParent.Add(Parent, Instance);
			}
			if (FirstInstance == nullptr)
			{
				FirstInstance = Instance;
			}
			Component->SetMaterial(SlotIndex, Instance);
		}
		return FirstInstance;
	}

	UMaterialInstanceDynamic* MakeColoredMaterial(UMaterialInterface* Base, UObject* Outer, const FLinearColor& Color)
	{
		if (Base == nullptr)
		{
			return nullptr;
		}
		UMaterialInstanceDynamic* Instance = UMaterialInstanceDynamic::Create(Base, Outer);
		if (Instance != nullptr)
		{
			Instance->SetVectorParameterValue(FName(ColorParameter), Color);
		}
		return Instance;
	}
}
