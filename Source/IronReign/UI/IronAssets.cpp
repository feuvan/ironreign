#include "UI/IronAssets.h"

#include "IronReignLog.h"
#include "UI/IronSession.h"

#include "Brushes/SlateColorBrush.h"
#include "Engine/Texture2D.h"
#include "HAL/FileManager.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Modules/ModuleManager.h"
#include "TextureResource.h"

namespace IronAssetsDetail
{
	/** Decodes PNG bytes into a transient BGRA8 sRGB texture. Returns nullptr (and logs) on failure. */
	UTexture2D* DecodePngTexture(const TArray<uint8>& Bytes, const FString& DebugName, FVector2D& OutSize)
	{
		IImageWrapperModule& ImageWrapperModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName(TEXT("ImageWrapper")));
		const TSharedPtr<IImageWrapper> Wrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
		if (!Wrapper.IsValid() || Bytes.Num() == 0 || !Wrapper->SetCompressed(Bytes.GetData(), Bytes.Num()))
		{
			UE_LOG(LogIronReign, Warning, TEXT("Art %s is not a readable PNG."), *DebugName);
			return nullptr;
		}

		TArray64<uint8> Raw;
		if (!Wrapper->GetRaw(ERGBFormat::BGRA, 8, Raw))
		{
			UE_LOG(LogIronReign, Warning, TEXT("Art %s could not be decoded to BGRA8."), *DebugName);
			return nullptr;
		}

		const int32 Width = static_cast<int32>(Wrapper->GetWidth());
		const int32 Height = static_cast<int32>(Wrapper->GetHeight());
		const int64 ExpectedBytes = static_cast<int64>(Width) * static_cast<int64>(Height) * 4;
		if (Width <= 0 || Height <= 0 || Raw.Num() < ExpectedBytes)
		{
			UE_LOG(LogIronReign, Warning, TEXT("Art %s has an unexpected size (%dx%d)."), *DebugName, Width, Height);
			return nullptr;
		}

		UTexture2D* Texture = UTexture2D::CreateTransient(Width, Height, PF_B8G8R8A8);
		if (Texture == nullptr)
		{
			UE_LOG(LogIronReign, Warning, TEXT("Could not create a %dx%d texture for %s."), Width, Height, *DebugName);
			return nullptr;
		}
		FTexturePlatformData* PlatformData = Texture->GetPlatformData();
		if (PlatformData == nullptr || PlatformData->Mips.Num() == 0)
		{
			UE_LOG(LogIronReign, Warning, TEXT("Texture for %s has no mip data."), *DebugName);
			return nullptr;
		}

		FTexture2DMipMap& Mip = PlatformData->Mips[0];
		void* Destination = Mip.BulkData.Lock(LOCK_READ_WRITE);
		if (Destination != nullptr)
		{
			const int64 CopyBytes = FMath::Min<int64>(Mip.BulkData.GetBulkDataSize(), ExpectedBytes);
			FMemory::Memcpy(Destination, Raw.GetData(), static_cast<SIZE_T>(CopyBytes));
		}
		Mip.BulkData.Unlock();

		Texture->SRGB = true;
		Texture->Filter = TF_Bilinear;
		Texture->LODGroup = TEXTUREGROUP_UI;
		Texture->UpdateResource();

		OutSize = FVector2D(static_cast<double>(Width), static_cast<double>(Height));
		return Texture;
	}
}

FIronAssets& FIronAssets::Get()
{
	// Intentionally leaked: textures must never be released during static destruction (after the UObject system).
	static FIronAssets* Instance = new FIronAssets();
	return *Instance;
}

FIronAssets::FEntry* FIronAssets::Load(const FString& RelativePath)
{
	if (FEntry* Existing = Images.Find(RelativePath))
	{
		return Existing;
	}

	FEntry NewEntry;
	const FString FullPath = FIronSession::DataDir() / RelativePath;
	TArray<uint8> Bytes;
	if (!FFileHelper::LoadFileToArray(Bytes, *FullPath, FILEREAD_Silent))
	{
		// Logged once: the failed entry is cached below.
		UE_LOG(LogIronReign, Warning, TEXT("Missing art file %s (using a placeholder)."), *FPaths::ConvertRelativePathToFull(FullPath));
	}
	else if (UTexture2D* Decoded = IronAssetsDetail::DecodePngTexture(Bytes, RelativePath, NewEntry.Size))
	{
		NewEntry.Texture.Reset(Decoded);
		NewEntry.Brush = MakeShared<FSlateBrush>();
		NewEntry.Brush->SetResourceObject(Decoded);
		NewEntry.Brush->ImageSize = NewEntry.Size;
		NewEntry.Brush->DrawAs = ESlateBrushDrawType::Image;
	}
	return &Images.Add(RelativePath, MoveTemp(NewEntry));
}

const FSlateBrush* FIronAssets::Image(const FString& RelativePath)
{
	const FEntry* Entry = Load(RelativePath);
	if (Entry != nullptr && Entry->Brush.IsValid())
	{
		return Entry->Brush.Get();
	}
	if (!MissingBrush.IsValid())
	{
		MissingBrush = MakeShared<FSlateColorBrush>(FLinearColor(0.85f, 0.1f, 0.6f, 0.55f));
	}
	return MissingBrush.Get();
}

const FSlateBrush* FIronAssets::Box(const FString& RelativePath, const FMargin& PixelMargin)
{
	const FString Key = FString::Printf(TEXT("%s|%.2f|%.2f|%.2f|%.2f"), *RelativePath, PixelMargin.Left, PixelMargin.Top, PixelMargin.Right, PixelMargin.Bottom);
	if (const TSharedPtr<FSlateBrush>* Found = Boxes.Find(Key))
	{
		return Found->Get();
	}

	const FEntry* Entry = Load(RelativePath);
	if (Entry == nullptr || !Entry->Brush.IsValid() || Entry->Size.X <= 0.0 || Entry->Size.Y <= 0.0)
	{
		return Image(RelativePath);
	}

	TSharedPtr<FSlateBrush> BoxBrush = MakeShared<FSlateBrush>(*Entry->Brush);
	BoxBrush->DrawAs = ESlateBrushDrawType::Box;
	BoxBrush->Margin = FMargin(
		static_cast<float>(PixelMargin.Left / Entry->Size.X),
		static_cast<float>(PixelMargin.Top / Entry->Size.Y),
		static_cast<float>(PixelMargin.Right / Entry->Size.X),
		static_cast<float>(PixelMargin.Bottom / Entry->Size.Y));
	Boxes.Add(Key, BoxBrush);
	return BoxBrush.Get();
}

const FSlateBrush* FIronAssets::Portrait(const FString& PortraitId)
{
	if (!PortraitId.IsEmpty())
	{
		const FString Path = FString::Printf(TEXT("Art/Portraits/%s.png"), *PortraitId);
		const FEntry* Entry = Images.Find(Path);
		if (Entry == nullptr)
		{
			if (Exists(Path))
			{
				Entry = Load(Path);
			}
			else
			{
				// Remember the miss quietly: officers without art use the silhouette.
				Entry = &Images.Add(Path, FEntry());
			}
		}
		if (Entry != nullptr && Entry->Brush.IsValid())
		{
			return Entry->Brush.Get();
		}
	}
	return Image(TEXT("Art/Portraits/unknown.png"));
}

const FSlateBrush* FIronAssets::Icon(const FString& Name)
{
	return Image(FString::Printf(TEXT("Art/UI/Icon_%s.png"), *Name));
}

const FSlateBrush* FIronAssets::White()
{
	if (!WhiteBrush.IsValid())
	{
		WhiteBrush = MakeShared<FSlateColorBrush>(FLinearColor::White);
	}
	return WhiteBrush.Get();
}

FVector2D FIronAssets::ImageSize(const FString& RelativePath)
{
	const FEntry* Entry = Load(RelativePath);
	return Entry != nullptr ? Entry->Size : FVector2D::ZeroVector;
}

UTexture2D* FIronAssets::Texture(const FString& RelativePath)
{
	const FEntry* Entry = Load(RelativePath);
	return Entry != nullptr ? Entry->Texture.Get() : nullptr;
}

bool FIronAssets::Exists(const FString& RelativePath) const
{
	if (const FEntry* Entry = Images.Find(RelativePath))
	{
		if (Entry->Texture.IsValid())
		{
			return true;
		}
	}
	return FPaths::FileExists(FIronSession::DataDir() / RelativePath);
}

void FIronAssets::Reset()
{
	Boxes.Empty();
	Images.Empty();
}
