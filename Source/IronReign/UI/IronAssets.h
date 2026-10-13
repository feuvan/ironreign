#pragma once

#include "CoreMinimal.h"
#include "Engine/Texture2D.h"
#include "Styling/SlateBrush.h"
#include "UObject/StrongObjectPtr.h"

class UTexture2D;

/**
 * Runtime art loader. Decodes PNGs from Content/Data (via IImageWrapper), creates transient UTexture2Ds and
 * caches Slate brushes. Missing files yield a visible fallback brush instead of crashing.
 * All paths are relative to Content/Data, e.g. TEXT("Art/UI/Panel.png").
 */
class IRONREIGN_API FIronAssets
{
public:
	static FIronAssets& Get();

	/** Image brush sized to the texture. */
	const FSlateBrush* Image(const FString& RelativePath);
	/** 9-slice box brush. Margin is in pixels of the source texture (converted to UV fractions internally). */
	const FSlateBrush* Box(const FString& RelativePath, const FMargin& PixelMargin);
	/** Portrait brush for Art/Portraits/<Id>.png, falling back to Art/Portraits/unknown.png. */
	const FSlateBrush* Portrait(const FString& PortraitId);
	/** Art/UI/Icon_<Name>.png. */
	const FSlateBrush* Icon(const FString& Name);
	/** Solid white brush for tinted rectangles. */
	const FSlateBrush* White();
	/** Texture size in pixels (0,0 if missing). */
	FVector2D ImageSize(const FString& RelativePath);
	UTexture2D* Texture(const FString& RelativePath);
	bool Exists(const FString& RelativePath) const;

	/** Releases every texture and brush (called on shutdown). */
	void Reset();

private:
	struct FEntry
	{
		TStrongObjectPtr<UTexture2D> Texture;
		TSharedPtr<FSlateBrush> Brush;
		FVector2D Size = FVector2D::ZeroVector;
	};

	FEntry* Load(const FString& RelativePath);

	TMap<FString, FEntry> Images;
	TMap<FString, TSharedPtr<FSlateBrush>> Boxes;
	TSharedPtr<FSlateBrush> WhiteBrush;
	TSharedPtr<FSlateBrush> MissingBrush;
};
