#!/usr/bin/env python3
"""Generate Gazebo and Unreal world files from one *.world.yaml layout.

The layout YAML (worlds/<name>.world.yaml) is the single source of truth for a
world. This script writes:

  * src/robot_splunker_gazebo/worlds/<name>.sdf        -- Gazebo Harmonic world
  * src/robot_splunker_gazebo/worlds/<name>.meta.json  -- spawn pose for launch files
  * unreal/SplunkerViz/Content/Splunker/Data/<name>_layout.json -- Unreal layout

so the walls the robot's lidar sees in Gazebo are exactly where Unreal draws them.

Frames / units
  YAML + SDF : ROS/Gazebo world frame (right-handed, x fwd, y left, z up), metres, radians
  UE JSON    : Unreal world frame (left-handed, X fwd, Y right, Z up), centimetres, degrees
               conversion:  X = 100 x,  Y = -100 y,  Z = 100 z,  yaw_deg = -degrees(yaw)

Run `generate_world.py --help` for options.
"""

import argparse
import json
import math
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - friendly message instead of a traceback
    sys.exit("PyYAML is required: sudo apt install python3-yaml  (or pip install pyyaml)")

REPO_DIR = Path(__file__).resolve().parent.parent
DEFAULT_LAYOUT_DIR = REPO_DIR / "worlds"
DEFAULT_SDF_DIR = REPO_DIR / "src" / "robot_splunker_gazebo" / "worlds"
DEFAULT_UE_DIR = REPO_DIR / "unreal" / "SplunkerViz" / "Content" / "Splunker" / "Data"

# Gazebo colours (RGB 0..1) per material tag. Unreal maps the same tags to real
# materials (see Project Settings > Plugins > Splunker Viz > Material Overrides).
MATERIAL_COLORS = {
    "concrete": (0.60, 0.60, 0.58),
    "rock": (0.45, 0.38, 0.30),
    "brick": (0.60, 0.26, 0.20),
    "metal": (0.50, 0.55, 0.60),
    "wood": (0.55, 0.40, 0.24),
    "floor": (0.30, 0.30, 0.30),
}

M_TO_CM = 100.0


# --------------------------------------------------------------------------- layout
def load_layout(path):
    """Read and validate a layout YAML file; returns a dict with defaults filled in."""
    with open(path, "r", encoding="utf-8") as f:
        layout = yaml.safe_load(f) or {}
    for key in ("name", "floor", "spawn"):
        if key not in layout:
            raise ValueError(f"{path}: missing required key '{key}'")
    layout.setdefault("defaults", {})
    layout["defaults"].setdefault("wall_height", 2.0)
    layout["defaults"].setdefault("wall_thickness", 0.2)
    layout["defaults"].setdefault("wall_material", "concrete")
    layout.setdefault("walls", [])
    layout.setdefault("props", [])
    layout["walls"] = layout["walls"] or []
    layout["props"] = layout["props"] or []
    return layout


def build_items(layout):
    """Turn walls + props into a flat list of solid items in the ROS world frame.

    Each item: name, shape (box|cylinder), material, x, y, z (centre), yaw,
    size (sx, sy, sz) for boxes or (diameter, diameter, height) for cylinders.
    """
    d = layout["defaults"]
    items = []
    for i, w in enumerate(layout["walls"]):
        (x0, y0), (x1, y1) = w["start"], w["end"]
        height = float(w.get("height", d["wall_height"]))
        thick = float(w.get("thickness", d["wall_thickness"]))
        length = math.hypot(x1 - x0, y1 - y0)
        if length <= 0.0:
            raise ValueError(f"wall {i} has zero length")
        items.append({
            "name": w.get("name", f"wall_{i}"),
            "shape": "box",
            "material": w.get("material", d["wall_material"]),
            "x": (x0 + x1) / 2.0,
            "y": (y0 + y1) / 2.0,
            "z": height / 2.0,
            "yaw": math.atan2(y1 - y0, x1 - x0),
            # + thickness so perpendicular walls overlap at the corners (no gaps).
            "size": (length + thick, thick, height),
        })
    for i, p in enumerate(layout["props"]):
        shape = p.get("shape", "box")
        x, y = p["xy"]
        if shape == "cylinder":
            r, h = float(p["radius"]), float(p["height"])
            size = (2 * r, 2 * r, h)
        elif shape == "box":
            size = tuple(float(v) for v in p["size"])
        else:
            raise ValueError(f"prop {i}: unknown shape '{shape}'")
        items.append({
            "name": p.get("name", f"prop_{i}"),
            "shape": shape,
            "material": p.get("material", "wood"),
            "x": float(x),
            "y": float(y),
            "z": size[2] / 2.0,
            "yaw": float(p.get("yaw", 0.0)),
            "size": size,
        })
    return items


# --------------------------------------------------------------------------- Gazebo SDF
def _color(material):
    r, g, b = MATERIAL_COLORS.get(material, MATERIAL_COLORS["concrete"])
    return f"{r:.2f} {g:.2f} {b:.2f} 1"


def _geometry(item):
    sx, sy, sz = item["size"]
    if item["shape"] == "cylinder":
        return f"<cylinder><radius>{sx / 2:.4f}</radius><length>{sz:.4f}</length></cylinder>"
    return f"<box><size>{sx:.4f} {sy:.4f} {sz:.4f}</size></box>"


def _link(item, indent="      "):
    geom = _geometry(item)
    col = _color(item["material"])
    return (
        f'{indent}<link name="{item["name"]}">\n'
        f'{indent}  <pose>{item["x"]:.4f} {item["y"]:.4f} {item["z"]:.4f} 0 0 {item["yaw"]:.5f}</pose>\n'
        f'{indent}  <collision name="collision"><geometry>{geom}</geometry></collision>\n'
        f'{indent}  <visual name="visual">\n'
        f'{indent}    <geometry>{geom}</geometry>\n'
        f'{indent}    <material><ambient>{col}</ambient><diffuse>{col}</diffuse>'
        f'<specular>0.1 0.1 0.1 1</specular></material>\n'
        f'{indent}  </visual>\n'
        f'{indent}</link>\n'
    )


def render_sdf(layout, items, source_name):
    """Build the Gazebo Harmonic world SDF as a string."""
    name = layout["name"]
    fx, fy = layout["floor"]["size"]
    floor_col = _color(layout["floor"].get("material", "floor"))
    links = "".join(_link(it) for it in items)
    walls_model = (
        '    <!-- All walls and props: one static model, one link per solid. -->\n'
        '    <model name="structure">\n'
        '      <static>true</static>\n'
        f'{links}'
        '    </model>\n'
    ) if items else ""
    return f"""<?xml version="1.0" ?>
<!--
  GENERATED by scripts/generate_world.py from worlds/{source_name}
  DO NOT EDIT BY HAND. Edit the YAML, then run scripts/generate_world.py
  (bld.sh runs it for you). Note: XML comments may not contain a double hyphen.
-->
<sdf version="1.9">
  <world name="{name}">
    <!-- 1 ms physics step, real time -->
    <physics name="1ms" type="ignored">
      <max_step_size>0.001</max_step_size>
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <!-- World systems: physics, GUI/user commands, scene publishing (GUI + sensors),
         sensor rendering (gpu_lidar needs ogre2) and the IMU sensor system. -->
    <plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-imu-system" name="gz::sim::systems::Imu"/>

    <scene>
      <ambient>0.4 0.4 0.4 1</ambient>
      <background>0.7 0.7 0.7 1</background>
      <shadows>true</shadows>
    </scene>

    <light type="directional" name="sun">
      <cast_shadows>true</cast_shadows>
      <pose>0 0 10 0 0 0</pose>
      <diffuse>0.8 0.8 0.8 1</diffuse>
      <specular>0.2 0.2 0.2 1</specular>
      <direction>-0.5 0.1 -0.9</direction>
    </light>

    <model name="ground_plane">
      <static>true</static>
      <link name="link">
        <collision name="collision">
          <geometry><plane><normal>0 0 1</normal><size>{fx} {fy}</size></plane></geometry>
        </collision>
        <visual name="visual">
          <geometry><plane><normal>0 0 1</normal><size>{fx} {fy}</size></plane></geometry>
          <material><ambient>{floor_col}</ambient><diffuse>{floor_col}</diffuse>
            <specular>0.05 0.05 0.05 1</specular></material>
        </visual>
      </link>
    </model>

{walls_model}  </world>
</sdf>
"""


# --------------------------------------------------------------------------- Unreal JSON
def ros_to_ue_loc(x, y, z):
    """ROS metres (right-handed) -> UE centimetres (left-handed): Y is mirrored."""
    return [round(x * M_TO_CM, 2), round(-y * M_TO_CM, 2), round(z * M_TO_CM, 2)]


def ros_yaw_to_ue_deg(yaw):
    """A counter-clockwise ROS yaw is a negative (clockwise-positive) UE yaw."""
    return round(-math.degrees(yaw), 4)


def render_ue(layout, items, source_name):
    """Build the Unreal layout document (dict) in UE units."""
    fx, fy = layout["floor"]["size"]
    sp = layout["spawn"]
    return {
        "format": 1,
        "generated_from": f"worlds/{source_name}",
        "units": "cm, degrees, Unreal left-handed (X fwd, Y right, Z up)",
        "world": layout["name"],
        "floor": {
            "material": layout["floor"].get("material", "floor"),
            "loc": [0.0, 0.0, -1.0],
            "size": [fx * M_TO_CM, fy * M_TO_CM, 2.0],
        },
        "spawn": {
            "loc": ros_to_ue_loc(sp["x"], sp["y"], 0.0),
            "rot": [0.0, ros_yaw_to_ue_deg(sp.get("yaw", 0.0)), 0.0],
        },
        "items": [
            {
                "name": it["name"],
                "shape": it["shape"],
                "material": it["material"],
                "loc": ros_to_ue_loc(it["x"], it["y"], it["z"]),
                # [pitch, yaw, roll] like FRotator
                "rot": [0.0, ros_yaw_to_ue_deg(it["yaw"]), 0.0],
                "size": [round(v * M_TO_CM, 2) for v in it["size"]],
            }
            for it in items
        ],
    }


def render_meta(layout, source_name):
    """Small JSON read by the launch files (spawn pose = SLAM map origin)."""
    sp = layout["spawn"]
    return {
        "generated_from": f"worlds/{source_name}",
        "world": layout["name"],
        "spawn": {"x": float(sp["x"]), "y": float(sp["y"]), "yaw": float(sp.get("yaw", 0.0))},
    }


# --------------------------------------------------------------------------- main
def _write(path, text, check, quiet):
    """Write text to path; in --check mode only compare. Returns True when up to date."""
    path = Path(path)
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if check:
        if current != text:
            print(f"OUT OF DATE: {path}")
            return False
        return True
    path.parent.mkdir(parents=True, exist_ok=True)
    if current != text:
        path.write_text(text, encoding="utf-8", newline="\n")
        if not quiet:
            print(f"wrote {path}")
    elif not quiet:
        print(f"unchanged {path}")
    return True


def generate(layout_path, sdf_dir, ue_dir, check=False, quiet=False):
    """Generate all outputs for one layout file. Returns True when everything is up to date."""
    layout_path = Path(layout_path)
    layout = load_layout(layout_path)
    items = build_items(layout)
    name = layout["name"]
    src = layout_path.name
    ok = True
    ok &= _write(Path(sdf_dir) / f"{name}.sdf", render_sdf(layout, items, src), check, quiet)
    ok &= _write(Path(sdf_dir) / f"{name}.meta.json",
                 json.dumps(render_meta(layout, src), indent=2) + "\n", check, quiet)
    ok &= _write(Path(ue_dir) / f"{name}_layout.json",
                 json.dumps(render_ue(layout, items, src), indent=2) + "\n", check, quiet)
    return ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="generate_world.py",
        description=("Generate the Gazebo SDF, launch metadata and Unreal layout JSON from "
                     "worlds/*.world.yaml (the single source of truth for each world)."),
        epilog=("Examples:\n"
                "  python3 scripts/generate_world.py                      # all layouts\n"
                "  python3 scripts/generate_world.py worlds/empty.world.yaml\n"
                "  python3 scripts/generate_world.py --check              # CI: fail if stale\n"
                "Related: ./scripts/bld.sh --worlds runs this for you."),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("layouts", nargs="*", type=Path,
                        help="layout YAML files (default: every worlds/*.world.yaml)")
    parser.add_argument("--sdf-dir", type=Path, default=DEFAULT_SDF_DIR,
                        help=f"output folder for .sdf/.meta.json (default: {DEFAULT_SDF_DIR})")
    parser.add_argument("--ue-dir", type=Path, default=DEFAULT_UE_DIR,
                        help=f"output folder for Unreal layout JSON (default: {DEFAULT_UE_DIR})")
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 if any generated file is out of date")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print problems")
    args = parser.parse_args(argv)

    layouts = args.layouts or sorted(DEFAULT_LAYOUT_DIR.glob("*.world.yaml"))
    if not layouts:
        parser.error(f"no layouts found in {DEFAULT_LAYOUT_DIR}")
    all_ok = True
    for lp in layouts:
        all_ok &= generate(lp, args.sdf_dir, args.ue_dir, check=args.check, quiet=args.quiet)
    if args.check and not all_ok:
        print("Generated world files are stale; run ./scripts/bld.sh --worlds", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
