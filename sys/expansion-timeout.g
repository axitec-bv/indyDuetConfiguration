; expansion-timeout.g
; Raised when a CAN expansion board stops communicating (RRF 3.5.0-beta.4 and later).
;
; WHY THIS FILE EXISTS:
; Without this macro the firmware default for an expansion timeout is
; "inform the user and continue printing". On this machine the Z axis runs on
; CAN closed-loop boards (drivers 72-75) while the extruder and heaters run on a
; different CAN board (1.x). If a motion board drops off CAN during a job, a
; default "continue" lets the extruder and heaters keep running while the tool
; no longer moves, extruding material in one spot.
;
; WHY NOT ALWAYS M112:
; Readdressing a closed-loop board (e.g. factory 123 -> 74) intentionally makes
; the old CAN address disappear. That also raises this event. Unconditional M112
; then halt/reset-loops the machine during bring-up before all boards are online.
; Only emergency-stop when a job is active; warn and continue while idle.
;
; Macro parameters passed by RRF:
;   param.B = CAN address of the board that stopped communicating
;   param.D = device number (0 for expansion-timeout)
;   param.S = full human-readable description of the event

if state.status == "processing" || state.status == "paused" || state.status == "pausing" || state.status == "resuming"
    M291 R"CAN communication lost" P{"Expansion board (CAN address " ^ param.B ^ ") stopped responding during a job. Printer halted - reset required. " ^ param.S}
    M98 P"/sys/signal-fault.g"  ; latch red before halt (daemon will stop)
    M112 ; emergency stop: turns off all heaters and motors and halts the print
else
    ; Idle / bring-up / board readdress: do not halt the machine
    M118 P0 L2 S{"CAN expansion timeout ignored (idle): board " ^ param.B ^ ". " ^ param.S}
