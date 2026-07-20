; daemon.g
; Self-restarting daemon (RRF 3.5+). config-sync hot-swaps this file by renaming the running
; copy to daemon.g.bak before uploading a new version. The loop below exits as soon as that
; .bak appears, letting RRF load the new daemon.g, which deletes the leftover .bak on startup.
; (First deploy of this version still needs one reboot; after that updates apply without reboot.)
;
; Signal lights (IEC 60073-style):
;   Solid green     = standby, ready to print
;   Green 1 Hz      = printing, all OK
;   Green 0.5 Hz    = print finished, remove product
;   Red flashing    = problem during a job (pause / attention)
;   Solid red       = fault, machine not available
; Flash timing uses state.upTime so rates stay accurate independent of loop delay.
if fileexists("/sys/daemon.g.bak")
    M472 P"/sys/daemon.g.bak"  ; remove leftover backup so this instance keeps running

while !fileexists("/sys/daemon.g.bak")

    ; --- Water temperature control ---
    if exists(sensors.analog[3])
        if sensors.analog[3].lastReading > global.waterTemp
            ; M118 P0 L2 S{"Water temp too high"}
            M42 P1 S1  ; Turn on pump
        elif sensors.analog[3].lastReading < global.waterTemp - 0.2
            ; M118 P0 L2 S{"Water temp ok"}
            M42 P1 S0  ; Turn off pump
    else
        ; M118 P0 L2 S{"Analog[3] not present - skipping pump control"}
        M42 P1 S0  ; Fail-safe: keep pump off (or on, if safer)

    ; --- Pellet feeder control ---
    if exists(sensors.analog[7])
        if sensors.analog[7].lastReading > 85 && global.pelletFeeding
            M42 P3 S1  ; Turn on feeder
        elif sensors.analog[7].lastReading < 85 || !global.pelletFeeding
            M42 P3 S0  ; Turn off feeder
    else
        ; M118 P0 L2 S{"Analog[7] not present - skipping feeder control"}
        M42 P3 S0  ; Fail-safe off

    ; --- Signal lights (P2/out8 = SL_G green, P4/out9 = SL_R red) ---
    if !exists(global.signalForceFault)
        global signalForceFault = false
    if !exists(global.printFinished)
        global printFinished = false
    if !exists(global.wasPrinting)
        global wasPrinting = false

    ; Track job lifecycle: processing -> idle means "print finished / remove product"
    if state.status == "processing" || state.status == "resuming"
        set global.wasPrinting = true
        set global.printFinished = false
    elif state.status == "idle" && global.wasPrinting
        set global.printFinished = true
        set global.wasPrinting = false

    ; 1 Hz = 0.5s on/off via upTime*2; 0.5 Hz = 1s on/off via upTime
    if global.signalForceFault && !(state.status == "processing" || state.status == "paused" || state.status == "pausing" || state.status == "resuming")
        ; Not printing + fault: solid red (machine unavailable)
        M42 P2 S0
        M42 P4 S1
    elif global.signalForceFault || state.status == "paused" || state.status == "pausing"
        ; Problem during a job: flash red @ 1 Hz
        M42 P2 S0
        if mod(floor(state.upTime * 2), 2) = 0
            M42 P4 S1
        else
            M42 P4 S0
    elif state.status == "processing" || state.status == "resuming" || state.status == "busy"
        ; Printing OK: flash green @ 1 Hz
        M42 P4 S0
        if mod(floor(state.upTime * 2), 2) = 0
            M42 P2 S1
        else
            M42 P2 S0
    elif state.status == "idle" && global.printFinished
        ; Print finished: slow flash green @ 0.5 Hz (remove product)
        M42 P4 S0
        if mod(floor(state.upTime), 2) = 0
            M42 P2 S1
        else
            M42 P2 S0
    elif state.status == "idle"
        ; Standby: solid green (ready to print)
        M42 P2 S1
        M42 P4 S0
    else
        M42 P2 S0
        M42 P4 S0

    G4 S0.2   ; Small delay to prevent overloading
