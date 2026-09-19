REM a flow when you have a folder full of images like "Pasted image 20250201014038.jpg" --> 01 02 03 04 (7 days in a virtual, not calendar, week) > 2025-01-01, -02 etc. (created date from the title)

py org.py pullup --yes
python org.py date --by title --into y-m-d --name-date y-m-d --yes
python org.py chunks --dirs --size 7 --sort name --yes
