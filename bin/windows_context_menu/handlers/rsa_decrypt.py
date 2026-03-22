"""
AEPGP RSA Decryption Module

This module provides RSA+AES hybrid decryption using the AEPGP card's private key.
Decrypts files encrypted with rsa_crypto.py
"""

import os
import sys
import struct

# Import debug logger
try:
    from debug_logger import get_logger
    logger = get_logger()
except ImportError:
    class DummyLogger:
        def info(self, msg): print(f"INFO: {msg}")
        def error(self, msg, e=None): print(f"ERROR: {msg}")
        def debug(self, msg): print(f"DEBUG: {msg}")
    logger = DummyLogger()


def decrypt_file_with_card(input_file, output_file, pin=None):
    """
    Decrypt a file using the AEPGP card's private key.

    The encrypted file format is:
    [4 bytes: encrypted AES key length]
    [encrypted AES key (256 bytes for RSA-2048)]
    [12 bytes: IV]
    [16 bytes: GCM auth tag]
    [ciphertext]

    Args:
        input_file: Path to encrypted file (.enc)
        output_file: Path for decrypted output
        pin: Optional PIN for card (if None, will use default)

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        from card_utils import find_aepgp_card
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend
        from smartcard.util import toHexString

        logger.info(f"Starting file decryption: {input_file}")
        print(f"Decrypting: {input_file}")

        # Read the encrypted file
        if not os.path.exists(input_file):
            error_msg = f"Input file not found: {input_file}"
            logger.error(error_msg)
            return False, error_msg

        logger.debug(f"Reading encrypted file...")
        with open(input_file, 'rb') as f:
            # Read encrypted AES key length
            key_len_bytes = f.read(4)
            if len(key_len_bytes) < 4:
                error_msg = "Invalid encrypted file format (too short)"
                logger.error(error_msg)
                return False, error_msg

            encrypted_key_len = struct.unpack('>I', key_len_bytes)[0]
            logger.debug(f"Encrypted AES key length: {encrypted_key_len} bytes")

            # Read encrypted AES key
            encrypted_aes_key = f.read(encrypted_key_len)
            if len(encrypted_aes_key) < encrypted_key_len:
                error_msg = "Invalid encrypted file format (truncated key)"
                logger.error(error_msg)
                return False, error_msg

            # Read IV
            iv = f.read(12)
            if len(iv) < 12:
                error_msg = "Invalid encrypted file format (missing IV)"
                logger.error(error_msg)
                return False, error_msg

            # Read GCM auth tag
            auth_tag = f.read(16)
            if len(auth_tag) < 16:
                error_msg = "Invalid encrypted file format (missing auth tag)"
                logger.error(error_msg)
                return False, error_msg

            # Read ciphertext
            ciphertext = f.read()

        logger.info(f"Read encrypted file: {len(ciphertext)} bytes ciphertext")
        print(f"Encrypted data size: {len(ciphertext)} bytes")

        # Find and connect to card
        logger.info("Connecting to AEPGP card...")
        print("Connecting to AEPGP card...")
        card, error = find_aepgp_card()
        if error:
            error_msg = f"Card not found: {error}"
            logger.error(error_msg)
            return False, error_msg

        logger.info(f"Card found: {card.reader}")
        print(f"Card found: {card.reader}")

        try:
            # Select OpenPGP applet
            card.select_applet()

            # Verify PIN (required for decryption)
            logger.info("Verifying PIN...")
            print("Verifying PIN...")

            # PIN is required — callers must pass it explicitly.
            # A None PIN is not silently replaced with a default because any
            # hardcoded default would be exposed in source and shown to users.
            if pin is None:
                error_msg = "PIN not provided — caller must supply a PIN"
                logger.error(error_msg)
                return False, error_msg

            # Verify PIN APDU: 00 20 00 82 [length] [PIN]
            pin_bytes = [ord(c) for c in pin]
            verify_pin_cmd = [0x00, 0x20, 0x00, 0x82, len(pin_bytes)] + pin_bytes

            response, sw1, sw2 = card.connection.transmit(verify_pin_cmd)
            card._log_apdu(verify_pin_cmd, response, sw1, sw2)

            if sw1 == 0x90 and sw2 == 0x00:
                logger.info("PIN verified successfully")
                print("PIN verified")
            elif sw1 == 0x63:
                retries = sw2 & 0x0F
                error_msg = f"Wrong PIN. {retries} retries remaining.\n\nDefault User PIN is 123456 (not the Admin PIN)."
                logger.error(error_msg)
                return False, error_msg
            elif sw1 == 0x69 and sw2 == 0x82:
                # SmartPGP returns SW=6982 (Security Status Not Satisfied) for a
                # wrong PIN — non-standard but confirmed in processVerify source.
                error_msg = "Wrong PIN.\n\nDefault User PIN is 123456 (not the Admin PIN 12345678)."
                logger.error(f"Wrong PIN (SW=6982): {error_msg}")
                return False, error_msg
            elif sw1 == 0x69 and sw2 == 0x83:
                error_msg = "User PIN is blocked (too many wrong attempts).\n\nUse the Admin PIN to reset it via 'Change PIN'."
                logger.error(f"PIN blocked (SW=6983)")
                return False, error_msg
            else:
                error_msg = f"PIN verification failed: SW={sw1:02X}{sw2:02X}"
                logger.error(error_msg)
                return False, error_msg

            # Decrypt the AES key using card's private key via DECIPHER APDU
            # PSO:DECIPHER format: 00 2A 80 86 [Lc] [0x00 + encrypted_data] [Le]
            # The 0x00 padding-indicator byte signals PKCS#1 v1.5 per OpenPGP
            # card spec (0x00 = PKCS#1 v1.5, 0x02 = OAEP).  The AES key was
            # encrypted with PKCS#1 v1.5 on the host side — these must match.
            logger.info("Decrypting AES key with card's private key...")
            print("Decrypting AES key with card...")

            # Prepare data: 0x00 padding indicator + encrypted AES key
            decipher_data = [0x00] + list(encrypted_aes_key)
            data_len = len(decipher_data)

            # Use extended APDU: CLA INS P1 P2 00 Lc_high Lc_low Data Le_high Le_low
            decipher_cmd = [0x00, 0x2A, 0x80, 0x86, 0x00, (data_len >> 8) & 0xFF, data_len & 0xFF] + decipher_data + [0x00, 0x00]

            logger.debug(f"Sending DECIPHER command: {len(decipher_cmd)} bytes (data: {data_len} bytes including padding)")
            response, sw1, sw2 = card.connection.transmit(decipher_cmd)
            card._log_apdu(decipher_cmd, response, sw1, sw2)

            if sw1 == 0x6A and sw2 == 0x88:
                error_msg = (
                    "No decryption key found on card.\n\n"
                    "Please generate keys first using the 'Generate Keys in Card' option."
                )
                logger.error(f"No key on card (SW=6A88): {error_msg}")
                return False, error_msg
            elif sw1 != 0x90 or sw2 != 0x00:
                error_msg = f"Decryption failed: SW={sw1:02X}{sw2:02X}"
                logger.error(error_msg)
                return False, error_msg

            # The response contains the decrypted AES key (should be exactly 32 bytes).
            if len(response) < 32:
                error_msg = f"Decrypted key too short: {len(response)} bytes (expected 32)"
                logger.error(error_msg)
                return False, error_msg

            if len(response) > 32:
                logger.warning(
                    f"Card DECIPHER returned {len(response)} bytes (expected 32). "
                    "Using first 32 bytes as the AES-256 key. "
                    "This may indicate unexpected card output — check card firmware."
                )

            aes_key = bytes(response[:32])  # 256-bit AES key
            logger.info(f"AES key decrypted: {len(aes_key)} bytes")
            print("AES key decrypted successfully")

        finally:
            card.disconnect()
            logger.debug("Card disconnected")

        # Decrypt the file data with AES-GCM
        logger.info("Decrypting file data with AES-256-GCM...")
        print("Decrypting file data...")

        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(iv, auth_tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        plaintext = decryptor.update(ciphertext) + decryptor.finalize()

        logger.info(f"File decrypted: {len(plaintext)} bytes")

        # Write decrypted file atomically: write to .tmp then os.replace() so
        # a crash or card removal never leaves a partial/corrupt output file.
        logger.debug(f"Writing decrypted data atomically to: {output_file}")
        tmp_output = output_file + ".tmp"
        try:
            with open(tmp_output, 'wb') as f:
                f.write(plaintext)
            os.replace(tmp_output, output_file)  # atomic on Windows and POSIX
        except Exception:
            if os.path.exists(tmp_output):
                try:
                    os.remove(tmp_output)
                except OSError:
                    pass
            raise

        logger.info(f"Decrypted file written successfully: {output_file}")
        print(f"Decryption successful!")
        print(f"Decrypted file: {output_file}")

        return True, None

    except Exception as e:
        logger.error(f"Decryption failed with exception: {e}", e)
        import traceback
        logger.error(traceback.format_exc())
        return False, f"Decryption failed: {str(e)}"
