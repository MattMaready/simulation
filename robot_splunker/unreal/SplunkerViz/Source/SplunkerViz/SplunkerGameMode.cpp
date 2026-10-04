#include "SplunkerGameMode.h"

#include "Engine/DirectionalLight.h"
#include "Engine/World.h"
#include "EngineUtils.h"
#include "LidarVisualizer.h"
#include "OccupancyMapActor.h"
#include "SplunkerCameraPawn.h"
#include "SplunkerHUD.h"
#include "SplunkerLightingRig.h"
#include "SplunkerRobot.h"
#include "SplunkerViz.h"
#include "SplunkerVizSettings.h"
#include "SplunkerWorldBuilder.h"

ASplunkerGameMode::ASplunkerGameMode()
{
	DefaultPawnClass = ASplunkerCameraPawn::StaticClass();
	HUDClass = ASplunkerHUD::StaticClass();
}

template <class T>
T* ASplunkerGameMode::EnsureActor()
{
	UWorld* World = GetWorld();
	for (TActorIterator<T> It(World); It; ++It)
	{
		return *It;   // the level already has one (e.g. placed and customised by hand)
	}
	FActorSpawnParameters Params;
	Params.SpawnCollisionHandlingOverride = ESpawnActorCollisionHandlingMethod::AlwaysSpawn;
	return World->SpawnActor<T>(T::StaticClass(), FTransform::Identity, Params);
}

void ASplunkerGameMode::StartPlay()
{
	const USplunkerVizSettings* S = USplunkerVizSettings::Get();
	if (S->bAutoSpawnActors)
	{
		// Robot first, so the world builder can move it to the spawn pose when it builds.
		EnsureActor<ASplunkerRobot>();
		EnsureActor<ASplunkerWorldBuilder>();
		EnsureActor<ALidarVisualizer>();
		EnsureActor<AOccupancyMapActor>();
	}
	if (S->bAutoSpawnLighting)
	{
		bool bHasSun = false;
		for (TActorIterator<ADirectionalLight> It(GetWorld()); It; ++It) { bHasSun = true; break; }
		if (!bHasSun)
		{
			EnsureActor<ASplunkerLightingRig>();
		}
	}
	UE_LOG(LogSplunker, Log, TEXT("SplunkerViz ready; connecting to %s"), *S->BridgeUrl);
	Super::StartPlay();   // BeginPlay on all actors happens here
}
