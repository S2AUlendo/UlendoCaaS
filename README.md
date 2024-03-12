# Calibration as a Service

Ulendo's Calibration as a Service

# Instructions to Autocalibrate in Octoprint

## Setup

	Save Autocal-Install.sh to your home folder.

	sudo chmod +x Autocal-Install.sh
	sudo . ./Autocal-Install.sh

## Usage:
	The setup script will start the server for you the first time you run it. 

	To run octoprint as usual:
		source venv/bin/activate
		venv/bin/octoprint serve
		
	Note: You may use PuTTY Secury Copy (pscp) to transfer data between machines, e.g.:
		pscp pi@octopi.local:/home/pi/a_folder/a_file.csv c:\Users\user001\Documents
