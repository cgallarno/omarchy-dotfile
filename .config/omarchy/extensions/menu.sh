# User overrides for omarchy-menu (sourced at the end of the stock script).

# System menu: stock options plus "Windows" (one-shot reboot into Windows).
show_system_menu() {
  local options="󱄄  Screensaver\n  Lock"
  ! omarchy-toggle-enabled suspend-off && options="$options\n󰒲  Suspend"
  omarchy-hibernation-available && options="$options\n󰤁  Hibernate"
  options="$options\n󰍃  Logout\n󰜉  Restart\n󰍹  Windows\n󰐥  Shutdown"

  case $(menu "System" "$options") in
  *Screensaver*) omarchy-launch-screensaver force ;;
  *Lock*) omarchy-system-lock ;;
  *Suspend*) systemctl suspend ;;
  *Hibernate*) systemctl hibernate ;;
  *Logout*) omarchy-system-logout ;;
  *Restart*) omarchy-system-reboot ;;
  *Windows*) "$HOME/.local/bin/reboot-windows" ;;
  *Shutdown*) omarchy-system-shutdown ;;
  *) back_to show_main_menu ;;
  esac
}
