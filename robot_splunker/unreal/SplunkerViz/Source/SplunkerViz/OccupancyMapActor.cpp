#include "OccupancyMapActor.h"

#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/Texture2D.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "SplunkerBridgeSubsystem.h"
#include "SplunkerViz.h"
#include "SplunkerVizSettings.h"
#include "UObject/ConstructorHelpers.h"

AOccupancyMapActor::AOccupancyMapActor()
{
	PrimaryActorTick.bCanEverTick = true;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> Plane(TEXT("/Engine/BasicShapes/Plane.Plane"));
	Overlay = CreateDefaultSubobject<UStaticMeshComponent>(TEXT("Overlay"));
	RootComponent = Overlay;
	Overlay->SetStaticMesh(Plane.Object);
	Overlay->SetMobility(EComponentMobility::Movable);
	Overlay->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	Overlay->SetCastShadow(false);
	Overlay->SetVisibility(false);   // shown once a map + overlay material exist
}

void AOccupancyMapActor::BeginPlay()
{
	Super::BeginPlay();
	const USplunkerVizSettings* S = USplunkerVizSettings::Get();
	if (UMaterialInterface* Mat = S->MapOverlayMaterial.LoadSynchronous())
	{
		OverlayMID = UMaterialInstanceDynamic::Create(Mat, this);
		Overlay->SetMaterial(0, OverlayMID);
	}
	else
	{
		UE_LOG(LogSplunker, Log, TEXT("No MapOverlayMaterial set: map shown on the HUD minimap only."));
	}
}

void AOccupancyMapActor::SetOverlayVisible(bool bVisible)
{
	bOverlayVisible = bVisible;
	Overlay->SetVisibility(bVisible && OverlayMID && MapTexture);
}

void AOccupancyMapActor::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	const USplunkerBridgeSubsystem* Bridge = USplunkerBridgeSubsystem::Get(this);
	if (!Bridge)
	{
		return;
	}
	const FSplunkerMapState& Map = Bridge->GetMap();
	if (Map.Seq == LastSeq || Map.Width <= 0 || Map.Height <= 0)
	{
		return;
	}
	LastSeq = Map.Seq;
	UpdateTexture(Map);
	UpdateOverlay(Map);
}

void AOccupancyMapActor::UpdateTexture(const FSplunkerMapState& Map)
{
	const int32 W = Map.Width, H = Map.Height;

	// (Re)create the texture when the map grows (SLAM expands the grid as it explores).
	if (!MapTexture || MapTexture->GetSizeX() != W || MapTexture->GetSizeY() != H)
	{
		MapTexture = UTexture2D::CreateTransient(W, H, PF_B8G8R8A8);
		MapTexture->Filter = TF_Nearest;   // crisp cells
		MapTexture->SRGB = true;
		MapTexture->NeverStream = true;
		MapTexture->UpdateResource();
	}

	// Cells: 255 = unknown (-1 as uint8), 0..100 = occupancy. Flip rows so the image is
	// north-up (map row 0 = y-min goes to the BOTTOM of the texture).
	TArray<FColor> Pixels;
	Pixels.SetNumUninitialized(W * H);
	for (int32 Row = 0; Row < H; ++Row)
	{
		const int32 DstRow = H - 1 - Row;
		for (int32 Col = 0; Col < W; ++Col)
		{
			const uint8 V = Map.Cells[Row * W + Col];
			Pixels[DstRow * W + Col] = (V == 255) ? UnknownColor : (V >= 50 ? OccupiedColor : FreeColor);
		}
	}

	FTexture2DMipMap& Mip = MapTexture->GetPlatformData()->Mips[0];
	void* Data = Mip.BulkData.Lock(LOCK_READ_WRITE);
	FMemory::Memcpy(Data, Pixels.GetData(), Pixels.Num() * sizeof(FColor));
	Mip.BulkData.Unlock();
	MapTexture->UpdateResource();
}

void AOccupancyMapActor::UpdateOverlay(const FSplunkerMapState& Map)
{
	if (!OverlayMID)
	{
		return;
	}
	OverlayMID->SetTextureParameterValue(USplunkerVizSettings::Get()->MapOverlayTextureParameter, MapTexture);

	// Map +x = rotated UE +X, map +y = rotated UE -Y (handedness flip), see SplunkerTypes.h.
	const float SizeX = Map.Width * Map.ResolutionCm;
	const float SizeY = Map.Height * Map.ResolutionCm;
	const FRotator Rot(0.f, Map.YawDeg, 0.f);
	const FVector Center = Map.Origin + Rot.RotateVector(FVector(SizeX / 2.f, -SizeY / 2.f, 0.f));
	// Engine plane is 100 x 100 cm. If the texture appears mirrored with your material,
	// flip its V coordinate (OneMinus on TexCoord.y) in the material.
	SetActorLocationAndRotation(FVector(Center.X, Center.Y, OverlayHeight), Rot);
	SetActorScale3D(FVector(SizeX / 100.f, SizeY / 100.f, 1.f));
	Overlay->SetVisibility(bOverlayVisible);
}
