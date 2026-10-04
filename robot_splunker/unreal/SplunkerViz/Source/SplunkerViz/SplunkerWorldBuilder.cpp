#include "SplunkerWorldBuilder.h"

#include "Components/StaticMeshComponent.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/StaticMesh.h"
#include "EngineUtils.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SplunkerBridgeSubsystem.h"
#include "SplunkerRobot.h"
#include "SplunkerViz.h"
#include "SplunkerVizSettings.h"
#include "UObject/ConstructorHelpers.h"

namespace
{
	constexpr float ShapeSize = 100.f;   // engine basic shapes are 100 cm

	bool ReadVec3(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, FVector& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj.IsValid() || !Obj->TryGetArrayField(Field, Arr) || !Arr || Arr->Num() < 3)
		{
			return false;
		}
		Out = FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		return true;
	}
}

ASplunkerWorldBuilder::ASplunkerWorldBuilder()
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.TickInterval = 0.5f;   // only watches for a world change

	Root = CreateDefaultSubobject<USceneComponent>(TEXT("Root"));
	RootComponent = Root;

	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cube(TEXT("/Engine/BasicShapes/Cube.Cube"));
	static ConstructorHelpers::FObjectFinder<UStaticMesh> Cylinder(TEXT("/Engine/BasicShapes/Cylinder.Cylinder"));
	static ConstructorHelpers::FObjectFinder<UMaterialInterface> Mat(
		TEXT("/Engine/BasicShapes/BasicShapeMaterial.BasicShapeMaterial"));
	CubeMesh = Cube.Object;
	CylinderMesh = Cylinder.Object;
	BaseMaterial = Mat.Object;
}

void ASplunkerWorldBuilder::BeginPlay()
{
	Super::BeginPlay();
	Rebuild();
}

void ASplunkerWorldBuilder::Rebuild()
{
	const FString Path = LayoutFileOverride.IsEmpty() ? USplunkerVizSettings::Get()->LayoutFile : LayoutFileOverride;
	BuildFromFile(Path);
}

void ASplunkerWorldBuilder::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);
	// If ROS runs a different world than the one we built, switch to "<world>_layout.json".
	const USplunkerBridgeSubsystem* Bridge = USplunkerBridgeSubsystem::Get(this);
	if (!Bridge || Bridge->GetWorldName().IsEmpty() || !LayoutFileOverride.IsEmpty())
	{
		return;
	}
	const FString Wanted = FString::Printf(TEXT("Splunker/Data/%s_layout.json"), *Bridge->GetWorldName());
	if (Wanted != CurrentLayout && FPaths::FileExists(FPaths::ProjectContentDir() / Wanted))
	{
		UE_LOG(LogSplunker, Log, TEXT("ROS world is '%s'; switching layout"), *Bridge->GetWorldName());
		BuildFromFile(Wanted);
	}
}

bool ASplunkerWorldBuilder::GetSpawnTransform(FTransform& Out) const
{
	Out = SpawnTransform;
	return bHasSpawn;
}

void ASplunkerWorldBuilder::ClearParts()
{
	for (UStaticMeshComponent* C : Parts)
	{
		if (C)
		{
			C->DestroyComponent();
		}
	}
	Parts.Reset();
}

UMaterialInterface* ASplunkerWorldBuilder::ResolveMaterial(FName Tag)
{
	if (TObjectPtr<UMaterialInterface>* Cached = MaterialCache.Find(Tag))
	{
		return *Cached;
	}
	const USplunkerVizSettings* S = USplunkerVizSettings::Get();
	UMaterialInterface* Result = nullptr;

	// 1. A real material assigned in Project Settings (e.g. a Megascans surface).
	if (const TSoftObjectPtr<UMaterialInterface>* Override = S->MaterialOverrides.Find(Tag))
	{
		Result = Override->LoadSynchronous();
	}
	// 2. Otherwise a plain colour on the engine's basic shape material.
	if (!Result && BaseMaterial)
	{
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseMaterial, this);
		const FLinearColor* Color = S->FallbackColors.Find(Tag);
		MID->SetVectorParameterValue(TEXT("Color"), Color ? *Color : FLinearColor(0.5f, 0.5f, 0.5f));
		Result = MID;
	}
	MaterialCache.Add(Tag, Result);
	return Result;
}

UStaticMeshComponent* ASplunkerWorldBuilder::AddPart(const FString& Name, UStaticMesh* Mesh, const FVector& Loc,
	const FRotator& Rot, const FVector& SizeCm, FName MaterialTag)
{
	// Unique name: a rebuild creates new parts while the destroyed ones may still exist.
	const FName UniqueName = MakeUniqueObjectName(this, UStaticMeshComponent::StaticClass(), FName(*Name));
	UStaticMeshComponent* C = NewObject<UStaticMeshComponent>(this, UniqueName);
	C->SetMobility(EComponentMobility::Movable);
	C->SetStaticMesh(Mesh);
	C->SetupAttachment(Root);
	C->RegisterComponent();
	C->SetRelativeLocationAndRotation(Loc, Rot);
	C->SetRelativeScale3D(SizeCm / ShapeSize);
	C->SetMaterial(0, ResolveMaterial(MaterialTag));
	C->SetCollisionEnabled(ECollisionEnabled::QueryOnly);   // lets the free-fly camera trace, no physics
	Parts.Add(C);
	return C;
}

bool ASplunkerWorldBuilder::BuildFromFile(const FString& RelativePath)
{
	const FString FullPath = FPaths::ProjectContentDir() / RelativePath;
	FString Text;
	if (!FFileHelper::LoadFileToString(Text, *FullPath))
	{
		UE_LOG(LogSplunker, Error, TEXT("Layout not found: %s (run ./scripts/bld.sh --worlds)"), *FullPath);
		return false;
	}
	TSharedPtr<FJsonObject> Doc;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
	if (!FJsonSerializer::Deserialize(Reader, Doc) || !Doc.IsValid())
	{
		UE_LOG(LogSplunker, Error, TEXT("Layout is not valid JSON: %s"), *FullPath);
		return false;
	}

	ClearParts();
	CurrentLayout = RelativePath;

	// ---- Floor ----
	const TSharedPtr<FJsonObject>* Floor = nullptr;
	if (Doc->TryGetObjectField(TEXT("floor"), Floor) && Floor)
	{
		FVector Loc(0.f, 0.f, -1.f), Size(1600.f, 1600.f, 2.f);
		ReadVec3(*Floor, TEXT("loc"), Loc);
		ReadVec3(*Floor, TEXT("size"), Size);
		FString Mat = TEXT("floor");
		(*Floor)->TryGetStringField(TEXT("material"), Mat);
		AddPart(TEXT("Floor"), CubeMesh, Loc, FRotator::ZeroRotator, Size, FName(*Mat));
	}

	// ---- Walls and props ----
	const TArray<TSharedPtr<FJsonValue>>* Items = nullptr;
	int32 Count = 0;
	if (Doc->TryGetArrayField(TEXT("items"), Items) && Items)
	{
		for (const TSharedPtr<FJsonValue>& V : *Items)
		{
			const TSharedPtr<FJsonObject> It = V.IsValid() ? V->AsObject() : nullptr;
			if (!It.IsValid())
			{
				continue;
			}
			FString Name, Shape, Mat;
			It->TryGetStringField(TEXT("name"), Name);
			It->TryGetStringField(TEXT("shape"), Shape);
			It->TryGetStringField(TEXT("material"), Mat);
			FVector Loc, Rot, Size;
			if (!ReadVec3(It, TEXT("loc"), Loc) || !ReadVec3(It, TEXT("size"), Size))
			{
				continue;
			}
			ReadVec3(It, TEXT("rot"), Rot);   // [Pitch, Yaw, Roll]
			UStaticMesh* Mesh = Shape == TEXT("cylinder") ? CylinderMesh.Get() : CubeMesh.Get();
			AddPart(Name.IsEmpty() ? FString::Printf(TEXT("Item_%d"), Count) : Name, Mesh, Loc,
				FRotator(Rot.X, Rot.Y, Rot.Z), Size, FName(*Mat));
			++Count;
		}
	}

	// ---- Spawn pose (robot waits here until the first bridge pose arrives) ----
	const TSharedPtr<FJsonObject>* Spawn = nullptr;
	bHasSpawn = false;
	if (Doc->TryGetObjectField(TEXT("spawn"), Spawn) && Spawn)
	{
		FVector Loc, Rot;
		if (ReadVec3(*Spawn, TEXT("loc"), Loc) && ReadVec3(*Spawn, TEXT("rot"), Rot))
		{
			SpawnTransform = FTransform(FRotator(Rot.X, Rot.Y, Rot.Z), Loc);
			bHasSpawn = true;
			for (TActorIterator<ASplunkerRobot> It(GetWorld()); It; ++It)
			{
				It->PlaceAtSpawn(SpawnTransform);
			}
		}
	}

	UE_LOG(LogSplunker, Log, TEXT("Built world from %s: %d items"), *RelativePath, Count);
	return true;
}
