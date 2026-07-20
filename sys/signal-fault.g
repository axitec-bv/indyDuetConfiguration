; Force fault indication on the tower light (machine not available).
; Sets signalForceFault so daemon keeps solid red while idle; GPIO is set
; immediately so red stays latched if M112 follows and the daemon stops.
if !exists(global.signalForceFault)
    global signalForceFault = false

set global.signalForceFault = true
M42 P2 S0  ; SL_G green off
M42 P4 S1  ; SL_R red on (solid)
