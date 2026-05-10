import os
import re
import frontmatter
from datetime import datetime
import argparse
import shutil
from dotenv import load_dotenv
from groq import Groq

# Load environment variables from .env file
load_dotenv()

GROQ_MODEL = "llama-3.3-70b-versatile"

# API key is loaded from GROQ_API_KEY environment variable (from .env or system env)
client = Groq()

# slugify text
def slugify(text):
    text = text.lower().replace(' ', '-')
    return re.sub(r'[^a-z0-9\-]', '', text)

def convert_obsidian_links(content, current_note_path, vault_root, asset_prefix="/assets"):
    def clean_asset_path(path):
        path = path.replace('\\', '/')
        return path.lstrip('/')

    def replacer(match):
        link_content = match.group(1)

        # This is the signature of wiki-links
        if '|' in link_content:
            target, display = link_content.split('|', 1)
        else:
            target = display = link_content

        if '#' in target:       # In this case, the link refers to one of the headers of the current note
            target, anchor = target.split('#', 1)
            anchor = f'#{slugify(anchor)}'
        else:
            anchor = ''

        # External links
        if target.startswith("http://") or target.startswith("https://"):
            return f'[{display}]({target}{anchor})'

        # Non-markdown files (assets). These will all be moved into a separate 'assets' folder by default
        ext = os.path.splitext(target)[-1].lower()
        if ext and ext != '.md':
            abs_path = os.path.normpath(os.path.join(os.path.dirname(current_note_path), target))
            rel_path = os.path.relpath(abs_path, vault_root).replace('\\', '/')
            if ext in ['.png', '.jpg', '.jpeg', '.gif']:
                return f'![{display}]({asset_prefix}/{clean_asset_path(rel_path)})'
            else:
                return f'[{display}]({asset_prefix}/{clean_asset_path(rel_path)})'

        # Internal notes
        # find file anywhere in vault
        target_name = f"{target.strip()}.md"
        found_path = None

        for root, _, files in os.walk(vault_root):
            for f in files:
                if f.lower() == target_name.lower():
                    found_path = os.path.join(root, f)
                    break
            if found_path:
                break

        if found_path:
            rel_path = os.path.splitext(os.path.relpath(found_path, vault_root))[0]
            parts = rel_path.replace('\\', '/').split('/')
            # Keep folder names as-is, slugify only filename
            folders = parts[:-1]
            note_name = parts[-1]  # Keep original filename
            jekyll_path = '/'.join(folders + [note_name])
            return f'[{display}](/notes/{jekyll_path}/{anchor})' if anchor else f'[{display}](/notes/{jekyll_path}/)'
        else:
            # Could not find file, just slugify everything
            parts = target.strip().replace('\\', '/').split('/')
            folders = parts[:-1]
            note_slug = slugify(parts[-1])
            jekyll_path = '/'.join(folders + [note_slug])
            return f'[{display}](/notes/{jekyll_path}/{anchor})' if anchor else f'[{display}](/notes/{jekyll_path}/)'

    # Replace Obsidian-style links
    content = re.sub(r'!\[\[([^\]\[]+)\]\]', replacer, content)
    content = re.sub(r'\[\[([^\]\[]+)\]\]', replacer, content)

    # Replace standard markdown image links
    def std_img_replacer(m):
        alt_text = m.group(1)
        raw_path = m.group(2).replace('\\', '/')
        
        # Skip if already has asset prefix or is an absolute URL/path
        if raw_path.startswith(asset_prefix) or raw_path.startswith('http') or raw_path.startswith('/'):
            return m.group(0)  # Return unchanged
            
        abs_img_path = os.path.normpath(os.path.join(os.path.dirname(current_note_path), raw_path))
        rel_img_path = os.path.relpath(abs_img_path, vault_root).replace('\\', '/')
        return f'![{alt_text}]({asset_prefix}/{clean_asset_path(rel_img_path)})'

    content = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', std_img_replacer, content)

    # Standard markdown file links (e.g., PDFs)
    def std_file_replacer(m):
        text = m.group(1)
        raw_path = m.group(2).replace('\\', '/')
        
        # Skip if already has asset prefix or is an absolute URL/path
        if raw_path.startswith(asset_prefix) or raw_path.startswith('http') or raw_path.startswith('/'):
            return m.group(0)  # Return unchanged
            
        abs_file_path = os.path.normpath(os.path.join(os.path.dirname(current_note_path), raw_path))
        rel_file_path = os.path.relpath(abs_file_path, vault_root).replace('\\', '/')
        return f'[{text}]({asset_prefix}/{clean_asset_path(rel_file_path)})'

    content = re.sub(
        r'\[([^\]]+)\]\(([^)]+\.(?:png|jpg|jpeg|gif|pdf|docx|pptx))\)',
        std_file_replacer,
        content
    )

    return content


def process_note(input_path, output_root, vault_root, asset_prefix="/assets", generate_excerpts=True):
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()

    try:
        post = frontmatter.loads(content)
    except Exception:
        post = frontmatter.Post(content)

    try:
        date_str = re.search(r'(\d{4}-\d{2}-\d{2})', os.path.basename(input_path)).group(1)
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except Exception:
        date = datetime.fromtimestamp(os.path.getmtime(input_path))

    filename_title = os.path.splitext(os.path.basename(input_path))[0]
    post.metadata['title'] = filename_title

    if generate_excerpts:
        ai_excerpt = generate_excerpt_with_ai(post.content, filename_title)
        if ai_excerpt:
            post.metadata['excerpt'] = ai_excerpt
        else:
            # Fallback to using the first paragraph as excerpt
            first_para = re.search(r'^\s*([^\n]+)', post.content, re.MULTILINE)
            post.metadata['excerpt'] = first_para.group(1).strip() if first_para else ""
    else:
        # Fallback to using the first paragraph as excerpt
        first_para = re.search(r'^\s*([^\n]+)', post.content, re.MULTILINE)
        post.metadata['excerpt'] = first_para.group(1).strip() if first_para else ""

    if 'layout' not in post.metadata or post.metadata['layout'] == 'post':
        post.metadata['layout'] = 'note'

    post.metadata['date'] = date.strftime('%Y-%m-%d')

    # Convert Obsidian links
    post.content = convert_obsidian_links(post.content, input_path, vault_root, asset_prefix)
    
    # Ensure hashtags have proper spacing after them
    post.content = fix_hashtag_spacing(post.content)
    
    # Fix math equation spacing
    post.content = fix_math_equations(post.content)
    
    # Fix code block spacing
    post.content = fix_code_block_spacing(post.content)

    rel_path = os.path.relpath(input_path, vault_root)
    output_path = os.path.join(output_root, '_notes', os.path.splitext(rel_path)[0] + '.md')
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("---\n")
        f.write(f"layout: {post.metadata.get('layout', 'note')}\n")
        f.write(f"title: \"{post.metadata['title']}\"\n")
        f.write(f"date: {post.metadata['date']}\n")
        if post.metadata.get('excerpt'):
            f.write(f"excerpt: \"{post.metadata['excerpt']}\"\n")
        f.write("---\n\n")
        f.write(post.content)

def copy_assets(vault_root, output_root):
    asset_root = os.path.join(output_root, 'assets')
    for root, _, files in os.walk(vault_root):
        for file in files:
            if not file.endswith('.md'):
                src_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_path, vault_root)
                dest_path = os.path.join(asset_root, rel_path)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                shutil.copy2(src_path, dest_path)

def _sanitize_for_yaml_line(s: str) -> str:
    if not s:
        return ""
    s = s.strip().replace('\n', ' ')
    s = s.replace('"', '\\"') 
    return s

def generate_excerpt_with_ai(content: str, title: str = "") -> str | None:
    try:
        prompt = (
            "Write a short excerpt (max 2 sentences, under 200 characters) for the note below. "
            "Style: neutral, informative, like a textbook or encyclopedia sidebar. "
            "The goal is to spark curiosity by stating the key idea clearly and concisely. "
            "Do NOT use hype or storytelling intros. "
            "Never start with: 'Did you know', 'In the world of', 'Here is', 'Discover', 'Imagine'. "
            "No filler phrases. No quotes, markdown, or headings.\n\n"
            f"Title: {title}\n\n"
            "Note:\n"
            f"{content[:8000]}"
        )

        print("⚡ Sending prompt to Groq…")   # DEBUG
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            timeout=30.0,  # 30 second timeout
        )

        print("✅ Got response from Groq")   # DEBUG
        excerpt = (resp.choices[0].message.content or "").strip()

        excerpt = clean_excerpt(excerpt)

        # Remove quotes completely
        excerpt = excerpt.replace('"', '').replace("'", "")
        
        # Sanitize for YAML (single-line, no newlines)
        excerpt = _sanitize_for_yaml_line(excerpt)[:240]

        print(f"📝 Excerpt generated: {excerpt}")   # DEBUG
        return excerpt or None
    except Exception as e:
        print(f"❌ AI excerpt failed: {type(e).__name__}: {e}")  # DEBUG full error
        return None
    

def clean_excerpt(raw: str) -> str:
    """
    Cleans model output so we never get intros like 'Here is...' or 'Did you know...'
    """
    bad_starts = [
        "here is", "here's", "did you know", "in the world",
        "discover", "imagine", "what happens", "can a", "this intriguing"
    ]
    excerpt = raw.strip()

    # Lowercase for checking
    lower = excerpt.lower()

    # Remove unwanted prefix phrases
    for phrase in bad_starts:
        if lower.startswith(phrase):
            # Remove everything before the first colon or dash if present
            if ":" in excerpt:
                excerpt = excerpt.split(":", 1)[1].strip()
            elif "-" in excerpt[:50]:  # some intros use "—"
                excerpt = excerpt.split("-", 1)[1].strip()
            else:
                # fallback: drop first 5 words
                excerpt = " ".join(excerpt.split()[5:]).strip()
            break

    # Ensure <=200 chars, cut at last full stop if needed
    if len(excerpt) > 200:
        cutoff = excerpt[:200].rfind(".")
        excerpt = excerpt[:cutoff+1] if cutoff != -1 else excerpt[:200]

    return excerpt


def fix_math_equations(content: str) -> str:
    """
    Ensures $$ display math blocks have blank lines before and after them.
    This is required for proper rendering in Jekyll.
    """
    lines = content.split('\n')
    result = []
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        # Check if line contains $$
        if '$$' in line:
            # Check if $$ is at the start or end of line (display math)
            stripped = line.strip()
            if stripped == '$$' or stripped.startswith('$$') or stripped.endswith('$$'):
                # Ensure blank line before (if not at start and previous line isn't blank)
                if result and result[-1].strip() != '':
                    result.append('')
                
                result.append(line)
                
                # If this is opening $$, find the closing one
                if stripped == '$$' or (stripped.startswith('$$') and not stripped.endswith('$$')):
                    i += 1
                    # Add lines until we find closing $$
                    while i < len(lines):
                        result.append(lines[i])
                        if '$$' in lines[i]:
                            break
                        i += 1
                
                # Ensure blank line after (if not at end and next line isn't blank)
                if i + 1 < len(lines) and lines[i + 1].strip() != '':
                    result.append('')
            else:
                # Inline math, keep as is
                result.append(line)
        else:
            result.append(line)
        
        i += 1
    
    return '\n'.join(result)


def fix_hashtag_spacing(content: str) -> str:
    """
    Ensures that if content starts with Obsidian hashtags (#tag1 #tag2),
    there's a blank line after them before the main body text starts.
    """
    lines = content.split('\n')
    
    if not lines:
        return content
    
    # Check if first non-empty line contains hashtags
    first_line_idx = None
    for i, line in enumerate(lines):
        if line.strip():
            first_line_idx = i
            break
    
    if first_line_idx is None:
        return content
    
    first_line = lines[first_line_idx].strip()
    
    # Check if it's a hashtag line (starts with # and all words are hashtags)
    if first_line.startswith('#') and all(word.startswith('#') or word == '' for word in first_line.split()):
        # This is a hashtag line
        # Check if the next non-empty line exists and isn't blank
        if first_line_idx + 1 < len(lines):
            next_line = lines[first_line_idx + 1] if first_line_idx + 1 < len(lines) else ''
            
            # If next line is not blank, insert a blank line
            if next_line.strip() != '':
                lines.insert(first_line_idx + 1, '')
    
    return '\n'.join(lines)


def fix_code_block_spacing(content: str) -> str:
    """
    Ensures code blocks (```) have blank lines before and after them.
    This is required for proper rendering in Jekyll/kramdown.
    """
    lines = content.split('\n')
    result = []
    i = 0
    in_code_block = False
    
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # Check if line contains ``` (code block delimiter)
        if stripped.startswith('```'):
            if not in_code_block:
                # Opening code block - ensure blank line before
                if result and result[-1].strip() != '':
                    result.append('')
                result.append(line)
                in_code_block = True
            else:
                # Closing code block
                result.append(line)
                # Ensure blank line after (if not at end)
                if i + 1 < len(lines) and lines[i + 1].strip() != '':
                    result.append('')
                in_code_block = False
        else:
            result.append(line)
        
        i += 1
    
    return '\n'.join(result)


def main():
    parser = argparse.ArgumentParser(description='Convert Obsidian to Jekyll Collection with correct asset links')
    parser.add_argument('vault_dir', help='Root of Obsidian vault')
    parser.add_argument('output_dir', help='Jekyll site root')
    parser.add_argument('--generate-excerpts', action='store_true', default=True, 
                        help='Generate AI excerpts for notes (default: enabled)')
    parser.add_argument('--no-generate-excerpts', dest='generate_excerpts', action='store_false',
                        help='Disable AI excerpt generation and use first paragraph instead')
    args = parser.parse_args()

    copy_assets(args.vault_dir, args.output_dir)

    for root, _, files in os.walk(args.vault_dir):
        for file in files:
            if file.endswith('.md'):
                process_note(
                    os.path.join(root, file),
                    args.output_dir,
                    args.vault_dir,
                    generate_excerpts=args.generate_excerpts
                )

    print("✅ Conversion complete! Notes saved to _notes/, assets copied to /assets/")


if __name__ == '__main__':
    # Test AI excerpt generation. Use for debugging
    # sample_excerpt = generate_excerpt_with_ai("Sample content for testing.", "Sample Title")
    # print("AI excerpt test output:", sample_excerpt)

    main()
