; Force fault indication on the tower light.
; Sets signalForceFault so daemon.g keeps flashing red (otherwise idle logic
; would restore green within ~0.2s). Also sets GPIO immediately.
; Call this before M112 in event handlers; after halt the last GPIO state sticks.
if !exists(global.signalForceFault)
    global signalForceFault = false
if !exists(global.signalFlashOn)
    global signalFlashOn = false

set global.signalForceFault = true
set global.signalFlashOn = true
M42 P2 S0  ; SL_G green off
M42 P4 S1  ; SL_R red on (daemon will flash while still running)
