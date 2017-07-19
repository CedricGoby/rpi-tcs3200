#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Description : Reads RGB values from a TCS3200 colour sensor and write the result into a CSV file.
# Use with switch buttons and LCD display.
# Usage : ./button_lcd.py
# Licence : Public Domain
# Versioning : https://github.com/CedricGoby/rpi-tcs3200
# Original script : http://abyz.co.uk/rpi/pigpio/index.html
# Script that allows to run pigpiod as a Linux service with root privileges : https://github.com/joan2937/pigpio/tree/master/util
# Python Library for LCD : https://github.com/adafruit/Adafruit_Python_CharLCD
#
# Before starting the script pigpiod must be running and the Pi host/port must be specified.
#
# sudo pigpiod (or use a startup script)
# export PIGPIO_ADDR=hostame (or use the pigpio.pi() function)
# export PIGPIO_PORT=port (or use the pigpio.pi() function)
# Import LCD module

if __name__ == "__main__":

   import sys
   import pigpio
   import tcs3200
   import os
   import time
   
   # specify the Pi host/port.  For the remote host name, use '' if on local machine
   pi = pigpio.pi('', 8888)

   capture = tcs3200.sensor(pi, 24, 22, 23, 4, 17, 18)

   capture.set_frequency(2) # 20%
   interval = 1 # Reading interval in second
   capture.set_update_interval(interval)

   _led_on = capture._led_on
   _led_off = capture._led_off
   
   _calibrate_lcd = capture._calibrate_lcd  
   _reading_lcd = capture._reading_lcd
   
   _csv_output_lcd = capture._csv_output_lcd
   _file_output = "readings.csv" # Name of the output csv file
   
   GPIO = tcs3200.GPIO
   _setup_buttons = tcs3200._setup_buttons()
   
   lcd = tcs3200.lcd
   
   _display_menu = True # State of the menu
   while True:
      if _display_menu:
	     lcd.clear()
	     lcd.message("TCS3200 ready...\nPress to start")
	     _display_menu = False # Display menu only once in the loop
      
      if(GPIO.input(1) == GPIO.LOW):
	     _led_on()
	     _calibrate_lcd()
	     _led_off()
	     _display_menu = True
      elif(GPIO.input(7) == GPIO.LOW):
	     _led_on()
	     _reading_lcd()
	     _csv_output_lcd(_file_output)
	     _led_off()
	     _display_menu = True
      elif(GPIO.input(8) == GPIO.LOW):
	     _led_off()
	     capture.cancel()
	     lcd.clear()
	     lcd.message("Bye !")
	     time.sleep(1.5)
	     lcd.set_backlight(0)
	     pi.stop()
	     GPIO.cleanup()            
	     quit()
