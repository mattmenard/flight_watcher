import time
from random import randrange
import board # type: ignore
import terminalio
from adafruit_matrixportal.matrixportal import MatrixPortal
from adafruit_portalbase.network import HttpError
import json
import os
import math

import adafruit_display_text.label
import displayio
import gc

import busio
from digitalio import DigitalInOut
import neopixel
from adafruit_esp32spi import adafruit_esp32spi
from adafruit_esp32spi.adafruit_esp32spi_wifimanager import WiFiManager

from microcontroller import watchdog as w
from watchdog import WatchDogMode


#------------------------------ GLOBAL VARIABLES ------------------------------
FONT=terminalio.FONT

# Load wifi configuration from settings.toml
WIFI_SSID=os.getenv("CIRCUITPY_WIFI_SSID")
WIFI_PASSWORD=os.getenv("CIRCUITPY_WIFI_PASSWORD")

LOCATION = os.getenv("LOCATION")
SEARCH_DISTANCE_MILES = os.getenv("SEARCH_DISTANCE_MILES")

LAT = (LOCATION.split(","))[0]
LON = ((LOCATION.split(","))[1]).lstrip()

OWM_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
UNITS = "imperial"

if not WIFI_SSID or not WIFI_PASSWORD or not LOCATION or not SEARCH_DISTANCE_MILES:
    print("Missing configuration! Please add CIRCUITPY_WIFI_SSID, CIRCUITPY_WIFI_PASSWORD, LOCATION, and SEARCH_DISTANCE_MILES to settings.toml file.")
    raise RuntimeError("Missing configuration")

# How often to query FlightRadar24
QUERY_DELAY=15

# Colors and timings
ROW_ONE_COLOUR=0xEE82EE
ROW_TWO_COLOUR=0xEE82EE
ROW_THREE_COLOUR=0xEE82EE
PAUSE_BETWEEN_LABEL_SCROLLING=3
PLANE_SPEED=0.06 
#PLANE_SPEED=0.08 # Too slow
#PLANE_SPEED=0.04 # Too fast
TEXT_SPEED=0.04

# 
w.timeout=16 # timeout in seconds
w.mode = WatchDogMode.RESET


#----------------------------- UTILITY FUNCTIONS ------------------------------
def get_bounding_box(lat, lon, distance_miles):

    # Constants for Earth's radius and degree equivalents
    earth_radius_miles = 3958.8
    miles_per_degree_lat = 69.17
    
    # Calculate latitude offset
    lat_offset = float(distance_miles) / miles_per_degree_lat
    
    # Calculate longitude offset (varies based on latitude)
    # 1 degree of longitude = cosine(latitude) * 69.17 miles
    lat_rad = math.radians(float(lat))
    miles_per_degree_lon = math.cos(lat_rad) * miles_per_degree_lat
    lon_offset = float(distance_miles) / miles_per_degree_lon
    
    return {
        "lat_min": float(lat) - lat_offset,
        "lat_max": float(lat) + lat_offset,
        "lon_min": float(lon) - lon_offset,
        "lon_max": float(lon) + lon_offset
    }

def scroll(line):
    line.x=matrixportal.display.width
    for i in range(matrixportal.display.width+1,0-line.bounding_box[2],-1):
        line.x=i
        w.feed()
        time.sleep(TEXT_SPEED)

def clear_display():
    gc.collect()

#------------------------------------------------------------------------------


boundsBox = get_bounding_box(LAT, LON, SEARCH_DISTANCE_MILES)

# URLs
FLIGHT_SEARCH_HEAD="https://data-cloud.flightradar24.com/zones/fcgi/feed.js?bounds="
FLIGHT_SEARCH_TAIL="&faa=1&satellite=1&mlat=1&flarm=1&adsb=1&gnd=0&air=1&vehicles=0&estimated=0&maxage=14400&gliders=0&stats=0&ems=1&limit=1"
FLIGHT_SEARCH_URL=FLIGHT_SEARCH_HEAD+str(boundsBox["lat_max"])+","+str(boundsBox["lat_min"])+","+str(boundsBox["lon_min"])+","+str(boundsBox["lon_max"])+FLIGHT_SEARCH_TAIL
FLIGHT_LONG_DETAILS_HEAD="https://data-live.flightradar24.com/clickhandler/?flight="
WEATHER_URL = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&appid={OWM_API_KEY}&units={UNITS}"

# Request headers
rheaders = {
     "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:106.0) Gecko/20100101 Firefox/106.0",
     "cache-control": "no-store, no-cache, must-revalidate, post-check=0, pre-check=0",
     "accept": "application/json"
}

esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)
spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)
status_light = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.2)

# Top level matrixportal object
matrixportal = MatrixPortal(
    headers=rheaders,
    esp=esp,
    rotation=0,
    debug=True,
    bit_depth=2
)

matrixportal.network.connect() # This uses the settings.toml credentials

if matrixportal.network.is_connected:
    print(f"Successfully connected to {WIFI_SSID}.")
else:
    print(f"Could not connected to {WIFI_SSID}.")



#json_size=14336
json_size = 9216
json_bytes = bytearray(json_size)


# ---- PLANE BITMAP ANNIMATION IMAGE ----
plane_bmp = displayio.Bitmap(24, 24, 6)
plane_palette = displayio.Palette(6)
plane_palette.make_transparent(0)
plane_palette[1] = 0x003366 # Primary Airline livery color
plane_palette[2] = 0xa5caef # Secondary Airline livery color
plane_palette[3] = 0xa4a4a4 # Terciary Airline livery color
plane_palette[4] = 0xb0b0b0 # Outline color
plane_palette[5] = 0x000000 # Accent color

plane_outline = [(11,1), (12,1), (13,1),
                 (11,2), (13,2),
                 (10,3), (13,3),
                 (7,4), (8,4), (9,4), (10,4), (12,4), (13,4),
                 (6,5), (9,5), (11,5), (12,5), (22, 5), (23,5),
                 (6,6), (7,6), (8,6), (10,6), (11,6), (12,6), (21,6), (23,6),
                 (8,7), (10,7), (12,7), (21,7), (23,7),
                 (7,8), (9,8), (10,8), (12,8), (20,8), (23,8),
                 (2,9), (3,9), (4,9), (5,9), (6,9), (8,9), (9,9), (10,9), (11,9), (13,9), (14,9), (15,9), (16,9), (17,9), (18,9), (19,9), (23,9),
                 (1,10), (22,10),
                 (0,11), (19,11), (20,11), (21,11), (22,11),
                 (0,12), (3,12), (17,12), (22,12),
                 (1,13), (22,13),
                 (2,14), (3,14), (4,14), (5,14), (6,14), (8,14), (9,14), (10,14), (11,14), (13,14), (14,14), (15,14), (16,14), (17,14), (18,14), (19,14), (23,14),
                 (7,15), (9,15), (10,15), (12,15), (20,15), (23,15),
                 (8,16), (10,16), (12,16), (21,16), (23,16),
                 (6,17), (10,17), (11,17), (7,17), (8,17), (12,17), (21,17), (23,17),
                 (6,18), (9,18), (11,18), (12,18), (22,18), (23,18), 
                 (7,19), (8,19), (9,19), (10,19), (12,19), (13,19),
                 (10,20), (13,20),
                 (11,21), (13,21),
                 (11,22), (12,22), (13,22)]
for x, y in plane_outline:
    plane_bmp[x, y] = 4

plane_accents = [(12,2),
                 (11,3), (12,3),
                 (11,4),
                 (7,5), (10,5),
                 (9,6), (22,6),
                 (9,7), (11,7), (22,7),
                 (8,8), (11,8), (21,8),
                 (7,9), (12,9), (20,9),
                 (23,10), 
                 (2,11), (18,11), (23,11),
                 (2,12), (18,12), (19,12), (20,12), (21,12), (23,12), 
                 (23,13),
                 (7,14), (12,14), (20, 14), 
                 (8,15), (11,15), (21,15),
                 (9,16), (11,16), (22,16), 
                 (9,17), (22,17), 
                 (7,18), (10,18), 
                 (11,19),
                 (11, 20), (12,20),
                 (12,21)]
for x, y in plane_accents:
    plane_bmp[x, y] = 5

plane_primary_livery = [(8,5),
                        (22,8),
                        (21,9), (22,9),
                        (2,10), (3,10), (4,10), (5,10), (6,10), (7,10), (8,10), (9,10), (10,10), (11,10), (12,10), (13,10), (14,10), (15,10), (16,10), (17,10), (18,10), (19,10), (20,10), (21,10),
                        (1,11), (3,11), (4,11), (5,11), (6,11), (7,11), (8,11), (9,11), (10,11), (11,11), (12,11), (13,11), (14,11), (15,11), (16,11), (17,11),
                        (1,12),
                        (8,18)]
for x, y in plane_primary_livery:
    plane_bmp[x, y] = 1

plane_secondary_livery = [(2,13), (3,13), (4,13), (5,13), (6,13), (7,13), (8,13), (9,13), (10,13), (11,13), (12,13), (13,13), (14,13), (15,13), (16,13), (17,13), (18,13), (19,13), (20,13), (21,13),
                          (21,14), (22,14),
                          (22,15)]
for x, y in plane_secondary_livery:
    plane_bmp[x, y] = 2

plane_terciary_livery = [(4,12), (5,12), (6,12), (7,12), (8,12), (9,12), (10,12), (11,12), (12,12), (13,12), (14,12), (15,12), (16,12)]
for x, y in plane_terciary_livery:
    plane_bmp[x, y] = 3

# Now that the bitmap is painted, delete the variables to free the memory.
del plane_outline, plane_accents, plane_primary_livery, plane_secondary_livery, plane_terciary_livery
gc.collect()

plane_tileGrid = displayio.TileGrid(plane_bmp, pixel_shader=plane_palette)
plane_group = displayio.Group(x=matrixportal.display.width + 24, y=4, scale=1)
plane_group.append(plane_tileGrid)


#---- FLIGHT INFORMATION LABELS ----
flight_num_airline_label = adafruit_display_text.label.Label(FONT, color=ROW_ONE_COLOUR, text="", x=1, y=5)
flight_src_dest_label = adafruit_display_text.label.Label(FONT, color=ROW_TWO_COLOUR, text="", x=1, y=16)
airplane_details_label = adafruit_display_text.label.Label(FONT, color=ROW_THREE_COLOUR, text="", x=1, y=26)

# ---- FLIGHT STATUS INDICATOR IMAGE ----
flight_status_indicator_bmp = displayio.Bitmap(4, 4, 2)
flight_status_palette = displayio.Palette(2)
flight_status_palette.make_transparent(0)
flight_status_palette[1] = 0x00FE45 # Green

flight_status_indicator = [(1,0), (2,0), (0,1), (1,1), (2,1), (3,1), (0,2), (1,2), (2,2), (3,2), (1,3), (2,3)]
for x, y in flight_status_indicator:
    flight_status_indicator_bmp[x, y] = 1

flight_status_indicator_tile_grid = displayio.TileGrid(flight_status_indicator_bmp, pixel_shader=flight_status_palette,  x=43, y=3)

flight_details_group = displayio.Group()
flight_details_group.append(flight_status_indicator_tile_grid)
flight_details_group.append(flight_num_airline_label)
flight_details_group.append(flight_src_dest_label)
flight_details_group.append(airplane_details_label)

flight_num_label = airline_name_label = airport_src_dest_iata_codes_label = airport_src_dest_name_label = airplane_code_label = aircraft_make_model_label = flight_status = ''





# ---- WEATHER DISPLAY ----
weather_group = displayio.Group()

# Simple Weather Icon Bitmap (12x12)
# Indices: 0: Transparent, 1: Sun, 2: Cloud, 3: Rain/Drop, 4: Snow/Flake
weather_bmp = displayio.Bitmap(12, 12, 5)
weather_pal = displayio.Palette(5)
weather_pal.make_transparent(0)
weather_pal[1] = 0xFFFF00 # Sun (Yellow)
weather_pal[2] = 0x808080 # Cloud (Grey)
weather_pal[3] = 0x0000FF # Rain (Blue)
weather_pal[4] = 0xFFFFFF # Snow (White)

weather_tg = displayio.TileGrid(weather_bmp, pixel_shader=weather_pal, x=1, y=15)
weather_current_label = adafruit_display_text.label.Label(FONT, color=0xFFFFFF, text="", x=5, y=5)
weather_temp_max_label = adafruit_display_text.label.Label(FONT, color=0xFFFFFF, text="", x=16, y=16)
weather_temp_min_label = adafruit_display_text.label.Label(FONT, color=0xFFFFFF, text="", x=16, y=26)

weather_group.append(weather_tg)
weather_group.append(weather_current_label)
weather_group.append(weather_temp_max_label)
weather_group.append(weather_temp_min_label)




# FLIGHT DISPLAY FUNCTIONS

def plane_animation(airline_string):
    gc.collect()

    # Determine colors based on the evaluated string
    # You can customize these hex codes or use your ROW_X_COLOUR variables
    airline_string = airline_string.upper()
    
    if "EMERGENCY" in airline_string or "MEDFLIGHT" in airline_string:
        # Red / White / Red
        colors = [0xFF0000, 0xFFFFFF, 0xFF0000]
    elif "PRIVATE" in airline_string:
        # Gold / Silver / Bronze
        colors = [0xD4AF37, 0xC0C0C0, 0xCD7F32]
    elif "AIR FORCE" in airline_string:
        # Blue / Grey / Blue
        colors = [0x205EA0, 0xF1F1F1, 0x205EA0]
    elif "ARMY" in airline_string:
        # Gold / White / Green
        colors = [0xF9CB34, 0xFFFFFF, 0x697866]
    elif "CIVIL AIR PATROL" in airline_string:
        # Blue / White / Grey
        colors = [0x205EA0, 0xFFFFFF, 0xF1F1F1]
    elif "POLICE" in airline_string:
        # Med. Blue / Light Blue / Dark Blue
        colors = [0x1C6CD4, 0x5394DF, 0x142C5C]
    elif "ALLEGIANT" in airline_string:
        # Blue / Orange / Yellow
        colors = [0x01579B, 0xF48120, 0xFBCE20]
    elif "AMERICAN" in airline_string:
        # Red / Blue / Silver
        colors = [0xB61F23, 0x0D73B1, 0xC7D0D7]
    elif "AVIANCA" in airline_string:
        # Red / Red / White
        colors = [0xDA291C, 0xDA291C, 0xFFFFFF]
    elif "BRITISH" in airline_string:
        # Blue / Red / White
        colors = [0x075AAA, 0xEB2226, 0xEFE9E5]
    elif "CAPE" in airline_string:
        # Blue / White / Blue
        colors = [0x005DAA, 0xFFFFFF, 0x005DAA]
    elif "COPA" in airline_string:
        # Blue / White / Blue
        colors = [0x0060A9, 0xFFFFFF, 0x0060A9]
    elif "DELTA" in airline_string:
        # BLue / Red / White
        colors = [0x003366, 0xC01933, 0xFFFFFF]
    elif "FEDEX" in airline_string:
        # Purple / Orange / Gray
        colors = [0x4D148C, 0xFF6200, 0xCCCCCC]
    elif "FLEX" in airline_string:
        # Gold / Gold / Silver
        colors = [0xD4AF37, 0xD4AF37, 0xC0C0C0]
    elif "FRANCE" in airline_string:
        # Blue / White / Red
        colors = [0x060935, 0xFFFFFF, 0xF30012]
    elif "FRONTIER" in airline_string:
        # Green / White / Green
        colors = [0x0F6744, 0xFFFFFF, 0x0F6744]
    elif "INDIA" in airline_string:
        # Red / Gold / Red
        colors = [0xCC0200, 0xFE9901, 0xFF0100]
    elif "JETBLUE" in airline_string:
        # Blue / Blue / Blue
        colors = [0x0033A0, 0x0033A0, 0x0033A0]
    elif "LUFTHANSA" in airline_string:
        # Blue / Yellow / Grey
        colors = [0x05164D, 0xFFAD00, 0x9B9B9B]
    elif "MEXICO" in airline_string:
        # Blue / Blue / Gray
        colors = [0x040444, 0x040444, 0xC0C0C0]
    elif "NETJETS" in airline_string:
        # Gold / Gold / Silver
        colors = [0xD4AF37, 0xD4AF37, 0xC0C0C0]
    elif "SOUTHWEST" in airline_string:
        # Blue / Red / Yellow
        colors = [0x304CB2, 0xD5152E, 0xFFBF27 ]
    elif "SPIRIT" in airline_string:
        # Yellow / Black / Yellow
        colors = [0xFFEC00, 0x808080, 0xFFEC00]
    elif "SUN" in airline_string:
        # Orange / Blue / White
        colors = [0xEB7C3B, 0x163A81, 0xFFFFFF]
    elif "UNITED" in airline_string:
        # Blue / Blue / White
        colors = [0x0033A0, 0x0033A0, 0xFFFFFF]
    else:
        # Default: Use the global row colors defined in your config
        colors = [ROW_ONE_COLOUR, ROW_TWO_COLOUR, ROW_THREE_COLOUR]

    # Update the palette before starting the animation
    plane_palette[1] = colors[0]
    plane_palette[2] = colors[1]
    plane_palette[3] = colors[2]

    # Run the animation
    matrixportal.display.root_group = plane_group
    for i in range(matrixportal.display.width + 24, -24, -1):
        plane_group.x = i
        w.feed()
        time.sleep(PLANE_SPEED)

    gc.collect()


def display_flight():
    gc.collect()
    matrixportal.display.root_group = flight_details_group

    flight_num_airline_label.color = plane_palette[1]
    
    # Update status color
    if flight_status == "green": flight_status_palette[1] = 0x00FE45
    elif flight_status == "yellow": flight_status_palette[1] = 0xFFFD00
    elif flight_status == "red": flight_status_palette[1] = 0xFF0000
    else: flight_status_palette[1] = 0x000000

    flight_num_airline_label.text = flight_num_label
    flight_src_dest_label.text = airport_src_dest_iata_codes_label
    airplane_details_label.text = airplane_code_label
    
    time.sleep(PAUSE_BETWEEN_LABEL_SCROLLING)
    
    for label, long, short in [
        (flight_num_airline_label, airline_name_label, flight_num_label),
        (flight_src_dest_label, airport_src_dest_name_label, airport_src_dest_iata_codes_label),
        (airplane_details_label, aircraft_make_model_label, airplane_code_label)
    ]:
        # Handle status indicator toggle
        prev_color = flight_status_palette[1]

        # If the flight number label is being scrolled, then shut off the
        # flight status indicator, but keep the color to reset the indicator
        # later.
        if label == flight_num_airline_label:
            flight_status_palette[1] = 0x000000

        label.x = matrixportal.display.width + 1
        label.text = long
        scroll(label)
        label.text = short
        label.x = 1
        
        flight_status_palette[1] = prev_color
        time.sleep(PAUSE_BETWEEN_LABEL_SCROLLING)



# WEATHER DISPLAY FUCTIONS

def display_weather():
    matrixportal.display.root_group = weather_group
    

def draw_weather_icon(condition, is_day):
    """Draws a simple shape based on weather condition"""
    weather_bmp.fill(0)
    cond = condition.lower()

    if "clear" in cond:
        weather_bmp[3,0]=weather_bmp[4,0]=weather_bmp[5,0]=weather_bmp[6,0]=weather_bmp[7,0]=weather_bmp[8,0]=1 if is_day else 2
        weather_bmp[2,1]=weather_bmp[3,1]=weather_bmp[4,1]=weather_bmp[5,1]=weather_bmp[6,1]=weather_bmp[7,1]=weather_bmp[8,1]=weather_bmp[9,1]=1 if is_day else 2
        weather_bmp[1,2]=weather_bmp[2,2]=weather_bmp[3,2]=weather_bmp[4,2]=weather_bmp[5,2]=weather_bmp[6,2]=weather_bmp[7,2]=weather_bmp[8,2]=weather_bmp[9,2]=weather_bmp[10,2]=1 if is_day else 2
        weather_bmp[0,3]=weather_bmp[1,3]=weather_bmp[2,3]=weather_bmp[3,3]=weather_bmp[4,3]=weather_bmp[5,3]=weather_bmp[6,3]=weather_bmp[7,3]=weather_bmp[8,3]=weather_bmp[9,3]=weather_bmp[10,3]=weather_bmp[11,3]=1 if is_day else 2
        weather_bmp[0,4]=weather_bmp[1,4]=weather_bmp[2,4]=weather_bmp[3,4]=weather_bmp[4,4]=weather_bmp[5,4]=weather_bmp[6,4]=weather_bmp[7,4]=weather_bmp[8,4]=weather_bmp[9,4]=weather_bmp[10,4]=weather_bmp[11,4]=1 if is_day else 2
        weather_bmp[0,5]=weather_bmp[1,5]=weather_bmp[2,5]=weather_bmp[3,5]=weather_bmp[4,5]=weather_bmp[5,5]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[8,5]=weather_bmp[9,5]=weather_bmp[10,5]=weather_bmp[11,5]=1 if is_day else 2
        weather_bmp[0,6]=weather_bmp[1,6]=weather_bmp[2,6]=weather_bmp[3,6]=weather_bmp[4,6]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[7,6]=weather_bmp[8,6]=weather_bmp[9,6]=weather_bmp[10,6]=weather_bmp[11,6]=1 if is_day else 2
        weather_bmp[0,7]=weather_bmp[1,7]=weather_bmp[2,7]=weather_bmp[3,7]=weather_bmp[4,7]=weather_bmp[5,7]=weather_bmp[6,7]=weather_bmp[7,7]=weather_bmp[8,7]=weather_bmp[9,7]=weather_bmp[10,7]=weather_bmp[11,7]=1 if is_day else 2
        weather_bmp[0,8]=weather_bmp[1,8]=weather_bmp[2,8]=weather_bmp[3,8]=weather_bmp[4,8]=weather_bmp[5,8]=weather_bmp[6,8]=weather_bmp[7,8]=weather_bmp[8,8]=weather_bmp[9,8]=weather_bmp[10,8]=weather_bmp[11,8]=1 if is_day else 2
        weather_bmp[1,9]=weather_bmp[2,9]=weather_bmp[3,9]=weather_bmp[4,9]=weather_bmp[5,9]=weather_bmp[6,9]=weather_bmp[7,9]=weather_bmp[8,9]=weather_bmp[9,9]=weather_bmp[10,9]=1 if is_day else 2
        weather_bmp[2,10]=weather_bmp[3,10]=weather_bmp[4,10]=weather_bmp[5,10]=weather_bmp[6,10]=weather_bmp[7,10]=weather_bmp[8,10]=weather_bmp[9,10]=1 if is_day else 2
        weather_bmp[3,11]=weather_bmp[4,11]=weather_bmp[5,11]=weather_bmp[6,11]=weather_bmp[7,11]=weather_bmp[8,11]=1 if is_day else 2

    elif "cloud" in cond:
        weather_bmp[5,2]=weather_bmp[6,2]=weather_bmp[7,2]=2
        weather_bmp[4,3]=weather_bmp[5,3]=weather_bmp[6,3]=weather_bmp[7,3]=weather_bmp[8,3]=2
        weather_bmp[2,4]=weather_bmp[3,4]=weather_bmp[4,4]=weather_bmp[5,4]=weather_bmp[6,4]=weather_bmp[7,4]=weather_bmp[8,4]=weather_bmp[9,4]=2
        weather_bmp[1,5]=weather_bmp[2,5]=weather_bmp[3,5]=weather_bmp[4,5]=weather_bmp[5,5]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[8,5]=weather_bmp[9,5]=weather_bmp[10,5]=2
        weather_bmp[0,6]=weather_bmp[1,6]=weather_bmp[2,6]=weather_bmp[3,6]=weather_bmp[4,6]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[7,6]=weather_bmp[8,6]=weather_bmp[9,6]=weather_bmp[10,6]=weather_bmp[11,6]=2
        weather_bmp[0,7]=weather_bmp[1,7]=weather_bmp[2,7]=weather_bmp[3,7]=weather_bmp[4,7]=weather_bmp[5,7]=weather_bmp[6,7]=weather_bmp[7,7]=weather_bmp[8,7]=weather_bmp[9,7]=weather_bmp[10,7]=weather_bmp[11,7]=2
        weather_bmp[0,8]=weather_bmp[1,8]=weather_bmp[2,8]=weather_bmp[3,8]=weather_bmp[4,8]=weather_bmp[5,8]=weather_bmp[6,8]=weather_bmp[7,8]=weather_bmp[8,8]=weather_bmp[9,8]=weather_bmp[10,8]=weather_bmp[11,8]=2
        weather_bmp[1,9]=weather_bmp[2,9]=weather_bmp[3,9]=weather_bmp[4,9]=weather_bmp[5,9]=weather_bmp[6,9]=weather_bmp[7,9]=weather_bmp[8,9]=weather_bmp[9,9]=weather_bmp[10,9]=2

    elif "thunderstorm" in cond:
        weather_bmp[5,0]=weather_bmp[6,0]=weather_bmp[7,0]=2
        weather_bmp[4,1]=weather_bmp[5,1]=weather_bmp[6,1]=weather_bmp[7,1]=weather_bmp[8,1]=2
        weather_bmp[2,2]=weather_bmp[3,2]=weather_bmp[4,2]=weather_bmp[5,2]=weather_bmp[6,2]=weather_bmp[7,2]=weather_bmp[8,2]=weather_bmp[9,2]=2
        weather_bmp[1,3]=weather_bmp[2,3]=weather_bmp[3,3]=weather_bmp[4,3]=weather_bmp[5,3]=weather_bmp[6,3]=weather_bmp[7,3]=weather_bmp[8,3]=weather_bmp[9,3]=weather_bmp[10,3]=2
        weather_bmp[0,4]=weather_bmp[1,4]=weather_bmp[2,4]=weather_bmp[3,4]=weather_bmp[4,4]=weather_bmp[5,4]=weather_bmp[6,4]=weather_bmp[7,4]=weather_bmp[8,4]=weather_bmp[9,4]=weather_bmp[10,4]=weather_bmp[11,4]=2
        weather_bmp[0,5]=weather_bmp[1,5]=weather_bmp[2,5]=weather_bmp[3,5]=weather_bmp[4,5]=weather_bmp[5,5]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[8,5]=weather_bmp[9,5]=weather_bmp[10,5]=weather_bmp[11,5]=2
        weather_bmp[0,6]=weather_bmp[1,6]=weather_bmp[2,6]=weather_bmp[3,6]=weather_bmp[4,6]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[7,6]=weather_bmp[8,6]=weather_bmp[9,6]=weather_bmp[10,6]=weather_bmp[11,6]=2
        weather_bmp[1,7]=weather_bmp[2,7]=weather_bmp[3,7]=weather_bmp[4,7]=weather_bmp[5,7]=weather_bmp[6,7]=weather_bmp[7,7]=weather_bmp[8,7]=weather_bmp[9,7]=weather_bmp[10,7]=2

        weather_bmp[8,3]=weather_bmp[7,4]=weather_bmp[8,4]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[4,7]=weather_bmp[5,7]=weather_bmp[6,7]=weather_bmp[7,7]=weather_bmp[8,7]=weather_bmp[6,8]=weather_bmp[7,8]=weather_bmp[5,9]=weather_bmp[6,9]=weather_bmp[4,10]=weather_bmp[5,10]=weather_bmp[3,11]=weather_bmp[4,11]=1

    elif "drizzle" in cond:
        weather_bmp[5,0]=weather_bmp[6,0]=weather_bmp[7,0]=2
        weather_bmp[4,1]=weather_bmp[5,1]=weather_bmp[6,1]=weather_bmp[7,1]=weather_bmp[8,1]=2
        weather_bmp[2,2]=weather_bmp[3,2]=weather_bmp[4,2]=weather_bmp[5,2]=weather_bmp[6,2]=weather_bmp[7,2]=weather_bmp[8,2]=weather_bmp[9,2]=2
        weather_bmp[1,3]=weather_bmp[2,3]=weather_bmp[3,3]=weather_bmp[4,3]=weather_bmp[5,3]=weather_bmp[6,3]=weather_bmp[7,3]=weather_bmp[8,3]=weather_bmp[9,3]=weather_bmp[10,3]=2
        weather_bmp[0,4]=weather_bmp[1,4]=weather_bmp[2,4]=weather_bmp[3,4]=weather_bmp[4,4]=weather_bmp[5,4]=weather_bmp[6,4]=weather_bmp[7,4]=weather_bmp[8,4]=weather_bmp[9,4]=weather_bmp[10,4]=weather_bmp[11,4]=2
        weather_bmp[0,5]=weather_bmp[1,5]=weather_bmp[2,5]=weather_bmp[3,5]=weather_bmp[4,5]=weather_bmp[5,5]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[8,5]=weather_bmp[9,5]=weather_bmp[10,5]=weather_bmp[11,5]=2
        weather_bmp[0,6]=weather_bmp[1,6]=weather_bmp[2,6]=weather_bmp[3,6]=weather_bmp[4,6]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[7,6]=weather_bmp[8,6]=weather_bmp[9,6]=weather_bmp[10,6]=weather_bmp[11,6]=2
        weather_bmp[1,7]=weather_bmp[2,7]=weather_bmp[3,7]=weather_bmp[4,7]=weather_bmp[5,7]=weather_bmp[6,7]=weather_bmp[7,7]=weather_bmp[8,7]=weather_bmp[9,7]=weather_bmp[10,7]=2

        weather_bmp[3,9]=weather_bmp[6,9]=weather_bmp[11,9]=3
        weather_bmp[1,10]=weather_bmp[8,10]=3
        weather_bmp[5,11]=weather_bmp[10,11]=3

    elif "rain" in cond:
        weather_bmp[5,0]=weather_bmp[6,0]=weather_bmp[7,0]=2
        weather_bmp[4,1]=weather_bmp[5,1]=weather_bmp[6,1]=weather_bmp[7,1]=weather_bmp[8,1]=2
        weather_bmp[2,2]=weather_bmp[3,2]=weather_bmp[4,2]=weather_bmp[5,2]=weather_bmp[6,2]=weather_bmp[7,2]=weather_bmp[8,2]=weather_bmp[9,2]=2
        weather_bmp[1,3]=weather_bmp[2,3]=weather_bmp[3,3]=weather_bmp[4,3]=weather_bmp[5,3]=weather_bmp[6,3]=weather_bmp[7,3]=weather_bmp[8,3]=weather_bmp[9,3]=weather_bmp[10,3]=2
        weather_bmp[0,4]=weather_bmp[1,4]=weather_bmp[2,4]=weather_bmp[3,4]=weather_bmp[4,4]=weather_bmp[5,4]=weather_bmp[6,4]=weather_bmp[7,4]=weather_bmp[8,4]=weather_bmp[9,4]=weather_bmp[10,4]=weather_bmp[11,4]=2
        weather_bmp[0,5]=weather_bmp[1,5]=weather_bmp[2,5]=weather_bmp[3,5]=weather_bmp[4,5]=weather_bmp[5,5]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[8,5]=weather_bmp[9,5]=weather_bmp[10,5]=weather_bmp[11,5]=2
        weather_bmp[0,6]=weather_bmp[1,6]=weather_bmp[2,6]=weather_bmp[3,6]=weather_bmp[4,6]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[7,6]=weather_bmp[8,6]=weather_bmp[9,6]=weather_bmp[10,6]=weather_bmp[11,6]=2
        weather_bmp[1,7]=weather_bmp[2,7]=weather_bmp[3,7]=weather_bmp[4,7]=weather_bmp[5,7]=weather_bmp[6,7]=weather_bmp[7,7]=weather_bmp[8,7]=weather_bmp[9,7]=weather_bmp[10,7]=2

        weather_bmp[1,9]=weather_bmp[4,9]=weather_bmp[7,9]=weather_bmp[10,9]=3
        weather_bmp[0,10]=weather_bmp[3,10]=weather_bmp[6,10]=weather_bmp[9,10]=3
        weather_bmp[2,11]=weather_bmp[5,11]=weather_bmp[8,11]=3

    elif "snow" in cond:
        weather_bmp[4,0]=weather_bmp[6,0]=weather_bmp[8,0]=4
        weather_bmp[2,1]=weather_bmp[5,1]=weather_bmp[6,1]=weather_bmp[7,1]=weather_bmp[10,1]=4
        weather_bmp[3,2]=weather_bmp[6,2]=weather_bmp[9,2]=4
        weather_bmp[1,3]=weather_bmp[4,3]=weather_bmp[6,3]=weather_bmp[8,3]=weather_bmp[11,3]=4
        weather_bmp[2,4]=weather_bmp[5,4]=weather_bmp[6,4]=weather_bmp[7,4]=weather_bmp[10,4]=4
        weather_bmp[1,5]=weather_bmp[2,5]=weather_bmp[3,5]=weather_bmp[4,5]=weather_bmp[5,5]=weather_bmp[6,5]=weather_bmp[7,5]=weather_bmp[8,5]=weather_bmp[9,5]=weather_bmp[10,5]=weather_bmp[11,5]=4
        weather_bmp[2,6]=weather_bmp[5,6]=weather_bmp[6,6]=weather_bmp[7,6]=weather_bmp[10,6]=4
        weather_bmp[1,7]=weather_bmp[4,7]=weather_bmp[6,7]=weather_bmp[8,7]=weather_bmp[11,7]=4
        weather_bmp[3,8]=weather_bmp[6,8]=weather_bmp[9,8]=4
        weather_bmp[2,9]=weather_bmp[5,9]=weather_bmp[6,9]=weather_bmp[7,9]=weather_bmp[10,9]=4
        weather_bmp[4,10]=weather_bmp[6,10]=weather_bmp[8,10]=4

    else: # Default Cloud
        for x in range(2, 10):
            for y in range(5, 9): weather_bmp[x, y] = 2



# WEATHER INFORMATION RETREIEVAL FUNCTIONS

def get_weather():
    gc.collect()
    try:
        print (f"  Attempting to retrieve local weather from Open Weather Map...")
        with matrixportal.network.requests.get(WEATHER_URL, timeout=10) as resp:
            data = resp.json()
            temp = int(data["main"]["temp"])
            feels_like = int(data["main"]["feels_like"])
            temp_min = int(data["main"]["temp_min"])
            temp_max = int(data["main"]["temp_max"])
            cond = data["weather"][0]["main"]
            icon = data["weather"][0]["icon"]
            loc = data["name"]

            unit_sym = "F" if UNITS == "imperial" else "C"

            if temp < 100 and feels_like >= 100:
                weather_current_label.x = 3
            elif temp >= 100 and feels_like < 100:
                weather_current_label.x = 3
            elif temp >= 100 and feels_like >= 100:
                weather_current_label.x = 0
            else:
                weather_current_label.x = 5

            weather_current_label.text = f"{temp}{unit_sym} ({feels_like}{unit_sym})"
            weather_temp_max_label.text = f"Hi: {temp_max}{unit_sym}"
            weather_temp_min_label.text = f"Lo: {temp_min}{unit_sym}"

            is_day = True

            if "n" in icon:
                is_day = False

            draw_weather_icon(cond, is_day)

            print(f"    Current local weather conditions for {loc}: \n      - Current: {temp}{unit_sym} ({feels_like}{unit_sym}), {cond}\n      - High: {temp_max}{unit_sym}\n      - Low: {temp_min}{unit_sym}")
            return True
    except Exception as e:
        print(f"! EXCEPTION - Error occurred while trying to retrieve weather data: get_weather(): {e}")
    return False


# FLIGHT INFORMATION RETRIEVAL FUNCTIONS

#
# Take the flight number we found with a search, and load details about it
#
def get_flight_details(flight_number):
    global json_bytes
    global json_size
    byte_counter = 0
    chunk_length = 512 

    gc.collect() # <--- FORCE CLEANUP BEFORE NETWORK START
    
    for i in range(0, json_size):
        json_bytes[i] = 0

    try:
        response = matrixportal.network.requests.get(
            url=FLIGHT_LONG_DETAILS_HEAD + flight_number, 
            headers=rheaders, 
            stream=True
        )
        
         # Use a try/finally to ensure the response is CLOSED even if code crashes
        try:
            for chunk in response.iter_content(chunk_size=chunk_length):
                chunk_len = len(chunk)
                if byte_counter + chunk_len > json_size:
                    print("    Exceeded max buffer size")
                    break

                json_bytes[byte_counter : byte_counter + chunk_len] = chunk
                byte_counter += chunk_len

                history_marker = b'"flightHistory":'
                marker_pos = json_bytes.find(history_marker)

                if marker_pos != -1:
                    last_brace = json_bytes.rfind(b"}", 0, marker_pos)
                    if last_brace != -1:
                        actual_end = last_brace + 1
                        json_bytes[actual_end] = ord('}') 
                        for i in range(actual_end + 1, json_size):
                            json_bytes[i] = 0
                        return True # Finally block will close response
        finally:
            response.close() # <--- ENSURE SOCKET IS CLOSED
            gc.collect()     # <--- CLEAN UP AFTER NETWORK FINISHED

    except (RuntimeError, OSError, HttpError) as e:
        print(f"! EXCEPTION - Error occurred while retrieving flight details for flight {flight_number}: get_flight_details(): {e}")
        return False

    return False

def parse_details_json():
    global json_bytes, flight_num_label, airline_name_label, airport_src_dest_iata_codes_label, airport_src_dest_name_label, airplane_code_label, aircraft_make_model_label, flight_status

    # Set some defaults
    flight_number            = 'Unknown'
    registration             = 'Unknown'
    aircraft_code            = 'Unknown'
    aircraft_model           = 'Unknown'
    airline_name             = 'Unknown'
    airport_origin_name      = 'Unknown'
    airport_origin_code      = 'ZZZ'
    airport_origin_gate      = 'Unknown'
    airport_destination_name = 'Unknown'
    airport_destination_code = 'ZZZ'
    airport_destination_gate = 'Unknown'
    flight_status            = 'Unknown' # The flight status: on-time (green), delayed (yellow), etc.

    try:
        long_json = json.loads(json_bytes)

        if long_json["identification"]["number"]["default"] is not None:
            flight_number = long_json["identification"]["number"]["default"]

        if long_json["status"]["icon"] is not None:
            flight_status = long_json["status"]["icon"]

        if long_json["airline"] is not None:
            if long_json["airline"]["name"] is not None:
                airline_name = long_json["airline"]["name"]

        if long_json["airport"]["origin"] is not None:
            if long_json["airport"]["origin"]["name"] is not None:
                airport_origin_name = long_json["airport"]["origin"]["name"].replace(" Airport", "")
                airport_origin_name = airport_origin_name.replace(" International", "")
                airport_origin_name = airport_origin_name.replace(" National", "")
            
            if long_json["airport"]["origin"]["code"]["iata"] is not None:
                airport_origin_code = long_json["airport"]["origin"]["code"]["iata"]
        
            if long_json["airport"]["origin"]["info"]["gate"] is not None:
                airport_origin_gate = long_json["airport"]["origin"]["info"]["gate"]

        if long_json["airport"]["destination"] is not None:
            if long_json["airport"]["destination"]["name"] is not None:
                airport_destination_name = long_json["airport"]["destination"]["name"].replace(" Airport", "")
                airport_destination_name = airport_destination_name.replace(" International", "")
                airport_destination_name = airport_destination_name.replace(" National", "")

            if long_json["airport"]["destination"]["code"]["iata"] is not None:
                airport_destination_code = long_json["airport"]["destination"]["code"]["iata"]

            if long_json["airport"]["destination"]["info"]["gate"] is not None:
                airport_destination_gate = long_json["airport"]["destination"]["info"]["gate"]

        if long_json["aircraft"]["model"]["code"] is not None:
            aircraft_code = long_json["aircraft"]["model"]["code"]
            
        if long_json["aircraft"]["model"]["text"] is not None:
            aircraft_model = long_json["aircraft"]["model"]["text"]

        if long_json["aircraft"]["registration"] is not None:
            registration = long_json["aircraft"]["registration"]

        # Logic to append gates to names if they are known
        origin_display = airport_origin_name
        if airport_origin_gate != "Unknown":
            origin_display += f" ({airport_origin_gate})"

        destination_display = airport_destination_name
        if airport_destination_gate != "Unknown":
            destination_display += f" ({airport_destination_gate})"

        registration_display = ""
        if registration != "Unknown":
            registration_display = f"({registration})"

        flight_num_label = f"{flight_number if flight_number else "Unknown"}"
        airline_name_label = airline_name if airline_name else "Unknown"
        airport_src_dest_iata_codes_label = f"{airport_origin_code} -> {airport_destination_code}"
        
        # Updated airport_src_dest_name_label with conditional gate info
        airport_src_dest_name_label = f"{origin_display} -> {destination_display}"
        
        airplane_code_label = f"{aircraft_code}"
        aircraft_make_model_label = f"{aircraft_model} {registration_display}"

        print(f"        - Airline: {airline_name_label} - Flight: {flight_num_label} - Status: {flight_status}")
        print(f"        - {airport_src_dest_name_label} ({airport_src_dest_iata_codes_label})")
        print(f"        - Aircraft details: {aircraft_make_model_label} ({airplane_code_label})")

    except (KeyError, ValueError, TypeError) as e:
        print(f"! EXCEPTION - Error occurred while processing flight details for flight {flight_number}: parse_details_json(): {e}")
        return False
        
    return True

def get_flights():
    try:
        print ("  Attempting to retrieve flight status from https://data-clound.flightradar24.com...")
        response = matrixportal.network.requests.get(url=FLIGHT_SEARCH_URL, headers=rheaders).json()
    except Exception as e:
        print(f"! EXCEPTION - Error occurred while occurred while attempting to retrieve flights: get_flights(): {e}")
        checkConnection()
        return False
    if len(response)==3:
        for flight_id, flight_info in response.items():
            if not (flight_id=="version" or flight_id=="full_count"):
                if len(flight_info)>13: return flight_id
    return False



# HELPER/UTILITY FUNCTIONS

def checkConnection():
    attempts=10
    attempt=1

    while (not matrixportal.network.is_connected) and attempt<attempts:
        w.feed()
        try:
            matrixportal.network.connect()
        except OSError as e:
            print(f"! EXCEPTION - Could not connect to Wifi network '{WIFI_SSID}' retrying {attempts-attempt} more times: ", e)
            continue
        attempt+=1

# Main Loop
checkConnection()
last_flight=''

# Cycle tracking
no_flight_cycles = 0
weather_request_delay = 0

print("\nStarting flight tracker.\n")

while True:
    w.feed()
    flight_id=get_flights()
    w.feed()

    if flight_id:
        no_flight_cycles = 0 # Reset counter
        if flight_id != last_flight:
            print(f"    New flight with flight ID {flight_id} was found! Getting additional flight details...")
            clear_display()
            if get_flight_details(flight_id):
                w.feed()
                gc.collect()
                if parse_details_json():
                    gc.collect()
                    plane_animation(airline_name_label)
                    display_flight()
            last_flight=flight_id
            gc.collect()
    else:
        clear_display()
        last_flight = ''
        no_flight_cycles += 1

        if no_flight_cycles < 2 :
            print(f"    No new flights found found within {SEARCH_DISTANCE_MILES} miles of {LOCATION}. Waiting {QUERY_DELAY} seconds before looking again (Attempt: {no_flight_cycles}/2).")
        elif no_flight_cycles >= 2 and weather_request_delay == 0:
            # Reset the weather request delay 
            weather_request_delay = 300/QUERY_DELAY # Get the weather every 5-minutes instead of every 15-secnds.

            print(f"    No new flights found found within {SEARCH_DISTANCE_MILES} miles of {LOCATION} for {no_flight_cycles} consecutive attempts. Retrieving weather local weather information.")

            get_weather()
            display_weather()
            # We don't reset the counter here so it stays on weather 
            # until a flight is found or the next cycle tries weather again
        else:
            print(f"    No new flights found found within {SEARCH_DISTANCE_MILES} miles of {LOCATION} for {no_flight_cycles} consecutive attempts. Displaying the current weather.")
            display_weather()

    
    for i in range(0, QUERY_DELAY, 5):
        time.sleep(5)
        w.feed()
    
    if weather_request_delay > 0:
        # If the weather request delay is greater and 0, decrement the counter after each cycle.
        weather_request_delay = weather_request_delay-1

    gc.collect()
