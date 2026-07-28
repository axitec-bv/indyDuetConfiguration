; heater-fault.g — RRF event handler when a heater monitor trips.
; Params: param.D = heater number, param.P = fault type code, param.B = CAN board,
;         param.S = full description (same as DWC popup).
;
; Heater is already switched off before this macro runs. Latch tower red via
; signal-fault.g; pause SD print if a job is active (replaces default handler).

M118 P0 L2 S{"Heater fault H" ^ param.D ^ ": " ^ param.S}

M291 R"Heater fault" P{param.S}

M98 P"/sys/signal-fault.g"

if state.status == "processing" || state.status == "resuming" || state.status == "pausing"
    M25
