
; General
G90 ; absolute coordinates
M83 ; relative extruder moves
M550 P"Indyprinter3" ; set hostname
 
M552 S1 P192.168.100.100
M553 P255.255.255.0  ; Subnet mask

; Wait a moment for the CAN expansion boards to become available
G4 S2

; Closed-Loop Drivers
M569.1 P70.0 T3 E5:9 R100 I0 D0 ; driver 70.0 has a magnetic encoder
M569.1 P71.0 T3 E5:9 R100 I0 D0 ; driver 71.0 has a magnetic encoder
M569.1 P72.0 T3 E5:9 R100 I0 D0 ; driver 72.0 has a magnetic encoder
M569.1 P73.0 T3 E2:4 R100 I0 D0 ; driver 73.0 has a magnetic encoder
M569.1 P74.0 T3 E2:4 R100 I0 D0 ; driver 73.0 has a magnetic encoder
M569.1 P75.0 T3 E2:4 R100 I0 D0 ; driver 73.0 has a magnetic encoder

; Smart Drivers
M569 P70.0 S0 D5 ; driver 70.0 goes backwards (X axis)
M569 P71.0 S0 D5 ; driver 71.0 goes backwards (Y axis)
M569 P72.0 S0 D5 ; driver 72.0 goes backwards (Z axis)
M569 P73.0 S0 D5 ; driver 73.0 goes backwards (Z axis)
M569 P74.0 S0 D5 ; driver 74.0 goes backwards (Z axis)
M569 P75.0 S0 D5 ; driver 73.0 goes backwards (Z axis)

; Simple Drivers
M569 P1.0 S1 D3  ; driver 1.0 goes forwards (E axis)

; Motor Idle Current Reduction
M906 I30 ; set motor current idle factor
M84 S30 ; set motor current idle timeout

; Axes
M584 X71.0 Y70.0 Z72.0:73.0:74.0:75.0 E1.0; map extruder to new stepper driver
M350 X16 Y16 Z16 E16 I1
M906 X3500 Y3500 Z2500 E4000
M92 X32.41 Y32.61 Z1600 E420; configure steps per mm
M208 X0:550 Y0:550 Z0:500 ; set minimum and maximum axis limits

M566 X2000 Y2000 Z20 E1000; set maximum instantaneous speed changes (mm/min)
M203 X8000 Y8000 Z250 E16000; set maximum speeds (mm/min)
M201 X750 Y750 Z20 E1000; set accelerations (mm/s^2)

; Temp sensors
M308 S0 P"temp0" Y"thermistor" A"Heated Bed" T100000 B4725 C7.06e-8 ; Bed sensor
M308 S1 P"1.temp0" Y"pt1000" A"Bandheater" W2 F50     ; configure sensor #1
M308 S2 P"1.temp1" Y"pt1000" A"Nozzle" W2 F50 ; configure sensor #2
M308 S3 P"1.temp2" Y"pt1000" A"Inlet"              ; configure sensor #3
M308 S7 P"1.io2.in" Y"linear-analog" A"Feeder" ; configure hopper sensor


; Heaters
M950 H0 C"out1" T0                ; create bed heater
M143 H0 P0 T0 C0 S140 A0          ; configure heater monitor #0 for bed heater
M307 H0 R0.2 D5.5 E1.35 K0.56 B1  ; configure model of bed heater

M950 H2 C"1.out7" T2              ; create heater #2
M143 H2 P0 T1 C0 S285 A0          ; configure heater monitor #0 for heater #2
M307 H2 R0.5 D5.5 E1.35 K0.56 B1 ; configure model of heater #2

M950 H1 C"1.out6" T1              ; create heater #1
M143 H1 P0 T1 C0 S285 A0          ; configure heater monitor #0 for heater #1
M307 H1 R0.5 D5.5 E1.35 K0.56 B1 ; configure model of heater #1

; Fan
M950 F0 C"!1.out3+out3.tach"   ; create fan #0
M106 P0 C"Tool" S0 L0 X1 B0.1 ; configure fan #0

; Heated beds
M140 P0 H0                        ; configure heated bed

; Kinematics
M669 X1:-1:0 Y-1:-1:0 K1

; Endstops
M574 X1 P"!io0.in" S1 ; configure X axis endstop
M574 Y1 P"!io2.in" S1 ; configure Y axis endstop
M574 Z1 P"!io3.in" S1 ; configure Z axis endstop

; Tools
M563 P0 D0 H1:2 F0 ; create tool #0
M568 P0 R0 S0      ; set initial tool #0 active and standby temperatures to 0C

; Pins
M950 P0 C"out2"
M950 P1 C"out7" ; Waterpomp
M950 P2 C"out8"
M950 P3 C"out3" ; Feeder

global waterTemp = 60
global pelletFeeding = false

; Miscellaneous
T0 ; select first tool
