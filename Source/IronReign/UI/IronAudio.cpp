#include "UI/IronAudio.h"

#include "Components/AudioComponent.h"
#include "CoreGlobals.h"
#include "Engine/Engine.h"
#include "Engine/World.h"
#include "HAL/FileManager.h"
#include "HAL/PlatformTime.h"
#include "Kismet/GameplayStatics.h"
#include "Math/NumericLimits.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Sound/SoundWaveProcedural.h"
#include "Templates/SharedPointer.h"
#include "UObject/Package.h"
#include "UObject/StrongObjectPtr.h"
#include "UObject/WeakObjectPtrTemplates.h"

#include <atomic>

DEFINE_LOG_CATEGORY_STATIC(LogIronAudio, Log, All);

namespace IronAudioDetail
{
	/**
	 * Decoded PCM of one WAV file: interleaved little-endian int16 frames. Immutable once loaded, so the audio
	 * render thread can read it without locking.
	 */
	struct FPcmClip
	{
		TArray<uint8> Bytes;
		int32 SampleRate = 0;
		int32 NumChannels = 0;
		float Duration = 0.0f;
	};

	using FPcmClipPtr = TSharedPtr<const FPcmClip, ESPMode::ThreadSafe>;

	/**
	 * Read position of a streamed music voice. The game thread primes it before the sound starts; afterwards only
	 * the audio render thread (underflow callback) advances it.
	 */
	struct FPcmStream
	{
		FPcmClipPtr Clip;
		std::atomic<int64> CursorBytes{0};
		bool bLoop = true;
	};

	using FPcmStreamPtr = TSharedPtr<FPcmStream, ESPMode::ThreadSafe>;

	constexpr int32 StreamChunkFrames = 8192;  // frames queued per underflow (~0.37 s at 22050 Hz)
	constexpr int32 MaxSfxVoices = 8;
	constexpr float MusicFadeInSeconds = 1.5f;
	constexpr float MusicFadeOutSeconds = 1.5f;
	constexpr double SfxRetriggerSeconds = 0.03;
	constexpr double VoiceEndSlackSeconds = 0.5;
	constexpr float MinAudibleVolume = 0.001f;

	static uint16 ReadLE16(const uint8* Data)
	{
		return static_cast<uint16>(static_cast<uint32>(Data[0]) | (static_cast<uint32>(Data[1]) << 8));
	}

	static uint32 ReadLE32(const uint8* Data)
	{
		return static_cast<uint32>(Data[0]) | (static_cast<uint32>(Data[1]) << 8) | (static_cast<uint32>(Data[2]) << 16) |
			(static_cast<uint32>(Data[3]) << 24);
	}

	static bool HasFourCC(const uint8* Data, const char* Tag)
	{
		return Data[0] == static_cast<uint8>(Tag[0]) && Data[1] == static_cast<uint8>(Tag[1]) && Data[2] == static_cast<uint8>(Tag[2]) &&
			Data[3] == static_cast<uint8>(Tag[3]);
	}

	/** Minimal RIFF/WAVE reader: "fmt " + "data" chunks, 16-bit PCM (plain or WAVE_FORMAT_EXTENSIBLE), 1-2 channels. */
	static FPcmClipPtr ParseWav(const TArray<uint8>& File, const FString& Label)
	{
		const uint8* Data = File.GetData();
		const int64 Size = File.Num();
		if (Size < 12 || !HasFourCC(Data, "RIFF") || !HasFourCC(Data + 8, "WAVE"))
		{
			UE_LOG(LogIronAudio, Warning, TEXT("%s: not a RIFF/WAVE file"), *Label);
			return nullptr;
		}

		uint16 Format = 0;
		uint16 Channels = 0;
		uint16 BitsPerSample = 0;
		uint32 SampleRate = 0;
		int64 DataOffset = -1;
		int64 DataSize = 0;
		int64 Pos = 12;
		while (Pos + 8 <= Size)
		{
			const uint8* Chunk = Data + Pos;
			const int64 ChunkSize = static_cast<int64>(ReadLE32(Chunk + 4));
			const int64 Body = Pos + 8;
			const int64 Available = FMath::Min<int64>(ChunkSize, Size - Body);
			if (HasFourCC(Chunk, "fmt ") && Available >= 16)
			{
				Format = ReadLE16(Data + Body);
				Channels = ReadLE16(Data + Body + 2);
				SampleRate = ReadLE32(Data + Body + 4);
				BitsPerSample = ReadLE16(Data + Body + 14);
				if (Format == 0xFFFE && Available >= 26)
				{
					// WAVE_FORMAT_EXTENSIBLE: the sub-format GUID at offset 24 starts with the actual format tag.
					Format = ReadLE16(Data + Body + 24);
				}
			}
			else if (HasFourCC(Chunk, "data") && DataOffset < 0)
			{
				DataOffset = Body;
				DataSize = FMath::Max<int64>(Available, 0);
			}
			Pos = Body + ChunkSize + (ChunkSize & 1);  // chunks are padded to an even size
		}

		if (Format != 1 || BitsPerSample != 16 || Channels < 1 || Channels > 2 || SampleRate < 8000 || SampleRate > 192000)
		{
			UE_LOG(LogIronAudio, Warning, TEXT("%s: unsupported WAV (format %d, %d channels, %d bits, %d Hz); expected 16-bit PCM mono/stereo"),
				*Label, static_cast<int32>(Format), static_cast<int32>(Channels), static_cast<int32>(BitsPerSample), static_cast<int32>(SampleRate));
			return nullptr;
		}
		const int64 FrameBytes = 2 * static_cast<int64>(Channels);
		DataSize -= DataSize % FrameBytes;
		if (DataOffset < 0 || DataSize <= 0 || DataSize > static_cast<int64>(TNumericLimits<int32>::Max()))
		{
			UE_LOG(LogIronAudio, Warning, TEXT("%s: missing, empty or oversized data chunk"), *Label);
			return nullptr;
		}

		TSharedRef<FPcmClip, ESPMode::ThreadSafe> Clip = MakeShared<FPcmClip, ESPMode::ThreadSafe>();
		Clip->Bytes.Append(Data + DataOffset, static_cast<int32>(DataSize));
		Clip->SampleRate = static_cast<int32>(SampleRate);
		Clip->NumChannels = static_cast<int32>(Channels);
		Clip->Duration = static_cast<float>(static_cast<double>(DataSize / FrameBytes) / static_cast<double>(SampleRate));
		return Clip;
	}

	/**
	 * Queues the next chunk of a streamed clip (at least NumSamplesRequired samples), wrapping around for loops.
	 * Called on the game thread to prime a voice and then on the audio render thread from the underflow callback.
	 */
	static void FeedStream(FPcmStream& Stream, USoundWaveProcedural* Wave, const int32 NumSamplesRequired)
	{
		if (Wave == nullptr || !Stream.Clip.IsValid())
		{
			return;
		}
		const TArray<uint8>& Bytes = Stream.Clip->Bytes;
		const int64 Total = Bytes.Num();
		const int64 FrameBytes = 2 * static_cast<int64>(Stream.Clip->NumChannels);
		if (FrameBytes <= 0 || Total < FrameBytes)
		{
			return;
		}
		int64 Wanted = FMath::Max<int64>(static_cast<int64>(NumSamplesRequired) * 2, static_cast<int64>(StreamChunkFrames) * FrameBytes);
		Wanted -= Wanted % FrameBytes;
		int64 Cursor = Stream.CursorBytes.load(std::memory_order_acquire);
		while (Wanted > 0)
		{
			if (Cursor >= Total)
			{
				if (!Stream.bLoop)
				{
					break;
				}
				Cursor = 0;
			}
			const int64 Count = FMath::Min<int64>(Wanted, Total - Cursor);
			Wave->QueueAudio(Bytes.GetData() + Cursor, static_cast<int32>(Count));
			Cursor += Count;
			Wanted -= Count;
		}
		Stream.CursorBytes.store(Cursor, std::memory_order_release);
	}

	static USoundWaveProcedural* NewProceduralWave(const FPcmClip& Clip, const bool bIndefinite)
	{
		USoundWaveProcedural* Wave = NewObject<USoundWaveProcedural>(GetTransientPackage());
		Wave->SetSampleRate(static_cast<uint32>(Clip.SampleRate));
		Wave->NumChannels = Clip.NumChannels;
		Wave->Duration = bIndefinite ? INDEFINITELY_LOOPING_DURATION : Clip.Duration;
		Wave->SoundGroup = SOUNDGROUP_Default;
		return Wave;
	}

	/** "Strategy" -> "Audio/Music_Strategy.wav"; a name that already ends in .wav is taken relative to Audio/. */
	static FString AudioPath(const TCHAR* Prefix, const FString& Name)
	{
		if (Name.EndsWith(TEXT(".wav")))
		{
			return FString::Printf(TEXT("Audio/%s"), *Name);
		}
		return FString::Printf(TEXT("Audio/%s%s.wav"), Prefix, *Name);
	}
}

struct FIronAudio::FState
{
	struct FVoice
	{
		TStrongObjectPtr<UAudioComponent> Component;
		TStrongObjectPtr<USoundWaveProcedural> Wave;
		FString Name;
		/** FPlatformTime::Seconds() after which the voice is certainly silent (procedural waves never "finish"). */
		double EndTime = 0.0;
	};

	TWeakObjectPtr<UWorld> WorldPtr;
	TMap<FString, IronAudioDetail::FPcmClipPtr> Clips;
	TSet<FString> MissingClips;
	FVoice Music;
	TArray<FVoice> FadingMusic;
	TArray<FVoice> SfxVoices;
	TMap<FString, double> LastSfxTimes;
	FString MusicTrack;
	bool bMusicLoop = true;
	uint32 SfxRequests = 0;
	float MusicVolume = 0.7f;
	float SfxVolume = 0.8f;

	/** The attached world if sounds can be heard in it, else nullptr. */
	UWorld* GetPlayableWorld() const
	{
		UWorld* World = WorldPtr.Get();
		if (World == nullptr || GEngine == nullptr || !GEngine->UseSound() || IsRunningDedicatedServer())
		{
			return nullptr;
		}
		if (World->GetAudioDeviceRaw() == nullptr && GEngine->GetMainAudioDeviceRaw() == nullptr)
		{
			return nullptr;
		}
		return World;
	}

	static bool IsActive(const FVoice& Voice, const double Now)
	{
		const UAudioComponent* Component = Voice.Component.Get();
		return Component != nullptr && IsValid(Component) && Component->IsPlaying() && Now < Voice.EndTime;
	}

	static void StopVoice(FVoice& Voice)
	{
		UAudioComponent* Component = Voice.Component.Get();
		if (Component != nullptr && IsValid(Component))
		{
			Component->Stop();
		}
		Voice.Component.Reset();
		Voice.Wave.Reset();
		Voice.Name.Reset();
		Voice.EndTime = 0.0;
	}

	void StopAll()
	{
		StopVoice(Music);
		for (FVoice& Voice : FadingMusic)
		{
			StopVoice(Voice);
		}
		for (FVoice& Voice : SfxVoices)
		{
			StopVoice(Voice);
		}
		FadingMusic.Reset();
		SfxVoices.Reset();
	}

	/** Releases finished fades and stings, and silences effects that ran past their length. */
	void Prune(const double Now)
	{
		for (int32 Index = FadingMusic.Num() - 1; Index >= 0; --Index)
		{
			if (!IsActive(FadingMusic[Index], Now))
			{
				StopVoice(FadingMusic[Index]);
				FadingMusic.RemoveAtSwap(Index);
			}
		}
		if (Music.Component.IsValid() && !IsActive(Music, Now))
		{
			StopVoice(Music);
		}
		for (FVoice& Voice : SfxVoices)
		{
			UAudioComponent* Component = Voice.Component.Get();
			if (Component != nullptr && IsValid(Component) && Now >= Voice.EndTime && Component->IsPlaying())
			{
				Component->Stop();
			}
		}
	}

	IronAudioDetail::FPcmClipPtr LoadClip(const FString& RelativePath)
	{
		if (const IronAudioDetail::FPcmClipPtr* Cached = Clips.Find(RelativePath))
		{
			return *Cached;
		}
		if (MissingClips.Contains(RelativePath))
		{
			return nullptr;
		}
		const FString FullPath = FPaths::ProjectContentDir() / TEXT("Data") / RelativePath;
		TArray<uint8> FileBytes;
		IronAudioDetail::FPcmClipPtr Clip;
		if (FFileHelper::LoadFileToArray(FileBytes, *FullPath, FILEREAD_Silent))
		{
			Clip = IronAudioDetail::ParseWav(FileBytes, FullPath);
		}
		else
		{
			UE_LOG(LogIronAudio, Warning, TEXT("Audio file not found: %s"), *FullPath);
		}
		if (!Clip.IsValid())
		{
			MissingClips.Add(RelativePath);
			return nullptr;
		}
		Clips.Add(RelativePath, Clip);
		return Clip;
	}

	void StartRequestedMusic(const double Now)
	{
		if (MusicTrack.IsEmpty() || MusicVolume <= IronAudioDetail::MinAudibleVolume)
		{
			return;
		}
		UWorld* World = GetPlayableWorld();
		if (World == nullptr)
		{
			return;
		}
		const IronAudioDetail::FPcmClipPtr Clip = LoadClip(IronAudioDetail::AudioPath(TEXT("Music_"), MusicTrack));
		if (!Clip.IsValid())
		{
			return;
		}

		IronAudioDetail::FPcmStreamPtr Stream = MakeShared<IronAudioDetail::FPcmStream, ESPMode::ThreadSafe>();
		Stream->Clip = Clip;
		Stream->bLoop = bMusicLoop;
		USoundWaveProcedural* Wave = IronAudioDetail::NewProceduralWave(*Clip, bMusicLoop);
		IronAudioDetail::FeedStream(*Stream, Wave, 0);  // prime the queue before the sound starts
		Wave->OnSoundWaveProceduralUnderflow.BindLambda([Stream](USoundWaveProcedural* InWave, int32 NumSamplesRequired)
		{
			// Audio render thread: only touches the immutable shared clip and the stream's atomic cursor.
			IronAudioDetail::FeedStream(*Stream, InWave, NumSamplesRequired);
		});

		UAudioComponent* Component = UGameplayStatics::CreateSound2D(World, Wave, MusicVolume, 1.0f, 0.0f, nullptr, false, false);
		if (Component == nullptr)
		{
			return;
		}
		if (bMusicLoop)
		{
			Component->FadeIn(IronAudioDetail::MusicFadeInSeconds, 1.0f);
		}
		else
		{
			Component->Play();
		}
		Music.Component.Reset(Component);
		Music.Wave.Reset(Wave);
		Music.Name = MusicTrack;
		Music.EndTime = bMusicLoop ? TNumericLimits<double>::Max() : Now + Clip->Duration + IronAudioDetail::VoiceEndSlackSeconds;
	}

	void FadeOutMusic(const double Now)
	{
		UAudioComponent* Component = Music.Component.Get();
		if (Component != nullptr && IsActive(Music, Now))
		{
			Component->FadeOut(IronAudioDetail::MusicFadeOutSeconds, 0.0f);
			Music.EndTime = FMath::Min(Music.EndTime, Now + IronAudioDetail::MusicFadeOutSeconds + IronAudioDetail::VoiceEndSlackSeconds);
			FadingMusic.Add(MoveTemp(Music));
			Music = FVoice();
		}
		else
		{
			StopVoice(Music);
		}
	}

	FVoice& PickSfxVoice(const double Now)
	{
		for (FVoice& Voice : SfxVoices)
		{
			if (!IsActive(Voice, Now))
			{
				return Voice;
			}
		}
		if (SfxVoices.Num() < IronAudioDetail::MaxSfxVoices)
		{
			return SfxVoices.AddDefaulted_GetRef();
		}
		FVoice* Oldest = &SfxVoices[0];
		for (FVoice& Voice : SfxVoices)
		{
			if (Voice.EndTime < Oldest->EndTime)
			{
				Oldest = &Voice;
			}
		}
		return *Oldest;
	}

	void PlaySfx(const FString& SfxName)
	{
		if (SfxName.IsEmpty() || SfxVolume <= IronAudioDetail::MinAudibleVolume)
		{
			return;
		}
		UWorld* World = GetPlayableWorld();
		if (World == nullptr)
		{
			return;
		}
		const double Now = FPlatformTime::Seconds();
		Prune(Now);
		if (const double* LastTime = LastSfxTimes.Find(SfxName))
		{
			if (Now - *LastTime < IronAudioDetail::SfxRetriggerSeconds)
			{
				return;
			}
		}
		const IronAudioDetail::FPcmClipPtr Clip = LoadClip(IronAudioDetail::AudioPath(TEXT("Sfx_"), SfxName));
		if (!Clip.IsValid())
		{
			return;
		}

		// Effects are short: queue the whole clip up front, no streaming callback needed.
		USoundWaveProcedural* Wave = IronAudioDetail::NewProceduralWave(*Clip, false);
		Wave->QueueAudio(Clip->Bytes.GetData(), Clip->Bytes.Num());

		FVoice& Voice = PickSfxVoice(Now);
		UAudioComponent* Component = Voice.Component.Get();
		if (Component != nullptr && IsValid(Component) && Component->GetWorld() == World)
		{
			// Stop first so SetSound does not restart the old sound, then start the new one exactly once.
			Component->Stop();
			Component->SetSound(Wave);
			Component->SetVolumeMultiplier(SfxVolume);
		}
		else
		{
			Component = UGameplayStatics::CreateSound2D(World, Wave, SfxVolume, 1.0f, 0.0f, nullptr, false, false);
			if (Component == nullptr)
			{
				return;
			}
			Voice.Component.Reset(Component);
		}
		Voice.Wave.Reset(Wave);
		Voice.Name = SfxName;
		Voice.EndTime = Now + Clip->Duration + IronAudioDetail::VoiceEndSlackSeconds;
		Component->Play();
		LastSfxTimes.Add(SfxName, Now);
	}
};

FIronAudio& FIronAudio::Get()
{
	// Intentionally never destroyed: no static destructor may touch UObjects after the engine has shut down.
	// Shutdown() releases every sound object while the engine is still alive.
	static FIronAudio* Instance = new FIronAudio();
	return *Instance;
}

FIronAudio::FIronAudio()
	: State(MakeUnique<FState>())
{
}

FIronAudio::~FIronAudio() = default;

void FIronAudio::Initialize(UWorld* World)
{
	FState& S = *State;
	if (S.WorldPtr.Get() != World)
	{
		S.StopAll();
		S.WorldPtr = World;
	}
	const double Now = FPlatformTime::Seconds();
	if (S.bMusicLoop && !FState::IsActive(S.Music, Now))
	{
		S.StartRequestedMusic(Now);
	}
}

void FIronAudio::Shutdown()
{
	FState& S = *State;
	S.StopAll();
	S.Clips.Reset();
	S.MissingClips.Reset();
	S.LastSfxTimes.Reset();
	S.MusicTrack.Reset();
	S.bMusicLoop = true;
	S.WorldPtr.Reset();
}

void FIronAudio::PlayMusic(const FString& TrackName, const bool bLoop)
{
	FState& S = *State;
	const double Now = FPlatformTime::Seconds();
	S.Prune(Now);
	if (S.MusicTrack == TrackName && S.bMusicLoop == bLoop && FState::IsActive(S.Music, Now))
	{
		return;
	}
	S.FadeOutMusic(Now);
	S.MusicTrack = TrackName;
	S.bMusicLoop = bLoop;
	S.StartRequestedMusic(Now);
}

void FIronAudio::StopMusic()
{
	FState& S = *State;
	const double Now = FPlatformTime::Seconds();
	S.Prune(Now);
	S.FadeOutMusic(Now);
	S.MusicTrack.Reset();
	S.bMusicLoop = true;
}

void FIronAudio::PlaySfx(const FString& Name)
{
	++State->SfxRequests;
	State->PlaySfx(Name);
}

uint32 FIronAudio::GetSfxRequestCount() const
{
	return State->SfxRequests;
}

void FIronAudio::SetMusicVolume(const float Volume)
{
	FState& S = *State;
	S.MusicVolume = FMath::Clamp(Volume, 0.0f, 1.0f);
	const double Now = FPlatformTime::Seconds();
	if (S.MusicVolume <= IronAudioDetail::MinAudibleVolume)
	{
		// Muted: stop the voices (silent procedural sounds would still stream); the request resumes on unmute.
		FState::StopVoice(S.Music);
		for (FState::FVoice& Voice : S.FadingMusic)
		{
			FState::StopVoice(Voice);
		}
		S.FadingMusic.Reset();
	}
	else if (FState::IsActive(S.Music, Now))
	{
		S.Music.Component->SetVolumeMultiplier(S.MusicVolume);
	}
	else if (S.bMusicLoop)
	{
		S.StartRequestedMusic(Now);
	}
}

void FIronAudio::SetSfxVolume(const float Volume)
{
	FState& S = *State;
	S.SfxVolume = FMath::Clamp(Volume, 0.0f, 1.0f);
	const double Now = FPlatformTime::Seconds();
	for (FState::FVoice& Voice : S.SfxVoices)
	{
		if (FState::IsActive(Voice, Now))
		{
			Voice.Component->SetVolumeMultiplier(FMath::Max(S.SfxVolume, IronAudioDetail::MinAudibleVolume));
		}
	}
}

float FIronAudio::GetMusicVolume() const
{
	return State->MusicVolume;
}

float FIronAudio::GetSfxVolume() const
{
	return State->SfxVolume;
}

FString FIronAudio::GetCurrentMusic() const
{
	return State->MusicTrack;
}

bool FIronAudio::IsAudioAvailable() const
{
	return State->GetPlayableWorld() != nullptr;
}
