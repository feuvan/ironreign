#pragma once

#include "CoreMinimal.h"
#include "Delegates/Delegate.h"
#include "Misc/DateTime.h"
#include "Sim/IronGame.h"

/** A scenario file found under Content/Data/Scenarios. */
struct FIronScenarioEntry
{
	FString Path;
	IronSim::FScenarioInfo Info;
};

/** One save slot as shown in the save/load dialog. */
struct FIronSaveSlot
{
	int32 Slot = 0;
	bool bUsed = false;
	/** e.g. "Iron Banner - Year 213, Month 4". */
	FText Summary;
	/** Last write time of the save file, in local time. */
	FDateTime Timestamp;
};

/**
 * Owns the running campaign (IronSim::FGame), scenario discovery, save slots, language and user settings.
 * Created by UIronReignWorldStateSubsystem and shared by every Slate screen.
 *
 * Files:
 *   Content/Data/Scenarios/<name>.json            scenarios
 *   Content/Data/Localization/<culture>/<table>.json  string tables (Strings.json + Scenario_<key>.json)
 *   <ProjectSaved>/SaveGames/IronReign_<slot>.json save games (slot 0 = autosave)
 *   <ProjectSaved>/IronReign/Settings.json        culture + options
 */
class IRONREIGN_API FIronSession : public TSharedFromThis<FIronSession>
{
public:
	static constexpr int32 SaveSlotCount = 8;

	FIronSession();

	/** Content/Data directory (absolute). */
	static FString DataDir();
	/** Loads settings and string tables. Call once after construction. */
	void Initialize();

	bool HasGame() const { return bHasGame; }
	IronSim::FGame& Game() { return Campaign; }
	const IronSim::FGame& Game() const { return Campaign; }
	IronSim::FGameState& State() { return Campaign.State; }
	const IronSim::FGameState& State() const { return Campaign.State; }

	TArray<FIronScenarioEntry> FindScenarios() const;
	bool StartNewGame(const FString& ScenarioPath, int32 FactionIndex, IronSim::EDifficulty Difficulty, FText& OutError);
	void EndGame();

	TArray<FIronSaveSlot> ListSaveSlots() const;
	bool SaveToSlot(int32 Slot, FText& OutError);
	bool LoadFromSlot(int32 Slot, FText& OutError);
	/** Writes slot 0. Called at the start of every planning phase. */
	bool AutoSave();

	/** "en", "zh-Hans", "zh-Hant", "ja", "ko". */
	static const TArray<FString>& SupportedCultures();
	/** Native name of a culture for the language menu ("English", "简体中文", "繁體中文", "日本語", "한국어"). */
	static FText CultureDisplayName(const FString& Culture);
	const FString& GetCulture() const { return Culture; }
	/** Loads the culture's string tables into IronSim::FLocale, rebuilds fonts, saves settings, broadcasts OnCultureChanged. */
	void SetCulture(const FString& NewCulture);

	/** Execution playback speed: days per second on the strategy map. */
	float GetDaysPerSecond() const { return DaysPerSecond; }
	void SetDaysPerSecond(float Value);
	/** Seconds per AI action animation in battles. */
	float GetBattleStepSeconds() const { return BattleStepSeconds; }
	void SetBattleStepSeconds(float Value);

	/** Broadcast after any UI-driven change to the game so widgets can refresh. */
	FSimpleMulticastDelegate OnStateChanged;
	void NotifyStateChanged() { OnStateChanged.Broadcast(); }
	/** Broadcast after the language changed; screens rebuild their text. */
	FSimpleMulticastDelegate OnCultureChanged;

	// ----- Additions (UE framework engineer) -----
	/** True if any save slot (including the autosave) holds a file. Cheap: does not parse the saves. */
	bool HasAnySave() const;
	/** Reads a UTF-8 JSON file (BOM tolerated) into the rules engine's DOM. */
	static bool LoadJsonFile(const FString& Path, IronSim::FJson& OutJson, FText& OutError);
	/** Maps any culture name ("zh-CN", "ja_JP", "zh-Hant-TW"...) to a supported culture, or "" if unsupported. */
	static FString NormalizeCulture(const FString& CultureName);
	/**
	 * Resets IronSim::FLocale::Active() to InCulture and loads every .json file in Localization/en, then every .json
	 * file in Localization/<InCulture>. Returns the number of tables loaded; files that fail to parse are
	 * reported in OutErrors (and logged). Does not touch fonts or settings (see SetCulture).
	 */
	static int32 LoadCultureStrings(const FString& InCulture, TArray<FString>* OutErrors = nullptr);

private:
	void LoadSettings();
	void SaveSettings() const;
	void LoadStringTables();
	static FString SaveSlotPath(int32 Slot);

	IronSim::FGame Campaign;
	bool bHasGame = false;
	FString Culture = TEXT("en");
	float DaysPerSecond = 6.0f;
	float BattleStepSeconds = 0.35f;
};
