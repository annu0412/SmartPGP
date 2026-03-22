"""
AEPGP Context Menu Dispatcher

This is the single entry point registered in the Windows registry for all
AEPGP context menu actions.  By funnelling all commands through one file,
only ONE absolute path is stored in the registry.  The handlers directory is
resolved at runtime relative to __file__, so renaming parent directories only
requires updating the registry path for this one script rather than for every
individual handler.

Usage (called by Windows shell):
    pythonw aepgp_launch.py encrypt    "<file>"
    pythonw aepgp_launch.py decrypt    "<file>"
    pythonw aepgp_launch.py generate_keys
    pythonw aepgp_launch.py delete_keys
    pythonw aepgp_launch.py change_pin
"""

import sys
import os

# ---------------------------------------------------------------------------
# Remote debugging support (VSCode / debugpy)
# Set the environment variable AEPGP_DEBUG=1 before triggering the context
# menu, then attach VSCode using the "Attach to AEPGP" launch config.
# ---------------------------------------------------------------------------
if os.environ.get("AEPGP_DEBUG") == "1":
    try:
        import debugpy
        debugpy.listen(("localhost", 5678))
        # Show a message box so you know when to click "Attach" in VSCode
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            "AEPGP debug mode: waiting for VSCode debugger on port 5678.\n\n"
            "Switch to VSCode and press F5 with 'Attach to AEPGP' selected.",
            "AEPGP Debug",
            0x40,  # MB_ICONINFORMATION
        )
        debugpy.wait_for_client()
    except ImportError:
        pass  # debugpy not installed — run normally

# Resolve the handlers directory relative to this file — never hardcode paths.
HANDLERS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "handlers")
sys.path.insert(0, HANDLERS_DIR)

_ACTIONS = {
    "encrypt":       "encrypt_handler",
    "decrypt":       "decrypt_handler",
    "generate_keys": "generate_keys_handler",
    "delete_keys":   "delete_keys_handler",
    "change_pin":    "change_pin_handler",
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in _ACTIONS:
        # Show a user-visible error rather than a silent exit.
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                None,
                f"AEPGP: unknown action '{sys.argv[1] if len(sys.argv) > 1 else '(none)'}'\n\n"
                "This is an installation problem. Please reinstall AEPGP.",
                "AEPGP Launch Error",
                0x10,  # MB_ICONERROR
            )
        except Exception:
            pass
        sys.exit(1)

    action = sys.argv[1]

    # Temporarily rebuild sys.argv so the handler sees only its own arguments:
    #   sys.argv[0] = dispatcher path (kept as-is)
    #   sys.argv[1] = optional file path (encrypt/decrypt), or nothing
    # We save and restore sys.argv so that repeated invocations in a test
    # harness (where modules are cached) do not see stale arguments.
    _saved_argv = sys.argv[:]
    sys.argv = [sys.argv[0]] + sys.argv[2:]
    try:
        module = __import__(_ACTIONS[action])
        module.main()
    finally:
        sys.argv = _saved_argv


if __name__ == "__main__":
    main()
