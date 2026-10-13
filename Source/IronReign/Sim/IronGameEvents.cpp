#include "Sim/IronGame.h"

#include "Sim/IronGameInternal.h"
#include "Sim/IronLocale.h"

#include <algorithm>

namespace IronSim
{
	namespace GameRules
	{
		namespace EventsDetail
		{
			/** What an event is about: the city, faction and officer its placeholders and "context" references resolve to. */
			struct FEventContext
			{
				int City = -1;
				int Faction = -1;
				int Officer = -1;
			};

			constexpr int MaxPlayerEventsPerMonth = 2;

			std::string Substitute(const FGameState& State, const std::string& Text, const FEventContext& Context)
			{
				const int Ruler = RulerOf(State, Context.Faction);
				return FormatText(Text, {
					{"city", ValidCity(State, Context.City) ? NameOf(At(State.Cities, Context.City)) : std::string()},
					{"ruler", Ruler >= 0 ? NameOf(At(State.Officers, Ruler)) : std::string()},
					{"faction", ValidFaction(State, Context.Faction) ? NameOf(At(State.Factions, Context.Faction)) : FactionLabel(State, -1)},
					{"officer", ValidOfficer(State, Context.Officer) ? NameOf(At(State.Officers, Context.Officer)) : std::string()},
				});
			}

			int PlayerCityCount(const FGameState& State)
			{
				int Count = 0;
				for (const FCity& City : State.Cities)
				{
					Count += IsPlayerFaction(State, City.Owner) ? 1 : 0;
				}
				return Count;
			}

			bool ConditionsMet(const FGameState& State, const FEventDef& Def)
			{
				const FEventCondition& Condition = Def.Condition;
				if (State.Year < Condition.MinYear || State.Year > Condition.MaxYear)
				{
					return false;
				}
				if (!Condition.Months.empty() && std::find(Condition.Months.begin(), Condition.Months.end(), State.Month) == Condition.Months.end())
				{
					return false;
				}
				const int Player = State.PlayerFaction;
				const bool bPlayerAlive = IsAliveFaction(State, Player);
				if (!Def.bWorld && !bPlayerAlive)
				{
					return false;
				}
				if (Condition.OwnsCity >= 0 && (!bPlayerAlive || !ValidCity(State, Condition.OwnsCity) || At(State.Cities, Condition.OwnsCity).Owner != Player))
				{
					return false;
				}
				if (Condition.HasOfficer >= 0)
				{
					if (!bPlayerAlive || !ValidOfficer(State, Condition.HasOfficer))
					{
						return false;
					}
					const FOfficer& Officer = At(State.Officers, Condition.HasOfficer);
					if (Officer.Status != EOfficerStatus::Serving || Officer.Faction != Player)
					{
						return false;
					}
				}
				if (Condition.Faction >= 0 && Condition.Faction != Player)
				{
					return false;
				}
				const int Cities = PlayerCityCount(State);
				if ((Condition.MinCities > 0 || Condition.MaxCities < 9999) && (Cities < Condition.MinCities || Cities > Condition.MaxCities))
				{
					return false;
				}
				return true;
			}

			bool EffectsUseLivingFactions(const FGameState& State, const std::vector<FEffect>& Effects)
			{
				for (const FEffect& Effect : Effects)
				{
					if (Effect.Faction >= 0 && !IsAliveFaction(State, Effect.Faction))
					{
						return false;
					}
				}
				return true;
			}

			bool ReferencesAlive(const FGameState& State, const FEventDef& Def)
			{
				if (Def.Speaker >= 0 && (!ValidOfficer(State, Def.Speaker) || At(State.Officers, Def.Speaker).Status != EOfficerStatus::Serving))
				{
					return false;
				}
				if (!EffectsUseLivingFactions(State, Def.Effects))
				{
					return false;
				}
				for (const FEventChoice& Choice : Def.Choices)
				{
					if (!EffectsUseLivingFactions(State, Choice.Effects))
					{
						return false;
					}
				}
				return true;
			}

			int PickContextCity(FGameState& State, const FEventDef& Def)
			{
				switch (Def.Context)
				{
				case EEventContext::RandomPlayerCity:
				{
					std::vector<int> Owned;
					for (int City = 0; City < CountOf(State.Cities); ++City)
					{
						if (IsPlayerFaction(State, At(State.Cities, City).Owner))
						{
							Owned.push_back(City);
						}
					}
					return Owned.empty() ? -1 : Owned[static_cast<size_t>(State.Rng.Range(0, CountOf(Owned) - 1))];
				}
				case EEventContext::Capital:
				{
					if (!IsAliveFaction(State, State.PlayerFaction))
					{
						return -1;
					}
					const int Capital = At(State.Factions, State.PlayerFaction).Capital;
					return (ValidCity(State, Capital) && At(State.Cities, Capital).Owner == State.PlayerFaction) ? Capital : -1;
				}
				case EEventContext::RandomCity:
					return State.Cities.empty() ? -1 : State.Rng.Range(0, CountOf(State.Cities) - 1);
				case EEventContext::FixedCity:
					return ValidCity(State, Def.ContextCity) ? Def.ContextCity : -1;
				}
				return -1;
			}

			/** Replaces Ref* values (and missing targets) with concrete indices. */
			FEffect Resolve(const FGameState& State, const FEffect& Source, const FEventContext& Context)
			{
				FEffect Effect = Source;
				const int Player = State.PlayerFaction;
				const int PlayerCapital = ValidFaction(State, Player) ? At(State.Factions, Player).Capital : -1;
				if (Effect.City == RefContext || Effect.City == RefNone)
				{
					Effect.City = Context.City;
				}
				else if (Effect.City == RefCapital)
				{
					Effect.City = PlayerCapital;
				}
				if (Effect.Officer == RefContext || Effect.Officer == RefNone)
				{
					Effect.Officer = Effect.Officer == RefContext ? Context.Officer : -1;
				}
				else if (Effect.Officer == RefRuler)
				{
					Effect.Officer = RulerOf(State, Player);
				}
				if (Effect.Faction == RefContext || Effect.Faction == RefNone)
				{
					Effect.Faction = Context.Faction;
				}
				else if (Effect.Faction == RefPlayer)
				{
					Effect.Faction = Player;
				}
				if (Effect.Sect < 0)
				{
					Effect.Sect = -1;
				}
				if (Effect.Technique < 0)
				{
					Effect.Technique = -1;
				}
				return Effect;
			}

			void AddToCity(FGameState& State, int City, EEffectType Type, int Amount)
			{
				if (!ValidCity(State, City))
				{
					return;
				}
				FCity& Data = At(State.Cities, City);
				switch (Type)
				{
				case EEffectType::Gold: Data.Gold = std::max(0, Data.Gold + Amount); break;
				case EEffectType::Food: Data.Food = std::max(0, Data.Food + Amount); break;
				case EEffectType::Troops: Data.Troops = std::max(0, Data.Troops + Amount); break;
				case EEffectType::Order: Data.Order = ClampInt(Data.Order + Amount, 0, 100); break;
				case EEffectType::Farm: Data.Farm = ClampInt(Data.Farm + Amount, 0, Data.FarmMax); break;
				case EEffectType::Commerce: Data.Commerce = ClampInt(Data.Commerce + Amount, 0, Data.CommerceMax); break;
				case EEffectType::Defense: Data.Defense = ClampInt(Data.Defense + Amount, 0, Data.DefenseMax); break;
				case EEffectType::Population: Data.Population = ClampInt(Data.Population + Amount, 0, Data.PopulationMax); break;
				case EEffectType::Training: Data.Training = ClampInt(Data.Training + Amount, 0, 100); break;
				default: break;
				}
			}

			/** Faction paired with the player by trust/alliance/truce effects, or -1 if the effect does not apply. */
			int DiplomacyPartner(const FGameState& State, const FEffect& Effect)
			{
				if (!IsAliveFaction(State, Effect.Faction) || !IsAliveFaction(State, State.PlayerFaction) || Effect.Faction == State.PlayerFaction)
				{
					return -1;
				}
				return Effect.Faction;
			}

			void ApplyEffect(FGameState& State, const FEffect& Effect, const FEventContext& Context)
			{
				switch (Effect.Type)
				{
				case EEffectType::Gold:
				case EEffectType::Food:
				case EEffectType::Troops:
				case EEffectType::Order:
				case EEffectType::Farm:
				case EEffectType::Commerce:
				case EEffectType::Defense:
				case EEffectType::Population:
				case EEffectType::Training:
					AddToCity(State, Effect.City, Effect.Type, Effect.Amount);
					break;
				case EEffectType::Loyalty:
					if (ValidOfficer(State, Effect.Officer) && At(State.Officers, Effect.Officer).Status == EOfficerStatus::Serving && !State.IsRuler(Effect.Officer))
					{
						FOfficer& Officer = At(State.Officers, Effect.Officer);
						Officer.Loyalty = ClampInt(Officer.Loyalty + Effect.Amount, 0, 100);
					}
					break;
				case EEffectType::LoyaltyAll:
					for (const int Officer : ServingOfficers(State, Effect.Faction))
					{
						if (!State.IsRuler(Officer))
						{
							FOfficer& Data = At(State.Officers, Officer);
							Data.Loyalty = ClampInt(Data.Loyalty + Effect.Amount, 0, 100);
						}
					}
					break;
				case EEffectType::Stat:
					if (ValidOfficer(State, Effect.Officer) && At(State.Officers, Effect.Officer).Status != EOfficerStatus::Dead)
					{
						FOfficer& Officer = At(State.Officers, Effect.Officer);
						const int Index = StatIndex(Effect.Stat);
						Officer.Stats[Index] = ClampInt(Officer.Stats[Index] + Effect.Amount, 1, MaxStatValue);
					}
					break;
				case EEffectType::JoinOfficer:
				{
					if (!ValidOfficer(State, Effect.Officer) || !IsAliveFaction(State, Effect.Faction))
					{
						break;
					}
					const EOfficerStatus Status = At(State.Officers, Effect.Officer).Status;
					if (Status != EOfficerStatus::Free && Status != EOfficerStatus::Hidden && Status != EOfficerStatus::Unborn)
					{
						break;
					}
					int City = Effect.City;
					if (!ValidCity(State, City) || At(State.Cities, City).Owner != Effect.Faction)
					{
						City = NearestOwnedCity(State, Effect.Faction, ValidCity(State, City) ? City : At(State.Officers, Effect.Officer).City);
					}
					if (!ValidCity(State, City))
					{
						break;
					}
					JoinFaction(State, Effect.Officer, Effect.Faction, City, 70);
					if (IsPlayerFaction(State, Effect.Faction))
					{
						LogPlayer(State, LocF("log.event.joined", "{officer} has joined your service in {city}.", {{"officer", OfficerLabel(State, Effect.Officer)}, {"city", CityLabel(State, City)}}), true);
					}
					break;
				}
				case EEffectType::RevealOfficer:
				{
					if (!ValidOfficer(State, Effect.Officer))
					{
						break;
					}
					FOfficer& Officer = At(State.Officers, Effect.Officer);
					if (Officer.Status != EOfficerStatus::Hidden && Officer.Status != EOfficerStatus::Unborn)
					{
						break;
					}
					Officer.Status = EOfficerStatus::Free;
					Officer.Faction = -1;
					Officer.Captor = -1;
					Officer.Army = -1;
					if (ValidCity(State, Effect.City))
					{
						Officer.City = Effect.City;
					}
					else if (!ValidCity(State, Officer.City))
					{
						Officer.City = 0;
					}
					break;
				}
				case EEffectType::Trust:
				{
					const int Partner = DiplomacyPartner(State, Effect);
					if (Partner >= 0)
					{
						FRelation& Relation = State.Relation(Partner, State.PlayerFaction);
						Relation.Trust = ClampInt(Relation.Trust + Effect.Amount, 0, 100);
					}
					break;
				}
				case EEffectType::Alliance:
				{
					const int Partner = DiplomacyPartner(State, Effect);
					if (Partner >= 0)
					{
						FRelation& Relation = State.Relation(Partner, State.PlayerFaction);
						Relation.AllianceMonths = Effect.Amount > 0 ? Effect.Amount : Balance::AllianceMonths;
						Relation.TruceMonths = 0;
						LogPlayer(State, LocF("log.diplomacy.alliance", "The {faction} and the {target} have sealed an alliance for {months} months.", {{"faction", FactionLabel(State, State.PlayerFaction)}, {"target", FactionLabel(State, Partner)}, {"months", ToText(Relation.AllianceMonths)}}), true);
					}
					break;
				}
				case EEffectType::Truce:
				{
					const int Partner = DiplomacyPartner(State, Effect);
					if (Partner >= 0)
					{
						FRelation& Relation = State.Relation(Partner, State.PlayerFaction);
						Relation.TruceMonths = Effect.Amount > 0 ? Effect.Amount : Balance::TruceMonths;
						LogPlayer(State, LocF("log.diplomacy.truce", "The {faction} and the {target} have agreed to a truce for {months} months.", {{"faction", FactionLabel(State, State.PlayerFaction)}, {"target", FactionLabel(State, Partner)}, {"months", ToText(Relation.TruceMonths)}}), true);
					}
					break;
				}
				case EEffectType::SectFavor:
					if (ValidSect(State, Effect.Sect) && ValidFaction(State, State.PlayerFaction))
					{
						FSect& Sect = At(State.Sects, Effect.Sect);
						Sect.Favor.resize(State.Factions.size(), 0);
						At(Sect.Favor, State.PlayerFaction) = ClampInt(At(Sect.Favor, State.PlayerFaction) + Effect.Amount, 0, 100);
					}
					break;
				case EEffectType::LearnTechnique:
					if (ValidOfficer(State, Effect.Officer) && ValidTechnique(State, Effect.Technique))
					{
						FOfficer& Officer = At(State.Officers, Effect.Officer);
						if (Officer.Status != EOfficerStatus::Dead && std::find(Officer.Techniques.begin(), Officer.Techniques.end(), Effect.Technique) == Officer.Techniques.end())
						{
							Officer.Techniques.push_back(Effect.Technique);
						}
					}
					break;
				case EEffectType::Message:
				{
					const std::string Text = Substitute(State, Effect.Text, Context);
					if (!Text.empty())
					{
						LogFaction(State, Context.Faction, Text, false);
					}
					break;
				}
				}
			}

			void Fire(FGameState& State, int DefIndex, int City)
			{
				const FEventDef& Def = At(State.Events, DefIndex);
				FEventContext Context;
				Context.City = City;
				Context.Faction = Def.bWorld ? At(State.Cities, City).Owner : State.PlayerFaction;
				Context.Officer = ValidOfficer(State, Def.Condition.HasOfficer) ? Def.Condition.HasOfficer : -1;
				const std::string Title = Substitute(State, TitleOf(Def), Context);
				const std::string Text = Substitute(State, TextOf(Def), Context);

				// Immediate effects (all effects of world events; "on arrival" effects of player events).
				const std::vector<FEffect> Immediate = Def.Effects;
				for (int Index = 0; Index < CountOf(Immediate); ++Index)
				{
					FEffect Effect = Resolve(State, At(Immediate, Index), Context);
					if (Effect.Type == EEffectType::Message)
					{
						Effect.Text = EffectTextOf(At(State.Events, DefIndex), -1, Index);
					}
					ApplyEffect(State, Effect, Context);
				}
				if (Def.bWorld)
				{
					LogFaction(State, Context.Faction, LocF("log.event.world", "{title}: {text}", {{"title", Title}, {"text", Text}}), IsPlayerFaction(State, Context.Faction));
					return;
				}

				const FEventDef& Fired = At(State.Events, DefIndex);
				FPendingEvent Pending;
				Pending.Def = DefIndex;
				Pending.Title = Title;
				Pending.Text = Text;
				Pending.Image = Fired.Image;
				Pending.Speaker = Fired.Speaker >= 0 ? Fired.Speaker : AdvisorOf(State, State.PlayerFaction);
				Pending.City = Context.City;
				Pending.Faction = Context.Faction;
				Pending.Officer = Context.Officer;
				if (Fired.Choices.empty())
				{
					FEventChoice Choice;
					Choice.Label = Loc("event.choice.ok", "So be it.");
					Pending.Choices.push_back(Choice);
				}
				for (int ChoiceIndex = 0; ChoiceIndex < CountOf(Fired.Choices); ++ChoiceIndex)
				{
					const FEventChoice& Source = At(Fired.Choices, ChoiceIndex);
					FEventChoice Choice;
					Choice.Label = Substitute(State, ChoiceLabelOf(Fired, ChoiceIndex), Context);
					Choice.RequireGold = Source.RequireGold;
					for (int Index = 0; Index < CountOf(Source.Effects); ++Index)
					{
						FEffect Effect = Resolve(State, At(Source.Effects, Index), Context);
						if (Effect.Type == EEffectType::Message)
						{
							Effect.Text = EffectTextOf(Fired, ChoiceIndex, Index);
						}
						Choice.Effects.push_back(Effect);
					}
					Pending.Choices.push_back(Choice);
				}
				State.PendingEvents.push_back(Pending);
			}
		}

		void CheckEventsRules(FGameState& State)
		{
			int PlayerEvents = 0;
			for (const FPendingEvent& Pending : State.PendingEvents)
			{
				PlayerEvents += Pending.Def >= 0 ? 1 : 0;
			}
			for (int Index = 0; Index < CountOf(State.Events); ++Index)
			{
				const FEventDef& Def = At(State.Events, Index);
				if (Def.bOnce && Def.TimesFired > 0)
				{
					continue;
				}
				if (!Def.bWorld && PlayerEvents >= EventsDetail::MaxPlayerEventsPerMonth)
				{
					continue;
				}
				if (!EventsDetail::ConditionsMet(State, Def) || !EventsDetail::ReferencesAlive(State, Def))
				{
					continue;
				}
				if (!State.Rng.Chance(Def.Condition.Chance))
				{
					continue;
				}
				const int City = EventsDetail::PickContextCity(State, Def);
				if (City < 0)
				{
					continue;
				}
				++At(State.Events, Index).TimesFired;
				if (!Def.bWorld)
				{
					++PlayerEvents;
				}
				EventsDetail::Fire(State, Index, City);
			}
		}

		bool CanChooseRules(const FGameState& State, int ChoiceIndex)
		{
			if (State.PendingEvents.empty())
			{
				return false;
			}
			const FPendingEvent& Event = State.PendingEvents.front();
			if (ChoiceIndex < 0 || ChoiceIndex >= CountOf(Event.Choices))
			{
				return false;
			}
			const int Required = At(Event.Choices, ChoiceIndex).RequireGold;
			if (Required <= 0)
			{
				return true;
			}
			int City = Event.City;
			if (!ValidCity(State, City) && ValidFaction(State, State.PlayerFaction))
			{
				City = At(State.Factions, State.PlayerFaction).Capital;
			}
			return ValidCity(State, City) && At(State.Cities, City).Gold >= Required;
		}

		void ChooseRules(FGameState& State, int ChoiceIndex)
		{
			if (!CanChooseRules(State, ChoiceIndex))
			{
				return;
			}
			const FPendingEvent Event = State.PendingEvents.front();
			State.PendingEvents.erase(State.PendingEvents.begin());
			EventsDetail::FEventContext Context;
			Context.City = Event.City;
			Context.Faction = Event.Faction;
			Context.Officer = Event.Officer;
			const FEventChoice& Choice = At(Event.Choices, ChoiceIndex);
			LogPlayer(State, LocF("log.event.choice", "{title}: you chose \"{choice}\".", {{"title", Event.Title}, {"choice", Choice.Label}}));
			// Proposals carry the proposing faction as context; the player's own events use the player.
			for (const FEffect& Effect : Choice.Effects)
			{
				EventsDetail::ApplyEffect(State, Effect, Context);
			}
		}

		void QueueProposal(FGameState& State, int FromFaction, bool bAlliance)
		{
			const int Player = State.PlayerFaction;
			if (!IsAliveFaction(State, FromFaction) || !IsAliveFaction(State, Player) || FromFaction == Player)
			{
				return;
			}
			for (const FPendingEvent& Pending : State.PendingEvents)
			{
				if (Pending.Def < 0 && Pending.Faction == FromFaction)
				{
					return;
				}
			}
			const int Months = bAlliance ? Balance::AllianceMonths : Balance::TruceMonths;
			FPendingEvent Pending;
			Pending.Def = -1;
			Pending.Faction = FromFaction;
			Pending.City = At(State.Factions, Player).Capital;
			Pending.Speaker = RulerOf(State, FromFaction);
			Pending.Officer = Pending.Speaker;
			Pending.Image = "Events/Envoy.png";
			const std::string Faction = FactionLabel(State, FromFaction);
			const std::string Ruler = OfficerLabel(State, Pending.Speaker);
			const std::string City = CityLabel(State, Pending.City);
			Pending.Title = LocF("event.envoy.title", "Envoy from the {faction}", {{"faction", Faction}});
			Pending.Text = bAlliance
				? LocF("event.envoy.alliance", "An envoy of {ruler} of the {faction} has arrived in {city}. {ruler} proposes an alliance between our houses for {months} months. Do you accept?", {{"ruler", Ruler}, {"faction", Faction}, {"city", City}, {"months", ToText(Months)}})
				: LocF("event.envoy.truce", "An envoy of {ruler} of the {faction} has arrived in {city}. {ruler} proposes to lay down arms for {months} months. Do you accept?", {{"ruler", Ruler}, {"faction", Faction}, {"city", City}, {"months", ToText(Months)}});

			FEventChoice Accept;
			Accept.Label = Loc("event.envoy.accept", "Accept");
			FEffect Pact;
			Pact.Type = bAlliance ? EEffectType::Alliance : EEffectType::Truce;
			Pact.Amount = Months;
			Pact.Faction = FromFaction;
			Accept.Effects.push_back(Pact);
			FEffect Warmth;
			Warmth.Type = EEffectType::Trust;
			Warmth.Amount = 5;
			Warmth.Faction = FromFaction;
			Accept.Effects.push_back(Warmth);

			FEventChoice Decline;
			Decline.Label = Loc("event.envoy.decline", "Decline");
			FEffect Snub;
			Snub.Type = EEffectType::Trust;
			Snub.Amount = -5;
			Snub.Faction = FromFaction;
			Decline.Effects.push_back(Snub);

			Pending.Choices.push_back(Accept);
			Pending.Choices.push_back(Decline);
			State.PendingEvents.push_back(Pending);
		}

		int AdvisorOf(const FGameState& State, int Faction)
		{
			const int Ruler = RulerOf(State, Faction);
			int Best = -1;
			for (const int Officer : ServingOfficers(State, Faction))
			{
				if (Officer == Ruler)
				{
					continue;
				}
				if (Best < 0 || StatOf(At(State.Officers, Officer), EStat::Strategy) > StatOf(At(State.Officers, Best), EStat::Strategy))
				{
					Best = Officer;
				}
			}
			return Best >= 0 ? Best : Ruler;
		}
	}

	// =============================================================================================
	// FGame: events
	// =============================================================================================

	const FPendingEvent* FGame::CurrentEvent() const
	{
		return State.PendingEvents.empty() ? nullptr : &State.PendingEvents.front();
	}

	bool FGame::CanChoose(int ChoiceIndex) const
	{
		return GameRules::CanChooseRules(State, ChoiceIndex);
	}

	void FGame::ChooseEventOption(int ChoiceIndex)
	{
		GameRules::ChooseRules(State, ChoiceIndex);
		GameRules::UpdateFactions(State);
	}
}
