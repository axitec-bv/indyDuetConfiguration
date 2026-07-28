; heater-fault.g — RRF event handler when a heater monitor trips.
; Params: param.D = heater number, param.P = fault type code, param.B = CAN board,
;         param.S = full description (same as DWC popup).
;
; Heater is already switched off before this macro runs. Tower red is driven live
; from heat.heaters[].state in daemon.g (clears automatically after M562).

M118 P0 L2 S{"Heater fault H" ^ param.D ^ ": " ^ param.S}

M291 R"Heater fault" P{param.S}

M42 P2 S0  ; SL_G off
M42 P4 S1  ; SL_R on until daemon loop / fault cleared

if state.status == "processing" || state.status == "resuming" || state.status == "pausing"
    M25
