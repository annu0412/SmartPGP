"""
AEPGP Change PIN Handler

Changes the User PIN on the AEPGP card using the standard OpenPGP
CHANGE REFERENCE DATA command (INS=0x24).  No GPG installation required.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_utils
from debug_logger import get_logger

logger = get_logger()


def change_pin():
    """
    Change the User PIN on the AEPGP card.

    Uses CHANGE REFERENCE DATA APDU (00 24 00 81 Lc [old_pin || new_pin]).
    The applet splits the data at the stored old-PIN length, so the host
    simply concatenates old and new PIN bytes.

    SW responses from SmartPGP processChangeReferenceData:
      9000  success
      6982  wrong current PIN (SmartPGP-specific — standard would be 63CX)
      6983  PIN blocked
      6700  wrong length (new PIN < 6 or > 127 bytes)
      6A86  wrong P1/P2
    """
    logger.log_operation_start("Change PIN", "AEPGP Card")
    logger.log_system_info()

    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        card_utils.show_info_dialog(
            "This will change the User PIN on your AEPGP card.\n\n"
            "You will need to enter:\n"
            "  1. Your current PIN  (default: 123456)\n"
            "  2. Your new PIN (twice for confirmation)\n\n"
            "Minimum PIN length: 6 characters",
            "Change AEPGP Card PIN"
        )

        # --- Prompt for current PIN ---
        current_pin = simpledialog.askstring(
            "Current PIN",
            "Enter your current AEPGP card PIN:\n(default: 123456)",
            show='*',
            parent=root
        )
        if not current_pin:
            logger.info("User cancelled current PIN entry")
            logger.log_operation_end("Change PIN", False, "User cancelled")
            root.destroy()
            return

        # --- Prompt for new PIN ---
        new_pin = simpledialog.askstring(
            "New PIN",
            "Enter your new PIN:\n(6–127 characters)",
            show='*',
            parent=root
        )
        if not new_pin:
            logger.info("User cancelled new PIN entry")
            logger.log_operation_end("Change PIN", False, "User cancelled")
            root.destroy()
            return

        # --- Confirm new PIN ---
        confirm_pin = simpledialog.askstring(
            "Confirm New PIN",
            "Re-enter your new PIN to confirm:",
            show='*',
            parent=root
        )
        root.destroy()

        if not confirm_pin:
            logger.info("User cancelled PIN confirmation")
            logger.log_operation_end("Change PIN", False, "User cancelled")
            return

        # --- Validate ---
        if new_pin != confirm_pin:
            card_utils.show_error_dialog(
                "The new PIN and confirmation do not match.\n\nPlease try again.",
                "PIN Mismatch"
            )
            logger.log_operation_end("Change PIN", False, "PIN mismatch")
            return

        if len(new_pin) < 6:
            card_utils.show_error_dialog(
                f"New PIN is too short ({len(new_pin)} characters).\n\nMinimum: 6 characters.",
                "Invalid PIN Length"
            )
            logger.log_operation_end("Change PIN", False, "New PIN too short")
            return

        if len(new_pin) > 127:
            card_utils.show_error_dialog(
                f"New PIN is too long ({len(new_pin)} characters).\n\nMaximum: 127 characters.",
                "Invalid PIN Length"
            )
            logger.log_operation_end("Change PIN", False, "New PIN too long")
            return

        # --- Connect to card ---
        logger.info("Connecting to AEPGP card...")
        card, error = card_utils.find_aepgp_card()
        if error:
            card_utils.show_error_dialog(
                f"AEPGP card not found:\n\n{error}\n\nPlease insert your card and try again.",
                "Card Not Found"
            )
            logger.log_operation_end("Change PIN", False, f"Card not found: {error}")
            return

        logger.info(f"Card found: {card.reader}")

        try:
            card.select_applet()

            # --- CHANGE REFERENCE DATA: 00 24 00 81 Lc [old_pin || new_pin] ---
            # The applet reads data.user_pin_length bytes as the old PIN and
            # treats the remainder as the new PIN — no explicit length separator needed.
            current_bytes = list(current_pin.encode('latin-1'))
            new_bytes     = list(new_pin.encode('latin-1'))
            payload       = current_bytes + new_bytes

            change_cmd = [0x00, 0x24, 0x00, 0x81, len(payload)] + payload
            logger.info("Sending CHANGE REFERENCE DATA APDU...")
            response, sw1, sw2 = card.connection.transmit(change_cmd)
            card._log_apdu(change_cmd, response, sw1, sw2)

            if sw1 == 0x90 and sw2 == 0x00:
                logger.info("PIN changed successfully")
                card_utils.show_info_dialog(
                    "PIN changed successfully!\n\n"
                    "Your new PIN is now active on the AEPGP card.\n"
                    "Please remember your new PIN.",
                    "PIN Change Successful"
                )
                logger.log_operation_end("Change PIN", True)

            elif sw1 == 0x69 and sw2 == 0x82:
                # SmartPGP returns 6982 for wrong PIN (same as processVerify)
                card_utils.show_error_dialog(
                    "Wrong current PIN.\n\n"
                    "The PIN was not changed.\n"
                    "Default User PIN is 123456 if you have not changed it.\n\n"
                    "Warning: too many wrong attempts will lock the card.",
                    "Wrong PIN"
                )
                logger.log_operation_end("Change PIN", False, "Wrong current PIN (SW=6982)")

            elif sw1 == 0x63:
                retries = sw2 & 0x0F
                card_utils.show_error_dialog(
                    f"Wrong current PIN.\n\n"
                    f"{retries} attempts remaining before the card is locked.",
                    "Wrong PIN"
                )
                logger.log_operation_end("Change PIN", False, f"Wrong PIN, {retries} retries left")

            elif sw1 == 0x69 and sw2 == 0x83:
                card_utils.show_error_dialog(
                    "The User PIN is blocked (too many wrong attempts).\n\n"
                    "Use your Admin PIN to reset it:\n"
                    "  Right-click desktop → AEPGP → Reset PIN with Admin PIN",
                    "PIN Blocked"
                )
                logger.log_operation_end("Change PIN", False, "PIN blocked (SW=6983)")

            elif sw1 == 0x67 and sw2 == 0x00:
                card_utils.show_error_dialog(
                    "Wrong data length.\n\n"
                    "The new PIN must be 6–127 characters.\n"
                    "Also check your current PIN is correct.",
                    "Wrong Length"
                )
                logger.log_operation_end("Change PIN", False, f"Wrong length SW=6700")

            else:
                card_utils.show_error_dialog(
                    f"PIN change failed.\n\nError code: {sw1:02X}{sw2:02X}",
                    "PIN Change Failed"
                )
                logger.log_operation_end("Change PIN", False, f"SW={sw1:02X}{sw2:02X}")

        finally:
            card.disconnect()
            logger.debug("Card disconnected")

    except Exception as e:
        logger.error("Exception during PIN change", e)
        import traceback
        logger.error(traceback.format_exc())
        card_utils.show_error_dialog(
            f"Error during PIN change:\n\n{str(e)}",
            "PIN Change Error"
        )
        logger.log_operation_end("Change PIN", False, str(e))


def main():
    change_pin()


if __name__ == "__main__":
    main()
