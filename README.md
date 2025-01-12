# Volcano Integration for Home Assistant

**This integration is under heavy, active development. There may be multiple updates per day, possibly resulting in errors or disruption to the integration or Home Assistant. I will change this notice once the software is available for a proper release.**

A custom Home Assistant integration to connect and control the **Storz & Bickel Volcano Hybrid Vaporizer** via Bluetooth. This integration enables precise control over the vaporizer's heat and pump functions, real-time monitoring of temperature, and seamless automation into the Home Assistant scripting and automation systems.

---

## Features

- **Temperature Control**: Set the heater temperature between 40°C and 230°C with 1°C precision.
- **Pump & Heat Control**: Turn the pump and heat **ON** or **OFF** individually.
- **Real-Time Temperature Monitoring**: Monitor the current heater temperature in real-time.
- **Bluetooth Status**: View the current Bluetooth connection status (Connected, Disconnected, etc.).
- **Device Configuration**: Control the LED screen brightness and auto shut-off timer.
- **Full Automation/Scripting Support**: Use services and device entities to build your own vaporization workflows.
- **User-Friendly Services**: Use built-in Home Assistant services to control the vaporizer.

---

## Requirements

- **Bluetooth Hardware**: The host system must have Bluetooth hardware or a compatible USB Bluetooth adapter.
- **Python Dependency**: Requires the `bleak` library (minimum version 0.20.0).

---

## Installation

### Installation via HACS

1. **Prerequisites**:
   - Ensure you have [HACS](https://hacs.xyz/) installed in your Home Assistant setup.

2. **Add the Repository to HACS**:
   - In Home Assistant, navigate to **HACS > Integrations**.
   - Click the **"+"** button to add a new repository.
   - Enter the repository URL: `https://github.com/Chuffnugget/volcano_integration`.
   - Select **Integration** as the category.

3. **Install the Integration**:
   - After adding, find **Volcano Integration** in the HACS Integrations list.
   - Click **Install**.

4. **Restart Home Assistant**:
   - After installation, restart Home Assistant to activate the integration.

5. **Configure the Integration**:
   - Navigate to **Settings > Devices & Services**, find **Volcano Integration**, and follow the setup instructions. The configuration menu will scan for Bluetooth devices, dsiplaying a list. Simply select your Volcano Vaporizer and the setup will complete.

### Manual Installation

1. **Download the Integration**:
   - Clone or download the repository from GitHub: [GitHub Repository](https://github.com/Chuffnugget/volcano_integration).

2. **Place in Custom Components**:
   - Extract the files and place the `volcano_integration` folder in the `custom_components` directory within your Home Assistant configuration directory.

3. **Install Dependencies**:
   - Ensure the required dependencies (e.g., `bleak>=0.20.0`) are installed. Home Assistant should handle this automatically.

4. **Restart Home Assistant**:
   - After placing the files, restart Home Assistant.

5. **Add the Integration**:
   - Navigate to **Settings > Devices & Services > Add Integration**, search for "Volcano Integration," and follow the setup instructions.

---

## Usage

### Entities

- **Sensors**:
  - **Current Temperature**: Displays the current temperature of the vaporizer.
  - **Heat Status**: Shows whether the heater is **ON**, **OFF**, or in an unknown state.
  - **Pump Status**: Indicates if the pump is **ON**, **OFF**, or in an unknown state.
  - **Bluetooth Status**: Displays the current Bluetooth connection status.

- **Buttons**:
  - **Connect**: Establishes a Bluetooth connection with the vaporizer.
  - **Disconnect**: Ends the Bluetooth connection.
  - **Pump On/Off**: Turns the pump **ON** or **OFF**.
  - **Heat On/Off**: Turns the heater **ON** or **OFF**.

- **Number Control**:
  - **Heater Temperature Setpoint**: Allows setting the desired temperature between 40°C and 230°C.

### Services

- `volcano_integration.connect`: Connect to the vaporizer.
- `volcano_integration.disconnect`: Disconnect from the vaporizer.
- `volcano_integration.pump_on`: Turn the pump **ON**.
- `volcano_integration.pump_off`: Turn the pump **OFF**.
- `volcano_integration.heat_on`: Turn the heater **ON**.
- `volcano_integration.heat_off`: Turn the heater **OFF**.
- `volcano_integration.set_temperature`: Set the heater temperature.
