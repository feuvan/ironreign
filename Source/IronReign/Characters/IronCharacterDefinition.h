#pragma once

#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "GameplayTagContainer.h"
#include "IronCharacterDefinition.generated.h"

USTRUCT(BlueprintType)
struct IRONREIGN_API FIronCharacterAttributes
{
	GENERATED_BODY()

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Attributes", meta = (ClampMin = "1"))
	int32 Martial = 1;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Attributes", meta = (ClampMin = "1"))
	int32 Command = 1;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Attributes", meta = (ClampMin = "1"))
	int32 Strategy = 1;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Attributes", meta = (ClampMin = "1"))
	int32 Politics = 1;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Attributes", meta = (ClampMin = "1"))
	int32 Charm = 1;
};

UCLASS(BlueprintType)
class IRONREIGN_API UIronCharacterDefinition : public UPrimaryDataAsset
{
	GENERATED_BODY()

public:
	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Identity")
	FText DisplayName;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Identity")
	FText Biography;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Identity")
	FGameplayTagContainer CharacterTags;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Attributes")
	FIronCharacterAttributes BaseAttributes;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Progression", meta = (ClampMin = "0"))
	int32 StartingLevel = 1;

	UPROPERTY(EditDefaultsOnly, BlueprintReadOnly, Category = "Progression", meta = (ClampMin = "0"))
	int32 StartingGold = 0;
};
