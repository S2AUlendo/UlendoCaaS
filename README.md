# Calibration as a Service

Ulendo's Calibration as a Service

# Instructions to Autocalibrate in Octoprint
	These instructions are intended to configure Octoprint with the Ulendo Autocalibration plugin from a fresh Raspbian install. 
	The install script has been tested on Raspberry Pi 3 and 4, running Raspberry Pi OS Lite (compatible with Pi 3/4/400/5)
	Save [Autocal-Install.sh](https://raw.githubusercontent.com/S2AUlendo/UlendoCaaS/main/Autocal-Install.sh) to your home folder.

## Setup (RPi)

	cd ~
	sudo chmod +x Autocal-Install.sh
	sudo . ./Autocal-Install.sh

## Usage:
	The setup script will start the server for you the first time you run it. 

	To run octoprint as usual:
		source venv/bin/activate
		venv/bin/octoprint serve
		
	Note: You may use PuTTY Secure Copy (pscp) to transfer data between machines, e.g.:
		pscp pi@octopi.local:/home/pi/a_folder/a_file.csv c:\Users\user001\Documents
