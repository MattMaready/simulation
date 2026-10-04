// Turns the SLAM occupancy grid into a texture: drawn as a minimap by the HUD and,
// if a material is configured, as a translucent "explored area" overlay on the floor.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "OccupancyMapActor.generated.h"

class UTexture2D;
class UStaticMeshComponent;
class UMaterialInstanceDynamic;
struct FSplunkerMapState;

UCLASS()
class SPLUNKERVIZ_API AOccupancyMapActor : public AActor
{
	GENERATED_BODY()

public:
	AOccupancyMapActor();

	virtual void Tick(float DeltaSeconds) override;

	/** North-up texture of the latest map (row 0 at the top = map y-max). May be null. */
	UTexture2D* GetTexture() const { return MapTexture; }

	void SetOverlayVisible(bool bVisible);
	bool IsOverlayVisible() const { return bOverlayVisible; }

	UPROPERTY(EditAnywhere, Category = "Map")
	FColor UnknownColor = FColor(30, 30, 30, 140);

	UPROPERTY(EditAnywhere, Category = "Map")
	FColor FreeColor = FColor(225, 225, 225, 200);

	UPROPERTY(EditAnywhere, Category = "Map")
	FColor OccupiedColor = FColor(255, 120, 0, 255);

	/** Height of the floor overlay above z = 0 (cm). */
	UPROPERTY(EditAnywhere, Category = "Map")
	float OverlayHeight = 1.5f;

protected:
	virtual void BeginPlay() override;

private:
	void UpdateTexture(const FSplunkerMapState& Map);
	void UpdateOverlay(const FSplunkerMapState& Map);

	UPROPERTY(Transient)
	TObjectPtr<UTexture2D> MapTexture;

	UPROPERTY(VisibleAnywhere, Category = "Map")
	TObjectPtr<UStaticMeshComponent> Overlay;

	UPROPERTY(Transient)
	TObjectPtr<UMaterialInstanceDynamic> OverlayMID;

	uint64 LastSeq = 0;
	bool bOverlayVisible = true;
};
