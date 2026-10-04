#include "LidarVisualizer.h"

#include "Components/InstancedStaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "SplunkerBridgeSubsystem.h"
#include "SplunkerVizSettings.h"
#include "UObject/ConstructorHelpers.h"

ALidarVisualizer::ALidarVisualizer()
{
	PrimaryActorTick.bCanEverTick = true;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> Sphere(TEXT("/Engine/BasicShapes/Sphere.Sphere"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Mat(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	BaseMaterial = Mat.Object;

	Points = CreateDefaultSubobject<UInstancedStaticMeshComponent>(TEXT("Points"));
	RootComponent = Points;
	Points->SetStaticMesh(Sphere.Object);
	Points->SetMobility(EComponentMobility::Movable);
	Points->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Points->SetCastShadow(false);
	Points->SetGenerateOverlapEvents(false);
}

void ALidarVisualizer::BeginPlay()
{
	Super::BeginPlay();
	if (BaseMaterial)
	{
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseMaterial, this);
		MID->SetVectorParameterValue(TEXT("Color"), USplunkerVizSettings::Get()->LidarColor);
		Points->SetMaterial(0, MID);
	}
}

void ALidarVisualizer::SetPointsVisible(bool bVisible)
{
	bPointsVisible = bVisible;
	Points->SetVisibility(bVisible);
}

void ALidarVisualizer::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const USplunkerBridgeSubsystem* Bridge = USplunkerBridgeSubsystem::Get(this);
	if (!Bridge)
	{
		return;
	}
	const FSplunkerScanState& Scan = Bridge->GetScan();
	if (Scan.Seq == LastSeq)
	{
		return;   // no new scan since last frame
	}
	LastSeq = Scan.Seq;

	// Keep the last N scans (a short "trail" makes the sweep easier to read).
	const USplunkerVizSettings* S = USplunkerVizSettings::Get();
	History.Add(Scan.Hits);
	while (History.Num() > FMath::Max(1, S->LidarScansToKeep))
	{
		History.RemoveAt(0);
	}

	// Rebuild all instances (a few hundred points: cheap).
	const FVector Scale(S->LidarPointSizeCm / 100.f);   // sphere mesh is 100 cm
	TArray<FTransform> Transforms;
	for (const TArray<FVector>& Hits : History)
	{
		for (const FVector& P : Hits)
		{
			Transforms.Emplace(FRotator::ZeroRotator, P, Scale);
		}
	}
	Points->ClearInstances();
	Points->AddInstances(Transforms, /*bShouldReturnIndices=*/false, /*bWorldSpace=*/true);
}
