"""
================================================================================
PyLTSpice Workshop — 3 Core Use Cases
================================================================================
This script walks through three increasingly powerful ways to automate LTSpice
simulations using Python. Each use case builds on the previous one.

USE CASE 1 — Parameter Sweep
    Run the same circuit with different R/C values and compare Bode plots.
    Great for understanding how component values affect filter behavior.

USE CASE 2 — AC Analysis & Custom Matplotlib Plotting
    Extract raw simulation data and build publication-quality Bode plots.
    Shows how to work with complex-valued frequency data from LTSpice.

USE CASE 3 — Monte Carlo / Tolerance Analysis
    Simulate component variation (e.g. ±5% resistor tolerance) across many
    random samples to see how manufacturing spread affects your design.

Requirements:
    pip install PyLTSpice matplotlib numpy

LTSpice must be installed. Update the config paths below before running.
================================================================================
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from PyLTSpice import LTspice, RawRead, SpiceEditor
import os
import shutil

# ── Config — update these paths for your machine ─────────────────────────────

LTSPICE_PATH   = r"C:\Program Files\ADI\LTspice\LTspice.exe"
SCHEMATIC_PATH = r"C:\Users\lizab\OneDrive\Documents\LTspice\Draft16.asc"
OUTPUT_FOLDER  = r"C:\Users\lizab\Downloads\rc_sweep_output"

# ── Shared helper ─────────────────────────────────────────────────────────────

def cutoff_hz(R, C):
    """Calculate the theoretical -3dB cutoff frequency for an RC filter."""
    return 1.0 / (2 * np.pi * R * C)


def run_simulation(R, C, filename):
    """
    Copy the base schematic, inject R and C parameter values,
    run LTSpice headlessly, and return the path to the .raw output file.

    PyLTSpice's SpiceEditor finds the .param line in the .asc file and
    overwrites the value for the named parameter. This means your schematic
    must already have .param R=... and .param C=... directives in it.
    """
    # Make a copy of the schematic so we never modify the original
    asc_path = os.path.join(OUTPUT_FOLDER, filename)
    shutil.copy(SCHEMATIC_PATH, asc_path)

    # Open the copied schematic and update parameter values
    se = SpiceEditor(asc_path)
    se.set_parameter("R", R)   # overwrites .param R=<value>
    se.set_parameter("C", C)   # overwrites .param C=<value>
    se.save_netlist(asc_path)  # writes changes back to the .asc file

    # Run LTSpice in batch mode (no GUI) on the modified schematic.
    # LTSpice automatically creates a .raw file next to the .asc file.
    LTspice.run(asc_path)

    # Return the path to the .raw file LTSpice generated
    raw_path = asc_path.replace(".asc", ".raw")
    return raw_path


def read_ac_results(raw_path):
    """
    Read an LTSpice .raw file and return frequency, magnitude (dB), and phase.

    LTSpice AC analysis stores voltages as complex numbers — magnitude gives
    you the gain and angle gives you the phase shift at each frequency point.
    """
    ltr = RawRead(raw_path)

    # get_trace() returns a trace object; get_wave(0) returns the data array
    # .real strips the tiny imaginary component from the frequency axis
    freq = np.array(ltr.get_trace("frequency").get_wave(0)).real
    vout = np.array(ltr.get_trace("V(out)").get_wave(0))

    # Convert complex voltage to magnitude in dB and phase in degrees
    mag_db = 20 * np.log10(np.abs(vout))       # |V| → dB
    phase  = np.angle(vout, deg=True)           # complex angle → degrees

    return freq, mag_db, phase


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 1 — Parameter Sweep
# ══════════════════════════════════════════════════════════════════════════════
#
# Goal: run the same schematic multiple times with different R and C values,
# then overlay all the Bode plots so you can directly compare them.
#
# This is useful for:
#   - Finding which component values hit a target cutoff frequency
#   - Visualizing the tradeoff between R and C for the same fc
#   - Quickly generating design curves without touching the schematic

def use_case_1_parameter_sweep():
    print("\n=== USE CASE 1: Parameter Sweep ===")
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Define the values you want to sweep.
    # np.meshgrid / list comprehension creates every R+C combination.
    R_VALUES = [15e3, 6.8e3, 4.7e3]    # ohms
    C_VALUES = [6.8e-9, 15e-9, 22e-9]  # farads

    # Build all (R, C) pairs — this gives 3×3 = 9 combinations
    combinations = [(R, C) for R in R_VALUES for C in C_VALUES]
    n = len(combinations)

    # Assign a unique color to each combination for the plot
    colors = cm.tab10(np.linspace(0, 1, n))

    # Set up a figure with two stacked subplots sharing the same x-axis
    fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax_mag.set_title("USE CASE 1 — Parameter Sweep: RC Low-Pass Filter", fontsize=13)

    for idx, (R, C) in enumerate(combinations):
        print(f"  Simulating R={R/1e3:.1f}kΩ, C={C*1e9:.0f}nF ...")

        # Run the simulation and get the .raw file path
        raw_path = run_simulation(R, C, filename=f"sweep_{idx}.asc")

        if not os.path.exists(raw_path):
            print(f"  [!] Simulation failed — skipping")
            continue

        # Read frequency, magnitude, and phase from the .raw file
        freq, mag_db, phase = read_ac_results(raw_path)

        # Calculate the theoretical cutoff to annotate the plot
        fc = cutoff_hz(R, C)
        label = f"R={R/1e3:.1f}kΩ, C={C*1e9:.0f}nF  (fc={fc:.0f} Hz)"

        # Plot magnitude and phase curves
        ax_mag.semilogx(freq, mag_db, color=colors[idx], linewidth=1.8, label=label)
        ax_phase.semilogx(freq, phase, color=colors[idx], linewidth=1.8, label=label)

        # Add a dashed vertical line at the theoretical -3dB frequency
        ax_mag.axvline(fc, color=colors[idx], linestyle="--", linewidth=0.8, alpha=0.5)

    # Add a horizontal reference line at -3 dB
    ax_mag.axhline(-3, color="gray", linestyle=":", linewidth=1, label="-3 dB")

    # Format magnitude plot
    ax_mag.set_ylabel("Magnitude (dB)")
    ax_mag.set_ylim(-50, 5)
    ax_mag.grid(True, which="both", alpha=0.3)
    ax_mag.legend(fontsize=7, loc="lower left", ncol=2)

    # Format phase plot
    ax_phase.set_ylabel("Phase (°)")
    ax_phase.set_xlabel("Frequency (Hz)")
    ax_phase.set_ylim(-100, 10)
    ax_phase.grid(True, which="both", alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc1_sweep.png"), dpi=150)
    plt.show()
    print("  Done. Plot saved to uc1_sweep.png")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 2 — AC Analysis & Custom Matplotlib Plotting
# ══════════════════════════════════════════════════════════════════════════════
#
# Goal: run a single simulation and build a polished, annotated Bode plot
# that goes beyond what LTSpice's waveform viewer can produce.
#
# This is useful for:
#   - Lab reports and presentations
#   - Annotating key points (fc, -3dB, -20dB/dec slope)
#   - Overlaying a theoretical curve against simulated data

def use_case_2_ac_analysis():
    print("\n=== USE CASE 2: AC Analysis & Custom Plotting ===")
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Use the best values from our earlier search — hits 1556 Hz within 0.28%
    R = 15e3    # 15 kΩ
    C = 6.8e-9  # 6.8 nF
    fc = cutoff_hz(R, C)
    print(f"  Simulating R={R/1e3:.0f}kΩ, C={C*1e9:.1f}nF → fc={fc:.1f} Hz")

    raw_path = run_simulation(R, C, filename="uc2_ac.asc")

    if not os.path.exists(raw_path):
        print("  [!] Simulation failed.")
        return

    freq, mag_db, phase = read_ac_results(raw_path)

    # ── Build a polished annotated Bode plot ─────────────────────────────────

    fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(f"USE CASE 2 — AC Analysis  |  R={R/1e3:.0f}kΩ, C={C*1e9:.1f}nF  |  fc={fc:.0f} Hz",
                 fontsize=12)

    # ── Magnitude plot ────────────────────────────────────────────────────────

    ax_mag.semilogx(freq, mag_db, color="steelblue", linewidth=2, label="Simulated")

    # Overlay the ideal theoretical response: H(f) = 1 / sqrt(1 + (f/fc)^2)
    f_theory = np.logspace(1, 6, 500)
    mag_theory = -10 * np.log10(1 + (f_theory / fc)**2)  # in dB
    ax_mag.semilogx(f_theory, mag_theory, color="orange", linewidth=1.5,
                    linestyle="--", label="Theoretical")

    # Mark the -3 dB point with a dot and annotation
    ax_mag.axhline(-3, color="gray", linestyle=":", linewidth=1)
    ax_mag.axvline(fc, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax_mag.annotate(f"fc = {fc:.0f} Hz\n-3 dB",
                    xy=(fc, -3), xytext=(fc * 3, -10),
                    arrowprops=dict(arrowstyle="->", color="red"),
                    color="red", fontsize=9)

    # Annotate the -20 dB/decade rolloff slope in the stopband
    ax_mag.annotate("-20 dB/decade", xy=(fc * 10, -23), fontsize=9,
                    color="steelblue", style="italic")

    ax_mag.set_ylabel("Magnitude (dB)")
    ax_mag.set_ylim(-60, 5)
    ax_mag.grid(True, which="both", alpha=0.3)
    ax_mag.legend(fontsize=9)

    # ── Phase plot ────────────────────────────────────────────────────────────

    ax_phase.semilogx(freq, phase, color="steelblue", linewidth=2, label="Simulated")

    # Theoretical phase: φ(f) = -arctan(f/fc)
    phase_theory = -np.degrees(np.arctan(f_theory / fc))
    ax_phase.semilogx(f_theory, phase_theory, color="orange", linewidth=1.5,
                      linestyle="--", label="Theoretical")

    # Mark -45° at fc — a key sanity check for any RC filter
    ax_phase.axhline(-45, color="gray", linestyle=":", linewidth=1)
    ax_phase.axvline(fc, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax_phase.annotate("-45° at fc", xy=(fc, -45), xytext=(fc * 3, -35),
                      arrowprops=dict(arrowstyle="->", color="red"),
                      color="red", fontsize=9)

    ax_phase.set_ylabel("Phase (°)")
    ax_phase.set_xlabel("Frequency (Hz)")
    ax_phase.set_ylim(-100, 10)
    ax_phase.grid(True, which="both", alpha=0.3)
    ax_phase.legend(fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc2_ac_analysis.png"), dpi=150)
    plt.show()
    print("  Done. Plot saved to uc2_ac_analysis.png")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 3 — Monte Carlo / Tolerance Analysis
# ══════════════════════════════════════════════════════════════════════════════
#
# Goal: simulate what happens when your components have real-world tolerances.
# Real resistors and capacitors are not exactly their labeled value — a "10kΩ"
# resistor with ±5% tolerance could actually be anywhere from 9.5kΩ to 10.5kΩ.
#
# We randomly sample R and C within their tolerance bands and run a simulation
# for each sample. The spread of the resulting Bode plots shows you how much
# your circuit's behavior varies due to manufacturing tolerances.
#
# This is useful for:
#   - Deciding whether ±5% or ±1% components are needed for your spec
#   - Understanding worst-case cutoff frequency drift
#   - Justifying component choices in a design review

def use_case_3_monte_carlo():
    print("\n=== USE CASE 3: Monte Carlo Tolerance Analysis ===")
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Nominal design values
    R_nom = 15e3    # 15 kΩ nominal
    C_nom = 6.8e-9  # 6.8 nF nominal

    # Tolerance as a fraction (0.05 = ±5%)
    R_tolerance = 0.05
    C_tolerance = 0.05

    # Number of random samples to simulate.
    # More samples = smoother distribution but longer runtime.
    N_SAMPLES = 30

    # Seed the random number generator for reproducibility
    np.random.seed(42)

    # Generate N random R and C values uniformly distributed within tolerance
    # np.random.uniform(low, high, N) draws N samples between low and high
    R_samples = np.random.uniform(R_nom * (1 - R_tolerance),
                                  R_nom * (1 + R_tolerance),
                                  N_SAMPLES)
    C_samples = np.random.uniform(C_nom * (1 - C_tolerance),
                                  C_nom * (1 + C_tolerance),
                                  N_SAMPLES)

    fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(f"USE CASE 3 — Monte Carlo  |  R={R_nom/1e3:.0f}kΩ ±{R_tolerance*100:.0f}%,"
                 f"  C={C_nom*1e9:.1f}nF ±{C_tolerance*100:.0f}%"
                 f"  ({N_SAMPLES} samples)", fontsize=11)

    # Store all cutoff frequencies so we can plot a histogram
    fc_list = []

    for i, (R, C) in enumerate(zip(R_samples, C_samples)):
        print(f"  Sample {i+1}/{N_SAMPLES}: R={R/1e3:.2f}kΩ, C={C*1e9:.2f}nF")

        raw_path = run_simulation(R, C, filename=f"mc_{i}.asc")

        if not os.path.exists(raw_path):
            print(f"  [!] Simulation failed — skipping")
            continue

        freq, mag_db, phase = read_ac_results(raw_path)
        fc = cutoff_hz(R, C)
        fc_list.append(fc)

        # Plot each sample as a thin semi-transparent line so overlaps are visible
        ax_mag.semilogx(freq, mag_db, color="steelblue", linewidth=0.8, alpha=0.3)
        ax_phase.semilogx(freq, phase, color="steelblue", linewidth=0.8, alpha=0.3)

    # Overlay the nominal (ideal) response in a bold contrasting color
    raw_nom = run_simulation(R_nom, C_nom, filename="mc_nominal.asc")
    if os.path.exists(raw_nom):
        freq_n, mag_n, phase_n = read_ac_results(raw_nom)
        fc_nom = cutoff_hz(R_nom, C_nom)
        ax_mag.semilogx(freq_n, mag_n, color="red", linewidth=2.5,
                        label=f"Nominal (fc={fc_nom:.0f} Hz)", zorder=5)
        ax_phase.semilogx(freq_n, phase_n, color="red", linewidth=2.5,
                          label="Nominal", zorder=5)

    # ── Annotate with statistics ──────────────────────────────────────────────

    fc_arr = np.array(fc_list)
    fc_mean = np.mean(fc_arr)
    fc_std  = np.std(fc_arr)
    fc_min  = np.min(fc_arr)
    fc_max  = np.max(fc_arr)

    stats_text = (f"fc stats ({N_SAMPLES} samples)\n"
                  f"Mean:  {fc_mean:.0f} Hz\n"
                  f"Std:   {fc_std:.0f} Hz\n"
                  f"Min:   {fc_min:.0f} Hz\n"
                  f"Max:   {fc_max:.0f} Hz")

    # Place the stats box in the upper right of the magnitude plot
    ax_mag.text(0.98, 0.95, stats_text, transform=ax_mag.transAxes,
                fontsize=8, verticalalignment="top", horizontalalignment="right",
                bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

    # Add a dummy line for the legend label for the Monte Carlo samples
    from matplotlib.lines import Line2D
    mc_line = Line2D([0], [0], color="steelblue", linewidth=1.5, alpha=0.5,
                     label=f"Monte Carlo samples (n={N_SAMPLES})")

    # Format magnitude plot
    ax_mag.axhline(-3, color="gray", linestyle=":", linewidth=1)
    ax_mag.set_ylabel("Magnitude (dB)")
    ax_mag.set_ylim(-50, 5)
    ax_mag.grid(True, which="both", alpha=0.3)
    ax_mag.legend(handles=[mc_line] + ax_mag.get_lines()[-1:], fontsize=8)

    # Format phase plot
    ax_phase.set_ylabel("Phase (°)")
    ax_phase.set_xlabel("Frequency (Hz)")
    ax_phase.set_ylim(-100, 10)
    ax_phase.grid(True, which="both", alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc3_monte_carlo.png"), dpi=150)
    plt.show()

    # ── Bonus: histogram of cutoff frequency spread ───────────────────────────
    # This gives an intuitive view of how much fc varies across samples

    fig2, ax_hist = plt.subplots(figsize=(7, 4))
    ax_hist.hist(fc_arr, bins=10, color="steelblue", edgecolor="white", alpha=0.85)
    ax_hist.axvline(fc_mean, color="red", linestyle="--", linewidth=1.5,
                    label=f"Mean = {fc_mean:.0f} Hz")
    ax_hist.axvline(fc_nom, color="orange", linestyle="--", linewidth=1.5,
                    label=f"Nominal = {fc_nom:.0f} Hz")
    ax_hist.set_xlabel("Cutoff Frequency (Hz)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title(f"fc Distribution — ±{R_tolerance*100:.0f}% Tolerance ({N_SAMPLES} samples)")
    ax_hist.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc3_histogram.png"), dpi=150)
    plt.show()

    print(f"  Done. fc mean={fc_mean:.0f} Hz, std={fc_std:.0f} Hz")
    print("  Plots saved to uc3_monte_carlo.png and uc3_histogram.png")


# ══════════════════════════════════════════════════════════════════════════════
# Entry point — run all three use cases in order
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    use_case_1_parameter_sweep()
    use_case_2_ac_analysis()
    use_case_3_monte_carlo()
