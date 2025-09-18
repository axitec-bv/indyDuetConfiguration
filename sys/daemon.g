; Test loop for temperature and pump control
while true

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

    G4 S0.2   ; Small delay to prevent overloading
