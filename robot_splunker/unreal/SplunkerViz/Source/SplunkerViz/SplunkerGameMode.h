// Game mode that makes an EMPTY level a complete twin: on StartPlay it spawns any
// missing world builder, robot, lidar visualizer, map actor and lighting rig, and
// uses the spectator camera pawn + HUD. Set as GlobalDefaultGameMode in DefaultEngine.ini.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/GameModeBase.h"
#include "SplunkerGameMode.generated.h"

UCLASS()
class SPLUNKERVIZ_API ASplunkerGameMode : public AGameModeBase
{
	GENERATED_BODY()

public:
	ASplunkerGameMode();

	virtual void StartPlay() override;

private:
	template <class T>
	T* EnsureActor();
};
