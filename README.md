# Obsidian Notes Conversion
This script can be use to prepare your obsidian notes for being published online. I did search for such a script online when I started keeping my own website, but I could not find any. I hope this helps :)

This script:
- converts wiki-links to standard links. 
- moves anything other than the notes to another folder and fixes the links that point to them. This folder is named `assets` by default
- ensures an empty line exists before and after equations, code blcoks, etc.

You can use the script with
```bash
python convert.py input_folder output_folder --no-generate-excerpts
```
The easiest way is to just copy your entire Obsidian vault somewhere and pass that as the input folder.

**_Note_**: Make sure to use a copy of your vault to prevent any unpected tampering with the original files.

## How to use AI excerpts
You can use an API key to generate exceprts for your notes. In this case, you just have to create a `.env` file in your directory with your API key inside. After that, you can use the AI excerpt feature with
```bash
python convert.py input_folder output_folder --generate-excerpts
```