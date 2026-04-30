---
name: Change-Linux-Root-Password
description: >
  This skill outlines two methods to change the root password in Linux: one when you have the current password, and another when you need to reset it without the current password.
license: MIT
compatibility: Requires bash
metadata:
  author: your-name
  version: "1.0"
triggers:
  - change-root-password
  - linux-password
---

# Skill Content

## How to Change the Root Password in Linux

### Method 1: If you have the current root password

1.  **Open a terminal window**: Press `Ctrl+Alt+T` to open a new terminal window with a command prompt.
    *   If you're not using a desktop environment, you're already at a command prompt, so proceed to the next step.
2.  **Type `su` at the command prompt**: Press `↵ Enter`. This will open a `Password:` line below the command prompt.
3.  **Type the current root password**: Press `↵ Enter`. When the password is accepted, you will be brought back to the command prompt as the root user.
    *   If you type the password incorrectly, run `su` and try again.
    *   Passwords are case-sensitive.
4.  **Type `passwd`**: Press `↵ Enter`. An `Enter new UNIX password:` line will appear below the prompt.
5.  **Type a new password**: Press `↵ Enter`. The password you type will not appear on the screen.
6.  **Retype the new password**: Press `↵ Enter`. You will see a message that reads “password updated successfully.”
7.  **Type `exit`**: Press `↵ Enter`. This will log you out of the root account.
8.  **Restart your computer**.

### Method 2: If you don't have access to the current root password (via Grub menu)

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
