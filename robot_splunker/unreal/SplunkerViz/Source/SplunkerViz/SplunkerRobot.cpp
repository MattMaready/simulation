#include "SplunkerRobot.h"

#include "Components/SpotLightComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "SplunkerBridgeSubsystem.h"
#include "SplunkerVizSettings.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	// Engine basic shapes are 100 cm (cube edge, cylinder/sphere diameter and height).
	constexpr float ShapeSize = 100.f;
}

ASplunkerRobot::ASplunkerRobot()
{
	PrimaryActorTick.bCanEverTick = true;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> CubeMesh(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> CylinderMesh(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> SphereMesh(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> ShapeMaterial(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	BaseMaterial = ShapeMaterial.Object;

	// Actor origin = base_footprint (ground point under the wheel axle centre).
	BaseFootprint = CreateDefaultSubobject<USceneComponent>(TEXT("BaseFootprint"));
	RootComponent = BaseFootprint;

	Chassis = MakeMesh(TEXT("Chassis"), CubeMesh.Object, BaseFootprint);

	// Wheel hubs rotate (pitch) with the joint angle; the cylinder inside is rolled 90°
	// so its axis lies along Y, like the URDF wheel axis.
	LeftHub = CreateDefaultSubobject<USceneComponent>(TEXT("LeftHub"));
	LeftHub->SetupAttachment(BaseFootprint);
	LeftWheel = MakeMesh(TEXT("LeftWheel"), CylinderMesh.Object, LeftHub);
	RightHub = CreateDefaultSubobject<USceneComponent>(TEXT("RightHub"));
	RightHub->SetupAttachment(BaseFootprint);
	RightWheel = MakeMesh(TEXT("RightWheel"), CylinderMesh.Object, RightHub);

	Caster = MakeMesh(TEXT("Caster"), SphereMesh.Object, BaseFootprint);
	Lidar = MakeMesh(TEXT("Lidar"), CylinderMesh.Object, BaseFootprint);

	Headlight = CreateDefaultSubobject<USpotLightComponent>(TEXT("Headlight"));
	Headlight->SetupAttachment(BaseFootprint);
	Headlight->SetMobility(EComponentMobility::Movable);
	Headlight->SetIntensityUnits(ELightUnits::Lumens);
	Headlight->SetOuterConeAngle(38.f);
	Headlight->SetInnerConeAngle(18.f);
	Headlight->SetAttenuationRadius(2500.f);
	Headlight->SetLightColor(FLinearColor(1.f, 0.93f, 0.8f));

	Ghost = MakeMesh(TEXT("SlamGhost"), CubeMesh.Object, BaseFootprint);
	Ghost->SetUsingAbsoluteLocation(true);
	Ghost->SetUsingAbsoluteRotation(true);
	Ghost->SetVisibility(false);

	ApplyDimensions();
}

UStaticMeshComponent* ASplunkerRobot::MakeMesh(const TCHAR* Name, UStaticMesh* Mesh, USceneComponent* Parent)
{
	UStaticMeshComponent* C = CreateDefaultSubobject<UStaticMeshComponent>(Name);
	C->SetupAttachment(Parent);
	C->SetStaticMesh(Mesh);
	C->SetMobility(EComponentMobility::Movable);
	C->SetCollisionEnabled(ECollisionEnabled::NoCollision);   // visual only
	C->SetGenerateOverlapEvents(false);
	return C;
}

void ASplunkerRobot::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);
	ApplyDimensions();   // so edits in the Details panel show immediately
}

void ASplunkerRobot::ApplyDimensions()
{
	// NOTE: ROS +y (left) is UE -Y, so the LEFT wheel sits at negative Y.
	Chassis->SetRelativeLocation(ChassisOffset);
	Chassis->SetRelativeScale3D(ChassisSize / ShapeSize);

	const float D = 2.f * WheelRadius / ShapeSize;
	LeftHub->SetRelativeLocation(FVector(0.f, -WheelSeparation / 2.f, WheelRadius));
	RightHub->SetRelativeLocation(FVector(0.f, WheelSeparation / 2.f, WheelRadius));
	for (UStaticMeshComponent* W : {LeftWheel.Get(), RightWheel.Get()})
	{
		W->SetRelativeRotation(FRotator(0.f, 0.f, 90.f));
		W->SetRelativeScale3D(FVector(D, D, WheelWidth / ShapeSize));
	}

	Caster->SetRelativeLocation(FVector(CasterX, 0.f, CasterRadius));
	Caster->SetRelativeScale3D(FVector(2.f * CasterRadius / ShapeSize));

	Lidar->SetRelativeLocation(LidarOffset);
	Lidar->SetRelativeScale3D(FVector(2.f * LidarRadius / ShapeSize, 2.f * LidarRadius / ShapeSize,
		LidarHeight / ShapeSize));

	Headlight->SetRelativeLocation(FVector(ChassisOffset.X + ChassisSize.X / 2.f + 1.f, 0.f, ChassisOffset.Z));
	Headlight->SetRelativeRotation(FRotator(-6.f, 0.f, 0.f));
	Headlight->SetIntensity(HeadlightLumens);

	Ghost->SetRelativeScale3D(FVector(ChassisSize.X, ChassisSize.Y, 1.f) / ShapeSize);
}

void ASplunkerRobot::Paint(UStaticMeshComponent* Mesh, const FLinearColor& Color)
{
	if (!BaseMaterial || !Mesh)
	{
		return;
	}
	UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseMaterial, this);
	MID->SetVectorParameterValue(TEXT("Color"), Color);   // BasicShapeMaterial's colour parameter
	Mesh->SetMaterial(0, MID);
}

void ASplunkerRobot::BeginPlay()
{
	Super::BeginPlay();
	Paint(Chassis, ChassisColor);
	Paint(LeftWheel, WheelColor);
	Paint(RightWheel, WheelColor);
	Paint(Caster, FLinearColor(0.6f, 0.6f, 0.6f));
	Paint(Lidar, LidarColor);
	Paint(Ghost, GhostColor);
	Ghost->SetCastShadow(false);
}

void ASplunkerRobot::PlaceAtSpawn(const FTransform& Spawn)
{
	if (!bHasPose)
	{
		SetActorTransform(Spawn);
	}
}

void ASplunkerRobot::SetGhostVisible(bool bVisible)
{
	bGhostVisible = bVisible;
	if (!bVisible)
	{
		Ghost->SetVisibility(false);
	}
}

void ASplunkerRobot::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const USplunkerBridgeSubsystem* Bridge = USplunkerBridgeSubsystem::Get(this);
	if (!Bridge)
	{
		return;
	}

	// ---- Pose: follow Gazebo ground truth, smoothed between 30 Hz updates ----
	const FSplunkerPoseState& P = Bridge->GetPose();
	if (P.bValid)
	{
		const float Speed = USplunkerVizSettings::Get()->PoseInterpSpeed;
		if (!bHasPose || FVector::Dist(GetActorLocation(), P.Location) > 100.f)
		{
			SetActorLocationAndRotation(P.Location, P.Rotation);   // first pose or teleport: snap
			bHasPose = true;
		}
		else
		{
			SetActorLocationAndRotation(
				FMath::VInterpTo(GetActorLocation(), P.Location, DeltaSeconds, Speed),
				FMath::RInterpTo(GetActorRotation(), P.Rotation, DeltaSeconds, Speed));
		}
	}

	// ---- Wheels: joint angle about +y (ROS) == negative pitch in UE ----
	const FSplunkerWheelState& W = Bridge->GetWheels();
	if (W.bValid && W.Seq != LastWheelSeq)
	{
		LastWheelSeq = W.Seq;
		LeftHub->SetRelativeRotation(FRotator(-FMath::RadiansToDegrees(W.LeftRad), 0.f, 0.f));
		RightHub->SetRelativeRotation(FRotator(-FMath::RadiansToDegrees(W.RightRad), 0.f, 0.f));
	}

	// ---- SLAM ghost: thin plate floating above where SLAM believes the robot is ----
	const FSplunkerPoseState& S = Bridge->GetSlamPose();
	if (bGhostVisible && S.bValid)
	{
		Ghost->SetVisibility(true);
		Ghost->SetWorldLocationAndRotation(S.Location + FVector(0.f, 0.f, 30.f) +
			S.Rotation.RotateVector(FVector(ChassisOffset.X, 0.f, 0.f)), S.Rotation);
	}
}
