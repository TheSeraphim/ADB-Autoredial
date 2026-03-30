# ADB Autoredial

Automated redial utility with human-answer detection via Android Debug Bridge.

---

## Overview

**ADB Autoredial** is a PowerShell script that repeatedly calls a target phone number through an ADB-connected Android device, detecting whether the call was answered by a human or terminated early by an auto-attendant. It exits automatically once a genuine human answer is confirmed, and produces structured, timestamped log output throughout execution.

---

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10 / 11 | PowerShell 5.1 or later |
| Android Debug Bridge | `adb` must be available in `PATH` |
| Android device | USB debugging enabled, device authorized |

To verify ADB is available and a device is connected:

```powershell
adb devices
```

Expected output:

```
List of devices attached
XXXXXXXXXXXXXXXX    device
```

---

## Installation

No installation required. Copy `adb_autoredial.ps1` to any directory and run it directly.

To allow execution if PowerShell restricts unsigned scripts:

```powershell
powershell -ExecutionPolicy Bypass -File .\adb_autoredial.ps1 -Number <number>
```

---

## Usage

```powershell
.\adb_autoredial.ps1 -Number <phone_number> [options]
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `-Number` | string | Yes | — | Phone number to dial |
| `-ValidAfterSeconds` | int | No | `20` | Minimum call duration in seconds to qualify as a human answer |
| `-RetryDelay` | int | No | `3` | Seconds to wait between attempts |
| `-MaxRetries` | int | No | `0` (unlimited) | Maximum number of dial attempts; `0` = retry indefinitely |
| `-TimeoutCall` | int | No | `60` | Seconds before an unanswered call is forcibly terminated |
| `-LogFile` | string | No | *(none)* | Path to a log file; if omitted, output is console-only |
| `-DryRun` | switch | No | `$false` | Simulate execution without placing real calls |

---

## Examples

**Minimal — dial indefinitely until a human answers:**

```powershell
.\adb_autoredial.ps1 -Number 039XXXXXXXX
```

**With retry limit and log file:**

```powershell
.\adb_autoredial.ps1 -Number 039XXXXXXXX -MaxRetries 20 -LogFile C:\logs\redial.log
```

**Tighter auto-attendant threshold (flag calls shorter than 20s as machine):**

```powershell
.\adb_autoredial.ps1 -Number 039XXXXXXXX -ValidAfterSeconds 20
```

**Dry run to verify configuration without calling:**

```powershell
.\adb_autoredial.ps1 -Number 039XXXXXXXX -DryRun
```

**Full parameter set:**

```powershell
.\adb_autoredial.ps1 `
  -Number 039XXXXXXXX `
  -ValidAfterSeconds 25 `
  -RetryDelay 5 `
  -MaxRetries 50 `
  -TimeoutCall 90 `
  -LogFile C:\logs\redial.log
```

---

## How It Works

1. The script dials the target number via `adb shell am start -a android.intent.action.CALL`.
2. It polls `adb shell dumpsys telecom` every second, inspecting the call state (`DIALING`, `RINGING`, `ACTIVE`).
3. If the call reaches `ACTIVE` state and remains connected for at least `ValidAfterSeconds` seconds, a human answer is confirmed. The script exits with code `0`, leaving the call active.
4. If the call drops before the threshold — due to voicemail, an auto-attendant, a busy signal, or no answer — it is classified as a failed attempt and the script waits `RetryDelay` seconds before the next dial.
5. If `MaxRetries` is set and exhausted, the script exits with code `1`.

### Detection Logic

| Condition | Classification |
|---|---|
| Call active >= `ValidAfterSeconds` | Human answer — exit `0`, call left active |
| Call drops with no `ACTIVE` state | No answer / busy |
| Call goes `ACTIVE` then drops early | Auto-attendant |
| No state change within `TimeoutCall` | Timeout — force hang up |

---

## Output

The script prints timestamped structured output to the console (and optionally to a log file):

```
[2025-03-30 14:22:01] [INFO]  ========================================
[2025-03-30 14:22:01] [INFO]  Auto-redial starting
[2025-03-30 14:22:01] [INFO]    Target number    : 039XXXXXXXX
[2025-03-30 14:22:01] [INFO]    Valid after      : 20s
[2025-03-30 14:22:01] [INFO]    Call timeout     : 60s
[2025-03-30 14:22:01] [INFO]    Retry delay      : 3s
[2025-03-30 14:22:01] [INFO]    Max retries      : unlimited
[2025-03-30 14:22:01] [INFO]    Log file         : none
[2025-03-30 14:22:01] [INFO]    Dry-run          : False
[2025-03-30 14:22:01] [INFO]  ========================================
[2025-03-30 14:22:01] [INFO]  Attempt 1 -- dialing 039XXXXXXXX
[2025-03-30 14:22:18] [WARN]  Call ended -- auto-attendant (hung up at 17s)
[2025-03-30 14:22:18] [INFO]  Waiting 3s before next attempt
[2025-03-30 14:22:21] [INFO]  Attempt 2 -- dialing 039XXXXXXXX
[2025-03-30 14:22:58] [INFO]  Human answer confirmed after 37s. Call left active.
```

A progress bar is displayed in the terminal during active calls and retry delays.

---

## Exit Codes

| Code | Meaning |
|---|---|
| `0` | Human answer confirmed |
| `1` | Max retries reached without confirmed answer |

---

## Known Limitations

- Detection relies on `dumpsys telecom` state strings, which may vary across Android versions and manufacturer ROM customizations. If detection behaves unexpectedly, run `adb shell dumpsys telecom` manually during a live call to verify the exact state strings present on your device.
- The script does not handle multiple simultaneous ADB devices. If more than one device is connected, specify the target with `adb -s <serial>` by modifying the `Invoke-Adb` and `Get-CallState` functions.
- Call audio is not analyzed. Detection is state-based only; a very long auto-attendant (exceeding `ValidAfterSeconds`) will be misclassified as a human answer.

---

## License

MIT
