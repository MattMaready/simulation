// Connection to the ROS 2 ue_bridge node (WebSocket client).
//
// Lives as long as the game instance. Connects to USplunkerVizSettings::BridgeUrl,
// reconnects automatically, parses the JSON protocol (protocol.py) and keeps the
// latest state. Actors poll the getters each tick (cheap, no binding needed);
// map/scan changes are also broadcast through native delegates.
//
// Thread safety: WebSocket callbacks may arrive on another thread, so they only
// enqueue events; all parsing and state changes happen on the game thread in Tick().
#pragma once

#include "CoreMinimal.h"
#include "Containers/Queue.h"
#include "Containers/Ticker.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "SplunkerTypes.h"
#include "SplunkerBridgeSubsystem.generated.h"

class IWebSocket;
class FJsonObject;

DECLARE_MULTICAST_DELEGATE(FOnSplunkerDataUpdated);

UCLASS()
class SPLUNKERVIZ_API USplunkerBridgeSubsystem : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	/** Convenience accessor from any actor / world context. May return nullptr. */
	static USplunkerBridgeSubsystem* Get(const UObject* WorldContext);

	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	virtual void Deinitialize() override;

	bool IsConnected() const { return bConnected; }
	const FString& GetUrl() const { return Url; }
	const FSplunkerPoseState& GetPose() const { return Pose; }
	const FSplunkerPoseState& GetSlamPose() const { return SlamPose; }
	const FSplunkerWheelState& GetWheels() const { return Wheels; }
	const FSplunkerScanState& GetScan() const { return Scan; }
	const FSplunkerMapState& GetMap() const { return Map; }
	const FString& GetExplorerState() const { return ExplorerState; }
	const FString& GetWorldName() const { return WorldName; }
	double GetSimTime() const { return SimTime; }
	float GetMessagesPerSecond() const { return MessagesPerSecond; }

	FOnSplunkerDataUpdated OnMapUpdated;
	FOnSplunkerDataUpdated OnScanUpdated;

private:
	enum class EEventKind : uint8 { Connected, Error, Closed, Message };
	struct FSocketEvent
	{
		EEventKind Kind = EEventKind::Message;
		FString Text;
	};

	void Connect();
	void DropSocket();
	bool Tick(float DeltaTime);
	void HandleMessage(const FString& Text);
	void HandleMap(const TSharedPtr<FJsonObject>& Obj);

	// WebSocket callbacks (any thread): only enqueue.
	void OnSocketConnected();
	void OnSocketError(const FString& Error);
	void OnSocketClosed(int32 StatusCode, const FString& Reason, bool bWasClean);
	void OnSocketMessage(const FString& Message);

	TSharedPtr<IWebSocket> Socket;
	TQueue<FSocketEvent, EQueueMode::Mpsc> Events;
	FTSTicker::FDelegateHandle TickHandle;

	FString Url;
	bool bConnected = false;
	bool bConnecting = false;
	double NextConnectTime = 0.0;
	double ConnectStartTime = 0.0;

	FSplunkerPoseState Pose;
	FSplunkerPoseState SlamPose;
	FSplunkerWheelState Wheels;
	FSplunkerScanState Scan;
	FSplunkerMapState Map;
	FString ExplorerState = TEXT("unknown");
	FString WorldName;
	double SimTime = 0.0;

	int32 MessagesThisWindow = 0;
	double RateWindowStart = 0.0;
	float MessagesPerSecond = 0.f;
};
