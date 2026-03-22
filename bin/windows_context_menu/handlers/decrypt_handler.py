"""
AEPGP File Decryption Handler

This script is called when the user right-clicks an encrypted file and selects
"Decrypt with AEPGP" from the context menu.

Uses RSA+AES hybrid decryption with AEPGP card's private key via APDU.
"""

import sys
import os

# Add parent directory to path to import card_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_utils
from debug_logger import get_logger
from rsa_decrypt import decrypt_file_with_card

# Initialize logger
logger = get_logger()


def decrypt_file(filepath):
    """
    Decrypt a file using the AEPGP card's private key.

    This function uses direct APDU communication with the card:
    - Reads encrypted file (.enc format)
    - Verifies PIN via APDU
    - Decrypts AES key using card's private key via DECIPHER APDU
    - Decrypts file data using AES-256-GCM
    - Creates decrypted output file

    Args:
        filepath: Path to the encrypted file (.enc)
    """
    logger.log_operation_start("Decryption", filepath)
    logger.log_system_info()

    # Verify file exists
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        card_utils.show_error_dialog(
            f"File not found:\n{filepath}",
            "AEPGP Decryption Error"
        )
        logger.log_operation_end("Decryption", False, "File not found")
        return

    logger.info(f"File exists, size: {os.path.getsize(filepath)} bytes")

    card_present, visibility_error = card_utils.sync_encrypted_file_visibility(filepath)
    if not card_present:
        logger.info(f"Card not present, encrypted file hidden: {visibility_error}")
        card_utils.show_error_dialog(
            f"AEPGP card not found:\n\n{visibility_error}\n\n"
            "Please insert your AEPGP card and try again.",
            "AEPGP Decryption Error"
        )
        logger.log_operation_end("Decryption", False, "Card not found")
        return

    # Prepare output filename (remove .enc extension)
    if filepath.lower().endswith('.enc'):
        output_path = filepath[:-4]  # Remove .enc
    else:
        output_path = filepath + ".decrypted"

    # Check if output file already exists
    if os.path.exists(output_path):
        overwrite = card_utils.show_question_dialog(
            f"The decrypted file already exists:\n\n{output_path}\n\n"
            "Do you want to overwrite it?",
            "File Already Exists"
        )
        if not overwrite:
            logger.info("User cancelled overwrite")
            logger.log_operation_end("Decryption", False, "User cancelled")
            return

    try:
        logger.info("Starting RSA+AES hybrid decryption with AEPGP card...")

        # Prompt user for PIN
        import tkinter as tk
        from tkinter import simpledialog

        logger.info("Prompting for PIN...")
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        root.attributes('-topmost', True)  # Make dialog appear on top

        pin = simpledialog.askstring(
            "PIN Required",
            "Enter your AEPGP card PIN:",
            show='*',
            parent=root
        )

        root.destroy()

        if pin is None or pin == "":
            logger.info("User cancelled PIN entry")
            logger.log_operation_end("Decryption", False, "User cancelled")
            return

        # Decrypt the file using RSA+AES hybrid decryption
        success, error_msg = decrypt_file_with_card(filepath, output_path, pin=pin)

        if success:
            # Success!
            logger.info(f"Decryption successful, output: {output_path}")

            card_utils.show_info_dialog(
                f"Decrypted file created:\n\n{output_path}",
                "Decryption Successful"
            )
            logger.log_operation_end("Decryption", True)
        else:
            # Decryption failed
            logger.error(f"Decryption failed: {error_msg}")

            # Provide helpful error messages
            if "PIN" in error_msg or "retries" in error_msg:
                error_display = (
                    f"PIN verification failed:\n\n{error_msg}\n\n"
                    f"Please ensure you are using the correct PIN."
                )
            elif "Card not found" in error_msg:
                error_display = (
                    f"AEPGP card not found:\n\n{error_msg}\n\n"
                    f"Please insert your AEPGP card and try again."
                )
            elif "No decryption key found on card" in error_msg or "generate keys" in error_msg.lower():
                error_display = error_msg
                card_utils.show_error_dialog(error_display, "Keys Not Generated")
                logger.log_operation_end("Decryption", False, error_msg)
                return
            else:
                error_display = f"Decryption failed:\n\n{error_msg}"

            card_utils.show_error_dialog(error_display, "Decryption Error")
            logger.log_operation_end("Decryption", False, error_msg)

    except Exception as e:
        logger.error("Exception during decryption", e)
        import traceback
        logger.error(traceback.format_exc())
        card_utils.show_error_dialog(
            f"Error during decryption:\n\n{str(e)}",
            "Decryption Error"
        )
        logger.log_operation_end("Decryption", False, str(e))


def main():
    """Main entry point for the decryption handler"""
    if len(sys.argv) < 2:
        card_utils.show_error_dialog(
            "No file specified for decryption.\n\n"
            "This script should be called from Windows Explorer context menu.",
            "AEPGP Decryption"
        )
        sys.exit(1)

    filepath = sys.argv[1]
    decrypt_file(filepath)


if __name__ == "__main__":
    main()
