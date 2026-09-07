# Silines Integration for Home Assistant

**English Setup Guide** | [Русское руководство по настройке](./README_RU.md)

An official-grade custom integration for **Silines** controllers (e.g., BOREAS series) in Home Assistant. This integration operates completely locally via asynchronous HTTP polling.

---

## 📦 Installation

### Method 1: Via HACS (Recommended)

1. Open **HACS** in your Home Assistant panel.
2. Click on the **three dots** in the top right corner and select **Custom repositories**.
3. Paste the URL of this repository into the **Repository** field.
4. Select **Integration** as the category and click **Add**.
5. Find **Silines** in the integration list and click **Download**.
6. **Restart** your Home Assistant server.

### Method 2: Manual Installation

1. Clone or download this repository.
2. Copy the `custom_components/silines` folder into your Home Assistant configuration directory (e.g., `/config/custom_components/silines`).
3. **Restart** your Home Assistant server.

---

## ⚙️ Configuration

1. In the Home Assistant UI, navigate to **Settings** ➡️ **Devices & Services**.
2. Click the **Add Integration** button in the bottom right corner.
3. Search for **Silines** and select it.
4. Fill in the network and authentication details form:
   * **Device IP Address:** The local IP address of your Silines controller.
   * **Port:** The HTTP port (Default is `80`).
   * **Username / Password:** Access credentials matching your device's web interface security locks.
   * **Polling Interval:** The data refresh rate in seconds (Minimum is `5`s).
   * **API Timeout:** Maximum network wait time for controller response.
5. Click **Submit**.
