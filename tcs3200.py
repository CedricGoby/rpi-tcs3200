#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Description : Reads RGB values from a TCS3200 colour sensor and write the result into a CSV file.
# Usage : ./tcs3200.py
# Licence : Public Domain
# Versioning : https://github.com/CedricGoby/rpi-tcs3200
# Original script : http://abyz.co.uk/rpi/pigpio/index.html
#
# Before starting the script :
# sudo pgpiod
# export PIGPIO_ADDR=hostame
# export PIGPIO_PORT=port

import pigpio
import time
import threading
import csv
from blessings import Terminal
term = Terminal()

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
   VDD         |          1          |      3v3 Power
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

   # Calibration
   def _calibrate(self):
      print (term.bold('\n> BLACK calibration'))
      input('Place a black object in front of the sensor\nthen press ENTER to start.\n')
      # Black	
      for i in range(5):
         time.sleep(self._interval)
         hz = self.get_hertz()
         print(hz)
      self.set_black_level(hz)

      print (term.bold('\n> WHITE calibration'))
      input('Place a white object in front of the sensor\nthen press ENTER to start.\n')
      # White
      for i in range(5):
         time.sleep(self._interval)
         hz = self.get_hertz()
         print(hz)
      self.set_white_level(hz)

      print ('\n{t.bold}{t.green}OK...{t.normal} Calibration finished'.format(t=term))

   # Reading
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

   # Write the last reading into a CSV file, add a timestamp
   def _csv_output(self, _file_output):
      print (self.r)	   
      with open(_file_output, 'a', newline='') as csvfile:
         capturewriter = csv.writer(csvfile, delimiter='\t')
         capturewriter.writerow([time.time()] + [self.r] + [self.g] + [self.b] + [self.rhz] + [self.ghz] + [self.bhz] + [self.rcy] + [self.gcy] + [self.bcy])

   # LED On
   def _led_on(self):
      self._pi.set_mode(25, pigpio.OUTPUT)
      self._pi.write(25, 1)
      time.sleep(1)

   # LED Off
   def _led_off(self):
      self._pi.set_mode(25, pigpio.INPUT)

# Run following code when the program starts
if __name__ == "__main__":

   import sys
   import pigpio
   import tcs3200
   import os

   # Create one instance of the pigpio.pi class. This class gives access to a specified Pi's GPIO. 
   pi = pigpio.pi()

   capture = tcs3200.sensor(pi, 24, 22, 23, 4, 17, 18)

   capture.set_frequency(2) # 20%

   interval = 1 # Reading interval in second
   capture.set_update_interval(interval)

   _led_on = capture._led_on
   _led_off = capture._led_off
   
   _calibrate = capture._calibrate
   
   _reading = capture._reading
   
   _csv_output = capture._csv_output
   _file_output = "output.csv" # Name of the output csv file
   
   while True:
	   print ('\n')
	   print (term.bold('TCS3200 Color Sensor'), end='')
	   print (term.normal, end='')
	   print (term.red, end='')
	   print (' ║▌║█', end='')
	   print (term.green, end='')
	   print (' ║▌│║▌', end='')
	   print (term.blue, end='')
	   print (' ║▌█', end='')
	   print (term.normal)
	   print ('', end='')
	   for i in range(35):
	    print('-', end='')
	   print (term.bold('\nMAIN MENU\n'))
	   print ('{t.bold}1{t.normal}. Calibrate and measure'.format(t=term))
	   print ('{t.bold}2{t.normal}. Measure'.format(t=term))
	   print ('{t.bold}3{t.normal}. Quit'.format(t=term))
	
	   # Wait for valid input in while...not
	   is_valid=0
	   while not is_valid :
	           try :
	                   print (term.bold('\nEnter your choice [1-3] : '), end='')
	                   choice = int ( input() ) # Only accept integer
	                   is_valid = 1 # set it to 1 to validate input and to terminate the while..not loop
	           except ValueError as e:
	                    print ("'%s' is not a number :-/" % e.args[0].split(": ")[1])
	
	   if choice == 1:
            _led_on()
            _calibrate()
            _reading()
            _led_off()

	   elif choice == 2:
            _led_on()
            _reading()
            _csv_output(_file_output)
            _led_off()
	   
	   elif choice == 3:
            #_led_off()
            capture.cancel()
            pi.stop()
            print("Bye !")
            quit()
	   
	   else:
	        print("Invalid choice, please try again...")
	        os.execv(__file__, sys.argv)
  
   print (term.normal)

			
