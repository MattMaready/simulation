// Plain data received from the ROS bridge. All values are already in Unreal
// units (cm, degrees, left-handed); see robot_splunker_ue_bridge/protocol.py.
#pragma once

#include "CoreMinimal.h"

/** Robot pose: ground truth ("pose") or SLAM estimate ("slam_pose"). */
struct FSplunkerPoseState
{
	bool bValid = false;
	FVector Location = FVector::ZeroVector;
	FRotator Rotation = FRotator::ZeroRotator;
	double Stamp = 0.0;
	uint64 Seq = 0;
};

/** Wheel joint angles in radians (positive = rolling forward). */
struct FSplunkerWheelState
{
	bool bValid = false;
	double LeftRad = 0.0;
	double RightRad = 0.0;
	uint64 Seq = 0;
};

/** One lidar scan projected into world hit points. */
struct FSplunkerScanState
{
	FVector Origin = FVector::ZeroVector;
	TArray<FVector> Hits;
	double Stamp = 0.0;
	uint64 Seq = 0;
};

/**
 * SLAM occupancy grid. Cells are row-major, row 0 = map y-min; 255 = unknown,
 * 0..100 = occupancy probability. Cell (col,row) is at
 * Origin + FRotator(0,YawDeg,0).RotateVector(FVector(col*Res, -row*Res, 0)).
 */
struct FSplunkerMapState
{
	int32 Width = 0;
	int32 Height = 0;
	float ResolutionCm = 5.f;
	FVector Origin = FVector::ZeroVector;
	float YawDeg = 0.f;
	TArray<uint8> Cells;
	uint64 Seq = 0;
};
