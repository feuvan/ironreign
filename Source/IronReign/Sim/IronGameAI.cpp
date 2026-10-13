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
			constexpr int NoTarget = -2;

			/** A faction's strategy for the month: which enemy to concentrate on and from where. */
			struct FWarPlan
			{
				int Faction = -1;
				/** Faction the AI concentrates on (-1 = independent cities), or NoTarget. */
				int Target = NoTarget;
				/** Cities the AI may command (all of an AI faction's cities, or the player's delegated ones). */
				std::vector<int> Controlled;
				/** Controlled cities next to a city of Target. */
				std::vector<int> Front;
			};

			/** Military situation of one city, as the AI governor sees it. */
			struct FCityPlan
			{
				int City = -1;
				/** Borders a hostile faction or an independent city. */
				bool bFrontier = false;
				/** Borders the faction's war target. */
				bool bFront = false;
				/** Strongest hostile faction garrison next door. */
				int Threat = 0;
				/** Hostile armies marching on the city. */
				int Incoming = 0;
				/** Troops kept home when an army marches out. */
				int Reserve = 0;
				/** Garrison size the governor drafts toward. */
				int TroopTarget = 0;
			};

			bool Contains(const std::vector<int>& Values, int Value)
			{
				return std::find(Values.begin(), Values.end(), Value) != Values.end();
			}

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

			/** Troops the city can feed from its harvest (with some help from the market). */
			int FoodCapacity(const FGameState& State, int City)
			{
				return static_cast<int>(static_cast<long long>(CityHarvest(State, City)) * 13 / 10 * Balance::GarrisonFoodDivisor / 12);
			}

			/** Largest garrison the governor drafts toward: bigger cities keep bigger garrisons. */
			int SizeCapacity(const FCity& City)
			{
				return 6000 + 6000 * City.Size;
			}

			FCityPlan AnalyzeCity(const FGameState& State, const FWarPlan& War, int City, int IgnoreCity)
			{
				const int Faction = War.Faction;
				FCityPlan Plan;
				Plan.City = City;
				Plan.bFront = Contains(War.Front, City);
				for (const int Neighbor : State.Neighbors(City))
				{
					const FCity& Data = At(State.Cities, Neighbor);
					if (Data.Owner == Faction || !State.AreHostile(Faction, Data.Owner))
					{
						// Hostile factions two roads away can strike through a neighbor they conquer: half weight.
						for (const int Second : State.Neighbors(Neighbor))
						{
							const FCity& Far = At(State.Cities, Second);
							if (Second != City && Second != IgnoreCity && Far.Owner >= 0 && Far.Owner != Faction && State.AreHostile(Faction, Far.Owner))
							{
								Plan.Threat = std::max(Plan.Threat, Far.Troops / 2);
							}
						}
						continue;
					}
					Plan.bFrontier = true;
					if (Data.Owner >= 0 && Neighbor != IgnoreCity)
					{
						Plan.Threat = std::max(Plan.Threat, Data.Troops);
					}
				}
				Plan.Incoming = IncomingHostileTroops(State, City, Faction);
				if (Plan.Threat > 0 || Plan.Incoming > 0)
				{
					Plan.Reserve = std::max(1500, Plan.Threat / 2) + Plan.Incoming;
				}
				else
				{
					Plan.Reserve = Plan.bFrontier ? 1500 : 1000;
				}
				const FCity& Data = At(State.Cities, City);
				if (ValidFaction(State, Faction) && At(State.Factions, Faction).Capital == City)
				{
					// The seat of government never empties its barracks.
					Plan.Reserve = std::max(Plan.Reserve, Data.Troops / 4);
				}
				Plan.TroopTarget = std::min(SizeCapacity(Data), FoodCapacity(State, City));
				if (Plan.Incoming > 0)
				{
					Plan.TroopTarget = std::max(Plan.TroopTarget, Plan.Incoming * 13 / 10);
				}
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

			std::vector<int> IdleNonRulers(const FGameState& State, int City, int Faction)
			{
				std::vector<int> Result = IdleOfficersIn(State, City, Faction);
				Result.erase(std::remove_if(Result.begin(), Result.end(), [&State](int Officer) { return State.IsRuler(Officer); }), Result.end());
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

			/** Picks the enemy to concentrate on: independent towns first, then the weakest hostile neighbor. */
			void ChooseWarTarget(const FGameState& State, FWarPlan& War)
			{
				const int Mine = std::max(1, State.FactionTotalTroops(War.Faction));
				long long BestScore = -1;
				for (const int City : War.Controlled)
				{
					for (const int Neighbor : State.Neighbors(City))
					{
						const int Owner = At(State.Cities, Neighbor).Owner;
						if (Owner == War.Faction || !State.AreHostile(War.Faction, Owner))
						{
							continue;
						}
						long long Score = 0;
						if (Owner < 0)
						{
							Score = 1000000;
						}
						else
						{
							Score = static_cast<long long>(Mine) * 100 / std::max(1, State.FactionTotalTroops(Owner));
						}
						if (Score > BestScore)
						{
							BestScore = Score;
							War.Target = Owner;
						}
					}
				}
				if (War.Target == NoTarget)
				{
					return;
				}
				for (const int City : War.Controlled)
				{
					for (const int Neighbor : State.Neighbors(City))
					{
						if (At(State.Cities, Neighbor).Owner == War.Target && !Contains(War.Front, City))
						{
							War.Front.push_back(City);
						}
					}
				}
			}

			/** Marches on a city of the war target (or a much weaker one) when local strength suffices. */
			bool TryAttack(FGameState& State, const FWarPlan& War, int City)
			{
				const int Faction = War.Faction;
				const FCity& Data = At(State.Cities, City);
				if (Data.Troops < 3000)
				{
					return false;
				}
				std::vector<int> Officers = IdleNonRulers(State, City, Faction);
				if (Officers.empty())
				{
					return false;
				}
				std::stable_sort(Officers.begin(), Officers.end(), [&State](int Left, int Right) {
					return MilitaryScore(At(State.Officers, Left)) > MilitaryScore(At(State.Officers, Right));
				});
				// Leave someone at home to govern when possible.
				const int Usable = CountOf(Officers) > 1 ? CountOf(Officers) - 1 : 1;
				const int Ratio = Balance::AIAttackRatioPercent[ClampInt(static_cast<int>(State.Difficulty), 0, 2)];
				// Aggression against other factions ramps up over the first two years of the campaign.
				const int MonthsPlayed = (State.Year - State.StartYear) * 12 + State.Month - 1;
				const int FactionRatio = Ratio + Ratio * std::max(0, Balance::AIWarmupMonths - MonthsPlayed) / (2 * Balance::AIWarmupMonths);

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
					if (!FindRoute(State, Faction, City, Target, Path, Tenths) || Tenths > 250)
					{
						continue;
					}
					const FCityPlan Plan = AnalyzeCity(State, War, City, Target);
					const int Available = Data.Troops - Plan.Reserve;
					if (Available < 2000)
					{
						continue;
					}
					// One army of up to five officers; a second army joins when the first cannot carry everyone.
					std::vector<int> Chosen;
					long long Capacity = 0;
					for (int Index = 0; Index < std::min(Usable, 2 * MaxArmyUnits) && Capacity < Available; ++Index)
					{
						Chosen.push_back(At(Officers, Index));
						Capacity += MaxUnitTroopsOf(State, At(Officers, Index));
					}
					const int Troops = static_cast<int>(std::min<long long>(Available, Capacity));
					const long long Attack = Power(Troops, Data.Training, StatOf(At(State.Officers, Chosen.front()), EStat::Command));
					const long long Defense = std::max<long long>(1, CityDefensePower(State, Target));
					const long long Score = Attack * 100 / Defense;
					// Off-plan targets need overwhelming odds.
					const int Needed = Owner < 0 ? Ratio : (Owner == War.Target ? FactionRatio : FactionRatio * 3 / 2);
					if (Score < Needed)
					{
						continue;
					}
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
				// Split into armies of at most five officers, troops in proportion to what each can lead.
				std::vector<std::vector<int>> Groups(1);
				for (const int Officer : BestOfficers)
				{
					if (CountOf(Groups.back()) >= MaxArmyUnits)
					{
						Groups.emplace_back();
					}
					Groups.back().push_back(Officer);
				}
				long long TotalCapacity = 0;
				for (const int Officer : BestOfficers)
				{
					TotalCapacity += MaxUnitTroopsOf(State, Officer);
				}
				bool bFormed = false;
				int TroopsLeft = BestTroops;
				for (size_t Group = 0; Group < Groups.size(); ++Group)
				{
					long long GroupCapacity = 0;
					for (const int Officer : Groups[Group])
					{
						GroupCapacity += MaxUnitTroopsOf(State, Officer);
					}
					const int Troops = Group + 1 == Groups.size() ? TroopsLeft : static_cast<int>(static_cast<long long>(BestTroops) * GroupCapacity / std::max<long long>(1, TotalCapacity));
					if (Troops < CountOf(Groups[Group]) * Balance::MinUnitTroops)
					{
						continue;
					}
					const FCity& Home = At(State.Cities, City);
					const int Daily = ArmyFoodPerDay(Troops);
					const int HomeNeed = GarrisonFood(Home.Troops - Troops) * 2;
					// Enough food to reach the target and sustain a full siege.
					const int Food = std::min(Daily * (Days + DaysPerMonth + 5), Home.Food - HomeNeed);
					if (Food < Daily * (Days + 10))
					{
						break;
					}
					FArmyPlan Army;
					Army.City = City;
					Army.Officers = Groups[Group];
					Army.Troops = std::min(Troops, Home.Troops);
					Army.Food = Food;
					Army.Target = BestTarget;
					std::string Error;
					if (FormArmyRules(State, Army, Error) > 0)
					{
						bFormed = true;
						TroopsLeft -= Army.Troops;
					}
				}
				return bFormed;
			}

			/** Officers stationed in City plus those ordered to move there this month. */
			std::vector<int> OfficersArriving(const FGameState& State, int City, int Faction)
			{
				std::vector<int> Result = OfficersInCity(State, City, Faction);
				for (const FOrder& Order : State.Orders)
				{
					if (Order.Type == EOrderType::Move && Order.TargetCity == City && ValidOfficer(State, Order.Officer) && At(State.Officers, Order.Officer).Faction == Faction)
					{
						Result.push_back(Order.Officer);
					}
				}
				return Result;
			}

			/** Troops a front city wants: enough to storm the weakest adjacent enemy city with margin (as far as its officers can lead), plus its reserve. */
			int ArmyNeedAt(const FGameState& State, const FWarPlan& War, int City)
			{
				long long Weakest = -1;
				for (const int Neighbor : State.Neighbors(City))
				{
					const FCity& Data = At(State.Cities, Neighbor);
					if (Data.Owner == War.Target)
					{
						const long long Defense = CityDefensePower(State, Neighbor);
						Weakest = Weakest < 0 ? Defense : std::min(Weakest, Defense);
					}
				}
				if (Weakest < 0)
				{
					return 0;
				}
				long long Leadable = 0;
				int Leaders = 0;
				for (const int Officer : OfficersArriving(State, City, War.Faction))
				{
					if (!State.IsRuler(Officer) && Leaders < 2 * MaxArmyUnits)
					{
						Leadable += MaxUnitTroopsOf(State, Officer);
						++Leaders;
					}
				}
				const FCityPlan Plan = AnalyzeCity(State, War, City, -1);
				const int Wanted = static_cast<int>(std::min(Weakest * 2, Leadable));
				return Wanted + Plan.Reserve - At(State.Cities, City).Troops;
			}

			/** Officers each city should keep: governors everywhere, commanders on the front. */
			int DesiredOfficers(const FGameState& State, const FWarPlan& War, int City)
			{
				const FCityPlan Plan = AnalyzeCity(State, War, City, -1);
				if (Plan.bFront)
				{
					return 5 + At(State.Cities, City).Size;
				}
				if (Plan.Incoming > 0)
				{
					return 3;
				}
				return Plan.Threat > 0 ? 2 : 1;
			}

			/** Moves spare officers (best commanders first) from quiet cities to the cities that need them. */
			void AllocateOfficers(FGameState& State, const FWarPlan& War)
			{
				const int Faction = War.Faction;
				std::vector<std::pair<int, int>> Deficits;
				for (const int City : War.Controlled)
				{
					const int Missing = DesiredOfficers(State, War, City) - CountOf(OfficersArriving(State, City, Faction));
					if (Missing > 0)
					{
						Deficits.push_back({City, Missing + (OfficersInCity(State, City, Faction).empty() ? 100 : 0)});
					}
				}
				std::stable_sort(Deficits.begin(), Deficits.end(), [](const std::pair<int, int>& Left, const std::pair<int, int>& Right) { return Left.second > Right.second; });
				for (std::pair<int, int>& Deficit : Deficits)
				{
					const int Target = Deficit.first;
					int Missing = Deficit.second >= 100 ? Deficit.second - 100 : Deficit.second;
					Missing = std::max(1, Missing);
					for (const int Source : War.Controlled)
					{
						if (Source == Target || Missing <= 0)
						{
							continue;
						}
						const int Spare = CountOf(OfficersInCity(State, Source, Faction)) - DesiredOfficers(State, War, Source);
						std::vector<int> Idle = IdleNonRulers(State, Source, Faction);
						for (int Moved = 0; Moved < Spare && Missing > 0 && !Idle.empty(); ++Moved)
						{
							const bool bFrontTarget = Contains(War.Front, Target);
							const int Mover = bFrontTarget ? TakeBest(Idle, State, [](const FOfficer& Officer) { return MilitaryScore(Officer); })
														   : TakeBest(Idle, State, [](const FOfficer& Officer) { return StatOf(Officer, EStat::Politics) + StatOf(Officer, EStat::Charm); });
							FOrder Order = MakeOrder(EOrderType::Move, Mover, Source);
							Order.TargetCity = Target;
							if (Issue(State, Order))
							{
								--Missing;
							}
						}
					}
				}
			}

			void PlanLogistics(FGameState& State, const FWarPlan& War)
			{
				const int Faction = War.Faction;
				AllocateOfficers(State, War);
				// Destinations: cities under attack first, then the front against the war target.
				std::vector<std::pair<int, int>> Needs;
				for (const int City : War.Controlled)
				{
					const FCityPlan Plan = AnalyzeCity(State, War, City, -1);
					int Need = 0;
					if (Plan.Incoming > 0)
					{
						Need = Plan.Incoming * 13 / 10 + std::max(1500, Plan.Threat / 2) - At(State.Cities, City).Troops;
						Need = Need > 0 ? Need + 100000 : 0;
					}
					else if (Plan.bFront)
					{
						Need = ArmyNeedAt(State, War, City);
					}
					if (Need > 0)
					{
						Needs.push_back({City, Need});
					}
				}
				std::stable_sort(Needs.begin(), Needs.end(), [](const std::pair<int, int>& Left, const std::pair<int, int>& Right) { return Left.second > Right.second; });

				for (const int Source : War.Controlled)
				{
					const FCityPlan Plan = AnalyzeCity(State, War, Source, -1);
					if (Plan.Incoming > 0 || Plan.bFront)
					{
						continue;
					}
					FCity& Data = At(State.Cities, Source);
					const int Surplus = Data.Troops - Plan.Reserve - 1000;
					std::vector<int> Idle = IdleNonRulers(State, Source, Faction);
					if (Surplus < 2000 || Idle.empty())
					{
						continue;
					}
					int Destination = -1;
					for (std::pair<int, int>& Need : Needs)
					{
						std::vector<int> Path;
						int Tenths = 0;
						if (Need.first != Source && Need.second > 0 && FindRoute(State, Faction, Source, Need.first, Path, Tenths))
						{
							Destination = Need.first;
							Need.second -= Surplus;
							break;
						}
					}
					if (Destination < 0)
					{
						continue;
					}
					const int Courier = TakeBest(Idle, State, [](const FOfficer& Officer) { return -StatOf(Officer, EStat::Politics); });
					FOrder Order = MakeOrder(EOrderType::Transport, Courier, Source);
					Order.TargetCity = Destination;
					Order.Troops = Surplus;
					const int FoodKeep = GarrisonFood(Data.Troops - Surplus) * (MonthsUntilHarvest(State.Month) + 3);
					Order.Food = std::max(0, std::min(Data.Food - FoodKeep, GarrisonFood(Surplus) * 8));
					Order.Gold = Data.Gold > 1500 ? Data.Gold - 1000 : 0;
					Issue(State, Order);
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

				// 6. Fortify against hostile neighbors.
				if (!Idle.empty() && Plan.Threat > 0 && Data.Defense < Data.DefenseMax && Budget() >= Balance::WallsCost)
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

			/** Seeks peace with dangerous neighbors other than the war target, and allies far away. */
			void PlanDiplomacy(FGameState& State, const FWarPlan& War)
			{
				const int Faction = War.Faction;
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
					if (Other == Faction || Other == War.Target || !IsAliveFaction(State, Other) || State.AreAllied(Faction, Other))
					{
						continue;
					}
					const bool bNeighbor = SharesBorder(State, Faction, Other);
					const int Theirs = State.FactionTotalTroops(Other);
					const int Trust = State.Relation(Faction, Other).Trust;
					EOrderType Type = EOrderType::Count;
					if (bNeighbor && !State.HaveTruce(Faction, Other) && static_cast<long long>(Theirs) * 10 > static_cast<long long>(Mine) * 12)
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
					// Send the best diplomat available.
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

			FWarPlan MakeWarPlan(const FGameState& State, int Faction, bool bDelegatedOnly)
			{
				FWarPlan War;
				War.Faction = Faction;
				for (int City = 0; City < CountOf(State.Cities); ++City)
				{
					const FCity& Data = At(State.Cities, City);
					if (Data.Owner == Faction && (!bDelegatedOnly || Data.bDelegated))
					{
						War.Controlled.push_back(City);
					}
				}
				ChooseWarTarget(State, War);
				return War;
			}

			void PlanFaction(FGameState& State, int Faction, bool bDelegatedOnly)
			{
				const FWarPlan War = MakeWarPlan(State, Faction, bDelegatedOnly);
				if (War.Controlled.empty())
				{
					return;
				}
				// Strongest garrisons consider attacking first.
				std::vector<int> ByTroops = War.Controlled;
				std::stable_sort(ByTroops.begin(), ByTroops.end(), [&State](int Left, int Right) { return At(State.Cities, Left).Troops > At(State.Cities, Right).Troops; });
				int Attacks = std::min(3, 1 + CountOf(War.Controlled) / 4);
				for (const int City : ByTroops)
				{
					RewardOfficers(State, City, Faction);
					TradeFood(State, City);
					if (Attacks > 0 && TryAttack(State, War, City))
					{
						--Attacks;
					}
				}
				PlanLogistics(State, War);
				for (const int City : War.Controlled)
				{
					PlanDomestic(State, City, Faction, AnalyzeCity(State, War, City, -1));
				}
				if (!bDelegatedOnly)
				{
					PlanDiplomacy(State, War);
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
			AIDetail::FWarPlan War = AIDetail::MakeWarPlan(State, Faction, true);
			if (!AIDetail::Contains(War.Controlled, City))
			{
				War.Controlled.push_back(City);
			}
			AIDetail::RewardOfficers(State, City, Faction);
			AIDetail::TradeFood(State, City);
			AIDetail::TryAttack(State, War, City);
			AIDetail::PlanDomestic(State, City, Faction, AIDetail::AnalyzeCity(State, War, City, -1));
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
