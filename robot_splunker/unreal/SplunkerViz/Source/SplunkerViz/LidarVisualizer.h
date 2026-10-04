// Draws the most recent lidar scans as small spheres where the beams hit the walls.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "LidarVisualizer.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInterface;

UCLASS()
class SPLUNKERVIZ_API ALidarVisualizer : public AActor
{
	GENERATED_BODY()

public:
	ALidarVisualizer();

	virtual void Tick(float DeltaSeconds) override;

	void SetPointsVisible(bool bVisible);
	bool ArePointsVisible() const { return bPointsVisible; }

protected:
	virtual void BeginPlay() override;

private:
	UPROPERTY(VisibleAnywhere, Category = "Lidar")
	TObjectPtr<UInstancedStaticMeshComponent> Points;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInterface> BaseMaterial;

	TArray<TArray<FVector>> History;   // ring of recent scans (oldest first)
	uint64 LastSeq = 0;
	bool bPointsVisible = true;
};
