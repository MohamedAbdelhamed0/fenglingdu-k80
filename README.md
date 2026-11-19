# FENGLINGDU K80 – Wireless Gaming Keyboard

A Windows companion app for the FENGLINGDU K80 87-key keyboard. The keyboard supports wireless modes, and the app communicates with it over USB-C in **Cable** mode.

Created by [Mohamed Abdelhamed](https://github.com/MohamedAbdelhamed0).

## Open the app

1. Connect the keyboard with a USB-C data cable and set its switch to **Cable**.
2. Download the Windows x64 ZIP from [GitHub Releases](https://github.com/MohamedAbdelhamed0/fenglingdu-k80/releases/latest), extract the entire folder, and run `K80 Control Center.exe`. If installed locally, open **FENGLINGDU K80 – Wireless Gaming Keyboard** from Start. Windows uses its built-in HID driver.
3. Wait for **K80 connected over USB-C**. The Lighting tab reads the keyboard automatically.

## Lighting and profiles

- Change an effect, brightness, speed, backlight state, or Windows key lock directly. Effect and switch changes apply immediately. Slider changes apply when you release the mouse or pause briefly. The app reads back each update. Brightness zero is used for backlight off.
- Click **Read keyboard** after changing settings using Fn shortcuts. The app checks the current hardware state before each write and alerts you if the keyboard changed since its last read.
- Use **New** to create a profile. **Save to profile** saves the current lighting settings. **Load profile lighting** sends the active profile’s lighting settings to the K80 immediately.
- Profiles and shortcut values are local in `%LOCALAPPDATA%\K80 Control Center\profiles.json`. Copy that file to back up your profiles.

## Key tester and shortcuts

- Open **Key tester** and press physical keys on the wired K80. Green shows keys currently held and blue shows keys already tested.
- Open **Windows shortcuts**, click **Capture a K80 chord**, then hold at least one modifier and press a regular key. Choose an action and click **Save shortcut**. Capturing the same chord again updates its action.
- Supported actions open a local file or app, control media, type text, or send key sequences such as `Ctrl+S, Enter`. Enable shortcuts to run actions while the app is focused. Use **Run while app is in background** for other Windows apps. Actions run after the wired K80 keys are released. Windows and the active app still receive the original chord, so pick a chord that they do not already use.
- Shortcuts start paused each time the app opens. Closing the app stops them. Windows can restrict key injection into elevated applications.

## Hardware coverage

The app matches USB ID `5566:0008`, the `K80` product, and the `ZXWCustom` interface on the same physical device. The related [ZXWMicroChip protocol reference](https://github.com/Sahin1705/Everest-KB-MK1/blob/main/docs/PROTOCOL.md) documents the report format and supplies effect names. The connected K80 accepted and returned all 22 listed effect IDs, brightness, speed, backlight off, and the Win-lock setting. Effect names describe the related firmware and may differ on this model. The physical results require visual or hands-on verification.

The manual describes 24 Fn-selectable modes. The app offers the 22 effect IDs with known names and successful readback. If a different effect is active, its ID is displayed and preserved when you adjust another setting.

The **Keyboard guide** covers the manual’s Fn shortcuts. USB control for per-key lighting and color, onboard remaps and macros, battery, wireless settings, and Windows/Mac layout remains unverified. Windows actions and profiles run on this PC. The app does not flash firmware.

## Run and build from source

Use Windows with Python 3.12 and PySide6 Essentials. PyInstaller is only needed for packaging.

```powershell
python -m pip install -r requirements.txt
python -B k80_control.py
python -B -m unittest -v
python -m pip install pyinstaller
python -m PyInstaller --noconfirm --onedir --windowed --name "K80 Control Center" --icon k80.ico --version-file version_info.txt --add-data "k80.ico;." k80_control.py
```

The portable Windows build uses dynamically linked Qt for Python under LGPLv3. See [third-party notices](THIRD_PARTY_NOTICES.md) for the corresponding sources and license texts.
