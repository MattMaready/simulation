// Default "dusk in a cave" lighting so an empty level looks good with Lumen:
// low sun + sky atmosphere, real-time sky light, height fog. The robot's own
// headlight (ASplunkerRobot) does the rest. Spawned by ASplunkerGameMode only
// when the level has no directional light of its own.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SplunkerLightingRig.generated.h"

class UDirectionalLightComponent;
class USkyAtmosphereComponent;
class USkyLightComponent;
class UExponentialHeightFogComponent;

UCLASS()
class SPLUNKERVIZ_API ASplunkerLightingRig : public AActor
{
	GENERATED_BODY()

public:
	ASplunkerLightingRig();

private:
	UPROPERTY(VisibleAnywhere, Category = "Lighting")
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(VisibleAnywhere, Category = "Lighting")
	TObjectPtr<UDirectionalLightComponent> Sun;

	UPROPERTY(VisibleAnywhere, Category = "Lighting")
	TObjectPtr<USkyAtmosphereComponent> Sky;

	UPROPERTY(VisibleAnywhere, Category = "Lighting")
	TObjectPtr<USkyLightComponent> SkyLight;

	UPROPERTY(VisibleAnywhere, Category = "Lighting")
	TObjectPtr<UExponentialHeightFogComponent> Fog;
};
