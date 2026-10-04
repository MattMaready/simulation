using UnrealBuildTool;

// SplunkerViz game module. Uses only engine modules that ship with every UE5
// install (no marketplace plugins): WebSockets for the ROS bridge connection,
// Json for parsing its messages, DeveloperSettings for Project Settings.
public class SplunkerViz : ModuleRules
{
	public SplunkerViz(ReadOnlyTargetRules Target) : base(Target)
	{
		PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;

		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",
			"CoreUObject",
			"Engine",
			"InputCore",
			"DeveloperSettings"
		});

		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"WebSockets",
			"Json",
			"JsonUtilities"
		});
	}
}
