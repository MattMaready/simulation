#include "SplunkerLightingRig.h"

#include "Components/DirectionalLightComponent.h"
#include "Components/ExponentialHeightFogComponent.h"
#include "Components/SkyAtmosphereComponent.h"
#include "Components/SkyLightComponent.h"

ASplunkerLightingRig::ASplunkerLightingRig()
{
	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	// Low evening sun: long shadows across the walls, dim enough for the headlight to matter.
	Sun = CreateDefaultSubobject<UDirectionalLightComponent>(TEXT("Sun"));
	Sun->SetupAttachment(Root);
	Sun->SetMobility(EComponentMobility::Movable);
	Sun->SetRelativeRotation(FRotator(-18.f, 35.f, 0.f));
	Sun->SetIntensity(3.f);                    // lux
	Sun->SetLightColor(FLinearColor(1.f, 0.82f, 0.62f));
	Sun->SetAtmosphereSunLight(true);

	Sky = CreateDefaultSubobject<USkyAtmosphereComponent>(TEXT("SkyAtmosphere"));
	Sky->SetupAttachment(Root);

	// Real-time capture so the sky light follows the atmosphere (required for Lumen GI).
	SkyLight = CreateDefaultSubobject<USkyLightComponent>(TEXT("SkyLight"));
	SkyLight->SetupAttachment(Root);
	SkyLight->SetMobility(EComponentMobility::Movable);
	SkyLight->bRealTimeCapture = true;
	SkyLight->SetIntensity(0.6f);

	Fog = CreateDefaultSubobject<UExponentialHeightFogComponent>(TEXT("HeightFog"));
	Fog->SetupAttachment(Root);
	Fog->SetFogDensity(0.03f);
	Fog->SetVolumetricFog(true);
}
