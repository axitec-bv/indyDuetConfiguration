; increase Z
G91                                                     ; relative positioning
G1 H2 Z5                                                ; move Z relative to current position to avoid dragging nozzle over the bed
G90                                                     ; absolute positioning

; home X
G91                                                     ; relative positioning
var maxTravel = move.axes[0].max - move.axes[0].min + 5 ; calculate how far X can travel plus 5mm
G1 H1 X{-var.maxTravel} F2000                            ; coarse home in the -X direction
G1 X5 F6000                                             ; move back 5mm
G1 H1 X{-var.maxTravel} F300                            ; fine home in the -X direction
G90                                                     ; absolute positioning

; decrease Z again
G91                                                     ; relative positioning
G1 H2 Z-5 F6000                                         ; move Z relative to current position
G90                                                     ; absolute positioning