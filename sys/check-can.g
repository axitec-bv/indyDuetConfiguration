; check-can.g
; Verify expected CAN boards are present and running.
;
; WHY: expansion-timeout.g only fires when a board that was communicating drops.
; A board that never comes online at boot produces no timeout event — this check
; closes that gap (bring-up incomplete, wrong address, unpowered motor, etc.).
;
; Expected:
;   1        expansion (extruder / heaters / tool I/O)
;   70, 71   CoreXY
;   72-75    Z (front left, front right, back left, back right)
;
; Sets global.canBoardsOffline to "" when OK, else a short description.
; Aborts only when global.canCheckAbort is true (startup / manual M98).

if !exists(global.canCheckAbort)
    global canCheckAbort = true
if !exists(global.canBoardsOffline)
    global canBoardsOffline = ""

var required = {1, 70, 71, 72, 73, 74, 75}
var offline = ""

while iterations < #var.required
    var addr = var.required[iterations]
    var found = false
    var i = 0
    while var.i < #boards
        if boards[var.i].canAddress = var.addr
            if boards[var.i].state = "running"
                set var.found = true
            else
                set var.offline = var.offline ^ " B" ^ var.addr ^ "(" ^ boards[var.i].state ^ ")"
            ; end if
        ; end if
        set var.i = var.i + 1
    ; end while
    if !var.found
        set var.offline = var.offline ^ " B" ^ var.addr ^ "(missing)"
    ; end if
; end while

set global.canBoardsOffline = var.offline

if var.offline != ""
    echo {"CAN boards offline:" ^ var.offline}
    if global.canCheckAbort
        abort {"CAN boards offline:" ^ var.offline}
    ; end if
elif global.canCheckAbort
    echo "All CAN boards OK (1, 70-75)"
; end if
