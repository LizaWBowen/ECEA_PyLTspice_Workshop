import numpy as np
import matplotlib.pyplot as plt
import os
import shutil
import subprocess
import time
import re

from PyLTSpice import RawRead


# ────────────────────────────────────────────────────────────────
# USER CONFIGURATION (EDIT THESE FIRST)
# ────────────────────────────────────────────────────────────────

# Path to LTSpice executable (REQUIRED)
LTSPICE_PATH = r"C:\Program Files\ADI\LTspice\LTspice.exe"

# Path to your base schematic (.asc file)
SCHEMATIC_PATH = r"C:\Users\lizab\OneDrive\Documents\LTspice\Draft16.asc"

# Folder where all generated files will be stored
OUTPUT_FOLDER = r"C:\Users\lizab\Downloads\rc_sweep_output"

# Name of the node you want to measure
NODE_NAME = "out"

# Toggle which use cases to run
RUN_UC1 = True
RUN_UC2 = True
RUN_UC3 = True


# ────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────────────────────

def cutoff_hz(R, C):
    """
    Compute theoretical cutoff frequency for RC low-pass filter:
        fc = 1 / (2πRC)
    """
    return 1.0 / (2 * np.pi * R * C)


def wait_for_file(path, timeout=10):
    """
    Wait until a file exists (used for LTSpice .raw output).

    Why this is needed:
    LTSpice runs as a separate process, so Python might try to read
    the .raw file BEFORE it's finished writing.
    """
    start = time.time()
    while not os.path.exists(path):
        if time.time() - start > timeout:
            raise TimeoutError(f"{path} not created")
        time.sleep(0.1)


def run_simulation(R, C, filename):
    """
    Run a single LTSpice simulation with given R and C values.

    Steps:
    1. Copy the base schematic (so we never modify the original)
    2. Replace the .param R and C values directly in the file text
    3. Run LTSpice in batch mode (no GUI)
    4. Wait for .raw output file and return its path
    """
    asc_path = os.path.join(OUTPUT_FOLDER, filename)
    shutil.copy(SCHEMATIC_PATH, asc_path)

    # Read the schematic as plain text
    with open(asc_path, "r") as f:
        content = f.read()

    # Make sure .param line exists
    param_lines = [l for l in content.splitlines() if 'param' in l.lower()]
    if not param_lines:
        raise ValueError("No .param line found in schematic. Add '.param R=1k C=10n' in LTSpice.")

    # Replace the .param values directly using regex
    # Handles the LTSpice .asc format: TEXT x y Left 2 !.param R=... C=...
    content = re.sub(
        r'(\.param\s+R=)\S+(\s+C=)\S+',
        lambda m: m.group(1) + str(R) + m.group(2) + str(C),
        content,
        flags=re.IGNORECASE
    )

    with open(asc_path, "w") as f:
        f.write(content)

    # Run LTSpice in batch mode (-b = no GUI)
    
    subprocess.run([LTSPICE_PATH, "-b", "-Run", asc_path], check=True, timeout=30)

    # Wait for .raw file to be written
    raw_path = asc_path.replace(".asc", ".raw")
    wait_for_file(raw_path)

    return raw_path


def read_ac_results(raw_path):
    """
    Read frequency, magnitude, and phase from LTSpice .raw file.

    LTSpice AC analysis outputs COMPLEX numbers:
        V(f) = magnitude * e^(j*phase)

    We convert:
        magnitude → dB
        phase → degrees
    """
    ltr = RawRead(raw_path)
    traces = ltr.get_trace_names()
    target = f"V({NODE_NAME})"

    # Safety check: make sure node exists
    if target not in traces:
        raise ValueError(f"{target} not found. Available traces: {traces}")

    # Frequency axis (real values only)
    freq = np.array(ltr.get_trace("frequency").get_wave(0)).real

    # Complex output voltage
    vout = np.array(ltr.get_trace(target).get_wave(0))

    # Convert to magnitude (dB) and phase (degrees)
    mag_db = 20 * np.log10(np.abs(vout))
    phase = np.angle(vout, deg=True)

    return freq, mag_db, phase


def find_fc(freq, mag_db):
    """
    Estimate cutoff frequency from simulation data.
    Finds the frequency where magnitude is closest to -3 dB.
    """
    idx = np.argmin(np.abs(mag_db + 3))
    return freq[idx]


def save_csv(freq, mag, phase, filename):
    """
    Save simulation data to CSV for external tools (Excel, MATLAB, etc.)
    """
    np.savetxt(
        filename,
        np.column_stack([freq, mag, phase]),
        delimiter=",",
        header="freq,mag_db,phase",
        comments=""
    )


# ────────────────────────────────────────────────────────────────
# USE CASE 1 — PARAMETER SWEEP
# ────────────────────────────────────────────────────────────────

def use_case_1():
    print("\n=== USE CASE 1: Parameter Sweep ===")

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Define values to sweep
    R_VALUES = [15e3, 6.8e3, 4.7e3]
    C_VALUES = [6.8e-9, 15e-9, 22e-9]

    # Generate all R+C combinations
    combos = [(R, C) for R in R_VALUES for C in C_VALUES]

    fig, (ax_mag, ax_phase) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax_mag.set_title("USE CASE 1 — Parameter Sweep: RC Low-Pass Filter", fontsize=13)

    for i, (R, C) in enumerate(combos):
        print(f"  Simulating R={R/1e3:.1f}kΩ, C={C*1e9:.1f}nF ...")
        raw = run_simulation(R, C, f"sweep_{i}.asc")
        freq, mag, phase = read_ac_results(raw)
        fc_meas = find_fc(freq, mag)

        label = f"R={R/1e3:.1f}kΩ, C={C*1e9:.0f}nF  (fc={fc_meas:.0f} Hz)"
        ax_mag.semilogx(freq, mag, label=label)
        ax_phase.semilogx(freq, phase)

    ax_mag.axhline(-3, color="gray", linestyle=":", linewidth=1, label="-3 dB")
    ax_mag.set_ylabel("Magnitude (dB)")
    ax_mag.set_ylim(-50, 5)
    ax_mag.grid(True, which="both", alpha=0.3)
    ax_mag.legend(fontsize=7, loc="lower left")

    ax_phase.set_ylabel("Phase (°)")
    ax_phase.set_xlabel("Frequency (Hz)")
    ax_phase.set_ylim(-100, 10)
    ax_phase.grid(True, which="both", alpha=0.3)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc1_sweep.png"), dpi=150)
    plt.show()

    print("  Done.")


# ────────────────────────────────────────────────────────────────
# USE CASE 2 — SINGLE AC ANALYSIS
# ────────────────────────────────────────────────────────────────

def use_case_2():
    print("\n=== USE CASE 2: AC Analysis ===")

    R, C = 15e3, 6.8e-9
    fc_theory = cutoff_hz(R, C)
    print(f"  Simulating R={R/1e3:.0f}kΩ, C={C*1e9:.1f}nF → fc={fc_theory:.1f} Hz")

    raw = run_simulation(R, C, "uc2.asc")
    freq, mag, phase = read_ac_results(raw)
    fc = find_fc(freq, mag)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(f"USE CASE 2 — AC Analysis  |  R={R/1e3:.0f}kΩ, C={C*1e9:.1f}nF  |  fc={fc:.0f} Hz", fontsize=12)

    # Overlay theoretical response
    f_theory = np.logspace(1, 6, 500)
    mag_theory = -10 * np.log10(1 + (f_theory / fc_theory)**2)
    phase_theory = -np.degrees(np.arctan(f_theory / fc_theory))

    ax1.semilogx(freq, mag, color="steelblue", linewidth=2, label="Simulated")
    ax1.semilogx(f_theory, mag_theory, color="orange", linewidth=1.5, linestyle="--", label="Theoretical")
    ax1.axvline(fc, color="red", linestyle="--", linewidth=1, alpha=0.7)
    ax1.axhline(-3, color="gray", linestyle=":", linewidth=1)
    ax1.annotate(f"fc = {fc:.0f} Hz\n-3 dB", xy=(fc, -3), xytext=(fc * 3, -10),
                 arrowprops=dict(arrowstyle="->", color="red"), color="red", fontsize=9)

    ax2.semilogx(freq, phase, color="steelblue", linewidth=2, label="Simulated")
    ax2.semilogx(f_theory, phase_theory, color="orange", linewidth=1.5, linestyle="--", label="Theoretical")
    ax2.axhline(-45, color="gray", linestyle=":", linewidth=1)
    ax2.axvline(fc, color="red", linestyle="--", linewidth=1, alpha=0.7)

    ax1.set_ylabel("Magnitude (dB)")
    ax1.set_ylim(-60, 5)
    ax1.grid(True, which="both", alpha=0.3)
    ax1.legend(fontsize=9)

    ax2.set_ylabel("Phase (°)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.set_ylim(-100, 10)
    ax2.grid(True, which="both", alpha=0.3)
    ax2.legend(fontsize=9)

    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc2_ac_analysis.png"), dpi=150)

    # Save data to CSV for external analysis
    save_csv(freq, mag, phase, os.path.join(OUTPUT_FOLDER, "uc2.csv"))

    plt.show()
    print("  Done.")


# ────────────────────────────────────────────────────────────────
# USE CASE 3 — MONTE CARLO ANALYSIS
# ────────────────────────────────────────────────────────────────

def use_case_3():
    print("\n=== USE CASE 3: Monte Carlo ===")

    R_nom, C_nom = 15e3, 6.8e-9
    tol = 0.05
    N = 30

    np.random.seed(42)

    # Generate random R and C values within tolerance band
    Rs = np.random.uniform(R_nom * (1 - tol), R_nom * (1 + tol), N)
    Cs = np.random.uniform(C_nom * (1 - tol), C_nom * (1 + tol), N)

    all_mag = []
    fc_list = []

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    fig.suptitle(f"USE CASE 3 — Monte Carlo  |  R={R_nom/1e3:.0f}kΩ ±{tol*100:.0f}%,"
                 f"  C={C_nom*1e9:.1f}nF ±{tol*100:.0f}%  ({N} samples)", fontsize=11)

    for i, (R, C) in enumerate(zip(Rs, Cs)):
        print(f"  Sample {i+1}/{N}: R={R/1e3:.2f}kΩ, C={C*1e9:.2f}nF")
        raw = run_simulation(R, C, f"mc_{i}.asc")
        freq, mag, phase = read_ac_results(raw)

        all_mag.append(mag)
        fc_list.append(find_fc(freq, mag))

        # Faint line for each sample
        ax1.semilogx(freq, mag, color="steelblue", alpha=0.3, linewidth=0.8)
        ax2.semilogx(freq, phase, color="steelblue", alpha=0.3, linewidth=0.8)

    # Overlay nominal response in bold red
    raw_nom = run_simulation(R_nom, C_nom, "mc_nominal.asc")
    freq_n, mag_n, phase_n = read_ac_results(raw_nom)
    fc_nom = find_fc(freq_n, mag_n)
    ax1.semilogx(freq_n, mag_n, color="red", linewidth=2.5, label=f"Nominal (fc={fc_nom:.0f} Hz)", zorder=5)
    ax2.semilogx(freq_n, phase_n, color="red", linewidth=2.5, label="Nominal", zorder=5)

    # Convert list to array for envelope
    all_mag = np.array(all_mag)
    ax1.fill_between(freq, all_mag.min(0), all_mag.max(0), alpha=0.15, color="steelblue", label="Min/Max envelope")

    # Stats box
    fc_arr = np.array(fc_list)
    stats = (f"fc stats ({N} samples)\n"
             f"Mean:  {np.mean(fc_arr):.0f} Hz\n"
             f"Std:   {np.std(fc_arr):.0f} Hz\n"
             f"Min:   {np.min(fc_arr):.0f} Hz\n"
             f"Max:   {np.max(fc_arr):.0f} Hz")
    ax1.text(0.98, 0.95, stats, transform=ax1.transAxes, fontsize=8,
             verticalalignment="top", horizontalalignment="right",
             bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))

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

    # Bonus histogram of fc distribution
    fig2, ax_hist = plt.subplots(figsize=(7, 4))
    ax_hist.hist(fc_arr, bins=10, color="steelblue", edgecolor="white", alpha=0.85)
    ax_hist.axvline(np.mean(fc_arr), color="red", linestyle="--", linewidth=1.5, label=f"Mean = {np.mean(fc_arr):.0f} Hz")
    ax_hist.axvline(fc_nom, color="orange", linestyle="--", linewidth=1.5, label=f"Nominal = {fc_nom:.0f} Hz")
    ax_hist.set_xlabel("Cutoff Frequency (Hz)")
    ax_hist.set_ylabel("Count")
    ax_hist.set_title(f"fc Distribution — ±{tol*100:.0f}% Tolerance ({N} samples)")
    ax_hist.legend(fontsize=9)
    plt.tight_layout()
    plt.savefig(os.path.join(OUTPUT_FOLDER, "uc3_histogram.png"), dpi=150)
    plt.show()

    print(f"  Done. fc mean={np.mean(fc_arr):.0f} Hz, std={np.std(fc_arr):.0f} Hz")


# ────────────────────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if RUN_UC1:
        use_case_1()

    if RUN_UC2:
        use_case_2()

    if RUN_UC3:
        use_case_3()
