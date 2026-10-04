// Builds the Unreal version of the Gazebo world from the layout JSON written by
// scripts/generate_world.py (same walls, same places, nicer materials).
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "SplunkerWorldBuilder.generated.h"

class UStaticMesh;
class UStaticMeshComponent;
class UMaterialInterface;
class FJsonObject;

UCLASS()
class SPLUNKERVIZ_API ASplunkerWorldBuilder : public AActor
{
	GENERATED_BODY()

public:
	ASplunkerWorldBuilder();

	virtual void Tick(float DeltaSeconds) override;

	/** Re-read the layout JSON and rebuild all walls/props (also a button in the Details panel). */
	UFUNCTION(CallInEditor, Category = "Splunker")
	void Rebuild();

	/** Spawn pose from the layout (valid after a successful build). */
	bool GetSpawnTransform(FTransform& Out) const;

	/** Overrides USplunkerVizSettings::LayoutFile (path relative to Content/). */
	UPROPERTY(EditAnywhere, Category = "Splunker")
	FString LayoutFileOverride;

protected:
	virtual void BeginPlay() override;

private:
	bool BuildFromFile(const FString& RelativePath);
	void ClearParts();
	UStaticMeshComponent* AddPart(const FString& Name, UStaticMesh* Mesh, const FVector& Loc,
		const FRotator& Rot, const FVector& SizeCm, FName MaterialTag);
	UMaterialInterface* ResolveMaterial(FName Tag);

	UPROPERTY(VisibleAnywhere, Category = "Splunker")
	TObjectPtr<USceneComponent> Root;

	UPROPERTY(Transient)
	TArray<TObjectPtr<UStaticMeshComponent>> Parts;

	UPROPERTY(Transient)
	TMap<FName, TObjectPtr<UMaterialInterface>> MaterialCache;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CubeMesh;

	UPROPERTY()
	TObjectPtr<UStaticMesh> CylinderMesh;

	UPROPERTY()
	TObjectPtr<UMaterialInterface> BaseMaterial;

	FString CurrentLayout;
	FTransform SpawnTransform;
	bool bHasSpawn = false;
	float WorldCheckTimer = 0.f;
};
