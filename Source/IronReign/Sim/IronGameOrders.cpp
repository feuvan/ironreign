#include "Sim/IronGame.h"

#include "Sim/IronGameInternal.h"
#include "Sim/IronLocale.h"

#include <algorithm>

namespace IronSim
{
	namespace GameRules
	{
		namespace OrdersDetail
		{
			int PendingDraft(const FGameState& State, int City)
			{
				int Total = 0;
				for (const FOrder& Order : State.Orders)
				{
					if (Order.Type == EOrderType::Draft && Order.City == City)
					{
						Total += std::max(0, Order.Amount);
					}
				}
				return Total;
			}

			bool HasEnvoy(const FGameState& State, int Faction, int Target)
			{
				for (const FOrder& Order : State.Orders)
				{
					const bool bDiplomacy = Order.Type == EOrderType::Alliance || Order.Type == EOrderType::Truce || Order.Type == EOrderType::Gift;
					if (bDiplomacy && Order.TargetFaction == Target && ValidOfficer(State, Order.Officer) && At(State.Officers, Order.Officer).Faction == Faction)
					{
						return true;
					}
				}
				return false;
			}

			std::vector<int> LearnableTechniques(const FGameState& State, int Officer, int Sect)
			{
				std::vector<int> Result;
				if (!ValidOfficer(State, Officer) || !ValidSect(State, Sect))
				{
					return Result;
				}
				const FOfficer& Data = At(State.Officers, Officer);
				for (const int Technique : At(State.Sects, Sect).Techniques)
				{
					if (!ValidTechnique(State, Technique))
					{
						continue;
					}
					const bool bKnown = std::find(Data.Techniques.begin(), Data.Techniques.end(), Technique) != Data.Techniques.end();
					if (!bKnown && StatOf(Data, EStat::Martial) >= At(State.Techniques, Technique).MinMartial)
					{
						Result.push_back(Technique);
					}
				}
				return Result;
			}

			int TechniqueChance(const FOfficer& Officer)
			{
				return ClampInt(20 + StatOf(Officer, EStat::Martial) / 4, 5, 60);
			}

			int SectFavor(const FGameState& State, int Sect, int Faction)
			{
				if (!ValidSect(State, Sect) || Faction < 0)
				{
					return 0;
				}
				const FSect& Data = At(State.Sects, Sect);
				return Faction < CountOf(Data.Favor) ? At(Data.Favor, Faction) : 0;
			}

			void AddSectFavor(FGameState& State, int Sect, int Faction, int Amount)
			{
				if (!ValidSect(State, Sect) || !ValidFaction(State, Faction))
				{
					return;
				}
				FSect& Data = At(State.Sects, Sect);
				Data.Favor.resize(State.Factions.size(), 0);
				At(Data.Favor, Faction) = ClampInt(At(Data.Favor, Faction) + Amount, 0, 100);
			}

			int MergeTraining(int TrainingA, int TroopsA, int TrainingB, int TroopsB)
			{
				const long long Total = static_cast<long long>(std::max(0, TroopsA)) + std::max(0, TroopsB);
				if (Total <= 0)
				{
					return TrainingA;
				}
				return static_cast<int>((static_cast<long long>(TrainingA) * std::max(0, TroopsA) + static_cast<long long>(TrainingB) * std::max(0, TroopsB)) / Total);
			}

			void ExecuteDiplomacy(FGameState& State, const FOrder& Order, FOfficer& Envoy, bool bPlayer)
			{
				const int Faction = Envoy.Faction;
				const int Target = Order.TargetFaction;
				if (!IsAliveFaction(State, Target) || Target == Faction)
				{
					return;
				}
				// AI envoys to the player arrive as a proposal the player answers.
				if (IsPlayerFaction(State, Target) && !bPlayer && Order.Type != EOrderType::Gift)
				{
					QueueProposal(State, Faction, Order.Type == EOrderType::Alliance);
					return;
				}
				FRelation& Relation = State.Relation(Faction, Target);
				const std::string Ours = FactionLabel(State, Faction);
				const std::string Theirs = FactionLabel(State, Target);
				GainExp(Envoy, EStat::Politics, 15);
				GainExp(Envoy, EStat::Charm, 5);
				Envoy.Merit += 5;
				if (Order.Type == EOrderType::Gift)
				{
					const int Gain = GiftTrustGain(Envoy, Order.Gold);
					Relation.Trust = ClampInt(Relation.Trust + Gain, 0, 100);
					if (bPlayer || IsPlayerFaction(State, Target))
					{
						LogPlayer(State, LocF("log.order.gift", "{officer} delivered {gold} gold from the {faction} to the {target}. Trust is now {trust}.", {{"officer", NameOf(Envoy)}, {"gold", ToText(Order.Gold)}, {"faction", Ours}, {"target", Theirs}, {"trust", ToText(Relation.Trust)}}));
					}
					return;
				}
				const bool bAlliance = Order.Type == EOrderType::Alliance;
				if (bAlliance ? State.AreAllied(Faction, Target) : (State.AreAllied(Faction, Target) || State.HaveTruce(Faction, Target)))
				{
					return;
				}
				const int Chance = bAlliance ? AllianceChanceOf(State, Order.Officer, Faction, Target) : TruceChanceOf(State, Order.Officer, Faction, Target);
				if (State.Rng.Chance(Chance))
				{
					if (bAlliance)
					{
						Relation.AllianceMonths = Balance::AllianceMonths;
						Relation.TruceMonths = 0;
						Relation.Trust = ClampInt(Relation.Trust + 10, 0, 100);
						LogBetween(State, Faction, Target, LocF("log.diplomacy.alliance", "The {faction} and the {target} have sealed an alliance for {months} months.", {{"faction", Ours}, {"target", Theirs}, {"months", ToText(Balance::AllianceMonths)}}), true);
					}
					else
					{
						Relation.TruceMonths = Balance::TruceMonths;
						Relation.Trust = ClampInt(Relation.Trust + 5, 0, 100);
						LogBetween(State, Faction, Target, LocF("log.diplomacy.truce", "The {faction} and the {target} have agreed to a truce for {months} months.", {{"faction", Ours}, {"target", Theirs}, {"months", ToText(Balance::TruceMonths)}}), true);
					}
					Envoy.Merit += 10;
					GainExp(Envoy, EStat::Politics, 10);
				}
				else
				{
					Relation.Trust = ClampInt(Relation.Trust - 3, 0, 100);
					if (bPlayer)
					{
						LogPlayer(State, bAlliance
							? LocF("log.diplomacy.allianceRefused", "The {target} turned down the alliance proposed by {officer}.", {{"target", Theirs}, {"officer", NameOf(Envoy)}})
							: LocF("log.diplomacy.truceRefused", "The {target} turned down the truce proposed by {officer}.", {{"target", Theirs}, {"officer", NameOf(Envoy)}}));
					}
				}
			}

			void ExecuteOrder(FGameState& State, const FOrder& Order)
			{
				if (!ValidOfficer(State, Order.Officer) || !ValidCity(State, Order.City))
				{
					return;
				}
				FOfficer& Officer = At(State.Officers, Order.Officer);
				FCity& City = At(State.Cities, Order.City);
				if (Officer.Status != EOfficerStatus::Serving || Officer.City != Order.City || Officer.Army >= 0 || City.Owner != Officer.Faction)
				{
					return;
				}
				const int Faction = Officer.Faction;
				const bool bPlayer = IsPlayerFaction(State, Faction);
				const std::string Who = NameOf(Officer);
				const std::string Where = NameOf(City);
				switch (Order.Type)
				{
				case EOrderType::Farm:
				{
					const int Before = City.Farm;
					City.Farm = std::min(City.FarmMax, City.Farm + DevelopGain(Officer));
					GainExp(Officer, EStat::Politics, 15);
					Officer.Merit += 5;
					if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.farm", "{officer} developed the farmland of {city} to {value} (+{amount}).", {{"officer", Who}, {"city", Where}, {"value", ToText(City.Farm)}, {"amount", ToText(City.Farm - Before)}}));
					}
					break;
				}
				case EOrderType::Commerce:
				{
					const int Before = City.Commerce;
					City.Commerce = std::min(City.CommerceMax, City.Commerce + DevelopGain(Officer));
					GainExp(Officer, EStat::Politics, 15);
					Officer.Merit += 5;
					if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.commerce", "{officer} expanded the markets of {city} to {value} (+{amount}).", {{"officer", Who}, {"city", Where}, {"value", ToText(City.Commerce)}, {"amount", ToText(City.Commerce - Before)}}));
					}
					break;
				}
				case EOrderType::Walls:
				{
					const int Before = City.Defense;
					City.Defense = std::min(City.DefenseMax, City.Defense + WallsGain(Officer));
					GainExp(Officer, EStat::Politics, 10);
					GainExp(Officer, EStat::Command, 5);
					Officer.Merit += 5;
					if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.walls", "{officer} strengthened the walls of {city} to {value} (+{amount}).", {{"officer", Who}, {"city", Where}, {"value", ToText(City.Defense)}, {"amount", ToText(City.Defense - Before)}}));
					}
					break;
				}
				case EOrderType::Patrol:
				{
					const int Before = City.Order;
					City.Order = std::min(100, City.Order + PatrolGain(Officer));
					GainExp(Officer, EStat::Command, 10);
					GainExp(Officer, EStat::Martial, 5);
					Officer.Merit += 5;
					if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.patrol", "{officer} patrolled the streets of {city}. Public order is now {value} (+{amount}).", {{"officer", Who}, {"city", Where}, {"value", ToText(City.Order)}, {"amount", ToText(City.Order - Before)}}));
					}
					break;
				}
				case EOrderType::Draft:
				{
					const int Capacity = std::max(0, City.Population / Balance::DraftPopulationDivisor);
					const int Amount = ClampInt(Order.Amount, 0, std::min(DraftLimit(Officer), Capacity));
					const int Refund = std::max(0, Order.Cost - DraftCostOf(Amount));
					City.Gold += Refund;
					City.Training = MergeTraining(City.Training, City.Troops, Balance::RecruitTraining, Amount);
					City.Troops += Amount;
					City.Population = std::max(0, City.Population - Amount);
					City.Order = std::max(0, City.Order - Balance::DraftOrderLoss);
					GainExp(Officer, EStat::Charm, 12);
					Officer.Merit += 5;
					if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.draft", "{officer} raised {amount} troops in {city}. The garrison now numbers {value}.", {{"officer", Who}, {"amount", ToText(Amount)}, {"city", Where}, {"value", ToText(City.Troops)}}));
					}
					break;
				}
				case EOrderType::Train:
				{
					const int Before = City.Training;
					City.Training = std::min(100, City.Training + TrainGain(Officer));
					GainExp(Officer, EStat::Command, 15);
					Officer.Merit += 5;
					if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.train", "{officer} drilled the troops of {city}. Training is now {value} (+{amount}).", {{"officer", Who}, {"city", Where}, {"value", ToText(City.Training)}, {"amount", ToText(City.Training - Before)}}));
					}
					break;
				}
				case EOrderType::Search:
				{
					std::vector<int> Hidden;
					for (int Index = 0; Index < CountOf(State.Officers); ++Index)
					{
						if (At(State.Officers, Index).Status == EOfficerStatus::Hidden && At(State.Officers, Index).City == Order.City)
						{
							Hidden.push_back(Index);
						}
					}
					GainExp(Officer, EStat::Strategy, 8);
					GainExp(Officer, EStat::Charm, 8);
					Officer.Merit += 5;
					if (!Hidden.empty() && State.Rng.Chance(SearchChance(Officer)))
					{
						const int Found = Hidden[static_cast<size_t>(State.Rng.Range(0, CountOf(Hidden) - 1))];
						FOfficer& Talent = At(State.Officers, Found);
						Talent.Status = EOfficerStatus::Free;
						Talent.Faction = -1;
						Talent.Army = -1;
						Officer.Merit += 10;
						if (State.Rng.Chance(RecruitChanceOf(State, Order.Officer, Found)))
						{
							JoinFaction(State, Found, Faction, Order.City, 60 + State.Rng.Range(0, 15));
							GainExp(Officer, EStat::Charm, 15);
							if (bPlayer)
							{
								LogPlayer(State, LocF("log.order.searchJoined", "{officer} found {talent} living in obscurity near {city}. {talent} has agreed to serve you!", {{"officer", Who}, {"talent", NameOf(Talent)}, {"city", Where}}), true);
							}
						}
						else if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.searchFound", "{officer} found {talent} living in obscurity near {city}, but {talent} declined to serve for now.", {{"officer", Who}, {"talent", NameOf(Talent)}, {"city", Where}}), true);
						}
						break;
					}
					const int Roll = State.Rng.Range(0, 99);
					if (Roll < 45)
					{
						const int Gold = State.Rng.Range(30, 80) + StatOf(Officer, EStat::Charm);
						City.Gold += Gold;
						if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.searchGold", "{officer} found no hidden talent but collected {amount} gold in {city}.", {{"officer", Who}, {"amount", ToText(Gold)}, {"city", Where}}));
						}
					}
					else if (Roll < 75)
					{
						const int Food = State.Rng.Range(300, 900) + StatOf(Officer, EStat::Strategy) * 5;
						City.Food += Food;
						if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.searchFood", "{officer} found no hidden talent but secured {amount} food in {city}.", {{"officer", Who}, {"amount", ToText(Food)}, {"city", Where}}));
						}
					}
					else if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.searchNothing", "{officer} searched {city} but found nothing of note.", {{"officer", Who}, {"city", Where}}));
					}
					break;
				}
				case EOrderType::Recruit:
				{
					const int Target = Order.TargetOfficer;
					GainExp(Officer, EStat::Charm, 15);
					Officer.Merit += 5;
					const std::vector<int> Targets = RecruitTargetsOf(State, Order.City, Faction);
					if (!ValidOfficer(State, Target) || std::find(Targets.begin(), Targets.end(), Target) == Targets.end())
					{
						if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.recruitGone", "{officer} could not find {target}.", {{"officer", Who}, {"target", OfficerLabel(State, Target)}}));
						}
						break;
					}
					FOfficer& Candidate = At(State.Officers, Target);
					const bool bWasEnemy = Candidate.Status == EOfficerStatus::Serving;
					const int Previous = bWasEnemy ? Candidate.Faction : -1;
					if (State.Rng.Chance(RecruitChanceOf(State, Order.Officer, Target)))
					{
						JoinFaction(State, Target, Faction, Order.City, (bWasEnemy ? 55 : 65) + State.Rng.Range(0, 15));
						GainExp(Officer, EStat::Charm, 15);
						Officer.Merit += 10;
						if (bWasEnemy)
						{
							FRelation& Relation = State.Relation(Faction, Previous);
							Relation.Trust = ClampInt(Relation.Trust - 5, 0, 100);
							LogBetween(State, Faction, Previous, LocF("log.order.recruitDefect", "{target} has abandoned the {previous} and joined the {faction}, persuaded by {officer}.", {{"target", NameOf(Candidate)}, {"previous", FactionLabel(State, Previous)}, {"faction", FactionLabel(State, Faction)}, {"officer", Who}}), true);
						}
						else if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.recruitJoined", "{target} has accepted the invitation of {officer} and now serves you in {city}.", {{"target", NameOf(Candidate)}, {"officer", Who}, {"city", Where}}), true);
						}
					}
					else if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.recruitFailed", "{target} politely declined the offer made by {officer}.", {{"target", NameOf(Candidate)}, {"officer", Who}}));
					}
					break;
				}
				case EOrderType::Move:
				{
					if (ValidCity(State, Order.TargetCity) && At(State.Cities, Order.TargetCity).Owner == Faction && Order.TargetCity != Order.City)
					{
						PlaceInCity(State, Order.Officer, Order.TargetCity);
						if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.move", "{officer} moved from {city} to {target}.", {{"officer", Who}, {"city", Where}, {"target", CityLabel(State, Order.TargetCity)}}));
						}
					}
					break;
				}
				case EOrderType::Transport:
				{
					const bool bArrives = ValidCity(State, Order.TargetCity) && At(State.Cities, Order.TargetCity).Owner == Faction;
					FCity& Destination = bArrives ? At(State.Cities, Order.TargetCity) : City;
					const int Troops = std::max(0, Order.Troops);
					Destination.Training = MergeTraining(Destination.Training, Destination.Troops, City.Training, Troops);
					Destination.Gold += std::max(0, Order.Gold);
					Destination.Food += std::max(0, Order.Food);
					Destination.Troops += Troops;
					GainExp(Officer, EStat::Command, 5);
					Officer.Merit += 3;
					if (bPlayer && bArrives)
					{
						LogPlayer(State, LocF("log.order.transport", "{officer} delivered {gold} gold, {food} food and {troops} troops from {city} to {target}.", {{"officer", Who}, {"gold", ToText(std::max(0, Order.Gold))}, {"food", ToText(std::max(0, Order.Food))}, {"troops", ToText(Troops)}, {"city", Where}, {"target", CityLabel(State, Order.TargetCity)}}));
					}
					break;
				}
				case EOrderType::SectTraining:
				{
					if (!ValidSect(State, Order.TargetSect))
					{
						break;
					}
					const FSect& Sect = At(State.Sects, Order.TargetSect);
					GainExp(Officer, EStat::Martial, Balance::SectTrainingExp);
					Officer.Merit += 5;
					AddSectFavor(State, Order.TargetSect, Faction, 2);
					if (Officer.Sect < 0)
					{
						Officer.Sect = Order.TargetSect;
					}
					const std::vector<int> Learnable = LearnableTechniques(State, Order.Officer, Order.TargetSect);
					if (SectFavor(State, Order.TargetSect, Faction) >= Balance::SectTechniqueFavor && !Learnable.empty() && State.Rng.Chance(TechniqueChance(Officer)))
					{
						const int Technique = Learnable[static_cast<size_t>(State.Rng.Range(0, CountOf(Learnable) - 1))];
						Officer.Techniques.push_back(Technique);
						if (bPlayer)
						{
							LogPlayer(State, LocF("log.order.sectTechnique", "{officer} trained with the {sect} and mastered the technique {technique}!", {{"officer", Who}, {"sect", NameOf(Sect)}, {"technique", NameOf(At(State.Techniques, Technique))}}), true);
						}
					}
					else if (bPlayer)
					{
						LogPlayer(State, LocF("log.order.sect", "{officer} trained with the {sect}. Martial is now {value}.", {{"officer", Who}, {"sect", NameOf(Sect)}, {"value", ToText(StatOf(Officer, EStat::Martial))}}));
					}
					break;
				}
				case EOrderType::Alliance:
				case EOrderType::Truce:
				case EOrderType::Gift:
					ExecuteDiplomacy(State, Order, Officer, bPlayer);
					break;
				case EOrderType::Count:
					break;
				}
			}

			std::string HiddenRumor(const FGameState& State, int Officer, int City)
			{
				const FOfficer& Data = At(State.Officers, Officer);
				const std::string Rumor = RumorOf(Data);
				if (!Rumor.empty())
				{
					return Rumor;
				}
				int Best = 0;
				for (int Stat = 1; Stat < StatCount; ++Stat)
				{
					if (Data.Stats[Stat] > Data.Stats[Best])
					{
						Best = Stat;
					}
				}
				const std::string Place = CityLabel(State, City);
				switch (static_cast<EStat>(Best))
				{
				case EStat::Martial: return LocF("rumor.hidden.martial", "They say a fearsome warrior lives in seclusion near {city}.", {{"city", Place}});
				case EStat::Command: return LocF("rumor.hidden.command", "They say a former general hides from the world near {city}.", {{"city", Place}});
				case EStat::Strategy: return LocF("rumor.hidden.strategy", "They say a brilliant strategist keeps a hermitage near {city}.", {{"city", Place}});
				case EStat::Politics: return LocF("rumor.hidden.politics", "They say a wise administrator retired to the countryside near {city}.", {{"city", Place}});
				case EStat::Charm: return LocF("rumor.hidden.charm", "They say a charismatic wanderer has been seen near {city}.", {{"city", Place}});
				}
				return std::string();
			}
		}

		int DevelopGain(const FOfficer& Officer)
		{
			return 4 + StatOf(Officer, EStat::Politics) / 8;
		}

		int WallsGain(const FOfficer& Officer)
		{
			return 4 + (StatOf(Officer, EStat::Politics) + StatOf(Officer, EStat::Command)) / 20;
		}

		int PatrolGain(const FOfficer& Officer)
		{
			return 3 + (StatOf(Officer, EStat::Martial) + StatOf(Officer, EStat::Command)) / 30;
		}

		int TrainGain(const FOfficer& Officer)
		{
			return 5 + StatOf(Officer, EStat::Command) / 10;
		}

		int DraftLimit(const FOfficer& Officer)
		{
			return Balance::DraftBase + StatOf(Officer, EStat::Charm) * Balance::DraftPerCharm;
		}

		int SearchChance(const FOfficer& Officer)
		{
			return ClampInt(25 + StatOf(Officer, EStat::Charm) / 3 + StatOf(Officer, EStat::Strategy) / 5, 0, 95);
		}

		int DraftCapacityOf(const FGameState& State, int City)
		{
			if (!ValidCity(State, City))
			{
				return 0;
			}
			return std::max(0, At(State.Cities, City).Population / Balance::DraftPopulationDivisor - OrdersDetail::PendingDraft(State, City));
		}

		int DraftCostOf(int Troops)
		{
			return (std::max(0, Troops) + Balance::DraftCostDivisor - 1) / Balance::DraftCostDivisor;
		}

		int RecruitChanceOf(const FGameState& State, int Recruiter, int Target)
		{
			if (!ValidOfficer(State, Recruiter) || !ValidOfficer(State, Target) || Recruiter == Target)
			{
				return 0;
			}
			const FOfficer& Envoy = At(State.Officers, Recruiter);
			const FOfficer& Candidate = At(State.Officers, Target);
			const int Faction = Envoy.Faction;
			if (Envoy.Status != EOfficerStatus::Serving || Faction < 0 || State.IsRuler(Target))
			{
				return 0;
			}
			const int Ruler = RulerOf(State, Faction);
			const int RulerAffinity = Ruler >= 0 ? At(State.Officers, Ruler).Affinity : Envoy.Affinity;
			const int Distance = AffinityDistance(Candidate.Affinity, RulerAffinity);
			const int Charm = StatOf(Envoy, EStat::Charm);
			if (Candidate.Status == EOfficerStatus::Free || Candidate.Status == EOfficerStatus::Hidden)
			{
				return ClampInt(35 + Charm / 2 - Distance / 2 - (Candidate.Ambition - 50) / 5, 5, 95);
			}
			if (Candidate.Status == EOfficerStatus::Serving && Candidate.Faction != Faction)
			{
				return ClampInt((85 - Candidate.Loyalty) + Charm / 4 - Distance / 3 + (Candidate.Ambition - 50) / 10, 0, 90);
			}
			return 0;
		}

		int PrisonerRecruitChanceOf(const FGameState& State, int Prisoner, int Captor)
		{
			if (!ValidOfficer(State, Prisoner) || Captor < 0)
			{
				return 0;
			}
			const FOfficer& Data = At(State.Officers, Prisoner);
			if (Data.Status != EOfficerStatus::Prisoner || Data.Captor != Captor)
			{
				return 0;
			}
			const int Ruler = RulerOf(State, Captor);
			const int RulerCharm = Ruler >= 0 ? StatOf(At(State.Officers, Ruler), EStat::Charm) : 50;
			const int RulerAffinity = Ruler >= 0 ? At(State.Officers, Ruler).Affinity : Data.Affinity;
			const int Distance = AffinityDistance(Data.Affinity, RulerAffinity);
			const bool bHomeless = !IsAliveFaction(State, Data.Faction);
			return ClampInt(30 + RulerCharm / 3 - Distance / 2 - Data.Loyalty / 3 + (bHomeless ? 25 : 0), 0, 90);
		}

		int AllianceChanceOf(const FGameState& State, int Envoy, int From, int To)
		{
			if (!ValidOfficer(State, Envoy) || !ValidFaction(State, From) || !ValidFaction(State, To) || From == To)
			{
				return 0;
			}
			const FOfficer& Data = At(State.Officers, Envoy);
			const int Trust = State.Relation(From, To).Trust;
			int Chance = Trust - 30 + StatOf(Data, EStat::Politics) / 4 + StatOf(Data, EStat::Charm) / 10;
			if (State.HaveTruce(From, To))
			{
				Chance += 5;
			}
			return ClampInt(Chance, 0, 90);
		}

		int TruceChanceOf(const FGameState& State, int Envoy, int From, int To)
		{
			if (!ValidOfficer(State, Envoy) || !ValidFaction(State, From) || !ValidFaction(State, To) || From == To)
			{
				return 0;
			}
			const FOfficer& Data = At(State.Officers, Envoy);
			const int Trust = State.Relation(From, To).Trust;
			int Chance = Trust - 10 + StatOf(Data, EStat::Politics) / 4 + StatOf(Data, EStat::Charm) / 10;
			if (State.FactionTotalTroops(From) > State.FactionTotalTroops(To))
			{
				Chance += 10;
			}
			return ClampInt(Chance, 0, 90);
		}

		int GiftTrustGain(const FOfficer& Envoy, int Gold)
		{
			if (Gold <= 0)
			{
				return 0;
			}
			return std::min(30, Gold / 40 + StatOf(Envoy, EStat::Politics) / 25);
		}

		std::vector<int> RecruitTargetsOf(const FGameState& State, int City, int Faction)
		{
			std::vector<int> Result;
			if (!ValidCity(State, City) || Faction < 0)
			{
				return Result;
			}
			const std::vector<int> Neighbors = State.Neighbors(City);
			for (int Index = 0; Index < CountOf(State.Officers); ++Index)
			{
				const FOfficer& Officer = At(State.Officers, Index);
				const bool bAdjacent = std::find(Neighbors.begin(), Neighbors.end(), Officer.City) != Neighbors.end();
				if (Officer.Status == EOfficerStatus::Free && (Officer.City == City || bAdjacent))
				{
					Result.push_back(Index);
				}
				else if (Officer.Status == EOfficerStatus::Serving && Officer.Faction != Faction && Officer.Faction >= 0 && Officer.Army < 0 && bAdjacent
					&& !State.IsRuler(Index) && !State.AreAllied(Faction, Officer.Faction))
				{
					Result.push_back(Index);
				}
			}
			return Result;
		}

		std::vector<int> SectsNearOf(const FGameState& State, int City)
		{
			std::vector<int> Result;
			if (!ValidCity(State, City))
			{
				return Result;
			}
			const std::vector<int> Neighbors = State.Neighbors(City);
			for (int Sect = 0; Sect < CountOf(State.Sects); ++Sect)
			{
				const int Home = At(State.Sects, Sect).City;
				if (Home == City || std::find(Neighbors.begin(), Neighbors.end(), Home) != Neighbors.end())
				{
					Result.push_back(Sect);
				}
			}
			return Result;
		}

		bool IsRecruitTargeted(const FGameState& State, int Target, int Faction)
		{
			for (const FOrder& Order : State.Orders)
			{
				if (Order.Type == EOrderType::Recruit && Order.TargetOfficer == Target && ValidOfficer(State, Order.Officer) && At(State.Officers, Order.Officer).Faction == Faction)
				{
					return true;
				}
			}
			return false;
		}

		int FoodBuyPriceOf(const FGameState& State)
		{
			// Food is cheapest right after the month 9 harvest and dearest in the lean summer months.
			static const int SeasonPercent[12] = {100, 105, 110, 115, 120, 125, 130, 135, 70, 75, 85, 95};
			return std::max(1, Balance::FoodBasePrice * SeasonPercent[ClampInt(State.Month, 1, 12) - 1] / 100);
		}

		int FoodSellPriceOf(const FGameState& State)
		{
			return std::max(1, FoodBuyPriceOf(State) * 6 / 10);
		}

		bool TradeFoodRules(FGameState& State, int City, int FoodDelta, std::string& OutError)
		{
			if (State.Phase != EPhase::Planning)
			{
				OutError = Loc("trade.reason.notPlanning", "The market is only open during the planning phase.");
				return false;
			}
			if (!ValidCity(State, City) || At(State.Cities, City).Owner < 0)
			{
				OutError = Loc("trade.reason.noCity", "Choose a city.");
				return false;
			}
			if (FoodDelta == 0)
			{
				OutError = Loc("trade.reason.amount", "Choose an amount of food.");
				return false;
			}
			FCity& Data = At(State.Cities, City);
			if (FoodDelta > 0)
			{
				const long long Cost = (static_cast<long long>(FoodDelta) * FoodBuyPriceOf(State) + 99) / 100;
				if (Cost > Data.Gold)
				{
					OutError = LocF("trade.reason.noGold", "Not enough gold: {cost} needed, {gold} in {city}.", {{"cost", ToText(static_cast<int>(std::min<long long>(Cost, 2000000000)))}, {"gold", ToText(Data.Gold)}, {"city", NameOf(Data)}});
					return false;
				}
				Data.Gold -= static_cast<int>(Cost);
				Data.Food += FoodDelta;
				return true;
			}
			const int Amount = -FoodDelta;
			if (Amount > Data.Food)
			{
				OutError = LocF("trade.reason.noFood", "{city} has only {amount} food.", {{"city", NameOf(Data)}, {"amount", ToText(Data.Food)}});
				return false;
			}
			Data.Food -= Amount;
			Data.Gold += static_cast<int>(static_cast<long long>(Amount) * FoodSellPriceOf(State) / 100);
			return true;
		}

		int RewardLoyaltyGain(int Gold)
		{
			return std::max(0, Gold) / 20;
		}

		FOrderCheck CheckOrderRules(const FGameState& State, const FOrder& Order)
		{
			FOrderCheck Check;
			if (State.Phase != EPhase::Planning)
			{
				return DenyCheck(Check, Loc("order.reason.notPlanning", "Orders can only be given during the planning phase."));
			}
			if (!ValidCity(State, Order.City))
			{
				return DenyCheck(Check, Loc("order.reason.noCity", "Choose a city."));
			}
			if (!ValidOfficer(State, Order.Officer))
			{
				return DenyCheck(Check, Loc("order.reason.noOfficer", "Choose an officer."));
			}
			const FOfficer& Officer = At(State.Officers, Order.Officer);
			const FCity& City = At(State.Cities, Order.City);
			const std::string Who = NameOf(Officer);
			const std::string Where = NameOf(City);
			if (Officer.Status != EOfficerStatus::Serving || City.Owner < 0 || Officer.Faction != City.Owner)
			{
				return DenyCheck(Check, LocF("order.reason.notServing", "{officer} does not serve the lord of {city}.", {{"officer", Who}, {"city", Where}}));
			}
			if (Officer.Army >= 0 || Officer.City != Order.City)
			{
				return DenyCheck(Check, LocF("order.reason.notInCity", "{officer} is not in {city}.", {{"officer", Who}, {"city", Where}}));
			}
			if (State.OfficerOrder(Order.Officer) != nullptr)
			{
				return DenyCheck(Check, LocF("order.reason.busy", "{officer} already has orders this month.", {{"officer", Who}}));
			}
			const int Faction = City.Owner;
			switch (Order.Type)
			{
			case EOrderType::Farm:
			{
				const int Gain = std::min(DevelopGain(Officer), City.FarmMax - City.Farm);
				Check.Cost = Balance::DevelopCost;
				Check.Preview = LocF("order.preview.farm", "Farmland +{amount}", {{"amount", ToText(std::max(0, Gain))}});
				if (Gain <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.farmMax", "The farmland is fully developed."));
				}
				break;
			}
			case EOrderType::Commerce:
			{
				const int Gain = std::min(DevelopGain(Officer), City.CommerceMax - City.Commerce);
				Check.Cost = Balance::DevelopCost;
				Check.Preview = LocF("order.preview.commerce", "Commerce +{amount}", {{"amount", ToText(std::max(0, Gain))}});
				if (Gain <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.commerceMax", "Commerce is fully developed."));
				}
				break;
			}
			case EOrderType::Walls:
			{
				const int Gain = std::min(WallsGain(Officer), City.DefenseMax - City.Defense);
				Check.Cost = Balance::WallsCost;
				Check.Preview = LocF("order.preview.walls", "Defense +{amount}", {{"amount", ToText(std::max(0, Gain))}});
				if (Gain <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.wallsMax", "The walls are already as strong as they can be."));
				}
				break;
			}
			case EOrderType::Patrol:
			{
				const int Gain = std::min(PatrolGain(Officer), 100 - City.Order);
				Check.Cost = Balance::PatrolCost;
				Check.Preview = LocF("order.preview.patrol", "Public order +{amount}", {{"amount", ToText(std::max(0, Gain))}});
				if (Gain <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.orderMax", "Public order is already perfect."));
				}
				break;
			}
			case EOrderType::Draft:
			{
				const int Amount = std::max(0, Order.Amount);
				const int Limit = DraftLimit(Officer);
				const int Capacity = DraftCapacityOf(State, Order.City);
				Check.Cost = DraftCostOf(Amount);
				Check.Preview = LocF("order.preview.draft", "Troops +{amount}, public order -{order}", {{"amount", ToText(Amount)}, {"order", ToText(Balance::DraftOrderLoss)}});
				if (Amount <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.draftAmount", "Choose how many troops to draft."));
				}
				if (Amount > Limit)
				{
					return DenyCheck(Check, LocF("order.reason.draftLimit", "{officer} can raise at most {amount} troops in one month.", {{"officer", Who}, {"amount", ToText(Limit)}}));
				}
				if (Amount > Capacity)
				{
					return DenyCheck(Check, LocF("order.reason.draftCapacity", "{city} can provide only {amount} more recruits this month.", {{"city", Where}, {"amount", ToText(Capacity)}}));
				}
				break;
			}
			case EOrderType::Train:
			{
				const int Gain = std::min(TrainGain(Officer), 100 - City.Training);
				Check.Cost = Balance::TrainCost;
				Check.Preview = LocF("order.preview.train", "Training +{amount}", {{"amount", ToText(std::max(0, Gain))}});
				if (City.Troops <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.noTroops", "There are no troops to train."));
				}
				if (Gain <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.trainingMax", "The troops are already fully trained."));
				}
				break;
			}
			case EOrderType::Search:
			{
				Check.Cost = Balance::SearchCost;
				Check.SuccessChance = SearchChance(Officer);
				Check.Preview = LocF("order.preview.search", "Find hidden talent {chance}%, otherwise gold or food", {{"chance", ToText(Check.SuccessChance)}});
				break;
			}
			case EOrderType::Recruit:
			{
				Check.Cost = Balance::RecruitCost;
				if (!ValidOfficer(State, Order.TargetOfficer))
				{
					return DenyCheck(Check, Loc("order.reason.noRecruitTarget", "Choose an officer to recruit."));
				}
				const std::string Target = OfficerLabel(State, Order.TargetOfficer);
				const std::vector<int> Targets = RecruitTargetsOf(State, Order.City, Faction);
				if (std::find(Targets.begin(), Targets.end(), Order.TargetOfficer) == Targets.end())
				{
					return DenyCheck(Check, LocF("order.reason.recruitUnreachable", "{target} cannot be approached from {city}.", {{"target", Target}, {"city", Where}}));
				}
				Check.SuccessChance = RecruitChanceOf(State, Order.Officer, Order.TargetOfficer);
				Check.Preview = LocF("order.preview.chance", "Success {chance}%", {{"chance", ToText(Check.SuccessChance)}});
				if (IsRecruitTargeted(State, Order.TargetOfficer, Faction))
				{
					return DenyCheck(Check, LocF("order.reason.recruitTaken", "Another of your officers is already trying to recruit {target} this month.", {{"target", Target}}));
				}
				break;
			}
			case EOrderType::Move:
			{
				if (!ValidCity(State, Order.TargetCity) || Order.TargetCity == Order.City || At(State.Cities, Order.TargetCity).Owner != Faction)
				{
					return DenyCheck(Check, Loc("order.reason.moveTarget", "Choose another city under your control."));
				}
				Check.Preview = LocF("order.preview.move", "Move to {city}", {{"city", CityLabel(State, Order.TargetCity)}});
				break;
			}
			case EOrderType::Transport:
			{
				if (!ValidCity(State, Order.TargetCity) || Order.TargetCity == Order.City || At(State.Cities, Order.TargetCity).Owner != Faction)
				{
					return DenyCheck(Check, Loc("order.reason.transportTarget", "Choose another city under your control to supply."));
				}
				const std::string Target = CityLabel(State, Order.TargetCity);
				Check.Preview = LocF("order.preview.transport", "Deliver {gold} gold, {food} food and {troops} troops to {city}", {{"gold", ToText(std::max(0, Order.Gold))}, {"food", ToText(std::max(0, Order.Food))}, {"troops", ToText(std::max(0, Order.Troops))}, {"city", Target}});
				if (Order.Gold < 0 || Order.Food < 0 || Order.Troops < 0 || Order.Gold + Order.Food + Order.Troops <= 0)
				{
					return DenyCheck(Check, Loc("order.reason.transportEmpty", "Choose what to transport."));
				}
				if (Order.Gold > City.Gold)
				{
					return DenyCheck(Check, LocF("order.reason.transportGold", "{city} has only {amount} gold.", {{"city", Where}, {"amount", ToText(City.Gold)}}));
				}
				if (Order.Food > City.Food)
				{
					return DenyCheck(Check, LocF("order.reason.transportFood", "{city} has only {amount} food.", {{"city", Where}, {"amount", ToText(City.Food)}}));
				}
				if (Order.Troops > City.Troops)
				{
					return DenyCheck(Check, LocF("order.reason.transportTroops", "{city} has only {amount} troops.", {{"city", Where}, {"amount", ToText(City.Troops)}}));
				}
				std::vector<int> Path;
				int Tenths = 0;
				if (!FindRoute(State, Faction, Order.City, Order.TargetCity, Path, Tenths))
				{
					return DenyCheck(Check, LocF("order.reason.transportRoute", "There is no safe road from {city} to {target}.", {{"city", Where}, {"target", Target}}));
				}
				break;
			}
			case EOrderType::SectTraining:
			{
				Check.Cost = Balance::SectTrainingCost;
				if (!ValidSect(State, Order.TargetSect))
				{
					return DenyCheck(Check, Loc("order.reason.noSect", "Choose a sect."));
				}
				const FSect& Sect = At(State.Sects, Order.TargetSect);
				const std::vector<int> Near = SectsNearOf(State, Order.City);
				if (std::find(Near.begin(), Near.end(), Order.TargetSect) == Near.end())
				{
					return DenyCheck(Check, LocF("order.reason.sectFar", "The {sect} is too far from {city}.", {{"sect", NameOf(Sect)}, {"city", Where}}));
				}
				const std::vector<int> Learnable = OrdersDetail::LearnableTechniques(State, Order.Officer, Order.TargetSect);
				if (OrdersDetail::SectFavor(State, Order.TargetSect, Faction) >= Balance::SectTechniqueFavor && !Learnable.empty())
				{
					Check.SuccessChance = OrdersDetail::TechniqueChance(Officer);
					Check.Preview = LocF("order.preview.sectTechnique", "Martial experience +{exp}; learn a technique {chance}%", {{"exp", ToText(Balance::SectTrainingExp)}, {"chance", ToText(Check.SuccessChance)}});
				}
				else
				{
					Check.Preview = LocF("order.preview.sect", "Martial experience +{exp}", {{"exp", ToText(Balance::SectTrainingExp)}});
				}
				break;
			}
			case EOrderType::Alliance:
			case EOrderType::Truce:
			case EOrderType::Gift:
			{
				const int Target = Order.TargetFaction;
				if (!IsAliveFaction(State, Target) || Target == Faction)
				{
					return DenyCheck(Check, Loc("order.reason.noFaction", "Choose another faction."));
				}
				const std::string Theirs = FactionLabel(State, Target);
				if (Order.Type == EOrderType::Alliance)
				{
					Check.Cost = Balance::AllianceCost;
					Check.SuccessChance = AllianceChanceOf(State, Order.Officer, Faction, Target);
					Check.Preview = LocF("order.preview.chance", "Success {chance}%", {{"chance", ToText(Check.SuccessChance)}});
					if (State.AreAllied(Faction, Target))
					{
						return DenyCheck(Check, LocF("order.reason.allied", "You are already allied with the {faction}.", {{"faction", Theirs}}));
					}
				}
				else if (Order.Type == EOrderType::Truce)
				{
					Check.Cost = Balance::TruceCost;
					Check.SuccessChance = TruceChanceOf(State, Order.Officer, Faction, Target);
					Check.Preview = LocF("order.preview.chance", "Success {chance}%", {{"chance", ToText(Check.SuccessChance)}});
					if (State.AreAllied(Faction, Target))
					{
						return DenyCheck(Check, LocF("order.reason.allied", "You are already allied with the {faction}.", {{"faction", Theirs}}));
					}
					if (State.HaveTruce(Faction, Target))
					{
						return DenyCheck(Check, LocF("order.reason.truce", "A truce with the {faction} is already in force.", {{"faction", Theirs}}));
					}
				}
				else
				{
					Check.Cost = std::max(0, Order.Gold);
					Check.Preview = LocF("order.preview.gift", "Trust +{amount}", {{"amount", ToText(GiftTrustGain(Officer, Order.Gold))}});
					if (Order.Gold <= 0)
					{
						return DenyCheck(Check, Loc("order.reason.giftAmount", "Choose how much gold to send."));
					}
				}
				if (OrdersDetail::HasEnvoy(State, Faction, Target))
				{
					return DenyCheck(Check, LocF("order.reason.envoyBusy", "An envoy is already on the way to the {faction}.", {{"faction", Theirs}}));
				}
				break;
			}
			case EOrderType::Count:
				return DenyCheck(Check, Loc("order.reason.unknown", "Unknown order."));
			}
			if (City.Gold < Check.Cost)
			{
				return DenyCheck(Check, LocF("order.reason.noGold", "Not enough gold: {cost} needed, {gold} in {city}.", {{"cost", ToText(Check.Cost)}, {"gold", ToText(City.Gold)}, {"city", Where}}));
			}
			Check.bAllowed = true;
			Check.Reason.clear();
			return Check;
		}

		bool IssueOrderRules(FGameState& State, const FOrder& Order, std::string& OutError)
		{
			const FOrderCheck Check = CheckOrderRules(State, Order);
			if (!Check.bAllowed)
			{
				OutError = Check.Reason;
				return false;
			}
			FOrder Stored = Order;
			Stored.Cost = Check.Cost;
			FCity& City = At(State.Cities, Order.City);
			City.Gold -= Check.Cost;
			if (Order.Type == EOrderType::Transport)
			{
				// The convoy's cargo leaves the city now; it is refunded if the order is cancelled.
				City.Gold -= Order.Gold;
				City.Food -= Order.Food;
				City.Troops -= Order.Troops;
			}
			State.Orders.push_back(Stored);
			return true;
		}

		bool CancelOrderRules(FGameState& State, int Officer)
		{
			if (State.Phase != EPhase::Planning)
			{
				return false;
			}
			for (size_t Index = 0; Index < State.Orders.size(); ++Index)
			{
				const FOrder Order = State.Orders[Index];
				if (Order.Officer != Officer)
				{
					continue;
				}
				if (ValidCity(State, Order.City))
				{
					FCity& City = At(State.Cities, Order.City);
					City.Gold += Order.Cost;
					if (Order.Type == EOrderType::Transport)
					{
						City.Gold += std::max(0, Order.Gold);
						City.Food += std::max(0, Order.Food);
						City.Troops += std::max(0, Order.Troops);
					}
				}
				State.Orders.erase(State.Orders.begin() + static_cast<std::ptrdiff_t>(Index));
				return true;
			}
			return false;
		}

		void ExecuteOrders(FGameState& State)
		{
			const std::vector<FOrder> Orders = State.Orders;
			for (const FOrder& Order : Orders)
			{
				OrdersDetail::ExecuteOrder(State, Order);
			}
		}
	}

	// =============================================================================================
	// FGame: orders and immediate actions
	// =============================================================================================

	FOrderCheck FGame::CheckOrder(const FOrder& Order) const
	{
		if (!IsPlayerCity(Order.City))
		{
			FOrderCheck Check;
			Check.Reason = Loc("order.reason.notYourCity", "This city is not under your control.");
			return Check;
		}
		return GameRules::CheckOrderRules(State, Order);
	}

	bool FGame::IssueOrder(const FOrder& Order, std::string& OutError)
	{
		if (!IsPlayerCity(Order.City))
		{
			OutError = Loc("order.reason.notYourCity", "This city is not under your control.");
			return false;
		}
		return GameRules::IssueOrderRules(State, Order, OutError);
	}

	bool FGame::CancelOrder(int Officer)
	{
		if (!GameRules::ValidOfficer(State, Officer) || State.PlayerFaction < 0 || GameRules::At(State.Officers, Officer).Faction != State.PlayerFaction)
		{
			return false;
		}
		return GameRules::CancelOrderRules(State, Officer);
	}

	int FGame::FoodBuyPrice() const
	{
		return GameRules::FoodBuyPriceOf(State);
	}

	int FGame::FoodSellPrice() const
	{
		return GameRules::FoodSellPriceOf(State);
	}

	bool FGame::TradeFood(int City, int FoodDelta, std::string& OutError)
	{
		if (!IsPlayerCity(City))
		{
			OutError = Loc("order.reason.notYourCity", "This city is not under your control.");
			return false;
		}
		if (!GameRules::TradeFoodRules(State, City, FoodDelta, OutError))
		{
			return false;
		}
		const FCity& Data = GameRules::At(State.Cities, City);
		if (FoodDelta > 0)
		{
			GameRules::LogPlayer(State, LocF("log.market.buy", "Bought {amount} food in {city}. Gold left: {gold}.", {{"amount", ToText(FoodDelta)}, {"city", NameOf(Data)}, {"gold", ToText(Data.Gold)}}));
		}
		else
		{
			GameRules::LogPlayer(State, LocF("log.market.sell", "Sold {amount} food in {city}. Gold is now {gold}.", {{"amount", ToText(-FoodDelta)}, {"city", NameOf(Data)}, {"gold", ToText(Data.Gold)}}));
		}
		return true;
	}

	int FGame::RewardLoyaltyGain(int Gold) const
	{
		return GameRules::RewardLoyaltyGain(Gold);
	}

	bool FGame::RewardOfficer(int Officer, int Gold, std::string& OutError)
	{
		if (State.Phase != EPhase::Planning)
		{
			OutError = Loc("reward.reason.notPlanning", "Rewards can only be given during the planning phase.");
			return false;
		}
		if (!GameRules::ValidOfficer(State, Officer) || State.PlayerFaction < 0)
		{
			OutError = Loc("reward.reason.noOfficer", "Choose an officer.");
			return false;
		}
		FOfficer& Data = GameRules::At(State.Officers, Officer);
		if (Data.Status != EOfficerStatus::Serving || Data.Faction != State.PlayerFaction)
		{
			OutError = LocF("reward.reason.notServing", "{officer} does not serve you.", {{"officer", NameOf(Data)}});
			return false;
		}
		if (State.IsRuler(Officer))
		{
			OutError = Loc("reward.reason.ruler", "Your ruler needs no reward.");
			return false;
		}
		if (Data.Army >= 0 || !IsPlayerCity(Data.City))
		{
			OutError = LocF("reward.reason.away", "{officer} is away with the army.", {{"officer", NameOf(Data)}});
			return false;
		}
		if (Data.Loyalty >= 100)
		{
			OutError = LocF("reward.reason.loyal", "{officer} is already completely loyal.", {{"officer", NameOf(Data)}});
			return false;
		}
		if (GameRules::RewardLoyaltyGain(Gold) <= 0)
		{
			OutError = Loc("reward.reason.amount", "Offer at least 20 gold.");
			return false;
		}
		FCity& City = GameRules::At(State.Cities, Data.City);
		if (City.Gold < Gold)
		{
			OutError = LocF("order.reason.noGold", "Not enough gold: {cost} needed, {gold} in {city}.", {{"cost", ToText(Gold)}, {"gold", ToText(City.Gold)}, {"city", NameOf(City)}});
			return false;
		}
		City.Gold -= Gold;
		Data.Loyalty = std::min(100, Data.Loyalty + GameRules::RewardLoyaltyGain(Gold));
		GameRules::LogPlayer(State, LocF("log.reward", "{officer} gratefully accepts {gold} gold. Loyalty is now {loyalty}.", {{"officer", NameOf(Data)}, {"gold", ToText(Gold)}, {"loyalty", ToText(Data.Loyalty)}}));
		return true;
	}

	bool FGame::DonateToSect(int City, int Sect, int Gold, std::string& OutError)
	{
		if (State.Phase != EPhase::Planning)
		{
			OutError = Loc("donate.reason.notPlanning", "Donations can only be made during the planning phase.");
			return false;
		}
		if (!IsPlayerCity(City))
		{
			OutError = Loc("order.reason.notYourCity", "This city is not under your control.");
			return false;
		}
		const std::vector<int> Near = GameRules::SectsNearOf(State, City);
		if (!GameRules::ValidSect(State, Sect) || std::find(Near.begin(), Near.end(), Sect) == Near.end())
		{
			OutError = Loc("donate.reason.noSect", "There is no such sect near this city.");
			return false;
		}
		if (Gold < 20)
		{
			OutError = Loc("donate.reason.amount", "Donate at least 20 gold.");
			return false;
		}
		FCity& Data = GameRules::At(State.Cities, City);
		if (Data.Gold < Gold)
		{
			OutError = LocF("order.reason.noGold", "Not enough gold: {cost} needed, {gold} in {city}.", {{"cost", ToText(Gold)}, {"gold", ToText(Data.Gold)}, {"city", NameOf(Data)}});
			return false;
		}
		Data.Gold -= Gold;
		GameRules::OrdersDetail::AddSectFavor(State, Sect, State.PlayerFaction, Gold / 20);
		const FSect& SectData = GameRules::At(State.Sects, Sect);
		GameRules::LogPlayer(State, LocF("log.donate", "The {sect} thanks you for the donation of {gold} gold. Their favor toward you is now {favor}.", {{"sect", NameOf(SectData)}, {"gold", ToText(Gold)}, {"favor", ToText(GameRules::OrdersDetail::SectFavor(State, Sect, State.PlayerFaction))}}));
		return true;
	}

	void FGame::SetDelegated(int City, bool bDelegated)
	{
		if (!IsPlayerCity(City))
		{
			return;
		}
		FCity& Data = GameRules::At(State.Cities, City);
		const bool bWasDelegated = Data.bDelegated;
		Data.bDelegated = bDelegated;
		if (bDelegated && !bWasDelegated && State.Phase == EPhase::Planning)
		{
			GameRules::PlanDelegatedCity(State, City);
		}
	}

	bool FGame::CanDecidePrisoner(int Prisoner) const
	{
		if (!GameRules::ValidOfficer(State, Prisoner) || State.PlayerFaction < 0 || State.Phase == EPhase::GameOver)
		{
			return false;
		}
		const FOfficer& Data = GameRules::At(State.Officers, Prisoner);
		return Data.Status == EOfficerStatus::Prisoner && Data.Captor == State.PlayerFaction;
	}

	int FGame::PrisonerRecruitChance(int Prisoner) const
	{
		return GameRules::PrisonerRecruitChanceOf(State, Prisoner, State.PlayerFaction);
	}

	bool FGame::DecidePrisoner(int Prisoner, EPrisonerDecision Decision, std::string& OutMessage)
	{
		if (!CanDecidePrisoner(Prisoner))
		{
			OutMessage = Loc("prisoner.reason.invalid", "This prisoner is not in your custody.");
			return false;
		}
		FOfficer& Data = GameRules::At(State.Officers, Prisoner);
		const std::string Who = NameOf(Data);
		const int Former = Data.Faction;
		GameRules::RemovePendingPrisoner(State, Prisoner);
		switch (Decision)
		{
		case EPrisonerDecision::Recruit:
		{
			// One attempt per prisoner per month: the roll does not change when retried.
			uint32_t Hash = HashCombine(static_cast<uint32_t>(State.Year * 12 + State.Month), static_cast<uint32_t>(Prisoner));
			Hash = HashCombine(Hash, static_cast<uint32_t>(State.PlayerFaction + 7 * State.StartYear));
			const int Roll = static_cast<int>(Hash % 100u);
			if (Roll < PrisonerRecruitChance(Prisoner))
			{
				GameRules::JoinFaction(State, Prisoner, State.PlayerFaction, Data.City, 55 + static_cast<int>((Hash >> 8) % 16u));
				if (GameRules::ValidFaction(State, Former))
				{
					FRelation& Relation = State.Relation(State.PlayerFaction, Former);
					Relation.Trust = ClampInt(Relation.Trust - 3, 0, 100);
				}
				OutMessage = LocF("prisoner.recruited", "{officer} kneels and swears to serve you.", {{"officer", Who}});
			}
			else
			{
				OutMessage = LocF("prisoner.refused", "{officer} refuses to serve you and remains in prison.", {{"officer", Who}});
			}
			break;
		}
		case EPrisonerDecision::Release:
		{
			if (GameRules::ValidFaction(State, Former))
			{
				FRelation& Relation = State.Relation(State.PlayerFaction, Former);
				Relation.Trust = ClampInt(Relation.Trust + GameRules::Balance::ReleaseTrustGain, 0, 100);
			}
			GameRules::ReleasePrisoner(State, Prisoner);
			OutMessage = LocF("prisoner.released", "{officer} has been released.", {{"officer", Who}});
			break;
		}
		case EPrisonerDecision::Execute:
		{
			GameRules::KillOfficer(State, Prisoner);
			for (int Faction = 0; Faction < GameRules::CountOf(State.Factions); ++Faction)
			{
				if (Faction != State.PlayerFaction && GameRules::IsAliveFaction(State, Faction))
				{
					FRelation& Relation = State.Relation(State.PlayerFaction, Faction);
					Relation.Trust = ClampInt(Relation.Trust - GameRules::Balance::ExecuteTrustLoss, 0, 100);
				}
			}
			for (const int Officer : GameRules::ServingOfficers(State, State.PlayerFaction))
			{
				if (!State.IsRuler(Officer))
				{
					FOfficer& Member = GameRules::At(State.Officers, Officer);
					Member.Loyalty = std::max(0, Member.Loyalty - 2);
				}
			}
			OutMessage = LocF("prisoner.executed", "{officer} has been executed. The realm takes note of your harshness.", {{"officer", Who}});
			break;
		}
		case EPrisonerDecision::Imprison:
			OutMessage = LocF("prisoner.imprisoned", "{officer} remains in prison.", {{"officer", Who}});
			break;
		}
		GameRules::LogPlayer(State, OutMessage);
		return true;
	}

	std::string FGame::TavernRumor(int City) const
	{
		if (!GameRules::ValidCity(State, City))
		{
			return std::string();
		}
		const uint32_t Seed = HashCombine(static_cast<uint32_t>(State.Year * 12 + State.Month), static_cast<uint32_t>(City));
		std::vector<int> Near = State.Neighbors(City);
		Near.push_back(City);
		std::vector<int> Hidden;
		std::vector<int> Free;
		for (int Officer = 0; Officer < GameRules::CountOf(State.Officers); ++Officer)
		{
			const FOfficer& Data = GameRules::At(State.Officers, Officer);
			if (Data.Status == EOfficerStatus::Hidden && std::find(Near.begin(), Near.end(), Data.City) != Near.end())
			{
				Hidden.push_back(Officer);
			}
			else if (Data.Status == EOfficerStatus::Free && Data.City == City)
			{
				Free.push_back(Officer);
			}
		}
		if (!Hidden.empty() && (Seed % 3u) != 0u)
		{
			const int Officer = Hidden[(Seed >> 4) % Hidden.size()];
			return GameRules::OrdersDetail::HiddenRumor(State, Officer, GameRules::At(State.Officers, Officer).City);
		}
		if (!Free.empty())
		{
			const int Officer = Free[(Seed >> 8) % Free.size()];
			return LocF("rumor.free", "{officer} has been drinking here for days, waiting for a lord worth serving.", {{"officer", GameRules::OfficerLabel(State, Officer)}});
		}
		if (!Hidden.empty())
		{
			const int Officer = Hidden[(Seed >> 4) % Hidden.size()];
			return GameRules::OrdersDetail::HiddenRumor(State, Officer, GameRules::At(State.Officers, Officer).City);
		}
		// Realm news: the strongest power and the largest army near the city.
		int Strongest = -1;
		int StrongestCities = 0;
		for (int Faction = 0; Faction < GameRules::CountOf(State.Factions); ++Faction)
		{
			const int Count = CityCount(Faction);
			if (GameRules::IsAliveFaction(State, Faction) && Count > StrongestCities)
			{
				Strongest = Faction;
				StrongestCities = Count;
			}
		}
		int Threat = -1;
		for (const int Neighbor : State.Neighbors(City))
		{
			const FCity& Data = GameRules::At(State.Cities, Neighbor);
			if (Data.Owner >= 0 && Data.Owner != State.PlayerFaction && (Threat < 0 || Data.Troops > GameRules::At(State.Cities, Threat).Troops))
			{
				Threat = Neighbor;
			}
		}
		if (Threat >= 0 && (Seed % 2u) == 0u)
		{
			const FCity& Data = GameRules::At(State.Cities, Threat);
			return LocF("rumor.threat", "Merchants from {city} say the {faction} keeps about {troops} soldiers there.", {{"city", NameOf(Data)}, {"faction", GameRules::FactionLabel(State, Data.Owner)}, {"troops", ToText(Data.Troops / 1000 * 1000)}});
		}
		if (Strongest >= 0)
		{
			return LocF("rumor.strongest", "Travelers say the {faction} is the greatest power in the realm, holding {count} cities.", {{"faction", GameRules::FactionLabel(State, Strongest)}, {"count", ToText(StrongestCities)}});
		}
		return Loc("rumor.quiet", "The tavern is quiet tonight. Nobody has news worth hearing.");
	}
}
