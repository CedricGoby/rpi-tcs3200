#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Description : Reads RGB values from a TCS3200 colour sensor and write the result into a CSV file.
# Usage : ./stdout.py
# Licence : Public Domain
# Versioning : https://github.com/CedricGoby/rpi-tcs3200
# Script that allows to run pigpiod as a Linux service with root privileges : https://github.com/joan2937/pigpio/tree/master/util
#
# Before starting the script pigpiod must be running and the Pi host/port must be specified.
#
# sudo pigpiod (or use a startup script)
# export PIGPIO_ADDR=hostame (or use the pigpio.pi() function)
# export PIGPIO_PORT=port (or use the pigpio.pi() function)

from __future__ import print_function

if __name__ == "__main__":

   import sys
   import pigpio
   import time
   import tcs3200
   import os
   from blessings import Terminal
   term = Terminal()

   # specify the Pi host/port.  For the remote host name, use '' if on local machine
   pi = pigpio.pi('', 8888)

   capture = tcs3200.sensor(pi, 24, 22, 23, 4, 17, 18)

   capture.set_frequency(2) # 20%

   interval = 1 # Reading interval in second
   capture.set_update_interval(interval)

   _led_on = capture._led_on
   _led_off = capture._led_off
   
   _calibrate = capture._calibrate
   
   _reading = capture._reading
   
   _csv_output = capture._csv_output
   _file_output = "readings.csv" # Name of the output csv file
   
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
	   print ('{t.bold}1{t.normal}. Calibrate'.format(t=term))
	   print ('{t.bold}2{t.normal}. Measure'.format(t=term))
	   print ('{t.bold}3{t.normal}. Quit'.format(t=term))
	
	   # Wait for valid input in while...not
	   is_valid=0
	   while not is_valid :
	           try :
	                   print (term.bold('\nEnter your choice [1-3] : '), end='')
	                   choice = int ( raw_input() ) # Only accept integer
	                   is_valid = 1 # set it to 1 to validate input and to terminate the while..not loop
	           except ValueError as e:
	                    print ("'%s' is not a number :-/" % e.args[0].split(": ")[1])
	
	   if choice == 1:
            _led_on()
            _calibrate()
            _led_off()

	   elif choice == 2:		   
            _led_on()
            _reading()
            _csv_output(_file_output)
            _led_off()
	   
	   elif choice == 3:
            _led_off()
            capture.cancel()
            print("Bye !")
            time.sleep(1.5)
            pi.stop()            
            quit()
	   
	   else:
	        print("Invalid choice, please try again...")
	        os.execv(__file__, sys.argv)
  
   print (term.normal)
