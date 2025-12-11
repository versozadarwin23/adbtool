The "Dars V3 Controller" is a desktop application designed to simplify the management and control of multiple Android devices simultaneously. It leverages the Android Debug Bridge (ADB) to send commands quickly and efficiently. Through its simple interface, you can perform various tasks such as tapping, swiping, and running specific commands on all connected devices at once.

---

### Getting Started

1. **Connect Your Devices**: Ensure **USB Debugging** is enabled on all Android devices you intend to use. Then, connect them to your computer using USB cables.

2. **Refresh the Device List**: On the left-side control panel, click the **"Refresh"** button. The application will automatically detect and list all connected devices by their serial number.

3. **Select the Device to Control**: Click on a device's serial number from the list. When selected, the device's screen will appear on the right side of the app, allowing you to control it directly.

---

### Controlling the Device Screen

The main feature of this tool is the **live screen control**. Once your device is connected and its screen is visible, you can perform the following actions:

* **Tap (Single Click)**: Click anywhere on the screen to simulate a single tap.
* **Swipe**: Click and drag your mouse on the device screen. This will perform a swipe gesture just like on the physical device.
* **Long Press**: Press and hold the left mouse button for half a second (0.5s). This will execute a long press command.

Additionally, there are pre-set buttons below the device screen for quick actions:
* **Home**: Returns to the device's home screen.
* **Back**: Navigates back to the previous screen.
* **Recents**: Shows the list of recently used apps.
* **Scroll Down/Up**: Scrolls the screen up or down.

---

### Additional Features (Tab View)

The left-side panel features a **Tab View** with various command categories.

* **FB Lite**: Use this tab to open Facebook posts, share links, or launch/force-stop the Facebook Lite app.
* **TikTok**: Open TikTok post URLs or launch/force-stop the TikTok Lite app.
* **YouTube**: Visit YouTube video URLs or launch/force-stop the YouTube app (using Chrome).
* **Text Cmd**: Select a text file and send a random line of text to all devices. You can also remove emojis from the selected file.
* **Image**: Enter the filename of an image in your phone's `Download` folder to share it via Facebook Lite.

---

### Important Notes

* **General Control**: All commands (except for taps, swipes, and long presses) are sent to **all connected devices simultaneously**.
* **Stop All Commands**: To halt any currently running commands, click the **"Stop All Commands"** button.
* **Auto-Update**: The tool includes an update feature. Click the "Update" button to automatically download the latest version to your Desktop.
* **ADB Path**: Ensure that **ADB (Android Debug Bridge)** is installed and added to your system's PATH for the application to function correctly.
        


<img width="1920" height="1042" alt="image" src="https://github.com/user-attachments/assets/22d2a0d0-8da2-41cf-802d-960efcd8e1f7" />
