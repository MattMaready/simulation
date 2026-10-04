#include "SplunkerHUD.h"

#include "Engine/Canvas.h"
#include "Engine/Engine.h"
#include "Engine/Font.h"
#include "Engine/Texture2D.h"
#include "EngineUtils.h"
#include "OccupancyMapActor.h"
#include "SplunkerBridgeSubsystem.h"
#include "SplunkerCameraPawn.h"
#include "SplunkerRobot.h"

void ASplunkerHUD::DrawHUD()
{
	Super::DrawHUD();
	if (!Canvas)
	{
		return;
	}
	const USplunkerBridgeSubsystem* Bridge = USplunkerBridgeSubsystem::Get(this);
	UFont* Font = GEngine ? GEngine->GetSmallFont() : nullptr;
	const float X = 20.f;
	float Y = 20.f;
	const float Line = 20.f;

	// ---- Status panel ----
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.45f), X - 10.f, Y - 8.f, 380.f, 118.f);
	if (Bridge)
	{
		const bool bUp = Bridge->IsConnected();
		DrawText(bUp ? FString::Printf(TEXT("ROS bridge: CONNECTED  (%.0f msg/s)"), Bridge->GetMessagesPerSecond())
		             : FString::Printf(TEXT("ROS bridge: waiting for %s"), *Bridge->GetUrl()),
			bUp ? FLinearColor(0.3f, 1.f, 0.3f) : FLinearColor(1.f, 0.35f, 0.25f), X, Y, Font);
		Y += Line;
		DrawText(FString::Printf(TEXT("World: %s"), Bridge->GetWorldName().IsEmpty() ? TEXT("-") : *Bridge->GetWorldName()),
			FLinearColor::White, X, Y, Font);
		Y += Line;
		DrawText(FString::Printf(TEXT("Explorer: %s"), *Bridge->GetExplorerState()), FLinearColor(1.f, 0.8f, 0.3f), X, Y, Font);
		Y += Line;
		DrawText(FString::Printf(TEXT("Sim time: %.1f s"), Bridge->GetSimTime()), FLinearColor::White, X, Y, Font);
		Y += Line;
	}
	const ASplunkerCameraPawn* Cam = Cast<ASplunkerCameraPawn>(GetOwningPawn());
	if (Cam)
	{
		DrawText(FString::Printf(TEXT("Camera: %s   (F1 help)"), ASplunkerCameraPawn::ModeName(Cam->GetMode())),
			FLinearColor::White, X, Y, Font);
		Y += Line;
	}

	// ---- Key help ----
	if (Cam && Cam->IsHelpVisible())
	{
		Y += 14.f;
		static const TCHAR* Help[] = {
			TEXT("1 chase   2 orbit (mouse)   3 top-down   4 free-fly (WASD QE, Shift)"),
			TEXT("Wheel zoom   H map overlay   G SLAM ghost   L lidar   F1 hide help   Esc quit"),
		};
		DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.45f), X - 10.f, Y - 6.f, 560.f, 2 * Line + 8.f);
		for (const TCHAR* H : Help)
		{
			DrawText(H, FLinearColor(0.8f, 0.8f, 0.8f), X, Y, Font);
			Y += Line;
		}
	}

	DrawMinimap();
}

void ASplunkerHUD::DrawMinimap()
{
	const USplunkerBridgeSubsystem* Bridge = USplunkerBridgeSubsystem::Get(this);
	const AOccupancyMapActor* MapActor = nullptr;
	for (TActorIterator<AOccupancyMapActor> It(GetWorld()); It; ++It)
	{
		MapActor = *It;
		break;
	}
	UTexture2D* Tex = MapActor ? MapActor->GetTexture() : nullptr;
	if (!Bridge || !Tex)
	{
		return;
	}
	const FSplunkerMapState& Map = Bridge->GetMap();
	if (Map.Width <= 0 || Map.Height <= 0)
	{
		return;
	}

	// Fit the map into MinimapSize, top-right corner.
	const float Scale = MinimapSize / FMath::Max(Map.Width, Map.Height);
	const float W = Map.Width * Scale, H = Map.Height * Scale;
	const float X0 = Canvas->SizeX - W - 20.f, Y0 = 20.f;
	DrawRect(FLinearColor(0.f, 0.f, 0.f, 0.5f), X0 - 4.f, Y0 - 4.f, W + 8.f, H + 8.f);
	DrawTexture(Tex, X0, Y0, W, H, 0.f, 0.f, 1.f, 1.f, FLinearColor::White, BLEND_Translucent);

	// Robot dot: undo the map placement (see FSplunkerMapState) to get its cell.
	const ASplunkerRobot* Robot = nullptr;
	for (TActorIterator<ASplunkerRobot> It(GetWorld()); It; ++It)
	{
		Robot = *It;
		break;
	}
	if (Robot && Map.ResolutionCm > 0.f)
	{
		const FVector Local = FRotator(0.f, -Map.YawDeg, 0.f).RotateVector(Robot->GetActorLocation() - Map.Origin);
		const float Col = Local.X / Map.ResolutionCm;
		const float Row = -Local.Y / Map.ResolutionCm;           // map +y is UE -Y
		const float Px = X0 + Col * Scale;
		const float Py = Y0 + (Map.Height - Row) * Scale;        // texture is north-up
		DrawRect(FLinearColor(0.1f, 1.f, 0.2f), Px - 3.f, Py - 3.f, 6.f, 6.f);
	}
	DrawText(TEXT("SLAM map"), FLinearColor::White, X0, Y0 + H + 6.f, GEngine ? GEngine->GetSmallFont() : nullptr);
}
