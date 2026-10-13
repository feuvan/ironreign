#include "Sim/IronGame.h"

#include "Sim/IronGameInternal.h"
#include "Sim/IronLocale.h"

#include <algorithm>

namespace IronSim
{
	namespace GameRules
	{
		namespace MonthDetail
		{
			void CollectIncome(FGameState& State)
			{
				int PlayerIncome = 0;
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					FCity& Data = At(State.Cities, City);
					if (Data.Owner < 0)
					{
						continue;
					}
					const int Income = CityGoldIncome(State, City);
					Data.Gold += Income;
					if (IsPlayerFaction(State, Data.Owner))
					{
						PlayerIncome += Income;
					}
				}
				if (State.PlayerFaction >= 0 && PlayerIncome > 0)
				{
					LogPlayer(State, LocF("log.month.income", "Your cities collected {gold} gold in taxes.", {{"gold", ToText(PlayerIncome)}}));
				}
			}

			void PayUpkeep(FGameState& State)
			{
				std::vector<int> Unpaid(State.Cities.size(), 0);
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					FOfficer& Data = At(State.Officers, Officer);
					if (Data.Status != EOfficerStatus::Serving)
					{
						continue;
					}
					int Payer = Data.City;
					if (Data.Army >= 0)
					{
						const FArmy* Army = State.FindArmy(Data.Army);
						Payer = Army ? Army->Home : -1;
					}
					if (!ValidCity(State, Payer) || At(State.Cities, Payer).Owner != Data.Faction)
					{
						Payer = NearestOwnedCity(State, Data.Faction, -1);
					}
					if (!ValidCity(State, Payer))
					{
						continue;
					}
					FCity& City = At(State.Cities, Payer);
					if (City.Gold >= Balance::OfficerUpkeep)
					{
						City.Gold -= Balance::OfficerUpkeep;
					}
					else
					{
						City.Gold = 0;
						if (!State.IsRuler(Officer))
						{
							Data.Loyalty = std::max(0, Data.Loyalty - 2);
						}
						++At(Unpaid, Payer);
					}
				}
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					if (At(Unpaid, City) > 0 && IsPlayerFaction(State, At(State.Cities, City).Owner))
					{
						LogPlayer(State, LocF("log.month.unpaid", "{city} could not pay {count} of its officers. Their loyalty suffers.", {{"city", CityLabel(State, City)}, {"count", ToText(At(Unpaid, City))}}), true);
					}
				}
			}

			void FeedGarrisons(FGameState& State)
			{
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					FCity& Data = At(State.Cities, City);
					const int Need = GarrisonFood(Data.Troops);
					if (Data.Food >= Need)
					{
						Data.Food -= Need;
						continue;
					}
					Data.Food = 0;
					const int Deserters = Data.Troops * Balance::ShortageDesertionPercent / 100;
					Data.Troops -= Deserters;
					Data.Order = std::max(0, Data.Order - Balance::ShortageOrderLoss);
					if (IsPlayerFaction(State, Data.Owner))
					{
						LogPlayer(State, LocF("log.month.starving", "{city} has run out of food! {count} soldiers deserted and public order fell.", {{"city", NameOf(Data)}, {"count", ToText(Deserters)}}), true);
					}
				}
			}

			void GrowCities(FGameState& State)
			{
				for (FCity& City : State.Cities)
				{
					if (City.Order >= 20)
					{
						const long long Gap = std::max(0, City.PopulationMax - City.Population);
						City.Population += static_cast<int>(Gap * (City.Order - 20) / 4000);
					}
					else
					{
						City.Population -= City.Population * (20 - City.Order) / 2000;
					}
					City.Population = ClampInt(City.Population, 0, City.PopulationMax);
					if (City.Order > Balance::OrderDecayAbove)
					{
						--City.Order;
					}
				}
			}

			void Harvest(FGameState& State)
			{
				int PlayerFood = 0;
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					FCity& Data = At(State.Cities, City);
					const int Yield = CityHarvest(State, City);
					Data.Food += Yield;
					if (IsPlayerFaction(State, Data.Owner))
					{
						PlayerFood += Yield;
					}
				}
				if (State.PlayerFaction >= 0)
				{
					LogPlayer(State, LocF("log.month.harvest", "The autumn harvest is in: your cities gathered {food} food.", {{"food", ToText(PlayerFood)}}), true);
				}
			}

			void AgeOfficers(FGameState& State)
			{
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					const FOfficer& Data = At(State.Officers, Officer);
					if (Data.Status == EOfficerStatus::Dead || Data.Status == EOfficerStatus::Unborn)
					{
						continue;
					}
					const int Age = State.OfficerAge(Officer);
					if (Age < 60 || State.Rng.Range(0, 999) >= (Age - 55) / 2)
					{
						continue;
					}
					const int Faction = Data.Status == EOfficerStatus::Serving ? Data.Faction : -1;
					const bool bRuler = State.IsRuler(Officer);
					const std::string Name = NameOf(Data);
					if (IsPlayerFaction(State, Faction))
					{
						LogPlayer(State, LocF("log.officer.diedOld", "{officer} has died of old age at {age}.", {{"officer", Name}, {"age", ToText(Age)}}), true);
					}
					else if (bRuler)
					{
						LogWorld(State, LocF("log.ruler.died", "{officer}, ruler of the {faction}, has died at the age of {age}.", {{"officer", Name}, {"faction", FactionLabel(State, Faction)}, {"age", ToText(Age)}}), true);
					}
					KillOfficer(State, Officer);
				}
			}

			int LoyaltyTarget(const FGameState& State, const FOfficer& Officer)
			{
				const int Ruler = RulerOf(State, Officer.Faction);
				if (Ruler < 0)
				{
					return 50;
				}
				const FOfficer& Lord = At(State.Officers, Ruler);
				const int Distance = AffinityDistance(Officer.Affinity, Lord.Affinity);
				return ClampInt(50 + StatOf(Lord, EStat::Charm) / 5 - Distance / 3 - (Officer.Ambition - 50) / 5 + std::min(10, Officer.Merit / 200), 20, 95);
			}

			void UpdateLoyalty(FGameState& State)
			{
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					FOfficer& Data = At(State.Officers, Officer);
					if (Data.Status != EOfficerStatus::Serving)
					{
						continue;
					}
					if (State.IsRuler(Officer))
					{
						Data.Loyalty = 100;
						continue;
					}
					const int Target = LoyaltyTarget(State, Data);
					if (Data.Loyalty < Target)
					{
						++Data.Loyalty;
					}
					else if (Data.Loyalty > Target)
					{
						--Data.Loyalty;
					}
					// Ambitious, disloyal officers may leave.
					if (Data.Army >= 0 || Data.Loyalty >= 40 || Data.Ambition < 40)
					{
						continue;
					}
					const int Chance = (40 - Data.Loyalty) / 2 + (Data.Ambition - 40) / 10;
					if (!State.Rng.Chance(Chance))
					{
						continue;
					}
					const int Faction = Data.Faction;
					const int City = Data.City;
					if (IsPlayerFaction(State, Faction))
					{
						LogPlayer(State, LocF("log.officer.deserted", "{officer} has lost faith in your cause and left your service in {city}.", {{"officer", NameOf(Data)}, {"city", CityLabel(State, City)}}), true);
					}
					SetFree(State, Officer, City);
				}
			}

			void WanderFreeOfficers(FGameState& State)
			{
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					FOfficer& Data = At(State.Officers, Officer);
					if (Data.Status != EOfficerStatus::Free || !State.Rng.Chance(15))
					{
						continue;
					}
					const std::vector<int> Neighbors = State.Neighbors(Data.City);
					if (!Neighbors.empty())
					{
						Data.City = Neighbors[static_cast<size_t>(State.Rng.Range(0, CountOf(Neighbors) - 1))];
					}
				}
			}

			void PrisonerEscapes(FGameState& State)
			{
				for (int Officer = 0; Officer < CountOf(State.Officers); ++Officer)
				{
					const FOfficer& Data = At(State.Officers, Officer);
					if (Data.Status != EOfficerStatus::Prisoner || !State.Rng.Chance(Balance::PrisonerEscapeChance))
					{
						continue;
					}
					const int Captor = Data.Captor;
					const int Home = Data.Faction;
					const std::string Name = NameOf(Data);
					const std::string Where = CityLabel(State, Data.City);
					ReleasePrisoner(State, Officer);
					if (IsPlayerFaction(State, Captor))
					{
						LogPlayer(State, LocF("log.prisoner.escaped", "{officer} has escaped from prison in {city}.", {{"officer", Name}, {"city", Where}}), true);
					}
					else if (IsPlayerFaction(State, Home) && At(State.Officers, Officer).Status == EOfficerStatus::Serving)
					{
						LogPlayer(State, LocF("log.prisoner.returned", "{officer} has escaped captivity in {city} and returned to your service.", {{"officer", Name}, {"city", Where}}), true);
					}
				}
			}

			void UpdateDiplomacy(FGameState& State)
			{
				const int Count = CountOf(State.Factions);
				for (int A = 0; A < Count; ++A)
				{
					for (int B = A + 1; B < Count; ++B)
					{
						FRelation& Relation = State.Relation(A, B);
						if (!IsAliveFaction(State, A) || !IsAliveFaction(State, B))
						{
							Relation.AllianceMonths = 0;
							Relation.TruceMonths = 0;
							continue;
						}
						const std::string NameA = FactionLabel(State, A);
						const std::string NameB = FactionLabel(State, B);
						if (Relation.AllianceMonths > 0)
						{
							--Relation.AllianceMonths;
							Relation.Trust = std::min(100, Relation.Trust + 1);
							if (Relation.AllianceMonths == 0)
							{
								LogBetween(State, A, B, LocF("log.diplomacy.allianceEnded", "The alliance between the {a} and the {b} has expired.", {{"a", NameA}, {"b", NameB}}), true);
							}
						}
						else if (Relation.Trust > 60 && State.Rng.Chance(25))
						{
							--Relation.Trust;
						}
						else if (Relation.Trust < 30 && State.Rng.Chance(25))
						{
							++Relation.Trust;
						}
						if (Relation.TruceMonths > 0)
						{
							--Relation.TruceMonths;
							if (Relation.TruceMonths == 0 && Relation.AllianceMonths == 0)
							{
								LogBetween(State, A, B, LocF("log.diplomacy.truceEnded", "The truce between the {a} and the {b} has ended.", {{"a", NameA}, {"b", NameB}}), true);
							}
						}
					}
				}
			}
		}

		int MonthsUntilHarvest(int Month)
		{
			const int Months = (Balance::HarvestMonth - ClampInt(Month, 1, 12) + 12) % 12;
			return Months == 0 ? 12 : Months;
		}

		void EndMonthRules(FGameState& State)
		{
			State.Orders.clear();
			MonthDetail::CollectIncome(State);
			MonthDetail::PayUpkeep(State);
			MonthDetail::FeedGarrisons(State);
			MonthDetail::GrowCities(State);

			++State.Month;
			if (State.Month > 12)
			{
				State.Month = 1;
				++State.Year;
			}
			State.Day = 0;
			if (State.Month == Balance::HarvestMonth)
			{
				MonthDetail::Harvest(State);
			}

			MonthDetail::AgeOfficers(State);
			MonthDetail::UpdateLoyalty(State);
			MonthDetail::WanderFreeOfficers(State);
			RevealDueOfficers(State);
			MonthDetail::PrisonerEscapes(State);
			DecideAIPrisoners(State);
			MonthDetail::UpdateDiplomacy(State);
			UpdateFactions(State);
			if (State.Phase == EPhase::GameOver)
			{
				return;
			}
			BeginPlanning(State);
		}

		void BeginPlanning(FGameState& State)
		{
			State.Phase = EPhase::Planning;
			State.Day = 0;
			State.bDayInProgress = false;
			State.BattleQueue.clear();
			State.Orders.clear();
			CheckEventsRules(State);
			PlanAllAI(State);
		}
	}
}
