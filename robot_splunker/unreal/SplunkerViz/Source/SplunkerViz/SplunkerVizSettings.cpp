#include "SplunkerVizSettings.h"

USplunkerVizSettings::USplunkerVizSettings()
{
	// Same colours as the Gazebo world (scripts/generate_world.py MATERIAL_COLORS).
	FallbackColors.Add(TEXT("concrete"), FLinearColor(0.60f, 0.60f, 0.58f));
	FallbackColors.Add(TEXT("rock"),     FLinearColor(0.45f, 0.38f, 0.30f));
	FallbackColors.Add(TEXT("brick"),    FLinearColor(0.60f, 0.26f, 0.20f));
	FallbackColors.Add(TEXT("metal"),    FLinearColor(0.50f, 0.55f, 0.60f));
	FallbackColors.Add(TEXT("wood"),     FLinearColor(0.55f, 0.40f, 0.24f));
	FallbackColors.Add(TEXT("floor"),    FLinearColor(0.30f, 0.30f, 0.30f));
}
