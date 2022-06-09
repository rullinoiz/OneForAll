#!/usr/bin/env python
# sudo apt-get install python-serial
#
# This file originates from Vascofazza's Retropie open OSD project.
# Author: Federico Scozzafava
#
# THIS HEADER MUST REMAIN WITH THIS FILE AT ALL TIMES
#
# This firmware is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This firmware is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this repo. If not, see <http://www.gnu.org/licenses/>.
#
import Adafruit_ADS1x15
import RPi.GPIO as gpio
import configparser
import logging
import logging.handlers
import os
import re
import signal
import sys
import thread as thread
import time
import uinput
# from evdev import uinput, UInput, AbsInfo, categorize, ecodes as e
from subprocess import Popen, PIPE, check_output, check_call
from threading import Event
from threading import Timer

# Batt variables
voltscale = 118.0  # ADJUST THIS
currscale = 640.0
resdivmul = 4.0
resdivval = 1000.0
dacres = 20.47
dacmax = 4096.0

batt_threshold = 4

temperature_max = 70.0
temperature_threshold = 5.0

# BT Variables
bt_state = 'UNKNOWN'

# Wifi variables
wifi_state = 'UNKNOWN'
wif = 0
wifi_off = 0
wifi_warning = 1
wifi_error = 2
wifi_1bar = 3
wifi_2bar = 4
wifi_3bar = 5

bin_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
osd_path = bin_dir + '/osd/osd'
rfkill_path = 'rfkill'

# Configure buttons
config = configparser.ConfigParser()
config.read(bin_dir + '/keys.cfg')
keys = config['KEYS']
general = config['GENERAL']
LEFT = int(keys['LEFT'])
RIGHT = int(keys['RIGHT'])
DOWN = int(keys['DOWN'])
UP = int(keys['UP'])
BUTTON_A = int(keys['BUTTON_A'])
BUTTON_B = int(keys['BUTTON_B'])
BUTTON_X = int(keys['BUTTON_X'])
BUTTON_Y = int(keys['BUTTON_Y'])
BUTTON_L1 = int(keys['BUTTON_L1'])
BUTTON_R1 = int(keys['BUTTON_R1'])
SELECT = int(keys['SELECT'])
START = int(keys['START'])
HOTKEY = int(keys['HOTKEY'])
QUICKSAVE = int(keys['QUICKSAVE'])
QUICKLOAD = 99  # Probably not the cleanest way to do this, but we're pretending like quickload is GPIO pin 99

if config.has_option("GENERAL", "DEBUG"):
    logging.basicConfig(filename=bin_dir + '/osd.log', level=logging.DEBUG,
                        format='%(asctime)s %(levelname)s - %(message)s',
                        datefmt='%Y-%m-%d,%H:%M:%S:%f', )

SHUTDOWN = int(general['SHUTDOWN_DETECT'])
LID_SENSOR = int(general['LID_SENSOR'])

# Joystick Hardware settings
joystickConfig = config['JOYSTICK']
DZONE = int(joystickConfig['DEADZONE'])  # dead zone applied to joystick (mV)
VREF = int(joystickConfig['VCC'])  # joystick Vcc (mV)
JOYSTICK_DISABLED = joystickConfig['DISABLED']
ON_BY_DEFAULT = joystickConfig['ON_BY_DEFAULT']

# Battery config
battery = config['BATTERY']
monitoring_enabled = battery['ENABLED']
batt_full = int(battery['FULL_BATT_VOLTAGE'])
batt_low = int(battery['BATT_LOW_VOLTAGE'])
batt_shdn = int(battery['BATT_SHUTDOWN_VOLT'])

BUTTONS = [LEFT, RIGHT, DOWN, UP, BUTTON_A, BUTTON_B,
           BUTTON_X, BUTTON_Y, BUTTON_L1, BUTTON_R1, SELECT, START, QUICKSAVE]

HOTKEYS = [LEFT, RIGHT, DOWN, UP, BUTTON_A, START, QUICKSAVE]

BOUNCE_TIME = 0.03  # Debounce time in seconds

# GPIO Init
gpio.setwarnings(False)
gpio.setmode(gpio.BCM)
gpio.setup(BUTTONS, gpio.IN, pull_up_down=gpio.PUD_UP)

if not SHUTDOWN == -1:
    gpio.setup(SHUTDOWN, gpio.IN, pull_up_down=gpio.PUD_UP)

if not LID_SENSOR == -1:
    gpio.setup(LID_SENSOR, gpio.IN, pull_up_down=gpio.PUD_UP)

if not HOTKEY in BUTTONS:
    if HOTKEY != -1:
        gpio.setup(HOTKEY, gpio.IN, pull_up_down=gpio.PUD_UP)

if JOYSTICK_DISABLED == 'False':
    KEYS = {  # EDIT KEYCODES IN THIS TABLE TO YOUR PREFERENCES:
        # See /usr/include/linux/input.h for keycode names
        BUTTON_A: uinput.BTN_A,  # 'A' button
        BUTTON_B: uinput.BTN_B,  # 'B' button
        BUTTON_X: uinput.BTN_X,  # 'X' button
        BUTTON_Y: uinput.BTN_Y,  # 'Y' button
        BUTTON_L1: uinput.BTN_TL,  # 'L1' button
        BUTTON_R1: uinput.BTN_TR,  # 'R1' button
        SELECT: uinput.BTN_SELECT,  # 'Select' button
        START: uinput.BTN_START,  # 'Start' button
        UP: uinput.BTN_DPAD_UP,  # Analog up
        DOWN: uinput.BTN_DPAD_DOWN,  # Analog down
        LEFT: uinput.BTN_DPAD_LEFT,  # Analog left
        RIGHT: uinput.BTN_DPAD_RIGHT,  # Analog right
        10001: uinput.ABS_X + (0, VREF, 0, 0),
        10002: uinput.ABS_Y + (0, VREF, 0, 0),
    }
else:
    KEYS = {  # EDIT KEYCODES IN THIS TABLE TO YOUR PREFERENCES:
        # See /usr/include/linux/input.h for keycode names
        BUTTON_A: uinput.KEY_LEFTCTRL,  # 'A' button
        BUTTON_B: uinput.KEY_LEFTALT,  # 'B' button
        BUTTON_X: uinput.KEY_Z,  # 'X' button
        BUTTON_Y: uinput.KEY_X,  # 'Y' button
        BUTTON_L1: uinput.KEY_G,  # 'L1' button
        BUTTON_R1: uinput.KEY_H,  # 'R1' button
        SELECT: uinput.KEY_SPACE,  # 'Select' button
        START: uinput.KEY_ENTER,  # 'Start' button
        UP: uinput.KEY_UP,  # Analog up
        DOWN: uinput.KEY_DOWN,  # Analog down
        LEFT: uinput.KEY_LEFT,  # Analog left
        RIGHT: uinput.KEY_RIGHT,  # Analog right
        QUICKSAVE: uinput.KEY_F2,  # Quick save key
        QUICKLOAD: uinput.KEY_F4,  # Quick load key
        ESCAPE: uinput.KEY_ESC  # dang
    }

# Global Variables

global brightness
global volt
global info
global wifi
global volume
global charge
global bat
global joystick
global bluetooth
global lowbattery

brightness = -1
info = False
volt = 410
volume = 1
wifi = 2
charge = 0
bat = 0
last_bat_read = 450
joystick = False
showOverlay = False
lowbattery = 0
overrideCounter = Event()

if ON_BY_DEFAULT == 'True':
    joystick = True

# TO DO REPLACE A LOT OF OLD CALLS WITH THE CHECK_OUTPUT
if monitoring_enabled == 'True':
    adc = Adafruit_ADS1x15.ADS1015()
else:
    adc = False

# Create virtual HID for Joystick
if JOYSTICK_DISABLED == 'False':
    device = uinput.Device(KEYS.values(), name="OneForAll-GP", version=0x3)
else:
    device = uinput.Device(KEYS.values(), name="mintyPad", version=0x3)

time.sleep(1)


def hotkeyAction(key):
    if not gpio.input(HOTKEY):
        if key in HOTKEYS:
            return True

    return False


def handle_button(pin):
    global showOverlay
    time.sleep(BOUNCE_TIME)
    state = 0 if gpio.input(pin) else 1

    if pin == HOTKEY:
        print "hotkey pressed"
        if state == 1:
            showOverlay = True
        else:
            showOverlay = False
        try:
            checkKeyInputPowerSaving()
        except Exception:
            pass
        return
    elif pin == QUICKSAVE:
        print "quicksave pressed"
        device.emit(KEYS[SELECT], state)
        if not gpio.input(HOTKEY):
            device.emit(KEYS[QUICKLOAD], state)
        else:
            device.emit(KEYS[QUICKSAVE], state)
        time.sleep(BOUNCE_TIME)
        device.syn()
        return

    key = KEYS[pin]
    if not hotkeyAction(pin):
        device.emit(key, state)
        time.sleep(BOUNCE_TIME)
        device.syn()
    else:
        checkKeyInputPowerSaving()

    logging.debug("Pin: {}, KeyCode: {}, Event: {}".format(pin, key, 'press' if state else 'release'))


def handle_shutdown(pin):
    state = 0 if gpio.input(pin) else 1
    if (state):
        logging.info("SHUTDOWN")
        doShutdown()


def handle_lid_close(pin):
    state = gpio.input(pin)
    print 'Hall effect sensor tripped: ' + str(state)
    if state == 0:
        device.emit(KEYS[SELECT], 1)
        device.emit(KEYS[QUICKSAVE], 1)
        time.sleep(BOUNCE_TIME)
        device.syn()
        device.emit(KEYS[SELECT], 0)
        device.emit(KEYS[QUICKSAVE], 0)
        time.sleep(BOUNCE_TIME)
        device.syn()
        time.sleep(3)
        os.system("killall retroarch")
        time.sleep(2)
        os.system('aplay ' + bin_dir + '/resources/lid_beep.wav')
        doShutdown()


# Initialise Safe shutdown
if not SHUTDOWN == -1:
    gpio.add_event_detect(SHUTDOWN, gpio.BOTH, callback=handle_shutdown, bouncetime=1)

if not LID_SENSOR == -1:
    gpio.add_event_detect(LID_SENSOR, gpio.BOTH, callback=handle_lid_close, bouncetime=5)

# Initialise Buttons
for button in BUTTONS:
    gpio.add_event_detect(button, gpio.BOTH, callback=handle_button, bouncetime=1)
    logging.debug("Button: {}".format(button))

if not HOTKEY in BUTTONS:
    if HOTKEY != -1:
        gpio.add_event_detect(HOTKEY, gpio.BOTH, callback=handle_button, bouncetime=1)

# Send centering commands
device.emit(uinput.ABS_X, VREF / 2, syn=False)
device.emit(uinput.ABS_Y, VREF / 2)

# Set up OSD service
try:
    if JOYSTICK_DISABLED == 'True':
        osd_proc = Popen([osd_path, bin_dir, "nojoystick"], shell=False, stdin=PIPE, stdout=None, stderr=None)
    else:
        osd_proc = Popen([osd_path, bin_dir, "full"], shell=False, stdin=PIPE, stdout=None, stderr=None)
    osd_in = osd_proc.stdin
    time.sleep(1)
    osd_poll = osd_proc.poll()
    if (osd_poll):
        logging.error("ERROR: Failed to start OSD, got return code [" + str(osd_poll) + "]\n")
        sys.exit(1)
except Exception as e:
    logging.exception("ERROR: Failed start OSD binary")
    sys.exit(1)


def turnOffLowBatteryWarning():
    global lowbattery
    lowbattery = 2
    overrideCounter.set()
    print "Turning off low battery"


# Check for shutdown state
def checkShdn(volt):
    global lowbattery
    global info
    if volt < batt_low and lowbattery == 0:
        print "Triggering Low Batt warning"
        lowbattery = 1
        t = Timer(2.0, turnOffLowBatteryWarning)
        t.start()
    if volt < batt_shdn:
        logging.info("Low Voltage Shutdown Triggered")
        info = 1
        overrideCounter.set()
        doShutdown()


# Read voltage
def readVoltage():
    global last_bat_read
    voltVal = adc.read_adc(0, gain=1)
    volt = int((float(voltVal) * (4.09 / 2047.0)) * 100)
    # volt = int(((voltVal * voltscale * dacres + (dacmax * 5)) / ((dacres * resdivval) / resdivmul)))

    if volt < 300 or (last_bat_read > 300 and last_bat_read - volt > 6 and not last_bat_read == 450):
        volt = last_bat_read

    last_bat_read = volt

    return volt


# Get voltage percent
def getVoltagepercent(volt):
    return clamp(int(float(volt - batt_shdn) / float(batt_full - batt_shdn) * 100), 0, 100)


def readVolumeLevel():
    process = os.popen("amixer | grep 'Left:' | awk -F'[][]' '{ print $2 }'")
    res = process.readline()
    process.close()

    vol = 0
    try:
        vol = int(res.replace("%", "").replace("'C\n", ""))
    except Exception as e:
        logging.info("Audio Err    : " + str(e))

    return vol


# Read wifi (Credits: kite's SAIO project) Modified to only read, not set wifi.
def readModeWifi(toggle=False):
    ret = 0
    wifiVal = not os.path.exists(osd_path + 'wifi')  # int(ser.readline().rstrip('\r\n'))
    if toggle:
        wifiVal = not wifiVal
    global wifi_state
    if (wifiVal):
        if os.path.exists(osd_path + 'wifi'):
            os.remove(osd_path + 'wifi')
        if (wifi_state != 'ON'):
            wifi_state = 'ON'
            logging.info("Wifi    [ENABLING]")
            try:
                out = check_output(['sudo', rfkill_path, 'unblock', 'wifi'])
                logging.info("Wifi    [" + str(out) + "]")
            except Exception as e:
                logging.info("Wifi    : " + str(e))
                ret = wifi_warning  # Get signal strength

    else:
        with open(osd_path + 'wifi', 'a'):
            n = 1
        if (wifi_state != 'OFF'):
            wifi_state = 'OFF'
            logging.info("Wifi    [DISABLING]")
            try:
                out = check_output(['sudo', rfkill_path, 'block', 'wifi'])
                logging.info("Wifi    [" + str(out) + "]")
            except Exception as e:
                logging.info("Wifi    : " + str(e))
                ret = wifi_error
        return ret
    # check signal
    raw = check_output(['cat', '/proc/net/wireless'])
    strengthObj = re.search(r'.wlan0: \d*\s*(\d*)\.\s*[-]?(\d*)\.', raw, re.I)
    if strengthObj:
        strength = 0
        if (int(strengthObj.group(1)) > 0):
            strength = int(strengthObj.group(1))
        elif (int(strengthObj.group(2)) > 0):
            strength = int(strengthObj.group(2))
        logging.info("Wifi    [" + str(strength) + "]strength")
        if (strength > 55):
            ret = wifi_3bar
        elif (strength > 40):
            ret = wifi_2bar
        elif (strength > 5):
            ret = wifi_1bar
        else:
            ret = wifi_warning
    else:
        logging.info("Wifi    [---]strength")
        ret = wifi_error
    return ret


def readModeBluetooth(toggle=False):
    ret = 0
    BtVal = not os.path.exists(osd_path + 'bluetooth')  # int(ser.readline().rstrip('\r\n'))
    if toggle:
        BtVal = not BtVal
    global bt_state
    if (BtVal):
        if os.path.exists(osd_path + 'bluetooth'):
            os.remove(osd_path + 'bluetooth')
        if (bt_state != 'ON'):
            bt_state = 'ON'
            logging.info("BT    [ENABLING]")
            try:
                check_call("sudo systemctl enable hciuart.service && sudo systemctl start hciuart.service", shell=True)
                out = check_output(['sudo', rfkill_path, 'unblock', 'bluetooth'])
                logging.info("BT      [" + str(out) + "]")
            except Exception as e:
                logging.info("BT    : " + str(e))
                ret = wifi_warning  # Get signal strength

    else:
        with open(osd_path + 'bluetooth', 'a'):
            n = 1
        if (bt_state != 'OFF'):
            bt_state = 'OFF'
            logging.info("BT    [DISABLING]")
            try:
                check_call("sudo systemctl disable hciuart.service && sudo systemctl stop hciuart.service", shell=True)
                out = check_output(['sudo', rfkill_path, 'block', 'bluetooth'])
                logging.info("BT      [" + str(out) + "]")
            except Exception as e:
                logging.info("BT    : " + str(e))
                ret = wifi_error
        return ret
    # check if it's enabled
    raw = check_output(['hcitool', 'dev'])
    return True if raw.find("hci0") > -1 else False


# Do a shutdown
def doShutdown(channel=None):
    check_call("sudo killall emulationstation", shell=True)
    time.sleep(1)
    check_call("sudo shutdown -h now", shell=True)
    try:
        sys.stdout.close()
    except:
        pass
    try:
        sys.stderr.close()
    except:
        pass
    sys.exit(0)


# Signals the OSD binary
def updateOSD(volt=0, bat=0, temp=0, wifi=0, audio=0, lowbattery=0, info=False, charge=False, bluetooth=False):
    commands = "s" + str(int(showOverlay)) + " v" + str(volt) + " b" + str(bat) + " t" + str(temp) + " w" + str(
        wifi) + " a" + str(
        audio) + " j" + ("1 " if joystick else "0 ") + " u" + ("1 " if bluetooth else "0 ") + " l" + str(
        int(lowbattery)) + " " + ("on " if info else "off ") + (
                   "charge" if charge else "ncharge") + "\n"
    # print commands
    osd_proc.send_signal(signal.SIGUSR1)
    osd_in.write(commands)
    osd_in.flush()


# Misc functions
def clamp(n, minn, maxn):
    return max(min(maxn, n), minn)


def volumeUp():
    global volume
    volume = min(100, volume + 10)
    os.system("amixer sset -q 'PCM' " + str(volume) + "%")


def volumeDown():
    global volume
    volume = max(0, volume - 10)
    os.system("amixer sset -q 'PCM' " + str(volume) + "%")


def checkKeyInputPowerSaving():
    global info
    global wifi
    global joystick
    global bluetooth
    global bat
    global volume
    global volt
    global showOverlay

    info = showOverlay
    overrideCounter.set()

    # TODO Convert to state
    if not gpio.input(HOTKEY):
        if not gpio.input(UP):
            volumeUp()
            time.sleep(0.5)
        elif not gpio.input(DOWN):
            volumeDown()
            time.sleep(0.5)
        elif not gpio.input(LEFT):
            wifi = readModeWifi(True)
            time.sleep(0.5)
        elif not gpio.input(BUTTON_A):
            bluetooth = readModeBluetooth(True)
            time.sleep(0.5)
        elif not gpio.input(QUICKSAVE):
            device.emit(KEYS[QUICKLOAD], 1)
            time.sleep(2)
            device.syn()
        elif not gpio.input(START):  # for when Start+Select just doesn't cut it
            device.emit(uinput.KEY_ESC,1)
            time.sleep(0.5)
            device.emit(uinput.KEY_ESC,0)
            device.syn()


def exit_gracefully(signum=None, frame=None):
    gpio.cleanup
    osd_proc.terminate()
    sys.exit(0)


signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

# Read Initial States
volume = readVolumeLevel()

wifi = readModeWifi()
bluetooth = bluetooth = readModeBluetooth()

try:
    while 1:
        try:
            if not adc == False:
                volt = readVoltage()
                logging.info('Battery Voltage' + str(volt));
                bat = getVoltagepercent(volt)
                logging.info('Battery Percent' + str(bat));
            checkShdn(volt)
            updateOSD(volt, bat, 20, wifi, volume, lowbattery, info, charge, bluetooth)
            overrideCounter.wait(10)
            if overrideCounter.is_set():
                overrideCounter.clear()
            runCounter = 0

        except Exception:
            logging.info("EXCEPTION")
            pass

except KeyboardInterrupt:
    exit_gracefully()
