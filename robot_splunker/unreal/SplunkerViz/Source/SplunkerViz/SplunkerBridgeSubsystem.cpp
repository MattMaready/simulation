#include "SplunkerBridgeSubsystem.h"

#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"
#include "Engine/GameInstance.h"
#include "Engine/World.h"
#include "HAL/PlatformTime.h"
#include "IWebSocket.h"
#include "Misc/Base64.h"
#include "Modules/ModuleManager.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "SplunkerViz.h"
#include "SplunkerVizSettings.h"
#include "WebSocketsModule.h"

namespace
{
	/** Read a [x, y, z] JSON array field into a vector. */
	bool ReadVec3(const TSharedPtr<FJsonObject>& Obj, const TCHAR* Field, FVector& Out)
	{
		const TArray<TSharedPtr<FJsonValue>>* Arr = nullptr;
		if (!Obj->TryGetArrayField(Field, Arr) || Arr == nullptr || Arr->Num() < 3)
		{
			return false;
		}
		Out = FVector((*Arr)[0]->AsNumber(), (*Arr)[1]->AsNumber(), (*Arr)[2]->AsNumber());
		return true;
	}

	/** If a connection attempt hangs this long, abandon it and retry. */
	constexpr double ConnectTimeoutSeconds = 5.0;
}

USplunkerBridgeSubsystem* USplunkerBridgeSubsystem::Get(const UObject* WorldContext)
{
	const UWorld* World = WorldContext ? WorldContext->GetWorld() : nullptr;
	UGameInstance* GI = World ? World->GetGameInstance() : nullptr;
	return GI ? GI->GetSubsystem<USplunkerBridgeSubsystem>() : nullptr;
}

void USplunkerBridgeSubsystem::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	Url = USplunkerVizSettings::Get()->BridgeUrl;
	FModuleManager::Get().LoadModuleChecked<FWebSocketsModule>(TEXT("WebSockets"));
	RateWindowStart = FPlatformTime::Seconds();
	NextConnectTime = 0.0;   // connect on the first tick
	TickHandle = FTSTicker::GetCoreTicker().AddTicker(
		FTickerDelegate::CreateUObject(this, &USplunkerBridgeSubsystem::Tick), 0.0f);
	UE_LOG(LogSplunker, Log, TEXT("Splunker bridge subsystem started; target %s"), *Url);
}

void USplunkerBridgeSubsystem::Deinitialize()
{
	FTSTicker::GetCoreTicker().RemoveTicker(TickHandle);
	DropSocket();
	Super::Deinitialize();
}

// ---------------------------------------------------------------------------- connection

void USplunkerBridgeSubsystem::Connect()
{
	DropSocket();
	// No sub-protocol: the Python `websockets` server does not use one.
	Socket = FWebSocketsModule::Get().CreateWebSocket(Url, FString());
	Socket->OnConnected().AddUObject(this, &USplunkerBridgeSubsystem::OnSocketConnected);
	Socket->OnConnectionError().AddUObject(this, &USplunkerBridgeSubsystem::OnSocketError);
	Socket->OnClosed().AddUObject(this, &USplunkerBridgeSubsystem::OnSocketClosed);
	Socket->OnMessage().AddUObject(this, &USplunkerBridgeSubsystem::OnSocketMessage);
	bConnecting = true;
	ConnectStartTime = FPlatformTime::Seconds();
	Socket->Connect();
}

void USplunkerBridgeSubsystem::DropSocket()
{
	if (Socket.IsValid())
	{
		Socket->OnConnected().RemoveAll(this);
		Socket->OnConnectionError().RemoveAll(this);
		Socket->OnClosed().RemoveAll(this);
		Socket->OnMessage().RemoveAll(this);
		if (Socket->IsConnected())
		{
			Socket->Close();
		}
		Socket.Reset();
	}
	bConnected = false;
	bConnecting = false;
}

void USplunkerBridgeSubsystem::OnSocketConnected()                  { Events.Enqueue({EEventKind::Connected, FString()}); }
void USplunkerBridgeSubsystem::OnSocketError(const FString& Error)  { Events.Enqueue({EEventKind::Error, Error}); }
void USplunkerBridgeSubsystem::OnSocketMessage(const FString& Msg)  { Events.Enqueue({EEventKind::Message, Msg}); }
void USplunkerBridgeSubsystem::OnSocketClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
	Events.Enqueue({EEventKind::Closed, FString::Printf(TEXT("%d %s"), StatusCode, *Reason)});
}

// ---------------------------------------------------------------------------- tick

bool USplunkerBridgeSubsystem::Tick(float DeltaTime)
{
	const double Now = FPlatformTime::Seconds();
	const double Retry = USplunkerVizSettings::Get()->ReconnectIntervalSeconds;

	// 1. Drain events queued by the socket callbacks.
	FSocketEvent Ev;
	while (Events.Dequeue(Ev))
	{
		switch (Ev.Kind)
		{
		case EEventKind::Connected:
			bConnected = true;
			bConnecting = false;
			UE_LOG(LogSplunker, Log, TEXT("Connected to ROS bridge at %s"), *Url);
			break;
		case EEventKind::Error:
		case EEventKind::Closed:
			if (bConnected || bConnecting)
			{
				UE_LOG(LogSplunker, Warning, TEXT("ROS bridge %s: %s (retrying every %.1fs)"),
					Ev.Kind == EEventKind::Error ? TEXT("connection error") : TEXT("closed"), *Ev.Text, Retry);
			}
			DropSocket();
			NextConnectTime = Now + Retry;
			break;
		case EEventKind::Message:
			HandleMessage(Ev.Text);
			break;
		}
	}

	// 2. (Re)connect when idle, or abandon an attempt that hangs.
	if (!bConnected && !bConnecting && Now >= NextConnectTime)
	{
		Connect();
	}
	else if (bConnecting && Now - ConnectStartTime > ConnectTimeoutSeconds)
	{
		DropSocket();
		NextConnectTime = Now + Retry;
	}

	// 3. Message-rate statistic for the HUD.
	if (Now - RateWindowStart >= 1.0)
	{
		MessagesPerSecond = MessagesThisWindow / static_cast<float>(Now - RateWindowStart);
		MessagesThisWindow = 0;
		RateWindowStart = Now;
	}
	return true;   // keep ticking
}

// ---------------------------------------------------------------------------- parsing

void USplunkerBridgeSubsystem::HandleMessage(const FString& Text)
{
	TSharedPtr<FJsonObject> Obj;
	const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Text);
	if (!FJsonSerializer::Deserialize(Reader, Obj) || !Obj.IsValid())
	{
		return;
	}
	FString Type;
	if (!Obj->TryGetStringField(TEXT("type"), Type))
	{
		return;
	}
	++MessagesThisWindow;

	double Stamp = 0.0;
	if (Obj->TryGetNumberField(TEXT("stamp"), Stamp) && Stamp > 0.0)
	{
		SimTime = Stamp;
	}

	if (Type == TEXT("pose") || Type == TEXT("slam_pose"))
	{
		FSplunkerPoseState& P = (Type == TEXT("pose")) ? Pose : SlamPose;
		FVector Loc, Rot;   // Rot = [Pitch, Yaw, Roll]
		if (ReadVec3(Obj, TEXT("loc"), Loc) && ReadVec3(Obj, TEXT("rot"), Rot))
		{
			P.Location = Loc;
			P.Rotation = FRotator(Rot.X, Rot.Y, Rot.Z);
			P.Stamp = Stamp;
			P.bValid = true;
			++P.Seq;
		}
	}
	else if (Type == TEXT("wheels"))
	{
		Obj->TryGetNumberField(TEXT("left"), Wheels.LeftRad);
		Obj->TryGetNumberField(TEXT("right"), Wheels.RightRad);
		Wheels.bValid = true;
		++Wheels.Seq;
	}
	else if (Type == TEXT("scan"))
	{
		ReadVec3(Obj, TEXT("origin"), Scan.Origin);
		Scan.Hits.Reset();
		const TArray<TSharedPtr<FJsonValue>>* Hits = nullptr;
		if (Obj->TryGetArrayField(TEXT("hits"), Hits) && Hits)
		{
			Scan.Hits.Reserve(Hits->Num());
			for (const TSharedPtr<FJsonValue>& V : *Hits)
			{
				const TArray<TSharedPtr<FJsonValue>>* P = nullptr;
				if (V.IsValid() && V->TryGetArray(P) && P && P->Num() >= 3)
				{
					Scan.Hits.Emplace((*P)[0]->AsNumber(), (*P)[1]->AsNumber(), (*P)[2]->AsNumber());
				}
			}
		}
		Scan.Stamp = Stamp;
		++Scan.Seq;
		OnScanUpdated.Broadcast();
	}
	else if (Type == TEXT("map"))
	{
		HandleMap(Obj);
	}
	else if (Type == TEXT("status"))
	{
		Obj->TryGetStringField(TEXT("state"), ExplorerState);
	}
	else if (Type == TEXT("hello"))
	{
		Obj->TryGetStringField(TEXT("world"), WorldName);
		UE_LOG(LogSplunker, Log, TEXT("ROS bridge says hello; world = %s"), *WorldName);
	}
}

void USplunkerBridgeSubsystem::HandleMap(const TSharedPtr<FJsonObject>& Obj)
{
	int32 W = 0, H = 0;
	double Res = 0.0, Yaw = 0.0;
	FString B64;
	FVector Origin;
	if (!Obj->TryGetNumberField(TEXT("w"), W) || !Obj->TryGetNumberField(TEXT("h"), H) ||
		!Obj->TryGetNumberField(TEXT("res_cm"), Res) || !Obj->TryGetStringField(TEXT("data_b64"), B64) ||
		!ReadVec3(Obj, TEXT("origin"), Origin))
	{
		return;
	}
	Obj->TryGetNumberField(TEXT("yaw"), Yaw);

	TArray<uint8> Cells;
	if (!FBase64::Decode(B64, Cells) || Cells.Num() != W * H)
	{
		UE_LOG(LogSplunker, Warning, TEXT("Bad map message (%dx%d, %d bytes)"), W, H, Cells.Num());
		return;
	}
	Map.Width = W;
	Map.Height = H;
	Map.ResolutionCm = static_cast<float>(Res);
	Map.Origin = Origin;
	Map.YawDeg = static_cast<float>(Yaw);
	Map.Cells = MoveTemp(Cells);
	++Map.Seq;
	OnMapUpdated.Broadcast();
}
