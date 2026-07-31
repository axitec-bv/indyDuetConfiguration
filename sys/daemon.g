; daemon.g
; Self-restarting daemon (RRF 3.5+). config-sync hot-swaps this file by renaming the running
; copy to daemon.g.bak before uploading a new version. The loop below exits as soon as that
; .bak appears, letting RRF load the new daemon.g, which deletes the leftover .bak on startup.
; (First deploy of this version still needs one reboot; after that updates apply without reboot.)
;
; GPIO / dwell use {expression} form so RRF does not sync daemon commands to the motion
; queue during long manual extrusions or slow moves (see Duet forum #31714).
;
; Signal lights (IEC 60073-style):
;   Green 0.5 Hz    = idle / ready (standby or print finished — remove product)
;   Green 1 Hz      = printing / busy, all OK
;   Red flashing    = problem during a job (pause / attention)
;   Solid red       = fault, machine not available
; Flash timing uses state.upTime so rates stay accurate independent of loop delay.
if fileexists("/sys/daemon.g.bak")
    M472 P"/sys/daemon.g.bak"  ; remove leftover backup so this instance keeps running

while !fileexists("/sys/daemon.g.bak")

    ; --- Water temperature control ---
    if exists(sensors.analog[3])
        if sensors.analog[3].lastReading > global.waterTemp
            M42 P{1} S{1}  ; pump on
        elif sensors.analog[3].lastReading < global.waterTemp - 0.2
            M42 P{1} S{0}  ; pump off
    else
        M42 P{1} S{0}  ; fail-safe: pump off

    ; --- Pellet feeder control ---
    if exists(sensors.analog[7])
        if sensors.analog[7].lastReading > 85 && global.pelletFeeding
            M42 P{3} S{1}
        elif sensors.analog[7].lastReading < 85 || !global.pelletFeeding
            M42 P{3} S{0}
    else
        M42 P{3} S{0}

    ; --- Signal lights (P2/out8 = SL_G green, P4/out9 = SL_R red) ---
    if !exists(global.signalForceFault)
        global signalForceFault = false
    if !exists(global.printFinished)
        global printFinished = false
    if !exists(global.wasPrinting)
        global wasPrinting = false

    if !exists(global.heaterFaultActive)
        global heaterFaultActive = false

    ; Live heater fault flag — clears automatically when M562 / fault reset (not latched)
    if (exists(heat.heaters[0]) && heat.heaters[0].state == "fault") || (exists(heat.heaters[1]) && heat.heaters[1].state == "fault") || (exists(heat.heaters[2]) && heat.heaters[2].state == "fault")
        set global.heaterFaultActive = true
    else
        set global.heaterFaultActive = false

    ; Drop stale signalForceFault latched by an earlier heater fault (M562 / fault cleared)
    if !exists(global.lastHeaterFaultActive)
        global lastHeaterFaultActive = false
    if global.lastHeaterFaultActive && !global.heaterFaultActive
        set global.signalForceFault = false
    set global.lastHeaterFaultActive = global.heaterFaultActive

    ; Track job lifecycle: processing -> idle means "print finished / remove product"
    if state.status == "processing" || state.status == "resuming"
        set global.wasPrinting = true
        set global.printFinished = false
    elif state.status == "idle" && global.wasPrinting
        set global.printFinished = true
        set global.wasPrinting = false

    ; signalForceFault = latched faults (stall, CAN loss, manual test); heaterFaultActive = live
    ; 1 Hz = 0.5s on/off via upTime*2; 0.5 Hz = 1s on/off via upTime
    if (global.signalForceFault || global.heaterFaultActive) && !(state.status == "processing" || state.status == "paused" || state.status == "pausing" || state.status == "resuming")
        ; Not printing + fault: solid red (machine unavailable)
        M42 P{2} S{0}
        M42 P{4} S{1}
    elif global.signalForceFault || global.heaterFaultActive || state.status == "paused" || state.status == "pausing"
        ; Problem during a job: flash red @ 1 Hz
        M42 P{2} S{0}
        if mod(floor(state.upTime * 2), 2) = 0
            M42 P{4} S{1}
        else
            M42 P{4} S{0}
    elif state.status == "processing" || state.status == "resuming" || state.status == "busy"
        ; Printing / long manual move: flash green @ 1 Hz
        M42 P{4} S{0}
        if mod(floor(state.upTime * 2), 2) = 0
            M42 P{2} S{1}
        else
            M42 P{2} S{0}
    elif state.status == "idle"
        ; Idle / ready / print finished: slow flash green @ 0.5 Hz
        M42 P{4} S{0}
        if mod(floor(state.upTime), 2) = 0
            M42 P{2} S{1}
        else
            M42 P{2} S{0}
    else
        M42 P{2} S{0}
        M42 P{4} S{0}

    G4 P{200}   ; 200 ms between loops — expression form avoids motion sync
