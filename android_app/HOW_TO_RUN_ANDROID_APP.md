# How to Run and Test the Android App with SmartPGP Card

## Quick Start Guide

### Prerequisites Checklist

**Hardware:**
- ✅ Android phone with NFC (or USB OTG support)
- ✅ SmartPGP card with applet installed (from `cap/` folder)
- ✅ USB cable for phone connection (for development)

**Software:**
- ✅ Android Studio (latest version)
- ✅ Phone with Developer Options enabled
- ✅ USB Debugging enabled on phone

---

## Method 1: Using Android Studio (Recommended for Testing)

### Step 1: Open Project in Android Studio

1. Launch **Android Studio**
2. Click **File → Open**
3. Navigate to: `c:\Jasper\Ambimat\openpgp\SmartPGP\android_app\AEPGPEncryptor`
4. Click **OK**
5. Wait for Gradle sync to complete (first time may take 5-10 minutes)

### Step 2: Configure Your Phone

1. On your Android phone:
   - Go to **Settings → About Phone**
   - Tap **Build Number** 7 times to enable Developer Options
   - Go to **Settings → System → Developer Options**
   - Enable **USB Debugging**
   - Enable **Stay Awake** (optional, helpful for testing)

2. Connect phone to PC via USB cable

3. On phone, tap **Allow** when prompted for USB debugging permission

### Step 3: Verify Device Connection

In Android Studio:
- Look at the top toolbar
- You should see your device name in the device dropdown
- If not, click the dropdown and select your device

### Step 4: Run the App

**Option A: Using Run Button**
- Click the green **Run** button (▶️) in the toolbar
- Or press `Shift+F10`

**Option B: Using Menu**
- Click **Run → Run 'app'**
- Select your connected device
- Click **OK**

### Step 5: Grant Permissions

When the app launches on your phone:
1. Allow **NFC** access (if prompted)
2. Allow **Storage** permissions (if prompted)
3. Allow **USB** access (if testing USB mode)

---

## Method 2: Using Command Line

### Step 1: Install Gradle Wrapper (One-Time Setup)

If you have Android Studio installed, you can use its bundled Gradle:

**On Windows:**
```powershell
cd c:\Jasper\Ambimat\openpgp\SmartPGP\android_app\AEPGPEncryptor

# Find Android Studio's Gradle (adjust path if needed)
# Typical locations:
# C:\Program Files\Android\Android Studio\gradle\gradle-8.x\bin\gradle.bat
# Or use Android Studio to create wrapper: Tools → Create Command-line Launcher

# Or download Gradle manually from https://gradle.org/releases/
```

### Step 2: Build Debug APK

**Using Android Studio's Gradle:**
```powershell
# Navigate to project
cd c:\Jasper\Ambimat\openpgp\SmartPGP\android_app\AEPGPEncryptor

# Build debug APK (if gradlew exists)
.\gradlew assembleDebug

# Or use Android Studio's Gradle
& "C:\Program Files\Android\Android Studio\gradle\gradle-8.x\bin\gradle.bat" assembleDebug
```

**Output:** APK will be in `app/build/outputs/apk/debug/app-debug.apk`

### Step 3: Install on Phone

```powershell
# Using ADB (Android Debug Bridge)
adb devices  # Verify phone is connected
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

---

## Testing the App with Your SmartPGP Card

### Test 1: NFC Card Detection (Recommended)

**Prerequisites:**
- SmartPGP applet installed on NFC card
- NFC enabled on phone

**Steps:**
1. Open the app
2. You should see: **"Ready for NFC tap or USB card"**
3. Tap your SmartPGP card to the back of your phone
4. App should detect card and show: **"Card detected"**
5. App will send SELECT command to applet
6. Should show: **"Card applet selected successfully"**

**What's happening behind the scenes:**
```kotlin
// NFC Layer (IsoDepConnection.kt)
IsoDep.connect() → Opens NFC connection

// APDU Layer (OpenPGPCard.kt)
selectApplet() → Sends: 00 A4 04 00 06 D2 76 00 01 24 01

// JavaCard Applet (SmartPGPApplet.java)
process(APDU apdu) → Receives SELECT command
→ Returns: 90 00 (Success)
```

### Test 2: Read Public Key

**Steps:**
1. After card is detected and selected
2. (If implemented in UI) Tap **"Read Public Key"** or similar
3. App sends GET PUBLIC KEY command
4. Should display key information or success message

**What's happening:**
```kotlin
// Android App
getPublicKey() → Sends: 00 47 81 00 02 B8 00

// JavaCard Applet
processGetData() → Returns RSA public key
→ Response: [key data] 90 00
```

### Test 3: Verify PIN

**Steps:**
1. After card selected
2. Tap **"Decrypt File"** or any operation requiring PIN
3. Enter PIN (default: `123456`)
4. App sends VERIFY PIN command
5. Should show success if PIN correct

**What's happening:**
```kotlin
// Android App
verifyPin("123456") → Sends: 00 20 00 82 06 313233343536

// JavaCard Applet
processVerify() → Validates PIN
→ Returns: 90 00 (Success) or 63 CX (X retries left)
```

### Test 4: File Encryption (Full Flow)

**Steps:**
1. Tap **"Encrypt File"**
2. Select a small test file (e.g., text file)
3. Tap card to phone
4. App reads public key from card
5. App encrypts file using RSA+AES
6. Check output: `testfile.txt.enc` created

**What's happening:**
```kotlin
// Android App Flow:
1. OpenPGPCard.getPublicKey() → Gets RSA public key from card
2. AESEncryption.generateKey() → Creates random AES-256 key
3. AESEncryption.encrypt() → Encrypts file with AES-256-GCM
4. RSAEncryption.encrypt(aesKey, publicKey) → Encrypts AES key with RSA
5. FileUtils.writeEncryptedFile() → Writes .enc file

// SmartPGP Applet involvement:
- Only provides public key (no private key leaves card)
```

### Test 5: File Decryption (Full Flow with Card)

**Steps:**
1. Tap **"Decrypt File"**
2. Select `.enc` file
3. Enter PIN when prompted
4. Tap card to phone
5. App sends encrypted AES key to card
6. Card decrypts using private RSA key
7. App decrypts file using recovered AES key
8. Original file restored

**What's happening:**
```kotlin
// Android App Flow:
1. FileUtils.readEncryptedFile() → Reads .enc file
2. Extracts encrypted AES key (256 bytes)
3. OpenPGPCard.verifyPin() → Authenticates user
4. OpenPGPCard.psoDecipher(encryptedKey) → Card decrypts with private key
5. AESEncryption.decrypt() → Decrypts file data
6. FileUtils.writeDecryptedFile() → Restores original file

// SmartPGP Applet (processPerformSecurityOperation):
- Receives PSO:DECIPHER command (00 2A 80 86)
- Uses private RSA key (never exposed)
- Returns decrypted AES key
```

---

## Verifying Android Implementation Matches SmartPGP Applet

### Key Alignment Points to Check:

#### 1. **APDU Commands Match**

**Android App (`OpenPGPCard.kt`):**
```kotlin
fun selectApplet(): Boolean {
    val response = send(APDUCommand.select(CardConstants.OPENPGP_AID))
    // AID: D2 76 00 01 24 01
}
```

**SmartPGP Applet (`SmartPGPApplet.java`):**
```java
public static void install(byte[] buf, short off, byte len) {
    // Registers with AID: D2 76 00 01 24 01
}
```

✅ **Aligned:** Both use same OpenPGP AID

#### 2. **PIN Verification**

**Android App:**
```kotlin
fun verifyPin(pin: CharArray): Boolean {
    val command = APDUCommand(
        cla = 0x00,
        ins = 0x20,  // VERIFY
        p1 = 0x00,
        p2 = 0x82    // PW1 (User PIN)
    )
}
```

**SmartPGP Applet:**
```java
private void processVerify(short lc, final byte p1, final byte p2) {
    // INS = 0x20
    // P2 = 0x82 for user PIN (PW1)
}
```

✅ **Aligned:** PIN verification follows OpenPGP spec

#### 3. **Public Key Retrieval**

**Android App:**
```kotlin
fun getPublicKey(keyRef: Int = DO_PUBKEY_DECRYPT): ByteArray {
    // GET DATA command for public key
    // Tag: 0xB800 (decryption key)
}
```

**SmartPGP Applet:**
```java
private void processGetData(final byte p1, final byte p2) {
    // Returns public key for tag 0xB800
    // From decryption key slot
}
```

✅ **Aligned:** Uses standard OpenPGP GET DATA

#### 4. **RSA Decryption**

**Android App:**
```kotlin
fun psoDecipher(ciphertext: ByteArray): ByteArray {
    val command = APDUCommand(
        cla = 0x00,
        ins = 0x2A,  // PSO
        p1 = 0x80,
        p2 = 0x86    // DECIPHER
    )
}
```

**SmartPGP Applet:**
```java
private void processPerformSecurityOperation(short lc, byte p1, byte p2) {
    // INS = 0x2A
    // P1P2 = 0x8086 for DECIPHER
    // Uses decryption key to decrypt
}
```

✅ **Aligned:** PSO:DECIPHER follows OpenPGP spec

---

## Debugging Tips

### View Android Logs

**Using Android Studio:**
1. Click **Logcat** tab at bottom
2. Select your device
3. Filter by "com.aepgp" to see app logs

**Using ADB:**
```powershell
# All app logs
adb logcat | Select-String "com.aepgp"

# NFC-specific logs
adb logcat -s NfcService IsoDep

# View last 100 lines
adb logcat -t 100
```

### Enable Detailed APDU Logging

In the Android app, you can add logging in `OpenPGPCard.kt`:

```kotlin
private fun send(command: APDUCommand): APDUResponse {
    val commandBytes = command.toByteArray()
    Log.d("OpenPGPCard", "→ APDU: ${commandBytes.toHexString()}")
    
    val response = channel.transceive(commandBytes)
    Log.d("OpenPGPCard", "← Response: ${response.toHexString()}")
    
    return APDUResponse.from(response)
}
```

### Common Issues and Solutions

#### Issue: "Card not detected"
**Solution:**
- Ensure NFC is enabled: Settings → Connected devices → Connection preferences → NFC
- Hold card flat against phone back (near NFC antenna)
- Keep card close for entire operation

#### Issue: "Applet not found" (6A 82)
**Solution:**
- Verify SmartPGP applet is installed on card
- Check AID matches: `D2 76 00 01 24 01`
- Use `smartpgp-cli` to verify card: `python bin/smartpgp.py -r 0 info`

#### Issue: "Wrong PIN" (63 C3)
**Solution:**
- Default PIN is `123456`
- You have 3 attempts remaining (C3 = 3)
- After 3 failures, card locks

#### Issue: "Security condition not satisfied" (69 82)
**Solution:**
- PIN not verified before operation
- Call `verifyPin()` before `psoDecipher()`

---

## Next Steps After Testing

### 1. Test Each APDU Command
- ✅ SELECT applet
- ✅ VERIFY PIN
- ✅ GET PUBLIC KEY
- ✅ PSO:DECIPHER
- ⏳ GENERATE KEYPAIR (if implementing)
- ⏳ CHANGE PIN (if implementing)

### 2. Test File Operations
- ✅ Encrypt small file (\u003c1MB)
- ✅ Decrypt small file
- ⏳ Encrypt large file (\u003e10MB)
- ⏳ Test cross-platform (encrypt on Android, decrypt on Windows)

### 3. Test Error Handling
- ⏳ Card removed during operation
- ⏳ Wrong PIN entered
- ⏳ NFC timeout
- ⏳ Corrupted file

### 4. Performance Testing
- ⏳ Measure encryption speed
- ⏳ Measure decryption speed
- ⏳ Test with different file sizes

---

## Summary

**To run the Android app and test with SmartPGP:**

1. **Open in Android Studio** → `android_app/AEPGPEncryptor`
2. **Connect phone** with USB debugging enabled
3. **Click Run** (▶️) to install and launch app
4. **Enable NFC** on phone
5. **Tap SmartPGP card** to phone to test

**The Android app communicates with SmartPGP applet via:**
```
Android App (Kotlin/Java)
    ↓ APDU commands
NFC / USB interface
    ↓ ISO 7816 protocol
SmartPGP Applet (JavaCard)
    ↓ Crypto operations
Card Hardware
```

**All APDU commands in the Android app are designed to match the SmartPGP applet's implementation**, following the OpenPGP Card 3.4 specification.

Good luck with testing! 🚀
