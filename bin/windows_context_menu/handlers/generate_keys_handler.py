"""
AEPGP Generate Keys in Card Handler

This script generates RSA key pairs directly on the AEPGP card.
Called from Windows Explorer context menu (no file required).
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_utils
from debug_logger import get_logger

# Initialize logger
logger = get_logger()


def generate_keys():
    """
    Generate RSA-2048 key pair on the AEPGP card.

    Flow:
      1. Connect to card
      2. Check if a key already exists + read existing alias
      3. Single confirmation dialog (shows alias + timing warning)
      4. Prompt for new key alias
      5. Prompt for Admin PIN (masked)
      6. Verify Admin PIN via APDU
      7. Clear old alias (if key existed), show progress dialog
      8. Generate key pair via APDU
      9. Verify key readable, store alias, show success
    """
    logger.log_operation_start("Generate Keys", "AEPGP Card")
    logger.log_system_info()

    try:
        # --- Step 1: Connect to card ---
        logger.info("Connecting to AEPGP card...")
        card, error = card_utils.find_aepgp_card()
        if error:
            error_msg = f"AEPGP card not found: {error}"
            logger.error(error_msg)
            card_utils.show_error_dialog(
                f"AEPGP card not found:\n\n{error}\n\n"
                "Please ensure:\n"
                "1. The card is inserted\n"
                "2. No other application is using the card",
                "Connection Error"
            )
            logger.log_operation_end("Generate Keys", False, error_msg)
            return

        logger.info(f"Card found: {card.reader}")

        try:
            # --- Step 2: Check existing key + read alias ---
            card.select_applet()

            read_apdu = [0x00, 0x47, 0x81, 0x00, 0x02, 0xB8, 0x00, 0x00]
            response, sw1, sw2 = card.connection.transmit(read_apdu)
            card._log_apdu(read_apdu, response, sw1, sw2)

            if sw1 == 0x61 or (sw1 == 0x90 and sw2 == 0x00):
                key_exists = True
            elif sw1 == 0x6A and sw2 == 0x88:
                key_exists = False
            else:
                error_msg = f"Failed to check existing key: SW={sw1:02X}{sw2:02X}"
                logger.error(error_msg)
                card_utils.show_error_dialog(
                    f"Could not verify existing key state.\n\nStatus: {sw1:02X}{sw2:02X}",
                    "Key Check Error"
                )
                logger.log_operation_end("Generate Keys", False, error_msg)
                return

            existing_alias = card_utils.get_key_alias(card) if key_exists else None

            # --- Step 3: Single confirmation dialog ---
            if key_exists:
                alias_display = existing_alias if existing_alias else "Unknown"
                confirm_message = (
                    f"A key pair already exists on this card.\n"
                    f"Existing alias: {alias_display}\n\n"
                    "This will OVERWRITE the existing key pair. Any files encrypted\n"
                    "with the old key will no longer be decryptable!\n\n"
                    "Key generation takes 30-60 seconds — do not remove the card.\n\n"
                    "Do you want to continue?"
                )
            else:
                confirm_message = (
                    "This will generate a new RSA-2048 key pair on your AEPGP card.\n\n"
                    "Slot: Decryption/Encryption\n"
                    "Algorithm: RSA-2048\n\n"
                    "Key generation takes 30-60 seconds — do not remove the card.\n\n"
                    "Do you want to continue?"
                )

            if not card_utils.show_question_dialog(confirm_message, "Generate Keys in Card"):
                logger.info("User cancelled key generation")
                logger.log_operation_end("Generate Keys", False, "User cancelled")
                return

            # --- Step 4: Prompt for alias ---
            alias = card_utils.show_input_dialog(
                "Enter a name (alias) for this key pair:\n"
                "e.g. 'Work Card', 'John Doe', 'Personal'",
                "Key Pair Alias"
            )
            if not alias:
                logger.info("User cancelled alias entry")
                card_utils.show_error_dialog(
                    "Key alias is required. Operation cancelled.",
                    "Key Generation Cancelled"
                )
                logger.log_operation_end("Generate Keys", False, "Alias required")
                return
            try:
                alias_bytes = alias.encode("ascii")
            except UnicodeEncodeError:
                card_utils.show_error_dialog(
                    "Alias must contain only ASCII characters.",
                    "Alias Error"
                )
                logger.log_operation_end("Generate Keys", False, "Alias not ASCII")
                return
            if len(alias_bytes) > 255:
                card_utils.show_error_dialog(
                    "Alias is too long (max 255 characters).",
                    "Alias Error"
                )
                logger.log_operation_end("Generate Keys", False, "Alias too long")
                return

            # --- Step 5: Prompt for Admin PIN (masked) ---
            import tkinter as tk
            from tkinter import simpledialog

            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            admin_pin = simpledialog.askstring(
                "Admin PIN",
                "Enter the Admin PIN for your AEPGP card:\n"
                "(Default is 12345678 if you have not changed it)",
                show='*',
                parent=root
            )
            root.destroy()

            if not admin_pin:
                logger.info("User cancelled admin PIN entry")
                logger.log_operation_end("Generate Keys", False, "User cancelled admin PIN")
                return

            # --- Step 6: Verify Admin PIN ---
            logger.info("Verifying admin PIN...")
            pin_bytes = [ord(c) for c in admin_pin]
            verify_apdu = [0x00, 0x20, 0x00, 0x83, len(pin_bytes)] + pin_bytes
            response, sw1, sw2 = card.connection.transmit(verify_apdu)
            card._log_apdu(verify_apdu, response, sw1, sw2)

            if sw1 == 0x63:
                retries = sw2 & 0x0F
                error_msg = f"Admin PIN incorrect: {retries} retries remaining"
                logger.error(error_msg)
                card_utils.show_error_dialog(
                    f"Incorrect Admin PIN.\n\n"
                    f"{retries} attempts remaining before the card is locked.",
                    "PIN Verification Error"
                )
                logger.log_operation_end("Generate Keys", False, error_msg)
                return
            elif sw1 != 0x90 or sw2 != 0x00:
                error_msg = f"Admin PIN verification failed: SW={sw1:02X}{sw2:02X}"
                logger.error(error_msg)
                card_utils.show_error_dialog(
                    f"Admin PIN verification failed.\nStatus: {sw1:02X}{sw2:02X}",
                    "PIN Verification Error"
                )
                logger.log_operation_end("Generate Keys", False, error_msg)
                return

            logger.info("Admin PIN verified")

            # --- Step 7: Clear old alias + show progress ---
            if key_exists:
                card_utils.clear_key_alias(card)

            card_utils.show_info_dialog(
                "Generating RSA-2048 key pair on card...\n\n"
                "This will take 30-60 seconds.\n"
                "Please wait and do NOT remove the card.",
                "Generating Keys — Please Wait"
            )

            # --- Step 8: Generate key pair (APDU 00 47 80 00 02 B8 00 00) ---
            logger.info("Sending GENERATE KEY APDU (30-60 seconds)...")
            gen_apdu = [0x00, 0x47, 0x80, 0x00, 0x02, 0xB8, 0x00, 0x00]
            response, sw1, sw2 = card.connection.transmit(gen_apdu)
            card._log_apdu(gen_apdu, response, sw1, sw2)

            # Handle GET RESPONSE (SW=61XX means more data available)
            if sw1 == 0x61:
                logger.info(f"Fetching remaining {sw2} bytes with GET RESPONSE...")
                get_response = [0x00, 0xC0, 0x00, 0x00, sw2]
                response2, sw1, sw2 = card.connection.transmit(get_response)
                card._log_apdu(get_response, response2, sw1, sw2)
                response = response + response2

            if sw1 != 0x90 or sw2 != 0x00:
                error_msg = f"Key generation failed: SW={sw1:02X}{sw2:02X}"
                logger.error(error_msg)
                card_utils.show_error_dialog(
                    f"Key generation failed.\n\nStatus: {sw1:02X}{sw2:02X}\n\n"
                    "Please try again. If the problem persists, try resetting the card.",
                    "Key Generation Error"
                )
                logger.log_operation_end("Generate Keys", False, error_msg)
                return

            logger.info(f"Key generation successful — {len(response)} bytes of public key data received")

            # --- Step 9: Verify key readable + store alias + success ---
            logger.info("Verifying generated key is readable...")
            read_apdu = [0x00, 0x47, 0x81, 0x00, 0x02, 0xB8, 0x00, 0x00]
            response, sw1, sw2 = card.connection.transmit(read_apdu)
            card._log_apdu(read_apdu, response, sw1, sw2)

            if sw1 not in (0x90, 0x61):
                logger.warning(f"Key verify returned SW={sw1:02X}{sw2:02X} but generation succeeded")

            if not card_utils.set_key_alias(card, alias):
                card_utils.show_error_dialog(
                    "Keys generated but failed to store alias on the card.",
                    "Alias Error"
                )
                logger.log_operation_end("Generate Keys", False, "Alias store failed")
                return

            card_utils.show_info_dialog(
                "RSA-2048 key pair generated successfully!\n\n"
                f"Alias:     {alias}\n"
                "Slot:      Decryption/Encryption\n"
                "Algorithm: RSA-2048\n\n"
                "The private key is stored securely on your card and will never leave it.\n"
                "You can now use this card to encrypt and decrypt files.",
                "Key Generation Successful"
            )
            logger.log_operation_end("Generate Keys", True)

        finally:
            card.disconnect()

    except Exception as e:
        logger.error("Exception during key generation", e)
        import traceback
        logger.error(traceback.format_exc())
        card_utils.show_error_dialog(
            f"Error during key generation:\n\n{str(e)}",
            "Key Generation Error"
        )
        logger.log_operation_end("Generate Keys", False, str(e))


def main():
    """Main entry point for the key generation handler"""
    generate_keys()


if __name__ == "__main__":
    main()
