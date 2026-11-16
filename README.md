# Soundcore Liberty 4 NC Control for macOS and Windows

A local web interface for changing the listening mode and equalizer on Soundcore Liberty 4 NC earbuds from a computer. Connect the earbuds in Bluetooth settings, run the launcher, and use the controls in your browser.

## Features

- Switch between Noise Cancellation, Transparency, and Normal.
- Adjust eight EQ bands from 100 Hz to 12.8 kHz and apply the curve to both earbuds.
- Read the current listening mode, EQ curve, and firmware version.
- Confirm settings changes by reading them back from the earbuds.

## Requirements

- Soundcore Liberty 4 NC earbuds (model A3947) paired with the computer.
- **macOS:** A Mac with Bluetooth and Apple Command Line Tools. The macOS app has been used successfully with this model on Apple Silicon.
- **Windows:** Windows 10 or 11 with a Bluetooth Classic-capable adapter and [Python 3.10 or later](https://www.python.org/downloads/windows/). The Windows port has been tested with simulated Bluetooth responses. Live verification on Windows is pending.

## Quick start

Download the repository with **Code → Download ZIP**, extract it, and keep the files together. Take both earbuds out of the case and connect them in your computer’s Bluetooth settings. Close the Soundcore app on your phone if it is using the earbuds.

### macOS

In Terminal, change to the extracted folder and run:

```bash
bash Start-Soundcore.command
```

You can also type `bash` followed by a space, drag **Start-Soundcore.command** into Terminal, and press **Return**. If Command Line Tools installation starts, run the launcher again once it finishes. Allow Bluetooth access if macOS prompts you.

### Windows

1. Install Python if needed. If the installer offers **Add python.exe to PATH**, enable it.
2. Open **Settings → Bluetooth & devices** (or **Devices → Bluetooth & other devices** on Windows 10) and connect **soundcore Liberty 4 NC**.
3. Double-click **Start-Soundcore.bat** in the extracted folder.

If automatic discovery fails, open Command Prompt in the extracted folder and pass the earbuds’ Bluetooth address. Replace the example address with the one shown in the Bluetooth device details in Device Manager.

```bat
Start-Soundcore.bat --address 00:11:22:33:44:55
```

The launcher opens the control panel in your default browser. If it doesn’t open, visit the address printed in the launcher window. Keep that window open while you use the panel. Press **Ctrl+C** to stop it.

## Using the controls

- **Listening mode** applies the selected mode immediately. The highlighted button shows the mode reported by the earbuds.
- **Equalizer** lets you adjust each band and send the curve with **Apply EQ**. **Flatten curve** sets all sliders to 0 dB. Click **Apply EQ** to send the flat curve.
- **Read earbuds** refreshes the page after you change settings on the earbuds or in the mobile app.

Applying a custom EQ turns off HearID so the custom curve can take effect.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| The page can’t find the earbuds | Confirm that **Liberty 4 NC** shows as connected in your computer’s Bluetooth settings. If you renamed them, keep “Liberty 4 NC” in the Bluetooth name. |
| The control channel won’t open | Close the Soundcore app on your phone. Reconnect the earbuds, then click **Read earbuds**. If macOS blocked Bluetooth access, check **System Settings → Privacy & Security → Bluetooth**. |
| **Apply EQ** is disabled | Take both earbuds out of the case and click **Read earbuds**. |
| The browser can’t reach the page | Keep the launcher running and use the exact local address it prints. The port can change each time you launch it. |

## How it works

The browser talks to a Python HTTP server bound to `127.0.0.1`. The macOS launcher uses an Objective-C helper with IOBluetooth. The Windows launcher uses Winsock to resolve the Liberty 4 NC Bluetooth service and connect to it. Both send the same Soundcore commands over Bluetooth Classic RFCOMM. The app runs locally and needs no cloud service or account. GitHub hosts the source and download.

The A3947 packet layout and test data were cross-checked against [OpenSCQ30](https://github.com/Oppzippy/OpenSCQ30/tree/master/lib/src/devices/soundcore/a3947). This is an independent project and is unaffiliated with Anker or Soundcore.
