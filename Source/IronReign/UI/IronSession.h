#pragma once

#include "CoreMinimal.h"
#include "Delegates/Delegate.h"
#include "Misc/DateTime.h"
#include "Sim/IronGame.h"
#include "UObject/WeakObjectPtr.h"
#include "UObject/WeakObjectPtrTemplates.h"

class UWorld;

/**
 * How the campaign map and the battles are presented (Settings.json "presentation": "auto" / "3d" / "2d").
 * The real-time 3D scenes (Source/IronReign/World, docs/DESIGN.md section 12) need the imported assets; without them
 * every mode shows the 2D painted map and hex board.
 */
enum class EIronPresentationMode : uint8
{
	/** The 3D scenes when their assets are available (default). */
	Auto,
	/** The 3D scenes (the 2D views only while the scene loads or when the assets are missing). */
	ThreeD,
	/** Always the 2D painted map and hex board. */
	TwoD
};

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
 * Owns the running campaign (IronSim::FGame), scenario discovery, save slots, language and user settings (including
 * the graphics options of the 3D presentation), and knows the world the 3D scenes live in.
 * Created by UIronReignWorldStateSubsystem and shared by every Slate screen.
 *
 * Files:
 *   Content/Data/Scenarios/<name>.json            scenarios
 *   Content/Data/Localization/<culture>/<table>.json  string tables (Strings.json + Scenario_<key>.json)
 *   <ProjectSaved>/SaveGames/IronReign_<slot>.json save games (slot 0 = autosave)
 *   <ProjectSaved>/IronReign/Settings.json        culture + options (speeds, volumes, graphics)
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
	/**
	 * Music and sound-effect volumes, linear 0..1. Applied to FIronAudio immediately (also on load).
	 * bPersist = false skips writing Settings.json, e.g. while a volume slider is being dragged.
	 */
	float GetMusicVolume() const { return MusicVolume; }
	void SetMusicVolume(float Value, bool bPersist = true);
	float GetSfxVolume() const { return SfxVolume; }
	void SetSfxVolume(float Value, bool bPersist = true);

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

	// ----- Graphics options (3D presentation integration; persisted in Settings.json) -----
	EIronPresentationMode GetPresentationMode() const { return PresentationMode; }
	void SetPresentationMode(EIronPresentationMode Mode);
	/** 0 Low, 1 Medium, 2 High (default), 3 Epic: the quality levels of AIronWorldMap3D / AIronBattleBoard3D / AIronEnvironment. */
	int32 GetGraphicsQuality() const { return GraphicsQuality; }
	void SetGraphicsQuality(int32 Level);
	/** Tilt-shift depth of field of the 3D scenes (AIronEnvironment::SetTiltShiftStrength 1 / 0). */
	bool IsTiltShiftEnabled() const { return bTiltShift; }
	void SetTiltShiftEnabled(bool bEnabled);
	/** Ink outline post-process of the 3D scenes (AIronEnvironment::SetInkStrength 1 / 0). */
	bool IsInkOutlinesEnabled() const { return bInkOutlines; }
	void SetInkOutlinesEnabled(bool bEnabled);
	/** Broadcast after any graphics option changed. AIronReignPlayerController applies them to the 3D scenes. */
	FSimpleMulticastDelegate OnGraphicsChanged;
	/** Incremented by every graphics option change (cheap change detection for per-frame code). */
	int32 GetGraphicsRevision() const { return GraphicsRevision; }

	/** False in the 2D presentation mode. */
	bool Allows3D() const { return PresentationMode != EIronPresentationMode::TwoD; }
	/** AIronWorldMap3D::AreAssetsAvailable(), cached (a negative answer is re-checked at most every 30 seconds). */
	bool Is3DMapAvailable() const;
	/** AIronBattleBoard3D::AreAssetsAvailable(), cached the same way. */
	bool Is3DBattleAvailable() const;
	/** The strategy map is presented in 3D: Allows3D() and Is3DMapAvailable(). */
	bool Uses3DMap() const { return Allows3D() && Is3DMapAvailable(); }
	/** Battles are presented in 3D: Allows3D() and Is3DBattleAvailable(). */
	bool Uses3DBattle() const { return Allows3D() && Is3DBattleAvailable(); }

	// ----- Presentation context -----
	/** World that hosts the 3D scenes and the game viewport (set by UIronReignWorldStateSubsystem; weakly held). */
	void SetPresentationWorld(UWorld* InWorld);
	UWorld* GetPresentationWorld() const;
	/**
	 * True while the game viewport renders the world, i.e. a 3D scene (strategy map or battle board) is on screen behind
	 * the Slate screens; they must not paint an opaque backdrop over it then.
	 */
	bool IsWorldRendered() const;
	/** Incremented whenever the campaign is replaced (new game, load, end): per-campaign presentation state is rebuilt. */
	int32 GetCampaignSerial() const { return CampaignSerial; }

private:
	void LoadSettings();
	void SaveSettings() const;
	/** Pushes MusicVolume / SfxVolume to FIronAudio. */
	void ApplyAudioVolumes() const;
	void LoadStringTables();
	static FString SaveSlotPath(int32 Slot);
	/** Bumps the graphics revision, saves the settings and broadcasts OnGraphicsChanged. */
	void CommitGraphicsChange();

	IronSim::FGame Campaign;
	bool bHasGame = false;
	FString Culture = TEXT("en");
	float DaysPerSecond = 6.0f;
	float BattleStepSeconds = 0.35f;
	float MusicVolume = 0.7f;
	float SfxVolume = 0.8f;

	EIronPresentationMode PresentationMode = EIronPresentationMode::Auto;
	int32 GraphicsQuality = 2;
	bool bTiltShift = true;
	bool bInkOutlines = false;
	int32 GraphicsRevision = 0;
	int32 CampaignSerial = 0;
	TWeakObjectPtr<UWorld> PresentationWorld;

	/** Asset availability caches (see Is3DMapAvailable): answer and the time (FPlatformTime::Seconds) of the check. */
	mutable bool bMapAssetsAvailable = false;
	mutable bool bBattleAssetsAvailable = false;
	mutable double MapAssetsCheckedAt = -1.0;
	mutable double BattleAssetsCheckedAt = -1.0;
};
