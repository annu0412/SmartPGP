"""
AEPGP Card Public Key Reader

This module reads the public key directly from the SmartPGP card using APDUs,
without relying on GPG keyring.
"""

import sys
from smartcard.util import toHexString

# Import debug logger
try:
    from debug_logger import get_logger
    logger = get_logger()
except ImportError:
    class DummyLogger:
        def info(self, msg): pass
        def warning(self, msg): pass
        def error(self, msg, e=None): pass
        def debug(self, msg): pass
    logger = DummyLogger()


# APDU commands for OpenPGP card
GET_PUBLIC_KEY_CMD = [0x00, 0x47, 0x81, 0x00]

# Key slot tags (OpenPGP card v3.4 specification)
KEY_SLOTS = {
    'signature': 0xB6,      # Signature key
    'encryption': 0xB8,     # Decryption/Encryption key
    'authentication': 0xA4  # Authentication key
}


def assemble_apdu_with_len(prefix, data):
    """Assemble APDU command with proper length encoding"""
    return prefix + [len(data)] + data + [0x00]


def parse_tlv_length(data, offset):
    """
    Parse TLV (Tag-Length-Value) length field.
    Returns (length, bytes_consumed)
    """
    if offset >= len(data):
        return 0, 0

    first_byte = data[offset]

    if first_byte <= 0x7F:
        # Short form: length is in first byte
        return first_byte, 1
    elif first_byte == 0x81:
        # Long form: next 1 byte contains length
        if offset + 1 >= len(data):
            return 0, 0
        return data[offset + 1], 2
    elif first_byte == 0x82:
        # Long form: next 2 bytes contain length
        if offset + 2 >= len(data):
            return 0, 0
        length = (data[offset + 1] << 8) | data[offset + 2]
        return length, 3
    else:
        return 0, 0


class NoKeyOnCardError(Exception):
    """Raised when the requested key slot on the card is empty (SW=6A88)."""
    pass


def read_public_key_from_card(card, key_slot='encryption'):
    """
    Read the public key from the SmartPGP card using APDU commands.

    Args:
        card: AEPGPCard object with active connection
        key_slot: Which key to read ('signature', 'encryption', or 'authentication')

    Returns:
        bytes: Raw public key data in OpenPGP format, or None on error
    """
    try:
        if key_slot not in KEY_SLOTS:
            logger.error(f"Invalid key slot: {key_slot}. Must be one of: {list(KEY_SLOTS.keys())}")
            return None

        slot_tag = KEY_SLOTS[key_slot]
        logger.info(f"Reading {key_slot} public key from card (slot 0x{slot_tag:02X})...")

        # Build GET PUBLIC KEY command
        # Format: CLA INS P1 P2 Lc Data Le
        # CLA=00, INS=47, P1=81, P2=00
        # Data contains the key slot tag
        apdu_data = [slot_tag, 0x00]  # Key slot tag + template
        apdu = assemble_apdu_with_len(GET_PUBLIC_KEY_CMD, apdu_data)

        logger.debug(f"Sending APDU: {toHexString(apdu)}")

        # Send APDU to card
        response, sw1, sw2 = card.connection.transmit(apdu)

        # Log APDU response
        card._log_apdu(apdu, response, sw1, sw2)

        # SW=61XX means more data available — chain GET RESPONSE until SW != 61XX.
        # A single GET RESPONSE is not sufficient: the card may split the 270-byte
        # RSA-2048 public key across more than two T=1 frames depending on hardware.
        # Safety cap: 16 iterations is far more than any real card will need.
        _MAX_GET_RESPONSE_ITERATIONS = 16
        _iteration = 0
        while sw1 == 0x61 and _iteration < _MAX_GET_RESPONSE_ITERATIONS:
            _iteration += 1
            logger.info(
                f"GET RESPONSE iteration {_iteration}: "
                f"{sw2 or 256} bytes remaining, total so far {len(response)} bytes"
            )
            get_response_cmd = [0x00, 0xC0, 0x00, 0x00, sw2]
            logger.debug(f"Sending GET RESPONSE: {toHexString(get_response_cmd)}")
            response_chunk, sw1, sw2 = card.connection.transmit(get_response_cmd)
            card._log_apdu(get_response_cmd, response_chunk, sw1, sw2)
            response = response + response_chunk

        if _iteration == _MAX_GET_RESPONSE_ITERATIONS and sw1 == 0x61:
            logger.warning(
                f"GET RESPONSE loop hit safety cap ({_MAX_GET_RESPONSE_ITERATIONS} "
                "iterations) — response may be incomplete."
            )

        logger.info(f"Combined response: {len(response)} bytes total")

        # Check for errors
        if sw1 == 0x6A and sw2 == 0x88:
            # Referenced data not found - no key in this slot
            logger.error(f"No key found in {key_slot} slot (SW=6A88)")
            raise NoKeyOnCardError(
                f"No keys found on card (slot: {key_slot}).\n\n"
                "Please generate keys first using the 'Generate Keys in Card' option."
            )

        if not response:
            logger.error("Empty response from card")
            return None

        # If we got data, try to use it even if status is not 9000
        if sw1 != 0x90 or sw2 != 0x00:
            logger.warning(f"Non-standard status: SW={sw1:02X}{sw2:02X}, but received {len(response)} bytes")
            # Continue anyway if we have data

        logger.info(f"Received {len(response)} bytes of public key data")
        logger.debug(f"Raw response: {toHexString(response)}")

        return bytes(response)

    except NoKeyOnCardError:
        raise  # let callers handle the no-key case explicitly
    except Exception as e:
        logger.error(f"Error reading public key from card: {e}", e)
        return None


def extract_rsa_public_key_components(key_data):
    """
    Extract RSA public key components (n, e) from OpenPGP card response.

    Args:
        key_data: Raw bytes from GET PUBLIC KEY response

    Returns:
        tuple: (modulus_n, exponent_e) as bytes, or (None, None) on error
    """
    try:
        logger.debug("Parsing RSA public key components...")
        logger.debug(f"Key data (first 50 bytes): {key_data[:50].hex()}")

        # OpenPGP card returns public key in TLV format
        # Expected structure: 7F49 Len [81 Len modulus] [82 Len exponent]
        offset = 0

        # Check for template tag (0x7F49)
        if len(key_data) >= 2 and key_data[0] == 0x7F and key_data[1] == 0x49:
            logger.debug("Found 7F49 template tag")
            offset = 2
            # Skip template length
            template_len, len_bytes = parse_tlv_length(key_data, offset)
            offset += len_bytes
            logger.debug(f"Template length: {template_len}, offset now at: {offset}")

        # Find modulus tag (0x81)
        while offset < len(key_data):
            if key_data[offset] == 0x81:
                # Found modulus
                logger.debug(f"Found modulus tag at offset {offset}")
                offset += 1
                mod_len, len_bytes = parse_tlv_length(key_data, offset)
                offset += len_bytes

                if offset + mod_len > len(key_data):
                    logger.error(f"Invalid modulus length: {mod_len} at offset {offset}, total data: {len(key_data)}")
                    return None, None

                modulus = key_data[offset:offset + mod_len]
                offset += mod_len
                logger.debug(f"Modulus length: {len(modulus)} bytes ({len(modulus)*8} bits)")

                # Find exponent tag (0x82)
                if offset < len(key_data) and key_data[offset] == 0x82:
                    logger.debug(f"Found exponent tag at offset {offset}")
                    offset += 1
                    exp_len, len_bytes = parse_tlv_length(key_data, offset)
                    offset += len_bytes

                    if offset + exp_len > len(key_data):
                        logger.error(f"Invalid exponent length: {exp_len}")
                        return None, None

                    exponent = key_data[offset:offset + exp_len]
                    logger.debug(f"Exponent length: {len(exponent)} bytes")
                    logger.debug(f"Exponent value: {int.from_bytes(exponent, byteorder='big')}")
                    logger.info("Successfully extracted RSA public key components")

                    return bytes(modulus), bytes(exponent)
                else:
                    found_str = f"{key_data[offset]:02X}" if offset < len(key_data) else "EOF"
                    logger.error(f"Expected exponent tag 0x82 at offset {offset}, found: {found_str}")
            offset += 1

        logger.error("Could not find RSA key components in response")
        logger.debug(f"Full key data: {key_data.hex()}")
        return None, None

    except Exception as e:
        logger.error(f"Error extracting RSA components: {e}", e)
        import traceback
        logger.error(traceback.format_exc())
        return None, None


def convert_to_pgp_format(modulus, exponent):
    """
    Convert RSA public key components to OpenPGP public key object.

    This constructs an OpenPGP v4 public key packet manually and parses it with PGPy.

    Args:
        modulus: RSA modulus (n) as bytes
        exponent: RSA exponent (e) as bytes

    Returns:
        PGPKey: PGPy public key object, or None on error
    """
    try:
        import pgpy
        import struct
        from datetime import datetime
        import io

        logger.info("Converting RSA components to PGP key object...")

        logger.debug(f"RSA modulus length: {len(modulus)} bytes ({len(modulus)*8} bits)")
        logger.debug(f"RSA exponent length: {len(exponent)} bytes")

        # Construct OpenPGP v4 public key packet
        # Reference: RFC 4880 section 5.5.2

        # Packet format:
        # - Version (1 byte): 0x04
        # - Creation time (4 bytes): Unix timestamp
        # - Algorithm (1 byte): 0x01 for RSA (Encrypt or Sign)
        # - RSA n (MPI format): bit length (2 bytes) + data
        # - RSA e (MPI format): bit length (2 bytes) + data

        packet = io.BytesIO()

        # Version
        packet.write(b'\x04')

        # Creation time (use current time)
        created = int(datetime.utcnow().timestamp())
        packet.write(struct.pack('>I', created))

        # Algorithm: RSA Encrypt-Only (0x03)
        # This tells PGPy the key is specifically for encryption
        packet.write(b'\x03')

        # Write MPI (Multi-Precision Integer) for modulus
        # MPI format: 2-byte bit length + data (big-endian)
        n_bits = len(modulus) * 8
        # Remove leading zero bytes
        modulus_clean = modulus.lstrip(b'\x00')
        # Recalculate bit length for cleaned modulus
        if modulus_clean:
            n_bits = (len(modulus_clean) - 1) * 8 + modulus_clean[0].bit_length()
        packet.write(struct.pack('>H', n_bits))
        packet.write(modulus_clean)

        # Write MPI for exponent
        e_bits = len(exponent) * 8
        exponent_clean = exponent.lstrip(b'\x00')
        if exponent_clean:
            e_bits = (len(exponent_clean) - 1) * 8 + exponent_clean[0].bit_length()
        packet.write(struct.pack('>H', e_bits))
        packet.write(exponent_clean)

        # Get the packet data
        packet_data = packet.getvalue()
        logger.debug(f"Constructed packet size: {len(packet_data)} bytes")

        # Create OpenPGP packet with proper header
        # Old format packet header for public key (tag 6)
        # If packet length > 255, use 2-byte length format
        packet_len = len(packet_data)

        if packet_len < 256:
            # Short length format: tag byte + 1-byte length
            header = bytes([0x99, packet_len])
        else:
            # Long length format: tag byte + 2-byte length
            header = bytes([0x99]) + struct.pack('>H', packet_len)

        # Complete packet
        full_packet = header + packet_data

        logger.debug(f"Full packet size: {len(full_packet)} bytes")
        logger.debug(f"Packet header: {full_packet[:10].hex()}")

        # Parse the packet with PGPy
        key, _ = pgpy.PGPKey.from_blob(full_packet)

        logger.info("Successfully created PGP key object from RSA components")
        logger.debug(f"Key fingerprint: {key.fingerprint}")

        # Add an unsigned User ID by directly modifying the key's internal structure
        # This is a workaround since PGPy requires a User ID for encryption
        # but won't let us sign it without a private key
        try:
            uid = pgpy.PGPUID.new('SmartPGP Card <card@smartpgp.local>')
            # Check if _uids is a dict or list and add accordingly
            if hasattr(key, '_uids'):
                if isinstance(key._uids, dict):
                    key._uids[uid.name] = uid
                elif isinstance(key._uids, list):
                    key._uids.append(uid)
                else:
                    # Try appending to _uids as if it's a collection
                    key._uids.append(uid)
                logger.debug(f"Added unsigned User ID: {uid.name}")
        except Exception as e:
            logger.warning(f"Could not add unsigned User ID: {e}")
            logger.debug(f"_uids type: {type(key._uids) if hasattr(key, '_uids') else 'not found'}")
            # Continue anyway - encryption might still work

        return key

    except Exception as e:
        logger.error(f"Error converting to PGP format: {e}", e)
        import traceback
        logger.error(traceback.format_exc())
        return None


def read_pgp_public_key_from_card(card, key_slot='encryption'):
    """
    Read public key from card and convert to PGP format in one step.

    Args:
        card: AEPGPCard object with active connection
        key_slot: Which key to read ('signature', 'encryption', or 'authentication')

    Returns:
        PGPKey: PGPy public key object, or None on error
    """
    try:
        logger.info(f"Reading PGP public key from card (slot: {key_slot})...")

        # Read raw public key data from card
        key_data = read_public_key_from_card(card, key_slot)
        if not key_data:
            logger.error("Failed to read public key from card")
            return None

        # Extract RSA components
        modulus, exponent = extract_rsa_public_key_components(key_data)
        if not modulus or not exponent:
            logger.error("Failed to extract RSA components")
            return None

        # Convert to PGP format
        pgp_key = convert_to_pgp_format(modulus, exponent)
        if not pgp_key:
            logger.error("Failed to convert to PGP format")
            return None

        logger.info("Successfully read and converted public key from card")
        return pgp_key

    except Exception as e:
        logger.error(f"Error reading PGP public key from card: {e}", e)
        return None


def encrypt_with_card_key(message_data, card, key_slot='encryption'):
    """
    Encrypt data using RSA public key from card, bypassing PGPy's usage flag checks.

    This function reads the RSA public key from the card and performs encryption
    using cryptography library directly, then wraps the result in PGP format.

    Args:
        message_data: bytes to encrypt
        card: AEPGPCard object with active connection
        key_slot: Which key to use ('signature', 'encryption', or 'authentication')

    Returns:
        str: PGP-encrypted message in ASCII armor format, or None on error
    """
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa, padding
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.backends import default_backend
        import pgpy

        logger.info("Encrypting data using card RSA public key directly...")

        # Read raw key data from card
        key_data = read_public_key_from_card(card, key_slot)
        if not key_data:
            return None

        # Extract RSA components
        modulus_bytes, exponent_bytes = extract_rsa_public_key_components(key_data)
        if not modulus_bytes or not exponent_bytes:
            return None

        # Convert to integers
        n = int.from_bytes(modulus_bytes, byteorder='big')
        e = int.from_bytes(exponent_bytes, byteorder='big')

        # Create RSA public key using cryptography library
        public_numbers = rsa.RSAPublicNumbers(e, n)
        rsa_public_key = public_numbers.public_key(default_backend())

        logger.debug(f"Created RSA public key: {n.bit_length()} bits")

        # Encrypt the data using RSA-OAEP
        ciphertext = rsa_public_key.encrypt(
            message_data,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        logger.info(f"Encrypted {len(message_data)} bytes -> {len(ciphertext)} bytes ciphertext")

        # Wrap in PGP message format
        # For now, return base64-encoded ciphertext with PGP armor
        import base64
        armored = "-----BEGIN PGP MESSAGE-----\\n\\n"
        armored += base64.b64encode(ciphertext).decode('ascii')
        armored += "\\n-----END PGP MESSAGE-----\\n"

        return armored

    except Exception as e:
        logger.error(f"Error encrypting with card key: {e}", e)
        import traceback
        logger.error(traceback.format_exc())
        return None
