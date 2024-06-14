# Ulendo Calibration as a Service

Ulendo's Calibration as a Service

# Install Ulendo's Calibration as a Service plugin for OctoPrint

These instructions are intended to configure OctoPrint with Ulendo's Calibration as a Service plugin from a fresh Raspbian install.

The install script has been tested on Raspberry Pi 3 and 4, running Raspberry Pi OS Lite (compatible with Pi 3/4/400/5)

Follow the instructions below to download [UlendoCaaS-Install.sh](UlendoCaaS-Install.sh) 

## Setup (RPi)

	curl https://raw.githubusercontent.com/S2AUlendo/UlendoCaaS/main/UlendoCaas-Install.sh > UlendoCaaS-Install.sh
	sudo chmod +x UlendoCaaS-Install.sh
	. ./UlendoCaaS-Install.sh

## Usage:
	The setup script will start the server for you and create the OctoPrint service.
	The OctoPrint service will automatically start OctoPrint with the OS when it boots. 

	To run OctoPrint as usual:
		source ~/OctoPrint/venv/bin/activate
		~/OctoPrint/venv/bin/octoprint serve

