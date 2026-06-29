; expansion-timeout.g
; Raised when a CAN expansion board stops communicating (RRF 3.5.0-beta.4 and later).
;
; WHY THIS FILE EXISTS:
; Without this macro the firmware default for an expansion timeout is
; "inform the user and continue printing". On this machine the Z axis runs on
; CAN closed-loop boards (drivers 72-75) while the extruder and heaters run on a
; different CAN board (1.x). If a motion board drops off CAN, a default "continue"
; lets the extruder and heaters keep running while the tool no longer moves,
; extruding material in one spot. This macro stops the printer instead.
;
; Macro parameters passed by RRF:
;   param.B = CAN address of the board that stopped communicating
;   param.D = device number (0 for expansion-timeout)
;   param.S = full human-readable description of the event
M291 R"CAN communication lost" P{"Expansion board (CAN address " ^ param.B ^ ") stopped responding. Printer halted - reset required. " ^ param.S}
M112 ; emergency stop: turns off all heaters and motors and halts the print
