import subprocess
import sys
import os
import glob

# Find all .spec files in the current directory
spec_files = glob.glob("*.spec")

if not spec_files:
    print("No .spec files found in the current directory.")
    sys.exit(1)

print("Available .spec files:")
for i, spec in enumerate(spec_files, 1):
    print(f"{i}. {spec}")

# Prompt user to choose a spec file
while True:
    try:
        choice = int(input("Enter the number of the .spec file to use: ")) - 1
        if 0 <= choice < len(spec_files):
            selected_spec = spec_files[choice]
            break
        else:
            print("Invalid choice. Please enter a valid number.")
    except ValueError:
        print("Invalid input. Please enter a number.")

print(f"Building project using {selected_spec}")

# Ask if user wants to use UPX compression
use_upx = input("Use UPX compression? (y/n): ").lower().strip() == 'y'

# Build project using PyInstaller
cmd = [
    "python", "-m", "PyInstaller",
    "--clean", "--noconfirm"
]

if use_upx:
    cmd.append('--upx-dir')
    cmd.append(r"C:\Tools\upx")

cmd.append(selected_spec)

subprocess.run(cmd)