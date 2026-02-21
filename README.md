# Anna's Archive Ebook Search & Download

A Claude Code skill and CLI tool for searching and downloading ebooks from [Anna's Archive](https://annas-archive.li).

## Features

- Search by title, author, or both
- Filter by format (PDF, EPUB, MOBI, AZW3, DJVU)
- Download via fast API with membership key
- Automatic mirror fallback when primary domain is down
- Verify search results against expected titles
- No external dependencies (stdlib only)

## Prerequisites

**Downloads require an Anna's Archive membership key.**

1. Get a membership at https://annas-archive.li/donate
2. Set your API key:
   ```bash
   export ANNAS_ARCHIVE_KEY="your-key-here"
   ```

Search works without a key. Downloads will fail without one.

## Usage

### Search for books

```bash
python3 annas.py search "Clean Code Robert Martin" --format pdf --limit 5
```

### Get book details

```bash
python3 annas.py details adb5293cf369256a883718e71d3771c3
```

### Download a book

```bash
python3 annas.py download adb5293cf369256a883718e71d3771c3 --output ./books/
```

### Verify a match

```bash
python3 annas.py search "Design Patterns" --verify "Design Patterns"
```

### Check API key

```bash
python3 annas.py check-key
```

## As a Claude Code Skill

Drop the `SKILL.md` and `annas.py` files into your Claude Code skills directory to use this as an AI-assisted ebook lookup tool. The skill triggers on book lookups, ebook downloads, and related queries.

## Format Priority

When no format is specified: `pdf > epub > mobi > azw3 > djvu`

## Mirror Fallback

The tool automatically tries multiple mirrors if the primary domain is unreachable:

1. annas-archive.li (primary)
2. annas-archive.gl
3. annas-archive.in
4. annas-archive.pm

If all known mirrors fail, it checks the status page at https://open-slum.pages.dev/ to discover new domains automatically.

## Troubleshooting

### SSL Certificate Error on macOS

If you see `[SSL: CERTIFICATE_VERIFY_FAILED]`:

```bash
pip3 install certifi
python3 -c "import certifi; print(certifi.where())"
# Add to ~/.zshrc:
export SSL_CERT_FILE=/path/from/above/cacert.pem
```

## License

MIT
