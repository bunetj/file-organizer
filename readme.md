# automatic organization by date and type

## usage

```
usage: org.py [-h]
              {ext,chunks,date,pullup,rm-empty,undo} ...

Organize a folder in place. Files only, unless
stated.

positional arguments:
  {ext,chunks,date,pullup,rm-empty,undo}
    ext                 move files into type folders
    chunks              split files (or folders)
                        into numbered folders
    date                group by date and/or prefix
                        filenames
    pullup              move all files from
                        subfolders up to this folder
    rm-empty            delete empty subfolders
    undo                reverse the last journal in
                        a folder

options:
  -h, --help            show this help message and
                        exit

See each command's --help for details.
```

## cases

fill folders.txt and the script will organize them by date.

- obsidian: `pasted image 20251111111111.jpg`
- days: 2025-01-01/ etc --> 01/ 7 "days" inside (not a real calendar week)

