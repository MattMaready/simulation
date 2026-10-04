// Visual twin of robot_splunker. Built from engine primitive shapes sized to match
// robot_splunker_description/urdf/properties.xacro (converted to cm). Follows the
// Gazebo ground-truth pose from the bridge and spins its wheels from /joint_states.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SplunkerRobot.generated.h"

class UStaticMeshComponent;
class USpotLightComponent;
class UMaterialInterface;
class UStaticMesh;

UCLASS()
class SPLUNKERVIZ_API ASplunkerRobot : public AActor
{
	GENERATED_BODY()

public:
	ASplunkerRobot();

	virtual void Tick(float DeltaSeconds) override;

	/** Show/hide the SLAM-estimate "ghost" (blue plate where SLAM thinks the robot is). */
	void SetGhostVisible(bool bVisible);
	bool IsGhostVisible() const { return bGhostVisible; }

	/** Place the robot at the world spawn pose until the first bridge pose arrives. */
	void PlaceAtSpawn(const FTransform& Spawn);

	// ---- Dimensions (cm), defaults = properties.xacro * 100. Origin = base_footprint. ----
	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	FVector ChassisSize = FVector(40.f, 30.f, 10.f);

	/** Chassis centre relative to base_footprint (x = +10 ahead of the axle, z = 5 + 3). */
	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	FVector ChassisOffset = FVector(10.f, 0.f, 8.f);

	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float WheelRadius = 5.f;

	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float WheelWidth = 4.f;

	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float WheelSeparation = 36.f;

	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float CasterRadius = 2.5f;

	/** Caster x relative to base_footprint (25 cm ahead of the axle). */
	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float CasterX = 25.f;

	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float LidarRadius = 4.f;

	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	float LidarHeight = 5.f;

	/** Lidar centre relative to base_footprint. */
	UPROPERTY(EditAnywhere, Category = "Robot|Dimensions")
	FVector LidarOffset = FVector(12.f, 0.f, 15.5f);

	// ---- Look ----
	UPROPERTY(EditAnywhere, Category = "Robot|Look")
	FLinearColor ChassisColor = FLinearColor(1.f, 0.45f, 0.05f);

	UPROPERTY(EditAnywhere, Category = "Robot|Look")
	FLinearColor WheelColor = FLinearColor(0.03f, 0.03f, 0.03f);

	UPROPERTY(EditAnywhere, Category = "Robot|Look")
	FLinearColor LidarColor = FLinearColor(0.05f, 0.15f, 0.45f);

	UPROPERTY(EditAnywhere, Category = "Robot|Look")
	FLinearColor GhostColor = FLinearColor(0.1f, 0.4f, 1.f);

	/** Headlight brightness in lumens (the "splunker's" lamp). */
	UPROPERTY(EditAnywhere, Category = "Robot|Look")
	float HeadlightLumens = 2500.f;

protected:
	virtual void BeginPlay() override;
	virtual void OnConstruction(const FTransform& Transform) override;

private:
	void ApplyDimensions();
	void Paint(UStaticMeshComponent* Mesh, const FLinearColor& Color);
	UStaticMeshComponent* MakeMesh(const TCHAR* Name, UStaticMesh* Mesh, USceneComponent* Parent);

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<USceneComponent> BaseFootprint;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<UStaticMeshComponent> Chassis;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<USceneComponent> LeftHub;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<UStaticMeshComponent> LeftWheel;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<USceneComponent> RightHub;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<UStaticMeshComponent> RightWheel;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<UStaticMeshComponent> Caster;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<UStaticMeshComponent> Lidar;

	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<USpotLightComponent> Headlight;

	/** SLAM estimate marker; uses absolute transform so it moves independently. */
	UPROPERTY(VisibleAnywhere, Category = "Robot")
	TObjectPtr<UStaticMeshComponent> Ghost;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> BaseMaterial;

	uint64 LastWheelSeq = 0;
	bool bHasPose = false;
	bool bGhostVisible = true;
};
