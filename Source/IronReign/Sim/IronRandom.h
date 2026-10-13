#pragma once

#include <cstdint>

namespace IronSim
{
	/** Small deterministic generator (SplitMix64). State is a single 64-bit word so it round-trips through save games. */
	class FRng
	{
	public:
		FRng() = default;
		explicit FRng(uint64_t InSeed)
			: State(InSeed)
		{
		}

		uint32_t Next()
		{
			State += 0x9E3779B97F4A7C15ull;
			uint64_t Mixed = State;
			Mixed = (Mixed ^ (Mixed >> 30)) * 0xBF58476D1CE4E5B9ull;
			Mixed = (Mixed ^ (Mixed >> 27)) * 0x94D049BB133111EBull;
			Mixed ^= Mixed >> 31;
			return static_cast<uint32_t>(Mixed >> 32);
		}

		/** Uniform integer in [Low, High] (inclusive). Returns Low when the range is empty. */
		int Range(int Low, int High)
		{
			if (High <= Low)
			{
				return Low;
			}
			const uint64_t Span = static_cast<uint64_t>(static_cast<int64_t>(High) - static_cast<int64_t>(Low) + 1);
			return Low + static_cast<int>((static_cast<uint64_t>(Next()) * Span) >> 32);
		}

		/** True with the given percent probability (clamped to 0..100). */
		bool Chance(int Percent)
		{
			return Range(0, 99) < Percent;
		}

		/** Uniform double in [0, 1). */
		double Unit()
		{
			return static_cast<double>(Next()) / 4294967296.0;
		}

		/** Uniform double in [Low, High). */
		double Uniform(double Low, double High)
		{
			return Low + (High - Low) * Unit();
		}

		uint64_t GetState() const { return State; }
		void SetState(uint64_t InState) { State = InState; }

	private:
		uint64_t State = 0x853C49E6748FEA9Bull;
	};

	/** Stateless hash, handy for deterministic per-entity variation (e.g. battle map generation). */
	inline uint32_t HashCombine(uint32_t Seed, uint32_t Value)
	{
		uint32_t Hash = Seed ^ (Value + 0x9E3779B9u + (Seed << 6) + (Seed >> 2));
		Hash ^= Hash >> 16;
		Hash *= 0x7FEB352Du;
		Hash ^= Hash >> 15;
		Hash *= 0x846CA68Bu;
		Hash ^= Hash >> 16;
		return Hash;
	}
}
