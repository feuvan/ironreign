#include "Sim/IronGame.h"

#include "Sim/IronGameInternal.h"
#include "Sim/IronLocale.h"

#include <algorithm>

namespace IronSim
{
	namespace GameRules
	{
		namespace AIDetail
		{
			/** Military situation of one city, as the AI governor sees it. */
			struct FCityPlan
			{
				int City = -1;
				/** Borders a hostile faction or an independent city. */
				bool bFrontier = false;
				/** Strongest hostile faction garrison next door plus hostile armies marching on the city. */
				int Threat = 0;
				/** Troops kept home when an army marches out. */
				int Reserve = 0;
				/** Garrison size the governor drafts toward. */
				int TroopTarget = 0;
			};

			long long Power(int Troops, int Training, int BestCommand)
			{
				return static_cast<long long>(std::max(0, Troops)) * (50 + Training) / 100 * (80 + BestCommand / 2) / 100;
			}

			int BestCommandIn(const FGameState& State, int City, int Faction)
			{
				int Best = Balance::GarrisonUnitStat;
				for (const int Officer : OfficersInCity(State, City, Faction))
				{
					Best = std::max(Best, StatOf(At(State.Officers, Officer), EStat::Command));
				}
				return Best;
			}

			long long CityDefensePower(const FGameState& State, int City)
			{
				const FCity& Data = At(State.Cities, City);
				const long long Base = Power(Data.Troops, Data.Training, BestCommandIn(State, City, Data.Owner));
				return Base * (100 + Data.Defense / 40) / 100;
			}

			int MilitaryScore(const FOfficer& Officer)
			{
				return StatOf(Officer, EStat::Command) * 2 + StatOf(Officer, EStat::Martial) + StatOf(Officer, EStat::Strategy);
			}

			FCityPlan AnalyzeCity(const FGameState& State, int City, int Faction, int IgnoreCity)
			{
				FCityPlan Plan;
				Plan.City = City;
				bool bFactionThreat = false;
				for (const int Neighbor : State.Neighbors(City))
				{
					const FCity& Data = At(State.Cities, Neighbor);
					if (Data.Owner == Faction || !State.AreHostile(Faction, Data.Owner))
					{
						continue;
					}
					Plan.bFrontier = true;
					if (Data.Owner >= 0 && Neighbor != IgnoreCity)
					{
						bFactionThreat = true;
						Plan.Threat = std::max(Plan.Threat, Data.Troops);
					}
				}
				const int Incoming = IncomingHostileTroops(State, City, Faction);
				Plan.Threat += Incoming;
				bFactionThreat = bFactionThreat || Incoming > 0;
				Plan.Reserve = bFactionThreat ? std::max(2000, Plan.Threat * 2 / 3) : (Plan.bFrontier ? 2000 : 1000);
				Plan.TroopTarget = bFactionThreat ? std::max(6000, Plan.Threat * 6 / 5) : (Plan.bFrontier ? 6000 : 3000);
				return Plan;
			}

			/** True if City can feed Troops until the next harvest (plus a margin) and the harvest roughly covers a year. */
			bool CanFeed(const FGameState& State, int City, int Troops)
			{
				const FCity& Data = At(State.Cities, City);
				const int Monthly = GarrisonFood(Troops);
				if (Data.Food < Monthly * (MonthsUntilHarvest(State.Month) + 2))
				{
					return false;
				}
				return static_cast<long long>(CityHarvest(State, City)) * 13 / 10 >= static_cast<long long>(Monthly) * 12;
			}

			int GoldReserve(const FGameState& State, int City)
			{
				const FCity& Data = At(State.Cities, City);
				return 100 + CountOf(OfficersInCity(State, City, Data.Owner)) * Balance::OfficerUpkeep * 2;
			}

			std::vector<int> IdleOfficersIn(const FGameState& State, int City, int Faction)
			{
				std::vector<int> Result;
				for (const int Officer : OfficersInCity(State, City, Faction))
				{
					if (State.OfficerOrder(Officer) == nullptr)
					{
						Result.push_back(Officer);
					}
				}
				return Result;
			}

			/** Removes and returns the officer of Pool with the best value of Score. */
			template <typename ScoreType>
			int TakeBest(std::vector<int>& Pool, const FGameState& State, ScoreType Score)
			{
				if (Pool.empty())
				{
					return -1;
				}
				size_t Best = 0;
				for (size_t Index = 1; Index < Pool.size(); ++Index)
				{
					if (Score(At(State.Officers, Pool[Index])) > Score(At(State.Officers, Pool[Best])))
					{
						Best = Index;
					}
				}
				const int Officer = Pool[Best];
				Pool.erase(Pool.begin() + static_cast<std::ptrdiff_t>(Best));
				return Officer;
			}

			bool Issue(FGameState& State, const FOrder& Order)
			{
				std::string Error;
				return IssueOrderRules(State, Order, Error);
			}

			FOrder MakeOrder(EOrderType Type, int Officer, int City)
			{
				FOrder Order;
				Order.Type = Type;
				Order.Officer = Officer;
				Order.City = City;
				return Order;
			}

			void RewardOfficers(FGameState& State, int City, int Faction)
			{
				int Rewards = 0;
				for (const int Officer : OfficersInCity(State, City, Faction))
				{
					FOfficer& Data = At(State.Officers, Officer);
					FCity& Treasury = At(State.Cities, City);
					if (Rewards >= 2 || State.IsRuler(Officer) || Data.Loyalty >= 65 || Treasury.Gold < GoldReserve(State, City) + 300)
					{
						continue;
					}
					Treasury.Gold -= 100;
					Data.Loyalty = std::min(100, Data.Loyalty + RewardLoyaltyGain(100));
					++Rewards;
				}
			}

			void TradeFood(FGameState& State, int City)
			{
				FCity& Data = At(State.Cities, City);
				const int Monthly = std::max(1, GarrisonFood(Data.Troops));
				const int Need = Monthly * (MonthsUntilHarvest(State.Month) + 2);
				std::string Error;
				if (Data.Food < Need)
				{
					const int Spare = Data.Gold - GoldReserve(State, City);
					const int Affordable = Spare > 0 ? Spare * 7 / 10 * 100 / FoodBuyPriceOf(State) : 0;
					const int Amount = std::min(Need - Data.Food, Affordable) / 100 * 100;
					if (Amount >= 100)
					{
						TradeFoodRules(State, City, Amount, Error);
					}
				}
				else if (Data.Food > Monthly * 30 + 20000 && Data.Gold < 400)
				{
					const int Amount = (Data.Food - Monthly * 20) / 100 * 100;
					if (Amount >= 100)
					{
						TradeFoodRules(State, City, -Amount, Error);
					}
				}
			}

			bool AlreadyTargeted(const FGameState& State, int Faction, int Target)
			{
				for (const FArmy& Army : State.Armies)
				{
					if (Army.Faction == Faction && Army.Target == Target && Army.State == EArmyState::Marching)
					{
						return true;
					}
				}
				return false;
			}

			bool TryAttack(FGameState& State, int City, int Faction)
			{
				const FCity& Data = At(State.Cities, City);
				if (Data.Troops < 3000)
				{
					return false;
				}
				std::vector<int> Officers = IdleOfficersIn(State, City, Faction);
				Officers.erase(std::remove_if(Officers.begin(), Officers.end(), [&State](int Officer) { return State.IsRuler(Officer); }), Officers.end());
				if (Officers.empty())
				{
					return false;
				}
				std::stable_sort(Officers.begin(), Officers.end(), [&State](int Left, int Right) {
					return MilitaryScore(At(State.Officers, Left)) > MilitaryScore(At(State.Officers, Right));
				});
				// Leave someone at home to govern when possible.
				const int MaxOfficers = std::min(MaxArmyUnits, CountOf(Officers) > 1 ? CountOf(Officers) - 1 : 1);
				const int Ratio = Balance::AIAttackRatioPercent[ClampInt(static_cast<int>(State.Difficulty), 0, 2)];

				int BestTarget = -1;
				long long BestScore = 0;
				std::vector<int> BestOfficers;
				int BestTroops = 0;
				for (const int Target : MarchTargetsOf(State, City, Faction))
				{
					const int Owner = At(State.Cities, Target).Owner;
					if (Owner == Faction || AlreadyTargeted(State, Faction, Target))
					{
						continue;
					}
					std::vector<int> Path;
					int Tenths = 0;
					if (!FindRoute(State, Faction, City, Target, Path, Tenths) || Tenths > 300)
					{
						continue;
					}
					const FCityPlan Plan = AnalyzeCity(State, City, Faction, Target);
					const int Available = Data.Troops - Plan.Reserve;
					if (Available < 2000)
					{
						continue;
					}
					std::vector<int> Chosen;
					long long Capacity = 0;
					for (int Index = 0; Index < MaxOfficers && Capacity < Available; ++Index)
					{
						Chosen.push_back(At(Officers, Index));
						Capacity += MaxUnitTroopsOf(State, At(Officers, Index));
					}
					const int Troops = static_cast<int>(std::min<long long>(Available, Capacity));
					const long long Attack = Power(Troops, Data.Training, StatOf(At(State.Officers, Chosen.front()), EStat::Command));
					const long long Defense = std::max<long long>(1, CityDefensePower(State, Target));
					const long long Score = Attack * 100 / Defense;
					if (Score < Ratio)
					{
						continue;
					}
					// Prefer short marches and weak targets.
					const long long Weighted = Score * 300 / (300 + Tenths);
					if (Weighted > BestScore)
					{
						BestScore = Weighted;
						BestTarget = Target;
						BestOfficers = Chosen;
						BestTroops = Troops;
					}
				}
				if (BestTarget < 0)
				{
					return false;
				}
				std::vector<int> Path;
				int Tenths = 0;
				FindRoute(State, Faction, City, BestTarget, Path, Tenths);
				const int Days = (Tenths + 9) / 10;
				const int Daily = ArmyFoodPerDay(BestTroops);
				const int HomeNeed = GarrisonFood(Data.Troops - BestTroops) * 2;
				int Food = Daily * (Days + 20);
				Food = std::min(Food, Data.Food - HomeNeed);
				if (Food < Daily * (Days + 5))
				{
					return false;
				}
				FArmyPlan Army;
				Army.City = City;
				Army.Officers = BestOfficers;
				Army.Troops = BestTroops;
				Army.Food = Food;
				Army.Target = BestTarget;
				std::string Error;
				return FormArmyRules(State, Army, Error) > 0;
			}

			void PlanLogistics(FGameState& State, int Faction, const std::vector<int>& Controlled)
			{
				std::vector<FCityPlan> Plans;
				for (const int City : Controlled)
				{
					Plans.push_back(AnalyzeCity(State, City, Faction, -1));
				}
				// Interior cities send surplus troops (and spare gold) to the frontier city that needs them most.
				for (const FCityPlan& Source : Plans)
				{
					if (Source.bFrontier)
					{
						continue;
					}
					FCity& Data = At(State.Cities, Source.City);
					const int Surplus = Data.Troops - 2000;
					std::vector<int> Idle = IdleOfficersIn(State, Source.City, Faction);
					if (Surplus < 1000 || Idle.empty())
					{
						continue;
					}
					int Best = -1;
					int BestNeed = 0;
					for (const FCityPlan& Destination : Plans)
					{
						const int Need = Destination.TroopTarget - At(State.Cities, Destination.City).Troops;
						if (!Destination.bFrontier || Need <= BestNeed)
						{
							continue;
						}
						std::vector<int> Path;
						int Tenths = 0;
						if (FindRoute(State, Faction, Source.City, Destination.City, Path, Tenths))
						{
							Best = Destination.City;
							BestNeed = Need;
						}
					}
					if (Best < 0)
					{
						continue;
					}
					const int Courier = TakeBest(Idle, State, [](const FOfficer& Officer) { return -StatOf(Officer, EStat::Politics); });
					FOrder Order = MakeOrder(EOrderType::Transport, Courier, Source.City);
					Order.TargetCity = Best;
					Order.Troops = std::min(Surplus, std::max(1000, BestNeed));
					const int FoodKeep = GarrisonFood(Data.Troops - Order.Troops) * (MonthsUntilHarvest(State.Month) + 3);
					Order.Food = std::max(0, std::min(Data.Food - FoodKeep, GarrisonFood(Order.Troops) * 6));
					Order.Gold = Data.Gold > 1500 ? Data.Gold - 1000 : 0;
					Issue(State, Order);
				}
				// Every city needs a governor; crowded cities lend officers to empty ones.
				for (const int Target : Controlled)
				{
					if (!OfficersInCity(State, Target, Faction).empty())
					{
						continue;
					}
					int Donor = -1;
					int DonorIdle = 2;
					for (const int City : Controlled)
					{
						const int Count = CountOf(IdleOfficersIn(State, City, Faction));
						if (City != Target && Count > DonorIdle)
						{
							Donor = City;
							DonorIdle = Count;
						}
					}
					if (Donor < 0)
					{
						continue;
					}
					std::vector<int> Idle = IdleOfficersIn(State, Donor, Faction);
					Idle.erase(std::remove_if(Idle.begin(), Idle.end(), [&State](int Officer) { return State.IsRuler(Officer); }), Idle.end());
					const int Mover = TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Politics) + StatOf(Officer, EStat::Command); });
					if (Mover >= 0)
					{
						FOrder Order = MakeOrder(EOrderType::Move, Mover, Donor);
						Order.TargetCity = Target;
						Issue(State, Order);
					}
				}
				// Frontier cities facing a faction get military officers from quiet cities with several officers.
				for (const FCityPlan& Destination : Plans)
				{
					if (!Destination.bFrontier || Destination.Threat <= 0 || CountOf(OfficersInCity(State, Destination.City, Faction)) >= 3)
					{
						continue;
					}
					for (const FCityPlan& Source : Plans)
					{
						if (Source.bFrontier || Source.City == Destination.City)
						{
							continue;
						}
						std::vector<int> Idle = IdleOfficersIn(State, Source.City, Faction);
						Idle.erase(std::remove_if(Idle.begin(), Idle.end(), [&State](int Officer) { return State.IsRuler(Officer); }), Idle.end());
						if (CountOf(Idle) < 3)
						{
							continue;
						}
						const int Mover = TakeBest(Idle, State, [](const FOfficer& Officer) { return MilitaryScore(Officer); });
						FOrder Order = MakeOrder(EOrderType::Move, Mover, Source.City);
						Order.TargetCity = Destination.City;
						Issue(State, Order);
						break;
					}
				}
			}

			void PlanDomestic(FGameState& State, int City, int Faction, const FCityPlan& Plan)
			{
				std::vector<int> Idle = IdleOfficersIn(State, City, Faction);
				if (Idle.empty())
				{
					return;
				}
				FCity& Data = At(State.Cities, City);
				const int Reserve = GoldReserve(State, City);
				auto Budget = [&Data, Reserve]() { return Data.Gold - Reserve; };

				// 1. Keep the peace.
				if (Data.Order < 60 && Budget() >= Balance::PatrolCost)
				{
					Issue(State, MakeOrder(EOrderType::Patrol, TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Martial) + StatOf(Officer, EStat::Command); }), City));
				}

				// 2. Recruit wandering officers, and tempt disloyal enemies.
				for (const int Target : RecruitTargetsOf(State, City, Faction))
				{
					if (Idle.empty() || Budget() < Balance::RecruitCost || IsRecruitTargeted(State, Target))
					{
						break;
					}
					const bool bFree = At(State.Officers, Target).Status == EOfficerStatus::Free;
					std::vector<int> Trial = Idle;
					const int Recruiter = TakeBest(Trial, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Charm); });
					const int Chance = RecruitChanceOf(State, Recruiter, Target);
					if (Chance < (bFree ? 25 : 35))
					{
						continue;
					}
					FOrder Order = MakeOrder(EOrderType::Recruit, Recruiter, City);
					Order.TargetOfficer = Target;
					if (Issue(State, Order))
					{
						Idle.erase(std::remove(Idle.begin(), Idle.end(), Recruiter), Idle.end());
					}
				}

				// 3. Draft toward the garrison target while food allows.
				for (int Guard = 0; Guard < 3 && !Idle.empty(); ++Guard)
				{
					int Pending = 0;
					for (const FOrder& Order : State.Orders)
					{
						if (Order.Type == EOrderType::Draft && Order.City == City)
						{
							Pending += Order.Amount;
						}
					}
					const int Missing = Plan.TroopTarget - Data.Troops - Pending;
					if (Missing < 300)
					{
						break;
					}
					std::vector<int> Trial = Idle;
					const int Recruiter = TakeBest(Trial, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Charm); });
					int Amount = std::min({Missing, DraftLimit(At(State.Officers, Recruiter)), DraftCapacityOf(State, City), std::max(0, Budget()) * Balance::DraftCostDivisor});
					Amount = Amount / 100 * 100;
					while (Amount >= 300 && !CanFeed(State, City, Data.Troops + Pending + Amount))
					{
						Amount -= 300;
					}
					if (Amount < 300)
					{
						break;
					}
					FOrder Order = MakeOrder(EOrderType::Draft, Recruiter, City);
					Order.Amount = Amount;
					if (!Issue(State, Order))
					{
						break;
					}
					Idle.erase(std::remove(Idle.begin(), Idle.end(), Recruiter), Idle.end());
				}

				// 4. Drill the garrison.
				if (!Idle.empty() && Data.Training < 80 && Data.Troops >= 2000 && Budget() >= Balance::TrainCost)
				{
					Issue(State, MakeOrder(EOrderType::Train, TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Command); }), City));
				}

				// 5. Develop: farmland first when the harvest cannot feed the garrison.
				const bool bFoodFirst = static_cast<long long>(CityHarvest(State, City)) < static_cast<long long>(GarrisonFood(Data.Troops)) * 12;
				for (int Round = 0; Round < 4 && !Idle.empty() && Budget() >= Balance::DevelopCost; ++Round)
				{
					const bool bFarmTurn = (Round % 2 == 0) == bFoodFirst;
					EOrderType Type = bFarmTurn ? EOrderType::Farm : EOrderType::Commerce;
					if (Type == EOrderType::Farm && Data.Farm >= Data.FarmMax)
					{
						Type = EOrderType::Commerce;
					}
					if (Type == EOrderType::Commerce && Data.Commerce >= Data.CommerceMax)
					{
						Type = Data.Farm < Data.FarmMax ? EOrderType::Farm : EOrderType::Walls;
					}
					if (Type == EOrderType::Walls && Data.Defense >= Data.DefenseMax)
					{
						break;
					}
					Issue(State, MakeOrder(Type, TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Politics); }), City));
				}

				// 6. Fortify the frontier.
				if (!Idle.empty() && Plan.bFrontier && Plan.Threat > 0 && Data.Defense < Data.DefenseMax && Budget() >= Balance::WallsCost)
				{
					Issue(State, MakeOrder(EOrderType::Walls, TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Politics) + StatOf(Officer, EStat::Command); }), City));
				}

				// 7. Polish public order.
				if (!Idle.empty() && Data.Order < 85 && Budget() >= Balance::PatrolCost)
				{
					Issue(State, MakeOrder(EOrderType::Patrol, TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Martial) + StatOf(Officer, EStat::Command); }), City));
				}

				// 8. Look for hidden talent now and then.
				if (!Idle.empty() && Budget() >= 150 && State.Rng.Chance(25))
				{
					Issue(State, MakeOrder(EOrderType::Search, TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Charm) + StatOf(Officer, EStat::Strategy); }), City));
				}

				// 9. Warriors train with a nearby sect.
				const std::vector<int> Sects = SectsNearOf(State, City);
				if (!Idle.empty() && !Sects.empty() && Budget() >= 200)
				{
					const int Warrior = TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Martial); });
					if (StatOf(At(State.Officers, Warrior), EStat::Martial) >= 65 && StatOf(At(State.Officers, Warrior), EStat::Martial) < MaxStatValue)
					{
						FOrder Order = MakeOrder(EOrderType::SectTraining, Warrior, City);
						Order.TargetSect = Sects.front();
						Issue(State, Order);
					}
				}
			}

			bool SharesBorder(const FGameState& State, int FactionA, int FactionB)
			{
				for (const FRoad& Road : State.Roads)
				{
					const int OwnerA = At(State.Cities, Road.A).Owner;
					const int OwnerB = At(State.Cities, Road.B).Owner;
					if ((OwnerA == FactionA && OwnerB == FactionB) || (OwnerA == FactionB && OwnerB == FactionA))
					{
						return true;
					}
				}
				return false;
			}

			int AllianceCount(const FGameState& State, int Faction)
			{
				int Count = 0;
				for (int Other = 0; Other < CountOf(State.Factions); ++Other)
				{
					Count += State.AreAllied(Faction, Other) ? 1 : 0;
				}
				return Count;
			}

			void PlanDiplomacy(FGameState& State, int Faction)
			{
				if (!State.Rng.Chance(20))
				{
					return;
				}
				const int Mine = State.FactionTotalTroops(Faction);
				const int Count = CountOf(State.Factions);
				const int Start = State.Rng.Range(0, std::max(0, Count - 1));
				for (int Step = 0; Step < Count; ++Step)
				{
					const int Other = (Start + Step) % Count;
					if (Other == Faction || !IsAliveFaction(State, Other) || State.AreAllied(Faction, Other))
					{
						continue;
					}
					const bool bNeighbor = SharesBorder(State, Faction, Other);
					const int Theirs = State.FactionTotalTroops(Other);
					const int Trust = State.Relation(Faction, Other).Trust;
					EOrderType Type = EOrderType::Count;
					if (bNeighbor && !State.HaveTruce(Faction, Other) && static_cast<long long>(Theirs) * 10 > static_cast<long long>(Mine) * 14)
					{
						Type = Trust < 25 ? EOrderType::Gift : EOrderType::Truce;
					}
					else if (Trust >= 70 && AllianceCount(State, Faction) == 0 && !bNeighbor)
					{
						Type = EOrderType::Alliance;
					}
					if (Type == EOrderType::Count)
					{
						continue;
					}
					if (IsPlayerFaction(State, Other) && Type != EOrderType::Gift)
					{
						QueueProposal(State, Faction, Type == EOrderType::Alliance);
						return;
					}
					// Send the best diplomat available with enough gold in his city.
					int Envoy = -1;
					for (const int Officer : ServingOfficers(State, Faction))
					{
						const FOfficer& Data = At(State.Officers, Officer);
						if (!State.IsOfficerIdle(Officer) || At(State.Cities, Data.City).Owner != Faction)
						{
							continue;
						}
						if (Envoy < 0 || StatOf(Data, EStat::Politics) > StatOf(At(State.Officers, Envoy), EStat::Politics))
						{
							Envoy = Officer;
						}
					}
					if (Envoy < 0)
					{
						return;
					}
					const int City = At(State.Officers, Envoy).City;
					FOrder Order = MakeOrder(Type, Envoy, City);
					Order.TargetFaction = Other;
					if (Type == EOrderType::Gift)
					{
						Order.Gold = std::min(300, At(State.Cities, City).Gold - GoldReserve(State, City));
						if (Order.Gold < 100)
						{
							return;
						}
					}
					Issue(State, Order);
					return;
				}
			}

			void PlanCity(FGameState& State, int City, int Faction, bool bAllowAttack)
			{
				RewardOfficers(State, City, Faction);
				TradeFood(State, City);
				if (bAllowAttack)
				{
					TryAttack(State, City, Faction);
				}
				PlanDomestic(State, City, Faction, AnalyzeCity(State, City, Faction, -1));
			}

			void PlanFaction(FGameState& State, int Faction, bool bDelegatedOnly)
			{
				std::vector<int> Controlled;
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					const FCity& Data = At(State.Cities, City);
					if (Data.Owner == Faction && (!bDelegatedOnly || Data.bDelegated))
					{
						Controlled.push_back(City);
					}
				}
				if (Controlled.empty())
				{
					return;
				}
				// Strongest garrisons consider attacking first.
				std::vector<int> ByTroops = Controlled;
				std::stable_sort(ByTroops.begin(), ByTroops.end(), [&State](int Left, int Right) { return At(State.Cities, Left).Troops > At(State.Cities, Right).Troops; });
				int Attacks = 1 + CountOf(Controlled) / 4;
				for (const int City : ByTroops)
				{
					RewardOfficers(State, City, Faction);
					TradeFood(State, City);
					if (Attacks > 0 && TryAttack(State, City, Faction))
					{
						--Attacks;
					}
				}
				PlanLogistics(State, Faction, Controlled);
				for (const int City : Controlled)
				{
					PlanDomestic(State, City, Faction, AnalyzeCity(State, City, Faction, -1));
				}
				if (!bDelegatedOnly)
				{
					PlanDiplomacy(State, Faction);
				}
			}
		}

		void PlanAllAI(FGameState& State)
		{
			if (State.Phase != EPhase::Planning)
			{
				return;
			}
			for (int Faction = 0; Faction < CountOf(State.Factions); ++Faction)
			{
				if (IsAliveFaction(State, Faction) && !IsPlayerFaction(State, Faction))
				{
					AIDetail::PlanFaction(State, Faction, false);
				}
			}
			if (IsAliveFaction(State, State.PlayerFaction))
			{
				AIDetail::PlanFaction(State, State.PlayerFaction, true);
			}
		}

		void PlanDelegatedCity(FGameState& State, int City)
		{
			if (!ValidCity(State, City) || State.Phase != EPhase::Planning)
			{
				return;
			}
			const int Faction = At(State.Cities, City).Owner;
			if (Faction < 0)
			{
				return;
			}
			AIDetail::PlanCity(State, City, Faction, true);
		}

		void DecideAIPrisoners(FGameState& State)
		{
			for (int Prisoner = 0; Prisoner < CountOf(State.Officers); ++Prisoner)
			{
				const FOfficer& Data = At(State.Officers, Prisoner);
				if (Data.Status != EOfficerStatus::Prisoner || Data.Captor < 0 || IsPlayerFaction(State, Data.Captor))
				{
					continue;
				}
				const int Captor = Data.Captor;
				const int Former = Data.Faction;
				const std::string Name = NameOf(Data);
				if (State.Rng.Chance(PrisonerRecruitChanceOf(State, Prisoner, Captor)))
				{
					JoinFaction(State, Prisoner, Captor, Data.City, 55 + State.Rng.Range(0, 15));
					if (IsPlayerFaction(State, Former))
					{
						LogPlayer(State, LocF("log.prisoner.turned", "{officer}, held prisoner by the {faction}, has agreed to serve them.", {{"officer", Name}, {"faction", FactionLabel(State, Captor)}}), true);
					}
				}
				else if (State.Rng.Chance(30))
				{
					if (ValidFaction(State, Former))
					{
						FRelation& Relation = State.Relation(Captor, Former);
						Relation.Trust = ClampInt(Relation.Trust + Balance::ReleaseTrustGain, 0, 100);
					}
					ReleasePrisoner(State, Prisoner);
					if (IsPlayerFaction(State, Former) && At(State.Officers, Prisoner).Status == EOfficerStatus::Serving)
					{
						LogPlayer(State, LocF("log.prisoner.releasedByAI", "The {faction} has released {officer}, who returns to your service.", {{"faction", FactionLabel(State, Captor)}, {"officer", Name}}), true);
					}
				}
			}
		}
	}
}
