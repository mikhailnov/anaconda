# Note, this script log will not be copied to the installed system.
%post --nochroot

NOSAVE_INPUT_KS_FILE=/tmp/NOSAVE_INPUT_KS
NOSAVE_LOGS_FILE=/tmp/NOSAVE_LOGS
PRE_ANA_LOGS=/tmp/pre-anaconda-logs
DNF_DEBUG_LOGS=/root/debugdata

if [ -e ${NOSAVE_INPUT_KS_FILE} ]; then
    rm -f ${NOSAVE_INPUT_KS_FILE}
elif [ -e /run/install/ks.cfg ]; then
    cp /run/install/ks.cfg $ANA_INSTALL_PATH/root/original-ks.cfg
fi

%end
