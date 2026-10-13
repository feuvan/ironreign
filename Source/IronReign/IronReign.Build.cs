using UnrealBuildTool;

public class IronReign : ModuleRules
{
	public IronReign(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		// Headers are included relative to the module root, e.g. "Sim/IronGame.h" and "UI/IronStyle.h".
		PublicIncludePaths.Add(ModuleDirectory);

		PublicDependencyModuleNames.AddRange(new[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"EnhancedInput",
			"GameplayTags",
			"GameplayAbilities",
			"GameplayTasks",
			// Public UI headers (SIronRoot.h, IronStyle.h) expose Slate types.
			"Slate",
			"SlateCore"
		});

		PrivateDependencyModuleNames.AddRange(new[]
		{
			"UMG",
			// Runtime PNG decoding for Content/Data/Art (FIronAssets).
			"ImageWrapper"
		});
	}
}
