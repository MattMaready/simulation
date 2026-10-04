#include "SplunkerCameraPawn.h"

#include "Camera/CameraComponent.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/KismetSystemLibrary.h"
#include "LidarVisualizer.h"
#include "OccupancyMapActor.h"
#include "SplunkerRobot.h"

ASplunkerCameraPawn::ASplunkerCameraPawn()
{
	PrimaryActorTick.bCanEverTick = true;
	Camera = CreateDefaultSubobject<UCameraComponent>(TEXT("Camera"));
	RootComponent = Camera;
	Camera->SetFieldOfView(75.f);
}

const TCHAR* ASplunkerCameraPawn::ModeName(ESplunkerCamMode InMode)
{
	switch (InMode)
	{
	case ESplunkerCamMode::Chase:   return TEXT("chase");
	case ESplunkerCamMode::Orbit:   return TEXT("orbit");
	case ESplunkerCamMode::TopDown: return TEXT("top-down");
	case ESplunkerCamMode::FreeFly: return TEXT("free-fly");
	}
	return TEXT("?");
}

void ASplunkerCameraPawn::BeginPlay()
{
	Super::BeginPlay();
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		PC->SetInputMode(FInputModeGameOnly());
		PC->bShowMouseCursor = false;
	}
}

ASplunkerRobot* ASplunkerCameraPawn::FindRobot()
{
	if (!Robot.IsValid())
	{
		for (TActorIterator<ASplunkerRobot> It(GetWorld()); It; ++It)
		{
			Robot = *It;
			break;
		}
	}
	return Robot.Get();
}

void ASplunkerCameraPawn::HandleKeys(APlayerController* PC)
{
	// Camera modes
	if (PC->WasInputKeyJustPressed(EKeys::One))   { Mode = ESplunkerCamMode::Chase; }
	if (PC->WasInputKeyJustPressed(EKeys::Two))   { Mode = ESplunkerCamMode::Orbit; }
	if (PC->WasInputKeyJustPressed(EKeys::Three)) { Mode = ESplunkerCamMode::TopDown; }
	if (PC->WasInputKeyJustPressed(EKeys::Four))
	{
		Mode = ESplunkerCamMode::FreeFly;
		FlyRotation = GetActorRotation();   // continue from the current view
	}

	// Zoom
	const float Zoom = PC->WasInputKeyJustPressed(EKeys::MouseScrollUp) ? 0.85f :
		(PC->WasInputKeyJustPressed(EKeys::MouseScrollDown) ? 1.15f : 1.f);
	if (Zoom != 1.f)
	{
		ChaseDistance = FMath::Clamp(ChaseDistance * Zoom, 60.f, 1500.f);
		ChaseHeight = FMath::Clamp(ChaseHeight * Zoom, 30.f, 800.f);
		OrbitDistance = FMath::Clamp(OrbitDistance * Zoom, 80.f, 3000.f);
		TopDownHeight = FMath::Clamp(TopDownHeight * Zoom, 300.f, 6000.f);
	}

	// Visualisation toggles
	if (PC->WasInputKeyJustPressed(EKeys::H))
	{
		for (TActorIterator<AOccupancyMapActor> It(GetWorld()); It; ++It) { It->SetOverlayVisible(!It->IsOverlayVisible()); }
	}
	if (PC->WasInputKeyJustPressed(EKeys::G))
	{
		if (ASplunkerRobot* R = FindRobot()) { R->SetGhostVisible(!R->IsGhostVisible()); }
	}
	if (PC->WasInputKeyJustPressed(EKeys::L))
	{
		for (TActorIterator<ALidarVisualizer> It(GetWorld()); It; ++It) { It->SetPointsVisible(!It->ArePointsVisible()); }
	}
	if (PC->WasInputKeyJustPressed(EKeys::F1)) { bShowHelp = !bShowHelp; }
	if (PC->WasInputKeyJustPressed(EKeys::Escape))
	{
		UKismetSystemLibrary::QuitGame(this, PC, EQuitPreference::Quit, false);
	}
}

void ASplunkerCameraPawn::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	APlayerController* PC = Cast<APlayerController>(GetController());
	float MouseX = 0.f, MouseY = 0.f;
	if (PC)
	{
		HandleKeys(PC);
		PC->GetInputMouseDelta(MouseX, MouseY);
	}

	const ASplunkerRobot* R = FindRobot();
	const FVector Target = R ? R->GetActorLocation() + FVector(0.f, 0.f, 15.f) : FVector(0.f, 0.f, 15.f);
	const float RobotYaw = R ? R->GetActorRotation().Yaw : 0.f;

	switch (Mode)
	{
	case ESplunkerCamMode::Chase:
	{
		// Behind and above the robot, smoothly following its heading.
		const FVector Desired = Target + FRotator(0.f, RobotYaw, 0.f).RotateVector(FVector(-ChaseDistance, 0.f, ChaseHeight));
		const FVector Loc = FMath::VInterpTo(GetActorLocation(), Desired, DeltaSeconds, ChaseLagSpeed);
		SetActorLocationAndRotation(Loc, (Target - Loc).Rotation());
		break;
	}
	case ESplunkerCamMode::Orbit:
	{
		OrbitYaw += MouseX * MouseSensitivity * 10.f;
		OrbitPitch = FMath::Clamp(OrbitPitch + MouseY * MouseSensitivity * 10.f, -85.f, -5.f);
		const FVector Loc = Target - FRotator(OrbitPitch, OrbitYaw, 0.f).Vector() * OrbitDistance;
		SetActorLocationAndRotation(Loc, (Target - Loc).Rotation());
		break;
	}
	case ESplunkerCamMode::TopDown:
	{
		// Looking straight down with world +X up the screen (= ROS x up, ROS y to the left).
		SetActorLocationAndRotation(FVector(Target.X, Target.Y, Target.Z + TopDownHeight), FRotator(-89.9f, 0.f, 0.f));
		break;
	}
	case ESplunkerCamMode::FreeFly:
	{
		FlyRotation.Yaw += MouseX * MouseSensitivity * 10.f;
		FlyRotation.Pitch = FMath::Clamp(FlyRotation.Pitch + MouseY * MouseSensitivity * 10.f, -89.f, 89.f);
		FVector Move = FVector::ZeroVector;
		if (PC)
		{
			const FRotationMatrix M(FlyRotation);
			if (PC->IsInputKeyDown(EKeys::W)) { Move += M.GetUnitAxis(EAxis::X); }
			if (PC->IsInputKeyDown(EKeys::S)) { Move -= M.GetUnitAxis(EAxis::X); }
			if (PC->IsInputKeyDown(EKeys::D)) { Move += M.GetUnitAxis(EAxis::Y); }
			if (PC->IsInputKeyDown(EKeys::A)) { Move -= M.GetUnitAxis(EAxis::Y); }
			if (PC->IsInputKeyDown(EKeys::E)) { Move += FVector::UpVector; }
			if (PC->IsInputKeyDown(EKeys::Q)) { Move -= FVector::UpVector; }
			if (PC->IsInputKeyDown(EKeys::LeftShift)) { Move *= 3.f; }
		}
		SetActorLocationAndRotation(GetActorLocation() + Move * FlySpeed * DeltaSeconds, FlyRotation);
		break;
	}
	}
}
