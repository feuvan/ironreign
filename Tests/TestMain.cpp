#include "IronTest.h"

#include <cstring>
#include <fstream>
#include <sstream>

namespace IronTest
{
	namespace
	{
		int FailureCount = 0;
	}

	std::vector<FCase>& Registry()
	{
		static std::vector<FCase> Cases;
		return Cases;
	}

	void ReportFailure(const char* File, int Line, const std::string& Message)
	{
		++FailureCount;
		std::fprintf(stderr, "  FAILED %s:%d: %s\n", File, Line, Message.c_str());
	}

	std::string DataDir()
	{
		return IRON_DATA_DIR;
	}

	bool ReadFile(const std::string& Path, std::string& OutText)
	{
		std::ifstream Stream(Path, std::ios::binary);
		if (!Stream)
		{
			return false;
		}
		std::ostringstream Buffer;
		Buffer << Stream.rdbuf();
		OutText = Buffer.str();
		return true;
	}
}

// Usage: IronSimTests [substring filter]
int main(int ArgCount, char** Args)
{
	const char* Filter = ArgCount > 1 ? Args[1] : nullptr;
	int Run = 0;
	int FailedCases = 0;
	for (const IronTest::FCase& Case : IronTest::Registry())
	{
		if (Filter && !std::strstr(Case.Name, Filter))
		{
			continue;
		}
		const int Before = IronTest::FailureCount;
		std::printf("[ RUN  ] %s\n", Case.Name);
		std::fflush(stdout);
		Case.Function();
		++Run;
		if (IronTest::FailureCount != Before)
		{
			++FailedCases;
			std::printf("[ FAIL ] %s\n", Case.Name);
		}
		else
		{
			std::printf("[  OK  ] %s\n", Case.Name);
		}
	}
	std::printf("%d test(s) run, %d failed\n", Run, FailedCases);
	return FailedCases == 0 ? 0 : 1;
}
