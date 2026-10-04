// Canvas HUD: bridge connection, explorer state, sim time, camera mode, key help
// and a north-up minimap of the SLAM map with the robot's position.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/HUD.h"
#include "SplunkerHUD.generated.h"

UCLASS()
class SPLUNKERVIZ_API ASplunkerHUD : public AHUD
{
	GENERATED_BODY()

public:
	virtual void DrawHUD() override;

	/** Longest side of the minimap in screen pixels. */
	UPROPERTY(EditAnywhere, Category = "HUD")
	float MinimapSize = 280.f;

private:
	void DrawMinimap();
};
