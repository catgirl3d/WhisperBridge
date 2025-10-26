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

# Inform the user about dynamic OCR flag support in spec files
if selected_spec != "WhisperBridge.spec":
    print("[build.py] Warning: Selected spec does not use dynamic OCR flag (OCR_ENABLED).")
    print("[build.py] OCR_ENABLED will be ignored and build behavior is defined by the selected spec file itself.")
    print("[build.py] For dynamic behavior and logging, select 'WhisperBridge.spec'.")
else:
    print("[build.py] Selected the dynamic spec (WhisperBridge.spec) — OCR_ENABLED will control the build profile.")

# Ask if user wants to use UPX compression
use_upx = input("Use UPX compression? (y/n): ").lower().strip() == 'y'

# Ask whether OCR should be included (generates _build_flags.py for baked flag)
include_ocr_input = input("Include OCR? (y/n): ").lower().strip()
include_ocr = include_ocr_input in ('y', 'yes', '1', 'true')

# Ask for build mode if using WhisperBridge.spec
build_mode = None
if selected_spec == "WhisperBridge.spec":
    print("Build modes for WhisperBridge.spec:")
    print("1. One-file executable (--onefile)")
    print("2. Directory with console (--onedir --console)")
    print("3. Directory without console (--onedir)")
    while True:
        try:
            mode_choice = int(input("Choose build mode (1-3): "))
            if mode_choice == 1:
                build_mode = "onefile"
                break
            elif mode_choice == 2:
                build_mode = "onedir_console"
                break
            elif mode_choice == 3:
                build_mode = "onedir"
                break
            else:
                print("Invalid choice. Please enter 1, 2, or 3.")
        except ValueError:
            print("Invalid input. Please enter a number.")

# Generate _build_flags.py with hard-coded OCR_ENABLED, BUILD_MODE and USE_UPX values
project_root = os.getcwd()
build_flags_content = f"OCR_ENABLED = {include_ocr}\n"
if build_mode:
    build_flags_content += f"BUILD_MODE = '{build_mode}'\n"
build_flags_content += f"USE_UPX = {use_upx}\n"
build_flags_path = os.path.join(project_root, '_build_flags.py')
with open(build_flags_path, 'w', encoding='utf-8') as f:
    f.write(build_flags_content)

print("========== build.py CONFIG ==========")
print(f"[build.py] Selected spec: {selected_spec}")
print(f"[build.py] Use UPX: {use_upx}")
print(f"[build.py] Include OCR: {include_ocr}")
if build_mode:
    print(f"[build.py] Build mode: {build_mode}")
print(f"[build.py] Generated _build_flags.py: OCR_ENABLED = {include_ocr}, USE_UPX = {use_upx}")
print("=====================================")

# Build project using PyInstaller (use current interpreter)
cmd = [
    sys.executable, "-m", "PyInstaller",
    "--clean", "--noconfirm"
]

# Note: Build mode flags (--onefile, --onedir, --console) are handled inside WhisperBridge.spec
# based on BUILD_MODE from _build_flags.py. Do not add them here when using .spec files.

if use_upx:
    cmd.append('--upx-dir')
    cmd.append(r"C:\Tools\upx")

cmd.append(selected_spec)

# Run PyInstaller (no special env needed, flag is baked in _build_flags.py)
result = subprocess.run(cmd)

# Surface exit code for CI/automation
if result.returncode != 0:
    print(f"[build.py] PyInstaller failed with exit code {result.returncode}")
    sys.exit(result.returncode)
else:
    print("[build.py] PyInstaller finished successfully")