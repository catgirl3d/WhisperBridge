import subprocess
import sys
import os
import argparse
import setuptools_scm
import glob

def get_version():
    """Get the clean version using setuptools_scm."""
    try:
        clean_version = setuptools_scm.get_version()
        print(f"[build.py] Detected clean version: {clean_version}")
        return clean_version
    except Exception as e:
        print(f"[build.py] Could not determine version with setuptools_scm: {e}")
        return None

def run_interactive_mode():
    """Run the build script in interactive mode to gather parameters."""
    # Find all .spec files
    spec_files = glob.glob("*.spec")
    if not spec_files:
        print("No .spec files found in the current directory.")
        sys.exit(1)

    print("Available .spec files:")
    for i, spec in enumerate(spec_files, 1):
        print(f"{i}. {spec}")

    # Prompt for spec file
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

    # Ask about UPX
    use_upx = input("Use UPX compression? (y/n): ").lower().strip() == 'y'
    
    # Ask about OCR
    include_ocr_input = input("Include OCR? (y/n): ").lower().strip()
    include_ocr = include_ocr_input in ('y', 'yes', '1', 'true')

    # Ask for build mode if using the dynamic spec
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

    return {
        "spec": selected_spec,
        "ocr": include_ocr,
        "upx": use_upx,
        "upx_dir": r"C:\Tools\upx",  # Default for interactive
        "mode": build_mode,
        "flags_dir": "build/flags"  # Default for interactive
    }

def print_build_summary(config):
    """Print a concise, deterministic summary at the end of the build."""
    mode = config.get('mode') or 'onedir'
    print("\n========== Build Summary ==========")
    print(f"  Spec: {config['spec']}")
    print(f"  OCR: {bool(config['ocr'])}")
    print(f"  UPX: {bool(config['upx'])}")
    print(f"  Mode: {mode}")
    print("===================================")


def run_build(config, clean_version):
    """Executes the PyInstaller build process using the provided configuration."""
    selected_spec = config["spec"]
    include_ocr = config["ocr"]
    use_upx = config["upx"]
    upx_dir = config["upx_dir"]
    build_mode = config["mode"]
    flags_dir = config["flags_dir"]

    # --- Dynamic Spec Warning ---
    if selected_spec != "WhisperBridge.spec":
        print("[build.py] Warning: Selected spec might not use dynamic flags (OCR_ENABLED, BUILD_MODE).")
    else:
        print("[build.py] Selected the dynamic spec (WhisperBridge.spec) — flags will control the build profile.")

    # --- Generate Build Flags ---
    os.makedirs(flags_dir, exist_ok=True)
    
    build_flags_content = f"OCR_ENABLED = {include_ocr}\n"
    if build_mode:
        build_flags_content += f"BUILD_MODE = '{build_mode}'\n"
    else:
        build_flags_content += "BUILD_MODE = 'onedir'\n"  # Default if not specified
    build_flags_content += f"USE_UPX = {use_upx}\n"
    
    build_flags_path = os.path.join(flags_dir, '_build_flags.py')
    with open(build_flags_path, 'w', encoding='utf-8') as f:
        f.write(build_flags_content)

    # --- Print Configuration ---
    print("========== build.py CONFIG ==========")
    print(f"[build.py] Selected spec: {selected_spec}")
    print(f"[build.py] Use UPX: {use_upx}")
    if use_upx:
        print(f"[build.py] UPX Path: {upx_dir}")
    print(f"[build.py] Include OCR: {include_ocr}")
    if build_mode:
        print(f"[build.py] Build mode: {build_mode}")
    print(f"[build.py] Generated flags at: {build_flags_path}")
    if clean_version:
        print(f"[build.py] Pretending version: {clean_version}")
    print("=====================================")

    # --- Build Project ---
    cmd = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm"]
    if use_upx:
        cmd.extend(['--upx-dir', upx_dir])
    cmd.append(selected_spec)

    # --- Environment Setup ---
    env = os.environ.copy()
    python_path = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{os.path.abspath(flags_dir)}{os.pathsep}{python_path}"
    if clean_version:
        env["SETUPTOOLS_SCM_PRETEND_VERSION"] = clean_version

    print(f"[build.py] Running PyInstaller with modified PYTHONPATH: {env['PYTHONPATH']}")
    
    result = subprocess.run(cmd, env=env)

    # --- Finalize ---
    if result.returncode != 0:
        print(f"[build.py] PyInstaller failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    else:
        print("[build.py] PyInstaller finished successfully")
        print_build_summary(config)

def main():
    """Main entry point that decides between interactive and non-interactive modes."""
    clean_version = get_version()

    parser = argparse.ArgumentParser(description="Build WhisperBridge via PyInstaller")
    parser.add_argument("--spec", help="Spec file to use (required for non-interactive mode)")
    parser.add_argument("--ocr", action="store_true", help="Include OCR support")
    parser.add_argument("--upx", action="store_true", help="Use UPX compression")
    parser.add_argument("--upx-dir", default=r"C:\Tools\upx", help="Path to UPX directory")
    parser.add_argument("--mode", choices=["onefile", "onedir", "onedir_console"], help="Build mode for dynamic spec")
    parser.add_argument("--flags-dir", default="build/flags", help="Directory for generated _build_flags.py")

    # Decide interactive vs non-interactive mode
    if len(sys.argv) == 1:
        # No arguments -> interactive mode
        config = run_interactive_mode()
    else:
        # Non-interactive -> require --spec (let argparse enforce it)
        for action in parser._actions:
            if '--spec' in getattr(action, 'option_strings', []):
                action.required = True
                break
        args = parser.parse_args()
        config = {
            "spec": args.spec,
            "ocr": args.ocr,
            "upx": args.upx,
            "upx_dir": args.upx_dir,
            "mode": args.mode,
            "flags_dir": args.flags_dir
        }

    run_build(config, clean_version)

if __name__ == "__main__":
    main()