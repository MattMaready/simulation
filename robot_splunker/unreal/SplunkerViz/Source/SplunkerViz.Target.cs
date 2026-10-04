using UnrealBuildTool;

public class SplunkerVizTarget : TargetRules
{
	public SplunkerVizTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Game;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SplunkerViz");
	}
}
