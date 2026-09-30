# EQ Beta UI Copy

https://eq-beta-ui-copy.onrender.com

A web page that renames EverQuest character INI files from a Live install so the server piece of each filename is `beta`. The result is a zip in your Downloads folder. The zip includes `readme.txt` with the steps for pasting those files into the EverQuest Beta folder, and for copying a custom UI by hand.

There is no program to install. Open the site in Chrome or Edge. The download is a zip of INI files and a text file.

Selected INI files are uploaded for that one request, renamed in memory, and discarded. They are not saved on the server.

The free server sleeps after about 15 minutes without a visit. The next visit wakes it, which takes about a minute.

## Use it

1. Close EverQuest and EverQuest Beta.
2. Open https://eq-beta-ui-copy.onrender.com in Chrome or Edge.
3. Choose **Browse Live folder**. Open your EverQuest folder, paste the search shown on the page into the search box, press Ctrl+A, then Open. Only character INI files are kept. Maps, sounds, and the rest of the game folder stay on your PC.
4. Check the servers you want to see. More than one server can be shown at once. Then check the characters you want. Each checked character includes its UI, hotkey, and persona INI files. Hidden characters stay checked.
5. Choose **Download zip**. `eq-beta-files.zip` saves to your Downloads folder.
6. Open the zip and follow `readme.txt`. Copy the renamed INI files into the EverQuest Beta folder, and copy the `userdata` folder into `EverQuest Beta\userdata`. Replace files that are already there.
7. If you use a custom UI, copy `EverQuest\uifiles` into `EverQuest Beta\uifiles` yourself. Those files are not in the zip.

Example: `UI_Bob_Vox_WAR.ini` becomes `UI_Bob_beta_WAR.ini`.
