# VS Code Setup for Android Development

## Quick Start

### 1. Install Required Extensions

Open VS Code and install these extensions (already configured in `.vscode/extensions.json`):

**Essential:**
- 🔧 **Android IDE** - Complete Android development support
- 🎯 **Kotlin Language** - Kotlin syntax and IntelliSense
- 📦 **Gradle for Java** - Build system support
- 📱 **Android Debug Bridge (ADB)** - Device management

**Recommended:**
- ☕ **Extension Pack for Java** - Java language support
- 📄 **XML Tools** - XML formatting for layouts
- 🔍 **Error Lens** - Inline error highlighting
- 🎨 **GitLens** - Enhanced Git features

### 2. Install Prerequisites

**Required Software:**
- ✅ **Android SDK** - Download from Android Studio or standalone
- ✅ **Java JDK 17+** - Required for Android development
- ✅ **Gradle 8.x** - Build tool (can use wrapper)
- ✅ **ADB (Android Debug Bridge)** - Comes with Android SDK

**Environment Variables (Windows):**
```powershell
# Add to System Environment Variables:
ANDROID_HOME = C:\Users\YourUsername\AppData\Local\Android\Sdk
JAVA_HOME = C:\Program Files\Java\jdk-17

# Add to PATH:
%ANDROID_HOME%\platform-tools
%ANDROID_HOME%\tools
%JAVA_HOME%\bin
```

### 3. Configure Android SDK Path

Update `.vscode/settings.json` with your SDK path:
```json
{
  "android-dev-ext.androidSDKPath": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\Android\\Sdk"
}
```

### 4. Open Project in VS Code

```powershell
cd c:\Jasper\Ambimat\openpgp\SmartPGP\android_app
code .
```

VS Code will:
- ✅ Detect the Gradle project
- ✅ Suggest installing recommended extensions
- ✅ Configure build tasks

---

## Building and Running

### Method 1: Using VS Code Tasks (Recommended)

**Press `Ctrl+Shift+B`** to see build tasks:

1. **Build Debug APK** - Compile the app
2. **Install Debug APK** - Install on connected device
3. **Build and Install** - Do both in sequence
4. **Clean Build** - Clean and rebuild
5. **Run Tests** - Run unit tests

### Method 2: Using Terminal

**Open Terminal in VS Code (`Ctrl+``):**

```powershell
# Navigate to project
cd AEPGPEncryptor

# Build debug APK
gradle assembleDebug

# Install on device
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Or combine:
gradle assembleDebug && adb install -r app/build/outputs/apk/debug/app-debug.apk
```

### Method 3: Using Command Palette

1. Press `Ctrl+Shift+P`
2. Type "Tasks: Run Task"
3. Select task to run

---

## Debugging

### View Logcat Logs

**Using VS Code:**
1. Press `Ctrl+Shift+P`
2. Type "Tasks: Run Task"
3. Select "View Logcat"

**Using Terminal:**
```powershell
# View all logs
adb logcat

# Filter by app package
adb logcat | Select-String "com.aepgp"

# Filter by tag
adb logcat -s "OpenPGPCard"

# Clear logs first
adb logcat -c && adb logcat
```

### Debug with Breakpoints

**Note:** VS Code debugging for Android is limited. For full debugging use Android Studio.

For basic debugging:
1. Install **Java Extension Pack**
2. Set breakpoints in Kotlin/Java files
3. Attach to Android process (limited support)

**Recommended:** Use Android Studio for debugging, VS Code for coding.

---

## Keyboard Shortcuts

### Build & Run
- `Ctrl+Shift+B` - Run default build task (Build Debug APK)
- `Ctrl+Shift+T` - Run any task
- `Ctrl+Shift+P` → "Tasks: Run Task" - Show all tasks

### Code Navigation
- `F12` - Go to definition
- `Ctrl+Click` - Go to definition
- `Alt+Left/Right` - Navigate back/forward
- `Ctrl+Shift+O` - Go to symbol in file
- `Ctrl+T` - Go to symbol in workspace
- `Ctrl+P` - Quick file open

### Editing
- `Ctrl+/` - Toggle line comment
- `Shift+Alt+F` - Format document
- `Ctrl+Space` - Trigger IntelliSense
- `F2` - Rename symbol
- `Ctrl+.` - Quick fix

### Terminal
- `Ctrl+`` - Toggle terminal
- `Ctrl+Shift+`` - New terminal

---

## File Explorer in VS Code

**Navigate to key files:**

```
android_app/
├── AEPGPEncryptor/
│   ├── app/
│   │   ├── src/main/
│   │   │   ├── java/com/aepgp/encryptor/
│   │   │   │   ├── MainActivity.kt          ← UI entry point
│   │   │   │   ├── apdu/
│   │   │   │   │   └── OpenPGPCard.kt       ← APDU commands
│   │   │   │   ├── nfc/
│   │   │   │   │   └── NFCCardManager.kt    ← NFC handling
│   │   │   │   ├── crypto/
│   │   │   │   │   ├── RSAEncryption.kt     ← RSA operations
│   │   │   │   │   └── AESEncryption.kt     ← AES operations
│   │   │   │   └── business/
│   │   │   │       ├── FileEncryptor.kt     ← Encryption logic
│   │   │   │       └── FileDecryptor.kt     ← Decryption logic
│   │   │   └── AndroidManifest.xml          ← App configuration
│   │   └── build.gradle                     ← App dependencies
│   └── build.gradle                         ← Project config
└── .vscode/                                 ← VS Code settings
    ├── settings.json
    ├── tasks.json
    └── extensions.json
```

---

## Gradle Commands

### Build Commands
```powershell
cd AEPGPEncryptor

# Clean build
gradle clean

# Build debug APK
gradle assembleDebug

# Build release APK
gradle assembleRelease

# Run unit tests
gradle test

# Run all checks
gradle check

# Build and list tasks
gradle tasks
```

### Installation Commands
```powershell
# List connected devices
adb devices

# Install debug APK
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Uninstall app
adb uninstall com.aepgp.encryptor

# Clear app data
adb shell pm clear com.aepgp.encryptor
```

---

## Comparing VS Code vs Android Studio

| Feature | VS Code | Android Studio |
|---------|---------|----------------|
| **Startup Time** | ⚡ Fast (2-5 sec) | 🐌 Slow (30-60 sec) |
| **Memory Usage** | ✅ Light (~200MB) | ❌ Heavy (~2GB) |
| **Code Editing** | ✅ Excellent | ✅ Excellent |
| **Kotlin Support** | ✅ Good (via extension) | ✅ Excellent (built-in) |
| **Gradle Integration** | ⚠️ Basic | ✅ Advanced |
| **Debugging** | ⚠️ Limited | ✅ Full support |
| **Layout Editor** | ❌ No visual editor | ✅ Visual editor |
| **Profiling** | ❌ Not available | ✅ CPU/Memory profiling |
| **Emulator Control** | ⚠️ Basic (via extension) | ✅ Full control |
| **APK Analysis** | ❌ Not available | ✅ Built-in analyzer |

### **Recommendation:**
- 📝 **Use VS Code for:** Coding, quick edits, reviewing code
- 🔧 **Use Android Studio for:** Debugging, UI design, profiling, emulator

---

## Workflow: Best of Both Worlds

**Efficient Development Workflow:**

1. **Code in VS Code** (fast, lightweight)
   ```
   - Edit Kotlin/Java files
   - Navigate codebase
   - Git operations
   - Build APKs
   ```

2. **Debug in Android Studio** (when needed)
   ```
   - Set breakpoints
   - Step through code
   - Inspect variables
   - Profile performance
   ```

3. **Test on Device** (using ADB from VS Code)
   ```
   - Install APK: Ctrl+Shift+B → "Install Debug APK"
   - View logs: Ctrl+Shift+P → "View Logcat"
   - Test app on phone
   ```

---

## Testing the Setup

### Test 1: Build the APK

```powershell
# In VS Code terminal:
cd AEPGPEncryptor
gradle assembleDebug
```

**Expected:** APK created at `app/build/outputs/apk/debug/app-debug.apk`

### Test 2: Connect Device

```powershell
# Enable USB debugging on phone
# Connect via USB

adb devices
```

**Expected:** Shows your device:
```
List of devices attached
ABC123XYZ    device
```

### Test 3: Install and Run

```powershell
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

**Expected:** 
```
Performing Streamed Install
Success
```

### Test 4: View Logs

```powershell
# Clear old logs
adb logcat -c

# Open app on phone

# View logs in VS Code
adb logcat | Select-String "com.aepgp"
```

**Expected:** See app logs when you open the app

---

## Troubleshooting

### Issue: "Gradle not found"

**Solution:**
```powershell
# Option 1: Use Gradle wrapper (if exists)
cd AEPGPEncryptor
.\gradlew assembleDebug

# Option 2: Install Gradle
# Download from https://gradle.org/releases/
# Add to PATH
```

### Issue: "ADB not recognized"

**Solution:**
```powershell
# Add to PATH (Windows):
# 1. Open System Properties → Environment Variables
# 2. Edit PATH variable
# 3. Add: C:\Users\YourUsername\AppData\Local\Android\Sdk\platform-tools

# Verify:
adb version
```

### Issue: "Android SDK not found"

**Solution:**
```powershell
# Option 1: Install Android Studio (includes SDK)
# Option 2: Download SDK standalone
# Set ANDROID_HOME environment variable
```

### Issue: "Java version incorrect"

**Solution:**
```powershell
# Check version
java -version

# Should be JDK 17 or higher
# Download from: https://adoptium.net/
```

---

## Additional Resources

### VS Code Android Extensions
- [Android IDE](https://marketplace.visualstudio.com/items?itemName=anan.android-dev-ext)
- [Kotlin Language](https://marketplace.visualstudio.com/items?itemName=fwcd.kotlin)
- [Gradle for Java](https://marketplace.visualstudio.com/items?itemName=vscjava.vscode-gradle)

### Documentation
- [Android Developer Docs](https://developer.android.com/)
- [Kotlin Language](https://kotlinlang.org/docs/home.html)
- [Gradle Build Tool](https://docs.gradle.org/)

### Tools
- [Android SDK Download](https://developer.android.com/studio#command-tools)
- [Gradle Download](https://gradle.org/releases/)
- [Java JDK Download](https://adoptium.net/)

---

## Quick Reference Card

```
╔══════════════════════════════════════════════════════════╗
║           VS Code Android Development                    ║
╠══════════════════════════════════════════════════════════╣
║ BUILD                                                    ║
║  Ctrl+Shift+B          → Build Debug APK                ║
║  Ctrl+Shift+P → Tasks  → Show all build tasks           ║
║                                                          ║
║ RUN                                                      ║
║  adb devices           → List connected devices         ║
║  adb install -r <apk>  → Install APK on device         ║
║                                                          ║
║ DEBUG                                                    ║
║  adb logcat            → View all logs                  ║
║  adb logcat -c         → Clear logs                     ║
║  adb shell             → Open device shell              ║
║                                                          ║
║ CODE                                                     ║
║  F12                   → Go to definition               ║
║  Ctrl+Click            → Go to definition               ║
║  Shift+Alt+F           → Format document                ║
║  Ctrl+Space            → IntelliSense                   ║
║                                                          ║
║ GRADLE                                                   ║
║  gradle assembleDebug  → Build debug APK                ║
║  gradle clean          → Clean build                    ║
║  gradle test           → Run tests                      ║
╚══════════════════════════════════════════════════════════╝
```

---

**You're all set! VS Code is now configured for Android development.** 🚀

**Quick Test:**
1. Press `Ctrl+Shift+B` in VS Code
2. Select "Build Debug APK"
3. Wait for build to complete
4. Connect phone and run "Install Debug APK"

Happy coding! 💻📱
