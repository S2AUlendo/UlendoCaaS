# Calibration as a Service

Ulendo's Calibration as a Service

# Instructions to Autocalibrate in Octoprint

These instructions are intended to configure Octoprint with the Ulendo Autocalibration plugin from a fresh Raspbian install.

The install script has been tested on Raspberry Pi 3 and 4, running Raspberry Pi OS Lite (compatible with Pi 3/4/400/5)

Download [Autocal-Install.sh](Autocal-Install.sh) and follow the instructions below:

## Setup (RPi)

	curl https://raw.githubusercontent.com/S2AUlendo/UlendoCaaS/main/Autocal-Install.sh > Autocal-Install.sh
	sudo chmod +x Autocal-Install.sh
	. ./Autocal-Install.sh

## Usage:
	The setup script will start the server for you and create the octoprint service.
	The octoprint service will automatically start octoprint with the OS when it boots. 

	To run octoprint as usual:
		source ~/OctoPrint/venv/bin/activate
		~/OctoPrint/venv/bin/octoprint serve

