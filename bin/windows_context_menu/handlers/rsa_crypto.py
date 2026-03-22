"""
AEPGP RSA Encryption Module

This module provides RSA encryption using the AEPGP card's public key.
Uses the cryptography library for hybrid encryption (RSA + AES).
"""

import os
import sys
from pathlib import Path

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

try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    logger.info("Cryptography library imported successfully")
except ImportError:
    logger.error("Cryptography library not found. Install it with: pip install cryptography")
    print("ERROR: Cryptography library not found.")
    sys.exit(1)


def encrypt_file_with_card_key(input_file, output_file):
    """
    Encrypt a file using hybrid encryption (RSA + AES) with the card's public key.

    Uses AES-256-GCM for file encryption and RSA PKCS#1 v1.5 for AES key
    encryption.

    IMPORTANT — padding scheme: RSA key encryption uses PKCS#1 v1.5, NOT OAEP.
    The card's PSO:DECIPHER APDU expects PKCS#1 v1.5 ciphertext; the mandatory
    0x00 padding-indicator byte sent with the DECIPHER command explicitly signals
    PKCS#1 v1.5 per the OpenPGP card spec (0x00 = PKCS#1 v1.5, 0x02 = OAEP).
    Changing the padding to OAEP will produce ciphertext the card cannot decrypt.

    Args:
        input_file: Path to file to encrypt
        output_file: Path for encrypted output

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        from card_utils import find_aepgp_card
        from card_key_reader import read_public_key_from_card, extract_rsa_public_key_components, NoKeyOnCardError
        import struct

        logger.info(f"Starting file encryption: {input_file}")
        print(f"Encrypting: {input_file}")

        # Read the input file
        if not os.path.exists(input_file):
            error_msg = f"Input file not found: {input_file}"
            logger.error(error_msg)
            return False, error_msg

        file_size = os.path.getsize(input_file)
        logger.info(f"Input file size: {file_size} bytes")
        print(f"File size: {file_size} bytes")

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

            # Read public key from card
            logger.info("Reading public key from card...")
            print("Reading public key from card...")
            key_data = read_public_key_from_card(card, 'encryption')
            if not key_data:
                error_msg = "Failed to read public key from card"
                logger.error(error_msg)
                return False, error_msg

            # Extract RSA components
            modulus_bytes, exponent_bytes = extract_rsa_public_key_components(key_data)
            if not modulus_bytes or not exponent_bytes:
                error_msg = "Failed to extract RSA components"
                logger.error(error_msg)
                return False, error_msg

            # Create RSA public key
            n = int.from_bytes(modulus_bytes, byteorder='big')
            e = int.from_bytes(exponent_bytes, byteorder='big')
            public_numbers = rsa.RSAPublicNumbers(e, n)
            rsa_public_key = public_numbers.public_key(default_backend())

            logger.info(f"Successfully loaded RSA public key: {n.bit_length()} bits")
            print(f"Public key loaded: {n.bit_length()} bits")

        finally:
            card.disconnect()
            logger.debug("Card disconnected")

        # Generate random AES key and IV
        logger.debug("Generating AES key and IV...")
        aes_key = os.urandom(32)  # 256-bit AES key
        iv = os.urandom(12)       # 96-bit IV for GCM

        # Stream plaintext through AES-256-GCM into a temp ciphertext file.
        # AES-GCM auth_tag is only available after finalize(), but the file
        # format places auth_tag BEFORE the ciphertext.  We therefore write
        # ciphertext to a temp file first, then assemble the final output in
        # the correct order:
        #   [4B key_len][encrypted_key][12B IV][16B auth_tag][ciphertext]
        _CHUNK = 65536  # 64 KiB streaming chunk size
        logger.info("Encrypting file data with AES-256-GCM (streaming)...")
        print("Encrypting file data...")
        cipher = Cipher(
            algorithms.AES(aes_key),
            modes.GCM(iv),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        tmp_cipher = output_file + ".ciphertmp"
        bytes_processed = 0

        try:
            with open(input_file, 'rb') as fin, open(tmp_cipher, 'wb') as ftmp:
                while True:
                    chunk = fin.read(_CHUNK)
                    if not chunk:
                        break
                    ftmp.write(encryptor.update(chunk))
                    bytes_processed += len(chunk)
                # finalize() flushes any buffered output and makes tag available
                last_block = encryptor.finalize()
                if last_block:
                    ftmp.write(last_block)

            auth_tag = encryptor.tag
            logger.info(f"File encrypted: {bytes_processed} bytes plaintext")

            # Encrypt the AES key with RSA PKCS#1 v1.5.
            # IMPORTANT: Do NOT change to OAEP — the card PSO:DECIPHER expects
            # PKCS#1 v1.5 (signalled by the 0x00 padding-indicator byte).
            logger.info("Encrypting AES key with RSA-PKCS#1 v1.5...")
            print("Encrypting AES key with card's public key...")
            encrypted_aes_key = rsa_public_key.encrypt(aes_key, padding.PKCS1v15())
            logger.info(f"AES key encrypted: {len(encrypted_aes_key)} bytes")

            # Assemble the final output file atomically (write to .tmp, then
            # os.replace() so a crash never leaves a partial .enc file).
            logger.debug(f"Assembling encrypted output atomically: {output_file}")
            tmp_output = output_file + ".tmp"
            try:
                with open(tmp_output, 'wb') as fout, open(tmp_cipher, 'rb') as fsrc:
                    fout.write(struct.pack('>I', len(encrypted_aes_key)))
                    fout.write(encrypted_aes_key)
                    fout.write(iv)
                    fout.write(auth_tag)
                    while True:
                        chunk = fsrc.read(_CHUNK)
                        if not chunk:
                            break
                        fout.write(chunk)
                os.replace(tmp_output, output_file)  # atomic on both Windows and POSIX
            except Exception:
                if os.path.exists(tmp_output):
                    try:
                        os.remove(tmp_output)
                    except OSError:
                        pass
                raise

        finally:
            # Always remove the intermediate ciphertext temp file
            if os.path.exists(tmp_cipher):
                try:
                    os.remove(tmp_cipher)
                except OSError:
                    pass

        logger.info(f"Encrypted file written successfully: {output_file}")
        print(f"Encryption successful!")
        print(f"Encrypted file: {output_file}")

        return True, None

    except NoKeyOnCardError as e:
        logger.error(f"Encryption aborted — no key on card: {e}")
        return False, str(e)
    except Exception as e:
        logger.error(f"Encryption failed with exception: {e}", e)
        import traceback
        logger.error(traceback.format_exc())
        return False, f"Encryption failed: {str(e)}"
