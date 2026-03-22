"""
AEPGP Delete Keys Handler

Factory-resets the AEPGP card using the standard OpenPGP commands:
  1. TERMINATE DF  (INS=0xE6) — requires Admin PIN, marks card as terminated
  2. ACTIVATE FILE (INS=0x44) — resets all keys, PINs and DOs to factory defaults

No GPG installation required.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_utils
from debug_logger import get_logger

logger = get_logger()


def delete_keys():
    """
    Factory-reset the AEPGP card.

    Requires the Admin PIN (not the User PIN) because TERMINATE DF calls
    assertAdmin() in the applet.  The sequence is:
      00 20 00 83 Lc [admin_pin]   — verify Admin PIN
      00 E6 00 00                  — TERMINATE DF  (marks card terminated)
      00 44 00 01                  — ACTIVATE FILE (resets keys + SM key)

    SW responses handled:
      9000  success
      6982  wrong PIN (SmartPGP-specific for wrong PIN)
      63CX  wrong PIN with retry count (standard)
      6983  PIN blocked
    """
    logger.log_operation_start("Delete Keys", "AEPGP Card")
    logger.log_system_info()

    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        # --- Step 1: Ask for Admin PIN ---
        logger.info("Prompting for Admin PIN...")
        admin_pin = simpledialog.askstring(
            "Admin PIN Required",
            "Enter the Admin PIN to factory-reset the card:\n"
            "(default Admin PIN: 12345678)\n\n"
            "WARNING: This will permanently delete ALL keys!",
            show='*',
            parent=root
        )
        root.destroy()

        if not admin_pin:
            logger.info("User cancelled Admin PIN entry")
            logger.log_operation_end("Delete Keys", False, "User cancelled")
            return

        # --- Step 2: Final confirmation ---
        if not card_utils.show_question_dialog(
            "WARNING: PERMANENT OPERATION\n\n"
            "This will factory-reset your AEPGP card:\n"
            "  • ALL cryptographic keys will be deleted\n"
            "  • All PINs reset to defaults (123456 / 12345678)\n"
            "  • Any encrypted files will be UNRECOVERABLE\n\n"
            "Are you absolutely sure?",
            "Confirm Factory Reset"
        ):
            logger.info("User cancelled factory reset")
            logger.log_operation_end("Delete Keys", False, "User cancelled")
            return

        # --- Step 3: Connect to card ---
        logger.info("Connecting to AEPGP card...")
        card, error = card_utils.find_aepgp_card()
        if error:
            card_utils.show_error_dialog(
                f"AEPGP card not found:\n\n{error}\n\nPlease insert your card and try again.",
                "Card Not Found"
            )
            logger.log_operation_end("Delete Keys", False, f"Card not found: {error}")
            return

        logger.info(f"Card found: {card.reader}")

        try:
            card.select_applet()

            # --- Step 4: Verify Admin PIN ---
            logger.info("Verifying Admin PIN...")
            pin_bytes = list(admin_pin.encode('latin-1'))
            verify_cmd = [0x00, 0x20, 0x00, 0x83, len(pin_bytes)] + pin_bytes
            response, sw1, sw2 = card.connection.transmit(verify_cmd)
            card._log_apdu(verify_cmd, response, sw1, sw2)

            if sw1 == 0x90 and sw2 == 0x00:
                logger.info("Admin PIN verified")

            elif sw1 == 0x69 and sw2 == 0x82:
                # SmartPGP returns 6982 for wrong PIN
                card_utils.show_error_dialog(
                    "Wrong Admin PIN.\n\n"
                    "Default Admin PIN is 12345678 if you have not changed it.\n\n"
                    "Warning: too many wrong attempts will lock the card.",
                    "Wrong Admin PIN"
                )
                logger.log_operation_end("Delete Keys", False, "Wrong Admin PIN (SW=6982)")
                return

            elif sw1 == 0x63:
                retries = sw2 & 0x0F
                card_utils.show_error_dialog(
                    f"Wrong Admin PIN.\n\n{retries} attempts remaining before the card is locked.",
                    "Wrong Admin PIN"
                )
                logger.log_operation_end("Delete Keys", False, f"Wrong Admin PIN, {retries} retries left")
                return

            elif sw1 == 0x69 and sw2 == 0x83:
                card_utils.show_error_dialog(
                    "The Admin PIN is blocked.\n\nThe card cannot be reset without a working Admin PIN.",
                    "Admin PIN Blocked"
                )
                logger.log_operation_end("Delete Keys", False, "Admin PIN blocked (SW=6983)")
                return

            else:
                card_utils.show_error_dialog(
                    f"Admin PIN verification failed.\n\nError code: {sw1:02X}{sw2:02X}",
                    "Verification Error"
                )
                logger.log_operation_end("Delete Keys", False, f"Admin PIN verify SW={sw1:02X}{sw2:02X}")
                return

            # --- Step 5: TERMINATE DF (00 E6 00 00) ---
            logger.info("Sending TERMINATE DF...")
            term_cmd = [0x00, 0xE6, 0x00, 0x00]
            response, sw1, sw2 = card.connection.transmit(term_cmd)
            card._log_apdu(term_cmd, response, sw1, sw2)

            if sw1 != 0x90 or sw2 != 0x00:
                card_utils.show_error_dialog(
                    f"TERMINATE DF failed.\n\nError code: {sw1:02X}{sw2:02X}\n\nCard was not reset.",
                    "Factory Reset Failed"
                )
                logger.log_operation_end("Delete Keys", False, f"TERMINATE DF SW={sw1:02X}{sw2:02X}")
                return

            logger.info("TERMINATE DF succeeded — card is now terminated")

            # --- Step 6: ACTIVATE FILE (00 44 00 01) — resets keys + SM key ---
            logger.info("Sending ACTIVATE FILE (P2=01 to reset SM key too)...")
            activate_cmd = [0x00, 0x44, 0x00, 0x01]
            response, sw1, sw2 = card.connection.transmit(activate_cmd)
            card._log_apdu(activate_cmd, response, sw1, sw2)

            if sw1 != 0x90 or sw2 != 0x00:
                card_utils.show_error_dialog(
                    f"ACTIVATE FILE failed.\n\nError code: {sw1:02X}{sw2:02X}\n\n"
                    "The card may be in a partially reset state. Try reinserting and retrying.",
                    "Factory Reset Failed"
                )
                logger.log_operation_end("Delete Keys", False, f"ACTIVATE FILE SW={sw1:02X}{sw2:02X}")
                return

            logger.info("ACTIVATE FILE succeeded — card is now factory reset")

        finally:
            card.disconnect()
            logger.debug("Card disconnected")

        card_utils.show_info_dialog(
            "Card factory reset successfully!\n\n"
            "All keys and data have been erased.\n\n"
            "Default User PIN:  123456\n"
            "Default Admin PIN: 12345678\n\n"
            "Generate new keys using 'Generate Keys in Card'.",
            "Factory Reset Successful"
        )
        logger.log_operation_end("Delete Keys", True)

    except Exception as e:
        logger.error("Exception during key deletion", e)
        import traceback
        logger.error(traceback.format_exc())
        card_utils.show_error_dialog(
            f"Error during factory reset:\n\n{str(e)}",
            "Delete Keys Error"
        )
        logger.log_operation_end("Delete Keys", False, str(e))


def main():
    delete_keys()


if __name__ == "__main__":
    main()
