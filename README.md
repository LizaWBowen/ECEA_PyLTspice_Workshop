# PyLTSpice Workshop
**Automating LTSpice Simulations with Python**

---

## Overview

This workshop teaches you how to control LTSpice from Python using the PyLTSpice library. Instead of manually adjusting component values and re-running simulations through the GUI, you will write scripts that automate the entire process — from editing schematics to parsing results and generating plots.

By the end of the workshop you will be able to:

- Run LTSpice simulations headlessly from a Python script
- Sweep component values across multiple combinations automatically
- Extract and plot simulation data using Matplotlib
- Perform Monte Carlo tolerance analysis to understand real-world component variation

---

## Prerequisites

### Software

| Software | Notes |
|----------|-------|
| LTSpice | Latest version from Analog Devices (ADI). Free download at analog.com/ltspice |
| Python 3.10+ | Download at python.org. Python 3.13 confirmed working. |
| VS Code | Recommended editor. Any editor works. |
| pip | Included with Python. Used to install PyLTSpice and plotting libraries. |

### Python Packages

Install all required packages before the workshop with:

```
pip install PyLTSpice matplotlib numpy
```

### Knowledge

- Basic Python — variables, functions, loops, imports
- Basic circuit theory — RC filters, Bode plots, cutoff frequency
- Familiarity with LTSpice GUI (drawing schematics, running .ac simulations)

If you want to learn more about pyltspice, this is their documentation
-  https://pyltspice.readthedocs.io/en/latest/

---

## Setup

### Step 1 — Build the Base Schematic

Before running any scripts, you need an LTSpice schematic (.asc file) with parameterized component values. The scripts modify these parameters for each simulation run.

Draw a simple RC low-pass filter in LTSpice with the following settings:

| Element | Value / Setting |
|---------|----------------|
| V1 (voltage source) | Set AC amplitude to 1  (AC 1) |
| R1 (resistor) | Set value to `{R}` — curly braces required |
| C1 (capacitor) | Set value to `{C}` — curly braces required |
| .param directive | Add `.param R=15k C=6.8n` to the canvas |
| .ac directive | Add `.ac dec 100 10 1000000` to the canvas |

> **Why curly braces?**
> In LTSpice schematics, `{R}` tells LTSpice to look up the value of parameter R from a `.param` directive. Without curly braces, LTSpice treats the letter R as an unknown and the simulation fails. In raw netlists (.net files), no curly braces are needed — plain R and C work directly.

> **Important:** Make sure the `.param` line has both R and C on the **same line**, e.g. `.param R=15k C=6.8n`. The script's regex expects them on one line. Add it via Edit > SPICE Directive in LTSpice.

### Step 2 — Update Paths in the Script

Open `LTSpice_Python_Workshop.py` and update the config constants at the top:

```python
LTSPICE_PATH   = r'C:\Program Files\ADI\LTspice\LTspice.exe'
SCHEMATIC_PATH = r'C:\Users\YourName\Documents\LTspice\YourSchematic.asc'
OUTPUT_FOLDER  = r'C:\Users\YourName\Downloads\rc_sweep_output'
NODE_NAME      = "out"   # must match your schematic node label exactly
```

To verify your LTSpice path is correct, run the following in PowerShell:

```powershell
Test-Path "C:\Program Files\ADI\LTspice\LTspice.exe"
```

This should return `True`. If it returns `False`, find the correct path and update the script.

### Step 3 — Run the Script

```
python LTSpice_Python_Workshop.py
```

Each use case runs sequentially. A plot window will appear after each one — **close it to continue to the next use case.**

---

## The Three Use Cases

---

### Use Case 1 — Parameter Sweep

Run the same circuit with different R and C values and overlay all the Bode plots for direct comparison.

**What it does:**
- Defines a list of R values and a list of C values
- Generates every R+C combination (3 × 3 = 9 simulations)
- Runs each simulation, reads the .raw output, and plots magnitude and phase
- Labels each curve with its R, C, and measured fc

**Key concept — the combination loop:**

```python
combinations = [(R, C) for R in R_VALUES for C in C_VALUES]
# Creates every pair, e.g. [(15k, 6.8n), (15k, 15n), (15k, 22n), ...]
```

Output file: `uc1_sweep.png`

---

### Use Case 2 — AC Analysis & Custom Matplotlib Plotting

Run a single simulation and build a polished, annotated Bode plot with a theoretical overlay.

**What it does:**
- Simulates at the target design point (15 kΩ, 6.8 nF → fc ≈ 1560 Hz)
- Overlays the theoretical response curve alongside the simulated data
- Annotates the -3 dB point and cutoff frequency with an arrow
- Marks -45° phase at fc as a sanity check
- Saves raw data to a CSV file

**Key concept — complex-valued AC data:**

```python
vout   = ltr.get_trace('V(out)').get_wave(0)   # complex array
mag_db = 20 * np.log10(np.abs(vout))            # magnitude in dB
phase  = np.angle(vout, deg=True)               # phase in degrees
```

Output files: `uc2_ac_analysis.png`, `uc2.csv`

---

### Use Case 3 — Monte Carlo / Tolerance Analysis

Simulate real component variation across 30 random samples to see how manufacturing tolerances affect your circuit.

**What it does:**
- Randomly samples R and C values within ±5% tolerance
- Runs a simulation for each sample
- Plots all curves as faint transparent lines with the nominal design in bold red
- Shades the min/max envelope across all samples
- Displays a statistics box with mean, std, min, and max cutoff frequency
- Generates a histogram of the cutoff frequency distribution

**Key concept — random sampling with NumPy:**

```python
R_samples = np.random.uniform(
    R_nom * (1 - tolerance),   # lower bound
    R_nom * (1 + tolerance),   # upper bound
    N_SAMPLES                   # number of draws
)
```

> **What to look for:**
> - Narrow spread → design is robust to component variation
> - Wide spread → consider tighter tolerance components (±1% instead of ±5%)
> - Histogram centered on target fc → nominal values are well chosen

Output files: `uc3_monte_carlo.png`, `uc3_histogram.png`

---

## How the Script Edits Schematics

LTSpice `.asc` files store SPICE directives as drawing commands in plain text:

```
TEXT -56 296 Left 2 !.param R=1k C=10n
```

The script uses Python's `re` module (regex) to find and replace the R and C values on this line directly — no GUI interaction needed:

```python
content = re.sub(
    r'(\.param\s+R=)\S+(\s+C=)\S+',
    lambda m: m.group(1) + str(R) + m.group(2) + str(C),
    content,
    flags=re.IGNORECASE
)
```

This approach is more reliable than PyLTSpice's `SpiceEditor` for the newer ADI LTSpice `.asc` format.

---

## How LTSpice is Launched

The script runs LTSpice in batch mode using Python's `subprocess` module:

```python
subprocess.run([LTSPICE_PATH, "-b", "-Run", asc_path], check=True, timeout=30)
```

| Flag | Meaning |
|------|---------|
| `-b` | Batch mode — suppresses the GUI entirely |
| `-Run` | Start simulation immediately on launch (required for newer ADI LTSpice) |
| `timeout=30` | Kill the process if it hangs for more than 30 seconds |

> **Note:** The `-Run` flag is required for newer ADI LTSpice versions. Without it, LTSpice launches but waits for user input even in batch mode, causing the script to hang indefinitely.

---

## Imports Reference

| Import | What it does |
|--------|-------------|
| `numpy (np)` | Math and arrays. Used for dB conversion, phase calculation, and random sampling. |
| `matplotlib.pyplot (plt)` | Creates figures, axes, and all plot elements — lines, labels, annotations. |
| `PyLTSpice.RawRead` | Reads and parses the binary .raw file LTSpice generates after each simulation. |
| `os` | Creates the output folder and builds file paths. |
| `shutil` | Copies your schematic for each iteration so the original is never modified. |
| `subprocess` | Launches LTSpice as an external process in batch mode. |
| `time` | Used by `wait_for_file()` to poll until the .raw file appears on disk. |
| `re` | Regular expressions — used to find and replace `.param` values in the .asc file. |

---

## Output Files

All output is saved to `OUTPUT_FOLDER`:

| File | Description |
|------|-------------|
| `uc1_sweep.png` | Overlaid Bode plots for all R/C combinations |
| `uc2_ac_analysis.png` | Annotated single-design Bode plot with theoretical overlay |
| `uc3_monte_carlo.png` | Monte Carlo Bode plot with envelope and stats box |
| `uc3_histogram.png` | Histogram of cutoff frequency spread |
| `uc2.csv` | Simulation data from Use Case 2 (freq, mag_dB, phase) |
| `sweep_N.asc` | Modified schematic copies for each Use Case 1 simulation |
| `uc2.asc` | Modified schematic for Use Case 2 |
| `mc_N.asc` / `mc_nominal.asc` | Modified schematics for each Monte Carlo sample |
| `*.raw` | Binary simulation output — readable by RawRead or LTSpice |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| Script hangs on first simulation | Missing `-Run` flag. Make sure your `subprocess.run` call includes `-Run`. |
| `FileNotFoundError` on .asc path | `SCHEMATIC_PATH` is wrong. Run `Get-ChildItem -Recurse -Filter "*.asc"` in PowerShell to find it. |
| `IndexError: doesn't contain trace V(out)` | `NODE_NAME` doesn't match your schematic. The error message prints valid trace names — update `NODE_NAME` to match. |
| No .raw file / TimeoutError | LTSpice failed silently. Open the .asc file manually in LTSpice and check for errors. Also check for a `.log` file in the output folder. |
| `Could not open LTSpice` | `LTSPICE_PATH` is wrong. Run `Test-Path "C:\..."` in PowerShell to verify. |
| `.param` line not being updated | Make sure R and C are on the **same** `.param` line: `.param R=1k C=10n`. Two separate lines won't be matched by the regex. |
| `check=True` raises `CalledProcessError` | LTSpice returned an error. Open the `.log` file in the output folder for details. |

---

## Quick Reference

### RC Filter Cutoff Frequency

```
fc = 1 / (2π R C)

Example: R = 15 kΩ, C = 6.8 nF
fc = 1 / (2π × 15000 × 0.0000000068) ≈ 1560 Hz

At fc:     magnitude = -3 dB,  phase = -45°
Above fc:  rolls off at -20 dB per decade
```

### Standard Value Combinations Near 1556 Hz

| R | C | fc | Error |
|---|---|----|-------|
| 15 kΩ | 6.8 nF | 1560 Hz | 0.28% |
| 6.8 kΩ | 15 nF | 1560 Hz | 0.28% |
| 4.7 kΩ | 22 nF | 1539 Hz | 1.08% |
| 10 kΩ | 10 nF | 1592 Hz | 2.28% |

### Useful PyLTSpice Patterns

```python
# Print all available trace names in a .raw file
ltr = RawRead(raw_path)
print(ltr.get_trace_names())

# Get frequency axis
freq = np.array(ltr.get_trace('frequency').get_wave(0)).real

# Get output voltage (complex)
vout = np.array(ltr.get_trace('V(out)').get_wave(0))

# Convert to dB and degrees
mag_db = 20 * np.log10(np.abs(vout))
phase  = np.angle(vout, deg=True)
```
