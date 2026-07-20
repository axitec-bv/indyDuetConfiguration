M291 R"Motor stalled" P"Motor stalled! Reset printer"
M98 P"/sys/signal-fault.g"  ; latch red before halt (daemon will stop)
M112 ; E-stop
