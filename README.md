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

### Step 2 — Update Paths in the Script

Open `pyltspice_workshop.py` and update the three path constants at the top of the file:

```python
LTSPICE_PATH   = r'C:\Program Files\ADI\LTspice\LTspice.exe'
SCHEMATIC_PATH = r'C:\Users\YourName\Documents\LTspice\YourSchematic.asc'
OUTPUT_FOLDER  = r'C:\Users\YourName\Downloads\rc_sweep_output'
```

To verify your LTSpice path is correct, run the following in PowerShell:

```powershell
Test-Path "C:\Program Files\ADI\LTspice\LTspice.exe"
```

This should return `True`. If it returns `False`, find the correct path and update the script.

### Step 3 — Run the Script

```
python pyltspice_workshop.py
```

The script runs all three use cases in sequence. Output files (plots and schematics) are saved to `OUTPUT_FOLDER`.

---

## The Three Use Cases

---

### Use Case 1 — Parameter Sweep

Run the same circuit with different R and C values and overlay all the Bode plots for direct comparison. This is the most common use of PyLTSpice and a natural extension of what you already do manually in LTSpice.

**What it does:**
- Defines a list of R values and a list of C values
- Generates every R+C combination (e.g. 3 R values × 3 C values = 9 simulations)
- Runs each simulation, reads the .raw output, and plots magnitude and phase
- Color-codes each curve and marks the theoretical -3 dB cutoff with a dashed vertical line

**Key concept — the combination loop:**

```python
combinations = [(R, C) for R in R_VALUES for C in C_VALUES]
# Creates every pair, e.g. [(15k, 6.8n), (15k, 15n), (15k, 22n), ...]
```

Output file: `uc1_sweep.png`

---

### Use Case 2 — AC Analysis & Custom Matplotlib Plotting

Run a single simulation and build a polished, annotated Bode plot. This use case focuses on what you can do with the data after the simulation runs — going well beyond LTSpice's built-in waveform viewer.

**What it does:**
- Simulates at the target design point (15 kΩ, 6.8 nF → fc ≈ 1560 Hz)
- Overlays the theoretical response curve alongside the simulated data
- Annotates the -3 dB point, cutoff frequency, and -20 dB/decade slope with arrows
- Marks -45° phase at fc as a sanity check

**Key concept — complex-valued AC data:**

```python
vout   = ltr.get_trace('V(out)').get_wave(0)   # complex array
mag_db = 20 * np.log10(np.abs(vout))            # magnitude in dB
phase  = np.angle(vout, deg=True)               # phase in degrees
```

LTSpice stores AC voltages as complex numbers. The magnitude gives you gain, the angle gives you phase shift. NumPy handles both with one line each.

Output file: `uc2_ac_analysis.png`

---

### Use Case 3 — Monte Carlo / Tolerance Analysis

Real resistors and capacitors are not exactly their labeled value. A 15 kΩ resistor with ±5% tolerance could be anywhere from 14.25 kΩ to 15.75 kΩ. This use case simulates that variation across many random samples so you can see how manufacturing tolerances affect your circuit.

**What it does:**
- Randomly samples R and C values within their tolerance band (default ±5%)
- Runs a simulation for each sample (default 30 samples)
- Plots all curves as faint transparent lines with the nominal design in bold red
- Displays a statistics box with mean, standard deviation, min, and max cutoff frequency
- Generates a histogram of the cutoff frequency distribution as a bonus plot

**Key concept — random sampling with NumPy:**

```python
R_samples = np.random.uniform(
    R_nom * (1 - R_tolerance),   # lower bound
    R_nom * (1 + R_tolerance),   # upper bound
    N_SAMPLES                     # number of draws
)
```

> **What to look for in the Monte Carlo output:**
> - If the spread of fc values is narrow, your design is robust to component variation.
> - If the spread is wide, consider using tighter tolerance components (±1% instead of ±5%).
> - The histogram shows whether the distribution is centered on your target fc.

Output files: `uc3_monte_carlo.png`, `uc3_histogram.png`

---

## Imports Reference

| Import | What it does |
|--------|-------------|
| `numpy (np)` | Math and arrays. Used for dB conversion, phase calculation, and random sampling. |
| `matplotlib.pyplot (plt)` | Creates figures, axes, and all plot elements — lines, labels, annotations. |
| `matplotlib.cm (cm)` | Provides color maps. tab10 assigns a unique color to each sweep curve. |
| `PyLTSpice.LTspice` | Runs LTSpice headlessly from Python via `LTspice.run()`. |
| `PyLTSpice.RawRead` | Reads and parses the binary .raw file LTSpice generates after each simulation. |
| `PyLTSpice.SpiceEditor` | Opens your .asc schematic and lets you modify .param values programmatically. |
| `os` | Creates the output folder and checks whether files exist. |
| `shutil` | Copies your schematic for each iteration so the original is never modified. |
| `subprocess` | Launches LTSpice as an external process to open the schematic after the sweep. |

---

## Output Files

All output is saved to `OUTPUT_FOLDER`. After the script runs you will find:

| File | Description |
|------|-------------|
| `uc1_sweep.png` | Overlaid Bode plots for all R/C combinations from Use Case 1 |
| `uc2_ac_analysis.png` | Annotated single-design Bode plot from Use Case 2 |
| `uc3_monte_carlo.png` | Monte Carlo Bode plot overlay from Use Case 3 |
| `uc3_histogram.png` | Histogram of cutoff frequency spread from Use Case 3 |
| `sweep_N.asc` | Modified schematic copies used for each Use Case 1 simulation |
| `uc2_ac.asc` | Modified schematic used for Use Case 2 |
| `mc_N.asc` | Modified schematic copies used for each Monte Carlo sample |
| `*.raw` | Binary simulation output files — readable by RawRead or LTSpice |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `FileNotFoundError` on .asc path | The `SCHEMATIC_PATH` is wrong. Use PowerShell `Get-ChildItem` to find your .asc file. |
| `IndexError: doesn't contain trace V(out)` | Your node is named differently. Check valid trace names printed in the error and update the `get_trace()` call to match. |
| No .raw file found | LTSpice failed silently. Open the .asc file manually in LTSpice and check for netlist errors. |
| Could not open LTSpice | `LTSPICE_PATH` is wrong. Run `Test-Path` in PowerShell to verify the exe location. |
| LTSpice GUI opens instead of running | Some versions require a `-b` (batch) flag. Wrap the run call: `subprocess.run([LTSPICE_PATH, '-b', asc_path])`. |
| `{R}` or `{C}` not found by SpiceEditor | Your .asc must have a `.param R=...` and `.param C=...` directive on the canvas. Add them in LTSpice via Edit > SPICE Directive. |

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

### Useful PyLTSpice Patterns

```python
# Read all available trace names
ltr = RawRead(raw_path)
print([t.name for t in ltr._plots[0]._trace_info])

# Get frequency axis
freq = np.array(ltr.get_trace('frequency').get_wave(0)).real

# Get output voltage (complex)
vout = np.array(ltr.get_trace('V(out)').get_wave(0))

# Convert to dB and degrees
mag_db = 20 * np.log10(np.abs(vout))
phase  = np.angle(vout, deg=True)
```
