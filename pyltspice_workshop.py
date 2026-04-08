"""
================================================================================
PyLTSpice Workshop — 3 Core Use Cases
================================================================================
This script automates LTSpice simulations entirely from Python.
Instead of manually adjusting component values and re-running simulations
through the LTSpice GUI, we script the whole process:

    1. Copy the base schematic
    2. Inject new component values by editing the .asc file directly
    3. Run LTSpice in batch mode (no GUI) using subprocess
    4. Read the binary .raw output file using PyLTSpice's RawRead
    5. Plot magnitude and phase using Matplotlib

USE CASE 1 — Parameter Sweep
    Run the same circuit with many R/C combinations and compare all Bode plots.

USE CASE 2 — AC Analysis & Custom Plotting
    Single simulation with an annotated, publication-quality Bode plot.
    Overlays the theoretical response against the simulated data.

USE CASE 3 — Monte Carlo / Tolerance Analysis
    Randomly vary R and C within ±5% to simulate real component tolerances.
    Shows how manufacturing variation affects your circuit's cutoff frequency.

Requirements:
    pip install PyLTSpice matplotlib numpy

LTSpice must be installed. Update the CONFIG section below before running.
================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
import os
import shutil
import subprocess
import time
import re

# RawRead: PyLTSpice class that parses the binary .raw file LTSpice generates.
# It lets us extract traces like V(out) and frequency as NumPy arrays.
from PyLTSpice import RawRead


# ────────────────────────────────────────────────────────────────
# USER CONFIGURATION (EDIT THESE FIRST)
# ────────────────────────────────────────────────────────────────

# Full path to the LTSpice executable on your machine.
# To verify this is correct, run in PowerShell:
#     Test-Path "C:\Program Files\ADI\LTspice\LTspice.exe"
# Should return True.
LTSPICE_PATH = r"C:\Program Files\ADI\LTspice\LTspice.exe"

# Path to your base schematic (.asc file).
# This file must have:
#   - {R} as the resistor value
#   - {C} as the capacitor value
#   - .param R=<value> C=<value> directive on the canvas
#   - .ac dec 100 10 1000000 directive on the canvas
#   - AC 1 on your voltage source
SCHEMATIC_PATH = r"C:\Users\lizab\OneDrive\Documents\LTspice\Draft16.asc"

# All generated .asc, .raw, and .png files will be saved here.
# The folder is created automatically if it doesn't exist.
OUTPUT_FOLDER = r"C:\Users\lizab\Downloads\rc_sweep_output"

# The node name to measure in the simulation.
# This must match the label in your schematic exactly.
# If your node is labeled "Vout", change this to "Vout".
# The script looks for V(NODE_NAME) in the .raw file.
NODE_NAME = "out"

# Set any of these to False to skip that use case.
RUN_UC1 = True
RUN_UC2 = True
RUN_UC3 = True


# ────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────────────────────

def cutoff_hz(R, C):
    """
    Calculate the theoretical -3 dB cutoff frequency of an RC low-pass filter.

    Formula: fc = 1 / (2 * pi * R * C)

    This is the frequency at which:
      - Magnitude drops to -3 dB (about 70.7% of DC gain)
      - Phase shift is exactly -45 degrees
    """
    return 1.0 / (2 * np.pi * R * C)


def wait_for_file(path, timeout=10):
    """
    Poll until a file exists on disk, up to a timeout.

    Why this is needed:
        LTSpice runs as a separate process. When subprocess.run() returns,
        LTSpice has finished, but the .raw file may not be fully flushed to
        disk yet. This loop checks every 100ms until the file appears.

    Args:
        path:    Full path to the file to wait for.
        timeout: Maximum seconds to wait before raising TimeoutError.
    """
    start = time.time()
    while not os.path.exists(path):
        if time.time() - start > timeout:
            raise TimeoutError(
                f"Timed out waiting for {path}. "
                "LTSpice may have failed — check the .log file in the output folder."
            )
        time.sleep(0.1)


def run_simulation(R, C, filename):
    """
    Run a single LTSpice AC simulation with specified R and C values.

    How it works:
        1. Copy the base schematic to a new file so we never modify the original.
        2. Use regex to find the .param line and replace R and C values.
           LTSpice .asc files store SPICE directives as:
               TEXT x y Left 2 !.param R=1k C=10n
           So we can't use a simple line replace — we need regex to handle
           the variable prefix before the .param keyword.
        3. Run LTSpice in batch mode with:
               -b     = batch mode (suppresses GUI)
               -Run   = start simulation immediately on launch
               timeout= kill the process if it hangs for more than 30 seconds
        4. Wait for the .raw file to appear and return its path.

    Args:
        R:        Resistance in ohms (e.g. 15000.0 for 15 kΩ)
        C:        Capacitance in farads (e.g. 6.8e-9 for 6.8 nF)
        filename: Name for the copied schematic file (e.g. "sweep_0.asc")

    Returns:
        Path to the generated .raw file.
    """
    # Build the full path for the copied schematic
    asc_path = os.path.join(OUTPUT_FOLDER, filename)

    # Copy the original schematic — we edit the copy, not the original
    shutil.copy(SCHEMATIC_PATH, asc_path)

    # Read the entire schematic as a plain text string
    with open(asc_path, "r") as f:
        content = f.read()

    # Verify the .param line exists before trying to replace it
    param_lines = [l for l in content.splitlines() if 'param' in l.lower()]
    if not param_lines:
        raise ValueError(
            "No .param line found in schematic.\n"
            "In LTSpice: Edit > SPICE Directive and add:  .param R=1k C=10n"
        )

    # Use regex to replace the .param R=... C=... values.
    #
    # Why regex instead of a simple string replace?
    # The .asc file stores the directive as:
    #     TEXT -56 296 Left 2 !.param R=10k C=10n
    # A simple replace on ".param R=10k C=10n" would work for that exact string,
    # but regex lets us handle any value already in the file (e.g. "15000.0", "6.8e-9").
    #
    # Pattern breakdown:
    #   (\.param\s+R=)   captures ".param R=" — we keep this part
    #   \S+              matches the current R value (any non-whitespace) — replaced
    #   (\s+C=)          captures the whitespace and "C=" — we keep this part
    #   \S+              matches the current C value — replaced
    content = re.sub(
        r'(\.param\s+R=)\S+(\s+C=)\S+',
        lambda m: m.group(1) + str(R) + m.group(2) + str(C),
        content,
        flags=re.IGNORECASE
    )

    # Write the modified schematic back to the file
    with open(asc_path, "w") as f:
        f.write(content)

    # Run LTSpice in batch mode.
    #
    # Flags:
    #   -b     batch mode — suppresses the GUI entirely
    #   -Run   tells LTSpice to start the simulation immediately
    #          (required for newer ADI LTSpice versions; without it the
    #           process hangs waiting for user input even in batch mode)
    #
    # check=True  raises an exception if LTSpice returns a non-zero exit code
    # timeout=30  kills the process if it takes longer than 30 seconds
    #             (prevents infinite hangs if something goes wrong)
    subprocess.run([LTSPICE_PATH, "-b", "-Run", asc_path], check=True, timeout=30)

    # The .raw file is always written next to the .asc file with the same base name
    raw_path = asc_path.replace(".asc", ".raw")

    # Wait until the file is fully written to disk
    wait_for_file(raw_path)

    return raw_path


def read_ac_results(raw_path):
    """
    Parse a LTSpice .raw file and return frequency, magnitude, and phase arrays.

    LTSpice AC analysis stores all voltages as COMPLEX numbers:
        V(f) = real + j*imag

    To get the Bode plot values we need:
        Magnitude (dB) = 20 * log10( |V| )      where |V| = sqrt(real² + imag²)
        Phase (degrees) = atan2(imag, real) * (180/pi)

    NumPy handles both with np.abs() and np.angle().

    Args:
        raw_path: Path to the .raw file generated by LTSpice.

    Returns:
        freq:   1D array of frequency points in Hz
        mag_db: 1D array of magnitude in dB
        phase:  1D array of phase in degrees
    """
    # RawRead parses the binary .raw file format
    ltr = RawRead(raw_path)

    # Get the list of all available signal names in this simulation
    traces = ltr.get_trace_names()
    target = f"V({NODE_NAME})"

    # If the target node isn't found, print what IS available so the user
    # can update NODE_NAME to match
    if target not in traces:
        raise ValueError(
            f"Node '{target}' not found in simulation output.\n"
            f"Available traces: {traces}\n"
            f"Update NODE_NAME at the top of the script to match your schematic."
        )

    # Extract the frequency axis — .real strips the tiny imaginary component
    # that RawRead sometimes attaches to the frequency trace
    freq = np.array(ltr.get_trace("frequency").get_wave(0)).real

    # Extract the complex output voltage at each frequency point
    vout = np.array(ltr.get_trace(target).get_wave(0))

    # Convert complex voltage to magnitude in dB
    # np.abs() computes the magnitude: sqrt(real² + imag²)
    # 20 * log10 converts to decibels
    mag_db = 20 * np.log10(np.abs(vout))

    # Convert complex voltage to phase in degrees
    # np.angle() computes atan2(imag, real) in radians; deg=True converts to degrees
    phase = np.angle(vout, deg=True)

    return freq, mag_db, phase


def find_fc(freq, mag_db):
    """
    Estimate the -3 dB cutoff frequency from simulation data.

    We find the index where the magnitude is closest to -3 dB,
    then return the corresponding frequency.

    Note: This is an approximation based on the simulation's frequency
    resolution. The theoretical fc = 1/(2πRC) is more precise.

    Args:
        freq:   Frequency array in Hz
        mag_db: Magnitude array in dB

    Returns:
        Estimated cutoff frequency in Hz
    """
    # np.argmin finds the index of the minimum value
    # np.abs(mag_db + 3) finds where magnitude is closest to -3 dB
    idx = np.argmin(np.abs(mag_db + 3))
    return freq[idx]


def save_csv(freq, mag, phase, filename):
    """
    Save simulation results to a CSV file.

    Useful for importing into Excel, MATLAB, or other analysis tools.
    The file will have a header row and three columns: freq, mag_db, phase.

    Args:
        freq:     Frequency array in Hz
        mag:      Magnitude array in dB
        phase:    Phase array in degrees
        filename: Full path to save the CSV file
    """
    np.savetxt(
        filename,
        np.column_stack([freq, mag, phase]),   # stack into 3-column array
        delimiter=",",
        header="freq,mag_db,phase",
        comments=""    # suppress the default # prefix on the header line
    )


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 1 — PARAMETER SWEEP
# ══════════════════════════════════════════════════════════════════════════════
#
# Runs the RC filter simulation for every combination of R and C values,
# then overlays all the Bode plots on one figure.
#
# This is the most common use of PyLTSpice — instead of manually changing
# a component value and re-running in the GUI, you define the sweep in Python
# and let the script handle everything.
#
# With 3 R values and 3 C values, this runs 9 simulations automatically.

def use_case_1():
    print("\n=== USE CASE 1: Parameter Sweep ===")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # ── Define sweep values ───────────────────────────────────────────────────
    # These are the R and C values to sweep.
    # Every combination will be simulated (3 x 3 = 9 total).
    R_VALUES = [15e3, 6.8e3, 4.7e3]    # ohms: 15kΩ, 6.8kΩ, 4.7kΩ
    C_VALUES = [6.8e-9, 15e-9, 22e-9]  # farads: 6.8nF, 15nF, 22nF

    # List comprehension builds every (R, C) pair
    # e.g. [(15k, 6.8n), (15k, 15n), (15k, 22n), (6.8k, 6.8n), ...]
    combos = [(R, C) for R in R_VALUES for C in C_VALUES]

    # ── Set up figure ─────────────────────────────────────────────────────────
    # Two stacked subplots sharing the same x-axis (frequency)
    fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax_mag.set_title("USE CASE 1 — Parameter Sweep: RC Low-Pass Filter", fontsize=13)

    # ── Simulate and plot each combination ───────────────────────────────────
    for i, (R, C) in enumerate(combos):
        print(f"  Simulating R={R/1e3:.1f}kΩ, C={C*1e9:.1f}nF ...")

        # Run the simulation — returns path to .raw file
        raw = run_simulation(R, C, f"sweep_{i}.asc")

        # Parse the .raw file to get frequency, magnitude, and phase arrays
        freq, mag, phase = read_ac_results(raw)

        # Find the -3 dB frequency from the simulation data
        fc_meas = find_fc(freq, mag)

        # Build a descriptive label for the legend
        label = f"R={R/1e3:.1f}kΩ, C={C*1e9:.0f}nF  (fc={fc_meas:.0f} Hz)"

        # semilogx plots with a logarithmic x-axis (required for Bode plots)
        ax_mag.semilogx(freq, mag, label=label)
        ax_phase.semilogx(freq, phase)

    # ── Format the magnitude plot ─────────────────────────────────────────────
    ax_mag.axhline(-3, color="gray", linestyle=":", linewidth=1, label="-3 dB")
    ax_mag.set_ylabel("Magnitude (dB)")
    ax_mag.set_ylim(-50, 5)
    ax_mag.grid(True, which="both", alpha=0.3)   # "both" = major and minor gridlines
    ax_mag.legend(fontsize=7, loc="lower left")

    # ── Format the phase plot ─────────────────────────────────────────────────
    ax_phase.set_ylabel("Phase (°)")
    ax_phase.set_xlabel("Frequency (Hz)")
    ax_phase.set_ylim(-100, 10)
    ax_phase.grid(True, which="both", alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc1_sweep.png"), dpi=150)
    plt.show()
    print("  Done. Plot saved to uc1_sweep.png")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 2 — SINGLE AC ANALYSIS & CUSTOM PLOTTING
# ══════════════════════════════════════════════════════════════════════════════
#
# Runs a single simulation at the target design point and builds a polished,
# annotated Bode plot — going beyond what LTSpice's waveform viewer can do.
#
# Key additions over Use Case 1:
#   - Theoretical response curve overlaid on the simulated data
#   - Annotated fc point with arrow
#   - -45° phase marker
#   - CSV export for use in Excel or MATLAB

def use_case_2():
    print("\n=== USE CASE 2: AC Analysis ===")

    # ── Design point ──────────────────────────────────────────────────────────
    # These values hit fc ≈ 1560 Hz, within 0.28% of the 1556 Hz target
    R, C = 15e3, 6.8e-9
    fc_theory = cutoff_hz(R, C)
    print(f"  Simulating R={R/1e3:.0f}kΩ, C={C*1e9:.1f}nF → fc={fc_theory:.1f} Hz")

    # Run simulation and read results
    raw = run_simulation(R, C, "uc2.asc")
    freq, mag, phase = read_ac_results(raw)

    # Find fc from simulation data (should match fc_theory closely)
    fc = find_fc(freq, mag)

    # ── Build theoretical curves ──────────────────────────────────────────────
    # Generate a smooth frequency array for the theoretical curves
    f_theory = np.logspace(1, 6, 500)   # 500 points from 10 Hz to 1 MHz

    # Theoretical magnitude: H(f) = 1 / sqrt(1 + (f/fc)²)  →  in dB:
    mag_theory = -10 * np.log10(1 + (f_theory / fc_theory)**2)

    # Theoretical phase: φ(f) = -arctan(f/fc)
    phase_theory = -np.degrees(np.arctan(f_theory / fc_theory))

    # ── Set up figure ─────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(
        f"USE CASE 2 — AC Analysis  |  R={R/1e3:.0f}kΩ, C={C*1e9:.1f}nF  |  fc={fc:.0f} Hz",
        fontsize=12
    )

    # ── Magnitude plot ────────────────────────────────────────────────────────
    ax1.semilogx(freq, mag, color="steelblue", linewidth=2, label="Simulated")
    ax1.semilogx(f_theory, mag_theory, color="orange", linewidth=1.5,
                 linestyle="--", label="Theoretical")

    # Vertical dashed line at fc
    ax1.axvline(fc, color="red", linestyle="--", linewidth=1, alpha=0.7)

    # Horizontal dashed line at -3 dB
    ax1.axhline(-3, color="gray", linestyle=":", linewidth=1)

    # Annotate the fc point with an arrow
    ax1.annotate(
        f"fc = {fc:.0f} Hz\n-3 dB",
        xy=(fc, -3),                         # arrow tip: at the -3 dB crossing
        xytext=(fc * 3, -10),                # label position: 3x fc, -10 dB
        arrowprops=dict(arrowstyle="->", color="red"),
        color="red", fontsize=9
    )

    ax1.set_ylabel("Magnitude (dB)")
    ax1.set_ylim(-60, 5)
    ax1.grid(True, which="both", alpha=0.3)
    ax1.legend(fontsize=9)

    # ── Phase plot ────────────────────────────────────────────────────────────
    ax2.semilogx(freq, phase, color="steelblue", linewidth=2, label="Simulated")
    ax2.semilogx(f_theory, phase_theory, color="orange", linewidth=1.5,
                 linestyle="--", label="Theoretical")

    # At fc, phase should be exactly -45° — good sanity check
    ax2.axhline(-45, color="gray", linestyle=":", linewidth=1)
    ax2.axvline(fc, color="red", linestyle="--", linewidth=1, alpha=0.7)

    ax2.set_ylabel("Phase (°)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylim(-100, 10)
    ax2.grid(True, which="both", alpha=0.3)
    ax2.legend(fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc2_ac_analysis.png"), dpi=150)

    # Save raw data to CSV — useful for lab reports or further analysis
    save_csv(freq, mag, phase, os.path.join(OUTPUT_FOLDER, "uc2.csv"))

    plt.show()
    print("  Done. Plot saved to uc2_ac_analysis.png, data saved to uc2.csv")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 3 — MONTE CARLO / TOLERANCE ANALYSIS
# ══════════════════════════════════════════════════════════════════════════════
#
# Real components have tolerances. A "15kΩ" resistor with ±5% tolerance could
# be anywhere from 14.25kΩ to 15.75kΩ. This use case randomly samples R and C
# within their tolerance bands and runs a separate simulation for each sample.
#
# The spread of the resulting curves shows how much your circuit's behavior
# varies due to manufacturing tolerances — a key consideration in real design.
#
# Output:
#   - Overlay of all Monte Carlo curves (faint blue) + nominal (bold red)
#   - Min/max envelope shaded in blue
#   - Statistics box: mean, std, min, max cutoff frequency
#   - Bonus histogram of the cutoff frequency distribution

def use_case_3():
    print("\n=== USE CASE 3: Monte Carlo ===")

    # ── Configuration ─────────────────────────────────────────────────────────
    R_nom, C_nom = 15e3, 6.8e-9  # nominal (ideal) component values
    tol = 0.05                    # tolerance as a fraction (0.05 = ±5%)
    N = 30                        # number of random samples to simulate

    # Seed the random number generator for reproducibility.
    # Using the same seed means you get the same random values every run,
    # making results comparable across sessions.
    np.random.seed(42)

    # ── Generate random component values ──────────────────────────────────────
    # np.random.uniform(low, high, N) draws N values uniformly between low and high.
    # Multiplying nominal by (1 ± tol) sets the tolerance band.
    Rs = np.random.uniform(R_nom * (1 - tol), R_nom * (1 + tol), N)
    Cs = np.random.uniform(C_nom * (1 - tol), C_nom * (1 + tol), N)

    # Storage for results
    all_mag = []
    fc_list = []

    # ── Set up figure ─────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(
        f"USE CASE 3 — Monte Carlo  |  R={R_nom/1e3:.0f}kΩ ±{tol*100:.0f}%,"
        f"  C={C_nom*1e9:.1f}nF ±{tol*100:.0f}%  ({N} samples)",
        fontsize=11
    )

    # ── Simulate each random sample ───────────────────────────────────────────
    for i, (R, C) in enumerate(zip(Rs, Cs)):
        print(f"  Sample {i+1}/{N}: R={R/1e3:.2f}kΩ, C={C*1e9:.2f}nF")

        raw = run_simulation(R, C, f"mc_{i}.asc")
        freq, mag, phase = read_ac_results(raw)

        # Store magnitude for envelope calculation later
        all_mag.append(mag)

        # Store measured fc for statistics
        fc_list.append(find_fc(freq, mag))

        # Plot each sample as a faint, thin line
        # alpha=0.3 makes lines semi-transparent so overlaps are visible
        ax1.semilogx(freq, mag, color="steelblue", alpha=0.3, linewidth=0.8)
        ax2.semilogx(freq, phase, color="steelblue", alpha=0.3, linewidth=0.8)

    # ── Overlay the nominal (ideal) response ──────────────────────────────────
    # This shows where the circuit SHOULD be, centered in the spread
    raw_nom = run_simulation(R_nom, C_nom, "mc_nominal.asc")
    freq_n, mag_n, phase_n = read_ac_results(raw_nom)
    fc_nom = find_fc(freq_n, mag_n)

    ax1.semilogx(freq_n, mag_n, color="red", linewidth=2.5,
                 label=f"Nominal (fc={fc_nom:.0f} Hz)", zorder=5)
    ax2.semilogx(freq_n, phase_n, color="red", linewidth=2.5,
                 label="Nominal", zorder=5)

    # ── Shaded envelope (min/max bounds across all samples) ───────────────────
    # np.array converts the list of 1D arrays into a 2D array (N x freq_points)
    # .min(0) and .max(0) collapse along axis 0 to get the min/max at each frequency
    all_mag = np.array(all_mag)
    ax1.fill_between(
        freq,
        all_mag.min(0),   # lower bound at each frequency
        all_mag.max(0),   # upper bound at each frequency
        alpha=0.15, color="steelblue", label="Min/Max envelope"
    )

    # ── Statistics box ────────────────────────────────────────────────────────
    fc_arr = np.array(fc_list)
    stats = (
        f"fc stats ({N} samples)\n"
        f"Mean:  {np.mean(fc_arr):.0f} Hz\n"
        f"Std:   {np.std(fc_arr):.0f} Hz\n"
        f"Min:   {np.min(fc_arr):.0f} Hz\n"
        f"Max:   {np.max(fc_arr):.0f} Hz"
    )
    # Place the box in the upper-right corner of the magnitude plot
    ax1.text(
        0.98, 0.95, stats,
        transform=ax1.transAxes,   # coordinates relative to axes (0-1)
        fontsize=8,
        verticalalignment="top", horizontalalignment="right",
        bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8)
    )

    # ── Format plots ──────────────────────────────────────────────────────────
    ax1.axhline(-3, color="gray", linestyle=":", linewidth=1)
    ax1.set_ylabel("Magnitude (dB)")
    ax1.set_ylim(-50, 5)
    ax1.grid(True, which="both", alpha=0.3)
    ax1.legend(fontsize=8)

    ax2.set_ylabel("Phase (°)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylim(-100, 10)
    ax2.grid(True, which="both", alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc3_monte_carlo.png"), dpi=150)
    plt.show()

    # ── Bonus: histogram of fc spread ─────────────────────────────────────────
    # This gives an intuitive view of how much fc varies across the 30 samples.
    # A tight histogram means your design is robust to component variation.
    # A wide histogram means you may need tighter tolerance components.
    fig2, ax_hist = plt.subplots(figsize=(7, 4))
    ax_hist.hist(fc_arr, bins=10, color="steelblue", edgecolor="white", alpha=0.85)
    ax_hist.axvline(np.mean(fc_arr), color="red", linestyle="--", linewidth=1.5,
                    label=f"Mean = {np.mean(fc_arr):.0f} Hz")
    ax_hist.axvline(fc_nom, color="orange", linestyle="--", linewidth=1.5,
                    label=f"Nominal = {fc_nom:.0f} Hz")
    ax_hist.set_xlabel("Cutoff Frequency (Hz)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title(f"fc Distribution — ±{tol*100:.0f}% Tolerance ({N} samples)")
    ax_hist.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc3_histogram.png"), dpi=150)
    plt.show()

    print(f"  Done. fc mean={np.mean(fc_arr):.0f} Hz, std={np.std(fc_arr):.0f} Hz")
    print("  Plots saved to uc3_monte_carlo.png and uc3_histogram.png")


# ────────────────────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────────────────────
# Each use case runs sequentially. plt.show() pauses at each plot —
# close the window to continue to the next use case.

if __name__ == "__main__":
    if RUN_UC1:
        use_case_1()

    if RUN_UC2:
        use_case_2()

    if RUN_UC3:
        use_case_3()
