#include "IronTest.h"

#include "Sim/IronJson.h"

using IronSim::FJson;

IRON_TEST(JsonParsesAndWritesRoundTrip)
{
	const std::string Text = "{\"a\": 1, \"b\": [1, 2.5, -3e2], \"c\": {\"d\": \"x\\ny\\u00e9\\ud83d\\ude00\"}, \"e\": true, \"f\": null} // trailing comment";
	FJson Root;
	std::string Error;
	IRON_EXPECT_MSG(FJson::Parse(Text, Root, Error), Error);
	IRON_EXPECT_EQ(Root.GetInt("a"), 1);
	IRON_EXPECT(Root.Get("b").Size() == 3);
	IRON_EXPECT(Root.Get("b").At(1).AsNumber() == 2.5);
	IRON_EXPECT(Root.Get("b").At(2).AsNumber() == -300.0);
	IRON_EXPECT(Root.Get("c").GetString("d") == "x\ny\xC3\xA9\xF0\x9F\x98\x80");
	IRON_EXPECT(Root.GetBool("e"));
	IRON_EXPECT(Root.Get("f").IsNull());
	IRON_EXPECT(Root.Get("missing").IsNull());

	FJson Again;
	IRON_EXPECT_MSG(FJson::Parse(Root.Write(true), Again, Error), Error);
	IRON_EXPECT(Again.Write(false) == Root.Write(false));
}

IRON_TEST(JsonReportsErrors)
{
	FJson Root;
	std::string Error;
	IRON_EXPECT(!FJson::Parse("{\"a\": }", Root, Error));
	IRON_EXPECT(!Error.empty());
	IRON_EXPECT(!FJson::Parse("[1, 2", Root, Error));
	IRON_EXPECT(!FJson::Parse("{\"a\": 1} x", Root, Error));
}

IRON_TEST(JsonWritesFractionsWithoutLocale)
{
	FJson Value = FJson::MakeNumber(-12.125);
	IRON_EXPECT(Value.Write(false) == "-12.125");
	IRON_EXPECT(FJson::MakeNumber(3).Write(false) == "3");
}
