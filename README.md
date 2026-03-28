# Flight & Weather Tracker

A real-time aviation and meteorology display for the Adafruit Matrix Portal M4. This script tracks aircraft within a specific radius of your location using the FlightRadar24 API. When flights are detected, it displays detailed flight information along with a custom-colored airplane icon representing the airline's livery. If no flights are found after two check cycles, the display switches to show local weather conditions via the OpenWeatherMap API.

## ✈️ Features

- **Real-time Flight Tracking**: Calculates a bounding box based on a mile-radius from your specific latitude/longitude.
- **Detailed Flight Info**: Displays Flight Number, Airline Name, Origin/Destination (IATA codes and full names), Aircraft Model, and Registration.
- **Dynamic Liveries**: The 24x24 pixel airplane icon changes colors to match the branding of over 20+ major airlines.
- **Flight Status Indicator**: A color-coded dot indicates if a flight is on-time (green), delayed <30-mins (yellow), or delayed >30-mins (red).
- **Smart Weather Mode**: Automatically switches to local weather if the skies are empty.
- **Weather Icons**: Custom-drawn icons for clear, sunny, cloudy, rainy, snowy, and thunderstorm conditions.
- **Memory Optimized**: Specifically tuned for the SAMD51 (M4) processor using JSON streaming, buffer truncation, and low-bit-depth display management to prevent `MemoryError` crashes.

## 🛠️ Hardware Requirements

- [Adafruit Matrix Portal M4](https://www.adafruit.com/product/4745)
- 64x32 RGB LED Matrix Display - [Adafruit](https://www.adafruit.com/product/2278) or [AliExpress](https://www.aliexpress.us/item/2251832064290423.html) (4mm pitch recommended)
- Acrylic Diffuser - [Adafruit](https://www.adafruit.com/product/4594) or [DigiKey](https://www.digikey.com/en/products/detail/adafruit-industries-llc/4749/13426657) or other sources
- 5V 1A (or higher) USB Power Supply

## 📚 Prerequisites

1. **CircuitPython 9.x**: Ensure your Matrix Portal is running the latest stable version of CircuitPython.
2. **Library Bundle**: Download the [Adafruit CircuitPython Library Bundle](https://circuitpython.org/libraries) and place the following folders/files in the `lib` folder on the Matrix Portal M4:
   - 📁 `adafruit_bitmap_font`
   - 📁 `adafruit_bus_device`
   - 📁 `adafruit_display_text`
   - 📁 `adafruit_esp32spi`
   - 📁 `adafruit_imageload`
   - 📁 `adafruit_io`
   - 📁 `adafruit_matrixportal`
   - 📁 `adafruit_minimqtt`
   - 📁 `adafruit_portalbase`
   - 📄 `adafruit_connection_manager.mpy`
   - 📄 `adafruit_debouncer.mpy`
   - 📄 `adafruit_fakerequests.mpy`
   - 📄 `adafruit_lis3dh.mpy`
   - 📄 `adafruit_requests.mpy`
   - 📄 `adafruit_ticks.mpy`
   - 📄 `neopixel.mpy`

## ⚙️ Configuration

### Initial Setup
Follow the [Adafruit instructions](https://learn.adafruit.com/adafruit-matrixportal-m4/prep-the-matrixportal) to prep the Matrix Portal M4.

### Personalization
Create a `settings.toml` file in the root directory of your `CIRCUITPY` drive with the following variables:

```toml
WIFI_SSID = "Your_WiFi_Name"
WIFI_PASSWORD = "Your_WiFi_Password"
# Your location as "Latitude, Longitude"
LOCATION = 40.7128, -74.0060
# Radius in miles to look for planes and local weather. 3-miles is a good distance to locate aircraft and collect the data about them before they are overhead.
SEARCH_DISTANCE_MILES = 3
# Get a free API key at openweathermap.org
OPENWEATHERMAP_API_KEY = "your_api_key_here"
```

## 🚀 Installation

1. Connect your Matrix Portal M4 to your computer via USB.
2. Copy the `code.py` file to the `CIRCUITPY` drive.
3. Ensure your `settings.toml` is configured correctly.
4. The board will automatically restart and begin searching for flights.

## 🪲 Debugging
Connect the Matrix Portal to your computer using USB and use [Putty](https://putty.org/index.html) or similar to connect to the Matrix Portal. If using Windows, find the COM port the portal is on using the device manager (if you're using Linux, you know how to find the COM port the device is on 😁), and setup a serial connection in Putty to that port at 115200. The code has a ton of print statements that will print out helpful messages about errors, flights it sees, weather updates, etc.

## 🧠 Technical Notes (Memory Management)

The SAMD51 processor on the Matrix Portal M4 has limited RAM (192KB). To ensure stability, this script uses several advanced techniques:

- **JSON Truncation**: FlightRadar24 returns massive JSON files. This script uses a streaming request and "cuts off" the data at the `flightHistory` tag to keep the data under 9KB.
- **Persistent UI**: Labels and Groups are created once at startup. Updating `.text` is much more memory-efficient than deleting and recreating labels.
- **Bit Depth 2**: The matrix display is initialized at bit-depth 2 to free up several kilobytes of RAM normally reserved for the framebuffer.
- **Manual GC**: `gc.collect()` is called at critical points (before network handshakes) to prevent memory fragmentation.

## 🤝 Credits

- Flight data provided by [FlightRadar24](https://www.flightradar24.com).
- Weather data provided by [OpenWeatherMap](https://openweathermap.org).
- Original MatrixPortal concept by Adafruit Industries.

---
*Safe skies and happy tracking!*
