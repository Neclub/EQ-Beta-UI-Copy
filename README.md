# EQ Beta UI Copy

A small web page that renames EverQuest character INI files from a Live install so the server piece of each filename is `beta`. The result is a zip in your Downloads folder. The zip includes `readme.txt` with the steps for pasting those files into the EverQuest Beta folder, and for copying a custom UI by hand.

There is no program to install. Open the site in Chrome or Edge. Windows Defender is not asked to trust an executable. The download is a zip of INI files and a text file.

Selected INI files are uploaded for that one request, renamed in memory, and discarded. They are not saved on the server.

## Use it

1. Close EverQuest and EverQuest Beta.
2. Open the site in Chrome or Edge. If it has been idle, the first load can take about a minute while the free server wakes up.
3. Choose **Browse Live folder**. On your own computer that opens a folder window. On the website, open your EverQuest folder, paste the search shown on the page into the search box, press Ctrl+A, then Open. Only character INI files are kept. Maps, sounds, and the rest of the game folder stay on your PC.
4. Check the servers you want to see. More than one server can be shown at once. Then check the characters you want. Each checked character includes its UI, hotkey, and persona INI files. Hidden characters stay checked.
5. Choose **Download zip**. `eq-beta-files.zip` saves to your Downloads folder.
6. Open the zip and follow `readme.txt`. Copy the renamed INI files into the EverQuest Beta folder, and copy the `userdata` folder into `EverQuest Beta\userdata`. Replace files that are already there.
7. If you use a custom UI, copy `EverQuest\uifiles` into `EverQuest Beta\uifiles` yourself. Those files are not in the zip.

Example: `UI_Bob_Vox_WAR.ini` becomes `UI_Bob_beta_WAR.ini`.

## Run it on your computer

```bash
pip install -r requirements.txt
python app.py
```

On Windows, if `python` is not available, use `py -3 app.py`.

Open http://127.0.0.1:5000 in Chrome or Edge.

## Deploy on Render (free)

This site is hosted the same way as [EQGM-Web](https://github.com/Neclub/EQGM-Web) ([eqgm-web.onrender.com](https://eqgm-web.onrender.com)): a public GitHub repo and a free Render web service from `render.yaml`.

1. This repository is [Neclub/EQ-Beta-UI-Copy](https://github.com/Neclub/EQ-Beta-UI-Copy).
2. In [Render](https://render.com/), **New → Blueprint** (uses `render.yaml`) or **New → Web Service** and connect **this** repo.
3. Settings if creating manually:
   - **Runtime:** Python
   - **Build:** `pip install -r requirements.txt`
   - **Start:** `gunicorn app:app --timeout 120 --bind 0.0.0.0:$PORT`
   - **Plan:** Free
4. After deploy, open https://eq-beta-ui-copy.onrender.com.

The free web service sleeps after about 15 minutes without a visit. The next visit wakes it, which takes about a minute. That fits a tool you use once a year.
