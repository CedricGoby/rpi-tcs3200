#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Description : Reads RGB values from a TCS3200 colour sensor and write the result into a CSV file.
# Usage : ./tcs3200.py
# Licence : Public Domain
# Versioning : https://gitlab.com/CedricGoby/rpi-tcs3200
# Original script : http://abyz.co.uk/rpi/pigpio/index.html
# Script that allows to run pigpiod as a Linux service with root privileges : https://github.com/joan2937/pigpio/tree/master/util
#
# Before starting the script pigpiod must be running and the Pi host/port must be specified.
#
# sudo pigpiod (or use a startup script)
# export PIGPIO_ADDR=hostame (or use the pigpio.pi() function)
# export PIGPIO_PORT=port (or use the pigpio.pi() function)

from __future__ import print_function

from blessings import Terminal
term = Terminal()

import pigpio
import time
import threading
import csv

# Buttons
import RPi.GPIO as GPIO

# Setup GPIO for buttons
def _setup_buttons():
  GPIO.setmode(GPIO.BCM)
  GPIO.setup(1, GPIO.IN, pull_up_down=GPIO.PUD_UP) # If using the pull-up resistor, no external resistor is needed and the switch should be connected between GPIO pin and ground
  GPIO.setup(7, GPIO.IN, pull_up_down=GPIO.PUD_UP)
  GPIO.setup(8, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Import LCD module
import Adafruit_CharLCD as LCD

# LCD PIN = PI PIN (BCM)
lcd_rs        = 5
lcd_en        = 6
lcd_d4        = 26
lcd_d5        = 16
lcd_d6        = 12
lcd_d7        = 13
lcd_backlight = 19

# Define LCD column and row size for 16x2 LCD.
lcd_columns = 16
lcd_rows    = 2

# Initialize the LCD using the pins above.
lcd = LCD.Adafruit_CharLCD(lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7,
                        lcd_columns, lcd_rows, lcd_backlight)

"""
This class reads RGB values from a TCS3200 colour sensor.

VDD   Supply Voltage (2.7-5.5V).
GND   Ground.
OE    Output enable.
LED   LED control.
GND   Ground (LED).
S0/S1 Output frequency scale selection.
S2/S3 Colour filter selection.
OUT   Output frequency square wave.
OE    Output enable, active low. When OE is high OUT is disabled allowing multiple sensors to share the same OUT line.
LED   If you want to turn on the LEDs on the board, you could connect the led pin to 5v or a digital pin to drive them. 
OUT   is a square wave whose frequency is proportional to the intensity of the selected filter colour.
S0/S1 scales the frequency at 100%, 20%, 2% or off.
S2/S3 selects between red, green, blue, and no filter. To take a reading the colour filters are selected in turn for a fraction of a second and the frequency is read and converted to Hz.
"""
class sensor(threading.Thread):
   """
   The gpios connected to the sensor OUT, S2, and S3 pins must be specified.
   The S0, S1 (frequency) and OE (output enable) gpios are optional.
   
   This script uses BCM numbers.
   
   TCS3200     |   GPIO (physical)   |   GPIO (BCM)   
   S0          |          7          |      BCM 4
   S1          |         11          |      BCM 17
   S2          |         15          |      BCM 22
   S3          |         16          |      BCM 23
   OUT         |         18          |      BCM 24
   VDD         |          1          |      5V Power
   GND         |         20          |      Ground
   OE          |         12          |      BCM 18
   LED         |         22          |      BCM 25
   GND         |          6          |      Ground
   """
   
   def __init__(self, pi, OUT, S2, S3, S0=None, S1=None, OE=None):
   
      threading.Thread.__init__(self)
      
      self._pi = pi
      self._OUT = OUT
      self._S2 = S2
      self._S3 = S3

      self._mode_OUT = pi.get_mode(OUT)
      self._mode_S2 = pi.get_mode(S2)
      self._mode_S3 = pi.get_mode(S3)

      """
      Disable frequency output (OUT).
      """
      pi.write(OUT, 0)
      
      """
      Disable colour filter selection (S2 S3).
      """     
      pi.set_mode(S2, pigpio.OUTPUT)
      pi.set_mode(S3, pigpio.OUTPUT)

      self._S0 = S0
      self._S1 = S1
      self._OE = OE

      if (S0 is not None) and (S1 is not None):
         self._mode_S0 = pi.get_mode(S0)
         self._mode_S1 = pi.get_mode(S1)
         """
         Enable S0/S1 Output frequency scale selection
         """        
         pi.set_mode(S0, pigpio.OUTPUT)
         pi.set_mode(S1, pigpio.OUTPUT)

      if OE is not None:
         self._mode_OE = pi.get_mode(OE)
         pi.set_mode(OE, pigpio.OUTPUT)
         """
         Enable device (active low).
         """
         pi.write(OE, 0)

      self.set_sample_size(20)

      """
      One reading per second.
      """
      self.set_update_interval(1.0)

      """
      S0/S1 2% Frequency scale selection.
            The higher the frequency the faster the response. If you go from setting 1 (2%) to setting 2 (20%) the readings may be faster.
            if (self._S0 is not None) and (self._S1 is not None)
      """
      self.set_frequency(3)

      """
      S2/S3 Clear (no colour filter).
      """
      self._set_filter(3) # Clear.

      self._rgb_black = [0]*3
      self._rgb_white = [10000]*3

      self.hertz=[0]*3 # Latest triplet.
      self._hertz=[0]*3 # Current values.

      self.tally=[1]*3 # Latest triplet.
      self._tally=[1]*3 # Current values.

      self._delay=[0.1]*3 # Tune delay to get _samples pulses.

      self._cycle = 0

      self._cb_OUT = pi.callback(OUT, pigpio.RISING_EDGE, self._cbf)
      self._cb_S2 = pi.callback(S2, pigpio.EITHER_EDGE, self._cbf)
      self._cb_S3 = pi.callback(S3, pigpio.EITHER_EDGE, self._cbf)

      self.daemon = True

      self.start()

   def cancel(self):
      """
      Cancel the sensor and release resources.
      """
      self._cb_S3.cancel()
      self._cb_S2.cancel()
      self._cb_OUT.cancel()

      self.set_frequency(0) # off

      self._set_filter(3) # Clear

      self._pi.set_mode(self._OUT, self._mode_OUT)
      self._pi.set_mode(self._S2, self._mode_S2)
      self._pi.set_mode(self._S3, self._mode_S3)

      if (self._S0 is not None) and (self._S1 is not None):
         self._pi.set_mode(self._S0, self._mode_S0)
         self._pi.set_mode(self._S1, self._mode_S1)

      if self._OE is not None:
         self._pi.write(self._OE, 1) # disable device
         self._pi.set_mode(self._OE, self._mode_OE)

   def get_rgb(self, top=255):
      """
      Get the latest RGB reading.

      The raw colour hertz readings are converted to RGB values as follows.
      RGB = 255 * (Sample Hz - calibrated black Hz) / (calibrated white Hz - calibrated black Hz)

      By default the RGB values are constrained to be between 0 and 255. A different upper limit can be set by using the top parameter.
      """
      rgb = [0]*3
      for c in range(3):
         v = self.hertz[c] - self._rgb_black[c]
         s = self._rgb_white[c] - self._rgb_black[c]
         p = top * v / s
         if p < 0:
            p = 0
         elif p > top:
            p = top
         rgb[c] = p
      return rgb[:]

   """
   Get the latest hertz reading.
   """
   def get_hertz(self):
      return self.hertz[:]
 
   """
   Set the black level calibration.
   """
   def set_black_level(self, rgb):
      for i in range(3):
         self._rgb_black[i] = rgb[i]

   """
   Get the black level calibration.
   """
   def get_black_level(self):
      return self._rgb_black[:]

   """
   Set the white level calibration.  
   """
   def set_white_level(self, rgb):
      for i in range(3):
         self._rgb_white[i] = rgb[i]

   """
   Get the white level calibration.
   """
   def get_white_level(self):
      return self._rgb_white[:]
 
   """
   Set the frequency scaling.
   
   f  S0  S1  Frequency scaling
   0  L   L   Off
   1  L   H   2%
   2  H   L   20%
   3  H   H   100%
   """
   def set_frequency(self, f):

      if f == 0: # off
         S0 = 0; S1 = 0
      elif f == 1: # 2%
         S0 = 0; S1 = 1
      elif f == 2: # 20%
         S0 = 1; S1 = 0
      else: # 100%
         S0 = 1; S1 = 1

      if (self._S0 is not None) and (self._S1 is not None):
         self._frequency = f
         self._pi.write(self._S0, S0) # BCM 4, valeur de S0 en fonction de f
         self._pi.write(self._S1, S1) # BCM 17, valeur de S1 en fonction de f
      else:
         self._frequency = None

   """
   Get the current frequency scaling.
   """
   def get_frequency(self):
      return self._frequency

   """
   Set the interval between RGB updates.
   """
   def set_update_interval(self, t):
      if (t >= 0.1) and (t < 2.0):
         self._interval = t

   """
   Get the interval between RGB updates.
   """
   def get_update_interval(self):
      return self._interval

   """
   Set the sample size (number of frequency cycles to accumulate).
   """
   def set_sample_size(self, samples):
      if samples < 10:
         samples = 10
      elif samples > 100:
         samples = 100

      self._samples = samples

   """
   Set the sample size (number of frequency cycles to accumulate).
   """
   def get_sample_size(self):
      return self._samples

   """
   Pause reading (until a call to resume).
   """
   def pause(self):
      self._read = False

   """
   Resume reading (after a call to pause).
   """
   def resume(self):
      self._read = True

   """
   Set the colour to be sampled.
   
   f  S2  S3  Photodiode
   0  L   L   Red
   1  H   H   Green
   2  L   H   Blue
   3  H   L   Clear (no filter)
   """
   def _set_filter(self, f):

      if f == 0: # Red
         S2 = 0; S3 = 0
      elif f == 1: # Green
         S2 = 1; S3 = 1
      elif f == 2: # Blue
         S2 = 0; S3 = 1
      else: # Clear
         S2 = 1; S3 = 0
				
      self._pi.write(self._S2, S2); self._pi.write(self._S3, S3)

   def _cbf(self, g, l, t):

      if g == self._OUT: # Frequency counter.
         if self._cycle == 0:
            self._start_tick = t
         else:
            self._last_tick = t
         self._cycle += 1

      else: # Must be transition between colour samples.
         if g == self._S2:
            if l == 0: # Clear -> Red.
               self._cycle = 0
               return
            else:      # Blue -> Green.
               colour = 2
         else:
            if l == 0: # Green -> Clear.
               colour = 1
            else:      # Red -> Blue.
               colour = 0

         if self._cycle > 1:
            self._cycle -= 1
            td = pigpio.tickDiff(self._start_tick, self._last_tick)
            self._hertz[colour] = (1000000 * self._cycle) / td
            self._tally[colour] = self._cycle
         else:
            self._hertz[colour] = 0
            self._tally[colour] = 0

         self._cycle = 0

         # Have we a new set of RGB?
         if colour == 1:
            for i in range(3):
               self.hertz[i] = self._hertz[i]
               self.tally[i] = self._tally[i]

   def run(self):

      self._read = True
      while True:
         if self._read:

            next_time = time.time() + self._interval

            self._pi.set_mode(self._OUT, pigpio.INPUT) # Enable output gpio.

            """
            The order Red -> Blue -> Green -> Clear is needed by the callback function so that each S2/S3 transition triggers state change.
            The order was chosen so that a single gpio changes state between each colour to be sampled.
            """
            self._set_filter(0) # Red
            time.sleep(self._delay[0])

            self._set_filter(2) # Blue
            time.sleep(self._delay[2])

            self._set_filter(1) # Green
            time.sleep(self._delay[1])

            self._pi.write(self._OUT, 0) # Disable output gpio.

            self._set_filter(3) # Clear

            delay = next_time - time.time()

            if delay > 0.0:
               time.sleep(delay)

            # Tune the next set of delays to get reasonable results as quickly as possible.

            for c in range(3):

               # Calculate dly needed to get _samples pulses.

               if self.hertz[c]:
                  dly = self._samples / float(self.hertz[c])
               else: # Didn't find any edges, increase sample time.
                  dly = self._delay[c] + 0.1

               # Constrain dly to reasonable values.

               if dly < 0.001:
                  dly = 0.001
               elif dly > 0.5:
                  dly = 0.5

               self._delay[c] = dly

         else:
            time.sleep(0.1)

   # Calibration get black and white level (hz) (stdout)
   def _calibrate(self):
      
      # stdout
      print (term.bold('\n> BLACK calibration'))    
      
      raw_input('Place a black object in front of the sensor\nthen press ENTER to start.\n')
                
      for i in range(5):
         time.sleep(self._interval)
         hz = self.get_hertz()
         print (hz)
      self.set_black_level(hz)

      # Get three separate values
      self.rhz, self.ghz, self.bhz = self.get_hertz()
      print("BLACK RGB (Hz) " + str(self.rhz) + " " + str(self.ghz) + " " + str(self.bhz))
      time.sleep(5)

      print (term.bold('\n> WHITE calibration'))    
      raw_input('Place a white object in front of the sensor\nthen press ENTER to start.\n')    

      for i in range(5):
         time.sleep(self._interval)
         hz = self.get_hertz()
         print(hz)
      self.set_white_level(hz)

      self.rhz, self.ghz, self.bhz = self.get_hertz()     
      print("WHITE RGB (Hz) " + str(self.rhz) + " " + str(self.ghz) + " " + str(self.bhz))
      time.sleep(3)

      print ('\n{t.bold}{t.green}OK...{t.normal} Calibration OK\n'.format(t=term))    
      time.sleep(3)

   # Calibration get black and white level (hz) (LCD display)
   def _calibrate_lcd(self):

      # LCD display for black     
      lcd.clear()
      lcd.message("BLACK calibration\nPlace black object")     
      time.sleep(5)     
      lcd.clear()
      lcd.blink(True)
      lcd.message('BLACK:Progress ')

      # Get black level           
      for i in range(5):
         time.sleep(self._interval)
         hz = self.get_hertz()
         print (hz)
      self.set_black_level(hz)

      # Get three separate values for black and display
      self.rhz, self.ghz, self.bhz = self.get_hertz()
      lcd.clear()
      lcd.blink(False)
      lcd.message("BLACK RGB (Hz)\n" + str(self.rhz) + " " + str(self.ghz) + " " + str(self.bhz))
      time.sleep(5)

      # LCD display for white
      lcd.clear()
      lcd.message("WHITE calibration\nPlace white object")
      time.sleep(5)
      lcd.clear()
      lcd.blink(True)
      lcd.message('WHITE:Progress ')      

      # Get white level
      for i in range(5):
         time.sleep(self._interval)
         hz = self.get_hertz()
         print(hz)
      self.set_white_level(hz)

      # Get three separate values for white and display
      self.rhz, self.ghz, self.bhz = self.get_hertz()     
      lcd.clear()
      lcd.blink(False)
      lcd.message("WHITE RGB (Hz)\n" + str(self.rhz) + " " + str(self.ghz) + " " + str(self.bhz))
      time.sleep(3)
      
      # Display end of calibration message
      lcd.clear()
      lcd.message("Calibration OK")
      time.sleep(3)

   # Reading (stdout)
   def _reading(self):
            
      for i in range(5): # 5 readings
	        """
	        The first triplet is the RGB values.
	        The second triplet is the PWM frequency in hertz generated for the R, G, and B filters. The PWM frequency is proportional to the amount of each colour.
	        The third triplet is the number of cycles of PWM the software needed to calculate the PWM frequency for R, G, and B.
	        The second and third triplets are only useful during debugging so you needn't worry about them.
	        """
	        self.r, self.g, self.b = self.get_rgb()
	        self.rhz, self.ghz, self.bhz = self.get_hertz()
	        self.rcy, self.gcy, self.bcy = self.tally

	        print(self.r, self.g, self.b, self.rhz, self.ghz, self.bhz, self.rcy, self.gcy, self.bcy)
	        time.sleep(self._interval)

   # Reading (LCD)
   def _reading_lcd(self):
 
      lcd.clear()
      lcd.blink(True)
      lcd.message('READING... ')
            
      for i in range(5): # 5 readings
	        """
	        The first triplet is the RGB values.
	        The second triplet is the PWM frequency in hertz generated for the R, G, and B filters. The PWM frequency is proportional to the amount of each colour.
	        The third triplet is the number of cycles of PWM the software needed to calculate the PWM frequency for R, G, and B.
	        The second and third triplets are only useful during debugging so you needn't worry about them.
	        """
	        self.r, self.g, self.b = self.get_rgb()
	        self.rhz, self.ghz, self.bhz = self.get_hertz()
	        self.rcy, self.gcy, self.bcy = self.tally
	        time.sleep(self._interval)	        

   # Write the last reading into a CSV file, add a timestamp (stdout)
   def _csv_output(self, _file_output):

      try:	   
          with open(_file_output, 'a') as csvfile:
             capturewriter = csv.writer(csvfile, delimiter='\t')
             capturewriter.writerow([time.time()] + [self.r] + [self.g] + [self.b] + [self.rhz] + [self.ghz] + [self.bhz] + [self.rcy] + [self.gcy] + [self.bcy])
      except:
		  print ("File error !")
      else:
		  print("Datas stored\n" + str(self.r) + " " + str(self.g) + " " + str(self.b))
		  time.sleep(5)

   # Write the last reading into a CSV file, add a timestamp (LCD)
   def _csv_output_lcd(self, _file_output):
      
      try:	   
          with open(_file_output, 'a') as csvfile:
             capturewriter = csv.writer(csvfile, delimiter='\t')
             capturewriter.writerow([time.time()] + [self.r] + [self.g] + [self.b] + [self.rhz] + [self.ghz] + [self.bhz] + [self.rcy] + [self.gcy] + [self.bcy])
      except:
		  lcd.clear()
		  lcd.message("File error !")
		  time.sleep(5)
      else:
		  lcd.clear()
		  lcd.blink(False)
		  lcd.message("Datas stored\n" + str(self.r) + " " + str(self.g) + " " + str(self.b))
		  time.sleep(5)

   # LED On
   def _led_on(self):
      
      self._pi.set_mode(25, pigpio.OUTPUT)
      self._pi.write(25, 1)
      time.sleep(1)

   # LED Off
   def _led_off(self):
      
      self._pi.set_mode(25, pigpio.INPUT)
