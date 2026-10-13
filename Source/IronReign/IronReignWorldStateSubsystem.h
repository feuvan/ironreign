#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "IronReignWorldStateSubsystem.generated.h"

class FIronSession;

DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FOnWorldDayAdvanced, int32, NewDay);

/**
 * Owns the FIronSession (and through it the IronSim::FGame campaign) for game and PIE worlds.
 * Created before any actor's BeginPlay, so AIronReignPlayerController can hand the session to the UI.
 */
UCLASS()
class IRONREIGN_API UIronReignWorldStateSubsystem : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	/** The campaign session shared by every Slate screen (valid between Initialize and Deinitialize). */
	TSharedPtr<FIronSession> GetSession() const { return Session; }

	/** Free-running day counter kept for Blueprint users; independent of the campaign calendar. */
	UFUNCTION(BlueprintPure, Category = "World State")
	int32 GetCurrentDay() const { return CurrentDay; }

	UFUNCTION(BlueprintCallable, Category = "World State")
	void AdvanceDays(int32 Days = 1);

	UPROPERTY(BlueprintAssignable, Category = "World State")
	FOnWorldDayAdvanced OnWorldDayAdvanced;

protected:
	/** Only game and PIE worlds run a campaign (no editor preview worlds). */
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override;

private:
	UPROPERTY()
	int32 CurrentDay = 1;

	TSharedPtr<FIronSession> Session;
};
