#pragma once

#include "Sim/IronDuel.h"
#include "Sim/IronLocale.h"
#include "Sim/IronRandom.h"
#include "Sim/IronState.h"
#include "Sim/IronTypes.h"

#include <string>
#include <vector>

namespace IronSim
{
	/** Tactical battle terrain. Art: Content/Data/Art/Battle/Hex_<AssetName>.png (e.g. Hex_Plain.png). */
	enum class EHexTerrain : uint8_t
	{
		Plain,
		Forest,
		Hill,
		Mountain,  // Impassable.
		Water,     // Impassable.
		Ford,      // Shallow river: slow, poor defense.
		Bridge,
		Road,
		Wall,      // Impassable city wall.
		Gate,      // Impassable to attackers until its HP reaches 0; defenders pass freely.
		Town,      // Streets inside the walls.
		Castle,    // Defender headquarters. An attacker unit standing here wins the siege.
		Rubble,    // A broken gate.
		Count
	};

	const char* EnumName(EHexTerrain Value);
	/** Asset file stem, never translated: "Plain", "Forest", ... (Art/Battle/Hex_<AssetName>.png). */
	const char* AssetName(EHexTerrain Value);
	/** Translated name for the UI (IronLocale). */
	std::string DisplayName(EHexTerrain Value);

	enum class ETactic : uint8_t
	{
		Fire,     // Range 2: damage + morale loss, sets the hex burning. Strong in forests, useless on water.
		Confuse,  // Range 2: target loses its next turn.
		Rally     // Self or adjacent ally: restores morale and cures confusion.
	};

	/** Translated name for the UI (IronLocale). */
	std::string DisplayName(ETactic Value);

	enum class EUnitStatus : uint8_t
	{
		Active,
		Routed,     // Morale broke; left the field with its remaining troops.
		Destroyed,  // Troops reached zero; the officer escaped.
		Captured,   // Troops reached zero (or lost a duel) and the officer was taken prisoner.
		Killed      // Officer died (rare; duels).
	};

	/** Offset hex coordinate, flat-top "odd-q" layout (odd columns are shifted down half a hex). */
	struct FHex
	{
		int Col = 0;
		int Row = 0;

		bool operator==(const FHex& Other) const { return Col == Other.Col && Row == Other.Row; }
		bool operator!=(const FHex& Other) const { return !(*this == Other); }
	};

	namespace HexMath
	{
		int Distance(FHex A, FHex B);
		/** Fills the six neighbours (some may be out of bounds). */
		void Neighbors(FHex Center, FHex OutNeighbors[6]);
		/** Hex center in pixels. Size is the center-to-corner radius; hex width = 2*Size, height = sqrt(3)*Size. */
		void ToPixel(FHex Hex, float Size, float& OutX, float& OutY);
		FHex FromPixel(float X, float Y, float Size);
		/** Pixel size of a Cols x Rows board. */
		void BoardSize(int Cols, int Rows, float Size, float& OutWidth, float& OutHeight);
	}

	struct FBattleUnitSetup
	{
		/** Officer index in the strategic game, or -1 for a nameless garrison detachment. */
		int Officer = -1;
		std::string Name;
		std::string Portrait;
		int Stats[StatCount] = {40, 40, 40, 40, 40};
		int Bravery = 50;
		int Troops = 0;
		ETroopType Type = ETroopType::Infantry;
		/** Indices into FBattleSetup::Techniques. */
		std::vector<int> Techniques;
	};

	struct FBattleSideSetup
	{
		int Faction = -1;
		std::string Name;
		std::string Glyph;
		uint32_t Color = 0x808080;
		bool bPlayer = false;
		int Training = 50;
		int Morale = 70;
		/** Days of food carried. The attacker withdraws when it runs out. */
		int FoodDays = 999;
		/** Units[0] is the commander; if the commander falls the side is defeated. */
		std::vector<FBattleUnitSetup> Units;
	};

	struct FBattleSetup
	{
		EBattleKind Kind = EBattleKind::Field;
		ETerrain Terrain = ETerrain::Plains;
		uint64_t Seed = 1;
		/** Display name of the battlefield ("Siege of Luojing", "Road to Wancheng"). */
		std::string Location;
		/** 1..3, scales siege maps. */
		int CitySize = 2;
		int GateHp = 0;
		/** Percent defense bonus for defenders standing inside the walls. */
		int WallBonus = 0;
		int MaxDays = 30;
		/** [0] attacker, [1] defender. */
		FBattleSideSetup Sides[2];
		/** Copy of the strategic technique table for duels. */
		std::vector<FTechnique> Techniques;
	};

	struct FBattleUnit
	{
		int Id = 0;
		int Side = 0;
		bool bCommander = false;
		FBattleUnitSetup Setup;
		int Troops = 0;
		int StartTroops = 0;
		int Morale = 70;
		FHex Pos;
		/** Position at the start of the unit's turn (for UndoMove). */
		FHex TurnStart;
		bool bMoved = false;
		bool bActed = false;
		int ConfusedDays = 0;
		EUnitStatus Status = EUnitStatus::Active;
		int DamageDealt = 0;
		int TacticsSucceeded = 0;
		int DuelsWon = 0;

		bool IsActive() const { return Status == EUnitStatus::Active; }
	};

	enum class EBattleEventType : uint8_t
	{
		DayStart,
		Move,
		Attack,
		Counter,
		GateHit,
		GateBroken,
		Tactic,
		TacticFailed,
		Burn,
		DuelChallenge,
		DuelDeclined,
		DuelResult,
		Routed,
		Destroyed,
		Captured,
		Victory,
		Message
	};

	/** Something that happened, for animation and the battle log. */
	struct FBattleEvent
	{
		EBattleEventType Type = EBattleEventType::Message;
		int Unit = -1;
		int Target = -1;
		FHex From;
		FHex To;
		/** Damage, chance, morale change... depending on Type. */
		int Value = 0;
		std::string Text;
	};

	struct FUnitOutcome
	{
		int Side = 0;
		int Officer = -1;
		int Troops = 0;
		EUnitStatus Status = EUnitStatus::Active;
		int DamageDealt = 0;
		int TacticsSucceeded = 0;
		int DuelsWon = 0;
	};

	struct FBattleResult
	{
		bool bFinished = false;
		/** 0 attacker, 1 defender. */
		int Winner = -1;
		int Days = 0;
		bool bGateBroken = false;
		/** Parallel to FBattle::Units(). */
		std::vector<FUnitOutcome> Units;
		std::string Summary;
	};

	struct FReachableHex
	{
		FHex Hex;
		int Cost = 0;
	};

	/**
	 * Hex-grid tactical battle in the style of classic Koei war maps.
	 * Each day the attacker's units act, then the defender's. A unit may move once and then act once
	 * (attack, tactic, duel challenge or wait). The battle ends when a commander falls, a side is wiped out
	 * or routed, an attacker occupies the castle, the attacker runs out of food, or MaxDays passes (defender wins).
	 */
	class FBattle
	{
	public:
		void Setup(const FBattleSetup& InSetup);
		const FBattleSetup& GetSetup() const { return Config; }

		int Cols() const { return GridCols; }
		int Rows() const { return GridRows; }
		bool InBounds(FHex Hex) const;
		EHexTerrain TerrainAt(FHex Hex) const;
		/** Remaining burning days on a hex (0 = not burning). */
		int BurningAt(FHex Hex) const;
		FHex GateHex() const { return Gate; }
		FHex CastleHex() const { return Castle; }
		int GateHp() const { return GateHitPoints; }
		int GateMaxHp() const { return GateMaxHitPoints; }

		const std::vector<FBattleUnit>& Units() const { return BattleUnits; }
		const FBattleUnit& Unit(int UnitId) const { return BattleUnits[static_cast<size_t>(UnitId)]; }
		int UnitAt(FHex Hex) const;
		int Day() const { return CurrentDay; }
		int ActiveSide() const { return CurrentSide; }
		bool IsSideAI(int Side) const;
		bool IsOver() const { return Outcome.bFinished; }
		const FBattleResult& Result() const { return Outcome; }
		/** True when the player may act: player side active, no duel or challenge pending, battle running. */
		bool IsPlayerTurn() const;

		// Queries (for the active side's units).
		std::vector<FReachableHex> Reachable(int UnitId) const;
		std::vector<int> AttackTargets(int UnitId) const;
		bool CanAttackGate(int UnitId) const;
		std::vector<int> TacticTargets(int UnitId, ETactic Tactic) const;
		int TacticChance(int UnitId, ETactic Tactic, int TargetId) const;
		std::vector<int> DuelTargets(int UnitId) const;
		/** Expected troops lost by the target if UnitId attacks it now. */
		int PreviewDamage(int UnitId, int TargetId) const;
		int MovePoints(int UnitId) const;

		// Actions. Each returns false when illegal and changes nothing.
		bool Move(int UnitId, FHex Destination);
		bool UndoMove(int UnitId);
		bool Attack(int UnitId, int TargetId);
		bool AttackGate(int UnitId);
		bool UseTactic(int UnitId, ETactic Tactic, int TargetId);
		bool Wait(int UnitId);
		/** Challenge an adjacent enemy officer. An AI target decides at once; on acceptance a duel becomes active. */
		bool ChallengeDuel(int UnitId, int TargetId);

		// Duel handshake.
		/** The AI challenged one of the player's officers; call AnswerChallenge. */
		bool HasPendingChallenge() const { return PendingChallenger >= 0; }
		int ChallengerUnit() const { return PendingChallenger; }
		int ChallengedUnit() const { return PendingChallenged; }
		void AnswerChallenge(bool bAccept);
		bool HasActiveDuel() const { return bDuelActive; }
		FDuel& ActiveDuel() { return Duel; }
		const FDuel& ActiveDuel() const { return Duel; }
		/** Battle unit fighting on duel side 0 / 1. */
		int DuelUnit(int DuelSide) const { return DuelUnits[DuelSide == 0 ? 0 : 1]; }
		/** Applies a finished duel's outcome to the battle. Call once ActiveDuel().IsOver(). */
		void FinishDuel();

		// Turn flow.
		/** Ends the active side's turn. AI turns are not played automatically: call StepAI. */
		void EndTurn();
		/** Performs one AI action for the active side if it is AI-controlled. Returns false when there is
		 *  nothing for the AI to do (player's turn, pending challenge/duel needing the player, or battle over). */
		bool StepAI();
		/** Hands one side to the AI (e.g. the player chose "Delegate"). */
		void SetAutoControl(int Side, bool bAuto);
		/** AI plays both sides to the end; duels are auto-played. */
		void AutoResolve();

		/** Events since the last ClearEvents(), oldest first. */
		const std::vector<FBattleEvent>& Events() const { return PendingEvents; }
		void ClearEvents() { PendingEvents.clear(); }
		/** Full human-readable log. */
		const std::vector<std::string>& Log() const { return BattleLog; }

	private:
		// Implementation detail; owned by the battle engine. Extend freely.
		friend struct FBattleInternals;

		FBattleSetup Config;
		int GridCols = 16;
		int GridRows = 11;
		std::vector<EHexTerrain> Grid;
		std::vector<int> Burning;
		FHex Gate = {-1, -1};
		FHex Castle = {-1, -1};
		int GateHitPoints = 0;
		int GateMaxHitPoints = 0;
		std::vector<FBattleUnit> BattleUnits;
		int CurrentDay = 1;
		int CurrentSide = 0;
		bool bAutoControl[2] = {false, false};
		FBattleResult Outcome;
		int PendingChallenger = -1;
		int PendingChallenged = -1;
		bool bDuelActive = false;
		FDuel Duel;
		int DuelUnits[2] = {-1, -1};
		std::vector<FBattleEvent> PendingEvents;
		std::vector<std::string> BattleLog;
		FRng Rng;
	};

	/** Builds and fully AI-resolves a battle. */
	FBattleResult ResolveBattleAuto(const FBattleSetup& Setup);
}
