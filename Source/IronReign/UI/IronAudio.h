#pragma once

#include "CoreMinimal.h"
#include "Templates/UniquePtr.h"

class UWorld;

/**
 * Music and sound-effect player. Plays the generated WAVs in Content/Data/Audio (16-bit PCM, mono or stereo;
 * see Tools/AudioGen) through procedural sound waves, so the game needs no imported .uasset sounds.
 *
 *   FIronAudio::Get().Initialize(World);          // once a game world exists (no-op without an audio device)
 *   FIronAudio::Get().PlayMusic(TEXT("Strategy")); // Audio/Music_Strategy.wav, looped, crossfaded
 *   FIronAudio::Get().PlaySfx(TEXT("Click"));      // Audio/Sfx_Click.wav, up to 8 voices at once
 *   FIronAudio::Get().Shutdown();                 // before the world / engine goes away
 *
 * Game thread only. Every call is a safe no-op when there is no world, no audio device (dedicated server,
 * -nosound, -nullrhi automation) or the file is missing (logged once). Decoded PCM is cached per file.
 * PlayMusic may be called before Initialize: the requested track starts once a world is attached.
 */
class IRONREIGN_API FIronAudio
{
public:
	static FIronAudio& Get();

	/** Attaches to the world sounds are created in. Switching worlds stops the voices of the previous one. */
	void Initialize(UWorld* World);
	/** Stops everything and releases all sound objects and cached PCM. */
	void Shutdown();

	/**
	 * Crossfades to Audio/Music_<TrackName>.wav. Requesting the track that is already playing does nothing.
	 * bLoop = false for the stings (Victory, Defeat): they play once and then stay silent.
	 */
	void PlayMusic(const FString& TrackName, bool bLoop = true);
	/** Fades the current music out. */
	void StopMusic();
	/** Plays Audio/Sfx_<Name>.wav once. The same effect re-triggered within 30 ms is ignored. */
	void PlaySfx(const FString& Name);
	/**
	 * Number of PlaySfx calls so far (audible or not). Lets a caller tell whether some code it ran requested an
	 * effect, e.g. IronStyle buttons play "Click" only when their handler did not already play a specific sound.
	 */
	uint32 GetSfxRequestCount() const;

	/** Volumes are linear multipliers in [0, 1] and apply immediately (also to sounds already playing). */
	void SetMusicVolume(float Volume);
	void SetSfxVolume(float Volume);
	float GetMusicVolume() const;
	float GetSfxVolume() const;

	/** Track requested by the last PlayMusic call (empty after StopMusic). */
	FString GetCurrentMusic() const;
	/** True when a world with an audio device is attached, i.e. sounds can actually be heard. */
	bool IsAudioAvailable() const;

	FIronAudio(const FIronAudio&) = delete;
	FIronAudio& operator=(const FIronAudio&) = delete;

private:
	FIronAudio();
	~FIronAudio();

	/** All state (UObject handles, PCM cache) lives in the .cpp so this header stays light. */
	struct FState;
	TUniquePtr<FState> State;
};
