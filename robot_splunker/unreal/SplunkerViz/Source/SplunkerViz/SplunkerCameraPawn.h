// Spectator camera for the twin. Keys (polled each frame, no input mappings needed):
//   1 chase   2 orbit (mouse)   3 top-down   4 free-fly (WASD/QE + mouse, Shift = fast)
//   mouse wheel = zoom (chase/orbit/top-down)
//   H map overlay   G SLAM ghost   L lidar points   F1 help   Esc quit (-game)
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Pawn.h"
#include "SplunkerCameraPawn.generated.h"

class UCameraComponent;
class ASplunkerRobot;
class APlayerController;

UENUM()
enum class ESplunkerCamMode : uint8
{
	Chase,
	Orbit,
	TopDown,
	FreeFly
};

UCLASS()
class SPLUNKERVIZ_API ASplunkerCameraPawn : public APawn
{
	GENERATED_BODY()

public:
	ASplunkerCameraPawn();

	virtual void Tick(float DeltaSeconds) override;

	ESplunkerCamMode GetMode() const { return Mode; }
	static const TCHAR* ModeName(ESplunkerCamMode InMode);
	bool IsHelpVisible() const { return bShowHelp; }

	UPROPERTY(EditAnywhere, Category = "Camera")
	float ChaseDistance = 160.f;

	UPROPERTY(EditAnywhere, Category = "Camera")
	float ChaseHeight = 80.f;

	UPROPERTY(EditAnywhere, Category = "Camera")
	float OrbitDistance = 350.f;

	UPROPERTY(EditAnywhere, Category = "Camera")
	float TopDownHeight = 1800.f;

	UPROPERTY(EditAnywhere, Category = "Camera")
	float FlySpeed = 500.f;

	UPROPERTY(EditAnywhere, Category = "Camera")
	float MouseSensitivity = 0.25f;

	/** Camera smoothing in chase mode (higher = stiffer). */
	UPROPERTY(EditAnywhere, Category = "Camera")
	float ChaseLagSpeed = 6.f;

protected:
	virtual void BeginPlay() override;

private:
	void HandleKeys(APlayerController* PC);
	ASplunkerRobot* FindRobot();

	UPROPERTY(VisibleAnywhere, Category = "Camera")
	TObjectPtr<UCameraComponent> Camera;

	TWeakObjectPtr<ASplunkerRobot> Robot;
	ESplunkerCamMode Mode = ESplunkerCamMode::Chase;
	float OrbitYaw = -135.f;
	float OrbitPitch = -25.f;
	FRotator FlyRotation = FRotator(-20.f, 0.f, 0.f);
	bool bShowHelp = true;
};
