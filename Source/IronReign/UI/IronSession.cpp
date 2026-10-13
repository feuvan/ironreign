#include "UI/IronSession.h"

#include "IronReignLog.h"
#include "UI/IronStyle.h"
#include "UI/IronUI.h"

#include "HAL/FileManager.h"
#include "HAL/PlatformMisc.h"
#include "HAL/PlatformTime.h"
#include "Internationalization/Culture.h"
#include "Internationalization/Internationalization.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

#include <string>

DEFINE_LOG_CATEGORY(LogIronReign);

namespace IronSessionDetail
{
	FString SettingsFilePath()
	{
		return FPaths::ProjectSavedDir() / TEXT("IronReign") / TEXT("Settings.json");
	}

	FString LocalizationDir(const FString& CultureFolder)
	{
		return FIronSession::DataDir() / TEXT("Localization") / CultureFolder;
	}

	FString DisplayPath(const FString& Path)
	{
		return FPaths::ConvertRelativePathToFull(Path);
	}

	/** UTF-8 bytes (optional BOM) to a std::string for IronSim::FJson. */
	std::string BytesToUtf8(const TArray<uint8>& Bytes)
	{
		int32 Offset = 0;
		if (Bytes.Num() >= 3 && Bytes[0] == 0xEF && Bytes[1] == 0xBB && Bytes[2] == 0xBF)
		{
			Offset = 3;
		}
		if (Bytes.Num() <= Offset)
		{
			return std::string();
		}
		return std::string(reinterpret_cast<const char*>(Bytes.GetData()) + Offset, static_cast<size_t>(Bytes.Num() - Offset));
	}

	bool WriteUtf8File(const FString& Path, const std::string& Utf8Text, FText& OutError)
	{
		IFileManager::Get().MakeDirectory(*FPaths::GetPath(Path), true);
		const FString Contents = IronUI::ToFString(Utf8Text);
		if (!FFileHelper::SaveStringToFile(Contents, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM))
		{
			OutError = IronUI::LocF("ui.error.writeFile", "Could not write the file {file}.", {{"file", IronUI::ToStd(DisplayPath(Path))}});
			return false;
		}
		return true;
	}

	/** Culture of the operating system mapped to a supported culture. */
	FString DetectDefaultCulture()
	{
		FString Detected = FIronSession::NormalizeCulture(FInternationalization::Get().GetCurrentCulture()->GetName());
		if (Detected.IsEmpty() || Detected == TEXT("en"))
		{
			// The ICU culture falls back to English when the game ships without ICU data for the OS language.
			const FString FromPlatform = FIronSession::NormalizeCulture(FPlatformMisc::GetDefaultLocale());
			if (!FromPlatform.IsEmpty())
			{
				Detected = FromPlatform;
			}
		}
		return Detected.IsEmpty() ? FString(TEXT("en")) : Detected;
	}

	/** "Iron Banner - Year 213, Month 4" from a save file's session block (faction name through the string tables). */
	FText SaveSummary(const IronSim::FJson& Save)
	{
		const IronSim::FJson& SessionJson = Save.Get("session");
		const std::string PlayerKey = SessionJson.GetString("player");
		std::string FactionName = PlayerKey;
		for (const IronSim::FJson& FactionJson : Save.Get("factions").Items())
		{
			if (FactionJson.GetString("key") == PlayerKey)
			{
				FactionName = FactionJson.GetString("name", PlayerKey);
				break;
			}
		}
		const std::string NameKey = "faction." + PlayerKey + ".name";
		if (const std::string* Translated = IronSim::FLocale::Active().Find(NameKey))
		{
			FactionName = *Translated;
		}
		const std::string Year = IronSim::ToText(SessionJson.GetInt("year"));
		const std::string Month = IronSim::ToText(SessionJson.GetInt("month"));
		const bool bOver = SessionJson.GetString("phase") == IronSim::EnumName(IronSim::EPhase::GameOver)
			|| SessionJson.GetString("outcome") == IronSim::EnumName(IronSim::EOutcome::Victory)
			|| SessionJson.GetString("outcome") == IronSim::EnumName(IronSim::EOutcome::Defeat);
		if (bOver)
		{
			return IronUI::LocF("ui.saveload.summaryOver", "{faction} - Year {year}, Month {month} (campaign over)", {{"faction", FactionName}, {"year", Year}, {"month", Month}});
		}
		return IronUI::LocF("ui.saveload.summary", "{faction} - Year {year}, Month {month}", {{"faction", FactionName}, {"year", Year}, {"month", Month}});
	}
}

FIronSession::FIronSession()
{
}

FString FIronSession::DataDir()
{
	// Kept relative like the engine's own content paths so lookups also work inside .pak files.
	return FPaths::ProjectContentDir() / TEXT("Data");
}

void FIronSession::Initialize()
{
	LoadSettings();
	LoadStringTables();
	IronStyle::SetSession(AsShared());
	IronStyle::Initialize(Culture);
	UE_LOG(LogIronReign, Log, TEXT("Iron Reign session ready (culture %s, data %s)."), *Culture, *IronSessionDetail::DisplayPath(DataDir()));
}

bool FIronSession::LoadJsonFile(const FString& Path, IronSim::FJson& OutJson, FText& OutError)
{
	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *Path, FILEREAD_Silent))
	{
		OutError = IronUI::LocF("ui.error.readFile", "Could not read the file {file}.", {{"file", IronUI::ToStd(IronSessionDetail::DisplayPath(Path))}});
		return false;
	}
	std::string ParseError;
	if (!IronSim::FJson::Parse(IronSessionDetail::BytesToUtf8(Bytes), OutJson, ParseError))
	{
		OutError = IronUI::LocF("ui.error.parseFile", "The file {file} is damaged: {error}", {{"file", IronUI::ToStd(IronSessionDetail::DisplayPath(Path))}, {"error", ParseError}});
		return false;
	}
	return true;
}

TArray<FIronScenarioEntry> FIronSession::FindScenarios() const
{
	TArray<FIronScenarioEntry> Result;
	const FString Directory = DataDir() / TEXT("Scenarios");
	TArray<FString> Files;
	IFileManager::Get().FindFiles(Files, *(Directory / TEXT("*.json")), true, false);
	Files.Sort();
	for (const FString& File : Files)
	{
		FIronScenarioEntry Entry;
		Entry.Path = Directory / File;
		IronSim::FJson Json;
		FText Error;
		if (!LoadJsonFile(Entry.Path, Json, Error))
		{
			UE_LOG(LogIronReign, Warning, TEXT("Skipping scenario: %s"), *Error.ToString());
			continue;
		}
		if (!IronSim::ReadScenarioInfo(Json, Entry.Info))
		{
			UE_LOG(LogIronReign, Warning, TEXT("Skipping scenario %s: not a valid Iron Reign scenario."), *IronSessionDetail::DisplayPath(Entry.Path));
			continue;
		}
		Result.Add(MoveTemp(Entry));
	}
	return Result;
}

bool FIronSession::StartNewGame(const FString& ScenarioPath, int32 FactionIndex, IronSim::EDifficulty Difficulty, FText& OutError)
{
	IronSim::FJson Scenario;
	if (!LoadJsonFile(ScenarioPath, Scenario, OutError))
	{
		return false;
	}
	const uint64 Seed = static_cast<uint64>(FDateTime::UtcNow().GetTicks()) ^ (FPlatformTime::Cycles64() << 17);
	std::string Error;
	// FGame::NewGame only replaces the state when the scenario loads, so a failure keeps any running campaign intact.
	if (!Campaign.NewGame(Scenario, FactionIndex, Difficulty, static_cast<uint64_t>(Seed), Error))
	{
		OutError = IronUI::LocF("ui.error.newGame", "The campaign could not be started: {error}", {{"error", Error}});
		return false;
	}
	bHasGame = true;
	UE_LOG(LogIronReign, Log, TEXT("New campaign: %s, faction %d, difficulty %s."), *IronSessionDetail::DisplayPath(ScenarioPath), FactionIndex, UTF8_TO_TCHAR(IronSim::EnumName(Difficulty)));
	NotifyStateChanged();
	return true;
}

void FIronSession::EndGame()
{
	bHasGame = false;
	Campaign.State = IronSim::FGameState();
	NotifyStateChanged();
}

FString FIronSession::SaveSlotPath(int32 Slot)
{
	return FPaths::ProjectSavedDir() / TEXT("SaveGames") / FString::Printf(TEXT("IronReign_%d.json"), Slot);
}

bool FIronSession::HasAnySave() const
{
	for (int32 SlotIndex = 0; SlotIndex < SaveSlotCount; ++SlotIndex)
	{
		if (IFileManager::Get().FileExists(*SaveSlotPath(SlotIndex)))
		{
			return true;
		}
	}
	return false;
}

TArray<FIronSaveSlot> FIronSession::ListSaveSlots() const
{
	TArray<FIronSaveSlot> Result;
	const FTimespan UtcToLocal = FDateTime::Now() - FDateTime::UtcNow();
	for (int32 SlotIndex = 0; SlotIndex < SaveSlotCount; ++SlotIndex)
	{
		FIronSaveSlot Entry;
		Entry.Slot = SlotIndex;
		const FString Path = SaveSlotPath(SlotIndex);
		if (IFileManager::Get().FileExists(*Path))
		{
			Entry.bUsed = true;
			Entry.Timestamp = IFileManager::Get().GetTimeStamp(*Path) + UtcToLocal;
			IronSim::FJson Save;
			FText Error;
			if (LoadJsonFile(Path, Save, Error))
			{
				Entry.Summary = IronSessionDetail::SaveSummary(Save);
			}
			else
			{
				Entry.Summary = IronUI::Loc("ui.saveload.damaged", "Damaged save file");
			}
		}
		Result.Add(Entry);
	}
	return Result;
}

bool FIronSession::SaveToSlot(int32 Slot, FText& OutError)
{
	if (Slot < 0 || Slot >= SaveSlotCount)
	{
		OutError = IronUI::Loc("ui.saveload.badSlot", "There is no such save slot.");
		return false;
	}
	if (!bHasGame)
	{
		OutError = IronUI::Loc("ui.saveload.noGame", "There is no campaign to save.");
		return false;
	}
	if (!Campaign.IsPlanning())
	{
		OutError = IronUI::Loc("ui.saveload.notPlanning", "You can only save during the planning phase.");
		return false;
	}
	const std::string Text = Campaign.SaveGame().Write(true);
	if (!IronSessionDetail::WriteUtf8File(SaveSlotPath(Slot), Text, OutError))
	{
		UE_LOG(LogIronReign, Warning, TEXT("Save to slot %d failed: %s"), Slot, *OutError.ToString());
		return false;
	}
	UE_LOG(LogIronReign, Log, TEXT("Saved the campaign to slot %d."), Slot);
	return true;
}

bool FIronSession::LoadFromSlot(int32 Slot, FText& OutError)
{
	if (Slot < 0 || Slot >= SaveSlotCount)
	{
		OutError = IronUI::Loc("ui.saveload.badSlot", "There is no such save slot.");
		return false;
	}
	const FString Path = SaveSlotPath(Slot);
	if (!IFileManager::Get().FileExists(*Path))
	{
		OutError = IronUI::Loc("ui.saveload.emptySlot", "This save slot is empty.");
		return false;
	}
	IronSim::FJson Save;
	if (!LoadJsonFile(Path, Save, OutError))
	{
		return false;
	}
	std::string Error;
	// FGame::LoadGame only replaces the state when the file loads, so a failure keeps the running campaign.
	if (!Campaign.LoadGame(Save, Error))
	{
		OutError = IronUI::LocF("ui.saveload.loadFailed", "The save could not be loaded: {error}", {{"error", Error}});
		UE_LOG(LogIronReign, Warning, TEXT("Load from slot %d failed: %s"), Slot, *OutError.ToString());
		return false;
	}
	bHasGame = true;
	UE_LOG(LogIronReign, Log, TEXT("Loaded the campaign from slot %d."), Slot);
	NotifyStateChanged();
	return true;
}

bool FIronSession::AutoSave()
{
	if (!bHasGame || !Campaign.IsPlanning())
	{
		return false;
	}
	FText Error;
	return SaveToSlot(0, Error);
}

const TArray<FString>& FIronSession::SupportedCultures()
{
	static const TArray<FString> Cultures = {TEXT("en"), TEXT("zh-Hans"), TEXT("zh-Hant"), TEXT("ja"), TEXT("ko")};
	return Cultures;
}

FText FIronSession::CultureDisplayName(const FString& InCulture)
{
	// Native names, written with escapes so the source stays ASCII.
	if (InCulture == TEXT("zh-Hans"))
	{
		return FText::FromString(TEXT("简体中文"));
	}
	if (InCulture == TEXT("zh-Hant"))
	{
		return FText::FromString(TEXT("繁體中文"));
	}
	if (InCulture == TEXT("ja"))
	{
		return FText::FromString(TEXT("日本語"));
	}
	if (InCulture == TEXT("ko"))
	{
		return FText::FromString(TEXT("한국어"));
	}
	return FText::FromString(TEXT("English"));
}

FString FIronSession::NormalizeCulture(const FString& CultureName)
{
	FString Lower = CultureName.ToLower();
	Lower.ReplaceInline(TEXT("_"), TEXT("-"));
	if (Lower.StartsWith(TEXT("zh")))
	{
		if (Lower.Contains(TEXT("hans")))
		{
			return TEXT("zh-Hans");
		}
		if (Lower.Contains(TEXT("hant")) || Lower.Contains(TEXT("-tw")) || Lower.Contains(TEXT("-hk")) || Lower.Contains(TEXT("-mo")))
		{
			return TEXT("zh-Hant");
		}
		return TEXT("zh-Hans");
	}
	if (Lower.StartsWith(TEXT("ja")))
	{
		return TEXT("ja");
	}
	if (Lower.StartsWith(TEXT("ko")))
	{
		return TEXT("ko");
	}
	if (Lower.StartsWith(TEXT("en")))
	{
		return TEXT("en");
	}
	return FString();
}

int32 FIronSession::LoadCultureStrings(const FString& InCulture, TArray<FString>* OutErrors)
{
	IronSim::FLocale& Locale = IronSim::FLocale::Active();
	Locale.Reset(IronUI::ToStd(InCulture));

	TArray<FString> Folders;
	Folders.Add(TEXT("en"));
	if (InCulture != TEXT("en"))
	{
		Folders.Add(InCulture);
	}

	int32 Loaded = 0;
	for (const FString& Folder : Folders)
	{
		const FString Directory = IronSessionDetail::LocalizationDir(Folder);
		TArray<FString> Files;
		IFileManager::Get().FindFiles(Files, *(Directory / TEXT("*.json")), true, false);
		Files.Sort();
		for (const FString& File : Files)
		{
			IronSim::FJson Table;
			FText Error;
			if (LoadJsonFile(Directory / File, Table, Error) && Table.IsObject())
			{
				Locale.AddStrings(Table);
				++Loaded;
				continue;
			}
			const FString Message = Error.IsEmpty() ? FString::Printf(TEXT("String table %s is not a JSON object."), *IronSessionDetail::DisplayPath(Directory / File)) : Error.ToString();
			UE_LOG(LogIronReign, Warning, TEXT("%s"), *Message);
			if (OutErrors)
			{
				OutErrors->Add(Message);
			}
		}
	}
	return Loaded;
}

void FIronSession::LoadStringTables()
{
	const int32 Loaded = LoadCultureStrings(Culture);
	UE_LOG(LogIronReign, Log, TEXT("Loaded %d string tables for culture %s."), Loaded, *Culture);
}

void FIronSession::SetCulture(const FString& NewCulture)
{
	FString Normalized = NormalizeCulture(NewCulture);
	if (Normalized.IsEmpty())
	{
		Normalized = TEXT("en");
	}
	if (Normalized.Equals(Culture, ESearchCase::CaseSensitive))
	{
		return;
	}
	Culture = Normalized;
	LoadStringTables();
	IronStyle::Initialize(Culture);
	SaveSettings();
	OnCultureChanged.Broadcast();
}

void FIronSession::SetDaysPerSecond(float Value)
{
	DaysPerSecond = FMath::Clamp(Value, 0.5f, 60.0f);
	SaveSettings();
}

void FIronSession::SetBattleStepSeconds(float Value)
{
	BattleStepSeconds = FMath::Clamp(Value, 0.02f, 3.0f);
	SaveSettings();
}

void FIronSession::LoadSettings()
{
	Culture = IronSessionDetail::DetectDefaultCulture();
	const FString Path = IronSessionDetail::SettingsFilePath();
	if (!IFileManager::Get().FileExists(*Path))
	{
		return;
	}
	IronSim::FJson SettingsJson;
	FText Error;
	if (!LoadJsonFile(Path, SettingsJson, Error) || !SettingsJson.IsObject())
	{
		UE_LOG(LogIronReign, Warning, TEXT("Ignoring settings: %s"), *Error.ToString());
		return;
	}
	const FString SavedCulture = NormalizeCulture(IronUI::ToFString(SettingsJson.GetString("culture")));
	if (!SavedCulture.IsEmpty())
	{
		Culture = SavedCulture;
	}
	DaysPerSecond = FMath::Clamp(static_cast<float>(SettingsJson.GetNumber("daysPerSecond", DaysPerSecond)), 0.5f, 60.0f);
	BattleStepSeconds = FMath::Clamp(static_cast<float>(SettingsJson.GetNumber("battleStepSeconds", BattleStepSeconds)), 0.02f, 3.0f);
}

void FIronSession::SaveSettings() const
{
	IronSim::FJson SettingsJson = IronSim::FJson::MakeObject();
	SettingsJson.SetString("culture", IronUI::ToStd(Culture));
	SettingsJson.SetNumber("daysPerSecond", DaysPerSecond);
	SettingsJson.SetNumber("battleStepSeconds", BattleStepSeconds);
	FText Error;
	if (!IronSessionDetail::WriteUtf8File(IronSessionDetail::SettingsFilePath(), SettingsJson.Write(true), Error))
	{
		UE_LOG(LogIronReign, Warning, TEXT("%s"), *Error.ToString());
	}
}
