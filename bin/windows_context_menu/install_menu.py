"""
AEPGP Windows Context Menu Installer - Cascading Menu Version

This script installs a cascading submenu structure for AEPGP operations.
All AEPGP options appear under a single "AEPGP" submenu.

IMPORTANT: This script requires Administrator privileges to modify the Windows
registry (HKEY_CLASSES_ROOT).
"""

import sys
import os
import glob
import subprocess
import winreg
import ctypes

# Version tracking
CURRENT_VERSION = "1.3.1"

# CLSID of the COM shell extension — must match AEPGPContextMenu.cs exactly
SHELL_EXT_CLSID = "{3F7E8D9A-B1C2-4E5F-8A6B-9C0D1E2F3A4B}"
VERSION_REG_KEY = r"Software\AEPGP\ContextMenu"
VERSION_VALUE_NAME = "Version"


def is_admin():
    """Check if the script is running with Administrator privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def elevate_privileges():
    """Re-run the script with Administrator privileges"""
    if sys.platform != 'win32':
        print("ERROR: This script is only for Windows")
        return False

    try:
        # Re-run the script with elevation
        ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",  # Request elevation
            sys.executable,  # Python interpreter
            " ".join([f'"{arg}"' for arg in sys.argv]),  # Script and arguments
            None,
            1  # SW_SHOWNORMAL
        )
        return True
    except Exception as e:
        print(f"ERROR: Failed to elevate privileges: {e}")
        return False


def is_windows_11():
    """Return True if running on Windows 11 (build number 22000 or higher)."""
    import platform
    try:
        build = int(platform.version().split('.')[2])
        return build >= 22000
    except Exception:
        return False


def _find_dotnet_tool(tool_name, prefer_x64=True):
    """Locate a .NET Framework 4.x tool (csc.exe, RegAsm.exe).

    Checks Framework64 before Framework so the compiled DLL is always x64,
    matching /platform:x64 in the csc.exe invocation.
    Returns the full path, or None if not found.
    """
    roots = (
        [r"C:\Windows\Microsoft.NET\Framework64",
         r"C:\Windows\Microsoft.NET\Framework"]
        if prefer_x64
        else [r"C:\Windows\Microsoft.NET\Framework",
              r"C:\Windows\Microsoft.NET\Framework64"]
    )
    for root in roots:
        # Prefer the known v4.0.30319 directory; fall back to any v4.x
        preferred = os.path.join(root, "v4.0.30319", tool_name)
        if os.path.isfile(preferred):
            return preferred
        for p in sorted(glob.glob(os.path.join(root, "v4*", tool_name)), reverse=True):
            if os.path.isfile(p):
                return p
    return None


def get_launcher_path():
    """
    Return the path to aepgp_launch.py and verify all handler scripts exist.

    All registry entries point to the single launcher script.  This means only
    ONE absolute path is stored in the registry per action — moving the
    installation directory requires updating only that one file reference.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    handlers_dir = os.path.join(script_dir, "handlers")

    launcher = os.path.join(script_dir, "aepgp_launch.py")
    if not os.path.exists(launcher):
        raise FileNotFoundError(f"Launcher not found: {launcher}")

    # Verify that every handler the launcher will dispatch to actually exists.
    for name in ("encrypt_handler.py", "decrypt_handler.py",
                 "generate_keys_handler.py", "delete_keys_handler.py",
                 "change_pin_handler.py"):
        path = os.path.join(handlers_dir, name)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Handler not found: {path}")

    return launcher


# Keep get_script_paths() for backward compatibility with any external callers.
def get_script_paths():
    """Get the absolute paths to the handler scripts"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    handlers_dir = os.path.join(script_dir, "handlers")
    watcher_script = os.path.join(script_dir, "visibility_watcher.py")

    encrypt_handler = os.path.join(handlers_dir, "encrypt_handler.py")
    decrypt_handler = os.path.join(handlers_dir, "decrypt_handler.py")
    generate_keys_handler = os.path.join(handlers_dir, "generate_keys_handler.py")
    delete_keys_handler = os.path.join(handlers_dir, "delete_keys_handler.py")
    # import_pfx_handler = os.path.join(handlers_dir, "import_pfx_handler.py")  # DISABLED - Feature incomplete
    change_pin_handler = os.path.join(handlers_dir, "change_pin_handler.py")

    # Verify handlers exist
    if not os.path.exists(encrypt_handler):
        raise FileNotFoundError(f"Encrypt handler not found: {encrypt_handler}")
    if not os.path.exists(decrypt_handler):
        raise FileNotFoundError(f"Decrypt handler not found: {decrypt_handler}")
    if not os.path.exists(generate_keys_handler):
        raise FileNotFoundError(f"Generate keys handler not found: {generate_keys_handler}")
    if not os.path.exists(delete_keys_handler):
        raise FileNotFoundError(f"Delete keys handler not found: {delete_keys_handler}")
    # if not os.path.exists(import_pfx_handler):  # DISABLED - Feature incomplete
    #     raise FileNotFoundError(f"Import PFX handler not found: {import_pfx_handler}")
    if not os.path.exists(change_pin_handler):
        raise FileNotFoundError(f"Change PIN handler not found: {change_pin_handler}")
    if not os.path.exists(watcher_script):
        raise FileNotFoundError(f"Visibility watcher not found: {watcher_script}")

    return (
        encrypt_handler,
        decrypt_handler,
        generate_keys_handler,
        delete_keys_handler,
        change_pin_handler,
        watcher_script,
    )  # Removed import_pfx_handler


def install_cascading_menu_for_all_files(launcher):
    """
    Install a single cascading AEPGP submenu for all files (*).

    Creates a consistent structure mirroring the desktop menu:
    Right-click any file → AEPGP →
        ├── Encrypt File
        ├── Decrypt File
        ├── Generate Keys in Card
        ├── Delete Keys from Card
        └── Change Card PIN

    All commands route through aepgp_launch.py (single registered path).

    Raises TypeError if a legacy handlers-tuple is passed instead of a
    launcher path string (guards against callers using the old signature).
    """
    if isinstance(launcher, (list, tuple)):
        raise TypeError(
            "install_cascading_menu_for_all_files() no longer accepts a handlers "
            "tuple. Pass the launcher script path string from get_launcher_path()."
        )

    try:
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        # Single top-level AEPGP cascading entry for all files
        main_key_path = r"*\shell\AEPGP"
        main_key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, main_key_path)
        winreg.SetValueEx(main_key, "MUIVerb", 0, winreg.REG_SZ, "AEPGP")
        winreg.SetValueEx(main_key, "Position", 0, winreg.REG_SZ, "Top")
        # Empty SubCommands tells Windows to build the submenu from shell subkeys
        winreg.SetValueEx(main_key, "SubCommands", 0, winreg.REG_SZ, "")

        shell_key = winreg.CreateKey(main_key, "shell")

        # 1. Encrypt File
        enc_key = winreg.CreateKey(shell_key, "encrypt")
        winreg.SetValueEx(enc_key, "", 0, winreg.REG_SZ, "Encrypt File")
        winreg.SetValueEx(enc_key, "MUIVerb", 0, winreg.REG_SZ, "Encrypt File")
        enc_cmd = winreg.CreateKey(enc_key, "command")
        winreg.SetValue(enc_cmd, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" encrypt "%1"')
        winreg.CloseKey(enc_cmd)
        winreg.CloseKey(enc_key)
        print("  ✓ Added 'Encrypt File'")

        # 2. Decrypt File
        dec_key = winreg.CreateKey(shell_key, "decrypt")
        winreg.SetValueEx(dec_key, "", 0, winreg.REG_SZ, "Decrypt File")
        winreg.SetValueEx(dec_key, "MUIVerb", 0, winreg.REG_SZ, "Decrypt File")
        dec_cmd = winreg.CreateKey(dec_key, "command")
        winreg.SetValue(dec_cmd, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" decrypt "%1"')
        winreg.CloseKey(dec_cmd)
        winreg.CloseKey(dec_key)
        print("  ✓ Added 'Decrypt File'")

        # 3. Generate Keys in Card
        gen_key = winreg.CreateKey(shell_key, "generatekeys")
        winreg.SetValueEx(gen_key, "", 0, winreg.REG_SZ, "Generate Keys in Card")
        winreg.SetValueEx(gen_key, "MUIVerb", 0, winreg.REG_SZ, "Generate Keys in Card")
        gen_cmd = winreg.CreateKey(gen_key, "command")
        winreg.SetValue(gen_cmd, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" generate_keys')
        winreg.CloseKey(gen_cmd)
        winreg.CloseKey(gen_key)
        print("  ✓ Added 'Generate Keys in Card'")

        # 4. Delete Keys from Card
        del_key = winreg.CreateKey(shell_key, "deletekeys")
        winreg.SetValueEx(del_key, "", 0, winreg.REG_SZ, "Delete Keys from Card")
        winreg.SetValueEx(del_key, "MUIVerb", 0, winreg.REG_SZ, "Delete Keys from Card")
        del_cmd = winreg.CreateKey(del_key, "command")
        winreg.SetValue(del_cmd, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" delete_keys')
        winreg.CloseKey(del_cmd)
        winreg.CloseKey(del_key)
        print("  ✓ Added 'Delete Keys from Card'")

        # 5. Change Card PIN
        pin_key = winreg.CreateKey(shell_key, "changepin")
        winreg.SetValueEx(pin_key, "", 0, winreg.REG_SZ, "Change Card PIN")
        winreg.SetValueEx(pin_key, "MUIVerb", 0, winreg.REG_SZ, "Change Card PIN")
        pin_cmd = winreg.CreateKey(pin_key, "command")
        winreg.SetValue(pin_cmd, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" change_pin')
        winreg.CloseKey(pin_cmd)
        winreg.CloseKey(pin_key)
        print("  ✓ Added 'Change Card PIN'")

        winreg.CloseKey(shell_key)
        winreg.CloseKey(main_key)

        # DISABLED - PFX Import feature incomplete
        # # 6. AEPGP: Import PFX (only for .pfx and .p12 files)
        # # Register for .pfx files
        # pfx_importkey = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r".pfx\shell\AEPGP_ImportPFX")
        # winreg.SetValueEx(pfx_importkey, "MUIVerb", 0, winreg.REG_SZ, "AEPGP: Import PFX to Card")
        # pfx_cmd_key = winreg.CreateKey(pfx_importkey, "command")
        # winreg.SetValue(pfx_cmd_key, "", winreg.REG_SZ, f'"{python_exe}" "{import_pfx_handler}" "%1"')
        # winreg.CloseKey(pfx_cmd_key)
        # winreg.CloseKey(pfx_importkey)
        #
        # # Register for .p12 files
        # p12_importkey = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, r".p12\shell\AEPGP_ImportPFX")
        # winreg.SetValueEx(p12_importkey, "MUIVerb", 0, winreg.REG_SZ, "AEPGP: Import PFX to Card")
        # p12_cmd_key = winreg.CreateKey(p12_importkey, "command")
        # winreg.SetValue(p12_cmd_key, "", winreg.REG_SZ, f'"{python_exe}" "{import_pfx_handler}" "%1"')
        # winreg.CloseKey(p12_cmd_key)
        # winreg.CloseKey(p12_importkey)
        # print("  ✓ Added 'AEPGP: Import PFX' for .pfx and .p12 files")

        print("✓ Installed AEPGP cascading menu for all files")
        return True

    except Exception as e:
        print(f"✗ Failed to install cascading menu: {e}")
        import traceback
        traceback.print_exc()
        return False


def install_cascading_menu_for_desktop(launcher):
    """
    Install cascading submenu for Desktop background.

    Creates structure:
    Right-click Desktop → AEPGP →
        ├── Generate Keys in Card
        ├── Delete Keys from Card
        └── Change Card PIN

    All commands route through aepgp_launch.py (single registered path).

    Raises TypeError if a legacy handlers-tuple is passed instead of a
    launcher path string (guards against callers using the old signature).
    """
    if isinstance(launcher, (list, tuple)):
        raise TypeError(
            "install_cascading_menu_for_desktop() no longer accepts a handlers "
            "tuple. Pass the launcher script path string from get_launcher_path()."
        )

    try:
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        # Create main AEPGP submenu for desktop background
        main_key_path = r"Directory\Background\shell\AEPGP"
        main_key = winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, main_key_path)

        # Set submenu text and make it a cascading menu
        winreg.SetValueEx(main_key, "MUIVerb", 0, winreg.REG_SZ, "AEPGP")
        # Empty SubCommands tells Windows to use shell subkeys
        winreg.SetValueEx(main_key, "SubCommands", 0, winreg.REG_SZ, "")

        # Create shell subkey for submenu items
        shell_key = winreg.CreateKey(main_key, "shell")

        # 1. Generate Keys in Card
        genkeys_key = winreg.CreateKey(shell_key, "generatekeys")
        winreg.SetValueEx(genkeys_key, "", 0, winreg.REG_SZ, "Generate Keys in Card")
        winreg.SetValueEx(genkeys_key, "MUIVerb", 0, winreg.REG_SZ, "Generate Keys in Card")
        genkeys_cmd_key = winreg.CreateKey(genkeys_key, "command")
        winreg.SetValue(genkeys_cmd_key, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" generate_keys')
        winreg.CloseKey(genkeys_cmd_key)
        winreg.CloseKey(genkeys_key)
        print("  ✓ Added 'Generate Keys in Card' to desktop menu")

        # 2. Delete Keys from Card
        delkeys_key = winreg.CreateKey(shell_key, "deletekeys")
        winreg.SetValueEx(delkeys_key, "", 0, winreg.REG_SZ, "Delete Keys from Card")
        winreg.SetValueEx(delkeys_key, "MUIVerb", 0, winreg.REG_SZ, "Delete Keys from Card")
        delkeys_cmd_key = winreg.CreateKey(delkeys_key, "command")
        winreg.SetValue(delkeys_cmd_key, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" delete_keys')
        winreg.CloseKey(delkeys_cmd_key)
        winreg.CloseKey(delkeys_key)
        print("  ✓ Added 'Delete Keys from Card' to desktop menu")

        # 3. Change Card PIN
        changepin_key = winreg.CreateKey(shell_key, "changepin")
        winreg.SetValueEx(changepin_key, "", 0, winreg.REG_SZ, "Change Card PIN")
        winreg.SetValueEx(changepin_key, "MUIVerb", 0, winreg.REG_SZ, "Change Card PIN")
        changepin_cmd_key = winreg.CreateKey(changepin_key, "command")
        winreg.SetValue(changepin_cmd_key, "", winreg.REG_SZ, f'"{python_exe}" "{launcher}" change_pin')
        winreg.CloseKey(changepin_cmd_key)
        winreg.CloseKey(changepin_key)
        print("  ✓ Added 'Change Card PIN' to desktop menu")

        winreg.CloseKey(shell_key)
        winreg.CloseKey(main_key)

        print("✓ Installed AEPGP cascading menu for desktop background")
        return True

    except Exception as e:
        print(f"✗ Failed to install desktop cascading menu: {e}")
        import traceback
        traceback.print_exc()
        return False


def install_com_shell_ext(launcher):
    """Compile and register the C# COM shell extension for Windows 11 primary menu.

    On success the AEPGP submenu appears in the *primary* Windows 11 right-click
    menu (not hidden under 'Show more options').  On Windows 10 the COM handler
    fires alongside the existing shell-verb entries — both work fine together.

    Steps:
      1. Locate com_shell_ext/AEPGPContextMenu.cs (relative to this script).
      2. Find csc.exe (Framework64 / Framework).
      3. Compile: csc /target:library /platform:x64 /out:...dll ...cs
      4. Find RegAsm.exe.
      5. Register: RegAsm.exe ...dll /codebase /nologo
      6. Write LauncherPath, PythonPath, DllPath to HKLM\\SOFTWARE\\AEPGP\\ContextMenu.

    Non-fatal: returns False (with a warning) if any step fails so the rest of
    the installation can still complete.
    """
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        cs_path  = os.path.join(script_dir, "com_shell_ext", "AEPGPContextMenu.cs")
        dll_path = os.path.join(script_dir, "com_shell_ext", "AEPGPContextMenu.dll")

        if not os.path.isfile(cs_path):
            print(f"  ⚠ COM shell extension source not found: {cs_path}")
            print("    Windows 11 primary menu will not be available.")
            return False

        # ── Step 1: find csc.exe ──────────────────────────────────────────
        csc = _find_dotnet_tool("csc.exe")
        if csc is None:
            print("  ⚠ csc.exe not found — .NET Framework 4.x may not be installed.")
            print("    Windows 11 primary menu will not be available.")
            return False
        print(f"  Found csc.exe: {csc}")

        # ── Step 2: compile ───────────────────────────────────────────────
        compile_result = subprocess.run(
            [csc, "/target:library", "/platform:x64",
             f"/out:{dll_path}", cs_path],
            capture_output=True, text=True
        )
        if compile_result.returncode != 0:
            print(f"  ✗ Compilation failed (exit {compile_result.returncode}):")
            for line in (compile_result.stdout + compile_result.stderr).splitlines():
                print(f"      {line}")
            return False
        print("  ✓ Compiled AEPGPContextMenu.dll")

        # ── Step 3: find RegAsm.exe ───────────────────────────────────────
        regasm = _find_dotnet_tool("RegAsm.exe")
        if regasm is None:
            print("  ⚠ RegAsm.exe not found.")
            return False
        print(f"  Found RegAsm.exe: {regasm}")

        # ── Step 4: register ──────────────────────────────────────────────
        reg_result = subprocess.run(
            [regasm, dll_path, "/codebase", "/nologo"],
            capture_output=True, text=True
        )
        if reg_result.returncode != 0:
            print(f"  ✗ Registration failed (exit {reg_result.returncode}):")
            for line in (reg_result.stdout + reg_result.stderr).splitlines():
                print(f"      {line}")
            return False
        print("  ✓ Registered COM shell extension")

        # ── Step 5: write registry paths for the DLL to read at runtime ──
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        with winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\AEPGP\ContextMenu") as k:
            winreg.SetValueEx(k, "LauncherPath", 0, winreg.REG_SZ, launcher)
            winreg.SetValueEx(k, "PythonPath",   0, winreg.REG_SZ, python_exe)
            winreg.SetValueEx(k, "DllPath",      0, winreg.REG_SZ, dll_path)

        print("  ✓ Wrote registry paths (HKLM\\SOFTWARE\\AEPGP\\ContextMenu)")
        print("✓ Installed COM shell extension for Windows 11 primary menu")
        return True

    except Exception as e:
        print(f"  ✗ COM shell extension install failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def set_installed_version(version):
    """Store the installed version in registry."""
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, VERSION_REG_KEY)
        winreg.SetValueEx(key, VERSION_VALUE_NAME, 0, winreg.REG_SZ, version)
        winreg.CloseKey(key)
        print(f"✓ Registered version: {version}")
    except Exception as e:
        print(f"Warning: Could not store version: {e}")


def create_debug_log():
    """Create a fresh debug log file"""
    try:
        temp_dir = os.environ.get('TEMP', os.environ.get('TMP', 'C:\\Temp'))
        log_file = os.path.join(temp_dir, 'aepgp_debug.log')

        # Remove old log if it exists
        if os.path.exists(log_file):
            os.remove(log_file)

        # Create empty log file
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"AEPGP Debug Log\n")
            f.write(f"Created during installation of version {CURRENT_VERSION}\n")
            f.write(f"{'=' * 80}\n\n")

        print(f"  ✓ Created debug log: {log_file}")
        return True
    except Exception as e:
        print(f"  ! Warning: Could not create debug log: {e}")
        return False


def install_visibility_watcher_startup(watcher_script):
    """Install the visibility watcher to run at user logon."""
    try:
        python_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(python_exe):
            python_exe = sys.executable

        run_key = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run"
        )
        winreg.SetValueEx(
            run_key,
            "AEPGPVisibilityWatcher",
            0,
            winreg.REG_SZ,
            f'"{python_exe}" "{watcher_script}"'
        )
        winreg.CloseKey(run_key)
        print("  ✓ Installed visibility watcher startup entry")
        return True
    except Exception as e:
        print(f"  ! Warning: Could not install watcher startup: {e}")
        return False


def main():
    """Main installation function"""
    print("=" * 70)
    print("AEPGP Windows Context Menu Installer - Cascading Menu Version")
    print(f"Version {CURRENT_VERSION}")
    print("=" * 70)

    # Check if running on Windows
    if sys.platform != 'win32':
        print("\nERROR: This installer is only for Windows operating systems.")
        print("Press Enter to exit...")
        input()
        sys.exit(1)

    # Check for admin privileges
    if not is_admin():
        print("\nThis installer requires Administrator privileges.")
        print("Requesting elevation...")
        if elevate_privileges():
            sys.exit(0)  # Exit this instance, elevated instance will run
        else:
            print("\nERROR: Could not obtain Administrator privileges.")
            print("Please run this script as Administrator.")
            print("\nPress Enter to exit...")
            input()
            sys.exit(1)

    print("\nRunning with Administrator privileges ✓")

    # Locate the launcher script and verify all handlers are present.
    try:
        launcher = get_launcher_path()
        print(f"\nFound launcher: {launcher}")
    except FileNotFoundError as e:
        print(f"\nERROR: {e}")
        print("\nPress Enter to exit...")
        input()
        sys.exit(1)

    # Install menu items
    print("\n" + "=" * 70)
    print("Installing AEPGP cascading context menu...")
    print("=" * 70)

    all_files_ok = install_cascading_menu_for_all_files(launcher)
    desktop_ok = install_cascading_menu_for_desktop(launcher)

    # Install COM shell extension for Windows 11 primary context menu
    print("\n" + "=" * 70)
    print("Installing COM shell extension (Windows 11 primary menu)...")
    print("=" * 70)
    com_ok = install_com_shell_ext(launcher)

    # Create fresh debug log file
    create_debug_log()

    # Install visibility watcher startup entry
    watcher_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "visibility_watcher.py")
    watcher_ok = install_visibility_watcher_startup(watcher_script)

    # Store version information
    if all_files_ok and desktop_ok:
        set_installed_version(CURRENT_VERSION)

    # Summary
    print("\n" + "=" * 70)
    if all_files_ok and desktop_ok:
        print("Installation completed successfully! ✓")
        print(f"\nInstalled version: {CURRENT_VERSION}")
        print("\nHow to use:")
        print("  Right-click any file → AEPGP →")
        print("    • Encrypt File")
        print("    • Decrypt File")
        print("    • Generate Keys in Card")
        print("    • Delete Keys from Card")
        print("    • Change Card PIN")
        print("  Right-click Desktop → AEPGP →")
        print("    • Generate Keys in Card")
        print("    • Delete Keys from Card")
        print("    • Change Card PIN")
        if is_windows_11():
            if com_ok:
                print("\nWindows 11: AEPGP is available in the PRIMARY context menu ✓")
                print("  (COM shell extension registered successfully)")
            else:
                print("\nWINDOWS 11 NOTICE:")
                print("  COM shell extension could not be installed.")
                print("  AEPGP entries appear only under 'Show more options'.")
                print("  Workaround: hold SHIFT while right-clicking to open")
                print("  the full legacy menu where AEPGP is immediately visible.")
                ctypes.windll.user32.MessageBoxW(
                    None,
                    "AEPGP has been installed successfully.\n\n"
                    "Windows 11 Notice\n"
                    "─────────────────\n"
                    "The COM shell extension could not be installed, so AEPGP\n"
                    "entries appear only under 'Show more options'.\n\n"
                    "Workaround: hold SHIFT while right-clicking any file or\n"
                    "the desktop to open the full legacy menu where AEPGP\n"
                    "entries are immediately visible.\n\n"
                    "Check that .NET Framework 4.x is installed and re-run\n"
                    "the installer as Administrator to retry.",
                    "Windows 11 Compatibility Notice",
                    0x40,  # MB_ICONINFORMATION
                )
        else:
            if not com_ok:
                print("\nNOTE: On Windows 11, AEPGP appears in 'Show more options'")
                print("      (COM extension install failed — shell-verb fallback active)")
    else:
        print("Installation completed with errors.")
        print("Some context menu items may not have been installed.")
        if not all_files_ok:
            print("  ✗ File context menu failed")
        if not desktop_ok:
            print("  ✗ Desktop context menu failed")
        if not com_ok:
            print("  ⚠ COM shell extension not installed (Windows 11 primary menu unavailable)")

    print("\nPress Enter to exit...")
    input()


if __name__ == "__main__":
    main()