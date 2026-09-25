#!/bin/bash
sleep 5
chromium --password-store=basic --kiosk --noerrdialogs --disable-infobars http://localhost:5000
