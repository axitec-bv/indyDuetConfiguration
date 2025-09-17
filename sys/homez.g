; home Z
G91                                                     ; relative positioning
var maxTravel = move.axes[2].max - move.axes[2].min + 5 ; calculate how far Z can travel plus 5mm
G1 H1 Z{-var.maxTravel} F300                            ; coarse home in the -Z direction
G1 Z5 F6000                                             ; move back 5mm
G1 H1 Z{-var.maxTravel} F300                            ; fine home in the -Z direction
G90                                                     ; absolute positioning