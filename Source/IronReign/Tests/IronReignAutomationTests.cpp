#include "CoreMinimal.h"
#include "Misc/AutomationTest.h"

#if WITH_DEV_AUTOMATION_TESTS

#include "Sim/IronGame.h"
#include "Sim/IronLocale.h"
#include "UI/IronAssets.h"
#include "UI/IronSession.h"
#include "UI/IronUI.h"

#include "Engine/Texture2D.h"
#include "HAL/FileManager.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"

#include <string>

namespace IronReignTestDetail
{
	constexpr int32 MonthsToPlay = 6;
	constexpr uint64_t CampaignSeed = 0x1A2B3C4D5E6F7788ull;

	FString BrokenMandatePath()
	{
		return FIronSession::DataDir() / TEXT("Scenarios") / TEXT("BrokenMandate.json");
	}

	/** Answers every pending event with its first available choice and releases every prisoner. */
	void ResolvePlanningDecisions(IronSim::FGame& Game)
	{
		for (int32 EventGuard = 0; EventGuard < 64; ++EventGuard)
		{
			const IronSim::FPendingEvent* Pending = Game.CurrentEvent();
			if (Pending == nullptr)
			{
				break;
			}
			int32 Choice = 0;
			const int32 ChoiceCount = static_cast<int32>(Pending->Choices.size());
			for (int32 ChoiceIndex = 0; ChoiceIndex < ChoiceCount; ++ChoiceIndex)
			{
				if (Game.CanChoose(ChoiceIndex))
				{
					Choice = ChoiceIndex;
					break;
				}
			}
			Game.ChooseEventOption(Choice);
		}

		for (int32 PrisonerGuard = 0; PrisonerGuard < 64 && !Game.State.PendingPrisoners.empty(); ++PrisonerGuard)
		{
			const int Prisoner = Game.State.PendingPrisoners.front();
			std::string Message;
			if (!Game.DecidePrisoner(Prisoner, IronSim::EPrisonerDecision::Release, Message))
			{
				break;
			}
		}
	}

	/** Plans nothing, ends the turn and plays the month; player battles are auto-resolved. False when the game ended. */
	bool PlayOneMonth(IronSim::FGame& Game, int32& InOutPlayerBattles)
	{
		ResolvePlanningDecisions(Game);
		if (!Game.IsPlanning())
		{
			return false;
		}
		Game.EndPlanning();
		for (int32 StepGuard = 0; StepGuard < 2000; ++StepGuard)
		{
			switch (Game.Step())
			{
			case IronSim::EStepResult::DayAdvanced:
				break;
			case IronSim::EStepResult::PlayerBattle:
				++InOutPlayerBattles;
				Game.AutoResolvePlayerBattle();
				break;
			case IronSim::EStepResult::MonthEnded:
				return true;
			case IronSim::EStepResult::Idle:
			case IronSim::EStepResult::GameOver:
				return false;
			}
		}
		return false;
	}
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronReignCampaignTest, "IronReign.Sim.Campaign", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronReignCampaignTest::RunTest(const FString& /*Parameters*/)
{
	const FString ScenarioPath = IronReignTestDetail::BrokenMandatePath();
	if (!FPaths::FileExists(ScenarioPath))
	{
		AddError(FString::Printf(TEXT("Missing scenario %s"), *FPaths::ConvertRelativePathToFull(ScenarioPath)));
		return false;
	}

	// Scenario discovery and the session's new-game path.
	const TSharedRef<FIronSession> Session = MakeShared<FIronSession>();
	const TArray<FIronScenarioEntry> Scenarios = Session->FindScenarios();
	const FIronScenarioEntry* BrokenMandate = Scenarios.FindByPredicate([](const FIronScenarioEntry& Candidate)
	{
		return Candidate.Info.Key == "broken_mandate";
	});
	if (!TestNotNull(TEXT("FindScenarios lists BrokenMandate.json"), BrokenMandate))
	{
		return false;
	}
	TestTrue(TEXT("The scenario has several factions"), BrokenMandate->Info.Factions.size() >= 2);

	FText StartError;
	const bool bStarted = Session->StartNewGame(BrokenMandate->Path, 0, IronSim::EDifficulty::Normal, StartError);
	TestTrue(FString::Printf(TEXT("FIronSession::StartNewGame succeeds (%s)"), *StartError.ToString()), bStarted);
	TestTrue(TEXT("The session has a game"), Session->HasGame());
	TestTrue(TEXT("A new game starts in the planning phase"), Session->Game().IsPlanning());

	// Deterministic campaign straight through FGame.
	IronSim::FJson Scenario;
	FText LoadError;
	if (!FIronSession::LoadJsonFile(ScenarioPath, Scenario, LoadError))
	{
		AddError(LoadError.ToString());
		return false;
	}
	IronSim::FGame Game;
	std::string Error;
	if (!Game.NewGame(Scenario, 0, IronSim::EDifficulty::Normal, IronReignTestDetail::CampaignSeed, Error))
	{
		AddError(FString::Printf(TEXT("FGame::NewGame failed: %s"), *IronUI::ToFString(Error)));
		return false;
	}

	const int32 StartStamp = Game.State.Year * 12 + Game.State.Month;
	int32 PlayerBattles = 0;
	int32 MonthsPlayed = 0;
	while (MonthsPlayed < IronReignTestDetail::MonthsToPlay && IronReignTestDetail::PlayOneMonth(Game, PlayerBattles))
	{
		++MonthsPlayed;
	}
	AddInfo(FString::Printf(TEXT("Played %d months (%d player battles auto-resolved); now %s."), MonthsPlayed, PlayerBattles, *IronUI::ToFString(Game.DateText())));

	if (Game.State.Phase != IronSim::EPhase::GameOver)
	{
		TestEqual(TEXT("Every month ended normally"), MonthsPlayed, IronReignTestDetail::MonthsToPlay);
		TestTrue(TEXT("The calendar advanced"), Game.State.Year * 12 + Game.State.Month > StartStamp);
	}
	for (const IronSim::FCity& City : Game.State.Cities)
	{
		if (City.Troops < 0 || City.Gold < 0 || City.Food < 0 || City.Order < 0 || City.Order > 100)
		{
			AddError(FString::Printf(TEXT("City %s has invalid values (troops %d, gold %d, food %d, order %d)."), *IronUI::ToFString(City.Key), City.Troops, City.Gold, City.Food, City.Order));
			break;
		}
	}

	// Save -> JSON text -> load round trip.
	IronReignTestDetail::ResolvePlanningDecisions(Game);
	const std::string SavedText = Game.SaveGame().Write(true);
	IronSim::FJson Parsed;
	if (!TestTrue(TEXT("The save parses"), IronSim::FJson::Parse(SavedText, Parsed, Error)))
	{
		return false;
	}
	IronSim::FGame Reloaded;
	if (!TestTrue(FString::Printf(TEXT("The save loads (%s)"), *IronUI::ToFString(Error)), Reloaded.LoadGame(Parsed, Error)))
	{
		return false;
	}
	TestEqual(TEXT("Year survives the round trip"), Reloaded.State.Year, Game.State.Year);
	TestEqual(TEXT("Month survives the round trip"), Reloaded.State.Month, Game.State.Month);
	TestEqual(TEXT("Player faction survives the round trip"), Reloaded.State.PlayerFaction, Game.State.PlayerFaction);
	TestEqual(TEXT("City count survives the round trip"), static_cast<int32>(Reloaded.State.Cities.size()), static_cast<int32>(Game.State.Cities.size()));
	TestEqual(TEXT("Officer count survives the round trip"), static_cast<int32>(Reloaded.State.Officers.size()), static_cast<int32>(Game.State.Officers.size()));
	TestEqual(TEXT("Army count survives the round trip"), static_cast<int32>(Reloaded.State.Armies.size()), static_cast<int32>(Game.State.Armies.size()));
	if (Reloaded.SaveGame().Write(true) != SavedText)
	{
		AddWarning(TEXT("Save -> load -> save is not byte-identical."));
	}

	// The same UTF-8 file path FIronSession uses for save slots (written to an automation scratch folder).
	const FString TempPath = FPaths::ProjectSavedDir() / TEXT("Automation") / TEXT("IronReign") / TEXT("RoundTrip.json");
	IFileManager::Get().MakeDirectory(*FPaths::GetPath(TempPath), true);
	TestTrue(TEXT("The save is written as UTF-8"), FFileHelper::SaveStringToFile(IronUI::ToFString(SavedText), *TempPath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM));
	IronSim::FJson FromDisk;
	FText DiskError;
	if (TestTrue(TEXT("The written save reads back"), FIronSession::LoadJsonFile(TempPath, FromDisk, DiskError)))
	{
		TestTrue(TEXT("The save text survives the file round trip"), FromDisk.Write(true) == SavedText);
	}
	IFileManager::Get().Delete(*TempPath, false, false, true);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronReignStringTablesTest, "IronReign.Sim.StringTables", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronReignStringTablesTest::RunTest(const FString& /*Parameters*/)
{
	const FString PreviousCulture = IronUI::ToFString(IronSim::FLocale::Active().Culture());
	bool bAnyTables = false;
	for (const FString& CultureName : FIronSession::SupportedCultures())
	{
		const FString Directory = FIronSession::DataDir() / TEXT("Localization") / CultureName;
		if (!IFileManager::Get().DirectoryExists(*Directory))
		{
			AddWarning(FString::Printf(TEXT("No string tables for %s yet (%s)."), *CultureName, *FPaths::ConvertRelativePathToFull(Directory)));
			continue;
		}
		bAnyTables = true;
		TArray<FString> Errors;
		const int32 Loaded = FIronSession::LoadCultureStrings(CultureName, &Errors);
		for (const FString& Message : Errors)
		{
			AddError(FString::Printf(TEXT("%s: %s"), *CultureName, *Message));
		}
		TestTrue(FString::Printf(TEXT("%s: string tables load"), *CultureName), Loaded > 0);
		TestTrue(FString::Printf(TEXT("%s: the active locale switched"), *CultureName), IronSim::FLocale::Active().Culture() == IronUI::ToStd(CultureName));
		TestFalse(FString::Printf(TEXT("%s: a UI string resolves"), *CultureName), IronUI::Loc("ui.title.newGame", "New Game").IsEmpty());
	}
	if (!bAnyTables)
	{
		AddWarning(TEXT("Content/Data/Localization has no culture folders yet; only the English defaults in code were checked."));
	}
	FIronSession::LoadCultureStrings(PreviousCulture.IsEmpty() ? FString(TEXT("en")) : PreviousCulture);
	return true;
}

IMPLEMENT_SIMPLE_AUTOMATION_TEST(FIronReignAssetsTest, "IronReign.Sim.AssetsDecodePng", EAutomationTestFlags::EditorContext | EAutomationTestFlags::ClientContext | EAutomationTestFlags::ProductFilter)

bool FIronReignAssetsTest::RunTest(const FString& /*Parameters*/)
{
	FIronAssets& Assets = FIronAssets::Get();
	const TCHAR* Candidates[] = {TEXT("Art/UI/Panel.png"), TEXT("Art/UI/Button.png"), TEXT("Art/Portraits/unknown.png"), TEXT("Art/Map/Banner.png")};
	FString Found;
	for (const TCHAR* Candidate : Candidates)
	{
		if (Assets.Exists(Candidate))
		{
			Found = Candidate;
			break;
		}
	}
	if (Found.IsEmpty())
	{
		AddWarning(TEXT("No PNG art found under Content/Data/Art; skipping the decode test."));
		return true;
	}

	UTexture2D* Texture = Assets.Texture(Found);
	if (!TestNotNull(FString::Printf(TEXT("%s decodes into a texture"), *Found), Texture))
	{
		return false;
	}
	const FVector2D Size = Assets.ImageSize(Found);
	TestTrue(TEXT("The decoded image has a size"), Size.X > 0.0 && Size.Y > 0.0);
	TestEqual(TEXT("Texture width matches the PNG"), Texture->GetSizeX(), static_cast<int32>(Size.X));
	TestEqual(TEXT("Texture height matches the PNG"), Texture->GetSizeY(), static_cast<int32>(Size.Y));

	const FSlateBrush* Brush = Assets.Image(Found);
	TestTrue(TEXT("The image brush uses the texture"), Brush != nullptr && Brush->GetResourceObject() == Texture);
	const FSlateBrush* BoxBrush = Assets.Box(Found, FMargin(8.0f));
	TestTrue(TEXT("The box brush is 9-sliced"), BoxBrush != nullptr && BoxBrush->DrawAs == ESlateBrushDrawType::Box);
	return true;
}

#endif // WITH_DEV_AUTOMATION_TESTS
