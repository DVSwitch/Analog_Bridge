#!/usr/bin/env bash
set -o errexit

# N4IRS 08/09/2019

#################################################
#                                               #
#                                               #
#                                               #
#################################################

function modeChange() {
    case $1 in
        dmr | DMR)
            /usr/local/sbin/dvs-remote.sh ambemode DMR
            /usr/local/sbin/dvs-remote.sh tlvtxport 31103
            /usr/local/sbin/dvs-remote.sh tlvrxport 31100
            # /usr/local/sbin/dvs-remote.sh tune 31123
            /usr/local/sbin/dvs-remote.sh info
        ;;
        dstar | DSTAR)
            /usr/local/sbin/dvs-remote.sh ambemode DSTAR
            /usr/local/sbin/dvs-remote.sh tlvtxport 32103
            /usr/local/sbin/dvs-remote.sh tlvrxport 32100
            # /usr/local/sbin/dvs-remote.sh tune 31123
            /usr/local/sbin/dvs-remote.sh info
        ;;
        nxdn | NXDN)
            /usr/local/sbin/dvs-remote.sh ambemode NXDN
            /usr/local/sbin/dvs-remote.sh tlvtxport 33103
            /usr/local/sbin/dvs-remote.sh tlvrxport 33100
            # /usr/local/sbin/dvs-remote.sh tune 31123
            /usr/local/sbin/dvs-remote.sh info
        ;;
        p25 | P25)
            /usr/local/sbin/dvs-remote.sh ambemode P25
            /usr/local/sbin/dvs-remote.sh tlvtxport 34103
            /usr/local/sbin/dvs-remote.sh tlvrxport 34100
            # /usr/local/sbin/dvs-remote.sh tune 31123
            /usr/local/sbin/dvs-remote.sh info
        ;;
        ysf | YSF | YSFN | YSFW)
            /usr/local/sbin/dvs-remote.sh ambemode YSFn
            /usr/local/sbin/dvs-remote.sh tlvtxport 35103
            /usr/local/sbin/dvs-remote.sh tlvrxport 35100
            # /usr/local/sbin/dvs-remote.sh tune 31123
            /usr/local/sbin/dvs-remote.sh info
        ;;
        *)
            echo "Unknown mode"
            exit 1
        ;;
    esac
}

modeChange $1
