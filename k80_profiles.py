"""Local profile persistence and validation."""

import json
import os
from pathlib import Path

from k80_input import KEY_NAMES, MEDIA, MODIFIERS, canonical, output_sequence

EFFECTS = {
    1: "Static", 2: "Breathing", 4: "Cross wave", 5: "Fade", 6: "Reverse ripple",
    7: "Horizontal wave", 8: "Twinkle", 9: "Vortex", 10: "Tide", 11: "Diagonal wave",
    13: "Ripple", 14: "Key trail", 15: "Cell", 16: "Knock", 17: "Moving ripple",
    18: "Laser ripple", 19: "Scan line", 20: "Rain", 21: "Starry night",
    22: "Fireworks", 23: "Sine wave", 24: "Swing",
}
ACTIONS = ("Open file or app", "Media", "Type text", "Send keys")
PATH = Path(os.environ["LOCALAPPDATA"]) / "K80 Control Center" / "profiles.json"


def default_profile():
    return {"lighting": None, "shortcuts": []}


def defaults():
    return {"version": 1, "active": "Default", "profiles": {"Default": default_profile()}}


def new_binding(modifiers, key, action, value):
    if not modifiers or key not in KEY_NAMES or key in MODIFIERS:
        raise ValueError("Choose a chord with at least one modifier and a regular K80 key.")
    if tuple(modifiers) != canonical(modifiers):
        raise ValueError("Invalid modifiers.")
    if action not in ACTIONS or not isinstance(value, str) or not value.strip() or len(value) > 2048:
        raise ValueError("Enter an action and a value up to 2,048 characters.")
    if action == "Media" and value not in MEDIA:
        raise ValueError("Choose a media action.")
    if action == "Open file or app" and not Path(value).is_absolute():
        raise ValueError("Choose a full path to a file or an application.")
    if action == "Send keys":
        if value.count(",") >= 32:
            raise ValueError("Use up to 32 key chords per action.")
        output_sequence(value)
    return {"modifiers": list(modifiers), "key": key, "action": action, "value": value}


def validate(data):
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported profile file version.")
    profiles = data["profiles"]
    if not isinstance(profiles, dict) or data["active"] not in profiles:
        raise ValueError("The active profile is missing.")
    for name, profile in profiles.items():
        if not name.strip() or len(name) > 50:
            raise ValueError("Invalid profile name.")
        light = profile["lighting"]
        if light is not None and (
            light["mode"] not in EFFECTS or type(light["brightness"]) is not int
            or not 0 <= light["brightness"] <= 100 or type(light["speed"]) is not int
            or not 0 <= light["speed"] <= 4 or type(light["win_lock"]) is not bool
        ):
            raise ValueError("Invalid saved lighting settings.")
        shortcuts = profile["shortcuts"]
        if not isinstance(shortcuts, list):
            raise ValueError("Invalid shortcut list.")
        seen = set()
        for item in shortcuts:
            new_binding(item["modifiers"], item["key"], item["action"], item["value"])
            chord = (tuple(item["modifiers"]), item["key"])
            if chord in seen:
                raise ValueError("Duplicate shortcut.")
            seen.add(chord)
    return data


def load(path=PATH):
    try:
        return validate(json.loads(path.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return defaults()
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, OSError) as exc:
        raise ValueError(f"Could not read profiles from {path}. {exc}") from exc


def save(data, path=PATH):
    validate(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
