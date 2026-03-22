"""
AEPGP Card Detection and Management Utilities

This module provides utilities for detecting and communicating with AEPGP cards
on Windows systems.
"""

import sys
import os

# Import debug logger
try:
    from debug_logger import get_logger
    logger = get_logger()
except ImportError:
    # Fallback if logger not available
    class DummyLogger:
        def info(self, msg): pass
        def error(self, msg, e=None): pass
        def debug(self, msg): pass
    logger = DummyLogger()

try:
    from smartcard.System import readers
    from smartcard.Exceptions import NoCardException, CardConnectionException
    from smartcard.util import toHexString, toBytes
except ImportError:
    print("ERROR: pyscard library not found. Install it with: pip install pyscard")
    sys.exit(1)

# OpenPGP AID (Application Identifier)
OPENPGP_AID = [0xD2, 0x76, 0x00, 0x01, 0x24, 0x01]

# Supported ATRs (Answer To Reset) for AEPGP/SmartPGP cards
# Multiple ATRs are supported to work with different card manufacturers
SUPPORTED_ATRS = [
    # Original AmbiSecure Token ATR
    [0x3B, 0xD5, 0x18, 0xFF, 0x81, 0xB1, 0xFE, 0x45, 0x1F, 0xC3, 0x80, 0x73, 0xC8, 0x21, 0x10, 0x6F],
    # SmartPGP on Gemalto/NXP JCOP cards: 3B D5 18 FF 81 91 FE 1F C3 80 73 C8 21 10 0A
    [0x3B, 0xD5, 0x18, 0xFF, 0x81, 0x91, 0xFE, 0x1F, 0xC3, 0x80, 0x73, 0xC8, 0x21, 0x10, 0x0A],
    # AmbiSecure variant: 3B D5 18 FF 81 91 FE 1F C3 AE 19 04 82 CE FF
    [0x3B, 0xD5, 0x18, 0xFF, 0x81, 0x91, 0xFE, 0x1F, 0xC3, 0xAE, 0x19, 0x04, 0x82, 0xCE, 0xFF],
]


class AEPGPCard:
    """Represents a connection to an AEPGP card"""

    def __init__(self, connection):
        self.connection = connection
        self.reader = connection.getReader()

    def _log_apdu(self, command, response, sw1, sw2):
        """Log APDU command and response"""
        cmd_hex = toHexString(command)
        resp_hex = toHexString(response) if response else ""
        logger.debug(f"APDU CMD: {cmd_hex}")
        logger.debug(f"APDU RSP: {resp_hex} SW={sw1:02X}{sw2:02X}")

    def select_applet(self):
        """Select the OpenPGP applet on the card"""
        SELECT_APDU = [0x00, 0xA4, 0x04, 0x00, len(OPENPGP_AID)] + OPENPGP_AID + [0x00]
        logger.info("Selecting OpenPGP applet...")
        response, sw1, sw2 = self.connection.transmit(SELECT_APDU)
        self._log_apdu(SELECT_APDU, response, sw1, sw2)

        if sw1 != 0x90 or sw2 != 0x00:
            error_msg = f"Failed to select OpenPGP applet: SW={sw1:02X}{sw2:02X}"
            logger.error(error_msg)
            raise Exception(error_msg)

        logger.info("OpenPGP applet selected successfully")
        return response

    def disconnect(self):
        """Close the connection to the card"""
        try:
            self.connection.disconnect()
        except:
            pass


def verify_supported_atr(atr):
    """
    Verify if the ATR matches any supported AEPGP/SmartPGP card.

    Args:
        atr: ATR bytes from the card

    Returns:
        bool: True if ATR matches a supported card, False otherwise
    """
    atr_list = list(atr)
    return any(atr_list == supported_atr for supported_atr in SUPPORTED_ATRS)


def find_aepgp_card():
    """
    Search for an AEPGP/SmartPGP card in all available readers.
    Supports multiple card types with different ATRs.

    Returns:
        tuple: (AEPGPCard object, None) on success
               (None, error_message) on failure
    """
    try:
        reader_list = readers()

        if not reader_list:
            return None, "No smart card readers found.\n\nPlease connect a USB smart card reader to your computer."

        # Try each reader
        for reader in reader_list:
            try:
                connection = reader.createConnection()
                connection.connect()

                # Get ATR and verify it's a supported card
                atr = connection.getATR()
                if not verify_supported_atr(atr):
                    # Not a supported card, skip this card
                    try:
                        connection.disconnect()
                    except:
                        pass
                    continue

                # Try to select OpenPGP applet
                card = AEPGPCard(connection)
                card.select_applet()

                # Success!
                return card, None

            except NoCardException:
                # No card in this reader, try next one
                continue
            except CardConnectionException:
                # Connection failed, try next reader
                continue
            except Exception as e:
                # Card present but wrong applet or wrong card, try next reader
                try:
                    connection.disconnect()
                except:
                    pass
                continue

        # No AEPGP card found in any reader
        return None, "AEPGP card not found.\n\nPlease insert your AEPGP card into the reader."

    except Exception as e:
        return None, f"Error accessing smart card:\n\n{str(e)}"


def get_card_info(card):
    """
    Get basic information about the AEPGP card.

    Args:
        card: AEPGPCard object

    Returns:
        dict: Card information
    """
    try:
        # GET DATA command for application related data (0x00 0x6E)
        GET_DATA = [0x00, 0xCA, 0x00, 0x6E, 0x00]
        response, sw1, sw2 = card.connection.transmit(GET_DATA)

        info = {
            'reader': card.reader,
            'connected': True,
            'response_status': f"{sw1:02X}{sw2:02X}"
        }

        return info
    except Exception as e:
        return {
            'reader': card.reader,
            'connected': True,
            'error': str(e)
        }


def _get_response_if_needed(card, response, sw1, sw2):
    if sw1 != 0x61:
        return response, sw1, sw2

    get_response_cmd = [0x00, 0xC0, 0x00, 0x00, sw2]
    response2, sw1_2, sw2_2 = card.connection.transmit(get_response_cmd)
    card._log_apdu(get_response_cmd, response2, sw1_2, sw2_2)
    return response + response2, sw1_2, sw2_2


def get_key_alias(card):
    """Fetch the stored alias for the card key pair (DO 0102)."""
    try:
        get_data_cmd = [0x00, 0xCA, 0x01, 0x02, 0x00]
        response, sw1, sw2 = card.connection.transmit(get_data_cmd)
        card._log_apdu(get_data_cmd, response, sw1, sw2)

        response, sw1, sw2 = _get_response_if_needed(card, response, sw1, sw2)

        if sw1 == 0x6A and sw2 == 0x88:
            return None
        if sw1 != 0x90 or sw2 != 0x00:
            logger.error(f"Failed to read key alias: SW={sw1:02X}{sw2:02X}")
            return None
        if not response:
            return None

        try:
            return bytes(response).decode("ascii")
        except Exception:
            return bytes(response).decode("utf-8", errors="replace")
    except Exception as e:
        logger.error(f"Failed to read key alias: {e}", e)
        return None


def set_key_alias(card, alias):
    """Store an alias for the card key pair (DO 0102)."""
    try:
        alias_bytes = alias.encode("ascii")
    except UnicodeEncodeError:
        logger.error("Alias must be ASCII")
        return False

    if len(alias_bytes) > 255:
        logger.error("Alias too long (max 255 bytes)")
        return False

    try:
        put_data_cmd = [0x00, 0xDA, 0x01, 0x02, len(alias_bytes)] + list(alias_bytes)
        response, sw1, sw2 = card.connection.transmit(put_data_cmd)
        card._log_apdu(put_data_cmd, response, sw1, sw2)

        if sw1 != 0x90 or sw2 != 0x00:
            logger.error(f"Failed to store key alias: SW={sw1:02X}{sw2:02X}")
            return False

        return True
    except Exception as e:
        logger.error(f"Failed to store key alias: {e}", e)
        return False


def clear_key_alias(card):
    """Clear the card key pair alias (DO 0102)."""
    try:
        put_data_cmd = [0x00, 0xDA, 0x01, 0x02, 0x00]
        response, sw1, sw2 = card.connection.transmit(put_data_cmd)
        card._log_apdu(put_data_cmd, response, sw1, sw2)

        if sw1 != 0x90 or sw2 != 0x00:
            logger.error(f"Failed to clear key alias: SW={sw1:02X}{sw2:02X}")
            return False

        return True
    except Exception as e:
        logger.error(f"Failed to clear key alias: {e}", e)
        return False

def set_hidden_attribute(path, hide):
    """
    Set or clear the Windows hidden attribute on a file.

    Args:
        path: Path to the file
        hide: True to hide, False to unhide

    Returns:
        tuple: (success: bool, error_message: str or None)
    """
    try:
        import ctypes
        from ctypes import wintypes

        FILE_ATTRIBUTE_HIDDEN = 0x02
        FILE_ATTRIBUTE_NORMAL = 0x80
        INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF

        get_attrs = ctypes.windll.kernel32.GetFileAttributesW
        set_attrs = ctypes.windll.kernel32.SetFileAttributesW
        get_attrs.argtypes = [wintypes.LPCWSTR]
        get_attrs.restype = wintypes.DWORD
        set_attrs.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
        set_attrs.restype = wintypes.BOOL

        attrs = get_attrs(path)
        if attrs == INVALID_FILE_ATTRIBUTES:
            return False, "Unable to read file attributes"

        if hide:
            new_attrs = attrs | FILE_ATTRIBUTE_HIDDEN
        else:
            new_attrs = attrs & ~FILE_ATTRIBUTE_HIDDEN
            if new_attrs == 0:
                new_attrs = FILE_ATTRIBUTE_NORMAL

        if not set_attrs(path, new_attrs):
            return False, "Unable to set file attributes"

        return True, None
    except Exception as e:
        logger.error(f"Failed to set hidden attribute for {path}: {e}", e)
        return False, str(e)


def sync_encrypted_file_visibility(path):
    """
    Show encrypted files only when an AEPGP card is present.

    Args:
        path: Path to the encrypted file

    Returns:
        tuple: (card_present: bool, error_message: str or None)
    """
    if not os.path.exists(path):
        return False, "File does not exist"

    card, error = find_aepgp_card()
    try:
        if error:
            set_hidden_attribute(path, True)
            return False, error

        set_hidden_attribute(path, False)
        return True, None
    finally:
        if card:
            card.disconnect()


def show_error_dialog(message, title="AEPGP"):
    """
    Show an error message dialog on Windows.

    Args:
        message: Error message to display
        title: Dialog title
    """
    try:
        import ctypes
        MessageBox = ctypes.windll.user32.MessageBoxW
        # MB_ICONERROR | MB_OK = 0x10 | 0x00
        MessageBox(None, message, title, 0x10)
    except Exception as e:
        print(f"ERROR: {message}")


def show_info_dialog(message, title="AEPGP"):
    """
    Show an information message dialog on Windows.

    Args:
        message: Information message to display
        title: Dialog title
    """
    try:
        import ctypes
        MessageBox = ctypes.windll.user32.MessageBoxW
        # MB_ICONINFORMATION | MB_OK = 0x40 | 0x00
        MessageBox(None, message, title, 0x40)
    except Exception as e:
        print(f"INFO: {message}")


def show_question_dialog(message, title="AEPGP"):
    """
    Show a yes/no question dialog on Windows.

    Args:
        message: Question to ask
        title: Dialog title

    Returns:
        bool: True if user clicked Yes, False otherwise
    """
    try:
        import ctypes
        MessageBox = ctypes.windll.user32.MessageBoxW
        # MB_ICONQUESTION | MB_YESNO = 0x20 | 0x04
        # Returns IDYES (6) or IDNO (7)
        result = MessageBox(None, message, title, 0x24)
        return result == 6  # IDYES
    except Exception as e:
        print(f"QUESTION: {message}")
        return False


def show_input_dialog(message, title="AEPGP"):
    """
    Show an input dialog for text entry.

    Returns:
        str or None
    """
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)

        value = simpledialog.askstring(title, message, parent=root)
        root.destroy()
        return value
    except Exception as e:
        print(f"INPUT: {message}")
        return None


if __name__ == "__main__":
    # Test the card detection
    print("Searching for AEPGP card...")
    card, error = find_aepgp_card()

    if error:
        print(f"Error: {error}")
        sys.exit(1)

    print(f"AEPGP card found in reader: {card.reader}")

    # Print ATR
    atr = card.connection.getATR()
    print(f"ATR: {toHexString(atr)}")

    info = get_card_info(card)
    print(f"Card info: {info}")

    card.disconnect()
    print("Disconnected successfully")
