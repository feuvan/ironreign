#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "IronReignWorldStateSubsystem.generated.h"

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWorldDayAdvanced, int32, NewDay);

UCLASS()
class IRONREIGN_API UIronReignWorldStateSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	UFUNCTION(BlueprintPure, Category = "World State")
	int32 GetCurrentDay() const { return CurrentDay; }

	UFUNCTION(BlueprintCallable, Category = "World State")
	void AdvanceDays(int32 Days = 1);

	UPROPERTY(BlueprintAssignable, Category = "World State")
	FOnWorldDayAdvanced OnWorldDayAdvanced;

private:
	UPROPERTY()
	int32 CurrentDay = 1;
};
