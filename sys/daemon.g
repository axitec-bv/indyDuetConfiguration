; daemon.g
; Self-restarting daemon (RRF 3.5+). config-sync hot-swaps this file by renaming the running
; copy to daemon.g.bak before uploading a new version. The loop below exits as soon as that
; .bak appears, letting RRF load the new daemon.g, which deletes the leftover .bak on startup.
; (First deploy of this version still needs one reboot; after that updates apply without reboot.)
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
    ; Flash red:  fault (signalForceFault) or paused
    ; Solid green: printing / running and OK
    ; Flash green: idle / standby (ready for a job)
    if !exists(global.signalForceFault)
        global signalForceFault = false
    if !exists(global.signalFlashOn)
        global signalFlashOn = false

    if global.signalForceFault || state.status == "paused" || state.status == "pausing"
        ; Flash red (~2.5 Hz with G4 S0.2)
        set global.signalFlashOn = !global.signalFlashOn
        M42 P2 S0
        if global.signalFlashOn
            M42 P4 S1
        else
            M42 P4 S0
    elif state.status == "processing" || state.status == "resuming" || state.status == "busy"
        ; Solid green while job is running
        set global.signalFlashOn = false
        M42 P2 S1
        M42 P4 S0
    elif state.status == "idle"
        ; Flash green = ready / standby
        set global.signalFlashOn = !global.signalFlashOn
        M42 P4 S0
        if global.signalFlashOn
            M42 P2 S1
        else
            M42 P2 S0
    else
        set global.signalFlashOn = false
        M42 P2 S0
        M42 P4 S0

    G4 S0.2   ; Small delay to prevent overloading
