#pragma once

// Tiny self-registering test framework for the Sim unit tests (no external dependencies).

#include <cstdio>
#include <string>
#include <vector>

namespace IronTest
{
	struct FCase
	{
		const char* Name;
		void (*Function)();
	};

	std::vector<FCase>& Registry();
	void ReportFailure(const char* File, int Line, const std::string& Message);
	/** Absolute path of Content/Data. */
	std::string DataDir();
	/** Reads a whole file; returns false if missing. */
	bool ReadFile(const std::string& Path, std::string& OutText);

	struct FRegistrar
	{
		FRegistrar(const char* Name, void (*Function)())
		{
			Registry().push_back({Name, Function});
		}
	};
}

#define IRON_TEST(Name) \
	static void Name(); \
	static IronTest::FRegistrar Name##Registrar(#Name, &Name); \
	static void Name()

#define IRON_EXPECT(Condition) \
	do \
	{ \
		if (!(Condition)) \
		{ \
			IronTest::ReportFailure(__FILE__, __LINE__, #Condition); \
		} \
	} while (0)

#define IRON_EXPECT_MSG(Condition, Message) \
	do \
	{ \
		if (!(Condition)) \
		{ \
			IronTest::ReportFailure(__FILE__, __LINE__, std::string(#Condition) + " : " + (Message)); \
		} \
	} while (0)

#define IRON_EXPECT_EQ(Actual, Expected) \
	do \
	{ \
		const auto IronActualValue = (Actual); \
		const auto IronExpectedValue = (Expected); \
		if (!(IronActualValue == IronExpectedValue)) \
		{ \
			IronTest::ReportFailure(__FILE__, __LINE__, std::string(#Actual) + " == " + #Expected + " (got " + std::to_string(IronActualValue) + ", expected " + std::to_string(IronExpectedValue) + ")"); \
		} \
	} while (0)
