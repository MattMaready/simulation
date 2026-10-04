using UnrealBuildTool;

public class SplunkerVizEditorTarget : TargetRules
{
	public SplunkerVizEditorTarget(TargetInfo Target) : base(Target)
	{
		Type = TargetType.Editor;
		DefaultBuildSettings = BuildSettingsVersion.Latest;
		IncludeOrderVersion = EngineIncludeOrderVersion.Latest;
		ExtraModuleNames.Add("SplunkerViz");
	}
}
