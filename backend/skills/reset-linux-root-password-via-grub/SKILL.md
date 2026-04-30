---
name: Reset-Linux-Root-Password-via-Grub
description: >
  This skill describes how to reset a forgotten Linux root password by booting into single-user mode through the Grub menu.
license: MIT
compatibility: Requires bash
metadata:
  author: your-name
  version: "1.0"
triggers:
  - reset-root-password
  - grub-reset
---

# Skill Content

## How to Reset the Linux Root Password (if you don't have access to the current root password)

1.  **Restart your Linux computer**.
2.  **Press `E` at the Grub menu**: The Grub menu appears right after you turn on the computer. In most cases, it only stays on the screen for a few moments.
    *   If you don’t press `E` before the Grub menu disappears, reboot and try again.
    *   This method works for most popular Linux distributions (Ubuntu, CentOS 7, Debian). If you’re not able to get to single-user mode with this method, check your distribution’s website for instructions specific to your system.
3.  **Scroll to the line that begins with `linux /boot`**: Use the `↑` and `↓` keys to do so. This is the line you will need to modify in order to boot into single-user mode.
    *   In CentOS and some other distributions, the line may begin with `linux16` rather than `linux`.
4.  **Move the cursor to the end of the line**: Use the `→`, `←`, `↑`, and `↓` keys to place the cursor right after `ro`.
5.  **Type `init=/bin/bash` after `ro`**: The end of the line should now look like this: `ro init=/bin/bash`. Note the space between `ro` and `init=/bin/bash`.
6.  **Press `Ctrl+X`**: This tells the system to boot directly to a root-level command prompt in single-user mode.
7.  **Type `mount –o remount,rw /` at the prompt**: Press `↵ Enter`. This mounts the file system in read-write mode.
8.  **Type `passwd` at the prompt**: Press `↵ Enter`. Since booting into single-user mode gives you root access, there is no need to pass additional parameters to the `passwd` command.
9.  **Type a new root password**: Press `↵ Enter`. The characters you type will not be displayed on the screen. This is normal.
10. **Retype the new password**: Press `↵ Enter`. When the system confirms you’ve re-entered the same password, you will see a message that reads “password updated successfully.”
11. **Type `reboot –f`**: Press `↵ Enter`. This command reboots the system normally.
