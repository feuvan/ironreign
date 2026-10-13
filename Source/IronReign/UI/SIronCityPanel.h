#pragma once

#include "CoreMinimal.h"
#include "Widgets/DeclarativeSyntaxSupport.h"
#include "Widgets/SCompoundWidget.h"

class FIronSession;

/**
 * Left panel of the strategy screen: the selected city's name, owner, development, garrison, treasury and the
 * officers stationed there (portrait, stats, loyalty, current order), plus tavern wanderers, prisoners and sect.
 * Foreign cities only show what a Koei-style spy report would (rounded troops, officer count).
 */
class IRONREIGN_API SIronCityPanel : public SCompoundWidget
{
public:
	SLATE_BEGIN_ARGS(SIronCityPanel)
		: _City(-1)
	{}
		SLATE_ARGUMENT(TSharedPtr<FIronSession>, Session)
		SLATE_ARGUMENT(int32, City)
	SLATE_END_ARGS()

	void Construct(const FArguments& InArgs);

	void SetCity(int32 InCity);
	int32 GetCity() const { return CityIndex; }
	/** Rebuilds the lists when the city's contents changed; numbers update live. Cheap enough to call every day. */
	void Refresh();

private:
	enum class EField : uint8
	{
		Population,
		Farm,
		Commerce,
		Defense,
		Order,
		Troops,
		Training,
		Gold,
		Food
	};

	uint32 ComputeSignature() const;
	void Rebuild();
	TSharedRef<SWidget> BuildHeader() const;
	TSharedRef<SWidget> BuildStatLine(EField Field, bool bExact) const;
	TSharedRef<SWidget> BuildOfficerRow(int32 Officer, bool bDetailed) const;
	TSharedRef<SWidget> BuildCompactOfficerRow(int32 Officer, const FText& Note) const;

	int32 FieldValue(EField Field) const;
	int32 FieldMax(EField Field) const;
	FText FieldText(EField Field, bool bExact) const;
	float FieldFraction(EField Field) const;

	TSharedPtr<FIronSession> Session;
	int32 CityIndex = -1;
	uint32 Signature = 0;
};
