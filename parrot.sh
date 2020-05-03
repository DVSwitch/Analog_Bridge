#!/usr/bin/env bash
set -o errexit

# N4IRS 11/03/2019

####################################################
#                                                  #
# This simple script is an example of how to use   #
# dvswitch.sh to send commands to Analog_Bridge    #
# This script asks dvswitch.sh what is the current #
# mode of Analog_Bridge and tunes Analog_bridge to #
# the parrot for that mode. As a added extra,      #
# this script sends a message to be displayed on   #
# the screen.                                      #
# This script can be run from the command line or  #
# as a macro from DVSM/UC                          #
# This script is very "brute force" on purpose.    #
# There are much more elegant ways to do some of   #
# the opperations below. This is done as a example #
#                                                  #
####################################################

dvsw="/opt/MMDVM_Bridge/dvswitch.sh"

function tgChange() {
    case $1 in
        dmr | DMR)
            $dvsw tune 4000
            $dvsw tune 31000
        ;;
        ysf | YSF | YSFN | YSFW)
            $dvsw tune disconnect
            $dvsw tune register.ysfreflector.de:42020
        ;;
        nxdn | NXDN)
            $dvsw tune 9999
            $dvsw tune 10
        ;;
        p25 | P25)
            $dvsw tune 9999
            $dvsw tune 10
        ;;
        dstar | DSTAR)
            $dvsw tune "       U"
            $dvsw tune REF030EL
        ;;
        *)
            echo "Unknown mode"
            exit 1
        ;;
    esac
}
		# This is where the script executes from
		# Ask dvswitch.sh what is the current mode
		# and put the reply into $mode variable
                mode=`$dvsw mode`
		# Send a message (toast) to DVSM
		# use the mode variable
		$dvsw message "Changing to parrot $mode"
		# Tune to the proper parrot for the current mode
                tgChange $mode
		exit 0
