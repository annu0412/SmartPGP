"""
AEPGP File Encryption Handler

This script is called when the user right-clicks a file and selects
"Encrypt with AEPGP" from the context menu.

Uses RSA+AES hybrid encryption with direct APDU access to AEPGP card.
"""

import sys
import os

# Add parent directory to path to import card_utils
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_utils
from debug_logger import get_logger
from rsa_crypto import encrypt_file_with_card_key

# Initialize logger
logger = get_logger()


def encrypt_file(filepath):
    """
    Encrypt a file using RSA+AES hybrid encryption with the AEPGP card's public key.

    This function uses direct APDU communication with the card:
    - Reads RSA public key directly from card via APDU (no GPG keyring)
    - Encrypts file using AES-256-GCM for performance
    - Encrypts AES key using RSA PKCS#1 v1.5 with card's public key
      (PKCS#1 v1.5 is required — the card PSO:DECIPHER cannot handle OAEP)
    - Creates .enc file that can be decrypted with the card's private key

    Args:
        filepath: Path to the file to encrypt
    """
    logger.log_operation_start("Encryption", filepath)
    logger.log_system_info()

    # Verify file exists
    if not os.path.exists(filepath):
        logger.error(f"File not found: {filepath}")
        card_utils.show_error_dialog(
            f"File not found:\n{filepath}",
            "AEPGP Encryption Error"
        )
        logger.log_operation_end("Encryption", False, "File not found")
        return

    logger.info(f"File exists, size: {os.path.getsize(filepath)} bytes")

    # Prepare output filename
    output_path = filepath + ".enc"

    # Check if output file already exists
    if os.path.exists(output_path):
        overwrite = card_utils.show_question_dialog(
            f"The encrypted file already exists:\n\n{output_path}\n\n"
            "Do you want to overwrite it?",
            "File Already Exists"
        )
        if not overwrite:
            logger.info("User cancelled overwrite")
            logger.log_operation_end("Encryption", False, "User cancelled")
            return

    try:
        logger.info("Starting RSA+AES hybrid encryption with AEPGP card...")

        # Encrypt the file using RSA+AES hybrid encryption
        success, error_msg = encrypt_file_with_card_key(filepath, output_path)

        if success:
            # Success!
            logger.info(f"Encryption successful, output: {output_path}")
            card_utils.sync_encrypted_file_visibility(output_path)

            # Get file sizes for display
            original_size = os.path.getsize(filepath)
            encrypted_size = os.path.getsize(output_path)

            card_utils.show_info_dialog(
                f"File encrypted successfully!\n\n"
                f"Original: {os.path.basename(filepath)} ({original_size:,} bytes)\n"
                f"Encrypted: {os.path.basename(output_path)} ({encrypted_size:,} bytes)\n\n"
                f"Location: {os.path.dirname(output_path)}\n\n"
                f"Encryption: RSA-2048 + AES-256-GCM\n"
                f"Security: Card-based encryption (no GPG keyring required)",
                "Encryption Successful"
            )
            logger.log_operation_end("Encryption", True)
        else:
            # Encryption failed
            logger.error(f"Encryption failed: {error_msg}")
            if "No keys found on card" in error_msg or "generate keys" in error_msg.lower():
                card_utils.show_error_dialog(
                    error_msg,
                    "Keys Not Generated"
                )
            else:
                card_utils.show_error_dialog(
                    f"Encryption failed:\n\n{error_msg}",
                    "Encryption Error"
                )
            logger.log_operation_end("Encryption", False, error_msg)

    except Exception as e:
        logger.error("Exception during encryption", e)
        import traceback
        logger.error(traceback.format_exc())
        card_utils.show_error_dialog(
            f"Error during encryption:\n\n{str(e)}",
            "Encryption Error"
        )
        logger.log_operation_end("Encryption", False, str(e))


def main():
    """Main entry point for the encryption handler"""
    if len(sys.argv) < 2:
        card_utils.show_error_dialog(
            "No file specified for encryption.\n\n"
            "This script should be called from Windows Explorer context menu.",
            "AEPGP Encryption"
        )
        sys.exit(1)

    filepath = sys.argv[1]
    encrypt_file(filepath)


if __name__ == "__main__":
    main()
